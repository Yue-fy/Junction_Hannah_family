"""Qualified recurrence and labeled historical cash-flow scenarios."""
import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from .ledger import transactions, account_scope, month_bounds, shift_month, fact_id
from .money import median_cents, percentile_cents, rounded
from .classification import TRANSFER_TYPES


def _reference(conn,customer_id,as_of):
    scope=account_scope(conn,customer_id)
    reference=date.fromisoformat(as_of or scope['observed_end'])
    if reference.isoformat()<scope['observed_start']: raise ValueError('No observed history by reference date')
    return reference


def detect_recurring(conn,customer_id,as_of=None):
    reference=_reference(conn,customer_id,as_of); month=reference.strftime('%Y-%m')
    if reference.isoformat()<month_bounds(month)[1]: month=shift_month(month,-1)
    first=shift_month(month,-5)+'-01'; last=month_bounds(month)[1]
    rows=transactions(conn,customer_id,first,last); groups=defaultdict(list)
    for row in rows:
        kind=row['transaction_type']
        if kind in ('salary','housing_payment','utilities_payment'): key=(kind,row['category'],None)
        else: key=(kind,row['category'],row['merchant_id'])
        groups[key].append(row)
    result=[]
    for (kind,category,merchant),group in groups.items():
        by_month=defaultdict(list)
        for r in group: by_month[r['date'][:7]].append(r)
        # Seeds and utilities are aggregated monthly; other groups need real row cadence.
        seed=kind in ('salary','housing_payment','utilities_payment')
        if seed:
            amounts=[sum(r['amount_cents'] for r in rs) for rs in by_month.values()]
            days=[median_cents([date.fromisoformat(r['date']).day for r in rs]) for rs in by_month.values()]
        else:
            amounts=[r['amount_cents'] for r in group]; days=[date.fromisoformat(r['date']).day for r in group]
        med=median_cents(amounts); amount_mad=median_cents([abs(a-med) for a in amounts]); day=median_cents(days); day_mad=median_cents([abs(d-day) for d in days])
        dates=sorted(date.fromisoformat(r['date']) for r in group)
        gaps=[(b-a).days for a,b in zip(dates,dates[1:])]
        appropriate_gaps=sum(25<=g<=35 for g in gaps)
        if kind=='utilities_payment' and len(by_month)<5: continue
        if not seed and (len(by_month)<5 or appropriate_gaps<4 or day_mad>3): continue
        fixed=(abs(med)>0 and Decimal(amount_mad)/abs(med)<=Decimal('.15'))
        recurrence='monthly envelope' if kind=='utilities_payment' else ('fixed' if fixed else 'variable recurring')
        refs=[r['transaction_ref'] for r in group]; group_id=fact_id('recurring',customer_id,kind,category,merchant)
        user_sources=[r for r in group if r['source']!='dataset']
        result.append({'id':group_id,'fact_id':fact_id('recurring-fact',group_id,refs),'customer_id':customer_id,'account_id':group[0]['account_id'],'transaction_type':kind,'category':category,'merchant_id':merchant,'role':group[-1]['role'],'amount_cents':med,'median_day':day,'amount_mad_cents':amount_mad,'day_mad':day_mad,'months_present':len(by_month),'qualifying_cadence_gaps':appropriate_gaps,'recurrence_kind':recurrence,'is_consumption':kind not in TRANSFER_TYPES and med<0,'transaction_refs':refs,'history_start':first,'history_end':last,'source':'user rule — You added this' if user_sources else 'deterministic recurrence','assumptions':['Median amount and calendar day from up to six complete months','Salary/housing seed recurrence; utilities are a monthly envelope']})
    return sorted(result,key=lambda r:(r['median_day'],r['id']))


def _flexible_windows(rows,reference,recurring_refs):
    if not rows: return [0],[],0
    earliest=date.fromisoformat(rows[0]['date']); latest_start=reference-timedelta(days=30)
    first_start=max(earliest,reference-timedelta(days=180))
    totals=[]; comparison_refs=set()
    # The literacy basket and cash-flow behavior answer different questions.
    # Groceries and transport are regular essentials, but they are not safe to
    # ignore when they do not qualify as a scheduled recurring item. Protect
    # every unscheduled consumption outflow in the historical buffer.
    unscheduled=[r for r in rows if r['amount_cents']<0 and r['transaction_type'] in ('purchase','utilities_payment','housing_payment') and r['transaction_type'] not in TRANSFER_TYPES and r['transaction_ref'] not in recurring_refs]
    cursor=first_start
    while cursor<=latest_start:
        end=cursor+timedelta(days=29)
        selected=[r for r in unscheduled if cursor.isoformat()<=r['date']<=end.isoformat()]
        totals.append(-sum(r['amount_cents'] for r in selected)); comparison_refs.update(r['transaction_ref'] for r in selected)
        cursor+=timedelta(days=1)
    return totals or [0],sorted(comparison_refs),len(totals)


def preview_30_days(conn,customer_id,as_of=None,assumptions=None):
    reference=_reference(conn,customer_id,as_of)
    rows=transactions(conn,customer_id,end=reference.isoformat())
    if not rows: raise ValueError('No observed balance')
    last=rows[-1]; balance=last['balance_after_cents']; recurring=detect_recurring(conn,customer_id,reference.isoformat()); assumptions=assumptions or {}
    known={r['id'] for r in recurring}
    if set(assumptions)-known: raise ValueError('Unknown recurring assumption')
    events=[]
    for item in recurring:
        edits=assumptions.get(item['id'],{})
        if set(edits)-{'enabled','amount_cents','median_day'}: raise ValueError('Unknown assumption field')
        if edits.get('enabled',True) is False: continue
        amount=edits.get('amount_cents',item['amount_cents']); day=edits.get('median_day',item['median_day'])
        if type(amount) is not int or type(day) is not int or not 1<=day<=31: raise ValueError('Invalid recurring amount/day')
        for offset in range(3):
            month=shift_month(reference.strftime('%Y-%m'),offset); y,m=map(int,month.split('-')); scheduled=date(y,m,min(day,calendar.monthrange(y,m)[1]))
            if reference<scheduled<=reference+timedelta(days=30): events.append({**item,'date':scheduled.isoformat(),'amount_cents':amount,'observed':False,'assumption_edited':bool(edits)})
    events.sort(key=lambda e:(e['date'],e['id']))
    recurring_refs={ref for item in recurring for ref in item['transaction_refs']}
    windows,comparison_refs,complete_window_count=_flexible_windows(rows,reference,recurring_refs)
    spend={'p25':percentile_cents(windows,.25),'p50':median_cents(windows),'p75':percentile_cents(windows,.75)}
    projected=[]; current=balance
    for i in range(1,31):
        day=(reference+timedelta(days=i)).isoformat(); todays=[e for e in events if e['date']==day]
        current+=sum(e['amount_cents'] for e in todays)
        bands={key:current-rounded(Decimal(value)*i/30) for key,value in spend.items()}
        projected.append({'date':day,'confirmed_balance_cents':current,'balance_cents':bands['p50'],'historical_flexible_scenarios':bands,'scheduled_item_ids':[e['id'] for e in todays],'observed':False})
    observed=[{'date':r['date'],'balance_cents':r['balance_after_cents'],'transaction_ref':r['transaction_ref'],'observed':True} for r in rows if r['date']>=(reference-timedelta(days=30)).isoformat()]
    observed_span_days=(reference-date.fromisoformat(rows[0]['date'])).days
    return {**account_scope(conn,customer_id),'as_of':reference.isoformat(),'latest_observed_date':last['date'],'starting_balance_cents':balance,'starting_transaction_ref':last['transaction_ref'],'observed':observed,'projected':projected,'scheduled_items':events,'recurring_items':recurring,'scenario_band':{'label':'Historical variation — not a probability interval','spending_cents':spend,'spending_scope':'all unscheduled consumption, including regular essentials','rolling_window_days':30,'window_count':complete_window_count,'complete_window_count':complete_window_count,'observed_span_days':observed_span_days,'comparison_transaction_refs':comparison_refs},'label':'Pattern-based cash-flow preview','assumptions':['Qualified recurring patterns use robust median dates and amounts','Unscheduled consumption uses historical 30-day variation; no probability claimed','No unconfirmed income or tax inference','Transfers affect balance and remain separate from consumption'],'fact_id':fact_id('preview',customer_id,reference.isoformat(),assumptions,last['transaction_ref']),'transaction_refs':[last['transaction_ref']]+[ref for r in recurring for ref in r['transaction_refs']]}


def safe_to_spend(conn, customer_id, as_of=None, days=7, reserve_floor_cents=None):
    """Return a conservative historical scenario, not a promise or credit decision."""
    if type(days) is not int or not 1 <= days <= 30:
        raise ValueError('days must be an integer from 1 to 30')
    reserve_floor_source = 'demo_default' if reserve_floor_cents is None else 'explicit_request'
    if reserve_floor_cents is None:
        reserve_floor_cents = 50_000
    if type(reserve_floor_cents) is not int or reserve_floor_cents < 0:
        raise ValueError('reserve_floor_cents must be nonnegative integer cents')
    scope = account_scope(conn, customer_id)
    reference = _reference(conn, customer_id, as_of)
    if reference.isoformat() > scope['observed_end']:
        raise ValueError('reference date is outside observed history')
    preview = preview_30_days(conn, customer_id, reference.isoformat())
    horizon = reference + timedelta(days=days)
    scheduled = [
        item for item in preview['scheduled_items']
        if item['date'] <= horizon.isoformat()
    ]
    outflows = [item for item in scheduled if item['amount_cents'] < 0]
    scheduled_outflows = -sum(item['amount_cents'] for item in outflows)
    excluded_income = sum(item['amount_cents'] for item in scheduled if item['amount_cents'] > 0)
    starting_balance = preview['starting_balance_cents']
    comparison_refs = preview['scenario_band']['comparison_transaction_refs']
    observed_history_days = preview['scenario_band']['observed_span_days']
    complete_windows = preview['scenario_band']['complete_window_count']
    available = observed_history_days >= 30 and complete_windows >= 1
    p75_30_days = preview['scenario_band']['spending_cents']['p75'] if available else None
    flexible_buffer = rounded(Decimal(p75_30_days) * days / 30) if available else None
    estimate = max(0, starting_balance - reserve_floor_cents - scheduled_outflows - flexible_buffer) if available else None
    refs = [preview['starting_transaction_ref']] + [ref for item in outflows for ref in item['transaction_refs']]
    result = {
        **scope,
        'reference_date': reference.isoformat(),
        'horizon_days': days,
        'horizon_end': horizon.isoformat(),
        'starting_balance_cents': starting_balance,
        'starting_transaction_ref': preview['starting_transaction_ref'],
        'reserve_floor_cents': reserve_floor_cents,
        'reserve_floor_source': reserve_floor_source,
        'scheduled_outflows_cents': scheduled_outflows,
        'scheduled_outflows': outflows,
        'scheduled_income_excluded_cents': excluded_income,
        'historical_flexible_buffer_cents': flexible_buffer,
        'historical_flexible_p75_30_day_cents': p75_30_days,
        'historical_buffer_scope': preview['scenario_band']['spending_scope'],
        'safe_to_spend_cents': estimate,
        'available': available,
        'needs_history': not available,
        'history_required_days': 30,
        'observed_history_days': observed_history_days,
        'complete_historical_window_count': complete_windows,
        'unavailable_reason': None if available else 'At least thirty days of history and one complete flexible-spending comparison window are required',
        'comparison_transaction_refs': comparison_refs,
        'transaction_refs': refs,
        'label': 'Estimated safe-to-spend — not a guarantee' if available else 'Safe-to-spend unavailable — more history needed',
        'assumptions': [
            'Expected income is excluded until it arrives',
            'Scheduled outflows use qualified recurring patterns, including committed transfers',
            'The unscheduled-consumption buffer scales the historical thirty-day upper-quartile scenario and includes regular essentials that are not scheduled separately',
            'Taxes or obligations not present in the transaction history are not inferred',
        ],
        'scenario': True,
        'observed': False,
    }
    result['fact_id'] = fact_id(
        'safe-to-spend', customer_id, reference.isoformat(), days,
        reserve_floor_cents, reserve_floor_source, starting_balance, scheduled_outflows,
        flexible_buffer, comparison_refs,
    )
    return result


def backtest_preview(conn,customer_id,as_of):
    reference=_reference(conn,customer_id,as_of); horizon=reference+timedelta(days=30)
    if horizon.isoformat()>account_scope(conn,customer_id)['observed_end']: raise ValueError('Backtest requires a fully observed 30-day horizon')
    preview=preview_30_days(conn,customer_id,as_of)
    actual=transactions(conn,customer_id,end=horizon.isoformat())[-1]; end=preview['projected'][-1]
    return {'customer_id':customer_id,'account_id':actual['account_id'],'as_of':as_of,'horizon_days':30,'actual_end_date':horizon.isoformat(),'actual_balance_date':actual['date'],'actual_end_balance_cents':actual['balance_after_cents'],'preview_end_balance_cents':end['balance_cents'],'confirmed_end_balance_cents':end['confirmed_balance_cents'],'ending_balance_error_cents':end['balance_cents']-actual['balance_after_cents'],'absolute_ending_balance_error_cents':abs(end['balance_cents']-actual['balance_after_cents']),'actual_transaction_ref':actual['transaction_ref'],'label':'Historical backtest error — not forecast confidence','fact_id':fact_id('backtest',preview['fact_id'],actual['transaction_ref'])}
