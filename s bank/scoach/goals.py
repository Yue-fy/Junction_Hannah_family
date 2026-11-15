"""One reserve-aware goal engine for all user-selected templates."""
from datetime import date
from .analytics import money_map, latest_complete_month
from .ledger import account_scope, month_bounds, shift_month, fact_id, transactions
from .money import median_cents
from .state import mutate, new_id, now
from .scenarios import _scenario, scenario_result

TEMPLATES={'buffer','spending','purchase','vehicle','home','trip','custom'}


def _reference(conn,customer_id,as_of):
    scope=account_scope(conn,customer_id)
    reference=date.fromisoformat(as_of or scope['observed_end'])
    if reference.isoformat()<scope['observed_start']:
        raise ValueError('No observed balance by the goal reference date')
    return reference


def _months_remaining(as_of,target):
    return (target.year-as_of.year)*12+target.month-as_of.month


def _validate_goal_fields(reference,name,target_cents,target_date,current_saved_cents,reserve_floor_cents,template,check_target_date=True):
    """Shared create/update validation; raises ValueError with the user-facing reason."""
    if not isinstance(target_date,str): raise ValueError('Goal target date must be an ISO date')
    target=date.fromisoformat(target_date)
    if not isinstance(name,str) or not name.strip() or len(name)>120: raise ValueError('Goal name required, up to 120 characters')
    if template not in TEMPLATES: raise ValueError('Unknown template')
    if any(type(v) is not int for v in (target_cents,current_saved_cents,reserve_floor_cents)) or target_cents<=0 or min(current_saved_cents,reserve_floor_cents)<0: raise ValueError('Goal inputs must be nonnegative integer cents, target positive')
    if check_target_date and (target<=reference or _months_remaining(reference,target)<1): raise ValueError('Goal target must be at least one calendar month ahead')


def create_goal(conn,customer_id,name,target_cents,target_date,current_saved_cents=0,reserve_floor_cents=0,template='custom',as_of=None,provenance='user'):
    reference=_reference(conn,customer_id,as_of)
    _validate_goal_fields(reference,name,target_cents,target_date,current_saved_cents,reserve_floor_cents,template)
    goal={'id':new_id('goal'),'customer_id':customer_id,'name':name.strip(),'target_cents':target_cents,'target_date':target_date,'current_saved_cents':current_saved_cents,'reserve_floor_cents':reserve_floor_cents,'template':template,'created_at':now()}
    def apply(): conn.execute('INSERT INTO goals VALUES(?,?,?,?,?,?,?,?,?)',tuple(goal.values()))
    _,audit=mutate(conn,customer_id,'create_goal',goal['id'],apply,provenance)
    return {**goal_plan(conn,customer_id,goal['id'],as_of),'audit_event':audit}


def goal_plan(conn,customer_id,goal_id,as_of=None):
    raw=conn.execute('SELECT * FROM goals WHERE id=? AND customer_id=?',(goal_id,customer_id)).fetchone()
    if raw is None: raise ValueError('Unknown goal in customer scope')
    goal=dict(raw); reference=_reference(conn,customer_id,as_of); target=date.fromisoformat(goal['target_date'])
    months=max(_months_remaining(reference,target),0); remaining=max(goal['target_cents']-goal['current_saved_cents'],0)
    required=(remaining+months-1)//months if months else (0 if not remaining else None)
    month=reference.strftime('%Y-%m')
    if reference.isoformat()<month_bounds(month)[1]: month=shift_month(month,-1)
    latest=latest_complete_month(conn,customer_id); month=min(month,latest)
    scope=account_scope(conn,customer_id)
    periods=[shift_month(month,i) for i in range(-5,1)]
    cashflows=[money_map(conn,customer_id,period) for period in periods if scope['observed_start'][:7]<=period<=scope['observed_end'][:7]]
    capacity_available=len(cashflows)==6
    # Typical (median) monthly left-over after consumption and committed saving transfers.
    capacity=max(median_cents([m['free_cashflow_cents'] for m in cashflows]),0) if capacity_available else 0
    latest_balance=transactions(conn,customer_id,end=reference.isoformat())[-1]['balance_after_cents']
    plan=_spending_plan(conn,customer_id,reference.isoformat())
    # What could go to the goal now is the spending plan's "could be saved" amount, the same
    # number Spending and Coach show, never the whole balance above a reserve.
    upfront=min(plan['extra_cents'],max(latest_balance-goal['reserve_floor_cents'],0))
    after_now=max(remaining-upfront,0)
    monthly_after_now=(after_now+months-1)//months if months else (0 if not after_now else None)
    links=[scenario_result(conn,customer_id,r[0]) for r in conn.execute('SELECT id FROM scenarios WHERE goal_id=? AND customer_id=? ORDER BY created_at,id',(goal_id,customer_id))]
    # One active scenario per goal. Legacy multiple links use the latest, never a sum.
    active=links[-1] if links else None
    modeled=min(active['modeled_monthly_contribution_cents'],remaining) if active else 0
    gap=max(monthly_after_now-capacity,0) if monthly_after_now is not None else None
    return {**goal,**account_scope(conn,customer_id),'as_of':reference.isoformat(),'remaining_cents':remaining,'months_remaining':months,'required_monthly_cents':required,
            'conservative_monthly_contribution_cents':capacity,'typical_monthly_left_over_cents':capacity,'capacity_available':capacity_available,
            'upfront_available_cents':upfront,'could_save_now_cents':plan['extra_cents'],'required_monthly_after_now_cents':monthly_after_now,
            'monthly_gap_cents':gap,'reserve_floor_cents':goal['reserve_floor_cents'],
            'spending_plan':{'as_of':plan['as_of'],'next_payday':plan['next_payday'],'free_cents':plan['free_cents'],'spendable_until_payday_cents':plan['spendable_until_payday_cents'],'extra_cents':plan['extra_cents'],'fact_id':plan['fact_id']},
            'cashflow_months':cashflows,'modeled_scenario_contribution_cents':modeled,'linked_scenarios':links,'active_scenario_id':active['id'] if active else None,'inactive_linked_scenario_ids':[s['id'] for s in links[:-1]],'scenario_contribution_cap_cents':remaining,'label':'Planning scenario — not promised savings','observed':False,'transaction_refs':[ref for m in cashflows for ref in m['transaction_refs']],'fact_id':fact_id('goal',goal_id,reference.isoformat(),capacity,upfront,modeled),
            'assumptions':['Monthly left-over is the median of six complete months after spending and regular saving transfers','What could go to the goal now is the spending plan\'s money that could be saved, after bills, everyday costs and a cushion until payday','Several goals share the same money that could be saved; it is not split automatically','Modeled adjustment is separate from existing contribution capacity']}


def _spending_plan(conn,customer_id,as_of):
    from .forecast import spending_plan
    from . import money_profile
    profile=money_profile.get_profile(conn,customer_id,as_of)
    return spending_plan(conn,customer_id,as_of=as_of,profile=None if profile['empty'] else money_profile.planning_inputs(profile,as_of))


def link_scenario_to_goal(conn,customer_id,goal_id,scenario_id,as_of=None,provenance='user'):
    goal_plan(conn,customer_id,goal_id,as_of); _scenario(conn,customer_id,scenario_id)
    def apply():
        if conn.execute('SELECT 1 FROM scenarios WHERE goal_id=? AND customer_id=?',(goal_id,customer_id)).fetchone():
            raise ValueError('Goal already has an active linked scenario; undo its link first')
        changed=conn.execute('UPDATE scenarios SET goal_id=? WHERE id=? AND customer_id=? AND goal_id IS NULL',(goal_id,scenario_id,customer_id))
        if changed.rowcount!=1:
            raise ValueError('Scenario is already linked to a goal; undo its link first')
    _,audit=mutate(conn,customer_id,'link_scenario_to_goal',goal_id,apply,provenance)
    return {**goal_plan(conn,customer_id,goal_id,as_of),'audit_event':audit}


UPDATABLE_GOAL_FIELDS=('name','target_cents','target_date','current_saved_cents','reserve_floor_cents')


def _goal_row(conn,customer_id,goal_id):
    raw=conn.execute('SELECT * FROM goals WHERE id=? AND customer_id=?',(goal_id,customer_id)).fetchone()
    if raw is None: raise ValueError('Unknown goal in customer scope')
    return dict(raw)


def update_goal(conn,customer_id,goal_id,fields,provenance='user',as_of=None):
    """Change fields of an existing goal, audited and undoable via state.undo_last (/api/undo).

    Args:
        conn: sqlite3 connection.
        customer_id: owner; a goal of another customer is rejected as unknown.
        goal_id: goal id (e.g. 'goal:...').
        fields: non-empty dict with any of name (str, 1-120 chars), target_cents
            (int > 0), target_date (ISO date at least one calendar month after the
            reference date), current_saved_cents (int >= 0), reserve_floor_cents
            (int >= 0). Same validation as create_goal; target_date is only
            date-checked when it is being changed. Unknown keys raise ValueError.
        provenance: 'user' | 'deterministic' | 'gemini_proposed_user_confirmed'.
        as_of: optional ISO reference date (default: last observed day).

    Returns:
        goal_plan(...) dict for the updated goal plus 'changed_fields' (list of
        field names whose value changed), 'previous' (the goal row before the
        change) and 'audit_event' (the audit_events row; action 'update_goal',
        scope goal_id, before/after JSON snapshots).
    Raises ValueError without writing anything (no goal change, no audit row).
    """
    if not isinstance(fields,dict) or not fields: raise ValueError('fields must be a non-empty dict')
    unknown=set(fields)-set(UPDATABLE_GOAL_FIELDS)
    if unknown: raise ValueError('Unsupported goal field: '+', '.join(sorted(unknown)))
    current=_goal_row(conn,customer_id,goal_id); reference=_reference(conn,customer_id,as_of)
    merged={**current,**fields}
    _validate_goal_fields(reference,merged['name'],merged['target_cents'],merged['target_date'],merged['current_saved_cents'],merged['reserve_floor_cents'],merged['template'],check_target_date='target_date' in fields)
    merged['name']=merged['name'].strip()
    changed=[k for k in UPDATABLE_GOAL_FIELDS if merged[k]!=current[k]]
    def apply():
        conn.execute('UPDATE goals SET name=?,target_cents=?,target_date=?,current_saved_cents=?,reserve_floor_cents=? WHERE id=? AND customer_id=?',(merged['name'],merged['target_cents'],merged['target_date'],merged['current_saved_cents'],merged['reserve_floor_cents'],goal_id,customer_id))
    _,audit=mutate(conn,customer_id,'update_goal',goal_id,apply,provenance)
    return {**goal_plan(conn,customer_id,goal_id,as_of),'changed_fields':changed,'previous':current,'audit_event':audit}


def delete_goal(conn,customer_id,goal_id,provenance='user'):
    """Delete a goal and unlink its scenarios in one audited transaction (undoable via /api/undo).

    Scenarios linked to the goal are kept but get goal_id = NULL. The audit
    before-state (full coach-state snapshot) contains the goal and the linked
    scenarios, so state.undo_last restores both the goal and the links.

    Args:
        conn, customer_id, goal_id: as update_goal; unknown or other customer's
            goal raises ValueError without writing.
        provenance: 'user' | 'deterministic' | 'gemini_proposed_user_confirmed'.

    Returns:
        {'deleted_goal_id': str, 'goal': dict (row before deletion),
         'unlinked_scenario_ids': [str], 'audit_event': dict (action
         'delete_goal', scope goal_id)}.
    """
    goal=_goal_row(conn,customer_id,goal_id)
    linked=[r[0] for r in conn.execute('SELECT id FROM scenarios WHERE goal_id=? AND customer_id=? ORDER BY created_at,id',(goal_id,customer_id))]
    def apply():
        conn.execute('UPDATE scenarios SET goal_id=NULL WHERE goal_id=? AND customer_id=?',(goal_id,customer_id))
        if conn.execute('DELETE FROM goals WHERE id=? AND customer_id=?',(goal_id,customer_id)).rowcount!=1:
            raise ValueError('Unknown goal in customer scope')
    _,audit=mutate(conn,customer_id,'delete_goal',goal_id,apply,provenance)
    return {'deleted_goal_id':goal_id,'goal':goal,'unlinked_scenario_ids':linked,'audit_event':audit}
