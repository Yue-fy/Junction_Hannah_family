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


# ---------------------------------------------------------------------------
# Customer-facing number formats (EN '€1,138.27' / '9.6%'; FI and SV
# '1 138,27 €' / '9,6 %'). Use these for every server-side sentence.
FORMAT_LOCALES = ('en', 'fi', 'sv')


def format_euro(cents, locale='en', decimals=2):
    """Integer cents as a localized euro string; decimals 2 (default) or 0 (whole euros, half-up)."""
    if type(cents) is not int:
        raise ValueError('Expected integer cents')
    locale = locale if locale in FORMAT_LOCALES else 'en'
    sign = '-' if cents < 0 else ''
    if decimals == 0:
        whole, part = rounded(Decimal(abs(cents)) / 100), None
    else:
        whole, part = divmod(abs(cents), 100)
    if locale == 'en':
        return sign + '€' + format(whole, ',') + ('' if part is None else '.' + format(part, '02d'))
    return sign + format(whole, ',').replace(',', ' ') + ('' if part is None else ',' + format(part, '02d')) + ' €'


def format_percent(value, locale='en', decimals=1):
    """A percentage (number or decimal string) as '9.6%' (en) or '9,6 %' (fi/sv).

    Never uses scientific notation: Decimal('1E+1') is shown as '10' (decimals=0)
    or '10.0' (decimals=1). Trailing zeros are kept to the requested decimals.
    """
    locale = locale if locale in FORMAT_LOCALES else 'en'
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError('Percentage must be finite')
    quantum = Decimal(1).scaleb(-decimals) if decimals else Decimal(1)
    text = format(number.quantize(quantum, rounding=ROUND_HALF_UP), 'f')
    if locale == 'en':
        return text + '%'
    return text.replace('.', ',') + ' %'
