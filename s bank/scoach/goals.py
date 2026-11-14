"""One reserve-aware goal engine for all user-selected templates."""
from datetime import date
from .analytics import money_map, latest_complete_month, _available
from .ledger import account_scope, month_bounds, shift_month, fact_id, transactions
from .money import percentile_cents
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


def create_goal(conn,customer_id,name,target_cents,target_date,current_saved_cents=0,reserve_floor_cents=0,template='custom',as_of=None,provenance='user'):
    reference=_reference(conn,customer_id,as_of); target=date.fromisoformat(target_date)
    if not isinstance(name,str) or not name.strip() or len(name)>120: raise ValueError('Goal name required, up to 120 characters')
    if template not in TEMPLATES: raise ValueError('Unknown template')
    if any(type(v) is not int for v in (target_cents,current_saved_cents,reserve_floor_cents)) or target_cents<=0 or min(current_saved_cents,reserve_floor_cents)<0: raise ValueError('Goal inputs must be nonnegative integer cents, target positive')
    if target<=reference or _months_remaining(reference,target)<1: raise ValueError('Goal target must be at least one calendar month ahead')
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
    cashflows=[money_map(conn,customer_id,shift_month(month,i)) for i in range(-5,1) if _available(conn,shift_month(month,i))]
    capacity_available=len(cashflows)==6
    capacity=max(percentile_cents([m['free_cashflow_cents'] for m in cashflows],.25),0) if capacity_available else 0
    latest_balance=transactions(conn,customer_id,end=reference.isoformat())[-1]['balance_after_cents']
    links=[scenario_result(conn,customer_id,r[0]) for r in conn.execute('SELECT id FROM scenarios WHERE goal_id=? AND customer_id=? ORDER BY created_at,id',(goal_id,customer_id))]
    # One active scenario per goal. Legacy multiple links use the latest, never a sum.
    active=links[-1] if links else None
    modeled=min(active['modeled_monthly_contribution_cents'],remaining) if active else 0
    return {**goal,**account_scope(conn,customer_id),'as_of':reference.isoformat(),'remaining_cents':remaining,'months_remaining':months,'required_monthly_cents':required,'conservative_monthly_contribution_cents':capacity,'capacity_available':capacity_available,'monthly_gap_cents':max(required-capacity,0) if required is not None else None,'reserve_floor_cents':goal['reserve_floor_cents'],'upfront_available_cents':max(latest_balance-goal['reserve_floor_cents'],0),'cashflow_months':cashflows,'modeled_scenario_contribution_cents':modeled,'linked_scenarios':links,'active_scenario_id':active['id'] if active else None,'inactive_linked_scenario_ids':[s['id'] for s in links[:-1]],'scenario_contribution_cap_cents':remaining,'label':'Planning scenario — not promised savings','observed':False,'transaction_refs':[ref for m in cashflows for ref in m['transaction_refs']],'fact_id':fact_id('goal',goal_id,reference.isoformat(),capacity,modeled),'assumptions':['Six complete months; nearest-rank P25 free cash flow','Committed saving transfers reduce monthly capacity','Protected reserve reduces upfront availability; upfront is not assigned automatically','Modeled adjustment is separate from existing contribution capacity']}


def link_scenario_to_goal(conn,customer_id,goal_id,scenario_id,as_of=None,provenance='user'):
    goal_plan(conn,customer_id,goal_id,as_of); _scenario(conn,customer_id,scenario_id)
    def apply():
        if conn.execute('SELECT 1 FROM scenarios WHERE goal_id=? AND customer_id=?',(goal_id,customer_id)).fetchone():
            raise ValueError('Goal already has an active linked scenario; undo its link first')
        conn.execute('UPDATE scenarios SET goal_id=? WHERE id=?',(goal_id,scenario_id))
    _,audit=mutate(conn,customer_id,'link_scenario_to_goal',goal_id,apply,provenance)
    return {**goal_plan(conn,customer_id,goal_id,as_of),'audit_event':audit}
