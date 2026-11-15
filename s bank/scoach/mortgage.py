"""Optional mortgage plan: repayment arithmetic from what the customer entered.

Finnish home loans are usually tied to a reference rate (most often the
12-month Euribor) plus a fixed bank margin, and are repaid either as an
annuity (tasaerä: the same payment every month while the rate stays the same)
or with equal principal (tasalyhennys: the same principal every month, so the
payment falls as interest falls). The reference rate is checked on the loan's
rate-check date (once a year for the 12-month Euribor) and the payment changes
then.

Everything here is an estimate from the customer's own numbers. No rate is
looked up, no credit decision is made and no product is recommended. Amounts
are integer cents; rates are basis points (1 % = 100 bp).
"""
from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP, localcontext

from .ledger import account_scope, fact_id, month_bounds, shift_month, transactions
from .money import median_cents

LOAN_TYPES = ('annuity', 'equal_principal')
REFERENCE_RATES = ('euribor_12m', 'euribor_6m', 'euribor_3m', 'fixed', 'other')
MAX_MONTHS = 600  # 50 years: a hard stop for every simulation
RATE_STEP_BP = 100  # the "+1 / -1 percentage point" what-if
# A typed payment that differs from the calculated one by more than this share
# is reported (it may include fees or insurance, or the term may be off).
PAYMENT_DIFF_NOTE_BP = 300
# Thin buffer: less than this many months of typical spending in the account,
# unless the customer set their own emergency-fund target.
DEFAULT_BUFFER_MONTHS = 1
DETECTION_MONTHS = 6
CHECK_WITH_BANK = 'Estimate from the numbers you entered. Your loan statement and your bank have the exact figures.'
# The "pay a little extra" what-ifs shown side by side in the rich result (€50 / €100 / €200 a month).
EXTRA_STEPS_CENTS = (5_000, 10_000, 20_000)
# A realistic Finnish home loan for the read-only example (V5 lane MG): €180,000 left,
# annuity, 12-month Euribor 2.30 % + bank margin 0.60 %, 22 years left.
EXAMPLE_PLAN = {'principal_cents': 18_000_000, 'loan_type': 'annuity', 'reference_rate': 'euribor_12m',
                'reference_rate_bp': 230, 'margin_bp': 60, 'remaining_months': 264}
# When the account shows a likely loan payment, the example loan is sized so its annuity
# payment is about that amount (rounded down to whole thousands of euros), within these bounds.
EXAMPLE_PRINCIPAL_BOUNDS_CENTS = (2_000_000, 60_000_000)


def _d(value):
    return Decimal(value)


def _monthly_rate(rate_bp):
    return _d(rate_bp) / _d(10_000) / _d(12)


def _half_up(value):
    return int(value.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _ceil(value):
    return int(value.quantize(Decimal('1'), rounding=ROUND_CEILING))


def annuity_payment(principal_cents, rate_bp, months):
    """Monthly annuity payment in cents (rounded up to the next cent)."""
    if principal_cents <= 0:
        return 0
    if months < 1:
        raise ValueError('months must be at least 1')
    with localcontext() as context:
        context.prec = 40
        r = _monthly_rate(rate_bp)
        if r == 0:
            return _ceil(_d(principal_cents) / months)
        factor = (1 + r) ** months
        return _ceil(_d(principal_cents) * r * factor / (factor - 1))


def simulate(principal_cents, rate_bp, loan_type, *, months=None, payment_cents=None, extra_cents=0):
    """Month-by-month repayment.

    Annuity: pays ``payment_cents`` (or the annuity payment for ``months``) plus
    ``extra_cents`` each month. Equal principal: pays principal/months plus
    interest plus ``extra_cents``. Extra money always goes to principal, so the
    loan ends sooner and the regular payment stays the same.
    Returns {months, total_interest_cents, total_paid_cents, first_payment_cents,
    last_payment_cents, rows: [{n, payment_cents, interest_cents, principal_cents, balance_cents}]}.
    Raises ValueError when the payment does not cover the interest.
    """
    if loan_type not in LOAN_TYPES:
        raise ValueError('loan_type must be annuity or equal_principal')
    if loan_type == 'equal_principal' and not months:
        raise ValueError('An equal-principal loan needs the years left')
    if loan_type == 'annuity' and payment_cents is None:
        payment_cents = annuity_payment(principal_cents, rate_bp, months)
    instalment = _ceil(_d(principal_cents) / months) if loan_type == 'equal_principal' else None
    r = _monthly_rate(rate_bp)
    balance = principal_cents
    rows = []
    total_interest = 0
    while balance > 0:
        if len(rows) >= MAX_MONTHS:
            raise ValueError('The loan would not be repaid within 50 years with this payment')
        interest = _half_up(_d(balance) * r)
        if loan_type == 'annuity':
            principal = payment_cents - interest + extra_cents
        else:
            principal = instalment + extra_cents
        if principal <= 0:
            raise ValueError('The monthly payment does not cover the interest')
        principal = min(principal, balance)
        balance -= principal
        total_interest += interest
        rows.append({'n': len(rows) + 1, 'payment_cents': principal + interest, 'interest_cents': interest,
                     'principal_cents': principal, 'balance_cents': balance})
    return {
        'months': len(rows),
        'total_interest_cents': total_interest,
        'total_paid_cents': principal_cents + total_interest,
        'first_payment_cents': rows[0]['payment_cents'] if rows else 0,
        'regular_payment_cents': (payment_cents + extra_cents) if loan_type == 'annuity' else (rows[0]['payment_cents'] if rows else 0),
        'rows': rows,
    }


def _clean(plan):
    if not isinstance(plan, dict):
        raise ValueError('plan must be an object')
    principal = plan.get('principal_cents')
    if type(principal) is not int or principal <= 0:
        raise ValueError('principal_cents must be positive integer cents')
    loan_type = plan.get('loan_type', 'annuity')
    if loan_type not in LOAN_TYPES:
        raise ValueError('loan_type must be annuity or equal_principal')
    reference = plan.get('reference_rate_bp', 0)
    margin = plan.get('margin_bp', 0)
    for name, value in (('reference_rate_bp', reference), ('margin_bp', margin)):
        if type(value) is not int:
            raise ValueError(name + ' must be integer basis points')
    months = plan.get('remaining_months')
    payment = plan.get('monthly_payment_cents')
    if months is None and payment is None:
        raise ValueError('Give the years left or the monthly payment')
    if loan_type == 'equal_principal' and months is None:
        raise ValueError('An equal-principal loan needs the years left')
    return {'principal_cents': principal, 'loan_type': loan_type, 'reference_rate': plan.get('reference_rate', 'euribor_12m'),
            'reference_rate_bp': reference, 'margin_bp': margin, 'rate_bp': max(reference + margin, 0),
            'remaining_months': months, 'monthly_payment_cents': payment,
            'payment_day': plan.get('payment_day'), 'next_rate_check': plan.get('next_rate_check')}


def _run(clean, rate_bp, extra_cents=0, payment_cents=None):
    """Simulate the plan with ONE payment: the one the customer is shown and that is held back.

    Annuity: a typed monthly payment wins (the payoff date is solved from it, even when
    years left were also given); otherwise the annuity payment for the years left.
    ``payment_cents`` overrides the payment (rate what-ifs). Equal principal: the years left.
    """
    if clean['loan_type'] == 'annuity' and (payment_cents is not None or clean['monthly_payment_cents'] is not None):
        payment = payment_cents if payment_cents is not None else clean['monthly_payment_cents']
        return simulate(clean['principal_cents'], rate_bp, 'annuity', payment_cents=payment, extra_cents=extra_cents)
    if clean['loan_type'] == 'annuity':
        payment = annuity_payment(clean['principal_cents'], rate_bp, clean['remaining_months'])
        return simulate(clean['principal_cents'], rate_bp, 'annuity', payment_cents=payment, extra_cents=extra_cents)
    return simulate(clean['principal_cents'], rate_bp, 'equal_principal', months=clean['remaining_months'], extra_cents=extra_cents)


def _month_after(start_month, months):
    return shift_month(start_month, months)


def _yearly(rows, first_month):
    years = {}
    for row in rows:
        year = int(_month_after(first_month, row['n'] - 1)[:4])
        item = years.setdefault(year, {'year': year, 'interest_cents': 0, 'principal_cents': 0, 'end_balance_cents': 0})
        item['interest_cents'] += row['interest_cents']
        item['principal_cents'] += row['principal_cents']
        item['end_balance_cents'] = row['balance_cents']
    return list(years.values())


def principal_for_payment(payment_cents, rate_bp, months):
    """The loan an annuity of ``payment_cents`` a month repays in ``months`` (cents, rounded down)."""
    if payment_cents <= 0 or months < 1:
        return 0
    with localcontext() as context:
        context.prec = 40
        r = _monthly_rate(rate_bp)
        if r == 0:
            return payment_cents * months
        value = _d(payment_cents) * (1 - (1 + r) ** -months) / r
        return int(value.to_integral_value(rounding='ROUND_FLOOR'))


def example_plan(prefill=None):
    """Inputs for the read-only example: the generic Finnish loan, or one sized to the detected payment.

    Returns (plan, basis) where basis is 'generic' or 'detected_payment'. A payment the
    customer saved in the money profile, or one seen as a housing/loan payment, sizes the
    example loan so the example payment is close to what they already pay each month.
    """
    plan = dict(EXAMPLE_PLAN)
    payment = (prefill or {}).get('monthly_payment_cents') if (prefill or {}).get('found') else None
    if type(payment) is int and payment > 0:
        principal = principal_for_payment(payment, plan['reference_rate_bp'] + plan['margin_bp'], plan['remaining_months'])
        principal = principal // 100_000 * 100_000
        low, high = EXAMPLE_PRINCIPAL_BOUNDS_CENTS
        if low <= principal <= high:
            plan['principal_cents'] = principal
            if (prefill or {}).get('payment_day'):
                plan['payment_day'] = prefill['payment_day']
            return plan, 'detected_payment'
    return plan, 'generic'


def _curve(principal_cents, rows, first_month):
    """Loan balance at the start and after every 12 payments (and at the end): chart points."""
    points = [{'n': 0, 'month': shift_month(first_month, -1), 'balance_cents': principal_cents}]
    for row in rows:
        if row['n'] % 12 == 0 or row['n'] == len(rows):
            points.append({'n': row['n'], 'month': _month_after(first_month, row['n'] - 1), 'balance_cents': row['balance_cents']})
    return points


def _split(rows):
    """Interest vs principal over the first and the last 12 payments (or fewer when the loan is short)."""
    def total(part):
        return {'payments': len(part), 'interest_cents': sum(r['interest_cents'] for r in part),
                'principal_cents': sum(r['principal_cents'] for r in part), 'paid_cents': sum(r['payment_cents'] for r in part)}
    if not rows:
        return None
    return {'first_year': total(rows[:12]), 'last_year': total(rows[-12:]) if len(rows) > 12 else None}


def _detail(clean, base, first_month, steady):
    """Rich-result extras for the UI: balance curve, principal/interest split, years left and the extra-payment what-ifs."""
    years, months = divmod(base['months'], 12)
    options = []
    if not steady:
        for step in EXTRA_STEPS_CENTS:
            run = _run(clean, clean['rate_bp'], step)
            options.append({'extra_cents': step, 'months_left': run['months'], 'months_saved': base['months'] - run['months'],
                            'interest_saved_cents': base['total_interest_cents'] - run['total_interest_cents'],
                            'total_interest_cents': run['total_interest_cents'],
                            'payoff_month': _month_after(first_month, run['months'] - 1),
                            'balance_curve': _curve(clean['principal_cents'], run['rows'], first_month)})
    return {'years_left': {'years': years, 'months': months},
            'balance_curve': _curve(clean['principal_cents'], base['rows'], first_month),
            'split': _split(base['rows']), 'extra_options': options}


def projection(plan, as_of, *, extra_cents=0, rate_delta_bp=0, buffer=None, steady=False, detail=False):
    """Repayment projection for a saved (or draft) mortgage plan.

    Args:
        plan: the plan_mortgage value (principal_cents, loan_type, reference_rate,
            reference_rate_bp, margin_bp, remaining_months?, monthly_payment_cents?,
            payment_day?, next_rate_check?).
        as_of: ISO date; the first payment is in the following month.
        extra_cents: extra principal each month for the what-if (0-1 000 000).
        rate_delta_bp: what-if change to the reference rate (-500..500).
        buffer: optional {'balance_cents', 'monthly_spending_cents', 'target_months'}
            from buffer_check, used for the gentle note before extra payments.
        steady: True in steady coaching mode: extra payments are never suggested.
        detail: True adds the rich result for the UI: years_left {years, months},
            balance_curve [{n, month, balance_cents}] (start + every 12 payments),
            split {first_year, last_year: {payments, interest_cents, principal_cents,
            paid_cents}|None}, extra_options [{extra_cents (EUR 50/100/200), months_left,
            months_saved, interest_saved_cents, total_interest_cents, payoff_month,
            balance_curve}] (empty in steady mode).
    Returns dict with monthly_payment_cents (the ONE payment of the card: held back each
    payday and the base of every total, the payoff date, the yearly split and the rate
    what-ifs), calculated_payment_cents (what the years left alone would need; differs only
    to explain a typed payment, see notes 'payment_differs'), term_basis ('payment' when a
    typed annuity payment sets the payoff date, else 'years'), entered_months, payoff_month, months_left, total_interest_cents,
    rate_bp, next_rate_check, yearly [...], what_if {extra_cents, months_saved,
    interest_saved_cents, payoff_month} or None, rate_change {up, down, ...},
    selected_rate {...} when rate_delta_bp != 0, extra_advice {suggest: bool,
    reason: 'steady'|'buffer_thin'|None}, notes [codes], estimate True, footer.
    """
    clean = _clean(plan)
    if type(extra_cents) is not int or not 0 <= extra_cents <= 1_000_000:
        raise ValueError('extra_cents must be 0 to 1000000')
    if type(rate_delta_bp) is not int or not -500 <= rate_delta_bp <= 500:
        raise ValueError('rate_delta_bp must be -500 to 500')
    day = date.fromisoformat(as_of)
    first_month = shift_month(day.strftime('%Y-%m'), 1)
    base = _run(clean, clean['rate_bp'])
    typed = clean['monthly_payment_cents']
    if clean['loan_type'] == 'annuity' and clean['remaining_months'] is not None:
        # What the years left alone would need; shown only to explain a typed payment that differs.
        calculated = annuity_payment(clean['principal_cents'], clean['rate_bp'], clean['remaining_months'])
    else:
        calculated = base['regular_payment_cents'] if clean['loan_type'] == 'annuity' else base['first_payment_cents']
    # The ONE payment of the card: held back on payday, and the base of the totals, the payoff
    # date, the yearly split and the rate what-ifs (V5 fix: never mix typed and calculated).
    held = typed if typed is not None else (base['regular_payment_cents'] if clean['loan_type'] == 'annuity' else base['first_payment_cents'])
    term_basis = 'payment' if clean['loan_type'] == 'annuity' and typed is not None else 'years'
    notes = []
    if clean['monthly_payment_cents'] is not None and clean['remaining_months'] is not None and calculated:
        diff = abs(clean['monthly_payment_cents'] - calculated) * 10_000
        if diff > PAYMENT_DIFF_NOTE_BP * calculated:
            notes.append('payment_differs')
    if clean['loan_type'] == 'equal_principal':
        notes.append('payment_falls')
    if clean['reference_rate'] != 'fixed':
        notes.append('rate_checked')

    def scenario(delta):
        rate = max(clean['rate_bp'] + delta, 0)
        if clean['loan_type'] == 'annuity' and typed is not None and clean['remaining_months'] is not None:
            # A Finnish annuity keeps its term when the reference rate is checked: the payment
            # shown moves by what the same loan and term need at the new rate.
            months = base['months']
            change = (annuity_payment(clean['principal_cents'], rate, months)
                      - annuity_payment(clean['principal_cents'], clean['rate_bp'], months))
            pay = held + change
            run = _run(clean, rate, payment_cents=pay)
        elif clean['loan_type'] == 'annuity' and typed is not None:
            # Payment fixed by the customer and no term: a rate change changes the term instead.
            run = _run(clean, rate)
            pay = held
        else:
            run = _run(clean, rate)
            pay = held + ((run['regular_payment_cents'] if clean['loan_type'] == 'annuity' else run['first_payment_cents'])
                          - (base['regular_payment_cents'] if clean['loan_type'] == 'annuity' else base['first_payment_cents']))
        return {'rate_bp': rate, 'monthly_payment_cents': pay, 'payment_change_cents': pay - held,
                'months_left': run['months'], 'total_interest_cents': run['total_interest_cents'],
                'interest_change_cents': run['total_interest_cents'] - base['total_interest_cents']}

    try:
        up = scenario(RATE_STEP_BP)
    except ValueError:
        up = None
    down = scenario(-RATE_STEP_BP)
    selected = None
    if rate_delta_bp:
        try:
            selected = scenario(rate_delta_bp)
        except ValueError:
            selected = None
    what_if = None
    if extra_cents:
        run = _run(clean, clean['rate_bp'], extra_cents)
        what_if = {'extra_cents': extra_cents, 'months_left': run['months'], 'months_saved': base['months'] - run['months'],
                   'interest_saved_cents': base['total_interest_cents'] - run['total_interest_cents'],
                   'payoff_month': _month_after(first_month, run['months'] - 1)}
    reason = None
    if steady:
        reason = 'steady'
    elif buffer and buffer.get('thin'):
        reason = 'buffer_thin'
    result = {
        'available': True,
        'inputs': {k: clean[k] for k in ('principal_cents', 'loan_type', 'reference_rate', 'reference_rate_bp', 'margin_bp',
                                          'remaining_months', 'monthly_payment_cents', 'payment_day', 'next_rate_check')},
        'as_of': as_of,
        'rate_bp': clean['rate_bp'],
        'monthly_payment_cents': held,
        'calculated_payment_cents': calculated,
        'term_basis': term_basis,
        'entered_months': clean['remaining_months'],
        'first_payment_month': first_month,
        'months_left': base['months'],
        'payoff_month': _month_after(first_month, base['months'] - 1),
        'total_interest_cents': base['total_interest_cents'],
        'total_paid_cents': base['total_paid_cents'],
        'next_rate_check': clean['next_rate_check'],
        'yearly': _yearly(base['rows'], first_month),
        'first_months': base['rows'][:12],
        'what_if': what_if,
        'rate_change': {'step_bp': RATE_STEP_BP, 'up': up, 'down': down},
        'selected_rate': selected,
        'buffer': buffer,
        'extra_advice': {'suggest': reason is None, 'reason': reason},
        'notes': notes,
        'estimate': True,
        'observed': False,
        'footer': CHECK_WITH_BANK,
    }
    if detail:
        result.update(_detail(clean, base, first_month, steady))
    result['fact_id'] = fact_id('mortgage-projection', sorted(result['inputs'].items(), key=lambda i: i[0]), as_of, extra_cents, rate_delta_bp)
    return result


# ---------------------------------------------------------------- from the account

def _complete_months(conn, customer_id, as_of, count):
    scope = account_scope(conn, customer_id)
    day = date.fromisoformat(as_of)
    month = day.strftime('%Y-%m')
    if as_of < month_bounds(month)[1]:
        month = shift_month(month, -1)
    first = shift_month(month, 1 - count)
    start = max(month_bounds(first)[0], scope['observed_start'])
    end = month_bounds(month)[1]
    return start, end


def detect_loan_payment(conn, customer_id, as_of):
    """A likely monthly home-loan payment from the account, for prefilling the form.

    Looks at housing payments (and payments labelled as loans) over the last six
    complete months. Housing payments may also be rent, so the result is only a
    suggestion the customer confirms. A saved 'mortgage' loan in the money
    profile wins. A home-loan application recorded as approved can suggest the
    loan amount; any other recorded outcome is not used.
    Returns {found, monthly_payment_cents, payment_day, months_seen, source
    ('profile'|'housing_payment'|'loan_payment'|None), principal_cents|None,
    principal_source, transaction_refs}.
    """
    from . import money_profile
    from .financing import financing_context
    result = {'found': False, 'monthly_payment_cents': None, 'payment_day': None, 'months_seen': 0, 'source': None,
              'principal_cents': None, 'principal_source': None, 'transaction_refs': []}
    profile = money_profile.get_profile(conn, customer_id, as_of)
    mortgage_debts = [e for e in profile['by_key'].get('debts', []) if e['value'].get('type') == 'mortgage']
    if mortgage_debts:
        value = mortgage_debts[-1]['value']
        result.update(found=True, monthly_payment_cents=value['monthly_payment_cents'], source='profile')
        if value.get('remaining_cents'):
            result.update(principal_cents=value['remaining_cents'], principal_source='profile')
    start, end = _complete_months(conn, customer_id, as_of, DETECTION_MONTHS)
    rows = transactions(conn, customer_id, start, end) if start <= end else []
    for kind in ('loan_payment', 'housing_payment'):
        selected = [r for r in rows if r['amount_cents'] < 0 and (r['transaction_type'] == kind or (
            kind == 'loan_payment' and any(w in (r['category'] or '').lower() for w in money_profile.LOAN_WORDS)))]
        by_month = {}
        for row in selected:
            by_month.setdefault(row['date'][:7], []).append(row)
        if len(by_month) < 3:
            continue
        amounts = [-sum(r['amount_cents'] for r in group) for group in by_month.values()]
        days = [int(group[0]['date'][8:]) for group in by_month.values()]
        if not result['found']:
            result.update(found=True, monthly_payment_cents=median_cents(amounts), source=kind)
        result.update(payment_day=median_cents(days), months_seen=len(by_month),
                      transaction_refs=[r['transaction_ref'] for r in selected])
        break
    if result['principal_cents'] is None:
        try:
            history = financing_context(conn, customer_id, 'home')
        except ValueError:
            history = {'available': False}
        decision = (history.get('recorded_outcome') or {}).get('decision') if history.get('available') else None
        if decision in ('approved', 'accepted', 'granted') and history.get('requested_loan_cents'):
            result.update(principal_cents=history['requested_loan_cents'], principal_source='loan_application')
    return result


def buffer_check(conn, customer_id, as_of, target_months=None):
    """Is the money in the account a thin cushion? Used before suggesting extra loan payments.

    Compares the balance on as_of with the median monthly spending (purchases,
    housing and utilities) over the last six complete months.
    Returns {balance_cents, monthly_spending_cents, target_months, months_covered
    (one decimal, str), thin (bool)} or None without enough history.
    """
    history = transactions(conn, customer_id, end=as_of)
    if not history:
        return None
    balance = history[-1]['balance_after_cents']
    start, end = _complete_months(conn, customer_id, as_of, DETECTION_MONTHS)
    rows = transactions(conn, customer_id, start, end) if start <= end else []
    by_month = {}
    for row in rows:
        if row['amount_cents'] < 0 and row['transaction_type'] in ('purchase', 'housing_payment', 'utilities_payment'):
            by_month[row['date'][:7]] = by_month.get(row['date'][:7], 0) - row['amount_cents']
    if len(by_month) < 2:
        return None
    monthly = median_cents(list(by_month.values()))
    target = target_months if target_months else DEFAULT_BUFFER_MONTHS
    covered = (Decimal(balance) / monthly).quantize(Decimal('.1'), rounding=ROUND_HALF_UP) if monthly else None
    return {'balance_cents': balance, 'monthly_spending_cents': monthly, 'target_months': target,
            'months_covered': format(covered, 'f') if covered is not None else None,
            'thin': bool(monthly) and balance < Decimal(str(target)) * monthly}
