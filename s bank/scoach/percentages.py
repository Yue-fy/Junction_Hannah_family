"""Read a complete, unambiguous percentage without matching numeric suffixes."""
import re
from decimal import Decimal


_EN = ('zero one two three four five six seven eight nine ten eleven twelve '
       'thirteen fourteen fifteen sixteen seventeen eighteen nineteen').split()
_FI = ('nolla yksi kaksi kolme neljä viisi kuusi seitsemän kahdeksan yhdeksän').split()
_SV = ('noll ett två tre fyra fem sex sju åtta nio').split()
_WORDS = {word: value for value, word in enumerate(_EN)}
_WORDS.update({word: value for words in (_FI, _SV) for value, word in enumerate(words)})
_WORDS['en'] = 1
for value, word in enumerate(_FI[1:], 1):
    _WORDS[word + 'toista'] = value + 10
_WORDS['kymmenen'] = 10
_WORDS.update(dict(zip('tio elva tolv tretton fjorton femton sexton sjutton arton nitton'.split(), range(10, 20))))
for value, en, sv in zip(range(20, 100, 10),
                         'twenty thirty forty fifty sixty seventy eighty ninety'.split(),
                         'tjugo trettio fyrtio femtio sextio sjuttio åttio nittio'.split()):
    fi = _FI[value // 10] + 'kymmentä'
    for word in (en, fi, sv):
        _WORDS[word] = value
    for unit in range(1, 10):
        _WORDS[en + ' ' + _EN[unit]] = value + unit
        _WORDS[fi + _FI[unit]] = value + unit
        _WORDS[sv + _SV[unit]] = value + unit
_WORDS.update({'one hundred': 100, 'hundred': 100, 'sata': 100, 'hundra': 100, 'etthundra': 100})
_DIGITS = {word: value for words in (_EN[:10], _FI, _SV) for value, word in enumerate(words)}
_DECIMAL_WORDS = {'point', 'pilkku', 'komma'}
# Collect the entire number phrase, including invalid scales/ranges, so that
# "one thousand twenty" cannot be silently truncated to "twenty".
_NUMBER_TOKENS = {token for phrase in _WORDS for token in phrase.split()} | _DECIMAL_WORDS | {
    'and', 'or', 'to', 'minus', 'miinus', 'plus', 'thousand', 'million', 'billion',
}
_MARKER = re.compile(r'[%％]|(?<!\w)(?:per\s+cent|percent(?:age)?|prosent\w*|procent\w*)(?!\w)')
_NUMERIC = re.compile(r'(?<![\w.,+\-–—−])([+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+))\s*$')


def parse_percentage(text):
    """Return an exact int/decimal string, or reject an unresolved expression."""
    text = text.casefold()
    markers = list(_MARKER.finditer(text))
    if len(markers) != 1 or re.search(r'percentage\s+points?|prosenttiyksikk|procentenhet', text):
        raise ValueError('Choose one percentage, not a range or percentage points')
    left = text[:markers[0].start()].rstrip()
    numeric = _NUMERIC.search(left)
    if numeric:
        prefix = left[:numeric.start()].rstrip()
        prefix_words = re.findall(r'\w+', prefix)
        if (prefix_words and prefix_words[-1] in _NUMBER_TOKENS) or re.search(r'[\d\-–—−]\s*$', prefix):
            raise ValueError('Ambiguous percentage')
        value = Decimal(numeric.group(1).replace(',', '.'))
    else:
        if re.search(r'(?<!\w)[\-−]\s*[^\W\d_]', left):
            raise ValueError('Negative percentage')
        tokens = re.findall(r'\w+', left.replace('-', ' '))
        phrase = []
        for token in reversed(tokens):
            if token not in _NUMBER_TOKENS:
                break
            phrase.insert(0, token)
        separators = [i for i, token in enumerate(phrase) if token in _DECIMAL_WORDS]
        if len(separators) == 1:
            index = separators[0]
            integer = _WORDS.get(' '.join(phrase[:index]))
            fraction = phrase[index + 1:]
            if integer is None or not fraction or any(token not in _DIGITS for token in fraction):
                raise ValueError('Unrecognized decimal percentage')
            value = Decimal(str(integer) + '.' + ''.join(str(_DIGITS[token]) for token in fraction))
        elif not separators and ' '.join(phrase) in _WORDS:
            value = Decimal(_WORDS[' '.join(phrase)])
        else:
            raise ValueError('Unrecognized percentage')
    if not value.is_finite() or not 0 <= value <= 100:
        raise ValueError('Percentage must be between zero and one hundred')
    return int(value) if value == value.to_integral_value() else format(value.normalize(), 'f')
