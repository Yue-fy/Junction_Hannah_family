"""Money in versus money out per month or year, from observed ledger rows.

Definitions (all integer cents, from ``ledger.transactions`` so user rules apply):

* ``income_cents`` = signed sum of ``salary`` + ``other_income`` rows
  (``analytics.money_map`` salary_cents + other_income_cents).
* ``consumption_cents`` = gross outflows (positive number) of ``purchase``,
  ``utilities_payment`` and ``housing_payment`` rows; refunds are not netted
  (``money_map`` consumption_cents; ``transaction_statistics`` with
  consumption_only).
* ``savings_contributions_cents`` = outflows of ``investment_deposit`` and
  ``salary_sweep`` (``money_map`` committed_saving_transfers_cents).
* ``savings_withdrawals_cents`` = inflows of ``investment_withdrawal``.
* ``savings_transfers_cents`` = contributions − withdrawals (net money moved
  to saving).  When every transfer has its usual sign this equals
  −``money_map`` transfer_net_cents.
* ``net_cents`` = income − consumption − savings_transfers: money left on the
  account from the period's activity (positive) or drawn from the balance.
* ``saving_rate_percent`` = savings_transfers ÷ income × 100, rounded half up
  to one decimal, as text; None when income is zero or negative.
"""

import calendar
from decimal import Decimal, ROUND_HALF_UP

from .ledger import account_scope, fact_id, month_bounds, shift_month, transactions


MAX_MONTHS = 36
MAX_YEARS = 5
GRANULARITIES = ('month', 'year')
_CONSUMPTION = ('purchase', 'utilities_payment', 'housing_payment')
_FIELDS = ('income_cents', 'salary_cents', 'other_income_cents', 'consumption_cents',
           'savings_contributions_cents', 'savings_withdrawals_cents', 'savings_transfers_cents', 'net_cents')


def _rate(savings, income):
    if income <= 0:
        return None
    return format((Decimal(savings) * 100 / Decimal(income)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP), 'f')


def _month(value, name):
    if not isinstance(value, str) or len(value) != 7:
        raise ValueError(name + ' must be YYYY-MM')
    try:
        month_bounds(value)
    except ValueError as error:
        raise ValueError(name + ' must be YYYY-MM') from error
    return value


def _range(scope, start_month, end_month, granularity):
    if granularity not in GRANULARITIES:
        raise ValueError('granularity must be month or year')
    low, high = scope['observed_start'][:7], scope['observed_end'][:7]
    if granularity == 'year' and isinstance(start_month, str) and len(start_month) == 4 and start_month.isdigit():
        start_month = max(start_month + '-01', low)
    if granularity == 'year' and isinstance(end_month, str) and len(end_month) == 4 and end_month.isdigit():
        end_month = min(end_month + '-12', high)
    start_month, end_month = _month(start_month, 'start_month'), _month(end_month, 'end_month')
    if start_month > end_month:
        raise ValueError('Reversed period')
    if start_month < low or end_month > high:
        raise ValueError('Period outside observed account history (' + low + ' to ' + high + ')')
    months = []
    month = start_month
    while month <= end_month:
        months.append(month)
        month = shift_month(month, 1)
    if granularity == 'month' and len(months) > MAX_MONTHS:
        raise ValueError('At most 36 months')
    if granularity == 'year' and int(end_month[:4]) - int(start_month[:4]) + 1 > MAX_YEARS:
        raise ValueError('At most 5 years')
    return start_month, end_month, months


def _covered(conn, month):
    """True when the dataset calendar covers every day of the month."""
    low, high = conn.execute('SELECT min(date), max(date) FROM transactions').fetchone()
    first, last = month_bounds(month)
    return bool(low and first >= low and last <= high)


def _sums(rows):
    salary = sum(r['amount_cents'] for r in rows if r['transaction_type'] == 'salary')
    other = sum(r['amount_cents'] for r in rows if r['transaction_type'] == 'other_income')
    consumption = -sum(min(r['amount_cents'], 0) for r in rows if r['transaction_type'] in _CONSUMPTION)
    contributions = -sum(min(r['amount_cents'], 0) for r in rows
                         if r['transaction_type'] in ('investment_deposit', 'salary_sweep'))
    withdrawals = sum(max(r['amount_cents'], 0) for r in rows if r['transaction_type'] == 'investment_withdrawal')
    savings = contributions - withdrawals
    income = salary + other
    return {'income_cents': income, 'salary_cents': salary, 'other_income_cents': other,
            'consumption_cents': consumption, 'savings_contributions_cents': contributions,
            'savings_withdrawals_cents': withdrawals, 'savings_transfers_cents': savings,
            'net_cents': income - consumption - savings}


def _label(period, granularity):
    if granularity == 'year':
        return period
    return calendar.month_abbr[int(period[5:])] + ' ' + period[:4]


def cashflow_series(conn, customer_id, start_month, end_month, granularity='month'):
    """Income, consumption, saving transfers and net per month or calendar year.

    Arguments:
      start_month, end_month: inclusive 'YYYY-MM' inside the customer's observed
        months (else ValueError). With granularity='year' a bare 'YYYY' is also
        accepted and clamped to the observed months (e.g. '2024' → observed
        start month).
      granularity: 'month' (max 36 months) or 'year' (max 5 calendar years).

    Returns a dict:
      granularity, start_month, end_month, period {start, end} (ISO dates),
      definitions: {field: English definition} (see module docstring),
      periods: list (chronological) of {period ('YYYY-MM' or 'YYYY'), label
        ('Mar 2025' or '2025'), start, end (ISO dates of the included part),
        months (number of included months), complete (bool: the whole
        calendar month/year is inside the requested range and covered by the
        observed data), income_cents, salary_cents, other_income_cents,
        consumption_cents (positive), savings_contributions_cents,
        savings_withdrawals_cents, savings_transfers_cents, net_cents,
        saving_rate_percent (one-decimal text or None), transaction_count,
        transaction_refs},
      totals: the same money fields summed over the range plus
        saving_rate_percent, complete_periods, partial_periods,
      chart: {kind: 'cashflow', title, unit: 'cents', labels: [label...],
        complete: [bool...], series: [
          {key: 'income', label: 'Money in', style: 'bar', values: [cents...]},
          {key: 'consumption', label: 'Spending', style: 'bar', values: [...]},
          {key: 'net', label: 'Net', style: 'line', values: [...]}]},
      basis, transaction_refs, fact_id, observed: True.
    """
    scope = account_scope(conn, customer_id)
    start_month, end_month, months = _range(scope, start_month, end_month, granularity)
    start, end = month_bounds(start_month)[0], month_bounds(end_month)[1]
    rows = transactions(conn, customer_id, start, end)
    buckets = {}
    for month in months:
        key = month[:4] if granularity == 'year' else month
        buckets.setdefault(key, []).append(month)
    periods = []
    for key, members in buckets.items():
        selected = [r for r in rows if r['date'][:7] in members]
        sums = _sums(selected)
        if granularity == 'year':
            complete = len(members) == 12 and all(_covered(conn, m) for m in members)
        else:
            complete = _covered(conn, key)
        refs = [r['transaction_ref'] for r in selected]
        periods.append({
            'period': key, 'label': _label(key, granularity),
            'start': month_bounds(members[0])[0], 'end': month_bounds(members[-1])[1],
            'months': len(members), 'complete': complete, **sums,
            'saving_rate_percent': _rate(sums['savings_transfers_cents'], sums['income_cents']),
            'transaction_count': len(selected), 'transaction_refs': refs,
            'fact_id': fact_id('cashflow-period', customer_id, key, members, refs),
        })
    totals = {field: sum(p[field] for p in periods) for field in _FIELDS}
    totals['saving_rate_percent'] = _rate(totals['savings_transfers_cents'], totals['income_cents'])
    totals['complete_periods'] = sum(p['complete'] for p in periods)
    totals['partial_periods'] = sum(not p['complete'] for p in periods)
    refs = [r['transaction_ref'] for r in rows]
    result = {
        **scope,
        'granularity': granularity,
        'start_month': start_month,
        'end_month': end_month,
        'period': {'start': start, 'end': end},
        'definitions': {
            'income_cents': 'Salary plus other income deposits',
            'consumption_cents': 'Gross purchases, utility and housing payments (refunds not netted)',
            'savings_transfers_cents': 'Investment deposits and salary sweeps out, minus investment withdrawals in',
            'net_cents': 'Income minus consumption minus savings transfers',
            'saving_rate_percent': 'Savings transfers divided by income, one decimal',
        },
        'periods': periods,
        'totals': totals,
        'chart': {
            'kind': 'cashflow', 'title': 'Money in vs money out', 'unit': 'cents',
            'labels': [p['label'] for p in periods], 'complete': [p['complete'] for p in periods],
            'series': [
                {'key': 'income', 'label': 'Money in', 'style': 'bar', 'values': [p['income_cents'] for p in periods]},
                {'key': 'consumption', 'label': 'Spending', 'style': 'bar',
                 'values': [p['consumption_cents'] for p in periods]},
                {'key': 'net', 'label': 'Net', 'style': 'line', 'values': [p['net_cents'] for p in periods]},
            ],
        },
        'basis': ('Observed account rows from ' + start + ' to ' + end + ' by ' + granularity +
                  '; income is salary plus other income, spending is consumption only, savings transfers are'
                  ' investment deposits and salary sweeps minus withdrawals. Partial periods are flagged.'),
        'transaction_refs': refs,
        'observed': True,
    }
    result['fact_id'] = fact_id('cashflow', customer_id, start_month, end_month, granularity, refs)
    return result


def _brief(period):
    return {key: period[key] for key in ('period', 'label', 'complete', 'income_cents', 'consumption_cents',
                                         'savings_transfers_cents', 'net_cents', 'saving_rate_percent')}


def cashflow_summary(conn, customer_id, start_month, end_month, granularity='month'):
    """``cashflow_series`` plus precomputed comparisons for the coach.

    Same arguments as ``cashflow_series``. Returns its dict (``periods`` keep
    every field) plus ``comparisons``:
      basis_periods: 'complete' when best/worst use complete periods only,
        'all' when no period is complete;
      best_net_period, worst_net_period: brief period dicts (period, label,
        complete, income/consumption/savings_transfers/net cents,
        saving_rate_percent); ties go to the earlier period;
      first_complete, last_complete: brief dicts or None;
      saving_rate_change: None unless two different complete periods both
        have a saving rate; else {from_period, to_period, from_percent,
        to_percent, change_points (one-decimal text, difference of the two
        rounded rates), direction ('up'|'down'|'same')};
      net_change_cents, income_change_cents, consumption_change_cents:
        last_complete minus first_complete (None without two complete periods);
      average_net_cents_per_complete_period: rounded half up, or None.
    """
    result = cashflow_series(conn, customer_id, start_month, end_month, granularity)
    periods = result['periods']
    complete = [p for p in periods if p['complete']]
    pool = complete or periods
    order = list(range(len(pool)))
    best = pool[max(order, key=lambda i: (pool[i]['net_cents'], -i))]
    worst = pool[min(order, key=lambda i: (pool[i]['net_cents'], i))]
    first = complete[0] if complete else None
    last = complete[-1] if complete else None
    two = len(complete) >= 2
    rate_change = None
    if two and first['saving_rate_percent'] is not None and last['saving_rate_percent'] is not None:
        delta = Decimal(last['saving_rate_percent']) - Decimal(first['saving_rate_percent'])
        rate_change = {
            'from_period': first['period'], 'to_period': last['period'],
            'from_percent': first['saving_rate_percent'], 'to_percent': last['saving_rate_percent'],
            'change_points': format(delta.quantize(Decimal('0.1')), 'f'),
            'direction': 'up' if delta > 0 else ('down' if delta < 0 else 'same'),
        }
    average = None
    if complete:
        average = int((Decimal(sum(p['net_cents'] for p in complete)) / len(complete)).quantize(
            Decimal('1'), rounding=ROUND_HALF_UP))
    result['comparisons'] = {
        'basis_periods': 'complete' if complete else 'all',
        'best_net_period': _brief(best),
        'worst_net_period': _brief(worst),
        'first_complete': _brief(first) if first else None,
        'last_complete': _brief(last) if last else None,
        'saving_rate_change': rate_change,
        'net_change_cents': last['net_cents'] - first['net_cents'] if two else None,
        'income_change_cents': last['income_cents'] - first['income_cents'] if two else None,
        'consumption_change_cents': last['consumption_cents'] - first['consumption_cents'] if two else None,
        'average_net_cents_per_complete_period': average,
    }
    result['fact_id'] = fact_id('cashflow-summary', result['fact_id'])
    return result
