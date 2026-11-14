"""Explicit modeled spending adjustments, never mutations to actual rows."""
from decimal import Decimal, InvalidOperation
from .money import rounded
from .ledger import transactions, account_scope, fact_id, month_bounds
from .classification import TRANSFER_TYPES
from .state import mutate, new_id, now


def _scenario(conn,customer_id,scenario_id):
    row=conn.execute('SELECT * FROM scenarios WHERE id=? AND customer_id=?',(scenario_id,customer_id)).fetchone()
    if row is None: raise ValueError('Unknown scenario in customer scope')
    return dict(row)


def preview_spending_adjustment(conn,customer_id,start,end,category='Restaurants',percent=20):
    """Calculate an unsaved category adjustment from observed rows."""
    if (start,end)!=month_bounds(start[:7]): raise ValueError('Monthly scenario requires one complete calendar month')
    try:
        percentage=Decimal(str(percent))
    except InvalidOperation as error:
        raise ValueError('Invalid scenario percent') from error
    if not percentage.is_finite() or not 0<=percentage<=100: raise ValueError('Percent must be 0–100')
    rows=transactions(conn,customer_id,start,end,{'category':category})
    if any(r['role']!='discretionary' or r['transaction_type'] in TRANSFER_TYPES for r in rows): raise ValueError('Default adjustment requires eligible discretionary spending')
    if not rows: raise ValueError('No eligible rows')
    selected=[r for r in rows if r['amount_cents']<0 and r['transaction_type'] not in TRANSFER_TYPES]
    base=-sum(r['amount_cents'] for r in selected)
    refs=[r['transaction_ref'] for r in selected]
    return {**account_scope(conn,customer_id),'start':start,'end':end,'category':category,'percent':str(percentage),'actual_total_cents':base,'adjustable_base_cents':base,'modeled_monthly_contribution_cents':rounded(Decimal(base)*percentage/100),'transaction_refs':refs,'formula':'adjustable_base × percent / 100, round half up','label':'Planning preview — modeled monthly contribution','scenario':True,'observed':False,'persistence':'not_saved','fact_id':fact_id('scenario-preview',customer_id,start,end,category,str(percentage),refs)}


def create_scenario(conn,customer_id,start,end,category='Restaurants',percent=20,name='Spending adjustment',provenance='user'):
    preview=preview_spending_adjustment(conn,customer_id,start,end,category,percent)
    row={'id':new_id('scenario'),'customer_id':customer_id,'name':name,'start':start,'end':end,'category':category,'percent':preview['percent'],'goal_id':None,'created_at':now()}
    def apply(): conn.execute('INSERT INTO scenarios VALUES(?,?,?,?,?,?,?,?,?)',tuple(row.values()))
    _,audit=mutate(conn,customer_id,'create_scenario',row['id'],apply,provenance)
    return {**scenario_result(conn,customer_id,row['id']),'audit_event':audit}


def scenario_result(conn,customer_id,scenario_id):
    scenario=_scenario(conn,customer_id,scenario_id)
    rows=[r for r in transactions(conn,customer_id,scenario['start'],scenario['end'],{'category':scenario['category']}) if r['amount_cents']<0 and r['transaction_type'] not in TRANSFER_TYPES]
    excluded=[r[0] for r in conn.execute('SELECT transaction_ref FROM scenario_exclusions WHERE scenario_id=? ORDER BY transaction_ref',(scenario_id,))]
    ineligible=[r['transaction_ref'] for r in rows if r['role']!='discretionary']
    included=[r for r in rows if r['transaction_ref'] not in excluded and r['role']=='discretionary']
    base=-sum(r['amount_cents'] for r in included)
    eligibility='invalid' if not included else ('stale' if ineligible else 'eligible')
    return {**scenario,**account_scope(conn,customer_id),'actual_total_cents':-sum(r['amount_cents'] for r in rows),'adjustable_base_cents':base,'modeled_monthly_contribution_cents':rounded(Decimal(base)*Decimal(scenario['percent'])/100),'excluded_transaction_refs':excluded,'ineligible_transaction_refs':ineligible,'eligibility_status':eligibility,'transaction_refs':[r['transaction_ref'] for r in included],'actual_transaction_refs':[r['transaction_ref'] for r in rows],'formula':'adjustable_base × percent / 100, round half up','label':'Planning scenario — modeled monthly contribution','observed':False,'fact_id':fact_id('scenario',scenario_id,base,excluded,ineligible,scenario['percent'])}


def exclude_from_scenario(conn,customer_id,scenario_id,transaction_ref,provenance='user'):
    scenario=_scenario(conn,customer_id,scenario_id)
    actual=scenario_result(conn,customer_id,scenario_id)
    if transaction_ref not in actual['actual_transaction_refs']: raise ValueError('Row outside scenario base')
    if transaction_ref in actual['excluded_transaction_refs']: raise ValueError('Row already excluded')
    def apply(): conn.execute('INSERT INTO scenario_exclusions VALUES(?,?,?,?)',(new_id('exclusion'),customer_id,scenario_id,transaction_ref))
    _,audit=mutate(conn,customer_id,'exclude_from_scenario',scenario_id,apply,provenance)
    return {**scenario_result(conn,customer_id,scenario_id),'audit_event':audit}
