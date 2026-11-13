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
    ("door", r"doors?|doorways?|\bov(?:i|ea|et)\b|ovi|\bt[üu]r(?:en)?\b|portes?\b|port[ae]\b|deuren|d[øo]re|d[öo]rr|uks|ust\b|puertas?"),
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
_NUMBERED = re.compile(r"numbered|nummerierten|num[ée]rot[ée]es|numerati", re.I)


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


def infer_task(q: str) -> tuple[str, str | None]:
    """-> (task, unit). Unit follows the question's own unit words (m² vs ft² etc.)."""
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
    if _LABELLED.search(q_noquote) and quoted:
        filters["label"] = quoted[0]
        scope = "label_total" if task in ("area", "volume", "length") else "label"
        target = "room"
    elif quoted and scope == "drawing":
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
