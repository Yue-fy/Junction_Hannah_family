"""Outer arithmetic over atomic IFC quantities, for question shapes no dataset template uses (W5's and W1's own
probes, cycle 4): a rate or multiplier given in the question ("each door costs 450 EUR", "35 EUR per m²",
"every window needs 2 curtains"), adding/removing N ("if 5 doors were removed"), ratios ("m² of floor per door",
"ratio of doors to windows"), numeric yes/no ("Are there more than 40 doors on X?"), and the numbers in a question
that no rule used (`leftover_numbers`, a guard: a number the answer ignores means the answer is not what was asked).

Only detection lives here (pure text -> `Outer`); `IfcSolver._outer` computes the atomic parts with the normal
rules and does the arithmetic in code."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from stoa.solvers.ifc.parse import _QUOTED, _kind_hits, fold

NUM = r"(\d+(?:[.,]\d+)?)"
_CUR = (r"(eur(?:os?|oa|on|ot|oja)?\b|€|usd\b|us ?dollars?|dollars?|\$|gbp\b|pounds?\b|£|chf\b|swiss francs?|francs?\b|sek\b|nok\b|"
        r"dkk\b|kronor|kroner|kr\b|pln\b|zloty|zl\b|ron\b|lei\b)")
_CUR_CODE = [("eur", "EUR"), ("€", "EUR"), ("usd", "USD"), ("dollar", "USD"), ("$", "USD"), ("gbp", "GBP"),
             ("pound", "GBP"), ("£", "GBP"), ("chf", "CHF"), ("franc", "CHF"), ("sek", "SEK"), ("kronor", "SEK"),
             ("nok", "NOK"), ("kroner", "NOK"), ("dkk", "DKK"), ("kr", "SEK"), ("pln", "PLN"), ("zl", "PLN"),
             ("ron", "RON"), ("lei", "RON")]
_AREA_U = r"(square met(?:er|re)s?|sq\.? ?m\b|m2\b|square f(?:ee|oo)t|sq\.? ?ft\b|ft2\b)"
_VOL_U = r"(cubic met(?:er|re)s?|m3\b|cubic f(?:ee|oo)t|ft3\b)"
_LEN_U = r"((?:running |linear |lineal )?met(?:er|re)s?\b|lm\b|m\b|feet\b|foot\b|ft\b)"
_EACH = r"(each|apiece|a piece|per piece|per unit|per item|per element|a unit)"
_STOREYISH = re.compile(r"^(floor|level|storey|story|geschoss|etage|verdieping|korrus|niveau|planta)s?\b")
_REMOVE = r"(remov\w*|demolish\w*|tak\w* out|delet\w*|brick\w* up|clos\w*|block\w*|fill\w* in|eliminat\w*|replac\w*)"
_ADD = r"(add\w*|install\w*|buil[dt]\w*|insert\w*|put in|creat\w*)"
_AUX = re.compile(r"^\s*(is|are|does|do|has|have|was|were|will|would|can|could|ist|sind|gibt es|hat|haben|heeft|hebben|"
                  r"zijn|is er|zijn er|y a-t-il|est-ce|hay|tiene|tienen|es|son|ha|hanno|c'e|ci sono|onko|ovatko|har|"
                  r"finns|er|czy|kas|on)\b")
_CMP = re.compile(r"\b(more than|greater than|larger than|bigger than|higher than|longer than|over|above|exceed\w*|"
                  r"at least|no less than|not less than|less than|fewer than|smaller than|lower than|shorter than|"
                  r"under|below|at most|no more than|not more than|exactly|equal to|mehr als|weniger als|groesser als|"
                  r"grosser als|kleiner als|mindestens|hochstens|hoechstens|genau|meer dan|minder dan|groter dan|"
                  r"kleiner dan|minstens|hoogstens|precies|mas de|menos de|plus de|moins de|piu di|meno di)\s+"
                  + NUM)
_LOWER = ("less", "fewer", "smaller", "lower", "shorter", "under", "below", "at most", "no more", "not more",
          "weniger", "kleiner", "hochstens", "hoechstens", "minder", "kleiner", "hoogstens", "menos", "moins", "meno")
_TOPK = re.compile(r"\b(top|largest|biggest|widest|tallest|highest|thickest|smallest|narrowest|thinnest|lowest|first)"
                   r"\s+\d+\b|\b\d+\s+(largest|biggest|widest|tallest|highest|thickest|smallest|narrowest|thinnest|"
                   r"lowest)\b")
_STOREY_NUM = re.compile(r"\b(level|floor|storey|story|etage|verdieping|geschoss|niveau|planta|korrus)\s*-?\d+\b|"
                         r"-?\b\d+(st|nd|rd|th|\.)?\s*(floor|level|storey|story|etage|verdieping|og|ug|eg|korrus)\b|"
                         r"\b\d+\s*\.?\s*(og|ug|obergeschoss|untergeschoss)\b")
_ROOM_REF = re.compile(r"\b(room|space|office|kitchen|bedroom|bathroom|apartment|flat|unit|zone|raum|zimmer|ruimte|"
                       r"lokaal|local|sala|stanza|piece|huone|rum|pomieszczenie|no\.?|nr\.?|number|#)\s*\d[\w.\-/]*")
_UNIT_DIGIT = re.compile(r"(m|ft|sq ?m|sq ?ft|cm|mm|km)[23]\b|\^[23]")


def text_of(question: str) -> str:
    """The question as the parser sees it: quoted names blanked (their digits are names, not numbers), folded,
    digit grouping removed ('1,200 euros' -> '1200 euros', see `ungroup`)."""
    return ungroup(" " + fold(_QUOTED.sub(" ", question)) + " ")


# digit grouping: '1,200' / '1.200' / "1'200" / '1 200' (+ an optional decimal part with the other separator:
# '1,250.50', '1.250,50'). Q's bug 17 (05:08): '1,200 euros' was read as 1.2 -> 55.2 EUR at 0.92 (gold 55,200).
_GROUPED = re.compile(r"(?<![\w.,'’])(\d{1,3})((?P<sep>[,.'’ ])\d{3}(?:(?P=sep)\d{3})*)(?:(?P<dsep>[.,])(?P<dec>\d{1,3}))?"
                      r"(?![\d]|[.,]\d)")


def ungroup(t: str) -> str:
    """Remove digit-group separators from numbers in folded text; the decimal separator becomes '.'.
    A separator followed by exactly three digits is a thousands separator when: it is an apostrophe or space (never
    decimal; a space only next to a currency, '1 200 euroa'), or the number has two or more groups ('1.200.000'), or
    a decimal part follows with the other separator ('1,250.50'), or it is a comma ('1,200': English grouping; three
    decimals after a comma are rare in questions), or it is a dot next to a currency ('1.200 €' German). A dot with
    three digits and no currency stays a decimal ('1.200 m' = 1.2 m in English)."""
    def rep(m: re.Match) -> str:
        sep, groups, dsep = m.group("sep"), m.group(2), m.group("dsep")
        if dsep is not None and dsep == sep:
            return m.group(0)
        near = t[max(0, m.start() - 6):m.end() + 10]
        money = re.search(_CUR, near) is not None
        multi = groups.count(sep) >= 2
        if sep == " " and not money:
            return m.group(0)
        if sep == "." and not (money or multi or dsep == ","):
            return m.group(0)
        digits = m.group(1) + groups.replace(sep, "")
        return digits + ("." + m.group("dec") if dsep else "")
    return _GROUPED.sub(rep, t)


def _cur(name: str) -> str:
    return "(?P<" + name + ">" + _CUR[1:]


def currency(t: str) -> str | None:
    m = re.search(_CUR, t)
    if not m:
        return None
    w = m.group(1)
    return next((code for k, code in _CUR_CODE if w.startswith(k) or w == k), "EUR")


def _num(s: str) -> float:
    return float(s.replace(",", "."))


@dataclass
class Outer:
    op: str  # mul | add | sub | div | cmp
    n: float | None = None  # factor / addend / threshold
    unit: str | None = None  # unit of the result (currency code, "count", ...)
    basis: str | None = None  # metric the factor applies to: count | area | volume | length
    basis_kind: str | None = None  # element kind a per-element factor applies to
    basis_unit: str | None = None  # m2 | ft2 | m3 | ft3 | m | ft (a rate per unit of measure)
    kinds: tuple[str | None, str | None] = (None, None)  # ratio: numerator / denominator kinds
    num_text: str = ""  # ratio: the question with the 'per <kind>' clause removed (numerator)
    cmp: str | None = None  # gt | ge | lt | le | eq
    spans: list[tuple[int, int]] = field(default_factory=list)  # consumed character spans of text_of(question)
    why: str = ""
    rate: float | None = None  # "15 m of wall per day": n = 1/15, rate = 15, per = 'day'
    per: str | None = None


# a unit word after a per-element factor: "takes 1.5 hours", "needs 4 kg", "uses 2 litres"
_UNIT_WORDS = [(r"hours?|hrs?|h|stunden?|uur|heures?|ore|tuntia?|timmar|godzin\w*", "h"),
               (r"minutes?|mins?|minuten?|minuti|minuuttia?", "min"), (r"seconds?|secs?|s|sekunden?", "s"),
               (r"days?|tage?n?|dagen?|jours?|giorni|paivaa?", "days"), (r"weeks?|wochen?|weken", "weeks"),
               (r"kg|kilos?|kilograms?|kilogrammes?", "kg"), (r"litres?|liters?|l", "l"),
               (r"workers?|people|persons?", "persons")]
_TIME_PER = r"(?P<per>hour|hr|h|day|working day|workday|shift|week|month|minute|min|stunde|tag|uur|dag|heure|jour)s?\b"


def unit_word(w: str | None) -> str | None:
    if not w:
        return None
    return next((u for rx, u in _UNIT_WORDS if re.fullmatch(rx, w)), None)


def _basis_of(s: str) -> tuple[str | None, str | None, str | None]:
    """'square metre of wall' -> ('area', None, 'm2'); 'door' -> ('count', 'door', None); 'floor' -> (None,...)"""
    s = s.strip()
    if re.match(_EACH, s) or re.match(r"(piece|unit|item|element)\b", s):
        return "count", None, None
    for rx, metric in ((_AREA_U, "area"), (_VOL_U, "volume"), (_LEN_U, "length")):
        m = re.match(rx, s)
        if m:
            w = m.group(1)
            u = {"area": "ft2" if re.search(r"f(ee|oo)t|ft", w) else "m2",
                 "volume": "ft3" if re.search(r"f(ee|oo)t|ft", w) else "m3",
                 "length": "ft" if re.search(r"f(ee|oo)t|ft", w) else "m"}[metric]
            return metric, None, u
    if _STOREYISH.match(s):
        return None, None, None
    hits = [h for h in _kind_hits(s[:30]) if h[0] <= 1 and h[2] != "storey"]
    if hits:
        return "count", hits[0][2], None
    return None, None, None


def detect(question: str) -> Outer | None:
    """The outer operation of a question, or None. Checked in order: rate/multiplier, add/remove, ratio, yes/no."""
    t = text_of(question)
    cur = currency(t)
    # 0. a work rate: "a crew builds 15 metres of wall per day", "paints 20 m² of wall an hour" -> quantity / rate
    #    (W4 05:02: read as 'add 15' -> 19 at 0.92)
    m = re.search(r"(?P<n>\d+(?:[.,]\d+)?)\s*(?P<u>" + _AREA_U[1:-1] + "|" + _VOL_U[1:-1] + "|" + _LEN_U[1:-1] +
                  r")\s*(?:of\s+(?P<kw>[a-z-]+(?:\s+[a-z-]+)?)\s+)?(?:per|a|an|each|every|/|in an?|in one)\s*"
                  + _TIME_PER, t)
    if m and _num(m.group("n")) > 0:
        metric, _k, bu = _basis_of(m.group("u"))
        kind = None
        if m.group("kw"):
            hits = [h for h in _kind_hits(m.group("kw")) if h[2] != "storey"]
            kind = hits[0][2] if hits else None
        if metric in ("area", "volume", "length"):
            per = m.group("per")
            per = {"hr": "hour", "h": "hour", "min": "minute", "working day": "day", "workday": "day", "stunde": "hour",
                   "tag": "day", "uur": "hour", "dag": "day", "heure": "hour", "jour": "day"}.get(per, per)
            r = _num(m.group("n"))
            return Outer("mul", 1.0 / r, per + "s", metric, kind, bu, spans=[m.span()], rate=r, per=per,
                         why=f"rate {m.group('n')} {bu} per {per}")
    # 1. a factor per something: "450 euros per door", "35 EUR per square metre", "2 curtains for every window"
    for m in re.finditer(r"(?:" + _cur("c1") + r"\s*)?(?P<n>\d+(?:[.,]\d+)?)\s*(?:" + _cur("c2") + r")?(?:\s+(?P<noun>[a-z]+))?\s*"
                         r"(?:per|/|for each|for every|each|every|pro|je|par|por)\s+(?P<basis>[^,;?]{1,40})", t):
        metric, kind, bu = _basis_of(m.group("basis"))
        if metric is None:
            continue
        noun = m.group("noun") or ""
        if metric == "count" and noun and _kind_hits(noun) and kind and _kind_hits(noun)[0][2] == kind:
            continue  # "3 doors per door"? never; guards odd overlaps
        if metric == "count" and noun and any(h[2] for h in _kind_hits(noun)) and not cur:
            continue  # "46 doors per storey"-like counts are not factors
        unit = cur if (m.group("c1") or m.group("c2") or cur) else ("count" if noun else None)
        return Outer("mul", _num(m.group("n")), unit, metric, kind, bu, spans=[m.span()],
                     why=f"factor {m.group('n')} {unit or ''} per {m.group('basis').strip()[:25]}")
    # other languages, verb anywhere: "wenn jede Tür 450 Euro kostet", "als een raam 800 euro kost", "si chaque
    # porte coûte 450 €" -> a currency amount next to an each/one word + a kind word
    m = re.search(r"\b(?:jede[rsnm]?|ein(?:e[rsnm]?)?|elke?|ieder(?:e)?|een|chaque|une?|cada|una?|ogni|jokainen|"
                  r"varje|hver(?:t)?|iga|kazd[aey]|fiecare)\s+(?P<kw>[a-z-]+)\b[^.?;]{0,30}?(?:" + _cur("c1") +
                  r"\s*)?(?P<n>\d+(?:[.,]\d+)?)\s*(?:" + _cur("c2") + r")?", t)
    if m and (m.group("c1") or m.group("c2")):
        hits = [h for h in _kind_hits(m.group("kw")) if h[2] != "storey"]
        if hits:
            return Outer("mul", _num(m.group("n")), cur, "count", hits[0][2], spans=[m.span()],
                         why=f"factor {m.group('n')} {cur} per {hits[0][2]}")
    # "each door costs 450 euros", "every window needs 2 curtains"
    m = re.search(r"\b(?:each|every|per|one|a single|any|an?)\s+(?P<kw>[a-z-]+(?:\s+[a-z-]+)?)\s+(?:costs?|is priced at|"
                  r"is worth|needs?|requires?|uses?|takes?|gets?|has|will (?:need|cost|require|get)|would (?:need|cost|"
                  r"require|get)|cost)\s+(?:about |approximately |roughly |around )?(?:" + _cur("c1") + r"\s*)?(?P<n>\d+(?:[.,]\d+)?)"
                  r"\s*(?:" + _cur("c2") + r")?(?:\s*(?P<noun>[a-z]+))?", t)
    if m:
        hits = [h for h in _kind_hits(m.group("kw")) if h[2] != "storey"]
        if hits:
            uw = unit_word(m.group("noun"))
            unit = cur if (m.group("c1") or m.group("c2") or cur) else (uw or "count")
            return Outer("mul", _num(m.group("n")), unit, "count", hits[0][2], spans=[m.span()],
                         why=f"factor {m.group('n')} {unit} per {hits[0][2]}")
    # verb last (German order, kept by some translations): "if each door 450 euros costs", "a window 1200 € costs"
    m = re.search(r"\b(?:each|every|one|a single|any|an?)\s+(?P<kw>[a-z-]+)\s+(?:" + _cur("c1") + r"\s*)?"
                  r"(?P<n>\d+(?:[.,]\d+)?)\s*(?:" + _cur("c2") + r")?(?:\s*(?P<noun>[a-z]+))?\s+(?:costs?|takes?|needs?|"
                  r"requires?)\b", t)
    if m:
        hits = [h for h in _kind_hits(m.group("kw")) if h[2] != "storey"]
        if hits:
            uw = unit_word(m.group("noun"))
            unit = cur if (m.group("c1") or m.group("c2") or cur) else (uw or "count")
            return Outer("mul", _num(m.group("n")), unit, "count", hits[0][2], spans=[m.span()],
                         why=f"factor {m.group('n')} {unit} per {hits[0][2]}")
    # "doors cost 450 euros each", "at €450 apiece"
    m = re.search(r"(?:" + _cur("c1") + r"\s*)?(?P<n>\d+(?:[.,]\d+)?)\s*(?:" + _cur("c2") + r")?\s*" + _EACH + r"\b", t)
    if m and (m.group("c1") or m.group("c2") or cur):
        return Outer("mul", _num(m.group("n")), cur or "EUR", "count", None, spans=[m.span()],
                     why=f"price {m.group('n')} {cur} each")
    # 2. add / remove N: "if 5 (doors) were removed", "after adding 3 windows", "if we demolish 2 walls"
    m = (re.search(r"\b(?:if|when|after|once|assuming|suppose|supposing)\b[^.?;]{0,30}?\b(?P<n>\d+)\b[^.?;\d]{0,30}?\b(?:"
                   r"(?P<rm>" + _REMOVE + r")|(?P<ad>" + _ADD + r"))", t)
         or re.search(r"\b(?:if|when|after|once|assuming|suppose|supposing)\b[^.?;\d]{0,20}?\b(?:(?P<rm>" + _REMOVE +
                      r")|(?P<ad>" + _ADD + r"))\s+(?:another\s+|an? additional\s+|a further\s+)?(?P<n>\d+)\b", t))
    if m:
        op = "sub" if m.group("rm") else "add"
        return Outer(op, float(m.group("n")), None, spans=[m.span()], why=f"{op} {m.group('n')}")
    # "Is the building taller than 15 m?"
    m = re.search(r"\b(building|house)\b.{0,25}?\b(taller|higher)\s+than\s+(?P<n>\d+(?:[.,]\d+)?)", t)
    if m:
        return Outer("height", _num(m.group("n")), "m", cmp="gt", spans=[m.span()], why=f"building height > {m.group('n')}?")
    # building height / perimeter / footprint: geometry of the whole building, no element kind needed
    m = re.search(r"\bhow (tall|high) is the (building|house)\b|\bheight of the (building|house)\b|\bbuilding'?s? "
                  r"height\b|\b(total|overall) height\b|\bgebaudehohe\b|\bhohe des gebaudes\b|\bhoogte van het gebouw\b|"
                  r"\bhauteur du batiment\b|\baltura del edificio\b|\brakennuksen korkeus\b", t)
    if m:
        return Outer("height", None, "m", spans=[m.span()], why="building height")
    m = re.search(r"\b(perimeter|outline length|umfang|omtrek|perimetre|perimetro|piiri|ymparys)\b", t)
    if m:
        return Outer("perimeter", None, "m", spans=[m.span()], why="perimeter of the outline")
    # window-to-wall ratio (a standard facade metric): window opening area / external wall area
    m = re.search(r"window[- ]?to[- ]?wall|\bwwr\b|window[- ]wall[- ]ratio|fensterflachenanteil|glazing ratio|"
                  r"raam[- ]?muur[- ]?verhouding", t)
    if m:
        return Outer("wwr", None, "%", spans=[m.span()], why="window-to-wall ratio")
    # "if the walls were 10% thicker", "a 15 % increase"
    m = re.search(r"(?P<n>\d+(?:[.,]\d+)?)\s*(?:%|percent|per ?cent|prozent|procent)\s*(?P<w>more|larger|bigger|thicker|"
                  r"higher|longer|wider|increase\w*|extra|less|smaller|thinner|lower|shorter|narrower|fewer|"
                  r"decrease\w*|reduc\w*)", t) or re.search(
                  r"\b(?P<w>increase\w*|grow\w*|rais\w*|decrease\w*|reduc\w*|cut\w*|shrink\w*)\b[^.?;]{0,30}?\bby\s+"
                  r"(?P<n>\d+(?:[.,]\d+)?)\s*(?:%|percent|per ?cent)", t)
    if m:
        down = bool(re.match(r"less|smaller|thinner|lower|shorter|narrower|fewer|decrease|reduc|cut|shrink", m.group("w")))
        f = 1 + (-1 if down else 1) * _num(m.group("n")) / 100.0
        return Outer("mul", f, None, None, spans=[m.span()], why=f"{'-' if down else '+'}{m.group('n')}% (x {f:g})")
    # 3. ratios: "ratio of doors to windows", "doors-to-windows ratio", "m² of floor per door", "windows per room"
    m = re.search(r"\bratio (?:of|between) (?P<a>[^,;?]{1,40}?) (?:to|and|versus|vs\.?|against) (?P<b>[^,;?]{1,40})", t) \
        or re.search(r"(?P<a>[a-z]+)[- ]to[- ](?P<b>[a-z]+) ratio", t)
    if m:
        ka = [h[2] for h in _kind_hits(m.group("a")) if h[2] != "storey"]
        kb = [h[2] for h in _kind_hits(m.group("b")) if h[2] != "storey"]
        if ka and kb and ka[0] != kb[0]:
            return Outer("div", None, None, "count", kinds=(ka[0], kb[0]), spans=[m.span()],
                         why=f"ratio {ka[0]} / {kb[0]}")
    m = re.search(r"\bper (?P<b>[a-z-]+)", t)
    if m:
        metric, kind, _ = _basis_of(m.group("b"))
        if metric == "count" and kind:
            rest = t[:m.start()] + " " + t[m.end():]
            rest_q = _strip_per(question, m.group(0))
            num_hits = [h[2] for h in _kind_hits(fold(_QUOTED.sub(" ", rest_q))) if h[2] != "storey"]
            if num_hits and (num_hits[0] != kind):
                return Outer("div", None, None, None, kinds=(None, kind), num_text=rest_q, spans=[m.span()],
                             why=f"per {kind}")
            if not num_hits and re.search(r"\b(square|sq|m2|area|floor|cubic|m3|volume)\b", rest):
                return Outer("div", None, None, None, kinds=(None, kind), num_text=rest_q, spans=[m.span()],
                             why=f"per {kind}")
    # 4. numeric yes/no: "Are there more than 40 doors on X?", "Is the room area on X larger than 800 m²?"
    if _AUX.match(t):
        m = _CMP.search(t)
        if m:
            w = m.group(1)
            if w in ("exactly", "equal to", "genau", "precies"):
                c = "eq"
            elif w in ("at most", "no more than", "not more than", "hochstens", "hoechstens", "hoogstens"):
                c = "le"
            elif w in ("at least", "no less than", "not less than", "mindestens", "minstens"):
                c = "ge"
            elif any(w.startswith(x) for x in _LOWER):
                c = "lt"
            else:
                c = "gt"
            return Outer("cmp", _num(m.group(2)), None, cmp=c, spans=[m.span()], why=f"yes/no: {c} {m.group(2)}")
    return None


def _strip_per(question: str, per_folded: str) -> str:
    """Remove 'per <word>' (and 'on average') from the raw question, keeping quoted names intact."""
    q = re.sub(r"\bper\s+" + re.escape(per_folded.split(None, 1)[1]) + r"\w*", " ", question, count=1, flags=re.I)
    q = re.sub(r"\b(on average|in average|average|mean)\b", " ", q, flags=re.I)
    return re.sub(r"\s+", " ", q).strip()


def leftover_numbers(question: str, consumed: list[tuple[int, int]], threshold: float | None = None,
                     dims: bool = False) -> list[str]:
    """Numbers in the question (outside quoted names) that no rule used: not units (m², m³), storey references
    ('level 4', '2nd floor'), top-k ('5 largest'), dimension thresholds ('wider than 0.9 m'), the parsed threshold,
    or a span an outer operator consumed."""
    from stoa.solvers.ifc.solver import _DIM_THRESHOLD

    t = text_of(question)
    blank = list(t)
    for a, b in consumed:
        for i in range(a, min(b, len(blank))):
            blank[i] = " "
    t2 = "".join(blank)
    for rx in (_UNIT_DIGIT, _STOREY_NUM, _TOPK, _ROOM_REF) + ((_DIM_THRESHOLD,) if dims else ()):
        t2 = rx.sub(lambda m: " " * len(m.group(0)), t2)
    out = []
    for m in re.finditer(r"(?<![\w.])\d+(?:[.,]\d+)?(?![\w])", t2):
        if threshold is not None and abs(_num(m.group(0)) - threshold) < 1e-9:
            continue
        out.append(m.group(0))
    return out


# ---- room types across languages (the model's labels are in its own language: 'Bad', 'Küche', 'TUALETTRUUM') ----
ROOM_TYPES: dict[str, tuple[str, ...]] = {
    "bathroom": ("bathroom", "bath", "bad", "badezimmer", "badkamer", "salle de bain", "salle d'eau", "bano",
                 "bagno", "kylpyhuone", "vannituba", "vannitoa", "lazienka", "baie", "badrum", "badevaerelse",
                 "shower room", "dusche", "douche", "pesuruum", "pesuhuone"),
    "toilet": ("toilet", "wc", "toilette", "toiletten", "aseo", "tualett", "tualettruum", "vessa", "toalett",
               "toaleta", "lavatory", "restroom", "gaste-wc", "gaeste-wc"),
    "kitchen": ("kitchen", "kuche", "kueche", "keuken", "cuisine", "cocina", "cucina", "keittio", "kook", "kuchnia",
                "kok", "koekken", "kitchenette", "pantry", "teekeuken", "kochen"),
    "bedroom": ("bedroom", "schlafzimmer", "schlafen", "slaapkamer", "chambre", "dormitorio", "camera da letto",
                "makuuhuone", "magamistuba", "sypialnia", "sovrum", "sovevaerelse", "kinderzimmer", "kind"),
    "living room": ("living room", "lounge", "wohnzimmer", "wohnen", "woonkamer", "sejour", "salon",
                    "sala de estar", "soggiorno", "olohuone", "elutuba", "pokoj dzienny", "vardagsrum", "stue"),
    "corridor": ("corridor", "hallway", "hall", "flur", "gang", "diele", "korridor", "couloir", "pasillo",
                 "corridoio", "kaytava", "koridor", "korytarz", "hal", "entree", "entrance", "eingang", "vestibule",
                 "foyer", "fuajee", "lobby", "esik", "verkeersruimte"),
    "storage": ("storage", "storeroom", "store room", "abstellraum", "abstellkammer", "lager", "berging",
                "rangement", "almacen", "ripostiglio", "deposito", "varasto", "panipaik", "schowek", "forrad", "bod"),
    "office": ("office", "buro", "bureau", "kantoor", "oficina", "ufficio", "toimisto", "kabinet", "kontor",
               "arbeitszimmer", "werkkamer", "studio", "study"),
    "staircase": ("staircase", "stairwell", "stair hall", "treppenhaus", "trappenhuis", "escalier", "vano scala",
                  "porraskaytava", "trepikoda", "klatka schodowa", "trapphus", "trappehus"),
    "technical room": ("technical room", "plant room", "mechanical room", "technikraum", "technik", "technische ruimte",
                       "local technique", "cuarto tecnico", "locale tecnico", "tekninen tila", "tehnoruum",
                       "kotlownia", "boiler room", "heizraum", "heizung"),
    "dining room": ("dining room", "dining", "essen", "esszimmer", "eetkamer", "salle a manger", "comedor",
                    "sala da pranzo", "ruokailu", "soogituba", "jadalnia"),
    "garage": ("garage", "garaz", "autotalli", "garaaz"),
    "balcony": ("balcony", "balkon", "balcon", "balcone", "parveke", "rodu", "loggia", "terrace", "terrasse",
                "terras"),
    "utility room": ("utility room", "laundry", "hauswirtschaftsraum", "hwr", "waschkuche", "waschkueche",
                     "wasruimte", "buanderie", "lavadero", "lavanderia", "kodinhoitohuone"),
}
_Q_AMBIGUOUS = {"kind", "gang", "lager", "essen", "kochen", "technik", "studio", "bath", "hall", "store", "camera",
                "chambre", "salon", "entree", "study", "lounge", "wohnen", "schlafen", "heizung"}
_NOT_ROOM = re.compile(r"\bliving (area|space)s?\b|\b(storey|stories|floor)\b|\boffice (building|block)s?\b")


def _syn_rx(s: str) -> str:
    return r"(?<![a-z])" + re.escape(s) + r"(s|es|en|e|er|n)?(?![a-z])"


def room_type_in_question(question: str) -> str | None:
    """The room-type concept a question asks about ('bathrooms' -> 'bathroom'), or None."""
    t = _NOT_ROOM.sub(" ", text_of(question))
    best = None
    for concept, syns in ROOM_TYPES.items():
        for s in syns:
            if (len(s) >= 4 or s == "wc") and s not in _Q_AMBIGUOUS and re.search(_syn_rx(s), t):
                if best is None or len(s) > best[1]:
                    best = (concept, len(s))
    return best[0] if best else None


def label_has_type(label: str, concept: str) -> bool:
    lab = fold(label or "")
    for s in ROOM_TYPES[concept]:
        if len(s) <= 4:
            if re.search(r"(?<![a-z])" + re.escape(s) + r"(?![a-z])", lab):
                return True
        elif s in lab:
            return True
    return False
