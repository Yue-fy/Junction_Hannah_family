"""Multilingual question parser for floor-plan questions (EN/DE/FR/IT + a few NL/SV words).

Not a template matcher: it finds the *pieces* of a question (object kinds, quoted room labels grounded in
the drawing's own vocabulary, room numbers, apartment letters, "total numbered rooms", the asked unit,
and the operation: sum / difference / largest / smallest) and returns a small expression

    Query(qtype="count"|"area"|"text", op="sum"|"diff"|"max"|"min", terms=[Term(...), ...], unit=...)

so compositions ("doors and windows", "how many more doors than windows", "room 1.06 minus room 1.04",
"apartments B and D") work without new code. Grounding labels in the floor's vocabulary handles quote
styles («», „“, '', "") and apostrophes inside labels ('Cage d'escalier').
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# --- vocabularies ----------------------------------------------------------------------------------
KIND_WORDS: dict[str, list[str]] = {
    "door": [r"doors?", r"doorways?", r"t[üu]ren", r"t[üu]r", r"portes?", r"porta", r"deuren", r"deur", r"d[öo]rr(?:ar)?"],
    "window": [r"windows?", r"fenster", r"fen[êe]tres?", r"finestr[ae]", r"ramen", r"raam", r"f[öo]nster"],
    "toilet": [r"toilets?", r"wcs?", r"toilettes?", r"water[- ]?closets?", r"wc[- ]?seats?", r"gabinett[oi]",
               r"vasi?\s+wc", r"klosett", r"toiletten"],
    "washbasin": [r"wash\s?basins?", r"hand\s?basins?", r"lavabos?", r"lavabi", r"lavandin[oi]", r"waschbecken",
                  r"waschtische?", r"bathroom\s+sinks?", r"basins?", r"wastafels?", r"tv[äa]ttst[äa]ll"],
    "bathtub": [r"bath\s?tubs?", r"baths?(?!\s?room)", r"badewannen?", r"baignoires?", r"vasch?e?\s+da\s+bagno",
                r"vasca", r"vasche", r"badkuip(?:en)?", r"badkar"],
    "shower": [r"showers?", r"duschen", r"dusche", r"douches?", r"docci[ae]", r"docce", r"douche"],
    "apartment": [r"apartments?", r"flats?", r"residential\s+units?", r"dwellings?", r"dwelling\s+units?",
                  r"wohnungen", r"wohnung", r"wohneinheiten", r"appartements?", r"logements?", r"appartament[oi]",
                  r"unit[àa]\s+abitativ[ae]", r"lägenhet(?:er)?", r"woningen", r"woning"],
}
# kinds that are fixtures/objects (not rooms); "sink" alone is ambiguous (kitchen sink vs washbasin)
AMBIGUOUS = {"sink": "washbasin", "sinks": "washbasin"}

# room-name concepts across the swiss vocabulary (used only when no quoted label is given)
CONCEPTS: dict[str, tuple[list[str], list[str]]] = {
    # concept: (question words, room labels in the drawings)
    "bedroom": ([r"bedrooms?", r"schlafzimmer", r"chambres?\s+[àa]\s+coucher", r"camer[ae]\s+da\s+letto", r"sovrum"],
                ["Schlafzimmer", "Chambre à coucher", "Camera da letto"]),
    "bathroom": ([r"bathrooms?", r"badezimmer", r"salles?\s+de\s+bains?", r"bagni", r"badkamers?"],
                 ["Bad", "Bain", "Bagno"]),
    "kitchen": ([r"kitchens?", r"k[üu]chen?", r"cuisines?", r"cucin[ae]", r"keukens?", r"k[öo]k"],
                ["Küche", "Cuisine", "Cucina"]),
    "corridor": ([r"corridors?", r"hallways?", r"halls?", r"korridore?", r"flure?", r"couloirs?", r"corridoi?o?",
                  r"gangen?"], ["Korridor", "Couloir", "Corridoio"]),
    "balcony": ([r"balcon(?:y|ies)", r"balkone?", r"balcons?", r"balconi", r"balcone"], ["Balkon", "Balcon", "Balcone"]),
    "loggia": ([r"loggi(?:a|as|en|e)"], ["Loggia"]),
    "terrace": ([r"terraces?", r"terrassen?", r"terrazz[ae]"], ["Terrasse"]),
    "living": ([r"living\s*(?:rooms?|/\s*dining|areas?)?", r"wohnzimmer", r"wohnen", r"s[ée]jours?", r"soggiorn[oi]",
                r"lounges?"], ["Wohnen/Essen", "Wohnen", "Séjour/repas", "Séjour", "Soggiorno/pranzo", "Soggiorno"]),
    "dining": ([r"dining\s*(?:rooms?)?", r"essz?immer", r"repas", r"pranzo"], ["Essen", "Repas", "Pranzo"]),
    "storage": ([r"storage\s*(?:rooms?)?", r"store\s?rooms?", r"closets?", r"reduits?", r"r[ée]duits?",
                 r"abstellr[äa]ume?", r"ripostigli?o?"], ["Reduit", "Réduit", "Ripostiglio"]),
    "stairs": ([r"stair\s?(?:cases?|wells?|s)", r"treppenh[äa]user?", r"cages?\s+d'escaliers?", r"vani?\s+scala"],
               ["Treppenhaus", "Cage d'escalier", "Vano scala"]),
    "lift": ([r"lifts?", r"elevators?", r"aufz[üu]ge?", r"ascenseurs?", r"ascensor[ei]"], ["Lift", "Ascenseur", "Ascensore"]),
    "cellar": ([r"cellars?", r"basement\s+compartments?", r"kellerabteile?", r"compartiments?\s+caves?"],
               ["Compartiment cave"]),
    "room": ([r"zimmer", r"pi[èe]ces?", r"stanz[ae]"], ["Zimmer", "Pièce", "Stanza", "Raum"]),
}

INCLUDE_OUT = (r"(?:including|incl\.?|inklusive|inkl\.?|einschliesslich|y\s+compris|compris|inclus|incluse?|compres[io]|"
               r"comprese|with)\s+(?:the\s+|die\s+|les\s+|i\s+)?(?:balcon|balkon|loggi|terrass|terrac|outdoor|au(?:ss|ß)en|"
               r"ext[ée]rieur|estern)")
GROSS = (r"\bgross\s+(?:floor\s+|internal\s+|external\s+|living\s+)?area|\bgfa\b|brutto|\bbgf\b|"
         r"surface\s+(?:de\s+plancher\s+)?brute|superficie\s+lorda")  # not "wie gross ist" (= how large)
MEAN_W = r"\baverage\b|\bmean\b|durchschnitt\w*|\bmittlere\w*|\bmoyen(?:ne)?s?\b|\bmedi[ao]\b|im\s+mittel"
PER_W = (r"\b(?:per|pro|je)\s+(?:residential\s+)?(?:apartment|unit|flat|dwelling|wohnung|wohneinheit)|divided\s+by|"
         r"par\s+(?:appartement|logement)|per\s+(?:appartamento|unit[àa]\s+abitativa)")
TIMES_W = (r"how\s+many\s+times|times\s+(?:larger|bigger|greater|as\s+(?:large|big))|give\s+the\s+ratio|\bratio\b|"
           r"\bfa[ck]tor\b|wievielmal|verh[äa]ltnis|combien\s+de\s+fois|\bfois\s+plus|\brapport\b|quante\s+volte|"
           r"\bvolte\s+pi[uù]|\brapporto\b")
SHARE_W = (r"\bshare\b|\bpercent(?:age)?\b|in\s+%|\bproportion\b|\banteil\b|prozent|pourcentage|\bpart\s+de\b|"
           r"percentuale|\bquota\b|\btake\s+up\b|\bnimmt\b.*\bein\b|\boccupe\b|\boccupa\b")
THRESH_GT = (r"(?:more|larger|greater|bigger)\s+than|exceed(?:s|ing)?|\bover\b|\babove\b|[üu]ber|mehr\s+als|"
             r"gr[öo](?:ss|ß)er\s+als|plus\s+de|plus\s+grande?s?\s+que|sup[ée]rieure?s?\s+[àa]|pi[uù]\s+di|"
             r"superiore\s+a|maggiore\s+di|oltre")
THRESH_LT = (r"(?:less|smaller|fewer)\s+than|\bunder\b|\bbelow\b|\bunter\b|weniger\s+als|kleiner\s+als|moins\s+de|"
             r"plus\s+petite?s?\s+que|inf[ée]rieure?s?\s+[àa]|meno\s+di|inferiore\s+a|minore\s+di")
THRESH_GE = r"at\s+least|mindestens|au\s+moins|almeno"
THRESH_W = (r"(" + THRESH_GT + r"|" + THRESH_LT + r"|" + THRESH_GE + r")\s+(\d+(?:[.,]\d+)?)\s*(?:m²|m2|qm|mq|sq|square)")
NEG_APT_W = (r"(?:do(?:es)?\s+not|don't|doesn't|not)\s+(?:belong|lie|part|in|inside|within)\w*|outside\s+(?:of\s+)?"
             r"(?:the\s+)?apartment|other\s+than\s+apartment|except\s+(?:for\s+)?apartment|exclud\w*\s+apartment|"
             r"without\s+apartment|ohne\s+(?:die\s+)?wohnung|au(?:ss|ß)er\s+(?:der\s+)?wohnung|nicht\s+zu\s+wohnung|"
             r"sans\s+l'\s*appartement|hors\s+(?:de\s+)?l'\s*appartement|n'appartiennent\s+pas|senza\s+l'\s*appartamento|"
             r"escluso\s+l'\s*appartamento|tranne\s+l'\s*appartamento|non\s+appartengono")
WHICH_CMP = r"^\s*(?:which|welche[rs]?|quel(?:le)?|quale)\b.*\b(smaller|larger|bigger|greater|kleiner|gr[öo]sser|plus\s+petit|plus\s+grand|più\s+piccol|più\s+grand)"
COUNT_WORDS = r"how\s+many|count|number\s+of|wie\s+viele|anzahl|combien|nombre\s+de|quant[ie]|quante|numero\s+di|hoeveel|hur\s+m[åa]nga"
AREA_WORDS = (r"\barea\b|fl[äa]che|surface|superficie|oppervlak|yta\b|m²|m2\b|square\s+met|sq\.?\s*m\b|square\s+f(?:ee|oo)t|"
              r"sq\.?\s*ft|ft²|ft2\b|how\s+(?:large|big)|wie\s+gross|wie\s+groß")
FT2 = r"square\s+f(?:ee|oo)t|sq\.?\s*ft|ft²|ft2\b|\bsf\b"
DIFF = (r"how\s+many\s+more|more\s+\w+\s+than|by\s+how\s+(?:many|much)|difference|minus|larger\s+than|bigger\s+than|"
        r"greater\s+than|exceeds?|mehr\s+.*\s+als|gr[öo]sser\s+als|größer\s+als|unterschied|differenz|plus\s+de\s+.*\s+que|"
        r"plus\s+grand\w*\s+que|diff[ée]rence|più\s+.*\s+(?:di|che)|differenza|meer\s+.*\s+dan|fler\s+.*\s+än")
DIFF_REV = r"fewer|less\s+than|smaller\s+than|weniger|kleiner\s+als|moins\s+de|plus\s+petit\w*\s+que|meno|minder|mindre"
MAX_W = r"largest|biggest|greatest|gr[öo]ss(?:te|ten)|größte|plus\s+grand|più\s+grande|maggiore|grootste|största"
MIN_W = r"smallest|kleinste|plus\s+petit|più\s+piccol|minore|kleinste|minsta"
TOTAL_NUMBERED = r"numbered|nummeriert|num[ée]rot|numerat|genummerd|numrerade"
JOIN = r"\s*(?:,|and|und|et|e|ed|&|\+|og|en|och)\s*"

ROOMNUM_RE = re.compile(r"(?<![\w.])([A-Z]{0,2}\d{1,3}\.\d{1,3}(?:\.\d{1,3})?)(?![\w.]*\s*(?:m²|m2|ft|%))")
APT_LEAD = (r"(?:apartments?|units?|flats?|wohnungen|wohnung|whg\.?|appartements?|l'appartement|appartament[oi]|"
            r"dell'appartamento|app\.?|lägenhet(?:er(?:na)?)?|woning(?:en)?)")
APT_RE = re.compile("(?i:" + APT_LEAD + r")\s+([A-Z](?:" + JOIN + r"[A-Z])*)(?![\w])")
QUOTES = "'\"«»„“”‘’‹›`´"


@dataclass
class Term:
    kind: str  # count | count_label | area_room | area_label | area_apartment | area_total
    arg: str | list[str] | None = None
    pos: int = 0  # position in the question (for ordering a difference)
    note: str = ""  # how it was parsed ("concept bedroom -> Schlafzimmer|...")
    scope: list[str] | None = None  # apartment letters the term is restricted to ("windows in apartment B")


@dataclass
class Query:
    qtype: str  # count | area | text
    op: str = "sum"  # sum | diff | max | min
    terms: list[Term] = field(default_factory=list)
    unit: str | None = None  # count | m2 | ft2
    notes: list[str] = field(default_factory=list)
    include_outdoor: bool = False  # "including balconies"
    gross: bool = False  # "gross floor area"
    threshold: float | None = None  # for op count_gt / count_lt / count_ge
    consumed: list[str] = field(default_factory=list)  # regexes of question parts the parse handled (for covered())

    def describe(self) -> str:
        parts = []
        for t in self.terms:
            a = t.arg if not isinstance(t.arg, list) else "|".join(t.arg)
            parts.append(f"{t.kind}({a})" if a else t.kind)
        return f"{self.qtype}/{self.op}: " + (" , ".join(parts) or "-") + f" [{self.unit}]"


def _norm(s: str) -> str:
    return unicodedata.normalize("NFC", s).replace(" ", " ")


def _find_words(pattern_list: list[str], text: str) -> list[int]:
    pos = []
    for p in pattern_list:
        for m in re.finditer(r"(?<![\w])" + p + r"(?![\w])", text, re.I):
            pos.append(m.start())
    return sorted(pos)


def find_labels(q: str, vocab: list[str]) -> list[tuple[str, int]]:
    """Room labels quoted in the question, grounded in `vocab` (longest first); falls back to any quoted span."""
    out: list[tuple[str, int]] = []
    taken: list[tuple[int, int]] = []
    for name in sorted(set(vocab), key=len, reverse=True):
        for m in re.finditer(re.escape(name), q):
            s, e = m.start(), m.end()
            if any(not (e <= a or s >= b) for a, b in taken):
                continue
            before = q[:s].rstrip(" ")[-1:] if q[:s].strip() else ""
            after = q[e:].lstrip(" ")[:1]
            if before in QUOTES and after in QUOTES:
                out.append((name, s))
                taken.append((s, e))
    if not out:
        for m in re.finditer(r"[«„“‘\"]\s*([^«»„“”‘’\"]{1,60}?)\s*[»“”’\"]|(?<!\w)'([^']{1,60})'(?!\w)", q):
            lab = (m.group(1) or m.group(2) or "").strip()
            if lab and not re.fullmatch(r"[\d.,\s]+", lab):
                out.append((lab, m.start()))
    return sorted(out, key=lambda t: t[1])


def parse(question: str, vocab: list[str] | None = None, room_numbers: set[str] | None = None) -> Query:
    q = _norm(question)
    ql = q.lower()
    vocab = vocab or []
    is_count = bool(re.search(COUNT_WORDS, ql))
    is_area = bool(re.search(AREA_WORDS, ql))
    unit = "ft2" if re.search(FT2, ql) else "m2"
    notes: list[str] = []

    labels = find_labels(q, vocab)
    # room numbers: keep those that exist on the floor if we know them, else anything room-number-like
    nums = [(m.group(1), m.start()) for m in ROOMNUM_RE.finditer(q)]
    if room_numbers is not None:
        known = [(n, p) for n, p in nums if n in room_numbers]
        if known or not nums:
            nums = known
        else:
            notes.append(f"room numbers {[n for n, _ in nums]} not found on this floor")
    apts: list[tuple[str, int]] = []
    for m in APT_RE.finditer(q):
        for k, letter in enumerate(re.split(JOIN, m.group(1))):
            if letter:
                apts.append((letter.strip(), m.start() + k))
    total_numbered = bool(re.search(TOTAL_NUMBERED, ql))

    # "how many times / by what factor is apartment B larger than A" compares sizes even without an area word
    if re.search(TIMES_W, ql) and (len(apts) >= 2 or len(nums) >= 2) and not is_area:
        is_area, is_count = True, False
    op = "sum"
    if re.search(MAX_W, ql):
        op = "max"
    elif re.search(MIN_W, ql) and not re.search(DIFF, ql):
        op = "min"
    if re.search(DIFF, ql) or re.search(DIFF_REV, ql):
        op = "diff"
    rev = bool(re.search(DIFF_REV, ql)) and not re.search(r"how\s+many\s+more|larger|bigger|greater", ql)

    terms: list[Term] = []
    # area questions -------------------------------------------------------------------------------
    if is_area and not (is_count and not re.search(r"m²|m2\b|square|ft|area|fl[äa]che|surface|superficie", ql)):
        qtype = "area"
        if nums:
            terms = [Term("area_room", n, p) for n, p in nums]
        elif apts:
            terms = [Term("area_apartment", a, p) for a, p in apts]
        elif labels:
            terms = [Term("area_label", lab, p) for lab, p in labels]
        elif total_numbered or re.search(r"\btotal\b|gesamt|totale?|insgesamt|whole\s+floor|entire\s+floor", ql):
            terms = [Term("area_total", None, 0)]
        else:
            for c, (words, labs) in CONCEPTS.items():
                for p in _find_words(words, ql)[:1]:
                    terms.append(Term("area_label", list(labs), p, note=f"concept {c}"))
            if not terms:
                terms = [Term("area_total", None, 0, note="no room/apartment/label named; assumed whole floor")]
        inc = bool(re.search(INCLUDE_OUT, ql))
        gross = bool(re.search(GROSS, ql))
        consumed: list[str] = []
        thr = None
        if apts and re.search(NEG_APT_W, ql) and (total_numbered or re.search(r"\btotal|gesamt|insgesamt|totale|tous|toutes|tutti", ql)):
            # "numbered indoor rooms that do NOT belong to apartment A" = floor total - apartment A
            terms = [Term("area_total", None, -1)] + [Term("area_apartment", a, p) for a, p in apts]
            op, rev = "diff", False
            consumed.append(NEG_APT_W)
        elif apts and re.search(SHARE_W, ql):
            terms = [Term("area_apartment", a, p) for a, p in apts[:1]] + [Term("area_total", None, 10**6)]
            op = "pct"
            consumed.append(SHARE_W)
        elif len(terms) == 2 and re.search(TIMES_W, ql):
            op, rev = "ratio", False
            consumed.append(TIMES_W)
        elif re.search(MEAN_W, ql):
            op = "mean"
            consumed.append(MEAN_W)
        if (m := re.search(THRESH_W, ql)) and is_count and len(terms) >= 1 and terms[0].kind in ("area_room", "area_label"):
            word = m.group(1).lower()
            thr = float(m.group(2).replace(",", "."))
            op = ("count_ge" if re.fullmatch(THRESH_GE, word) else
                  "count_lt" if re.fullmatch(THRESH_LT, word) else "count_gt")
            consumed += [THRESH_W, r"ha(?:ve|s)\s+(?:a|an)\b"]
            qr = Query("count", op, terms, "count", notes, include_outdoor=inc, gross=gross, threshold=thr, consumed=consumed)
            qr.terms.sort(key=lambda t: t.pos)
            return qr
        if re.search(WHICH_CMP, ql) and len(terms) >= 2:
            op = "min" if re.search(r"smaller|kleiner|petit|piccol", ql) else "max"
            qr = Query("text", op, terms, None, notes, include_outdoor=inc, gross=gross, consumed=consumed + [WHICH_CMP, r"\bwhich\b"])
            qr.terms.sort(key=lambda t: t.pos)
            return qr
        if op in ("max", "min") and len(terms) > 1 and not re.search(r"how\s+(?:large|big|much)|what\s+is\s+the\s+(?:net\s+)?(?:floor\s+)?area", ql):
            qtype = "text"
        unit_out = unit if qtype != "text" else None
        if op == "ratio":
            unit_out = None
        elif op == "pct":
            unit_out = "%"
        qr = Query(qtype, op, terms, unit_out, notes, include_outdoor=inc, gross=gross, consumed=consumed)
        if op in ("pct",) or (op == "diff" and consumed):
            qr.terms.sort(key=lambda t: t.pos)
            return qr
        return _finish(qr, rev)

    # count questions ------------------------------------------------------------------------------
    qtype = "count"
    if labels:
        terms = [Term("count_label", lab, p) for lab, p in labels]
    else:
        found: dict[str, int] = {}
        for kind, words in KIND_WORDS.items():
            ps = _find_words(words, ql)
            if ps:
                found[kind] = ps[0]
        if "toilet" in found and "washbasin" not in found and re.search(r"\bwc[- ]?seats?\b", ql):
            pass
        if not found:
            for w, kind in AMBIGUOUS.items():
                ps = _find_words([w], ql)
                if ps:
                    found[kind] = ps[0]
                    notes.append("'sink' read as washbasin (kitchen sinks are not on the FIXTURE layer rules)")
                    break
        # "bath" inside "bathtub" is the same object; "apartment" in "apartment A" is not a count of apartments
        terms = [Term("count", k, p) for k, p in sorted(found.items(), key=lambda kv: kv[1])]
        if not terms:
            for c, (words, labs) in CONCEPTS.items():
                for p in _find_words(words, ql)[:1]:
                    terms.append(Term("count_label", list(labs), p, note=f"concept {c}"))
        if not terms and re.search(r"\brooms?\b|r[äa]ume|pi[èe]ces|locali|kamers|rum\b", ql):
            terms = [Term("count_label", "<numbered>", 0, note="all numbered rooms")]
    if qtype == "count" and len(terms) == 2 and any(t.arg == "apartment" for t in terms) and \
            (re.search(PER_W, ql) or re.search(MEAN_W, ql)):
        # "on average, how many doors per apartment": doors / apartments
        terms = sorted(terms, key=lambda t: t.arg == "apartment")
        qr = Query("count", "ratio", terms, None, notes, consumed=[PER_W, MEAN_W, r"\beach\b"])
        return qr
    # "windows in apartment B": the apartment word + letter is a scope, not a count of apartments
    if apts and any(not (t.kind == "count" and t.arg == "apartment") for t in terms):
        terms = [t for t in terms if not (t.kind == "count" and t.arg == "apartment")]
        for t in terms:
            t.scope = [a for a, _ in apts]
    return _finish(Query(qtype, op if len(terms) > 1 else "sum", terms, "count", notes), rev)


def _finish(qr: Query, rev: bool) -> Query:
    qr.terms.sort(key=lambda t: t.pos)
    if qr.op == "diff" and len(qr.terms) < 2:
        qr.op = "sum"
    if qr.op == "diff" and rev:
        qr.terms = list(reversed(qr.terms))
        qr.notes.append("'fewer/smaller than': second minus first")
    return qr


UNCOVERED = re.compile(
    r"\b(which|welche[rs]?|lequel|laquelle|quale\s+(?:dei|delle)|average|mean|median|durchschnitt|moyenne|media|per\s|each|jede[rs]?|"
    r"chaque|ogni|ratio|percent|percentage|proportion|share|anteil|with\s+(?:a|an|no|more|at)|without\s+(?:a|an|any|windows?|doors?)|that\s+ha(?:ve|s)|"
    r"ha(?:ve|s)\s+(?:a|an|no|any|more|at\s+least|\d+)\b|contain\w*|adjacent|next\s+to|neighbo\w+|between|at\s+least|at\s+most|is\s+there|are\s+there\s+any|do\s+any|"
    r"mit\s+(?:einem|einer|mehr)|ohne\s+(?:fenster|t[üu]r)|avec\s+(?:un|une|plus)|sans\s+(?:fen|porte)|senza)\b|%|(?:more|less|larger|smaller)\s+than\s+\d",
    re.I)


def covered(question: str, qr: Query) -> bool:
    """False if the question has parts the rule parser ignores (then a table-QA fallback should answer)."""
    if not qr.terms:
        return False
    q = _norm(question)
    if qr.qtype == "count" and APT_RE.search(q) and not all(t.scope for t in qr.terms):
        return False  # an apartment letter the rules did not attach to every term
    if YESNO.match(q.strip()):
        return False  # yes/no question
    for pat in qr.consumed:  # parts the parse turned into an operator are covered
        q = re.sub(pat, " ", q, flags=re.I)
    m = UNCOVERED.search(q)
    if m:
        # the standard swiss templates contain none of these, except "excluding ... shafts and voids" etc.
        return False
    return True


YESNO = re.compile(r"^(is|are|does|do|has|have|can|gibt\s+es|hat|ist|sind|y\s+a-t-il|est-ce|existe|c'è|ci\s+sono|ha)\b", re.I)


OPERATOR_HINT = re.compile("|".join(f"(?:{p})" for p in (MEAN_W, TIMES_W, SHARE_W, THRESH_W, NEG_APT_W, PER_W)), re.I)


def operator_unapplied(question: str, qr: Query) -> bool:
    """The question contains an operator word (average, ratio, share, threshold, 'not in apartment', per) but the
    parse applied none: the plain sum is probably the wrong reading -> cap the confidence."""
    return qr.op in ("sum", "diff") and bool(OPERATOR_HINT.search(_norm(question)))
