"""Optional planning modules the customer can switch on: a mortgage plan and a tax plan.

Both live in the money profile (keys ``plan_mortgage`` and ``plan_tax``), so
they are listed on Me with a source label, can be edited or deleted there, are
audited and undoable, and "Forget everything" removes them.

``planning_set_asides(profile, as_of)`` turns the plans that are on into
monthly amounts to hold back on each payday (kind 'loan' and 'tax');
``money_profile.planning_inputs`` exposes them as ``plan_set_asides`` for the
spending plan. That function is pure: it needs only the profile and the date.

Nothing here is a loan offer, a credit decision, a tax decision or advice.
Customer text is produced by the UI from the codes and numbers returned here;
the few English sentences are for the AI coach and the API documentation.
"""
from datetime import date

from . import money_profile, mortgage, tax
from .ledger import account_scope

PLAN_KEYS = {'mortgage': 'plan_mortgage', 'tax': 'plan_tax'}
OMAVERO_TEXT = 'OmaVero (vero.fi)'
TAX_PLAN_FOOTER = 'Estimate from what you entered. Your tax decision in OmaVero is the official source.'
# Tax-card check: income this much above the card's income limit, or below it, is mentioned.
INCOME_ABOVE_LIMIT_BP = 10_500
INCOME_BELOW_LIMIT_BP = 8_000
# A back tax the customer expects (before any decision) is spread until this
# month and day of the next year, when back taxes are commonly first due.
EXPECTED_DUE_MONTH_DAY = (9, 1)


def _single(profile, key):
    found = profile.get('by_key', {}).get(key)
    if isinstance(found, list):
        return found[-1] if found else None
    return found


def _as_of_date(profile, as_of):
    value = as_of or profile.get('as_of')
    if isinstance(value, date):
        return value
    return date.fromisoformat(value) if value else date.today()


# ---------------------------------------------------------------- tax: pure parts

def _tax_entries(profile):
    return [e for e in profile.get('by_key', {}).get('tax', []) if e.get('active', True)]


def _decision_entry(profile, year):
    """The entered tax decision: last year's tax year first (decisions arrive the year after), then this year's."""
    entries = [e for e in _tax_entries(profile) if e['value'].get('decision_result')]
    for wanted in (year - 1, year):
        for entry in reversed(entries):
            if entry['value'].get('tax_year') == wanted:
                return entry
    return entries[-1] if entries else None


def _card_entry(profile, year):
    entries = [e for e in _tax_entries(profile) if e['value'].get('base_rate_bp') is not None]
    for entry in reversed(entries):
        if entry['value'].get('tax_year') == year:
            return entry
    return entries[-1] if entries else None


def _expected_due(day, calendar):
    """When an expected (not yet decided) back tax is planned to be due: next year, about September."""
    month, dom = EXPECTED_DUE_MONTH_DAY
    if calendar:
        typical = (calendar.get('back_tax_instalments_by_assessment_end_month') or {}).get('%d-07' % day.year)
        if typical:
            first = date.fromisoformat(typical[0])
            month, dom = first.month, first.day
    return date(day.year + 1, month, dom)


def tax_set_aside(profile, as_of=None):
    """Monthly amount to put aside for back taxes, from the profile only (no database).

    Sources, added together: back taxes on an entered tax decision (split over
    its instalments, money already set aside counts toward the earliest), and a
    back tax the customer expects for this year (``plan_tax.expected_back_tax_cents``),
    spread until about September next year.
    Returns {monthly_cents, remaining_cents, until (ISO or None), instalments:
    [{due_date, amount_cents, already_set_aside_cents, monthly_cents, source:
    'tax_decision'|'your_estimate', date_is_estimate}]}.
    """
    day = _as_of_date(profile, as_of)
    calendar = tax.load_tax_calendar(day.year)
    instalments = []
    decision = _decision_entry(profile, day.year)
    if decision and decision['value'].get('decision_result') == 'back_tax' and decision['value'].get('decision_amount_cents'):
        clean = tax._clean_tax(decision['value'])
        dates, source = tax._back_tax_dates(clean, calendar)
        estimate = False
        if not dates:
            dates, estimate = [_expected_due(day, calendar).isoformat() if day.month >= 11 else date(day.year, 12, 1).isoformat()], True
        amount = clean['decision_amount_cents']
        share, odd = divmod(amount, len(dates))
        left = clean['already_set_aside_cents'] or 0
        for index, due in enumerate(dates):
            part = share + (odd if index == 0 else 0)
            used = min(left, part)
            left -= used
            instalments.append({'due_date': due, 'amount_cents': part, 'already_set_aside_cents': used,
                                'source': 'tax_decision', 'date_is_estimate': estimate})
    plan = _single(profile, 'plan_tax')
    expected = plan['value'].get('expected_back_tax_cents') if plan else None
    if expected:
        instalments.append({'due_date': _expected_due(day, calendar).isoformat(), 'amount_cents': expected,
                            'already_set_aside_cents': 0, 'source': 'your_estimate', 'date_is_estimate': True})
    monthly = remaining = 0
    until = None
    for item in instalments:
        item['monthly_cents'] = 0
        if date.fromisoformat(item['due_date']) <= day:
            item['status'] = 'due_date_passed'
            continue
        item['status'] = 'upcoming'
        scenario = tax.tax_planning_scenario(item['amount_cents'], item['due_date'], day.isoformat(),
                                             already_set_aside_cents=item['already_set_aside_cents'])
        item['monthly_cents'] = scenario['required_monthly_set_aside_cents']
        monthly += item['monthly_cents']
        remaining += scenario['remaining_cents']
        until = max(until or item['due_date'], item['due_date'])
    return {'monthly_cents': monthly, 'remaining_cents': remaining, 'until': until, 'instalments': instalments}


def planning_set_asides(profile, as_of=None):
    """Monthly amounts the switched-on plans hold back on each payday (pure; profile only).

    Returns a list of {kind: 'loan'|'tax', plan: 'mortgage'|'tax', label,
    amount_cents (per month), day_of_month (int|None), until (ISO|None),
    dedupe_hint: {transaction_type, amount_cents}|None}. ``dedupe_hint`` tells a
    consumer that a recurring account payment of about this amount may already
    be the same money (e.g. the mortgage paid as a housing payment), so it must
    not be held back twice. Plans that are off, or that cannot be calculated,
    are left out.
    """
    day = _as_of_date(profile, as_of)
    out = []
    entry = _single(profile, 'plan_mortgage')
    if entry:
        try:
            result = mortgage.projection(entry['value'], day.isoformat())
        except ValueError:
            result = None
        if result and result['monthly_payment_cents'] > 0:
            out.append({'kind': 'loan', 'plan': 'mortgage', 'label': 'Mortgage payment',
                        'amount_cents': result['monthly_payment_cents'], 'day_of_month': entry['value'].get('payment_day'),
                        'until': result['payoff_month'],
                        'dedupe_hint': {'transaction_type': entry['value'].get('paid_as') or 'housing_payment',
                                        'amount_cents': result['monthly_payment_cents']}})
    if _single(profile, 'plan_tax'):
        plan = tax_set_aside(profile, day)
        if plan['monthly_cents'] > 0:
            out.append({'kind': 'tax', 'plan': 'tax', 'label': 'Money for back taxes', 'amount_cents': plan['monthly_cents'],
                        'day_of_month': None, 'until': plan['until'], 'dedupe_hint': None})
    return out


# ---------------------------------------------------------------- database-backed views

def _reference(conn, customer_id, as_of):
    scope = account_scope(conn, customer_id)
    return as_of or scope['observed_end']


def _entry_meta(entry):
    if not entry:
        return {'on': False, 'entry_id': None, 'source': None, 'source_label': None, 'updated_at': None}
    return {'on': True, 'entry_id': entry['id'], 'source': entry['source'], 'source_label': entry['source_label'],
            'updated_at': entry['updated_at']}


def mortgage_plan(conn, customer_id, as_of=None, *, extra_cents=0, rate_delta_bp=0, profile=None):
    """The mortgage plan card: the saved plan's projection (or a prefill to start one).

    Returns {plan: 'mortgage', on, entry_id, source, source_label, steady,
    prefill (detect_loan_payment), projection (mortgage.projection or None),
    error (str|None), footer}.
    """
    as_of = _reference(conn, customer_id, as_of)
    profile = profile or money_profile.get_profile(conn, customer_id, as_of)
    entry = _single(profile, 'plan_mortgage')
    steady = profile.get('mode') == 'steady'
    target = _single(profile, 'emergency_fund_target_months')
    buffer = mortgage.buffer_check(conn, customer_id, as_of, target['value'] if target else None)
    result = {'plan': 'mortgage', **_entry_meta(entry), 'as_of': as_of, 'steady': steady,
              'prefill': mortgage.detect_loan_payment(conn, customer_id, as_of), 'projection': None, 'error': None,
              'footer': mortgage.CHECK_WITH_BANK, 'estimate': True}
    if entry:
        try:
            result['projection'] = mortgage.projection(entry['value'], as_of, extra_cents=extra_cents,
                                                       rate_delta_bp=rate_delta_bp, buffer=buffer, steady=steady)
        except ValueError as error:
            result['error'] = str(error)
    return result


def _tax_card_check(conn, customer_id, as_of, card):
    """Does the tax card look right for this year's income? Suggestion only; OmaVero decides."""
    if not card:
        return {'status': 'missing', 'missing': ['gross_monthly_cents', 'base_rate_bp']}
    estimate = tax.withholding_estimate(conn, customer_id, as_of, card['value'])
    if not estimate['available']:
        return {'status': 'missing', 'missing': ['gross_monthly_cents' if 'gross' in m else 'base_rate_bp' for m in estimate['missing']]}
    limit = card['value'].get('income_limit_cents')
    projected = estimate['projected_gross_full_year_cents'] or estimate['gross_ytd_cents']
    status = 'looks_ok'
    if limit and projected * 10_000 > limit * INCOME_ABOVE_LIMIT_BP:
        status = 'income_above_limit'
    elif limit and projected * 10_000 < limit * INCOME_BELOW_LIMIT_BP:
        status = 'income_below_limit'
    elif estimate['gap_is_large']:
        status = 'pay_differs'
    return {'status': status, 'projected_gross_cents': projected, 'income_limit_cents': limit,
            'withheld_ytd_cents': estimate['withheld_ytd_cents'],
            'projected_withheld_cents': estimate['projected_withheld_full_year_cents'],
            'salary_months': estimate['salary_months'], 'transaction_refs': estimate['transaction_refs']}


def tax_plan(conn, customer_id, as_of=None, *, profile=None):
    """The tax plan card: monthly set-aside, refund expectation, tax-card check and dates.

    Returns {plan: 'tax', on, entry_id, source, source_label, as_of, steady,
    tax_year (this year's income), has_decision, set_aside (tax_set_aside),
    refund {amount_cents, expected_date, source, seen, seen_date}|None,
    tax_card {status: 'missing'|'looks_ok'|'income_above_limit'|
    'income_below_limit'|'pay_differs', ...}, stage {stage, label, next_date,
    days_until, date_source, check_note}, dates [{date, kind}], omavero_text,
    tasks [English sentences for the AI], footer}.
    """
    as_of = _reference(conn, customer_id, as_of)
    day = date.fromisoformat(as_of)
    profile = profile or money_profile.get_profile(conn, customer_id, as_of)
    entry = _single(profile, 'plan_tax')
    decision = _decision_entry(profile, day.year)
    card = _card_entry(profile, day.year)
    calendar = tax.load_tax_calendar(day.year)
    decision_value = decision['value'] if decision else None
    cycle = tax.tax_cycle_status(conn, customer_id, as_of, decision_value, calendar)
    refund = None
    if decision_value and decision_value.get('decision_result') == 'refund' and decision_value.get('decision_amount_cents'):
        expected, source = tax._refund_date(tax._clean_tax(decision_value), calendar)
        seen = cycle.get('refund_seen') or {}
        refund = {'amount_cents': decision_value['decision_amount_cents'], 'expected_date': expected, 'source': 'tax_decision',
                  'seen': bool(seen.get('seen')), 'seen_date': (seen.get('match') or {}).get('date')}
    elif entry and entry['value'].get('expected_refund_cents'):
        refund = {'amount_cents': entry['value']['expected_refund_cents'], 'expected_date': None, 'source': 'your_estimate',
                  'seen': False, 'seen_date': None}
    set_aside = tax_set_aside(profile, day)
    dates = []
    for item in set_aside['instalments']:
        if item['status'] == 'upcoming':
            dates.append({'date': item['due_date'], 'kind': 'back_tax', 'estimate': item['date_is_estimate']})
    if refund and refund['expected_date'] and refund['expected_date'] >= as_of and not refund['seen']:
        dates.append({'date': refund['expected_date'], 'kind': 'refund', 'estimate': False})
    if cycle.get('next_date') and cycle['stage'] in ('return_coming', 'check_return', 'decision_pending'):
        dates.append({'date': cycle['next_date'], 'kind': cycle['stage'], 'estimate': cycle.get('date_source') != 'tax_decision'})
    dates.sort(key=lambda item: item['date'])
    card_check = _tax_card_check(conn, customer_id, as_of, card)
    tasks = []
    if set_aside['monthly_cents']:
        tasks.append('Put aside about %s a month until %s for back taxes.' % (tax._euro(set_aside['monthly_cents']), set_aside['until']))
    if refund:
        tasks.append('A tax refund of about %s is expected%s.' % (tax._euro(refund['amount_cents']),
                     ' on or around ' + refund['expected_date'] if refund['expected_date'] else ' after the tax decision'))
    if card_check['status'] == 'income_above_limit':
        tasks.append('Income this year looks higher than the income limit on the tax card; a new tax card from OmaVero can help avoid back taxes.')
    elif card_check['status'] == 'income_below_limit':
        tasks.append('Income this year looks clearly lower than the income limit on the tax card; the customer may get a refund, or can change the tax card in OmaVero.')
    elif card_check['status'] == 'missing':
        tasks.append('To check the tax card, the customer can add their gross monthly salary and tax-card rate.')
    return {'plan': 'tax', **_entry_meta(entry), 'as_of': as_of, 'steady': profile.get('mode') == 'steady',
            'tax_year': day.year, 'has_decision': decision is not None, 'set_aside': set_aside, 'refund': refund,
            'tax_card': card_check,
            'stage': {'stage': cycle['stage'], 'label': cycle['stage_label'], 'next_date': cycle['next_date'],
                      'days_until': cycle['days_until'], 'date_source': cycle['date_source'], 'check_note': cycle['check_mytax_note']},
            'dates': dates, 'omavero_text': OMAVERO_TEXT, 'tasks': tasks, 'footer': TAX_PLAN_FOOTER,
            'estimate': True, 'not_tax_advice': True}


def plans_overview(conn, customer_id, as_of=None):
    """Which plans exist and which are on: GET /api/plans.

    Returns {as_of, steady, plans: [{id: 'mortgage'|'tax', on, entry_id, source,
    source_label, monthly_cents (held back each payday when on, else None),
    detected (mortgage: a likely loan payment was found)}], set_asides
    (planning_set_asides), held_back_monthly_cents}.
    """
    as_of = _reference(conn, customer_id, as_of)
    profile = money_profile.get_profile(conn, customer_id, as_of)
    set_asides = planning_set_asides(profile, as_of)
    monthly = {item['plan']: item['amount_cents'] for item in set_asides}
    detected = mortgage.detect_loan_payment(conn, customer_id, as_of)
    plans = []
    for plan_id, key in PLAN_KEYS.items():
        entry = _single(profile, key)
        plans.append({'id': plan_id, **_entry_meta(entry), 'monthly_cents': monthly.get(plan_id, 0 if entry else None),
                      'detected': bool(detected['found']) if plan_id == 'mortgage' else None})
    return {'as_of': as_of, 'steady': profile.get('mode') == 'steady', 'plans': plans, 'set_asides': set_asides,
            'held_back_monthly_cents': sum(item['amount_cents'] for item in set_asides)}


def save_plan(conn, customer_id, plan_id, value, *, as_of=None, source='you_told_me', provenance='user'):
    """Save (switch on or change) a plan as a money-profile entry; audited and undoable.

    A mortgage plan is checked by running its projection first, so a plan
    whose payment cannot repay the loan is refused with a plain message.
    Returns money_profile.save_entry(...) result.
    """
    if plan_id not in PLAN_KEYS:
        raise ValueError('plan must be mortgage or tax')
    key = PLAN_KEYS[plan_id]
    clean = money_profile.validate_entry(key, value)
    if plan_id == 'mortgage':
        mortgage.projection(clean, _reference(conn, customer_id, as_of))
    return money_profile.save_entry(conn, customer_id, key, clean, source, provenance=provenance)
