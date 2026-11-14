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


# ---------------------------------------------------------------------------
# WP-D: safe to spend until payday, safe to save (added; existing functions
# above are unchanged).

PROFILE_COACHING_MODES = ('normal', 'steady')
DECLARED_MATCH_TOLERANCE = Decimal('0.10')


def _euro(cents):
    sign = '-' if cents < 0 else ''
    return sign + '€' + format(Decimal(abs(cents)) / 100, ',.2f')


def _scheduled_date(reference, offset, day):
    month = shift_month(reference.strftime('%Y-%m'), offset)
    y, m = map(int, month.split('-'))
    return date(y, m, min(day, calendar.monthrange(y, m)[1]))


def _next_payday(reference, recurring):
    """Return (payday date or None, salary recurring item or None)."""
    salaries = [r for r in recurring if r['transaction_type'] == 'salary' and r['amount_cents'] > 0]
    if not salaries:
        return None, None
    # Several salary groups are unusual; the largest one sets the pay cycle.
    salary = max(salaries, key=lambda r: (r['amount_cents'], r['id']))
    day = int(salary['median_day'])
    for offset in range(3):
        candidate = _scheduled_date(reference, offset, day)
        # A payday on the reference date counts as already paid (balance includes it).
        if candidate > reference:
            return candidate, salary
    return None, salary


def _validate_profile(profile):
    if profile is None:
        profile = {}
    if not isinstance(profile, dict):
        raise ValueError('profile must be a dict or None')
    def number(value, name):
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise ValueError(name + ' must be a number')
        return value
    def cents(value, name):
        if type(value) is not int or value < 0:
            raise ValueError(name + ' must be nonnegative integer cents')
        return value
    clean = {}
    pct = profile.get('saving_rate_target_pct')
    if pct is not None:
        pct = Decimal(str(number(pct, 'saving_rate_target_pct')))
        if not pct.is_finite() or not 0 <= pct <= 100:
            raise ValueError('saving_rate_target_pct must be between 0 and 100')
        clean['saving_rate_target_pct'] = pct
    debts = profile.get('debts') or []
    if not isinstance(debts, list):
        raise ValueError('debts must be a list')
    clean['debts'] = []
    for debt in debts:
        if not isinstance(debt, dict):
            raise ValueError('each debt must be a dict')
        clean['debts'].append({'type': str(debt.get('type') or 'debt'), 'monthly_payment_cents': cents(debt.get('monthly_payment_cents'), 'debt monthly_payment_cents')})
    investing = profile.get('regular_investing')
    if investing is not None:
        if not isinstance(investing, dict):
            raise ValueError('regular_investing must be a dict')
        if investing.get('active'):
            clean['regular_investing'] = cents(investing.get('monthly_cents'), 'regular_investing monthly_cents')
    mode = profile.get('coaching_mode') or 'normal'
    if mode not in PROFILE_COACHING_MODES:
        raise ValueError('coaching_mode must be normal or steady')
    clean['coaching_mode'] = mode
    if profile.get('must_pays_monthly_cents') is not None:
        clean['must_pays_monthly_cents'] = cents(profile['must_pays_monthly_cents'], 'must_pays_monthly_cents')
    return clean


def _last_salary(conn, customer_id, reference):
    """Total salary of the most recent calendar month with salary, up to reference."""
    rows = [r for r in transactions(conn, customer_id, end=reference.isoformat(), filters={'transaction_type': 'salary'}) if r['amount_cents'] > 0]
    if not rows:
        return None, None, []
    month = rows[-1]['date'][:7]
    selected = [r for r in rows if r['date'][:7] == month]
    return sum(r['amount_cents'] for r in selected), month, [r['transaction_ref'] for r in selected]


def _must_pays_monthly(conn, customer_id, reference):
    """Average monthly Must-pays (fixed_obligation consumption) over the last 3 complete months."""
    scope = account_scope(conn, customer_id)
    month = reference.strftime('%Y-%m')
    if reference.isoformat() < month_bounds(month)[1]:
        month = shift_month(month, -1)
    months = [shift_month(month, i) for i in range(-2, 1)]
    months = [m for m in months if scope['observed_start'][:7] <= m <= scope['observed_end'][:7]]
    if not months:
        return 0, [], []
    rows = transactions(conn, customer_id, month_bounds(months[0])[0], month_bounds(months[-1])[1], filters={'role': 'fixed_obligation', 'consumption_only': 'true'})
    total = -sum(r['amount_cents'] for r in rows)
    return rounded(Decimal(total) / len(months)), months, [r['transaction_ref'] for r in rows]


def safe_until_payday(conn, customer_id, as_of=None, reserve_floor_cents=None, profile=None):
    """Estimate what is safe to spend until the next payday, and what is safe to save.

    A historical scenario, not a promise or credit decision. Unlike
    ``safe_to_spend(days=7)`` every scheduled bill before payday is held back.

    Args:
        conn: sqlite3 connection with the ledger schema.
        customer_id: customer in scope.
        as_of: ISO date (YYYY-MM-DD) of the reference day; default = last observed day.
        reserve_floor_cents: nonnegative int cents kept untouched; default 50_000
            (the same demo default as ``safe_to_spend``).
        profile: optional plain dict (money profile) with optional keys
            ``saving_rate_target_pct`` (number 0-100),
            ``debts`` (list of {type, monthly_payment_cents}),
            ``regular_investing`` ({active, monthly_cents}),
            ``coaching_mode`` ('normal'|'steady'),
            ``must_pays_monthly_cents`` (int, overrides the computed Must-pays month).
            Unknown keys are ignored.

    Method (all integer cents):
        1. next_payday = next occurrence (strictly after as_of) of the salary
           recurring item's median_day, clamped to month length; no salary ->
           as_of + 30 days, payday_source 'fallback_30_days'.
        2. committed = scheduled recurring outflows in (as_of, next_payday]
           (same qualified recurring items and day rule as preview_30_days)
           + declared monthly debt payments and regular investing, each counted
           once for the cycle. De-duplication: a declared item is skipped when
           a not-yet-matched recurring outflow exists whose amount is within
           +-10 % of the declared amount (each recurring item matches at most one
           declared item).
        3. planned_saving = saving_rate_target_pct x last salary month total
           (salary rows of the most recent month with salary); 0 if unset.
        4. free = balance - reserve - committed - planned_saving (may be negative;
           shortfall_cents reports the raw gap, derived spendables clamp at 0).
        5. per_day = max(free, 0) // days_until_payday (days >= 1);
           this_week = per_day x min(7, days_until_payday).
        6. safe_to_save = max(0, free - p75 30-day unscheduled spending x days/30),
           same historical buffer as safe_to_spend; 0 with
           safe_to_save_available False when history is too short.
        7. steady mode: reserve = max(reserve, one month of Must-pays
           (fixed_obligation consumption, average of last 3 complete months, or
           must_pays_monthly_cents)); planned_saving = 0; steady_mode True.

    Returns:
        dict with scope fields, reference_date, next_payday (ISO),
        days_until_payday, payday_source ('detected'|'fallback_30_days'),
        starting_balance_cents, reserve_floor_cents, reserve_floor_source,
        committed_cents, committed_items (list of {date, label, amount_cents
        (positive outflow), source ('recurring'|'declared'), transaction_type}),
        skipped_declared_items, planned_saving_cents, planned_saving_basis,
        free_cents (raw, may be negative), spendable_cents, shortfall_cents,
        per_day_cents, this_week_cents, this_week_days, everyday_buffer_cents,
        safe_to_save_cents, safe_to_save_available, steady_mode,
        must_pays_monthly_cents, components (list of {key, label, amount_cents,
        amount}), assumptions (list of str), transaction_refs,
        comparison_transaction_refs, chart ({kind:'runway', title, series:
        [{label: ISO date, value_cents}]}, projected p50 balance up to payday),
        label, scenario True, observed False, fact_id.
    """
    clean = _validate_profile(profile)
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
    recurring = preview['recurring_items']
    assumptions = ['Expected income is excluded until it arrives', 'Taxes or obligations not present in the transaction history or your profile are not inferred']

    # 1. Payday.
    payday, salary_item = _next_payday(reference, recurring)
    if payday is None:
        payday = reference + timedelta(days=30); payday_source = 'fallback_30_days'
        assumptions.append('No regular salary found, so a 30-day horizon is used instead of payday')
    else:
        payday_source = 'detected'
        assumptions.append('Next payday uses the usual salary day (' + str(salary_item['median_day']) + '), moved to the month end in shorter months')
    days = max((payday - reference).days, 1)

    # 2. Committed outflows up to and including payday.
    committed_items = []; refs = [preview['starting_transaction_ref']]
    recurring_outflows = [r for r in recurring if r['amount_cents'] < 0]
    for item in recurring_outflows:
        for offset in range(3):
            when = _scheduled_date(reference, offset, int(item['median_day']))
            if reference < when <= payday:
                committed_items.append({'date': when.isoformat(), 'label': item['category'] or item['transaction_type'], 'amount_cents': -item['amount_cents'], 'source': 'recurring', 'transaction_type': item['transaction_type'], 'recurring_id': item['id']})
                refs.extend(item['transaction_refs'])
    unmatched = list(recurring_outflows); skipped = []
    declared = [('Debt payment (' + d['type'] + ')', d['monthly_payment_cents'], 'debt') for d in clean['debts'] if d['monthly_payment_cents'] > 0]
    if clean.get('regular_investing'):
        declared.append(('Regular investing', clean['regular_investing'], 'regular_investing'))
    for label, amount, kind in declared:
        match = next((r for r in unmatched if abs(Decimal(-r['amount_cents'] - amount)) <= DECLARED_MATCH_TOLERANCE * amount), None)
        if match is not None:
            unmatched.remove(match)
            skipped.append({'label': label, 'amount_cents': amount, 'matched_recurring_id': match['id'], 'matched_amount_cents': -match['amount_cents']})
            continue
        committed_items.append({'date': None, 'label': label, 'amount_cents': amount, 'source': 'declared', 'transaction_type': kind, 'recurring_id': None})
    if declared:
        assumptions.append('Declared debts and investing count once this pay cycle; one is skipped when a recurring payment within 10% of its amount is already held back')
    committed_items.sort(key=lambda i: (i['date'] or '9999', i['label']))
    committed = sum(i['amount_cents'] for i in committed_items)

    # 3. Planned saving / 7. steady mode.
    steady = clean['coaching_mode'] == 'steady'
    must_pays = None; salary_refs = []
    pct = clean.get('saving_rate_target_pct')
    planned_saving = 0; planned_basis = 'No saving target set, so nothing is set aside for saving'
    if steady:
        if 'must_pays_monthly_cents' in clean:
            must_pays = clean['must_pays_monthly_cents']; source = 'from your profile'
        else:
            must_pays, months, must_refs = _must_pays_monthly(conn, customer_id, reference); source = 'average of ' + str(len(months)) + ' complete months'
        if must_pays > reserve_floor_cents:
            reserve_floor_cents = must_pays; reserve_floor_source = 'steady_mode_must_pays'
        planned_basis = 'Steady mode: no saving is planned this pay cycle'
        assumptions.append('Steady mode: the reserve covers at least one month of Must-pays (' + source + ') and no saving is planned')
    elif pct is not None and pct > 0:
        last_salary, salary_month, salary_refs = _last_salary(conn, customer_id, reference)
        if last_salary is None:
            planned_basis = 'Saving target set, but no salary was found to apply it to'
        else:
            planned_saving = rounded(Decimal(last_salary) * pct / 100)
            planned_basis = format(pct.normalize(), 'f') + '% saving target of your last salary (' + salary_month + ', ' + _euro(last_salary) + ')'
            refs.extend(salary_refs)
    assumptions.append(planned_basis)

    # 4-5. Free money and pacing.
    balance = preview['starting_balance_cents']
    free = balance - reserve_floor_cents - committed - planned_saving
    spendable = max(free, 0); shortfall = max(-free, 0)
    per_day = spendable // days; week_days = min(7, days); this_week = per_day * week_days

    # 6. Safe to save.
    band = preview['scenario_band']
    available = band['observed_span_days'] >= 30 and band['complete_window_count'] >= 1
    everyday = rounded(Decimal(band['spending_cents']['p75']) * days / 30) if available else None
    safe_to_save = max(0, free - everyday) if available else 0
    if not available:
        assumptions.append('Safe to save needs at least thirty days of history, so it is shown as zero')
    else:
        assumptions.append('Safe to save keeps back a busy (upper-quartile) month of everyday spending, scaled to the days until payday')

    components = [
        ('balance', 'Money in your account now', balance),
        ('reserve', 'Kept aside as a safety cushion', reserve_floor_cents),
        ('committed', 'Bills and payments due before payday', committed),
        ('planned_saving', 'Your planned saving', planned_saving),
        ('free', 'Free to use until payday', free),
        ('per_day', 'About this much a day', per_day),
        ('this_week', 'About this much this week', this_week),
        ('everyday_buffer', 'Usual everyday spending until payday (busy month)', everyday if everyday is not None else 0),
        ('safe_to_save', 'Could move to savings now', safe_to_save),
    ]
    series = [{'label': p['date'], 'value_cents': p['balance_cents']} for p in preview['projected'] if p['date'] <= payday.isoformat()]
    result = {
        **scope,
        'reference_date': reference.isoformat(),
        'next_payday': payday.isoformat(),
        'days_until_payday': days,
        'payday_source': payday_source,
        'salary_recurring_id': salary_item['id'] if salary_item else None,
        'starting_balance_cents': balance,
        'starting_transaction_ref': preview['starting_transaction_ref'],
        'reserve_floor_cents': reserve_floor_cents,
        'reserve_floor_source': reserve_floor_source,
        'committed_cents': committed,
        'committed_items': committed_items,
        'skipped_declared_items': skipped,
        'planned_saving_cents': planned_saving,
        'planned_saving_basis': planned_basis,
        'free_cents': free,
        'spendable_cents': spendable,
        'shortfall_cents': shortfall,
        'per_day_cents': per_day,
        'this_week_cents': this_week,
        'this_week_days': week_days,
        'everyday_buffer_cents': everyday,
        'historical_flexible_p75_30_day_cents': band['spending_cents']['p75'] if available else None,
        'safe_to_save_cents': safe_to_save,
        'safe_to_save_available': available,
        'steady_mode': steady,
        'must_pays_monthly_cents': must_pays,
        'components': [{'key': k, 'label': label, 'amount_cents': v, 'amount': _euro(v)} for k, label, v in components],
        'assumptions': assumptions,
        'transaction_refs': list(dict.fromkeys(refs)),
        'comparison_transaction_refs': band['comparison_transaction_refs'],
        'chart': {'kind': 'runway', 'title': 'Expected balance until payday', 'basis': 'Scheduled items plus typical (median) everyday spending', 'series': series},
        'label': 'Estimated safe to spend until payday — not a guarantee',
        'scenario': True,
        'observed': False,
    }
    result['fact_id'] = fact_id('safe-until-payday', customer_id, reference.isoformat(), payday.isoformat(), reserve_floor_cents, reserve_floor_source, balance, committed, planned_saving, everyday, steady, band['comparison_transaction_refs'])
    return result
