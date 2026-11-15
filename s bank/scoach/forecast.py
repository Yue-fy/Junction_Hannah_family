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
        if kind=='salary':
            # A median of two pay-day clusters (15th and month end) is a day salary never arrives on.
            pattern=cluster_paydays([date.fromisoformat(r['date']) for r in group])
            if pattern['dominant']: day=pattern['dominant']['day']; day_mad=pattern['dominant']['spread_days']
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
    # Salary lands on the same pay day the payday plan uses (dominant pay-day cluster and its
    # weekend rule), so the 30-day chart and Home never show two different paydays.
    pattern=payday_pattern(conn,customer_id,reference.isoformat())
    for item in recurring:
        edits=assumptions.get(item['id'],{})
        if set(edits)-{'enabled','amount_cents','median_day'}: raise ValueError('Unknown assumption field')
        if edits.get('enabled',True) is False: continue
        amount=edits.get('amount_cents',item['amount_cents']); day=edits.get('median_day',item['median_day'])
        if type(amount) is not int or type(day) is not int or not 1<=day<=31: raise ValueError('Invalid recurring amount/day')
        salary_rule=item['transaction_type']=='salary' and amount>0 and 'median_day' not in edits and pattern['dominant']
        if salary_rule and not pattern['regular']:
            # Irregular pay: the plan's next payday, then the usual gap between salaries.
            first,_=next_payday(pattern,reference); gap=_salary_gap(pattern)
            for k in range(6):
                scheduled=first+timedelta(days=gap*k)
                if reference<scheduled<=reference+timedelta(days=30): events.append({**item,'date':scheduled.isoformat(),'amount_cents':amount,'observed':False,'assumption_edited':bool(edits)})
            continue
        for offset in range(3):
            month=shift_month(reference.strftime('%Y-%m'),offset); y,m=map(int,month.split('-')); scheduled=date(y,m,min(day,calendar.monthrange(y,m)[1]))
            if salary_rule: scheduled=_cluster_date(pattern['dominant'],y,m,pattern['weekend_rule'])
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


def safe_to_spend(conn, customer_id, as_of=None, days=None, reserve_floor_cents=None, profile=None):
    """Legacy name for the one safe-to-spend answer: ``spending_plan`` until payday.

    The old seven-day estimate is gone. ``days`` is accepted for compatibility
    (an integer 1-30) and ignored, so every caller gets the same number.
    Returns the spending_plan dict plus the legacy keys safe_to_spend_cents
    (= this_week_cents), horizon_days, horizon_end, scheduled_outflows_cents.
    """
    if days is not None and (type(days) is not int or not 1 <= days <= 30):
        raise ValueError('days must be an integer from 1 to 30')
    plan = spending_plan(conn, customer_id, as_of=as_of, profile=profile, reserve_floor_cents=reserve_floor_cents)
    return {**plan, 'safe_to_spend_cents': plan['this_week_cents'] if plan['available'] else None,
            'horizon': 'until_payday', 'horizon_days': plan['this_week_days'], 'horizon_end': plan['next_payday'],
            'scheduled_outflows_cents': plan['committed_cents'], 'historical_flexible_buffer_cents': plan['everyday_cents']}


def backtest_preview(conn,customer_id,as_of):
    reference=_reference(conn,customer_id,as_of); horizon=reference+timedelta(days=30)
    if horizon.isoformat()>account_scope(conn,customer_id)['observed_end']: raise ValueError('Backtest requires a fully observed 30-day horizon')
    preview=preview_30_days(conn,customer_id,as_of)
    actual=transactions(conn,customer_id,end=horizon.isoformat())[-1]; end=preview['projected'][-1]
    return {'customer_id':customer_id,'account_id':actual['account_id'],'as_of':as_of,'horizon_days':30,'actual_end_date':horizon.isoformat(),'actual_balance_date':actual['date'],'actual_end_balance_cents':actual['balance_after_cents'],'preview_end_balance_cents':end['balance_cents'],'confirmed_end_balance_cents':end['confirmed_balance_cents'],'ending_balance_error_cents':end['balance_cents']-actual['balance_after_cents'],'absolute_ending_balance_error_cents':abs(end['balance_cents']-actual['balance_after_cents']),'actual_transaction_ref':actual['transaction_ref'],'label':'Historical backtest error — not forecast confidence','fact_id':fact_id('backtest',preview['fact_id'],actual['transaction_ref'])}


# ---------------------------------------------------------------------------
# V4: one spending plan until payday (safe to spend, could be saved), payday
# detection that respects mid-month and month-end pay patterns.

PROFILE_COACHING_MODES = ('normal', 'steady')
DECLARED_MATCH_TOLERANCE = Decimal('0.10')
DEFAULT_RESERVE_CENTS = 50_000          # small safety cushion kept untouched
SPENDABLE_CAP_MULTIPLIER = Decimal('1.5')   # spendable <= 1.5 x usual free-choice spending
STEADY_CAP_MULTIPLIER = Decimal('1.0')      # steady mode: no more than usual
MIN_DAILY_ROOM_CENTS = 500              # the cap never goes below €5 a day
EMERGENCY_FUND_BUILD_MONTHS = 12        # an emergency-fund goal is built up over a year
HISTORY_LOOKBACK_DAYS = 180
WINDOW_DAYS = 30

PAYDAY_LOOKBACK_DAYS = 365
PAYDAY_CLUSTER_GAP_DAYS = 2             # 13th/14th/15th are one pay day
MONTH_END_FROM_DAY = 28                 # salary on the 28th or later = "end of month"
PAYDAY_REGULAR_SHARE = Decimal('0.5')   # dominant pay day needs half of the salaries
PAYDAY_MIN_SALARIES = 3
PAYDAY_LATE_GRACE_DAYS = 3

_LOCALES = ('en', 'fi', 'sv')
_MONTHS_SV = ('jan', 'feb', 'mars', 'apr', 'maj', 'juni', 'juli', 'aug', 'sep', 'okt', 'nov', 'dec')
_MONTHS_EN = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')

# Held-back item names (EN / FI / SV). Buffer vocabulary (V5 fix spec): "Safety cushion" is
# the small reserve that is never spent; "Surprise buffer" is money set aside for Surprise
# must-pays. Nothing else is called a buffer or a cushion.
HELD_BACK_LABELS = {
    'rent': ('Rent', 'Vuokra', 'Hyra'),
    'utilities': ('Home bills', 'Kodin laskut', 'Hemräkningar'),
    'saving_transfer': ('Your regular saving transfer', 'Säännöllinen säästösiirtosi', 'Din regelbundna sparöverföring'),
    'regular_investing': ('Regular investing', 'Säännöllinen sijoittaminen', 'Regelbundet investerande'),
    'saving_target': ('Your saving target', 'Säästötavoitteesi', 'Ditt sparmål'),
    'debt': ('Loan payment', 'Lainanlyhennys', 'Låneavbetalning'),
    'mortgage': ('Mortgage payment', 'Asuntolainan erä', 'Bolånebetalning'),
    'tax': ('Money for taxes', 'Varaus veroihin', 'Pengar till skatt'),
    'buffer': ('Surprise buffer', 'Yllätyspuskuri', 'Buffert för oväntat'),
    'buffer_goal': ('Surprise buffer (your plan)', 'Yllätyspuskuri (oma suunnitelmasi)', 'Buffert för oväntat (din plan)'),
    'emergency_fund': ('Towards your emergency fund', 'Hätävaraasi', 'Till din sparkudde'),
    'reserve': ('Safety cushion', 'Turvatyyny', 'Säkerhetsmarginal'),
    'steady_reserve': ('Safety cushion: a month of must-pays', 'Turvatyyny: kuukauden pakolliset menot', 'Säkerhetsmarginal: en månads nödvändiga utgifter'),
    'everyday': ('Everyday costs until payday (food, getting around)', 'Arjen menot palkkapäivään asti (ruoka, liikkuminen)', 'Vardagsutgifter fram till lönedagen (mat, resor)'),
}
# Category names come from the one server table (scoach/labels.py); only the two bill
# categories read as the bill they are when held back before payday.
HELD_CATEGORY_KEYS = {'Housing': 'rent', 'Utilities': 'utilities'}
LOAN_WORDS = ('loan', 'laina', 'lån', 'credit', 'luotto', 'kredit', 'mortgage')


def _labels(key):
    en, fi, sv = HELD_BACK_LABELS[key]
    return {'en': en, 'fi': fi, 'sv': sv}


def _category_labels(category):
    from .labels import category_labels
    if category in HELD_CATEGORY_KEYS:
        return _labels(HELD_CATEGORY_KEYS[category])
    return category_labels(category)


def _euro(cents, locale='en'):
    from .money import format_euro
    return format_euro(cents, locale)


def _date_text(iso, locale='en'):
    day = date.fromisoformat(iso)
    if locale == 'fi':
        return '%d.%d.%d' % (day.day, day.month, day.year)
    if locale == 'sv':
        return '%d %s %d' % (day.day, _MONTHS_SV[day.month - 1], day.year)
    return '%d %s %d' % (day.day, _MONTHS_EN[day.month - 1], day.year)


def _scheduled_date(reference, offset, day):
    month = shift_month(reference.strftime('%Y-%m'), offset)
    y, m = map(int, month.split('-'))
    return date(y, m, min(day, calendar.monthrange(y, m)[1]))


def cluster_paydays(dates):
    """Group salary dates into pay-day clusters by day of month.

    Days on or after MONTH_END_FROM_DAY form one 'month_end' cluster (the 29th,
    30th and 31st are the same pay rule). Other days are grouped when they are at
    most PAYDAY_CLUSTER_GAP_DAYS apart. A cluster's day is its most frequent day
    (ties: the most recent); month_end uses 31 (clamped to the month length).

    Args: dates: list of datetime.date salary dates (any order).
    Returns {'clusters': [{'kind': 'day'|'month_end', 'day': int, 'count': int,
             'last_date': ISO, 'spread_days': int, 'days': [int]}] largest first,
             'dominant': cluster|None, 'regular': bool, 'salary_count': int,
             'weekend_rule': 'same_day'|'previous_banking_day'}.
    """
    dates = sorted(dates)
    month_end = [d for d in dates if d.day >= MONTH_END_FROM_DAY]
    others = sorted((d for d in dates if d.day < MONTH_END_FROM_DAY), key=lambda d: (d.day, d))
    groups = []
    for d in others:
        if groups and d.day - groups[-1][-1].day <= PAYDAY_CLUSTER_GAP_DAYS:
            groups[-1].append(d)
        else:
            groups.append([d])
    clusters = []
    for kind, members in [('day', g) for g in groups] + ([('month_end', month_end)] if month_end else []):
        days = [d.day for d in members]
        if kind == 'month_end':
            day = 31
        else:
            counts = {}
            for d in members:
                counts[d.day] = counts.get(d.day, 0) + 1
            day = max(counts, key=lambda x: (counts[x], max(m for m in members if m.day == x)))
        clusters.append({'kind': kind, 'day': day, 'count': len(members), 'last_date': max(members).isoformat(),
                         'spread_days': max(days) - min(days), 'days': sorted(days)})
    clusters.sort(key=lambda c: (c['count'], c['last_date']), reverse=True)
    dominant = clusters[0] if clusters else None
    regular = bool(dominant) and len(dates) >= PAYDAY_MIN_SALARIES and Decimal(dominant['count']) / len(dates) >= PAYDAY_REGULAR_SHARE
    # Finnish employers pay on banking days. If salary never arrived on a
    # weekend, a weekend pay day moves to the Friday before.
    weekend_rule = 'same_day' if any(d.weekday() >= 5 for d in dates) or not dates else 'previous_banking_day'
    return {'clusters': clusters, 'dominant': dominant, 'regular': regular,
            'salary_count': len(dates), 'weekend_rule': weekend_rule}


def _cluster_date(cluster, year, month, weekend_rule):
    last = calendar.monthrange(year, month)[1]
    day = date(year, month, last if cluster['kind'] == 'month_end' else min(cluster['day'], last))
    if weekend_rule == 'previous_banking_day':
        while day.weekday() >= 5:
            day -= timedelta(days=1)
    return day


def _month_offset(reference, offset):
    y, m = map(int, shift_month(reference.strftime('%Y-%m'), offset).split('-'))
    return y, m


def payday_pattern(conn, customer_id, as_of=None):
    """Salary pattern up to as_of: clusters, regularity and the salary rows used."""
    reference = _reference(conn, customer_id, as_of)
    start = (reference - timedelta(days=PAYDAY_LOOKBACK_DAYS)).isoformat()
    rows = [r for r in transactions(conn, customer_id, start, reference.isoformat(), {'transaction_type': 'salary'}) if r['amount_cents'] > 0]
    pattern = cluster_paydays([date.fromisoformat(r['date']) for r in rows])
    pattern['salary_dates'] = [r['date'] for r in rows]
    pattern['transaction_refs'] = [r['transaction_ref'] for r in rows]
    return pattern


def _salary_gap(pattern):
    """Usual days between salaries for irregular pay (upper quartile of gaps of 7+ days, so not too early; 30 without history)."""
    dates = [date.fromisoformat(d) for d in pattern.get('salary_dates', [])]
    gaps = [(b - a).days for a, b in zip(dates, dates[1:]) if (b - a).days >= 7]
    return percentile_cents(gaps, .75) if gaps else 30


def next_payday(pattern, reference):
    """Next plausible pay date strictly after ``reference`` (a pay day on the reference date is already in the balance).

    Returns (date|None, source) with source 'detected' | 'detected_late' |
    'irregular' | None (no salary). 'detected_late': this month's usual pay day
    passed without salary, so the other pay day seen in the history (for
    example month end instead of the 15th) is used.
    """
    dominant = pattern['dominant']
    if dominant is None:
        return None, None
    rule = pattern['weekend_rule']
    dates = [date.fromisoformat(d) for d in pattern.get('salary_dates', [])]
    if not pattern['regular']:
        # Irregular income: one usual gap after the last salary (upper quartile, so not too early).
        gap = _salary_gap(pattern)
        candidate = (dates[-1] if dates else reference) + timedelta(days=gap)
        while candidate <= reference:
            candidate += timedelta(days=gap)
        return candidate, 'irregular'
    usual = None
    for offset in range(3):
        candidate = _cluster_date(dominant, *_month_offset(reference, offset), rule)
        if candidate > reference:
            usual = candidate
            break
    this_month = _cluster_date(dominant, reference.year, reference.month, rule)
    if this_month + timedelta(days=PAYDAY_LATE_GRACE_DAYS) <= reference:
        since = this_month - timedelta(days=5)
        arrived = any(since <= d <= reference for d in dates)
        if not arrived:
            later = sorted(_cluster_date(c, reference.year, reference.month, rule) for c in pattern['clusters'][1:])
            later = [d for d in later if d > reference]
            if later and (usual is None or later[0] < usual):
                return later[0], 'detected_late'
    return usual, 'detected'


def _next_payday(reference, recurring, pattern=None):
    """Compatibility wrapper: (payday date or None, salary recurring item or None)."""
    salaries = [r for r in recurring if r['transaction_type'] == 'salary' and r['amount_cents'] > 0]
    salary = max(salaries, key=lambda r: (r['amount_cents'], r['id'])) if salaries else None
    if pattern is None:
        return None, salary
    day, _ = next_payday(pattern, reference)
    return day, salary


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
    protected = profile.get('protected_categories') or []
    if not isinstance(protected, list) or any(not isinstance(c, str) for c in protected):
        raise ValueError('protected_categories must be a list of category names')
    clean['protected_categories'] = [c.strip() for c in protected if c.strip()]
    months = profile.get('emergency_fund_target_months')
    if months is not None:
        months = Decimal(str(number(months, 'emergency_fund_target_months')))
        if not months.is_finite() or not 0 <= months <= 24:
            raise ValueError('emergency_fund_target_months must be between 0 and 24')
        if months > 0:
            clean['emergency_fund_target_months'] = months
    clean['plan_set_asides'] = []
    for item in profile.get('plan_set_asides') or []:
        if not isinstance(item, dict) or item.get('kind') not in ('loan', 'tax'):
            raise ValueError('plan_set_asides items need kind loan or tax')
        hint = item.get('dedupe_hint')
        if hint is not None and (not isinstance(hint, dict) or not isinstance(hint.get('transaction_type'), str)):
            raise ValueError('dedupe_hint must be {transaction_type, amount_cents}')
        day_of_month = item.get('day_of_month')
        if day_of_month is not None and (type(day_of_month) is not int or not 1 <= day_of_month <= 31):
            raise ValueError('plan day_of_month must be an integer from 1 to 31')
        clean['plan_set_asides'].append({'kind': item['kind'], 'plan': str(item.get('plan') or item['kind']),
                                         'label': str(item.get('label') or ''), 'amount_cents': cents(item.get('amount_cents'), 'plan amount_cents'),
                                         'until': item.get('until'), 'dedupe_hint': hint, 'day_of_month': day_of_month})
    if profile.get('tax_set_aside_monthly_cents') is not None:
        clean['tax_set_aside_monthly_cents'] = cents(profile['tax_set_aside_monthly_cents'], 'tax_set_aside_monthly_cents')
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


def _unscheduled_groups(rows, reference, recurring_refs, protected):
    """30-day rolling totals of unscheduled consumption, split into everyday / surprise / free-choice.

    everyday: Must-pays not scheduled separately (groceries, getting around) and
    any category the customer protected; surprise: Surprise must-pays (health,
    home and tech); free_choice: everything else (Little leaks and unclassified).
    Returns (windows {group: [cents]}, totals_in_lookback {group: cents},
    lookback_days, comparison_refs, window_count, history_days).
    """
    groups = ('everyday', 'surprise', 'free_choice')
    if not rows:
        return {g: [] for g in groups}, {g: 0 for g in groups}, 0, [], 0, 0
    earliest = date.fromisoformat(rows[0]['date'])
    first_start = max(earliest, reference - timedelta(days=HISTORY_LOOKBACK_DAYS))
    latest_start = reference - timedelta(days=WINDOW_DAYS)
    daily = {g: defaultdict(int) for g in groups}
    refs = []
    for r in rows:
        if r['amount_cents'] >= 0 or r['transaction_type'] not in ('purchase', 'utilities_payment', 'housing_payment'):
            continue
        if r['transaction_ref'] in recurring_refs or r['date'] < first_start.isoformat():
            continue
        if r['category'] in protected or r['role'] == 'fixed_obligation':
            group = 'everyday'
        elif r['role'] == 'flexible_essential':
            group = 'surprise'
        else:
            group = 'free_choice'
        daily[group][r['date']] += -r['amount_cents']
        refs.append(r['transaction_ref'])
    windows = {g: [] for g in groups}
    cursor = first_start
    while cursor <= latest_start:
        span = [(cursor + timedelta(days=i)).isoformat() for i in range(WINDOW_DAYS)]
        for g in groups:
            windows[g].append(sum(daily[g].get(d, 0) for d in span))
        cursor += timedelta(days=1)
    lookback = max((reference - first_start).days, 1)
    totals = {g: sum(daily[g].values()) for g in groups}
    return windows, totals, lookback, sorted(refs), len(windows['everyday']), (reference - earliest).days


def _held(kind, key, amount, when=None, labels=None, source='recurring', **extra):
    labels = labels or _labels(key)
    return {'kind': kind, 'key': key, 'label': labels['en'], 'labels': labels, 'amount_cents': amount,
            'date': when, 'source': source, **extra}


_SUMMARY = {
    'en': {'plan': 'For daily life until payday on {date} ({days} days): everyday basics {everyday} + free to spend {spendable} = {daily_life}, about {per_day} a day.',
           'plan_short': 'Nothing is free to spend until payday on {date} ({days} days).',
           'extra': 'That leaves about {extra} that could be saved.',

           'irregular': 'Your pay day varies, so this plans until {date}.'},
    'fi': {'plan': 'Arkeen palkkapäivään {date} asti ({days} päivää): arjen perusmenot {everyday} + vapaasti käytettävissä {spendable} = {daily_life}, noin {per_day} päivässä.',
           'plan_short': 'Palkkapäivään {date} asti ({days} päivää) vapaasti käytettävää rahaa ei ole.',
           'extra': 'Noin {extra} voisi siirtää säästöön.',

           'irregular': 'Palkkapäiväsi vaihtelee, joten suunnitelma ulottuu {date} asti.'},
    'sv': {'plan': 'Till vardagen fram till lönedagen {date} ({days} dagar): vardagsutgifter {everyday} + fritt att spendera {spendable} = {daily_life}, ungefär {per_day} om dagen.',
           'plan_short': 'Inget är fritt att spendera fram till lönedagen {date} ({days} dagar).',
           'extra': 'Då blir ungefär {extra} över som kan sparas.',

           'irregular': 'Din lönedag varierar, så planen gäller till {date}.'},
}


_NOTES = {
    'income_excluded': ('Expected income is counted only when it arrives.', 'Odotettu tulo lasketaan vasta, kun se saapuu.', 'Väntad inkomst räknas först när den kommer in.'),
    'not_guessed': ('Bills that are not in your transactions or your profile are not guessed.', 'Laskuja, jotka eivät näy tapahtumissasi tai profiilissasi, ei arvata.', 'Räkningar som inte syns i dina transaktioner eller din profil gissas inte.'),
    'no_salary': ('No regular salary found, so the plan looks 30 days ahead.', 'Säännöllistä palkkaa ei löytynyt, joten suunnitelma katsoo 30 päivää eteenpäin.', 'Ingen regelbunden lön hittades, så planen gäller 30 dagar framåt.'),
    'irregular': ('Your pay day varies, so the plan uses your usual gap between salaries.', 'Palkkapäiväsi vaihtelee, joten suunnitelma käyttää tavallista väliä palkkojen välillä.', 'Din lönedag varierar, så planen använder ditt vanliga avstånd mellan lönerna.'),
    'usual_payday': ('Next payday is your usual pay day: {day}.', 'Seuraava palkkapäivä on tavallinen palkkapäiväsi: {day}.', 'Nästa lönedag är din vanliga lönedag: {day}.'),
    'usual_payday_friday': ('Next payday is your usual pay day: {day}, or the Friday before when it falls on a weekend.', 'Seuraava palkkapäivä on tavallinen palkkapäiväsi: {day}, tai sitä edeltävä perjantai, jos se osuu viikonloppuun.', 'Nästa lönedag är din vanliga lönedag: {day}, eller fredagen innan om den infaller en helg.'),
    'late_salary': ("This month's salary has not arrived on the usual day, so the other pay day seen in your history is used.", 'Tämän kuun palkka ei ole tullut tavallisena päivänä, joten käytetään toista historiastasi näkyvää palkkapäivää.', 'Månadens lön har inte kommit på den vanliga dagen, så den andra lönedagen i din historik används.'),
    'declared': ('Loans and investing you told us about count once this pay cycle, unless a matching regular payment is already held back.', 'Kertomasi lainat ja sijoitukset lasketaan kerran tällä palkkajaksolla, ellei vastaavaa säännöllistä maksua ole jo varattu.', 'Lån och investeringar som du berättat om räknas en gång den här löneperioden, om inte en motsvarande regelbunden betalning redan är avsatt.'),
    'steady': ('Steady mode: a full month of must-pays ({amount}) is kept as your safety cushion, no saving is planned and spending stays at your usual pace.', 'Rauhallinen tahti: kuukauden pakolliset menot ({amount}) pidetään turvatyynynä, säästöä ei suunnitella ja käyttö pysyy tavallisessa tahdissa.', 'Lugnt tempo: en hel månads nödvändiga utgifter ({amount}) hålls som säkerhetsmarginal, inget sparande planeras och utgifterna hålls i din vanliga takt.'),
    'saving_target': ('Your saving target of {pct} of your last salary ({amount}) is set aside first.', 'Säästötavoitteesi, {pct} viimeisestä palkastasi ({amount}), varataan ensin.', 'Ditt sparmål på {pct} av din senaste lön ({amount}) avsätts först.'),
    'target_no_salary': ('You set a saving target, but no salary was found to apply it to.', 'Asetit säästötavoitteen, mutta palkkaa, johon sitä soveltaa, ei löytynyt.', 'Du har satt ett sparmål, men ingen lön hittades att tillämpa det på.'),
    'no_target': ('No saving target is set, so nothing extra is set aside for saving.', 'Säästötavoitetta ei ole asetettu, joten säästöön ei varata erikseen.', 'Inget sparmål är satt, så inget extra avsätts till sparande.'),
    'everyday_median': ('Everyday costs use your usual month of groceries and getting around, scaled to the days until payday.', 'Arjen menot perustuvat tavalliseen kuukauteesi ruokaostoksissa ja liikkumisessa, suhteutettuna palkkapäivään jäljellä oleviin päiviin.', 'Vardagsutgifterna bygger på din vanliga månad med matinköp och resor, omräknat till dagarna fram till lönedagen.'),
    'cap': ('A comfortable pace is up to one and a half times what you usually spend on eating out, fun and shopping ({amount} until payday); money beyond that is shown as could be saved.', 'Sopiva tahti on enintään puolitoista kertaa se, mitä tavallisesti käytät ulkona syömiseen, vapaa-aikaan ja ostoksiin ({amount} palkkapäivään asti); sen yli menevä raha näytetään säästettävänä.', 'En lagom takt är upp till en och en halv gång det du brukar lägga på restaurang, nöje och shopping ({amount} fram till lönedagen); pengar utöver det visas som möjliga att spara.'),
    'cap_steady': ('In steady mode a comfortable pace is what you usually spend on eating out, fun and shopping ({amount} until payday); money beyond that is shown as could be saved.', 'Rauhallisessa tahdissa sopiva tahti on se, mitä tavallisesti käytät ulkona syömiseen, vapaa-aikaan ja ostoksiin ({amount} palkkapäivään asti); sen yli menevä raha näytetään säästettävänä.', 'I lugnt tempo är en lagom takt det du brukar lägga på restaurang, nöje och shopping ({amount} fram till lönedagen); pengar utöver det visas som möjliga att spara.'),
    'buffer_goal': ('Your surprise buffer plan puts about {monthly} aside each payday, so that is held back instead of your usual surprise costs.', 'Yllätyspuskurisuunnitelmasi laittaa sivuun noin {monthly} joka palkkapäivä, joten se varataan tavallisten yllätysmenojen sijaan.', 'Din plan för bufferten för oväntat lägger undan ungefär {monthly} varje lönedag, så det avsätts i stället för dina vanliga oväntade utgifter.'),
    'mortgage_replaces': ('Your mortgage plan is the same money as the housing payment seen in your account, so it is held back once, as the mortgage payment.', 'Asuntolainasuunnitelmasi on samaa rahaa kuin tililläsi näkyvä asumismaksu, joten se varataan vain kerran, asuntolainan eränä.', 'Din bolåneplan är samma pengar som boendebetalningen på ditt konto, så den avsätts en gång, som bolånebetalning.'),
    'mortgage_after_payday': ('Your next mortgage payment ({day}) comes after payday, so it is not held back from this pay.', 'Seuraava asuntolainan erä ({day}) on palkkapäivän jälkeen, joten sitä ei varata tästä palkasta.', 'Nästa bolånebetalning ({day}) kommer efter lönedagen, så den avsätts inte från den här lönen.'),
    'protected': ('Categories you protected are kept with everyday costs: {categories}.', 'Suojaamasi luokat lasketaan arjen menoihin: {categories}.', 'Kategorier du skyddat räknas med vardagsutgifterna: {categories}.'),
    'short_history': ('There are fewer than thirty days of history, so everyday costs cannot be estimated yet.', 'Tapahtumahistoriaa on alle 30 päivää, joten arjen menoja ei voi vielä arvioida.', 'Det finns mindre än trettio dagars historik, så vardagsutgifterna kan inte uppskattas än.'),
    'emergency': ('Your emergency fund goal is {months} months of must-pays ({amount}). About {monthly} a month builds it in a year, so this payday\'s share is set aside towards it.', 'Hätävaratavoitteesi on {months} kuukauden pakolliset menot ({amount}). Noin {monthly} kuukaudessa kerryttää sen vuodessa, joten tämän palkkajakson osuus varataan hätävaraan.', 'Målet för din sparkudde är {months} månaders nödvändiga utgifter ({amount}). Ungefär {monthly} i månaden bygger upp den på ett år, så den här löneperiodens del avsätts till sparkudden.'),
}
_DAY_TEXT = {'en': ('the {day}th', 'month end'), 'fi': ('kuun {day}. päivä', 'kuun viimeinen päivä'), 'sv': ('den {day}:e', 'sista dagen i månaden')}


def _ordinal_en(day):
    return str(day) + ('th' if 10 <= day % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th'))


def _note_text(key, params, locale):
    from .money import format_percent
    template = _NOTES[key][_LOCALES.index(locale)]
    values = {}
    for name, value in params.items():
        if name == 'day':
            if value is None:
                values['day'] = _DAY_TEXT[locale][1]
            else:
                values['day'] = 'the ' + _ordinal_en(value) if locale == 'en' else _DAY_TEXT[locale][0].format(day=value)
        elif name in ('amount', 'salary', 'monthly'):
            values[name] = _euro(value, locale)
        elif name == 'pct':
            values[name] = format_percent(value, locale, 0 if Decimal(value) == Decimal(value).to_integral() else 1)
        elif name == 'months':
            values[name] = format(Decimal(value).normalize(), 'f').replace('.', ',' if locale != 'en' else '.')
        elif name == 'categories':
            from .labels import category_label
            values[name] = ', '.join(category_label(c, locale) for c in value)
    return template.format(**values)


# Why the plan is short (V5 fix): money covers bills first, then everyday costs, planned saving,
# the surprise buffer and last the safety cushion. The first part that cannot be covered is the
# cause, so a gap made by the cushion is never blamed on bills. Whole euros, like the Home card.
SHORTFALL_ORDER = ('bills', 'everyday', 'saving', 'buffer', 'cushion')
_SHORTFALL_TEXT = {
    'bills': ('Bills before payday ({bills}) are {bills_over} more than your balance ({balance}). Your safety cushion ({cushion}) cannot be kept this time.',
              'Ennen palkkapäivää erääntyvät laskut ({bills}) ovat {bills_over} enemmän kuin saldosi ({balance}). Turvatyynyäsi ({cushion}) ei voi pitää tällä kertaa.',
              'Räkningarna före lönedagen ({bills}) är {bills_over} mer än ditt saldo ({balance}). Din säkerhetsmarginal ({cushion}) kan inte behållas den här gången.'),
    'everyday': ('Bills before payday ({bills}) are covered, but food and getting around until payday ({everyday}) need {everyday_short} more than is left. Your safety cushion ({cushion}) cannot be kept this time.',
                 'Ennen palkkapäivää erääntyvät laskut ({bills}) on katettu, mutta ruokaan ja liikkumiseen palkkapäivään asti ({everyday}) puuttuu {everyday_short}. Turvatyynyäsi ({cushion}) ei voi pitää tällä kertaa.',
                 'Räkningarna före lönedagen ({bills}) är täckta, men till mat och resor fram till lönedagen ({everyday}) saknas {everyday_short}. Din säkerhetsmarginal ({cushion}) kan inte behållas den här gången.'),
    'saving': ('Bills and everyday costs until payday are covered. Your planned saving ({saving}) is {saving_short} more than what is left.',
               'Laskut ja arjen menot palkkapäivään asti on katettu. Suunniteltu säästösi ({saving}) on {saving_short} enemmän kuin mitä jää.',
               'Räkningar och vardagsutgifter fram till lönedagen är täckta. Ditt planerade sparande ({saving}) är {saving_short} mer än det som blir kvar.'),
    'buffer': ('Bills and everyday costs until payday are covered. The surprise buffer ({buffer}) and safety cushion ({cushion}) are {short} short this time.',
               'Laskut ja arjen menot palkkapäivään asti on katettu. Yllätyspuskuriin ({buffer}) ja turvatyynyyn ({cushion}) puuttuu tällä kertaa {short}.',
               'Räkningar och vardagsutgifter fram till lönedagen är täckta. Till bufferten för oväntat ({buffer}) och säkerhetsmarginalen ({cushion}) saknas {short} den här gången.'),
    'cushion': ('Bills and everyday costs until payday are covered. Only {cushion_kept} of your {cushion} safety cushion can be kept, {cushion_short} short.',
                'Laskut ja arjen menot palkkapäivään asti on katettu. {cushion} turvatyynystäsi voi pitää vain {cushion_kept}, {cushion_short} puuttuu.',
                'Räkningar och vardagsutgifter fram till lönedagen är täckta. Av din säkerhetsmarginal på {cushion} kan bara {cushion_kept} behållas, {cushion_short} saknas.'),
    'steady_reserve': ('Bills and everyday costs until payday are covered. Steady mode keeps a month of must-pays ({cushion}) as your safety cushion; {cushion_kept} of it can be kept now, {cushion_short} short.',
                       'Laskut ja arjen menot palkkapäivään asti on katettu. Rauhallisessa tahdissa turvatyynynä pidetään kuukauden pakolliset menot ({cushion}); siitä voi nyt pitää {cushion_kept}, {cushion_short} puuttuu.',
                       'Räkningar och vardagsutgifter fram till lönedagen är täckta. I lugnt tempo hålls en månads nödvändiga utgifter ({cushion}) som säkerhetsmarginal; {cushion_kept} av den kan behållas nu, {cushion_short} saknas.'),
}


def shortfall_breakdown(balance, held_back, everyday, steady_reserve=False):
    """Split a payday-plan gap into its cause (pure; integer cents).

    Parts, covered in this order: bills (held-back kinds bill, loan, tax), everyday
    (food and getting around until payday), saving (held-back kind goal), buffer
    (surprise buffer) and cushion (the safety cushion; a month of must-pays in steady
    mode). Returns {cause: one of SHORTFALL_ORDER or None, cushion_kind: 'reserve'|
    'steady_reserve', balance_cents, parts {name: {cents, covered_cents, short_cents}},
    bills_cents, everyday_cents, saving_cents, buffer_cents, cushion_cents,
    bills_over_balance_cents (bills not covered by the balance), below_zero_cents
    (how far the account itself would go below zero before payday: bills + everyday -
    balance, >= 0), cushion_kept_cents, cushion_short_cents, shortfall_cents (sum of
    every part's short_cents), texts {en, fi, sv} (None when nothing is short)}.
    """
    totals = {'bills': 0, 'everyday': max(everyday, 0), 'saving': 0, 'buffer': 0, 'cushion': 0}
    for item in held_back:
        part = {'bill': 'bills', 'loan': 'bills', 'tax': 'bills', 'goal': 'saving', 'buffer': 'buffer', 'reserve': 'cushion'}.get(item['kind'], 'bills')
        totals[part] += item['amount_cents']
    left = balance; parts = {}; cause = None
    for name in SHORTFALL_ORDER:
        covered = min(totals[name], max(left, 0))
        parts[name] = {'cents': totals[name], 'covered_cents': covered, 'short_cents': totals[name] - covered}
        left -= totals[name]
        if cause is None and parts[name]['short_cents'] > 0:
            cause = name
    result = {'cause': cause, 'cushion_kind': 'steady_reserve' if steady_reserve else 'reserve', 'balance_cents': balance, 'parts': parts,
              'bills_cents': totals['bills'], 'everyday_cents': totals['everyday'], 'saving_cents': totals['saving'],
              'buffer_cents': totals['buffer'], 'cushion_cents': totals['cushion'],
              'bills_over_balance_cents': parts['bills']['short_cents'],
              'below_zero_cents': max(totals['bills'] + totals['everyday'] - balance, 0),
              'cushion_kept_cents': parts['cushion']['covered_cents'], 'cushion_short_cents': parts['cushion']['short_cents'],
              'shortfall_cents': sum(p['short_cents'] for p in parts.values()), 'texts': None}
    if cause:
        key = 'steady_reserve' if cause == 'cushion' and steady_reserve else cause
        result['texts'] = {}
        for index, locale in enumerate(_LOCALES):
            money = lambda cents: _euro_whole(cents, locale)
            values = {'balance': money(max(balance, 0)), 'bills': money(totals['bills']), 'bills_over': money(parts['bills']['short_cents']),
                      'everyday': money(totals['everyday']), 'everyday_short': money(parts['everyday']['short_cents']),
                      'saving': money(totals['saving']), 'saving_short': money(parts['saving']['short_cents']),
                      'buffer': money(totals['buffer']), 'cushion': money(totals['cushion']),
                      'cushion_kept': money(parts['cushion']['covered_cents']), 'cushion_short': money(parts['cushion']['short_cents']),
                      'short': money(parts['buffer']['short_cents'] + parts['cushion']['short_cents'])}
            result['texts'][locale] = _SHORTFALL_TEXT[key][index].format(**values)
    return result


def _euro_whole(cents, locale='en'):
    from .money import format_euro
    return format_euro(cents, locale, 0)


def _summary(plan):
    out = {}
    for locale in _LOCALES:
        t = _SUMMARY[locale]
        values = {'free': _euro(plan['free_cents'], locale), 'date': _date_text(plan['next_payday'], locale),
                  'days': plan['days_to_payday'], 'per_day': _euro(plan['per_day_cents'], locale),
                  'extra': _euro(plan['extra_cents'], locale), 'short': _euro(plan['shortfall_cents'], locale),
                  'everyday': _euro(plan['daily_life_cents'] - plan['spendable_until_payday_cents'], locale),
                  'spendable': _euro(plan['spendable_until_payday_cents'], locale), 'daily_life': _euro(plan['daily_life_cents'], locale)}
        lines = [t['plan_short' if plan['shortfall_cents'] and not plan['spendable_until_payday_cents'] else 'plan'].format(**values)]
        if plan['shortfall_cents']:
            lines.append(plan['shortfall_breakdown']['texts'][locale])
        elif plan['extra_cents']:
            lines.append(t['extra'].format(**values))
        if plan['payday']['source'] == 'irregular':
            lines.append(t['irregular'].format(**values))
        out[locale] = lines
    return out


def _buffer_goal(conn, customer_id, reference):
    """The customer's saved surprise-buffer goal (template 'buffer') that is not reached yet, or None.

    Returns {goal_id, monthly_cents (what the goal needs each month from the reference
    month to its target month), remaining_cents, target_date}. The newest buffer goal wins.
    """
    import sqlite3
    try:
        rows = conn.execute("SELECT id, target_cents, current_saved_cents, target_date FROM goals "
                            "WHERE customer_id=? AND template='buffer' ORDER BY created_at DESC, id DESC", (customer_id,)).fetchall()
    except sqlite3.OperationalError:
        return None
    for goal_id, target, saved, target_date in rows:
        remaining = max(int(target) - int(saved or 0), 0)
        if not remaining:
            continue
        end = date.fromisoformat(target_date)
        months = max((end.year - reference.year) * 12 + end.month - reference.month, 1)
        return {'goal_id': goal_id, 'monthly_cents': min(-(-remaining // months), remaining),
                'remaining_cents': remaining, 'target_date': target_date}
    return None


def spending_plan(conn, customer_id, as_of=None, profile=None, reserve_floor_cents=None):
    """The one safe-to-spend answer: what is free until payday, what is spendable, what could be saved.

    Historical estimate, not a promise or credit decision.

    Args:
        conn, customer_id: ledger connection and customer in scope.
        as_of: ISO date of the reference day (default last observed day). A date
            after the customer's last observed day uses that last day.
        profile: optional plain dict (money_profile.planning_inputs shape):
            saving_rate_target_pct, debts [{type, monthly_payment_cents}],
            regular_investing {active, monthly_cents}, coaching_mode
            'normal'|'steady', must_pays_monthly_cents, protected_categories [str],
            emergency_fund_target_months, tax_set_aside_monthly_cents.
        reserve_floor_cents: nonnegative int; default DEFAULT_RESERVE_CENTS.

    Method (integer cents):
        1. next_payday from the salary pattern (cluster_paydays / next_payday):
           the dominant pay day (mode, never a median of two clusters), weekend
           rule from history, a late salary switches to the other seen pay day;
           irregular pay -> last salary + usual gap; no salary -> 30 days.
        2. held_back: every recurring bill, loan and saving transfer due in
           (as_of, payday]; declared debts / investing once per cycle (skipped
           when a recurring payment within 10 % already matches); saving target;
           tax set-aside; surprise buffer (Surprise must-pays per day over the
           last 180 days x days); reserve (steady mode: >= one month of Must-pays).
        3. everyday_cents: median 30-day unscheduled everyday spending
           (groceries, getting around, protected categories) x days/30.
        4. free = max(balance - held_back - everyday, 0); shortfall = the gap.
        5. cap = max(multiplier x median 30-day free-choice spending x days/30,
           MIN_DAILY_ROOM_CENTS x days); multiplier 1.5 (steady 1.0).
           spendable_until_payday = min(free, cap); extra = free - spendable
           ("could be saved"); per_day = spendable // days; this_week =
           per_day x min(7, days).  spendable + extra == free, always.

    Returns dict: as_of, balance_cents, next_payday, days_to_payday, payday
        {source, regular, weekend_rule, usual_day, clusters}, held_back [{kind,
        key, label, labels, amount_cents, date, source}], held_back_cents,
        everyday_cents, buffer_cents, reserve_floor_cents, free_cents,
        shortfall_cents, cap_cents, spendable_until_payday_cents, per_day_cents,
        this_week_cents, extra_cents, emergency_fund|None, summary {en,fi,sv:
        [str]}, basis {...}, evidence {transaction_refs, comparison_transaction_refs,
        query}, plus legacy keys used by the UI and coach (reference_date,
        days_until_payday, starting_balance_cents, committed_cents,
        committed_items, planned_saving_cents, spendable_cents, safe_to_save_cents,
        everyday_buffer_cents, components, assumptions, chart, fact_id ...).
    """
    clean = _validate_profile(profile)
    reserve_floor_source = 'demo_default' if reserve_floor_cents is None else 'explicit_request'
    if reserve_floor_cents is None:
        reserve_floor_cents = DEFAULT_RESERVE_CENTS
    if type(reserve_floor_cents) is not int or reserve_floor_cents < 0:
        raise ValueError('reserve_floor_cents must be nonnegative integer cents')
    scope = account_scope(conn, customer_id)
    if as_of and as_of > scope['observed_end']:
        as_of = scope['observed_end']
    reference = _reference(conn, customer_id, as_of)
    preview = preview_30_days(conn, customer_id, reference.isoformat())
    recurring = preview['recurring_items']
    notes = [('income_excluded', {}), ('not_guessed', {})]
    def note(key, **params):
        notes.append((key, params))

    # 1. Payday.
    pattern = payday_pattern(conn, customer_id, reference.isoformat())
    payday, payday_source = next_payday(pattern, reference)
    salaries = [r for r in recurring if r['transaction_type'] == 'salary' and r['amount_cents'] > 0]
    salary_item = max(salaries, key=lambda r: (r['amount_cents'], r['id'])) if salaries else None
    if payday is None:
        payday = reference + timedelta(days=30); payday_source = 'fallback_30_days'
        note('no_salary')
    elif payday_source == 'irregular':
        note('irregular')
    else:
        dominant = pattern['dominant']
        note('usual_payday_friday' if pattern['weekend_rule'] == 'previous_banking_day' else 'usual_payday',
             day=None if dominant['kind'] == 'month_end' else dominant['day'])
        if payday_source == 'detected_late':
            note('late_salary')
    days = max((payday - reference).days, 1)

    # 2. Held back: recurring bills, loans and saving transfers before payday.
    held_back = []; refs = [preview['starting_transaction_ref']]
    recurring_outflows = [r for r in recurring if r['amount_cents'] < 0]
    for item in recurring_outflows:
        for offset in range(3):
            when = _scheduled_date(reference, offset, int(item['median_day']))
            if not reference < when <= payday:
                continue
            kind_type = item['transaction_type']; category = item['category'] or ''
            if kind_type == 'housing_payment':
                entry = _held('bill', 'rent', -item['amount_cents'], when.isoformat())
            elif kind_type == 'utilities_payment':
                entry = _held('bill', 'utilities', -item['amount_cents'], when.isoformat())
            elif kind_type in TRANSFER_TYPES:
                entry = _held('goal', 'saving_transfer', -item['amount_cents'], when.isoformat())
            elif any(w in (category + ' ' + (item['merchant_id'] or '')).lower() for w in LOAN_WORDS):
                entry = _held('loan', 'debt', -item['amount_cents'], when.isoformat())
            else:
                entry = _held('bill', 'recurring', -item['amount_cents'], when.isoformat(), labels=_category_labels(category))
            entry.update(transaction_type=kind_type, recurring_id=item['id'], category=item['category'])
            held_back.append(entry)
            refs.extend(item['transaction_refs'])
    unmatched = list(recurring_outflows); skipped = []; upcoming = []
    declared = [('loan', 'mortgage' if d['type'] == 'mortgage' else 'debt', 'Debt payment (' + d['type'] + ')', d['monthly_payment_cents'], 'debt') for d in clean['debts'] if d['monthly_payment_cents'] > 0]
    if clean.get('regular_investing'):
        declared.append(('goal', 'regular_investing', 'Regular investing', clean['regular_investing'], 'regular_investing'))
    for kind, key, legacy_label, amount, legacy_type in declared:
        match = next((r for r in unmatched if abs(Decimal(-r['amount_cents'] - amount)) <= DECLARED_MATCH_TOLERANCE * amount), None)
        if match is not None:
            unmatched.remove(match)
            skipped.append({'label': legacy_label, 'amount_cents': amount, 'matched_recurring_id': match['id'], 'matched_amount_cents': -match['amount_cents']})
            continue
        held_back.append(_held(kind, key, amount, None, source='declared', transaction_type=legacy_type, recurring_id=None, legacy_label=legacy_label))
    if declared:
        note('declared')
    # Plans the customer switched on (mortgage, tax). A mortgage plan is the customer's real home
    # loan, so a recurring payment of the hinted type (a housing payment seen in the account) is
    # that same money: it is REPLACED by the plan payment, labelled "Mortgage payment", on the
    # plan's payment day (or the day it is seen paid). Never both. A dated payment after payday
    # is not held back this pay cycle. Undated plans (tax) are held back once per pay cycle.
    for item in clean['plan_set_asides']:
        if item['amount_cents'] <= 0 or (item['until'] and str(item['until'])[:7] < reference.strftime('%Y-%m')):
            continue
        key = 'mortgage' if item['plan'] == 'mortgage' else ('tax' if item['kind'] == 'tax' else 'debt')
        labels = _labels(key) if key == 'mortgage' else {**_labels(key), **({'en': item['label']} if item['label'] else {})}
        hint = item['dedupe_hint']
        match = None
        if item['kind'] == 'loan' and hint:
            target = hint.get('amount_cents') if type(hint.get('amount_cents')) is int else item['amount_cents']
            same_type = [r for r in unmatched if r['transaction_type'] == hint['transaction_type']]
            if hint['transaction_type'] not in ('housing_payment', 'loan_payment'):
                same_type = [r for r in same_type if abs(Decimal(-r['amount_cents'] - target)) <= DECLARED_MATCH_TOLERANCE * target]
            match = min(same_type, key=lambda r: (abs(-r['amount_cents'] - target), r['id'])) if same_type else None
        if match is not None:
            unmatched.remove(match)
            replaced = [h for h in held_back if h.get('recurring_id') == match['id']]
            held_back = [h for h in held_back if h.get('recurring_id') != match['id']]
            skipped.append({'label': item['label'] or item['plan'], 'amount_cents': item['amount_cents'], 'plan': item['plan'],
                            'matched_recurring_id': match['id'], 'matched_amount_cents': -match['amount_cents'],
                            'replaced_by_plan': True, 'replaced_dates': [h['date'] for h in replaced]})
            note('mortgage_replaces')
        day_of_month = item.get('day_of_month') or (int(match['median_day']) if match is not None else None)
        extra = dict(transaction_type='plan_' + item['plan'], recurring_id=None, plan=item['plan'],
                     replaces_recurring_id=match['id'] if match is not None else None)
        if item['kind'] == 'loan' and day_of_month:
            dates = [d for d in (_scheduled_date(reference, offset, day_of_month) for offset in range(3)) if reference < d <= payday]
            for when in dates:
                held_back.append(_held(item['kind'], key, item['amount_cents'], when.isoformat(), labels=labels, source='plan', **extra))
            if not dates:
                after = next((d for d in (_scheduled_date(reference, offset, day_of_month) for offset in range(4)) if d > payday), None)
                note('mortgage_after_payday', day=day_of_month)
                upcoming.append({'plan': item['plan'], 'date': after.isoformat() if after else None,
                                 'amount_cents': item['amount_cents'], 'labels': labels})
            continue
        held_back.append(_held(item['kind'], key, item['amount_cents'], None, labels=labels, source='plan', **extra))
    if clean.get('tax_set_aside_monthly_cents'):
        held_back.append(_held('tax', 'tax', clean['tax_set_aside_monthly_cents'], None, source='declared', transaction_type='tax', recurring_id=None))

    # Saving target / steady mode.
    steady = clean['coaching_mode'] == 'steady'
    must_pays = None
    pct = clean.get('saving_rate_target_pct')
    planned_saving = 0; planned_basis = 'No saving target set, so nothing extra is set aside for saving'
    if steady or clean.get('emergency_fund_target_months'):
        if 'must_pays_monthly_cents' in clean:
            must_pays = clean['must_pays_monthly_cents']; must_source = None
        else:
            must_pays, months_used, _ = _must_pays_monthly(conn, customer_id, reference); must_source = len(months_used)
    reserve_key = 'reserve'
    if steady:
        if must_pays > reserve_floor_cents:
            reserve_floor_cents = must_pays; reserve_floor_source = 'steady_mode_must_pays'; reserve_key = 'steady_reserve'
        planned_basis = 'Steady mode: no saving is planned this pay cycle'
        note('steady', amount=must_pays)
    elif pct is not None and pct > 0:
        last_salary, salary_month, salary_refs = _last_salary(conn, customer_id, reference)
        if last_salary is None:
            planned_basis = 'Saving target set, but no salary was found to apply it to'; note('target_no_salary')
        else:
            planned_saving = rounded(Decimal(last_salary) * pct / 100)
            planned_basis = format(pct.normalize(), 'f') + '% saving target of your last salary (' + salary_month + ', ' + _euro(last_salary) + ')'
            note('saving_target', pct=pct, amount=planned_saving, salary=last_salary)
            refs.extend(salary_refs)
            held_back.append(_held('goal', 'saving_target', planned_saving, None, source='profile', transaction_type='saving_target', recurring_id=None))
    if pct is None and not steady:
        note('no_target')

    # 3. Everyday costs and the surprise buffer from history.
    rows = transactions(conn, customer_id, end=reference.isoformat())
    recurring_refs = {ref for item in recurring for ref in item['transaction_refs']}
    protected = set(clean.get('protected_categories', []))
    windows, totals, lookback, comparison_refs, window_count, history_days = _unscheduled_groups(rows, reference, recurring_refs, protected)
    available = history_days >= 30 and window_count >= 1
    if available:
        everyday_month = median_cents(windows['everyday'])
        free_choice_month = median_cents(windows['free_choice'])
        everyday = rounded(Decimal(everyday_month) * days / WINDOW_DAYS)
        buffer = rounded(Decimal(totals['surprise']) * days / lookback)
        multiplier = STEADY_CAP_MULTIPLIER if steady else SPENDABLE_CAP_MULTIPLIER
        cap = max(rounded(multiplier * free_choice_month * days / WINDOW_DAYS), MIN_DAILY_ROOM_CENTS * days)
        note('everyday_median')
        note('cap_steady' if steady else 'cap', amount=cap)
        if protected:
            note('protected', categories=sorted(protected))
    else:
        everyday_month = free_choice_month = None
        everyday = buffer = 0; cap = None; multiplier = None
        note('short_history')
    # Emergency fund goal: build months x must-pays over EMERGENCY_FUND_BUILD_MONTHS; this pay
    # cycle's share is held back as the buffer when it is bigger than the usual surprise costs.
    emergency = None; buffer_key = 'buffer'; buffer_source = 'history'
    if clean.get('emergency_fund_target_months'):
        months_target = clean['emergency_fund_target_months']
        target = rounded(months_target * must_pays)
        this_cycle = rounded(Decimal(target) / EMERGENCY_FUND_BUILD_MONTHS * days / WINDOW_DAYS)
        emergency = {'target_months': format(months_target.normalize(), 'f'), 'target_cents': target,
                     'must_pays_monthly_cents': must_pays, 'build_months': EMERGENCY_FUND_BUILD_MONTHS,
                     'monthly_set_aside_cents': rounded(Decimal(target) / EMERGENCY_FUND_BUILD_MONTHS),
                     'this_payday_cents': this_cycle}
        if this_cycle > buffer:
            buffer = this_cycle; buffer_key = 'emergency_fund'; buffer_source = 'profile'
        note('emergency', months=months_target, amount=target, monthly=emergency['monthly_set_aside_cents'])
    # A saved surprise-buffer goal ("Set aside €400 monthly" on Home) is the customer's own plan:
    # its monthly amount is held back each payday (not less than the usual surprise costs), so
    # "could be saved" and the daily number already leave it out. Steady mode plans no saving.
    buffer_goal = None if steady else _buffer_goal(conn, customer_id, reference)
    if buffer_goal and buffer_goal['monthly_cents'] >= buffer:
        buffer = buffer_goal['monthly_cents']; buffer_key = 'buffer_goal'; buffer_source = 'goal'
        note('buffer_goal', monthly=buffer_goal['monthly_cents'])
    if buffer:
        held_back.append(_held('buffer', buffer_key, buffer, None, source=buffer_source,
                               **({'goal_id': buffer_goal['goal_id']} if buffer_key == 'buffer_goal' else {})))
    held_back.append(_held('reserve', reserve_key, reserve_floor_cents, None, source={'demo_default': 'default', 'steady_mode_must_pays': 'profile'}.get(reserve_floor_source, 'request')))
    held_back.sort(key=lambda i: (['bill', 'loan', 'tax', 'goal', 'buffer', 'reserve'].index(i['kind']), i['date'] or '9999', i['label']))

    # 4-5. Free money, spending room and what could be saved.
    balance = preview['starting_balance_cents']
    held_total = sum(i['amount_cents'] for i in held_back)
    raw_free = balance - held_total - everyday
    free = max(raw_free, 0); shortfall = max(-raw_free, 0)
    breakdown = shortfall_breakdown(balance, held_back, everyday, steady_reserve=reserve_key == 'steady_reserve')
    spendable = free if cap is None else min(free, cap)
    extra = free - spendable
    # The daily number is money for daily life: everyday costs (food, getting around) plus free choices.
    # Leaving food out made a headline like "€17 a day" look like everything a customer has to live on.
    # In a shortfall, only the part of everyday money that is really there counts.
    daily_life = max(everyday - shortfall, 0) + spendable
    per_day = daily_life // days; week_days = min(7, days); this_week = per_day * week_days

    if emergency is not None:
        emergency['could_add_now_cents'] = min(extra, max(emergency['target_cents'] - emergency['this_payday_cents'], 0))

    committed_items = [{'date': i['date'], 'label': i.get('legacy_label') or (i.get('category') or i['label']), 'amount_cents': i['amount_cents'],
                        'source': i['source'], 'transaction_type': i['transaction_type'], 'recurring_id': i['recurring_id'], 'kind': i['kind']}
                       for i in held_back if i['kind'] in ('bill', 'loan', 'tax') or i['key'] in ('saving_transfer', 'regular_investing')]
    committed = sum(i['amount_cents'] for i in committed_items)
    for item in held_back:
        item.pop('legacy_label', None)
    series = [{'label': p['date'], 'value_cents': p['balance_cents']} for p in preview['projected'] if p['date'] <= payday.isoformat()]
    components = [
        ('balance', 'Money in your account now', balance),
        ('committed', 'Bills and payments due before payday', committed),
        ('planned_saving', 'Your planned saving', planned_saving),
        ('everyday', 'Everyday costs until payday', everyday),
        ('buffer', 'Surprise costs', buffer),
        ('reserve', 'Kept aside as a safety cushion', reserve_floor_cents),
        ('free', 'Free until payday', free),
        ('spendable', 'Comfortable to spend until payday', spendable),
        ('per_day', 'About this much a day', per_day),
        ('this_week', 'About this much this week', this_week),
        ('safe_to_save', 'Could be saved', extra),
    ]
    unique_refs = list(dict.fromkeys(refs))
    assumption_texts = {locale: [_note_text(key, params, locale) for key, params in notes] for locale in _LOCALES}
    assumptions = assumption_texts['en']
    plan = {
        **scope,
        'as_of': reference.isoformat(),
        'reference_date': reference.isoformat(),
        'balance_cents': balance,
        'starting_balance_cents': balance,
        'starting_transaction_ref': preview['starting_transaction_ref'],
        'next_payday': payday.isoformat(),
        'days_to_payday': days,
        'days_until_payday': days,
        'payday_source': payday_source,
        'payday': {'source': payday_source, 'regular': pattern['regular'], 'weekend_rule': pattern['weekend_rule'],
                   'usual_day': pattern['dominant']['day'] if pattern['dominant'] else None,
                   'usual_kind': pattern['dominant']['kind'] if pattern['dominant'] else None,
                   'clusters': [{k: c[k] for k in ('kind', 'day', 'count', 'last_date')} for c in pattern['clusters']],
                   'salary_dates': pattern['salary_dates']},
        'salary_recurring_id': salary_item['id'] if salary_item else None,
        'held_back': held_back,
        'held_back_cents': held_total,
        'everyday_cents': everyday,
        'everyday_buffer_cents': everyday,
        'buffer_cents': buffer,
        'reserve_floor_cents': reserve_floor_cents,
        'reserve_floor_source': reserve_floor_source,
        'committed_cents': committed,
        'committed_items': committed_items,
        'skipped_declared_items': skipped,
        'planned_saving_cents': planned_saving,
        'planned_saving_basis': planned_basis,
        'free_cents': free,
        'shortfall_cents': shortfall,
        'shortfall_breakdown': breakdown,
        'upcoming_after_payday': upcoming,
        'cap_cents': cap,
        'spendable_until_payday_cents': spendable,
        'spendable_cents': spendable,
        'daily_life_cents': daily_life,
        'per_day_cents': per_day,
        'this_week_cents': this_week,
        'this_week_days': week_days,
        'extra_cents': extra,
        'safe_to_save_cents': extra,
        'safe_to_save_available': available,
        'available': available,
        'needs_history': not available,
        'unavailable_reason': None if available else 'At least thirty days of history are needed to estimate everyday costs',
        'steady_mode': steady,
        'must_pays_monthly_cents': must_pays,
        'protected_categories': sorted(protected),
        'emergency_fund': emergency,
        'basis': {
            'everyday_month_cents': everyday_month,
            'free_choice_month_cents': free_choice_month,
            'surprise_lookback_cents': totals['surprise'],
            'lookback_days': lookback,
            'window_days': WINDOW_DAYS,
            'window_count': window_count,
            'history_days': history_days,
            'cap_multiplier': format(multiplier.normalize(), 'f') if multiplier is not None else None,
            'min_daily_room_cents': MIN_DAILY_ROOM_CENTS,
            'rule': 'free = balance - held back - everyday; spendable = min(free, cap); could be saved = free - spendable',
        },
        'evidence': {'transaction_refs': unique_refs, 'comparison_transaction_refs': comparison_refs,
                     'query': {'start': scope['observed_start'], 'end': reference.isoformat()}},
        'components': [{'key': k, 'label': label, 'amount_cents': v, 'amount': _euro(v)} for k, label, v in components],
        'assumptions': assumptions,
        'assumption_texts': assumption_texts,
        'transaction_refs': unique_refs,
        'comparison_transaction_refs': comparison_refs,
        'chart': {'kind': 'runway', 'title': 'Expected balance until payday', 'basis': 'Scheduled items plus typical (median) everyday spending', 'series': series},
        'label': 'Estimated safe to spend until payday — not a guarantee',
        'scenario': True,
        'observed': False,
    }
    plan['summary'] = _summary(plan)
    plan['fact_id'] = fact_id('spending-plan', customer_id, reference.isoformat(), payday.isoformat(), reserve_floor_cents,
                              balance, held_total, everyday, cap, steady, sorted(protected), comparison_refs)
    return plan


def safe_until_payday(conn, customer_id, as_of=None, reserve_floor_cents=None, profile=None):
    """Compatibility name for ``spending_plan`` (same dict, same numbers)."""
    return spending_plan(conn, customer_id, as_of=as_of, profile=profile, reserve_floor_cents=reserve_floor_cents)
