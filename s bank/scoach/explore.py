"""Free, deterministic exploration of one customer's observed ledger.

``explore`` groups exact ledger rows (``ledger.transactions``, so user
correction rules apply) by one dimension and measures one metric.  The model
chooses validated arguments; all arithmetic happens here.
"""

import bisect
import calendar
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from .classification import ROLES
from .ledger import account_scope, fact_id, transactions
from .money import cents_to_euros, rounded
from .statistics import _period


GROUP_BYS = (
    'category', 'basket', 'month', 'weekday', 'week', 'day_of_month', 'hour_band',
    'merchant_id', 'mcc_code', 'transaction_type', 'payday_phase',
)
METRICS = (
    'outflow_total', 'inflow_total', 'count', 'average_outflow', 'largest_outflow', 'share_of_outflow',
)
FILTER_KEYS = {
    'category', 'role', 'merchant_id', 'transaction_type', 'account_id', 'transaction_ref',
    'mcc_code', 'consumption_only',
}
CONSUMPTION_TYPES = ('purchase', 'utilities_payment', 'housing_payment')
MAX_TOP = 31

_TIME_GROUPS = {'month', 'week'}
_ORDERED_GROUPS = {'month', 'week', 'weekday', 'day_of_month', 'hour_band', 'payday_phase'}
_WEEKDAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
_HOUR_BANDS = (
    ('night', 'Night (00–05)'), ('morning', 'Morning (06–11)'),
    ('afternoon', 'Afternoon (12–17)'), ('evening', 'Evening (18–23)'),
)
_PAYDAY_PHASES = (
    ('after_payday', 'First week after payday'), ('mid_cycle', 'Mid-cycle'),
    ('before_payday', 'Last week before payday'),
)
_BASKETS = {
    'fixed_obligation': ('regular', 'Must-pays'),
    'flexible_essential': ('irregular', 'Surprise must-pays'),
    'discretionary': ('everyday', 'Little leaks'),
    'income': (None, 'Income'),
    'saving_or_transfer': (None, 'Saving and transfers'),
    'needs_review': (None, 'Needs review'),
}
_TYPE_LABELS = {
    'purchase': 'Purchases', 'utilities_payment': 'Utility payments', 'housing_payment': 'Housing payments',
    'salary': 'Salary', 'other_income': 'Other income', 'investment_deposit': 'Investment deposits',
    'investment_withdrawal': 'Investment withdrawals', 'salary_sweep': 'Salary sweeps',
}
# Standard ISO 18245 merchant category descriptions for codes in the dataset.
MCC_LABELS = {
    '4111': 'Local commuter transport', '4121': 'Taxi', '4511': 'Airlines', '4722': 'Travel agencies',
    '5200': 'Home supply stores', '5251': 'Hardware stores', '5411': 'Grocery stores and supermarkets',
    '5422': 'Meat and fish shops', '5451': 'Dairy shops', '5499': 'Food stores and convenience shops',
    '5541': 'Service stations', '5542': 'Fuel dispensers', '5651': 'Clothing stores',
    '5691': "Men's and women's clothing", '5712': 'Furniture stores', '5732': 'Electronics stores',
    '5734': 'Computer software stores', '5812': 'Restaurants', '5813': 'Bars and pubs',
    '5814': 'Fast food', '5912': 'Pharmacy', '5941': 'Sporting goods', '5942': 'Book stores',
    '5945': 'Toy and game shops', '5999': 'Other retail', '7011': 'Hotels and lodging',
    '7512': 'Car rental', '7523': 'Parking', '7832': 'Cinemas', '7922': 'Theatre and event tickets',
    '7991': 'Tourist attractions', '7996': 'Amusement parks', '7999': 'Recreation services',
    '8011': 'Doctor', '8021': 'Dentist', '8099': 'Health services',
}
_METRIC_LABELS = {
    'outflow_total': 'Spending', 'inflow_total': 'Money in', 'count': 'Number of payments',
    'average_outflow': 'Average payment', 'largest_outflow': 'Largest payment',
    'share_of_outflow': 'Share of spending',
}
_GROUP_LABELS = {
    'category': 'category', 'basket': 'basket', 'month': 'month', 'weekday': 'weekday', 'week': 'week',
    'day_of_month': 'day of month', 'hour_band': 'time of day', 'merchant_id': 'merchant',
    'mcc_code': 'merchant type', 'transaction_type': 'transaction type', 'payday_phase': 'payday rhythm',
}
_MONTHS = {name: number for number, name in enumerate(calendar.month_abbr) if name}
_MONTHS = {name.upper(): number for name, number in _MONTHS.items()}
_SAS_TIMESTAMP = re.compile(
    r'^\s*(\d{1,2})([A-Za-z]{3})(\d{2}|\d{4})[:\s](\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?\s*$')


def parse_timestamp(value):
    """Parse a source timestamp into a naive ``datetime``, or return None.

    Accepts the SAS ``DATETIME`` text used by the source data
    (``'05OCT24:17:51:20'`` or ``'05OCT2024:17:51:20'``, seconds optional) and
    ISO 8601 (``'2024-10-05T17:51:20'``, ``'2024-10-05 17:51'``, trailing ``Z``
    or offset allowed; the offset is dropped, local wall-clock time is kept).
    Unparseable or impossible values return None rather than raising.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    match = _SAS_TIMESTAMP.match(value)
    if match:
        day, month_name, year, hour, minute, second = match.groups()
        month = _MONTHS.get(month_name.upper())
        year = int(year) + (2000 if len(year) == 2 else 0)
        try:
            return datetime(year, month, int(day), int(hour), int(minute), int(second or 0)) if month else None
        except ValueError:
            return None
    text = value.strip()
    if text.endswith(('Z', 'z')):
        text = text[:-1]
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if len(text) <= 10:
        return None  # date only: no time of day is known
    return parsed.replace(tzinfo=None)


def hour_band(timestamp):
    """Return 'night' (00–05), 'morning' (06–11), 'afternoon' (12–17), 'evening' (18–23) or 'unknown'."""
    parsed = parse_timestamp(timestamp)
    if parsed is None:
        return 'unknown'
    return _HOUR_BANDS[parsed.hour // 6][0]


def payday_phase(day, salary_dates):
    """Classify one ISO date against sorted ISO salary-deposit dates.

    Returns 'after_payday' when the date is 0–6 days after the latest salary
    deposit on or before it (the payday and the six following days), else
    'before_payday' when the next salary deposit is 1–7 days later, else
    'mid_cycle' when both surrounding salaries exist and are at most 62 days
    apart, else 'unknown' (no salary before/after, or a gap over 62 days).
    """
    current = date.fromisoformat(day)
    index = bisect.bisect_right(salary_dates, day)
    previous = date.fromisoformat(salary_dates[index - 1]) if index else None
    following = date.fromisoformat(salary_dates[index]) if index < len(salary_dates) else None
    if previous is not None and (current - previous).days <= 6:
        return 'after_payday'
    if following is not None and (following - current).days <= 7:
        return 'before_payday'
    if previous is not None and following is not None and (following - previous).days <= 62:
        return 'mid_cycle'
    return 'unknown'


def _validated_filters(filters):
    if filters is None:
        return {}
    if not isinstance(filters, dict) or set(filters) - FILTER_KEYS:
        raise ValueError('Unsupported explore filter')
    cleaned = {}
    for key, value in filters.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Explore filter values must be nonempty text')
        cleaned[key] = value
    if 'role' in cleaned and cleaned['role'] not in ROLES:
        raise ValueError('Unknown role')
    if 'mcc_code' in cleaned and not re.fullmatch(r'\d{4}', cleaned['mcc_code']):
        raise ValueError('mcc_code must be four digits')
    if 'consumption_only' in cleaned and cleaned['consumption_only'] != 'true':
        raise ValueError('consumption_only must be true')
    return cleaned


def _percent(part, whole):
    if not whole:
        return None
    return format((Decimal(part) * 100 / Decimal(whole)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP), 'f')


def _month_label(month):
    return calendar.month_name[int(month[5:])] + ' ' + month[:4]


def _ordinal(number):
    suffix = 'th' if 10 <= number % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
    return str(number) + suffix


def _week_start(day):
    value = date.fromisoformat(day)
    return (value - timedelta(days=value.weekday())).isoformat()


def _key(group_by, row, salary_dates):
    if group_by == 'category':
        return row['category']
    if group_by == 'basket':
        return row['role']
    if group_by == 'month':
        return row['date'][:7]
    if group_by == 'weekday':
        return date.fromisoformat(row['date']).isoweekday()
    if group_by == 'week':
        return _week_start(row['date'])
    if group_by == 'day_of_month':
        return int(row['date'][8:10])
    if group_by == 'hour_band':
        return hour_band(row.get('timestamp'))
    if group_by == 'payday_phase':
        return payday_phase(row['date'], salary_dates) if salary_dates else 'unknown'
    return row.get(group_by)  # merchant_id, mcc_code, transaction_type


def _label(group_by, key):
    if key is None:
        return 'Not available'
    if group_by == 'basket':
        return _BASKETS.get(key, (None, key))[1]
    if group_by == 'month':
        return _month_label(key)
    if group_by == 'weekday':
        return _WEEKDAYS[key - 1]
    if group_by == 'week':
        return 'Week of ' + key
    if group_by == 'day_of_month':
        return _ordinal(key) + ' of the month'
    if group_by == 'hour_band':
        return dict(_HOUR_BANDS).get(key, 'Time not recorded')
    if group_by == 'payday_phase':
        return dict(_PAYDAY_PHASES).get(key, 'No salary context')
    if group_by == 'mcc_code':
        return MCC_LABELS.get(key, 'Merchant code ' + key)
    if group_by == 'transaction_type':
        return _TYPE_LABELS.get(key, key.replace('_', ' ').capitalize())
    return str(key)


def _filled_keys(group_by, start, end):
    """Keys shown even when empty, so time charts have no silent gaps."""
    if group_by == 'month':
        keys, month = [], start[:7]
        while month <= end[:7]:
            keys.append(month)
            year, number = int(month[:4]), int(month[5:])
            month = '%04d-%02d' % (year + number // 12, number % 12 + 1)
        return keys
    if group_by == 'week':
        keys, current, last = [], date.fromisoformat(_week_start(start)), date.fromisoformat(end)
        while current <= last:
            keys.append(current.isoformat())
            current += timedelta(days=7)
        return keys
    if group_by == 'weekday':
        return list(range(1, 8))
    if group_by == 'hour_band':
        return [key for key, _ in _HOUR_BANDS]
    if group_by == 'payday_phase':
        return [key for key, _ in _PAYDAY_PHASES]
    return []


def _order(group_by, key):
    if group_by == 'hour_band':
        keys = [k for k, _ in _HOUR_BANDS]
        return keys.index(key) if key in keys else len(keys)
    if group_by == 'payday_phase':
        keys = [k for k, _ in _PAYDAY_PHASES]
        return keys.index(key) if key in keys else len(keys)
    return key


def _largest(rows):
    if not rows:
        return None
    row = sorted(rows, key=lambda item: (item['amount_cents'], item['date'], item['transaction_ref']))[0]
    return {'date': row['date'], 'category': row['category'], 'merchant_id': row['merchant_id'],
            'mcc_code': row['mcc_code'], 'transaction_type': row['transaction_type'],
            'amount_cents': -row['amount_cents'], 'transaction_ref': row['transaction_ref'],
            'fact_id': row['fact_id']}


def _basis(metric, filters, start, end, group_by):
    if metric == 'inflow_total':
        flows = 'Observed incoming payments (amount above zero)'
    elif filters.get('consumption_only') == 'true':
        flows = 'Observed consumption outflows (purchases, utility and housing payments; refunds and transfers excluded)'
    else:
        flows = 'Observed outgoing payments matching the filters'
    narrowed = {k: v for k, v in filters.items() if k not in ('consumption_only', 'account_id')}
    text = flows + ' from ' + start + ' to ' + end
    if narrowed:
        text += ', filtered by ' + ', '.join(k + '=' + v for k, v in sorted(narrowed.items()))
    text += ', grouped by ' + _GROUP_LABELS[group_by] + '; user category corrections applied.'
    if metric == 'count':
        text += ' Values are numbers of payments.'
    elif metric == 'average_outflow':
        text += ' Values are average payment size per group, rounded half up to cents.'
    elif metric == 'largest_outflow':
        text += ' Values are the single largest payment per group.'
    if group_by == 'payday_phase':
        text += (' Payday phases use observed salary deposits: the payday and six days after it, the seven days'
                 ' before the next salary, and the rest of the cycle.')
    return text


def explore(conn, customer_id, start, end, *, group_by, metric='outflow_total', filters=None, top=10):
    """Group one customer's observed transactions and measure one metric.

    Arguments:
      conn, customer_id: database connection and customer in scope.
      start, end: inclusive ISO dates ('YYYY-MM-DD') inside the observed months
        (validated with ``statistics._period``).
      group_by: one of ``GROUP_BYS``:
        category, basket (classification role; labels Must-pays / Surprise
        must-pays / Little leaks), month ('YYYY-MM'), weekday (ISO 1=Monday),
        week (Monday date 'YYYY-MM-DD'), day_of_month (1–31), hour_band
        (night 0–5, morning 6–11, afternoon 12–17, evening 18–23, from the
        source timestamp; 'unknown' if unparseable), merchant_id, mcc_code,
        transaction_type, payday_phase (after_payday = payday + 6 days,
        before_payday = 7 days before the next salary, mid_cycle, unknown).
      metric: one of ``METRICS``:
        outflow_total (gross outflow cents), inflow_total (inflow cents),
        count (number of rows in scope), average_outflow (cents, rounded half
        up), largest_outflow (cents of the single largest payment),
        share_of_outflow (outflow cents, ranked by share).
      filters: optional dict with the ``ledger.transactions`` keys (category,
        role, merchant_id, transaction_type, account_id, transaction_ref,
        mcc_code, consumption_only='true'). For every metric except
        inflow_total, consumption_only='true' is added unless role,
        transaction_type or consumption_only is given (same default as the
        spending tools).
      top: 1–31 rows to return.

    Returns a dict:
      group_by, metric, unit ('cents' or 'count'), filters (as applied),
      period {start, end},
      rows: list of {key, label, value_cents (money metrics; None for an
        empty group) or no value_cents for count, value (formatted '€12.34',
        or the count as text), count (rows in group), outflow_cents (money
        metrics), share_percent (one-decimal string of the group's share of
        the total for the metric; for average/largest the share of outflow
        cents; None when the total is zero), largest (largest_outflow only)}.
        Categorical groupings are sorted by value descending; month and week
        chronologically, weekday Monday–Sunday, day_of_month 1–31, hour_band
        night–evening, payday_phase after–mid–before–unknown.  Month, week,
        weekday, hour_band and payday_phase include empty groups.
      total_count: number of groups before capping; truncated: bool;
        truncation: rule used when truncated (month/week keep the most recent
        groups; others keep the highest values).
      total: {value_cents or count (metric over the whole scope), count,
        outflow_cents, inflow_cents}.
      basis: English sentence describing what was counted.
      chart: {kind: 'line' for month/week else 'bar', title, unit,
        series: [{label, value_cents}] for money metrics or [{label, value}]
        for count}.
      transaction_refs: refs of every row measured; fact_id; observed: True.
    Raises ValueError for an unknown group_by/metric/filter, bad dates or top.
    """
    if group_by not in GROUP_BYS:
        raise ValueError('Unsupported group_by; choose one of: ' + ', '.join(GROUP_BYS))
    if metric not in METRICS:
        raise ValueError('Unsupported metric; choose one of: ' + ', '.join(METRICS))
    if type(top) is not int or not 1 <= top <= MAX_TOP:
        raise ValueError('top must be an integer from 1 to 31')
    scope = account_scope(conn, customer_id)
    _period(scope, start, end)
    applied = _validated_filters(filters)
    if metric != 'inflow_total' and not {'role', 'transaction_type', 'consumption_only'} & set(applied):
        applied['consumption_only'] = 'true'
    rows = transactions(conn, customer_id, start, end, applied)
    measured = [r for r in rows if r['amount_cents'] > 0] if metric == 'inflow_total' else [
        r for r in rows if r['amount_cents'] < 0]
    if metric == 'count':
        measured = rows if applied.get('consumption_only') != 'true' else measured
    salary_dates = []
    if group_by == 'payday_phase':
        salary_dates = sorted({r['date'] for r in transactions(conn, customer_id)
                               if r['transaction_type'] == 'salary' and r['amount_cents'] > 0})

    groups = {key: [] for key in _filled_keys(group_by, start, end)}
    for row in measured:
        groups.setdefault(_key(group_by, row, salary_dates), []).append(row)

    money = metric != 'count'
    outflow_total = -sum(r['amount_cents'] for r in measured if r['amount_cents'] < 0)
    inflow_total = sum(r['amount_cents'] for r in measured if r['amount_cents'] > 0)

    def value(items):
        if metric == 'count':
            return len(items)
        if metric == 'inflow_total':
            return sum(r['amount_cents'] for r in items)
        if metric in ('outflow_total', 'share_of_outflow'):
            return -sum(r['amount_cents'] for r in items)
        if not items:
            return None
        if metric == 'average_outflow':
            return rounded(Decimal(-sum(r['amount_cents'] for r in items)) / len(items))
        return -min(r['amount_cents'] for r in items)  # largest_outflow

    share_base = {'count': len(measured), 'inflow_total': inflow_total}.get(metric, outflow_total)
    result_rows = []
    for key, items in groups.items():
        row_value = value(items)
        share_part = {'count': len(items), 'inflow_total': row_value}.get(
            metric, -sum(r['amount_cents'] for r in items))
        entry = {'key': key, 'label': _label(group_by, key), 'count': len(items),
                 'share_percent': _percent(share_part, share_base)}
        if money:
            entry['value_cents'] = row_value
            entry['value'] = '€' + cents_to_euros(row_value) if row_value is not None else None
            if metric != 'inflow_total':
                entry['outflow_cents'] = -sum(r['amount_cents'] for r in items)
        else:
            entry['value'] = str(row_value)
        if metric == 'largest_outflow':
            entry['largest'] = _largest(items)
        result_rows.append(entry)

    metric_key = 'value_cents' if money else 'count'
    if group_by in _ORDERED_GROUPS:
        result_rows.sort(key=lambda r: (r['key'] is None, _order(group_by, r['key'])))
    else:
        result_rows.sort(key=lambda r: (-(r[metric_key] or 0), r['key'] is None, str(r['key'])))
    total_count = len(result_rows)
    truncation = None
    if total_count > top:
        if group_by in _TIME_GROUPS:
            result_rows = result_rows[-top:]
            truncation = 'Most recent ' + str(top) + ' periods kept'
        elif group_by in _ORDERED_GROUPS:
            kept = {id(r) for r in sorted(result_rows, key=lambda r: (-(r[metric_key] or 0), str(r['key'])))[:top]}
            result_rows = [r for r in result_rows if id(r) in kept]
            truncation = 'Highest ' + str(top) + ' groups kept, shown in natural order'
        else:
            result_rows = result_rows[:top]
            truncation = 'Highest ' + str(top) + ' groups kept'

    total = {'count': len(measured), 'outflow_cents': outflow_total, 'inflow_cents': inflow_total}
    if money:
        total['value_cents'] = value(measured)
        total['value'] = '€' + cents_to_euros(total['value_cents']) if total['value_cents'] is not None else None
    if metric == 'largest_outflow':
        total['largest'] = _largest(measured)
    if metric == 'share_of_outflow':
        total['share_percent'] = '100.0' if outflow_total else None

    title = _METRIC_LABELS[metric] + ' by ' + _GROUP_LABELS[group_by]
    if money:
        series = [{'label': r['label'], 'value_cents': r['value_cents']} for r in result_rows]
    else:
        series = [{'label': r['label'], 'value': r['count']} for r in result_rows]
    refs = [r['transaction_ref'] for r in measured]
    result = {
        **scope,
        'group_by': group_by,
        'metric': metric,
        'unit': 'cents' if money else 'count',
        'filters': applied,
        'period': {'start': start, 'end': end},
        'rows': result_rows,
        'total_count': total_count,
        'truncated': truncation is not None,
        'truncation': truncation,
        'total': total,
        'basis': _basis(metric, applied, start, end, group_by),
        'chart': {'kind': 'line' if group_by in _TIME_GROUPS else 'bar', 'title': title,
                  'unit': 'cents' if money else 'count', 'series': series},
        'transaction_refs': refs,
        'observed': True,
    }
    if group_by == 'payday_phase' and not salary_dates:
        result['limitations'] = ['No salary deposits were observed, so payday phases are unknown']
    result['fact_id'] = fact_id('explore', customer_id, start, end, group_by, metric, applied, refs)
    return result
