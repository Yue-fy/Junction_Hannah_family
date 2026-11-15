"""Open-data benchmarks: compare one account's monthly spending with Finnish households of the same age band.

The snapshot in data/benchmarks/consumption_by_age_2022.json was downloaded from Statistics Finland's
PxWeb API (table StatFin/ktutk/14q4) and is used as-is; no figure here is estimated or invented. Every
comparison carries caveats because a household survey and one bank account measure different things.
"""
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from .ledger import account_scope, month_bounds, shift_month, transactions
from .money import cents_to_euros

SNAPSHOT = Path(__file__).resolve().parent.parent / 'data' / 'benchmarks' / 'consumption_by_age_2022.json'
CONSUMPTION_TYPES = {'purchase', 'utilities_payment', 'housing_payment'}

# Dataset category -> COICOP 2018 groups in the survey. Only categories with a defensible match are listed.
CATEGORY_MAP = {
    'Groceries': (('01',), 'Food and non-alcoholic beverages'),
    'Restaurants': (('1111',), 'Restaurants, cafés and the like'),
    'Lifestyle': (('03',), 'Clothing and footwear (the closest survey group; Lifestyle may include more)'),
    'Health': (('06',), 'Health'),
    # Running costs and transport services; the survey's vehicle purchases are deliberately excluded.
    'Transportation': (('072', '073'), 'Running a vehicle plus passenger transport services'),
    'Entertainment': (('09',), 'Recreation, sport and culture (a broader group)'),
}
CAVEATS = (
    'The survey describes households; this is one person\'s single account, so the per consumption unit figure is the closer match.',
    'The survey year is 2022, older than these transactions, and prices have changed since.',
    'Survey groups and bank categories only roughly match. Treat this as orientation, not a ranking.',
)


def _snapshot():
    if not SNAPSHOT.is_file():
        return None
    return json.loads(SNAPSHOT.read_text(encoding='utf-8'))


def age_band(age):
    """Map an age in years to the survey's reference-person age band, e.g. 30 -> '25-34'."""
    if not isinstance(age, int) or age < 17:
        return None
    for low, high in ((17, 24), (25, 34), (35, 44), (45, 54), (55, 64), (65, 74), (75, 84)):
        if low <= age <= high:
            return f'{low}-{high}'
    return '85-'


def _percent(part, whole):
    if not whole:
        return None
    return format((Decimal(part) * 100 / Decimal(whole)).quantize(Decimal('.1'), rounding=ROUND_HALF_UP), 'f')


def benchmark_categories():
    """Dataset categories that have a survey comparison, with the survey group description."""
    return [{'category': key, 'survey_group': label} for key, (_, label) in CATEGORY_MAP.items()]


def compare_to_peers(conn, customer_id, category, months=12, end_month=None):
    """Average monthly spending in one category vs the 2022 survey for the customer's age band.

    Returns available False with a reason when the snapshot, the mapping or the customer's age is missing.
    Otherwise: customer {monthly_average_cents, months_used, period}, peers {age_band, per_consumption_unit_cents,
    household_cents}, difference_cents and difference_percent against the per consumption unit figure,
    statistical_year, source, caveats (always present) and transaction_refs.
    """
    snapshot = _snapshot()
    if snapshot is None:
        return {'available': False, 'reason': 'No open-data snapshot is installed.', 'caveats': list(CAVEATS)}
    if category not in CATEGORY_MAP:
        return {'available': False, 'reason': 'There is no comparable survey group for ' + str(category) + '.',
                'comparable_categories': list(CATEGORY_MAP), 'caveats': list(CAVEATS)}
    if type(months) is not int or not 1 <= months <= 24:
        raise ValueError('months must be an integer from 1 to 24')
    row = conn.execute('SELECT age FROM customers WHERE customer_id=?', (customer_id,)).fetchone()
    band = age_band(row[0] if row else None)
    if band is None:
        return {'available': False, 'reason': 'The customer\'s age is not available.', 'caveats': list(CAVEATS)}
    scope = account_scope(conn, customer_id)
    last = end_month or scope['observed_end'][:7]
    if month_bounds(last)[1] > scope['observed_end']:
        last = shift_month(last, -1)
    first = shift_month(last, 1 - months)
    if first + '-01' < scope['observed_start']:
        first = scope['observed_start'][:7]
        if first + '-01' != scope['observed_start']:
            first = shift_month(first, 1)
    used = (int(last[:4]) - int(first[:4])) * 12 + int(last[5:]) - int(first[5:]) + 1
    if used < 1:
        return {'available': False, 'reason': 'Not enough complete months of history.', 'caveats': list(CAVEATS)}
    start, end = first + '-01', month_bounds(last)[1]
    rows = [r for r in transactions(conn, customer_id, start, end, {'category': category})
            if r['amount_cents'] < 0 and r['transaction_type'] in CONSUMPTION_TYPES]
    total = -sum(r['amount_cents'] for r in rows)
    monthly = int((Decimal(total) / used).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    codes, label = CATEGORY_MAP[category]
    groups = snapshot['groups']
    per_unit = sum(groups[code]['by_age'][band]['per_consumption_unit_month_eur'] for code in codes) * 100
    household = sum(groups[code]['by_age'][band]['household_month_eur'] for code in codes) * 100
    difference = monthly - per_unit
    return {
        'available': True,
        'category': category,
        'customer': {'monthly_average_cents': monthly, 'monthly_average': '€' + cents_to_euros(monthly),
                     'total_cents': total, 'months_used': used, 'payment_count': len(rows),
                     'period': {'start': start, 'end': end}},
        'peers': {'age_band': band, 'survey_group': label, 'per_consumption_unit_cents': per_unit,
                  'per_consumption_unit': '€' + cents_to_euros(per_unit), 'household_cents': household,
                  'household': '€' + cents_to_euros(household)},
        'difference_cents': difference,
        'difference': ('+' if difference > 0 else '−' if difference < 0 else '') + '€' + cents_to_euros(abs(difference)),
        'difference_percent': _percent(difference, per_unit),
        'direction': 'more' if difference > 0 else 'less' if difference < 0 else 'same',
        'statistical_year': snapshot['statistical_year'],
        'source': {'name': snapshot['source_name'], 'table': snapshot['table_id'], 'url': snapshot['source_url'],
                   'retrieved_at': snapshot['retrieved_at']},
        'caveats': list(CAVEATS),
        'transaction_refs': [r['transaction_ref'] for r in rows],
    }
