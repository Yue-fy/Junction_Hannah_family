"""Question -> object class, and room-label text -> room class (Finnish plan conventions).

Kept free of model calls so it is cheap to test. Classes:
  symbols (counted from drawn symbols): window, door, wc_seat, sink, shower_bath
  room labels (counted from room-name texts): bedroom, kitchen, bathroom, sauna, wc_room, balcony
  other: storey
"""

from __future__ import annotations

import re
import unicodedata

SYMBOL_CLASSES = ("window", "door", "wc_seat", "sink", "shower_bath")
ROOM_CLASSES = ("bedroom", "kitchen", "bathroom", "sauna", "wc_room", "balcony")
ALL_CLASSES = (*SYMBOL_CLASSES, *ROOM_CLASSES, "storey")

# Order matters: more specific patterns first (e.g. "separate WC rooms" before "WC seats").
_Q_RULES: list[tuple[str, re.Pattern]] = [
    # sinks/showers first: their questions mention "kitchen and bathroom"; bathrooms before WC rooms: the
    # bathroom question says "not counting separate WC rooms".
    ("sink", re.compile(r"sinks?\b|wash ?basins?|basins?\b|pesuallas|tiskiallas|pesu- ja tiskiallas|altaita|"
                        r"lavabo|waschbecken|spülbecken|lavandino|handfat|diskh", re.I)),
    ("shower_bath", re.compile(r"showers?\b|bath ?tubs?|suihku|kylpyamme|amme\b|dusche|badewanne|douche|"
                               r"baignoire|badkar|dusch", re.I)),
    ("bathroom", re.compile(r"bathrooms?|washrooms?|kylpyhuone|pesuhuone|kylpy- tai pesuhuone|badezimmer|badrum",
                            re.I)),
    ("wc_room", re.compile(r"separate wc|wc[- ]?rooms?|toilet rooms?|erillis\w* wc|wc-tilo|wc-tila|wc-räume|"
                           r"toalettrum", re.I)),
    ("wc_seat", re.compile(r"toilet bowls?|toilet seats?|wc seats?|wc bowls?|wc-istu|toilets?\b|water closets?|"
                           r"klosett|wcs\b|wc-schüssel\w*|toilettenschüssel\w*|toalettstol\w*|toaletter", re.I)),
    ("sauna", re.compile(r"saunas?|saunen|saunoja|saunaa|bastu\w*", re.I)),
    ("kitchen", re.compile(r"kitchen|keitti|küche|cuisine|cucina|kök\b|kokvr", re.I)),
    ("bedroom", re.compile(r"bedrooms?|makuuhuone|schlafzimmer|chambres?|camere da letto|sovrum", re.I)),
    ("balcony", re.compile(r"balcon\w*|parveke|parvekkeit|balkon\w*", re.I)),
    ("storey", re.compile(r"storeys?|stories|floors? \(|how many floors|levels?\b|kerros|geschoss\w*|stockwerk\w*|"
                          r"étages?|våning\w*", re.I)),
    ("door", re.compile(r"doors?\b|doorways?|ovea|ovia|ovet|türen|tür\b|portes?\b|porte\b|dörr\w*", re.I)),
    ("window", re.compile(r"windows?|ikkun\w*|fenster|fenêtres?|finestre|fönster", re.I)),
]


def question_class(question: str) -> str | None:
    q = question.strip()
    for cls, pat in _Q_RULES:
        if pat.search(q):
            return cls
    return None


_PAREN = re.compile(r"\([^()]*\)")
_NEGATED = re.compile(r"\b(not counting|excluding|except|without|apart from|ohne|utom|exklusive)\b[^.;?]*"
                      r"|[^,.;?]*\blukuun ottamatta\b", re.I)  # Finnish puts the negation after the phrase


def question_classes(question: str) -> list[str]:
    """Every object class a question names, in order of appearance (for compositions such as "doors and windows
    in total" or "more windows than doors"). Parenthetical hints and negated phrases ("not counting separate WC
    rooms") are dropped first; overlapping matches go to the earlier, more specific rule ("toilet rooms" is a
    WC room, not a toilet seat)."""
    t = _PAREN.sub(" ", question)
    t = _NEGATED.sub(" ", t)
    taken: list[tuple[int, int, str]] = []
    for cls, pat in _Q_RULES:
        for m in pat.finditer(t):
            if not any(m.start() < e and s < m.end() for s, e, _ in taken):
                taken.append((m.start(), m.end(), cls))
    out: list[str] = []
    for _, _, c in sorted(taken):
        if c not in out:
            out.append(c)
    return out


_MORE = re.compile(r"how many more (.+?) than (.+?)(?: are| is| does| do|\?|$)", re.I)
_YESNO = re.compile(r"^\s*(does|do|is|are|has|have|onko|gibt es|finns det)\b.*\b(yes|no|kyllä|ei|ja|nein|nej)\b", re.I)


def question_op(question: str) -> tuple[str, list[str]]:
    """-> (op, classes): op is "single", "sum", "diff" (first minus second) or "exists" (yes/no)."""
    m = _MORE.search(question)
    if m:
        a, b = question_classes(m.group(1)), question_classes(m.group(2))
        if a and b:
            return "diff", [a[0], b[0]]
    cs = question_classes(question)
    single = question_class(question)
    if _YESNO.search(question) and (cs or single):
        return "exists", [cs[0] if cs else single]
    if len(cs) >= 2:
        return "sum", cs
    return ("single", [single]) if single else ("none", [])


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).upper()
    s = s.replace("Ö", "O").replace("Ä", "A").replace("Å", "A")
    return s


# Room codes (after _norm: upper case, Ö->O, Ä->A). Union of R1's measured CODES table
# (experiments/r1/room_labels/run.py) and Finnish plan practice: MH makuuhuone, K keittiö, KK keittokomero,
# KT keittiötila, TK tupakeittiö (R1 counts it), KH/KPH kylpyhuone, PH/PESUH/PS pesuhuone, SH suihkuhuone,
# S/SAUNA/LH/LOYLYH sauna, WC, PARV parveke. Not mapped: KHH (utility), PKH (dressing), VH (closet),
# OH (living), ET (hall), RT (dining).
CODES = {
    "bedroom": {"MH", "MAKUUHUONE", "MAKUUH"},
    "kitchen": {"K", "KK", "TK", "KT", "KEITTIO", "KEITTOKOMERO", "TUPAKEITTIO", "AVOK", "AVOKEITTIO",
                "KEITTIOTILA", "APUK", "APUKEITTIO"},
    "bathroom": {"KH", "PH", "KPH", "PESUH", "SH", "KYLPYHUONE", "PESUHUONE", "KYLPYH", "PS", "PSH"},
    "wc_room": {"WC"},
    "sauna": {"S", "SAUNA", "LOYLYH", "LOYLYHUONE", "LH"},
    "balcony": {"PARV", "PARVEKE", "LASPARV", "LASITETTUPARVEKE", "RANSKALAINENPARVEKE"},
}
# combined labels ("KH/WC", "PH+S") count once, for the most specific room in this order
_PRIORITY = ("bathroom", "sauna", "bedroom", "kitchen", "balcony", "wc_room")


def label_classes(text: str) -> set[str]:
    """All classes a room label names (R1-style: split on + / , & - and spaces; strip trailing digits)."""
    t = _norm(text).strip().strip(".:;")
    if t.startswith("LASITETTU") or t.startswith("RANSKALAINEN"):
        t = re.sub(r"[\s.]+", "", t)
    hits = set()
    for tok in re.split(r"[+/,&\s-]+", t):
        tok = re.sub(r"\d+$", "", tok.strip(".:;()"))
        for cls, codes in CODES.items():
            if tok in codes:
                hits.add(cls)
    return hits


_TYPE_CODE = re.compile(r"^\s*(\d{1,2})\s*H\s*(\+|$)", re.I)  # apartment type "4H+K+S", "2 H + KK", "1H"


def type_code(text: str) -> dict | None:
    """Apartment type code ("4H+K+S" = 4 rooms + kitchen + sauna) -> {"rooms": 4, "classes": {...}} or None.
    Not a room label: it summarises the whole apartment, so it is a cross-check, never counted as a room."""
    m = _TYPE_CODE.match(_norm(text))
    if not m:
        return None
    rest = _norm(text)[m.end():]
    classes = set()
    for tok in re.split(r"[+/,&\s-]+", rest):
        tok = tok.strip(".:;()")
        for cls, codes in CODES.items():
            if tok in codes:
                classes.add(cls)
    return {"rooms": int(m.group(1)), "classes": classes}


def label_class(text: str) -> str | None:
    """Room label -> one class (combined labels count for the first class in _PRIORITY).
    Apartment type codes ("3H+K+S") return None (see `type_code`)."""
    if type_code(text):
        return None
    hits = label_classes(text)
    for c in _PRIORITY:
        if c in hits:
            return c
    return None


# Short visual definitions used in symbol prompts (Finnish plan drawing conventions).
SYMBOL_DEF = {
    "window": ("window",
               "a window drawn as an opening in an exterior wall, filled with two or three thin parallel lines "
               "along the wall. Count every window opening once (a wide window is still one window)"),
    "door": ("door",
             "a door drawn as a door leaf (a straight line) with a quarter-circle swing arc in a wall opening. "
             "A double door counts once. Openings without a door leaf do not count"),
    "wc_seat": ("toilet",
                "a toilet bowl (WC seat): a small oval or egg-shaped symbol with a small rectangular tank against "
                "the wall"),
    "sink": ("sink",
             "a sink or wash basin: a small rectangle or oval bowl with a drain dot, on the kitchen counter or in a "
             "bathroom/WC. A double-bowl sink counts once"),
    "shower_bath": ("shower or bathtub",
                    "a bathtub (a long rounded rectangle) or a shower (a square shower tray, often with a cross or "
                    "diagonal lines, or a shower head symbol)"),
}
