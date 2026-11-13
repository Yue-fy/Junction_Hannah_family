"""Scoring exactly as Stoa describes it.

- count: exact match after rounding the prediction to the nearest int.
- area / length / volume: |pred - gold| <= 2% of |gold|, after converting the predicted unit to the gold unit.
- text / other: not scored for accuracy (None). A rough fuzzy match is reported separately as `text_fuzzy`.
- abstention (value None) or an unparseable value: wrong.
"""

from __future__ import annotations

import math
import re
import unicodedata

REL_TOL = 0.02

# factor to convert 1 <unit> into the base SI unit of its dimension
_UNITS: dict[str, tuple[str, float]] = {}
for names, dim, f in [
    (("m", "meter", "meters", "metre", "metres"), "L", 1.0),
    (("mm", "millimeter", "millimeters", "millimetre", "millimetres"), "L", 1e-3),
    (("cm", "centimeter", "centimeters", "centimetre", "centimetres"), "L", 1e-2),
    (("ft", "feet", "foot", "'"), "L", 0.3048),
    (("in", "inch", "inches", '"'), "L", 0.0254),
    (("m2", "m^2", "m²", "sqm", "sq m", "square meter", "square meters", "square metre", "square metres"), "A", 1.0),
    (("mm2", "mm^2", "mm²"), "A", 1e-6),
    (("cm2", "cm^2", "cm²"), "A", 1e-4),
    (("ft2", "ft^2", "ft²", "sf", "sq ft", "sqft", "square feet", "square foot"), "A", 0.09290304),
    (("m3", "m^3", "m³", "cubic meter", "cubic meters", "cubic metre", "cubic metres"), "V", 1.0),
    (("mm3", "mm^3", "mm³"), "V", 1e-9),
    (("ft3", "ft^3", "ft³", "cf", "cu ft", "cubic feet", "cubic foot"), "V", 0.028316846592),
    (("l", "liter", "liters", "litre", "litres"), "V", 1e-3),
    (("count", "pcs", "pc", "items", "#"), "N", 1.0),
]:
    for n in names:
        _UNITS[n] = (dim, f)


def norm_unit(u: str | None) -> str | None:
    if u is None:
        return None
    u = unicodedata.normalize("NFKC", str(u)).strip().lower().replace("**", "^")
    u = u.replace("²", "2").replace("³", "3")
    u = re.sub(r"\s+", " ", u)
    return u or None


def convert(value: float, from_unit: str | None, to_unit: str | None) -> float | None:
    """Convert value between units of the same dimension. Unknown/None units are assumed equal.
    Returns None when dimensions differ (e.g. m vs m2)."""
    fu, tu = norm_unit(from_unit), norm_unit(to_unit)
    if fu is None or tu is None or fu == tu:
        return value
    a, b = _UNITS.get(fu), _UNITS.get(tu)
    if a is None or b is None:
        return value  # unknown unit string: trust the number
    if a[0] != b[0]:
        return None
    return value * a[1] / b[1]


_NUM_RE = re.compile(r"[-+]?\d{1,3}(?:[ ,  ]\d{3})+(?:\.\d+)?|[-+]?\d+(?:[.,]\d+)?")


def parse_number(v) -> float | None:
    """Best-effort number from a solver value: 12, 12.5, '12,5 m²', '1 234.5', 'about 7'."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return None if (isinstance(v, float) and not math.isfinite(v)) else float(v)
    s = unicodedata.normalize("NFKC", str(v))
    m = _NUM_RE.search(s)
    if not m:
        return None
    t = m.group(0)
    if re.fullmatch(r"[-+]?\d{1,3}(?:[ ,  ]\d{3})+(?:\.\d+)?", t):
        t = re.sub(r"[ ,  ]", "", t)  # thousands separators
    else:
        t = t.replace(",", ".")  # decimal comma
    try:
        return float(t)
    except ValueError:
        return None


def _norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s)).lower()
    return re.sub(r"[^\w.]+", " ", s).strip()


def text_fuzzy(pred, gold) -> bool:
    """Rough free-text match, reported separately (never part of accuracy)."""
    if pred is None or gold is None:
        return False
    p, g = _norm_text(pred), _norm_text(gold)
    if not p or not g:
        return False
    if p == g or (len(g) >= 2 and f" {g} " in f" {p} "):
        return True
    try:
        from rapidfuzz import fuzz

        # token_SORT, not token_set: token_set gives 100 whenever one side's tokens are a subset ("1" vs
        # "1 water closet, 1 lavatory")
        return fuzz.token_sort_ratio(p, g) >= 85
    except ImportError:  # pragma: no cover
        return False


def score(qtype: str, gold, gold_unit: str | None, pred_value, pred_unit: str | None) -> bool | None:
    """True/False for scored types; None for text/other (not scored)."""
    if qtype in ("text", "other"):
        return None
    x = parse_number(pred_value)
    if x is None:
        return False
    g = parse_number(gold)
    if g is None:
        return False
    if qtype == "count":
        if pred_unit is not None and norm_unit(pred_unit) not in (None, "count") and norm_unit(pred_unit) in _UNITS:
            if _UNITS[norm_unit(pred_unit)][0] != "N":
                return False
        return int(round(x)) == int(round(g))
    y = convert(x, pred_unit, gold_unit)
    if y is None:
        return False
    if g == 0:
        return abs(y) < 1e-9
    return abs(y - g) <= REL_TOL * abs(g) + 1e-12
