"""Deterministic comparisons, literacy flows and robust review candidates."""
from decimal import Decimal
from .money import rounded, median_cents, percentile_cents
from .ledger import transactions, account_scope, month_bounds, shift_month, fact_id
from .classification import TRANSFER_TYPES, COMMITTED_TYPES


def _coverage(conn):
    low,high=conn.execute('SELECT min(date),max(date) FROM transactions').fetchone()
    return low[:7],high[:7]


def _available(conn,month):
    low,high=_coverage(conn)
    return low<=month<=high


def latest_complete_month(conn, customer_id):
    # Source documentation guarantees coverage through the last calendar day.
    return account_scope(conn,customer_id)['observed_end'][:7]


def summarize(rows):
    selected=[r for r in rows if r['amount_cents']<0 and r['transaction_type'] not in TRANSFER_TYPES]
    total=-sum(r['amount_cents'] for r in selected)
    return {'total_cents':total,'count':len(selected),'average_cents':rounded(Decimal(total)/len(selected)) if selected else None,'transaction_refs':[r['transaction_ref'] for r in selected]}


def month_summary(conn, customer_id, month, filters=None):
    start,end=month_bounds(month); scope=account_scope(conn,customer_id)
    if not _available(conn,month): raise ValueError('Month outside observed dataset coverage')
    rows=transactions(conn,customer_id,start,end,filters)
    result={**scope,**summarize(rows),'month':month,'start':start,'end':end,'observed':True}
    result['fact_id']=fact_id('month',customer_id,month,filters,result['transaction_refs'])
    return result


def money_map(conn, customer_id, month=None):
    month=month or latest_complete_month(conn,customer_id); start,end=month_bounds(month)
    if not _available(conn,month): raise ValueError('Month outside observed dataset coverage')
    rows=transactions(conn,customer_id,start,end); all_rows=transactions(conn,customer_id)
    salary=sum(r['amount_cents'] for r in rows if r['transaction_type']=='salary')
    other=sum(r['amount_cents'] for r in rows if r['transaction_type']=='other_income')
    committed=-sum(min(r['amount_cents'],0) for r in rows if r['transaction_type'] in COMMITTED_TYPES)
    consumption=-sum(min(r['amount_cents'],0) for r in rows if r['transaction_type'] in ('purchase','utilities_payment','housing_payment'))
    flows=[]
    for role in ('income','fixed_obligation','flexible_essential','discretionary','saving_or_transfer','needs_review'):
        group=[r for r in rows if r['role']==role]
        flows.append({'role':role,'amount_cents':sum(r['amount_cents'] for r in group),'transaction_refs':[r['transaction_ref'] for r in group],'fact_id':fact_id('flow',customer_id,month,role,[r['transaction_ref'] for r in group])})
    result={**account_scope(conn,customer_id),'month':month,'start':start,'end':end,'salary_cents':salary,'other_income_cents':other,'consumption_cents':consumption,'committed_saving_transfers_cents':committed,'transfer_net_cents':sum(r['amount_cents'] for r in rows if r['transaction_type'] in TRANSFER_TYPES),'free_cashflow_cents':salary+other-consumption-committed,'latest_balance_cents':all_rows[-1]['balance_after_cents'],'latest_balance_date':all_rows[-1]['date'],'latest_balance_transaction_ref':all_rows[-1]['transaction_ref'],'flows':flows,'transaction_refs':[r['transaction_ref'] for r in rows],'observed':True}
    result['fixed_cost_share']=str(Decimal(-sum(min(r['amount_cents'],0) for r in rows if r['role']=='fixed_obligation'))/Decimal(salary+other)) if salary+other>0 else None
    result['fact_id']=fact_id('map',customer_id,month,result['transaction_refs'])
    return result


def _complete(conn,customer_id,start,end):
    if (start,end)!=month_bounds(start[:7]): raise ValueError('Comparison requires complete calendar months')
    coverage=conn.execute('SELECT min(date),max(date) FROM transactions').fetchone()
    # Opening rows need not fall on day one; use documented source calendar coverage.
    if start[:7]<coverage[0][:7] or end[:7]>coverage[1][:7]: raise ValueError('Period outside observed coverage')


def compare_periods(conn, customer_id, start, end, comparison_start, comparison_end, filters=None):
    _complete(conn,customer_id,start,end); _complete(conn,customer_id,comparison_start,comparison_end)
    current=month_summary(conn,customer_id,start[:7],filters); previous=month_summary(conn,customer_id,comparison_start[:7],filters)
    delta=current['total_cents']-previous['total_cents']; count_delta=current['count']-previous['count']
    # Symmetric decomposition sums to the exact change before display rounding.
    count_effect=size_effect=None
    if current['count'] and previous['count']:
        ca=Decimal(current['total_cents'])/current['count']; pa=Decimal(previous['total_cents'])/previous['count']
        count_effect=rounded(Decimal(count_delta)*(ca+pa)/2); size_effect=delta-count_effect
    return {**account_scope(conn,customer_id),'current':current,'previous':previous,'delta_cents':delta,'count_delta':count_delta,'count_effect_cents':count_effect,'average_size_effect_cents':size_effect,'transaction_refs':previous['transaction_refs']+current['transaction_refs'],'fact_id':fact_id('comparison',current['fact_id'],previous['fact_id']),'observed':True}


def trend_series(conn, customer_id, end_month=None, months=12, filters=None):
    if not isinstance(months,int) or not 1<=months<=24: raise ValueError('months must be 1–24')
    end_month=end_month or latest_complete_month(conn,customer_id)
    month_bounds(end_month)
    if not _available(conn,end_month): raise ValueError('Month outside observed dataset coverage')
    def summary(month):
        if _available(conn,month): return {**month_summary(conn,customer_id,month,filters),'available':True}
        return {'month':month,'available':False,'total_cents':None,'count':None,'average_cents':None,'transaction_refs':[],'observed':True}
    series=[summary(shift_month(end_month,i)) for i in range(-months+1,1)]
    previous=summary(shift_month(end_month,-12)); current=series[-1]
    baseline=[summary(shift_month(end_month,i)) for i in range(-6,0)]
    salary_maps=[money_map(conn,customer_id,shift_month(end_month,i)) for i in range(-8,1) if _available(conn,shift_month(end_month,i))]
    all_months=[summary(shift_month(end_month,i)) for i in range(-23,1)]
    annual={'available':all(m['available'] for m in all_months),'label':'Trailing 12 complete months versus preceding 12 complete months'}
    if annual['available']:
        for key,group in [('current',all_months[12:]),('previous',all_months[:12])]:
            refs=[ref for m in group for ref in m['transaction_refs']]
            annual[key]={'start':month_bounds(group[0]['month'])[0],'end':month_bounds(group[-1]['month'])[1],'total_cents':sum(m['total_cents'] for m in group),'count':sum(m['count'] for m in group),'transaction_refs':refs,'fact_id':fact_id('annual',customer_id,[m['fact_id'] for m in group])}
        annual['delta_cents']=annual['current']['total_cents']-annual['previous']['total_cents']
        annual['fact_id']=fact_id('annual-comparison',annual['current']['fact_id'],annual['previous']['fact_id'])
    refs=[ref for m in all_months for ref in m['transaction_refs']]
    return {**account_scope(conn,customer_id),'months':series,'same_month_previous_year':previous,'year_over_year_delta_cents':current['total_cents']-previous['total_cents'] if previous['available'] else None,'annual_comparison':annual,'trailing_six_median_cents':median_cents([m['total_cents'] for m in baseline]) if all(m['available'] for m in baseline) else None,'recent_three_salary_median_cents':median_cents([m['salary_cents'] for m in salary_maps[-3:]]) if len(salary_maps)>=3 else None,'prior_six_salary_median_cents':median_cents([m['salary_cents'] for m in salary_maps[:6]]) if len(salary_maps)==9 else None,'salary_transaction_refs':[ref for m in salary_maps for ref in m['transaction_refs']],'other_income_separate':True,'transaction_refs':refs,'fact_id':fact_id('trend',customer_id,end_month,filters,refs),'observed':True}


def investment_cashflows(conn, customer_id, end_month=None, months=12):
    """Summarize observed investment-related bank transfers, never portfolio value."""
    if type(months) is not int or not 1 <= months <= 24:
        raise ValueError('months must be 1–24')
    end_month = end_month or latest_complete_month(conn, customer_id)
    month_bounds(end_month)
    scope = account_scope(conn, customer_id)
    if not scope['observed_start'][:7] <= end_month <= scope['observed_end'][:7]:
        raise ValueError('Month outside observed dataset coverage')
    start_month = shift_month(end_month, -months + 1)
    start, end = month_bounds(start_month)[0], month_bounds(end_month)[1]
    rows = transactions(conn, customer_id, start, end)
    relevant = [row for row in rows if row['transaction_type'] in TRANSFER_TYPES]

    def monthly(month):
        selected = [row for row in relevant if row['date'].startswith(month)]
        deposits = -sum(min(row['amount_cents'], 0) for row in selected if row['transaction_type'] == 'investment_deposit')
        sweeps = -sum(min(row['amount_cents'], 0) for row in selected if row['transaction_type'] == 'salary_sweep')
        withdrawals = sum(max(row['amount_cents'], 0) for row in selected if row['transaction_type'] == 'investment_withdrawal')
        refs = [row['transaction_ref'] for row in selected]
        return {
            'month': month,
            'investment_deposits_cents': deposits,
            'salary_sweeps_cents': sweeps,
            'total_contributions_cents': deposits + sweeps,
            'withdrawals_cents': withdrawals,
            'net_contributions_cents': deposits + sweeps - withdrawals,
            'account_cashflow_cents': sum(row['amount_cents'] for row in selected),
            'transaction_refs': refs,
            'fact_id': fact_id('investment-month', customer_id, month, refs),
            'observed': True,
        }

    series = [monthly(shift_month(start_month, offset)) for offset in range(months)]
    deposits = sum(row['investment_deposits_cents'] for row in series)
    sweeps = sum(row['salary_sweeps_cents'] for row in series)
    contributions = deposits + sweeps
    withdrawals = sum(row['withdrawals_cents'] for row in series)
    salary = sum(max(row['amount_cents'], 0) for row in rows if row['transaction_type'] == 'salary')
    refs = [row['transaction_ref'] for row in relevant]
    result = {
        **scope,
        'start_month': start_month,
        'end_month': end_month,
        'period_months': months,
        'investment_deposits_cents': deposits,
        'salary_sweeps_cents': sweeps,
        'total_contributions_cents': contributions,
        'withdrawals_cents': withdrawals,
        'net_contributions_cents': contributions - withdrawals,
        'account_cashflow_cents': sum(row['amount_cents'] for row in relevant),
        'salary_cents': salary,
        'contribution_share_of_salary_basis_points': rounded(Decimal(contributions) * 10000 / salary) if salary else None,
        'contribution_months': sum(row['total_contributions_cents'] > 0 for row in series),
        'withdrawal_months': sum(row['withdrawals_cents'] > 0 for row in series),
        'months': series,
        'transaction_refs': refs,
        'label': 'Observed investment cash flows — not portfolio performance',
        'limitations': [
            'The transaction data shows transfers only, not holdings, market value, fees, risk, or returns',
            'No investment recommendation is made',
        ],
        'observed': True,
    }
    result['fact_id'] = fact_id('investment-cashflows', customer_id, start_month, end_month, refs)
    return result


def unusual_candidates(conn, customer_id, month=None):
    month=month or latest_complete_month(conn,customer_id); start,end=month_bounds(month)
    history_start=shift_month(month,-12)+'-01'
    prior=[r for r in transactions(conn,customer_id,history_start,start) if r['date']<start and r['transaction_type']=='purchase' and r['amount_cents']<0]
    monthly=[]
    for i in range(-12,0):
        m=shift_month(month,i); monthly.append(-sum(r['amount_cents'] for r in prior if r['date'].startswith(m)))
    monthly_median=median_cents(monthly); result=[]
    for row in transactions(conn,customer_id,start,end):
        if row['transaction_type']!='purchase' or row['amount_cents']>=0: continue
        group=[-r['amount_cents'] for r in prior if r['category']==row['category']]
        if len(group)<10: continue
        med=median_cents(group); q1=percentile_cents(group,.25); q3=percentile_cents(group,.75); mad=median_cents([abs(v-med) for v in group])
        cutoff=max(Decimal(q3)+Decimal('1.5')*(q3-q1),Decimal(med)+Decimal(3)*Decimal('1.4826')*mad,Decimal(10000),Decimal('.1')*monthly_median)
        if Decimal(-row['amount_cents'])<=cutoff: continue
        result.append({'candidate_id':fact_id('unusual',row['transaction_ref']),'fact_id':fact_id('unusual',row['transaction_ref']),'customer_id':customer_id,'account_id':row['account_id'],'amount_cents':-row['amount_cents'],'category':row['category'],'date':row['date'],'cutoff_cents':int(cutoff),'cutoff_exact_cents':str(cutoff),'prior_count':len(group),'prior_start':history_start,'prior_end':shift_month(month,-1)+'-'+month_bounds(shift_month(month,-1))[1][-2:],'median_cents':med,'q1_cents':q1,'q3_cents':q3,'mad_cents':mad,'transaction_refs':[row['transaction_ref']],'comparison_transaction_refs':[r['transaction_ref'] for r in prior if r['category']==row['category']],'label':'unusual for you — review prompt','observed':True})
    return result
