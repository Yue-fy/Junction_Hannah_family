"""Numeric provenance check, not a semantic proof that a financial claim is true."""
import re
from decimal import Decimal, DecimalException, ROUND_HALF_UP

_NUMBER = re.compile(r'(?<![\w])[-+]?(?:(?:€|EUR)\s*)?(?:\d{1,3}(?:[ ,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)(?:[eE][+-]?\d+)?[A-Za-z]*(?:\s+(?:thousand|million|billion|tuhatta|tuhat|miljoonaa|miljoona|tusen|miljoner|miljon)\b)?', re.I)
_UNIT = re.compile(r'^\s*(?:€|%|EUR\b|euro\w*|percent\w*|prosent\w*|procent\w*)', re.I)
_MONTH = r'(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|tammik\w*|helmik\w*|maalisk\w*|huhtik\w*|toukok\w*|kesäk\w*|heinäk\w*|elok\w*|syysk\w*|lokak\w*|marrask\w*|jouluk\w*|januari|februari|mars|maj|juni|juli|augusti|oktober)'
_APPROX = re.compile(r'(?:about|around|roughly|almost|nearly|over|under|more than|less than|approximately|~|noin|lähes|melkein|yli|alle|ungefär|nästan|cirka|drygt|knappt|över|under)\s*(?:€|EUR\s*)?$', re.I)
_MAGNITUDES = {'k': 1000, 'thousand': 1000, 'tuhat': 1000, 'tuhatta': 1000, 'tusen': 1000,
               'm': 1000000, 'million': 1000000, 'miljoona': 1000000, 'miljoonaa': 1000000, 'miljon': 1000000, 'miljoner': 1000000,
               'b': 1000000000, 'billion': 1000000000}
_UNTRUSTED_TEXT = {'name', 'label', 'caption', 'title', 'basis', 'description', 'definition', 'error',
                   'proposal', 'params', 'action', 'suggestions', 'formula', 'assumptions', 'limitations',
                   'rounding', 'category', 'mcc_code', 'merchant_id'}


def numeric_tokens(text):
    text = str(text).replace('\u00a0', ' ').replace('\u202f', ' ').replace('−', '-')
    for match in _NUMBER.finditer(text):
        token = re.sub(r'€|EUR', '', match.group(), flags=re.I).replace(' ', '')
        suffix = re.search(r'[A-Za-z]+$', token)
        multiplier = 1
        if suffix:
            multiplier = _MAGNITUDES.get(suffix.group().casefold())
            token = token[:suffix.start()]
        if ',' in token and '.' in token:
            decimal_mark = ',' if token.rfind(',') > token.rfind('.') else '.'
            token = token.replace('.' if decimal_mark == ',' else ',', '').replace(',', '.')
        elif ',' in token:
            parts = token.split(',')
            token = ''.join(parts) if all(len(part) == 3 for part in parts[1:]) else token.replace(',', '.')
        try:
            value = Decimal(token)
            if multiplier is None or not value.is_finite() or not -100 < value.adjusted() < 100:
                value = Decimal('Infinity')
            else:
                value *= multiplier
        except DecimalException:
            value = Decimal('Infinity')
        unit = ('€' in match.group() or 'eur' in match.group().casefold() or bool(_UNIT.match(text[match.end():])) or
                bool(re.search(r'(?:€|\bEUR)\s*$', text[:match.start()], re.I)))
        # Ignore day-of-month only inside a recognizable date, not arbitrary counts.
        is_day = (bool(re.match(r'\.?\s+' + _MONTH + r'\b', text[match.end():], re.I)) or
                  bool(re.search(r'\d{4}-\d{2}-$', text[:match.start()])))
        yield value, unit, is_day


def approximate_tokens(text):
    """Yield (value, approximate) so 'about €1,900' may round a sourced figure."""
    text = str(text).replace('\u00a0', ' ').replace('\u202f', ' ').replace('−', '-')
    for match, item in zip(_NUMBER.finditer(text), numeric_tokens(text)):
        percent = bool(re.match(r'\s*(?:%|percent|prosent|procent)', text[match.end():], re.I))
        # Rounding to tens or hundreds is only plausible for euro amounts, not shares.
        yield item, not percent and bool(_APPROX.search(text[max(0, match.start() - 24):match.start()]))


def allowed_numbers(results=(), message='', history=(), scope=None):
    values = set()

    def visit(value, key=''):
        if key.endswith(('_id', '_ids', '_ref', '_refs')) or key in _UNTRUSTED_TEXT | {'id', 'raw_json', 'row_hash'}:
            return
        if isinstance(value, dict):
            for name, item in value.items():
                visit(item, name)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item, key)
        elif type(value) in (int, float, Decimal) or isinstance(value, str):
            if key.endswith('_cents') and type(value) is int:
                euros = Decimal(value) / 100
                values.update((euros, euros.quantize(Decimal('1'), rounding=ROUND_HALF_UP)))
            elif key.endswith('_basis_points') and type(value) is int:
                values.add(Decimal(value) / 100)
            else:
                for item, _, _ in numeric_tokens(str(value)):
                    if item.is_finite() and abs(item) < Decimal('1e100'):
                        values.add(item)
                        # A sourced percentage or ratio may be quoted to one decimal or a whole number.
                        if item != item.to_integral_value():
                            values.update((item.quantize(Decimal('1'), rounding=ROUND_HALF_UP),
                                           item.quantize(Decimal('.1'), rounding=ROUND_HALF_UP)))

    visit(results)
    visit(scope or {})
    visit(message)
    for turn in history:
        visit(turn['text'])
    return values


def _rounded_match(value, allowed):
    """'About €1,900' may stand for a sourced €1,878.66; never for an unrelated amount."""
    if value <= 0 or value != value.to_integral_value():
        return False
    for known in allowed:
        magnitude = abs(known)
        if magnitude < 20:
            continue
        for step in (Decimal(10), Decimal(50), Decimal(100), Decimal(1000)):
            if step * 5 > magnitude:
                continue
            if (magnitude / step).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * step == value:
                return True
    return False


def unverified_numbers(text, results=(), message='', history=(), scope=None):
    allowed = allowed_numbers(results, message, history, scope)
    violations = []
    for (value, unit, is_day), approximate in approximate_tokens(text):
        if not value.is_finite() or abs(value) >= Decimal('1e100'):
            if 'unsupported numeric notation' not in violations:
                violations.append('unsupported numeric notation')
            continue
        if not unit and value == value.to_integral_value() and (0 <= value <= 12 or 2020 <= value <= 2030 or (is_day and 1 <= value <= 31)):
            continue
        if not any(abs(value - known) <= Decimal('.01') for known in allowed) and not (approximate and _rounded_match(value, allowed)):
            token = str(value)
            if token not in violations:
                violations.append(token)
    return violations
