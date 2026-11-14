"""Integer cents and one shared, explicit rounding convention."""
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from math import ceil


def euros_to_cents(value):
    try:
        amount = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError('Invalid euro amount') from error
    if not amount.is_finite():
        raise ValueError('Amount must be finite')
    return int((amount * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def cents_to_euros(value):
    if not isinstance(value, int):
        raise ValueError('Expected integer cents')
    return format(Decimal(value) / 100, '.2f')


def rounded(value):
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def median_cents(values):
    values = sorted(values)
    if not values:
        raise ValueError('Empty median')
    n = len(values)
    return values[n//2] if n % 2 else rounded(Decimal(values[n//2-1] + values[n//2]) / 2)


def percentile_cents(values, percentile):
    if not values or not 0 <= percentile <= 1:
        raise ValueError('Expected values and percentile in [0, 1]')
    return sorted(values)[max(ceil(len(values) * percentile)-1, 0)]
