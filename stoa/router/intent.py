"""Question -> structured intent, with rules that work across languages (no model call).

    parse("How many windows are shown on this floor plan?")
    -> Intent(task="count", target="window", scope="drawing", unit="count", filters={}, lang="en")

`Intent.key` is a language-independent concept key ("count:window:drawing") used by the router to share
gating decisions and priors between translations and paraphrases of the same question. Templates the rules
don't know get target "unknown"; the router then sends them to the general path (never to the prior alone).

Targets are normalised object classes: window, door, storey, wc (toilet seat), sink (sinks + wash basins),
washbasin, shower_bathtub, bathtub, shower, sauna, kitchen, bedroom, bathroom, wc_room, balcony, apartment,
room (rooms/spaces in general or "labelled X"), stair, wall, column, beam, slab, sanitary, light, ...
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field

# --- task (what kind of answer) ------------------------------------------------------------------------
_COUNT = re.compile(
    r"\b(how many|number of|count|kuinka monta|montako|wie viele|anzahl|combien|nombre d|cu[aá]nt[oa]s|"
    r"n[uú]mero de|numero di|num[aă]rul de|quant[ie]|hvor mange|hur m[aå]nga|hoeveel|ile|mitu|antal|aantal)\b", re.I)
_VOLUME = re.compile(r"(m³|\bm3\b|cubic|volume|volumen|tilavuus|\bmaht|rumfang|volym)", re.I)
_AREA = re.compile(r"(m²|\bm2\b|ft²|\bft2\b|sq\.? ?ft|square (?:feet|foot|met)|\barea\b|fl[aä]che|pinta-ala|"
                   r"surface|superficie|\bareal|oppervlakte|p[oõ]randapind|\bpind\b|powierzchnia|yta\b)", re.I)
_LENGTH = re.compile(r"(\blength\b|\blong\b|\blang\b|l[aä]nge|l[æe]ngde|pituus|lengte|longueur|lunghezza|"
                     r"longitud|pikkus|\bin met(?:re|er)s?\b|in metern|\bmeters?\b|\bmetres?\b|\bmeter\b)", re.I)
_YESNO = re.compile(r"^\s*(is|are|does|do|has|have|can|onko|gibt es|ist|sind|y a-t-il|est-ce|c'è|ci sono|er|har)\b",
                    re.I)
_WHICH = re.compile(r"^\s*(which|what is the (?:name|type|label|use|function)|name|list|give|welche|quel(?:le)?s?\b|"
                    r"mik[aä]|mitk[aä])", re.I)

# --- targets: (target, regex), most specific first ------------------------------------------------------
_T = [
    ("wc_room", r"separate wc rooms?|toilet rooms?|erillis\w* wc-til|wc-til|wc-r[aä]um|separate toilets?"),
    ("shower_bathtub", r"showers?\s*(?:and|plus|\+|&|,)\s*(?:bath)?tubs?|suihku\w* ja kylpyamme|duschen und badewannen|bathtubs?\s*(?:and|plus|\+|&|,)\s*showers?"),
    ("sink", r"sinks? and wash ?basins?|pesu- ja tiskial|wash ?basins? and sinks?|tiskial|sinks?\b|sp[üu]lbecken|[eé]viers?"),
    ("wc", r"toilet bowls?|wc seats?|wc-istui|toilets? \(wc\)|\btoilets?\b|\bwcs?\b|\bwc's\b|klosett|cuvettes?|wc-schalen"),
    ("washbasin", r"wash ?basins?|lavabos?|lavabi|waschbecken|handwaschbecken|lavandini|pesuallas|pesualtai"),
    ("bathtub", r"bath ?tubs?|badewannen?|baignoires?|vasche da bagno|vasca|kylpyamm|badekar"),
    ("shower", r"showers?|duschen?|douches?|docce|doccia|suihku"),
    ("sauna", r"saunas?|saunoja|saunaa|saunen|bastu\w*|badstue"),
    ("kitchen", r"kitchens?|kitchenettes?|keitti|k[üu]chen?|cuisines?|cucin[ae]|keuken|k[øo]kken|k[öo]k\b"),
    ("bedroom", r"bedrooms?|makuuhuon|schlafzimmer|chambres? [àa] coucher|camer[ae] da letto|slaapkamer|sovev[æe]relse|sovrum"),
    ("bathroom", r"bathrooms?|washrooms?|kylpy- tai pesuhuon|pesuhuon|kylpyhuon|badezimmer|salles? de bains?|bagni\b|badkamer"),
    ("balcony", r"balcon(?:y|ies|e|i)|parveke|balkon\w*|balcons?"),
    ("storey", r"floors? \(storeys?\)|storeys \(floors?\)|storeys\b|stories\b|number of floors|how many floors|kerrosta|kerroksia|geschosse\b|stockwerke|[eé]tages\b|piani\b|verdiepingen"),
    ("apartment", r"apartments?|residential units?|wohnungen|appartements?|logements?|appartament[io]|unit[àa] abitativ|"
                  r"asuntoj|asunto"),
    ("window", r"windows?|ikkun|fenster|fen[eê]tres?|finestr[ae]|ramen\b|vinduer|f[öo]nster|aken|akn|ventanas?|ferestre|okien|okna"),
    ("door", r"doors?|doorways?|\bov(?:i|ea|et)\b|\bovi\w*|\bt[üu]r(?:en)?\b|portes?\b|port[ae]\b|deuren|d[øo]re|d[öo]rr|\buks\b|\bukse\w*|\bust\b|puertas?"),
    ("stair", r"stairs?|staircases?|treppen?|escaliers?|scale\b|escaleras?|trappen?|trapper|portaat|trepp|sc[ăa]ri\b|schod"),
    ("column", r"columns?|st[üu]tzen|s[øo]jler|colonnes?|pilares?|pilastri|kolommen|pylv|\bposti|\bpost\b|st[âa]lpi|słup"),
    ("beam", r"beams?|tr[äa]ger|bjælker|poutres?|vigas?|travi\b|balken|palk|\btala|grinzi|belk"),
    ("slab", r"slabs?|decken und bodenplatten|bodenplatten|d[æe]k og plader|vloeren|losas?|dalles?|laatat"),
    ("wall", r"walls?|w[äa]nde?|v[æe]gge|murs?\b|muri\b|muros?|wanden|sein[äia]|pere[țt]i|[śs]cian"),
    ("sanitary", r"sanitary (?:fixtures?|terminals?)|sanit[äa]r|sanitaire|sanitari|sanitarios"),
    ("light", r"light(?:ing)? fixtures?|lights?\b|leuchten|luminaires?|corpuri de iluminat|lampen|valaisim|apparecchi di illuminazione|lumin"),
    ("furniture", r"furniture|m[öo]bel"),
    ("parking", r"parking (?:spaces?|spots?)|parkpl[äa]tze"),
    ("room", r"rooms?|spaces?|r[äa]ume?\b|raum\b|pi[eè]ces?|locali?\b|ruimtes?|ruimte|\brum(?:met)?\b|ruumi|"
             r"r[äa]ums\b|pomieszczeni|huonei|huonetta|local(?:es)?\b|\bdesignation|bezeichnung|denominazione"),
]
_TARGETS = [(t, re.compile(p, re.I)) for t, p in _T]

_QUOTED = re.compile(r"«([^»]{1,80})»|„([^“”\"]{1,80})[“”\"]|“([^”]{1,80})”|‘([^’]{1,80})’|(?<!\w)'((?:[^'\n]|(?<=\w)'(?=\w)){1,80})'(?!\w)|"
                     r"\"([^\"]{1,80})\"")
_ROOM_NO = re.compile(r"\b(?:room|raum|pi[eè]ce|locale|huone|ruimte|rum)\s+([A-Z]{0,2}\d+(?:\.\d+)*)\b", re.I)
_APT = re.compile(r"\b(?:apartment|wohnung|appartement|appartamento|dell'appartamento|de l'appartement|asunto|unit)\s+"
                  r"([A-Z0-9]{1,3})\b", re.I)
_SHEET = re.compile(r"\bsheet\s+([A-Z]{1,3}-?\d{1,4}(?:\.\d+)?)", re.I)
_LABELLED = re.compile(r"labell?ed|bezeichnung|d[ée]signation|d[ée]sign[ée]e?s|denominazione|denominati|"
                       r"named|called|nimetty", re.I)
_TOTAL = re.compile(r"\btotal\b|gesamt|totale?\b|samlede|totaal|zusammen|kokku|yhteens|alle\b|all\b|tous|toutes|tutti", re.I)
_MODEL = re.compile(r"\bin the model\b|enth[äa]lt das modell|\bmodel(?:o|lo|ul|u|len|e|l|lis|li)?\b|mod[eè]le\b|mudel\w*",
                    re.I)
_STOREY_PLAN = re.compile(r"floor plan of|on the floor plan|im grundriss|im geschoss|plantegningen for|plano de la planta|"
                          r"de la planta|plattegrond van|korruse(?:l)?|on <q>|op <q>|på <q>|kondygnacji", re.I)
_OUTDOOR_EXCL = re.compile(r"excluding balconies|ohne balkone|hors balcons|esclusi balconi|except balconies", re.I)
# "..., not counting separate WC rooms" must not make the target wc_room
_NEGATION = re.compile(r"(not counting|excluding|except|without|ohne|hors|esclusi|sauf)[^?;.]*|"
                       r"[^,;?]*\b(lukuun ottamatta|ausgenommen)", re.I)
_NO_LABEL = re.compile(r"\b([A-Z]{0,2}\d+(?:\.\d+)+)\s*\(\s*<q>\s*\)")
_NUMBERED = re.compile(r"numbered|nummerierten|num[ée]rot[ée]es|numerati", re.I)


# --- modifiers that change WHAT is computed (the hidden set is "harder"): a known key + one of these is NOT the
# known template ("average area of rooms labelled X" is not "total area of rooms labelled X"). The pipeline sends
# such questions to the general agent instead of canonicalising them to a template.
# number words for constants stated in words ("if every bedroom gets two beds")
_NUMWORD = (r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|twice|double|half|zwei|drei|vier|f[üu]nf|doppelt|"
            r"halb|deux|trois|quatre|cinq|double|moiti[ée]|due|tre|quattro|cinque|doppi[oa]|met[àa]|kaksi|kolme|nelj[äa]|"
            r"viisi|kahdesti|puoli|twee|drie|vier|vijf|tv[åa]|tre|fyra|fem|to|fire)\b")
_OPS = [
    ("avg", r"\b(average|mean|on average|durchschnitt\w*|moyenne|medi[ao]\b|keskim\w*|gennemsnit\w*|genomsnitt\w*|"
            r"gemiddeld\w*|keskmi\w*|[śs]redni\w*)\b"),
    ("share", r"\b(percent\w*|percentage|share|proportion|fraction|ratio|prozent\w*|anteil\w*|pourcentage|"
              r"percentuale|prosent\w*|osuus\w*|andel\w*|procent\w*)\b|%"),
    ("diff", r"\b(difference|differs?|compared (?:with|to)|unterschied\w*|diff[ée]rence|differenza|erotus|forskel\w*|"
             r"verschil)\b"),
    ("rest", r"\b(other than|leaving out|apart from|besides|all the other|the other rooms|remaining|übrigen|autres que|"
             r"lukuun ottamatta <q>|do(?:es)? not belong|don't belong|not (?:part of|belonging to|in|within) "
             r"(?:the )?(?:apartment|unit|storey|floor|level|room)|outside (?:of )?(?:the )?(?:apartment|unit)|"
             r"nicht zu|n'appartiennent pas|ne font pas partie)"),
    ("ratio", r"\b(how many times|times (?:larger|bigger|smaller|greater|as (?:large|big|many))|divided by|"
              r"per (?:apartment|unit|storey|floor|level|room|bedroom|person)|mal so (?:gro(?:ß|ss)|viel)|fois plus)\b"),
    ("threshold", r"\b(?:gr[öo](?:ß|ss)er|kleiner|mehr|weniger)\s+als\s+\d|\bplus (?:grande?s?|petite?s?|de)\s+(?:que\s+)?\d|"
                  r"\bmoins de\s+\d|\bpi[uù] (?:grandi|piccol[ie]|di)\s+(?:di\s+)?\d|\bmeno di\s+\d|"
                  r"\b(?:groter|kleiner|meer|minder)\s+dan\s+\d|\b(?:st[öo]rre|mindre|mer)\s+[äa]n\s+\d|"
                  r"\b(?:suurempi|suurempia|pienempi|pienempi[äa]|enemm[äa]n|v[äa]hemm[äa]n)\s+kuin\s+\d|"
                  r"\b(?:larger|bigger|smaller|more|less|greater|fewer)\s+than\s+(?:\d+|one|two|three|four|five|six|seven|"
                  r"eight|nine|ten)\b|\b(?:over|under|above|below|at least|at most|exceeding|mindestens|"
                  r"h[öo]chstens|au moins|v[äa]hint[äa][äa]n)\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|"
                  r"zwei|drei|deux|trois|kaksi|kolme)\b"),
    # comparison between named things: "which storey has more doors, '0' or '-1'?", "apartment B or apartment H"
    ("compare", r"\bwhich\b[^?]*\b(?:more|fewer|less|larger|bigger|smaller|greater|higher|lower|longer|shorter)\b|"
                r"<q>\s*,?\s*(?:or|oder|ou|o|vai|eller|of)\s+(?:on\s+)?<q>|"
                r"\b(?:apartment|unit|wohnung|appartement)\s+[A-Z]\s+(?:or|oder|ou)\s+(?:apartment|unit|wohnung|appartement)?\s*[A-Z]\b"),
    # two scopes summed: "all rooms on 'A' and on 'B'", "on 'EG' und auf '1.OG'"
    ("multi_scope", r"\b(?:on|auf|sur|op|in)\s+<q>\s*,?\s*(?:and|und|et|en|og|ja)\s+(?:on|auf|sur|op|in)\s+<q>"),
    # DERIVED quantities (W5 01:49): computed FROM a measured quantity, never the quantity itself. A rate ("m² of
    # floor per door", "doors per 100 m²"; 'per apartment/room/storey' stays an average, see ratio), a price ("each
    # door costs 450 €"), or a constant given in the question ("if one litre covers 8 m²"). 0 train templates hit
    # outside ifc_bench (free-text model questions, not routed by these).
    ("rate", r"\b(?:per|pro|par|kohden|por cada|per ogni|f[öo]r varje|for hver)\s+(?!(?:cent|cento|mille|cents?|"
             r"rapport|the|a|an|il|la|lo|l'|i|gli|le|les|un|una|uno|des|du|de|der|die|das|den|dem|el|los|las)\b)"
             r"(?!(?:apartments?|appartements?|wohnung\w*|appartament\w*|asun\w*|units?|storeys?|stories|floors?|levels?|"
             r"[ée]tages?|geschoss\w*|stockwerk\w*|piano|piani|kerro\w*|rooms?|zimmer|r[äa]ume?|pi[eè]ces?|stanz\w*|"
             r"local[ei]|huonee\w*|bedrooms?|persons?|personnes?|persona|people)\b)\w|/\s*(?:doors?|windows?|rooms?|m²|m2|sq)|"
             r"\d\s*\S+\s+(?:kohden|kohta)\b"),  # fi/et postposition: "100 neliömetriä kohden"
    ("cost", r"\b(?:cost\w*|price[sd]?|pricing|kost(?:et|en|ar|er)?|preis\w*|co[uû]t\w*|prix|prezz\w*|maksa\w*|hinta\w*|"
             r"euros?|eur|dollars?|usd|chf|franken|francs?|kronor|kroner|pounds?|budget)\b|[€$£]"),
    ("given", r"\d+(?:[.,]\d+)?\s*(?:hours?|hrs?|h|days?|minutes?|mins?|weeks?|months?|litres?|liters?|kg|kilos?|tonnes?|"
              r"tons?|workers?|stunden|std|tage?n?|minuten|wochen|liter|heures?|jours?|semaines?|ore|giorni|minuti|"
              r"tuntia?|p[äa]iv[äa][äa]?|minuuttia|litraa?|timmar|dagar|minuter|uur|dagen|timer|dage)\b|"
              r"\b(?:how many|wie viele|combien d['e]|quant[ie]|montako|kuinka monta|hur m[åa]nga|hoeveel|hvor mange)\s+"
              r"(?:hours|days|minutes|weeks|months|litres|liters|kilos|tonnes|workers|stunden|tage|minuten|liter|heures|"
              r"jours|ore|giorni|tuntia|p[äa]iv[äa][äa]|litraa|timmar|dagar|uur|dagen|timer|dage)\b|"
              r"\b(?:if|assuming|assume|suppose|supposing|given that|wenn|falls|angenommen|jos|hvis|ifall|indien|se)\b"
              r"[^?.;]*(?:\d|" + _NUMWORD + r")|\bsi\s+(?:une?|le|la|les|l'|chaque|on|el|cada)\b[^?.;]*(?:\d|" + _NUMWORD + r")"),
]
DERIVED = ("rate", "cost", "given")
_OPS_RX = [(n, re.compile(p, re.I)) for n, p in _OPS]
_APT_SCOPE = re.compile(r"\b(?i:apartment|wohnung|appartement|appartamento|asunto|unit)\s+[A-Z0-9]{1,3}\b")
_GENERIC = {"room", "unknown", "sanitary"}


def targets_mentioned(question: str) -> list[str]:
    """Distinct object classes named in the question (quoted names and 'not counting ...' clauses removed)."""
    q = _QUOTED.sub(" <q> ", _fold(question))
    q = _NEGATION.sub(" ", q)
    out = []
    for t, rx in _TARGETS:
        # whole words only here ("indoor" is not a door, "taken" is not Estonian 'aken')
        m = next((m for m in rx.finditer(q) if m.start() == 0 or not q[m.start() - 1].isalnum()), None)
        if m:
            out.append(t)
            q = q[:m.start()] + " " + q[m.end():]  # "showers and bathtubs" is one target, not shower + bathtub
    return out


# words that add structure beyond one plain concept (comparisons, exclusions, restrictions), in many languages; with a
# number outside quotes/parentheses. Parenthesised definitions ("(kitchen and bathroom combined)") do not count.
_STRUCT = re.compile(
    r"\b(?:more|fewer|less|than|difference|minus|both|either|neither|except|excluding|without|only|each|mehr als|"
    r"weniger als|ohne|au(?:ß|ss)er|nur|beide|plus de|moins de|plus que|moins que|sans|sauf|seulement|pi[uù] di|"
    r"meno di|senza|solo|enemm[äa]n|v[äa]hemm[äa]n|ilman|paitsi|vain|fler|f[äa]rre|än|utan|f[öo]rutom|bara|b[åa]da|"
    r"meer dan|minder dan|zonder|behalve|alleen|flere|f[æa]rre|uden|undtagen|kun|rohkem|v[äa]hem|ilma|ainult|"
    r"wi[eę]cej|mniej|bez|tylko|m[aá]s que|menos que|excepto)\b|\d", re.I)


def extra_structure(question: str) -> bool:
    """Does an unseen wording carry more than one plain concept? (F 03:23: on held-out, confident answers to such
    questions read as one atomic count were right 33% of the time; plain paraphrases in `hard` 79%.)"""
    t = re.sub(r"\([^)]*\)", " ", _QUOTED.sub(" ", _fold(question)))
    if _STRUCT.search(t):
        return True
    # two object classes outside definitions = a compound read as one (F 04:05)
    return len({x for x in targets_mentioned(t) if x not in _GENERIC}) >= 2


def modifiers(question: str) -> list[str]:
    """Meaning-changing modifiers: avg, share, diff, rest, threshold, multi (several object classes)."""
    q = _QUOTED.sub(" <q> ", _fold(question))
    ops = [n for n, rx in _OPS_RX if rx.search(q)]
    # several object classes: >= 2 outside parentheses, or an enumeration of >= 3 inside one ("wet rooms
    # (bathrooms, WC rooms and saunas)"); "(kitchen and bathroom combined)" in the sinks template is a definition
    q2 = _fold(question)
    q2 = _APT_SCOPE.sub(" ", q2)  # "windows in apartment B": the apartment is a scope, not a second object class
    outside = re.sub(r"\([^)]*\)", " ", q2)
    outside = re.sub(r"[^,;?(]*\bexcluded\b", " ", outside)
    t_out = {t for t in targets_mentioned(outside) if t not in _GENERIC}
    n_out = len(t_out)
    n_in = max([len({t for t in targets_mentioned(m) if t not in _GENERIC} - t_out)
                for m in re.findall(r"\(([^)]*)\)", q2)] or [0])
    if n_out >= 2 or n_in >= 3:
        ops.append("multi")
    return ops


@dataclass
class Intent:
    task: str  # count | area | volume | length | text | yesno | other
    target: str  # normalised object class or "unknown"
    scope: str  # drawing | room | label | label_total | apartment | floor_total | storey | model | sheet
    unit: str | None
    filters: dict = field(default_factory=dict)
    lang: str = "?"

    @property
    def key(self) -> str:
        return f"{self.task}:{self.target}:{self.scope}"

    def to_dict(self) -> dict:
        return {**asdict(self), "key": self.key}

    def describe(self) -> str:
        f = ", ".join(f"{k}={v}" for k, v in self.filters.items())
        return f"{self.task} {self.target} [{self.scope}]" + (f" ({f})" if f else "")


_LANG_HINTS = [
    ("es", r"(¿|\bcu[aá]l|\bcu[aá]nt|\bplanta\b|\blocal\b)"),
    ("pl", r"\b(jaka|jest|ile|pomieszcze\w*|kondygnacj\w*)\b"),
    ("fi", r"\b(kuinka|montako|pohjapiirustu|onko|mik[aä]|yhteens)\w*"),
    ("de", r"\b(wie|gibt|sind|ist|der|die|das|im|geschoss|grundriss)\b"),
    ("fr", r"\b(combien|quelle|quel|est|sont|de la|ce plan|cet [ée]tage|pi[eè]ce)\b"),
    ("it", r"\b(quant[ie]|qual|questo|questa|piano|pianta|locale)\b"),
    ("nl", r"\b(hoeveel|wat is|van de|op de|ruimte|vloer)\b"),
    ("da", r"\b(hvor|hvad|af|rummet|plantegningen)\b"),
    ("et", r"\b(kui|mitu|korrusel|ruumi)\b"),
    ("sv", r"\b(hur|m[aå]nga|vilka|finns)\b"),
    ("en", r"\b(how|what|which|is|are|the|of)\b"),
]
_LANGS = [(code, re.compile(p, re.I)) for code, p in _LANG_HINTS]


def _lang(q: str) -> str:
    for code, rx in _LANGS:
        if rx.search(q):
            return code
    return "?"


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


# "how many square feet of ...", "wie viele Quadratmeter ...": a count cue followed by a UNIT is a quantity question
_QTY_AFTER_COUNT = re.compile(
    r"\b(?:how many|how much|wie viele?|wieviel\w*|combien de|quant[ie]|hoeveel|hur m[aå]nga|kuinka (?:monta|paljon)|"
    r"ile|hvor mange|cu[aá]nt[oa]s)\s+(?:of\s+)?(?P<u>cubic (?:metres|meters|feet|foot)|m³|m3\b|kubikmeter\w*|"
    r"square (?:metres|meters|feet|foot)|sq\.? ?(?:ft|m)\b|m²|m2\b|ft²|ft2\b|quadratmeter\w*|qm\b|quadratfu(?:ß|ss)|"
    r"m[eè]tres? carr[ée]s|pieds? carr[ée]s|metri quadr\w*|piedi quadr\w*|vierkante (?:meter|voet)\w*|"
    r"kvadratmeter\w*|neli[öo]\w*|metres|meters|feet|foot|ft\b|meter\b|metern?\b|fu(?:ß|ss)\b|m[eè]tres?\b|pieds\b|"
    r"metri\b|piedi\b|metri[äa]\b|metres? of)", re.I)


def _qty_unit(u: str) -> tuple[str, str]:
    u = u.lower()
    feet = bool(re.search(r"feet|foot|ft|fu(?:ß|ss)|pied|piedi|voet", u))
    if re.search(r"cubic|³|m3|kubik", u):
        return "volume", "ft3" if feet else "m3"
    if re.search(r"square|sq|²|m2|ft2|quadrat|qm|carr|quadr|vierkant|kvadrat|neli", u):
        return "area", "ft2" if feet else "m2"
    return "length", "ft" if feet else "m"


def infer_task(q: str) -> tuple[str, str | None]:
    """-> (task, unit). Unit follows the question's own unit words (m² vs ft² etc.)."""
    mq = _QTY_AFTER_COUNT.search(q)
    if mq:
        return _qty_unit(mq.group("u"))
    if _VOLUME.search(q) and not _COUNT.search(q):
        return "volume", ("ft3" if re.search(r"ft³|ft3|cubic f", q, re.I) else "m3")
    if _COUNT.search(q):
        return "count", "count"
    if _AREA.search(q):
        return "area", ("ft2" if re.search(r"ft²|\bft2\b|sq\.? ?ft|square f", q, re.I) else "m2")
    if _LENGTH.search(q):
        unit = "ft" if re.search(r"\b(feet|ft)\b", q, re.I) else "m"
        return "length", unit
    if _YESNO.search(q):
        return "yesno", None
    return "text", None


def parse(question: str) -> Intent:
    q = _fold(question).strip()
    task, unit = infer_task(q)
    filters: dict = {}
    quoted = [next(g for g in m.groups() if g).strip() for m in _QUOTED.finditer(q)]
    # remove quoted names before matching targets ("rooms labelled 'Bad'" must not become bathroom)
    q_noquote = _QUOTED.sub(" <q> ", q)
    q_noquote = _NEGATION.sub(" ", q_noquote)
    target = "unknown"
    for t, rx in _TARGETS:
        if rx.search(q_noquote):
            target = t
            break
    scope = "drawing"
    m = _ROOM_NO.search(q_noquote)
    if m and task in ("area", "volume", "length"):
        filters["room_no"] = m.group(1)
        if quoted:
            filters["label"] = quoted[0]
        scope = "room"
        target = "room"
    ma = _APT.search(q_noquote)
    if ma and task in ("area",) and target in ("apartment", "balcony", "room", "unknown"):
        filters["apartment"] = ma.group(1).upper()
        scope, target = "apartment", "apartment"
    elif ma and task == "count" and (ma.group(1).isupper() or ma.group(1).isdigit()):
        # "How many windows in apartment B?": keep the scope (never canonicalise it to the whole floor; dxf answers it)
        rest = q_noquote[:ma.start()] + " " + q_noquote[ma.end():]
        t2 = next((t for t, rx in _TARGETS if rx.search(rest)), None)
        if t2 and t2 != "apartment":
            filters["apartment"] = ma.group(1)
            scope, target = "apartment", t2
    nos = _NO_LABEL.findall(q_noquote)
    if len(nos) >= 2 and scope == "drawing" and task in ("area", "count", "volume", "length", "text", "yesno"):
        # swiss "rooms 2.03 ('Bad') and 2.01 ('Zimmer')": numbered rooms with their labels, not a room on a storey
        filters["rooms"] = nos
        scope, target = "rooms", "room"
    elif _LABELLED.search(q_noquote) and quoted:
        filters["label"] = quoted[0]
        scope = "label_total" if task in ("area", "volume", "length") else "label"
        target = "room"
    elif quoted and scope == "drawing" and not nos:
        # ifc_models: "the room 'X' on 'Level 1'" / "on 'Level 1'" / "in the model 'X'"
        if _MODEL.search(q_noquote) and task == "count":
            filters["model"] = quoted[-1]
            scope = "model"
        elif _STOREY_PLAN.search(q_noquote) or len(quoted) >= 2 or task in ("count", "area", "volume", "length") or re.search(r"\b(on|op|på|auf|im|en|de)\s+<q>", q_noquote, re.I):
            filters["storey"] = quoted[-1]
            scope = "storey"
            if len(quoted) >= 2 or (task == "area" and target == "room" and not _TOTAL.search(q_noquote)):
                if len(quoted) >= 2:
                    filters["room"] = quoted[0]
                    scope = "room"
                    # "on '1.korrus' does 'KORIDOR (119)' take" / "on 'A' …, leaving out 'B'": the name right after a
                    # storey preposition is the storey, whatever its position (W4 novel: roles were swapped)
                    pos = [m.start() for m in re.finditer(r"<q>", q_noquote)]
                    st = [i for i, p in enumerate(pos) if re.search(
                        r"\b(?:on|op|på|auf|im|sur|au|dans|del|della|sul|kerroksessa|korrusel)\s*$", q_noquote[:p], re.I)]
                    if len(pos) == len(quoted) and len(st) == 1:
                        filters["storey"] = quoted[st[0]]
                        filters["room"] = next(x for i, x in enumerate(quoted) if i != st[0])
    if task in ("area",) and scope == "drawing" and (_NUMBERED.search(q_noquote) or _OUTDOOR_EXCL.search(q)):
        scope, target = "floor_total", "room"
    if scope == "storey" and task in ("area", "volume", "length") and _TOTAL.search(q_noquote):
        scope = "storey_total"
    ms = _SHEET.search(q)
    if ms:
        filters["sheet"] = ms.group(1).upper()
        if scope == "drawing":
            scope = "sheet"
    return Intent(task=task, target=target, scope=scope, unit=unit, filters=filters, lang=_lang(q))


if __name__ == "__main__":  # pragma: no cover
    import sys

    for line in sys.argv[1:] or sys.stdin:
        print(parse(line).to_dict())
