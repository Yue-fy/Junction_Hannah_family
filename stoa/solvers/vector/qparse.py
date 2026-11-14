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
               ["Compartiment cave", "Vano cantina", "Kellerabteil", "Keller", "Cave", "Cantina"]),
    "room": ([r"zimmer", r"pi[èe]ces?", r"stanz[ae]"], ["Zimmer", "Pièce", "Stanza", "Raum"]),
}

INCLUDE_OUT = (r"(?:including|incl\.?|inklusive|inkl\.?|einschliesslich|y\s+compris|compris|inclus|incluse?|compres[io]|"
               r"comprese|with)\s+(?:the\s+|die\s+|les\s+|i\s+)?(?:balcon|balkon|loggi|terrass|terrac|outdoor|au(?:ss|ß)en|"
               r"ext[ée]rieur|estern)")
GROSS = (r"\bgross\s+(?:floor\s+|internal\s+|external\s+|living\s+)?area|\bgfa\b|brutto|\bbgf\b|"
         r"surface\s+(?:de\s+plancher\s+)?brute|superficie\s+lorda")  # not "wie gross ist" (= how large)
MEAN_W = (r"\baverage\b|\bmean\b|durchschnitt\w*|\bmittlere\w*|\bmoyen(?:ne)?s?\b|\bmedi[ao]\b|im\s+mittel|"
          r"\bgemiddeld\w*|genomsnitt\w*|\bmedel\w*|\bpromedio\b|keskim[äa][äa]r\w*|keskiarvo|[śs]redni\w*")
PER_W = (r"\b(?:per|pro|je)\s+(?:residential\s+)?(?:apartment|unit|flat|dwelling|wohnung|wohneinheit)|divided\s+by|"
         r"par\s+(?:appartement|logement)|per\s+(?:appartamento|unit[àa]\s+abitativa)|"
         r"per\s+(?:woning|appartement|wooneenheid|l[äa]genhet|bostad|bostadsenhet)|por\s+(?:apartamento|vivienda)")
TIMES_W = (r"how\s+many\s+times|times\s+(?:larger|bigger|greater|as\s+(?:large|big))|give\s+the\s+ratio|\bratio\b|"
           r"\bfa[ck]tor\b|wievielmal|verh[äa]ltnis|combien\s+de\s+fois|\bfois\s+plus|\brapport\b|quante\s+volte|"
           r"\bvolte\s+pi[uù]|\brapporto\b|hoeveel\s+keer|\bkeer\s+(?:zo\s+)?(?:groter|groot|kleiner)|verhouding|"
           r"hur\s+m[åa]nga\s+g[åa]nger|g[åa]nger\s+(?:st[öo]rre|s[åa]\s+stor)|f[öo]rh[åa]llande|\bkvot\b|"
           r"cu[áa]ntas\s+veces|veces\s+(?:m[áa]s\s+grande|mayor)|\braz[óo]n\b|kuinka\s+monta\s+kertaa|kertaa\s+suurempi|"
           r"\bsuhde\b|ile\s+razy|razy\s+wi[ęe]ksz\w*|\bstosunek\b|\bmultiple\s+of\b|relative\s+to")
# "by what percentage is B larger than A" = relative difference 100·(B−A)/A, not B's share (W4 04:04)
PCTDIFF_W = (r"(?:what|how\s+(?:many|much))\s+(?:percent(?:age)?|%)(?:\s+points?)?\b.{0,60}?\b(?:larger|bigger|greater|more|"
             r"smaller|less|lower|higher)\b|\b(?:percent(?:age)?|%)\s+(?:larger|bigger|greater|more|smaller|less)\s+than\b|"
             r"um\s+wie\s*viel(?:e)?\s+prozent.{0,60}?(?:gr[öo]ss|gr[öo]ß|klein|mehr|weniger)|"
             r"prozent\s+(?:gr[öo]sser|größer|kleiner|mehr|weniger)\s+als|"
             r"de\s+combien\s+de\s+pour\s*-?\s*cent.{0,60}?\b(?:plus|moins)\b|pour\s*-?\s*cent\s+(?:plus|moins)\s+(?:grand|petit)|"
             r"di\s+(?:quanto|che)\s+percent\w*.{0,60}?\b(?:più|meno)\b|per\s*cento\s+(?:più|meno)\s+(?:grande|piccol)")
PCTLESS_W = r"\b(?:smaller|less|lower|kleiner|weniger|moins|plus\s+petit|meno|più\s+piccol)"
SHARE_W = (r"\bshare\b|\bpercent(?:age)?\b|in\s+%|\bproportion\b|\banteil\b|prozent|pourcentage|\bpart\s+de\b|"
           r"percentuale|\bquota\b|\btake\s+up\b|\bnimmt\b.*\bein\b|\boccupe\b|\boccupa\b|\baandeel\b|\bprocent\w*|"
           r"\bandel(?:en)?\b|\bporcentaje\b|\bproporci[óo]n\b|\bosuus\b|prosent\w*|\budzia[łl]\b|\btakes\s+up\b|"
           r"\binneemt\b|\btar\s+upp\b")
THRESH_GT = (r"(?:more|larger|greater|bigger)\s+than|exceed(?:s|ing)?|\bover\b|\babove\b|[üu]ber|mehr\s+als|"
             r"gr[öo](?:ss|ß)er\s+als|plus\s+de|plus\s+grande?s?\s+que|sup[ée]rieure?s?\s+[àa]|pi[uù]\s+di|"
             r"superiore\s+a|maggiore\s+di|oltre|meer\s+dan|groter\s+dan|\bboven\b|mer\s+[äa]n|st[öo]rre\s+[äa]n|"
             r"\b[öo]ver\b|m[áa]s\s+de|mayor(?:es)?\s+(?:a|que)|yli|suurempi\s+kuin|wi[ęe]ksz\w*\s+ni[żz]|powy[żz]ej")
THRESH_LT = (r"(?:less|smaller|fewer)\s+than|\bunder\b|\bbelow\b|\bunter\b|weniger\s+als|kleiner\s+als|moins\s+de|"
             r"plus\s+petite?s?\s+que|inf[ée]rieure?s?\s+[àa]|meno\s+di|inferiore\s+a|minore\s+di|minder\s+dan|"
             r"kleiner\s+dan|\bonder\b|mindre\s+[äa]n|\bunder\b|menos\s+de|menor(?:es)?\s+(?:a|que)|"
             r"pienempi\s+kuin|mniejsz\w*\s+ni[żz]|poni[żz]ej")
THRESH_GE = r"at\s+least|mindestens|au\s+moins|almeno|ten\s+minste|minstens|\bminst\b|al\s+menos|v[äa]hint[äa][äa]n|co\s+najmniej"
THRESH_W = (r"(" + THRESH_GT + r"|" + THRESH_LT + r"|" + THRESH_GE + r")\s+(\d+(?:[.,]\d+)?)\s*(?:m²|m2|qm|mq|sq|square|kvm|vierkante)")
NEG_APT_W = (r"(?:do(?:es)?\s+not|don't|doesn't|not)\s+(?:belong|lie|part|in|inside|within)\w*|outside\s+(?:of\s+)?"
             r"(?:the\s+)?apartment|other\s+than\s+apartment|except\s+(?:for\s+)?apartment|exclud\w*\s+apartment|"
             r"without\s+apartment|ohne\s+(?:die\s+)?wohnung|au(?:ss|ß)er\s+(?:der\s+)?wohnung|nicht\s+zu\s+wohnung|"
             r"sans\s+l'\s*appartement|hors\s+(?:de\s+)?l'\s*appartement|n'appartiennent\s+pas|senza\s+l'\s*appartamento|"
             r"escluso\s+l'\s*appartamento|tranne\s+l'\s*appartamento|non\s+appartengono|non\s+fanno\s+parte|"
             r"al\s+di\s+fuori\s+dell'\s*appartamento|eccetto\s+l'\s*appartamento|n't\s+(?:belong|in|part|inside|within)|"
             r"apart\s+from\s+apartment|besides\s+apartment|minus\s+apartment|"
             r"niet\s+(?:tot|bij|in)\s+(?:het\s+)?(?:appartement|woning)|buiten\s+(?:het\s+)?(?:appartement|woning)|"
             r"behalve\s+(?:het\s+)?(?:appartement|woning)|zonder\s+(?:het\s+)?(?:appartement|woning)|"
             r"exclusief\s+(?:het\s+)?(?:appartement|woning)|met\s+uitzondering\s+van\s+(?:het\s+)?(?:appartement|woning)|"
             r"inte\s+(?:tillh[öo]r|h[öo]r\s+till|ing[åa]r\s+i|ligger\s+i)|utom\s+l[äa]genhet|f[öo]rutom\s+l[äa]genhet|"
             r"exklusive\s+l[äa]genhet|utanf[öo]r\s+l[äa]genhet|excepto\s+el\s+apartamento|sin\s+el\s+apartamento|"
             r"fuera\s+del\s+apartamento|no\s+pertenecen")
WHICH_CMP = (r"^\s*(?:which|welche[rs]?|quel(?:le)?|lequel|laquelle|quale|welk[e]?|vilk(?:en|et)|cu[áa]l|kumpi|kt[óo]r[ey])\b.*"
             r"\b(smaller|larger|bigger|greater|kleiner|gr[öo]sser|größer|plus\s+petit|plus\s+grand|più\s+piccol|più\s+grand|"
             r"groter|mindre|st[öo]rre|m[áa]s\s+peque[ñn]|m[áa]s\s+grande|pienempi|suurempi|mniejsz|wi[ęe]ksz)")
COUNT_WORDS = (r"how\s+many|count|number\s+of|wie\s+viele|anzahl|combien|nombre\s+de|quant[ie]|quante|numero\s+di|hoeveel|"
               r"hur\s+m[åa]nga|cu[áa]nt[oa]s|quant[oa]s|n[úu]mero\s+de|kuinka\s+monta|montako|\bile\b|kolik|h[áa]ny\b|\bmitu\b|\bka[çc]\b|"
               r"\bhvor\s+mange|\bhur\s+m[åa]nga")
AREA_WORDS = (r"arean?\b|vloeroppervl|ytan\b|fl[äa]che|surface|superficie|oppervlak|yta\b|m²|m2\b|square\s+met|sq\.?\s*m\b|square\s+f(?:ee|oo)t|"
              r"sq\.?\s*ft|ft²|ft2\b|how\s+(?:large|big)|wie\s+gross|wie\s+groß")
FT2 = r"square\s+f(?:ee|oo)t|sq\.?\s*ft|ft²|ft2\b|\bsf\b"
DIFF = (r"how\s+many\s+more|more\s+\w+\s+than|by\s+how\s+(?:many|much)|difference|minus|larger\s+than|bigger\s+than|"
        r"greater\s+than|exceeds?|mehr\s+.*\s+als|gr[öo]sser\s+als|größer\s+als|unterschied|differenz|plus\s+de\s+.*\s+que|"
        r"plus\s+grand\w*\s+que|diff[ée]rence|più\s+.*\s+(?:di|che)|differenza|meer\s+.*\s+dan|fler\s+.*\s+än")
DIFF_REV = r"fewer|less\s+than|smaller\s+than|weniger|kleiner\s+als|moins\s+de|plus\s+petit\w*\s+que|meno|minder|mindre"
MAX_W = r"largest|biggest|greatest|gr[öo]ss(?:te|ten)|größte|plus\s+grand|più\s+grande|maggiore|grootste|största"
MIN_W = r"smallest|kleinste|plus\s+petit|più\s+piccol|minore|kleinste|minsta"
# "except balconies, loggias, terraces …" / "(Summe aller Räume ohne Balkone …)" / "hors balcons" / "esclusi balconi"
EXCL_CLAUSE = (r"(?:\bexcept\b|\bexcluding\b|\bexclusive\s+of\b|\bwithout\b|\bnot\s+counting\b|\bohne\b|\bau(?:ss|ß)er\b|"
               r"\bausgenommen\b|\bexkl\.?|\bhors\b|\bsans\b|à\s+l'exclusion|\bexcept[ée]e?s?\b|\bnon\s+compris\b|"
               r"\besclus[ioae]\b|\bsenza\b|\btranne\b|\beccett\w*|\bzonder\b|\bexklusive\b|\butom\b)[^)?;:]*")
# true superlatives only (not comparatives "plus grand que" / "più grande di" / "grösser als")
SUPER_MAX = (r"\b(?:largest|biggest|greatest)\b|gr[öo](?:ss|ß)te[nrs]?\b|\b(?:le|la|les|l')\s*plus\s+grand|"
             r"\b(?:il|la|lo|i|le|l')\s*(?:\w+\s+)?pi[uù]\s+grand|\bgrootste\b|\bst[öo]rsta\b")
SUPER_MIN = (r"\bsmallest\b|\bkleinste[nrs]?\b|\b(?:le|la|les|l')\s*plus\s+petit|\b(?:il|la|lo|i|le|l')\s*(?:\w+\s+)?pi[uù]\s+piccol|"
             r"\bminsta\b")
TOTAL_NUMBERED = r"numbered|nummeriert|num[ée]rot|numerat|genummerd|numrerade"
JOIN = r"\s*(?:,|and|und|et|e|ed|&|\+|og|en|och)\s*"
# generic "room" nouns (not a label): "the largest room", "la plus grande pièce", "das grösste Zimmer"
ROOM_NOUN = (r"\brooms?\b|\bzimmer\b|\br[äa]ume?\b|\bpi[èe]ces?\b|\blocaux\b|\blocal\b|\bstanz[ae]\b|\blocal[ei]\b|"
             r"\bvan[oi]\b|\bkamers?\b|\bruimtes?\b|\brum(?:men)?\b")
APT_NOUN = r"\b(?:apartments?|flats?|units?|dwellings?|wohnung(?:en)?|wohneinheit(?:en)?|appartements?|logements?|appartament[oi]|lägenhet(?:er)?|woning(?:en)?)\b"
SIZE_W = (r"\barea\b|fl[äa]che|surface|superficie|oppervlak|\bsize\b|gr[öo](?:ss|ß)e\b|taille|dimensione|m²|m2\b|"
          r"square|sq\.?\s*(?:m|ft)|how\s+(?:large|big)|wie\s+gro|quanto\s+[èe]\s+grande|hoe\s+groot")
DIFF_BETWEEN = (r"difference\s+(?:\w+\s+){0,4}?between|unterschied\s+(?:\w+\s+){0,4}?zwischen|diff[ée]rence\s+"
                r"(?:\w+\s+){0,4}?entre|differenza\s+(?:\w+\s+){0,4}?(?:tra|fra)|verschil\s+(?:\w+\s+){0,4}?tussen|"
                r"skillnad\w*\s+(?:\w+\s+){0,4}?mellan|diferencia\s+(?:\w+\s+){0,4}?entre")
COMMON_W = (r"common\s+(?:areas?|parts?|spaces?|rooms?)|shared\s+(?:areas?|spaces?|rooms?)|circulation\s+areas?|"
            r"(?:belong|belongs|belonging)\s+to\s+no\s+(?:apartment|unit|flat)|not\s+(?:in|part\s+of|assigned\s+to)\s+any\s+"
            r"(?:apartment|unit|flat)|outside\s+(?:all|any|the)\s+(?:apartments|units|flats)|allgemein(?:fl[äa]che|r[äa]ume|e\s+"
            r"fl[äa]che)\w*|gemeinschaft\w*|parties?\s+communes?|espaces?\s+communs?|parti\s+comuni|spazi\s+comuni|"
            r"keiner\s+wohnung|aucun\s+appartement|nessun\s+appartamento")
SIZE_ONLY = (r"\bsize\b|\bfloor\s*space\b|\bfloor\s*area\b|how\s+much\s+(?:floor\s+)?space|\bspace\s+(?:does|do|is)\b|"
             r"gr[öo](?:ss|ß)e\b|wie\s+gro|taille|dimensione|quanto\s+[èe]\s+grande|hoe\s+groot|storlek|hur\s+stor")
TEXT_Q = (r"^\s*(?:which|welche[rs]?|lequel|laquelle|quale|in\s+which|welk[e]?|vilk(?:en|et))\b|"
          r"^\s*quel(?:le)?s?\s+(?:pi[èe]ce|appartement|logement|local)|^\s*qual\s+[èe]\s+(?:la\s+stanza|l'appartamento|il\s+locale)|"
          r"^\s*what\s+(?:is\s+)?the\s+(?:largest|biggest|smallest)\s+(?:room|apartment|flat|unit)\b(?!.*\b(?:area|size)\b)")
WHICH_Q = (r"^\s*(?:which|what\s+(?:is\s+the\s+)?(?:name|number|label)|welche[rs]?|wie\s+heisst|quel(?:le)?s?\s+(?:est|sont)?|"
           r"lequel|laquelle|quale|qual\s+[èe]|welk[e]?|vilk(?:en|et))\b|^\s*what\s+(?:is\s+)?the\s+(?:largest|biggest|smallest)\s+room")

ROOMNUM_RE = re.compile(r"(?<![\w.])([A-Z]{0,2}\d{1,3}\.\d{1,3}(?:\.\d{1,3})?)(?![\w.]*\s*(?:m²|m2|ft|%))")
APT_LEAD = (r"(?:apartments?|units?|flats?|wohnungen|wohnung|whg\.?|appartements?|l'appartement|appartament[oi]|"
            r"dell'appartamento|app\.?|lägenhet(?:er(?:na)?)?|l[äa]genheten|woning(?:en)?|bostad(?:en)?|apartamentos?)")
APT_RE = re.compile("(?i:" + APT_LEAD + r")\s+([A-Z](?:" + JOIN + r"[A-Z])*)(?![\w])")
ROOM_NO_RE = re.compile(r"(?i:\b(?:room|raum|zimmer|pi[èe]ce|local[e]?|stanza|vano|kamer|ruimte|rum|rummet)\s+"
                        r"(?:no\.?\s*|nr\.?\s*|n°\s*|number\s+|nummer\s+|numéro\s+|numero\s+)?)"
                        r"([A-Z]{0,2}\d{1,4}[a-z]?)(?![\w.,]*\s*(?:m²|m2|ft|%|sq|qm|mq))(?![.\d])")
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
    absolute: bool = False  # "the difference between A and B": |A - B| (symmetric wording)

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
    if not is_count and not is_area and re.search(SIZE_ONLY, ql):
        is_area = True  # "what's the size of the Küche, room 3.09" is an area, not a count of Küche rooms (Q red team)
    unit = "ft2" if re.search(FT2, ql) else "m2"
    notes: list[str] = []

    labels = find_labels(q, vocab)
    # room numbers: keep those that exist on the floor if we know them, else anything room-number-like
    nums = [(m.group(1), m.start()) for m in ROOMNUM_RE.finditer(q)]
    # "room 1" / "Raum 12" / "pièce n° 3": a room number without a dot, named as a room (W4: was read as the floor total)
    for m in ROOM_NO_RE.finditer(q):
        if not any(m.start(1) <= p < m.end(1) or n == m.group(1) for n, p in nums):
            nums.append((m.group(1), m.start(1)))
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
    if re.search(TIMES_W, ql) and (len(apts) >= 2 or len(nums) >= 2):
        is_area, is_count = True, False  # "how many times" is not a count
    op = "sum"
    if re.search(MAX_W, ql):
        op = "max"
    elif re.search(MIN_W, ql) and not re.search(DIFF, ql):
        op = "min"
    if re.search(DIFF, ql) or re.search(DIFF_REV, ql):
        op = "diff"
    rev = bool(re.search(DIFF_REV, ql)) and not re.search(r"how\s+many\s+more|larger|bigger|greater", ql)

    terms: list[Term] = []
    inc0 = bool(re.search(INCLUDE_OUT, ql))
    # superlatives over a SET ("the largest room", "the smallest apartment", "la plus grande pièce") -------------
    # (the templates only ever compare NAMED things: "which is larger, apartment B or H")
    sup = re.search(SUPER_MAX, ql) or re.search(SUPER_MIN, ql)
    if sup and len(nums) < 2 and len(apts) < 2 and not re.search(DIFF, ql):
        sop = "max" if re.search(SUPER_MAX, ql) else "min"
        after = ql[sup.end():sup.end() + 40]
        asks_size = bool(re.search(SIZE_W, ql)) and not re.search(TEXT_Q, ql)
        cons = [SUPER_MAX, SUPER_MIN, ROOM_NOUN, APT_NOUN, SIZE_W, WHICH_Q]
        any_concept = any(_find_words(w, ql) for c, (w, _) in CONCEPTS.items() if c != "room")
        apt_sup = re.match(r"\s*(?:\w+\s+){0,2}?" + APT_NOUN, after) or (
            re.search(APT_NOUN, ql) and not re.search(ROOM_NOUN, ql) and not labels and not any_concept)
        if apt_sup and not apts:
            if is_count:  # "how many rooms does the largest apartment have": a nested query
                return Query("count", "sum", [], "count", notes + ["nested superlative (count inside the largest "
                                                                    "apartment): left to table QA"])
            t = [Term("area_apartment", "<all>", sup.start(), note=f"{sop} over all apartments")]
            return Query("area" if asks_size else "text", sop, t, (unit if asks_size else None), notes,
                         include_outdoor=inc0, gross=bool(re.search(GROSS, ql)), consumed=cons)
        if is_count:
            # "how many windows does the largest room have" etc.: nested, leave to table QA
            return Query("count", "sum", [], "count", notes + ["nested superlative: left to table QA"])
        if nums or (apts and not re.search(ROOM_NOUN, ql) and not labels):
            pass  # "largest of room 2.04" / "the largest apartment B" -> ordinary paths below
        else:
            labs: list[str] | None = [lab for lab, _ in labels] or [lab for lab, _ in bare_labels(q, vocab)] or None
            note = "any numbered indoor room"
            if labs is None:
                for c, (words, clabs) in CONCEPTS.items():
                    if c == "room":
                        continue
                    if _find_words(words, ql):
                        labs, note = list(clabs), f"concept {c}"
                        break
            t = Term("rooms", labs, sup.start(), note=note, scope=[a for a, _ in apts] or None)
            return Query("area" if asks_size else "text", sop, [t], (unit if asks_size else None), notes,
                         include_outdoor=inc0, consumed=cons)
    # common areas: numbered indoor rooms in NO apartment ("belong to no apartment", "common areas", "shared")
    if (is_area or re.search(SIZE_W, ql)) and not apts and not nums and not is_count and re.search(COMMON_W, ql):
        return Query("area", "sum", [Term("area_room", "<all>", 0, note="numbered indoor rooms in no apartment",
                                          scope=[None])], unit, notes, include_outdoor=inc0,
                     consumed=[COMMON_W, NEG_APT_W, APT_NOUN])
    # averages / thresholds over ALL apartments ("average apartment size", "apartments larger than 60 m²")
    if re.search(APT_NOUN, ql) and not apts and not nums and not labels:
        if re.search(MEAN_W, ql) and (is_area or re.search(SIZE_W, ql)) and not re.search(PER_W, ql):
            return Query("area", "mean", [Term("area_apartment", "<all>", 0, note="mean over all apartments")], unit,
                         notes, include_outdoor=inc0, gross=bool(re.search(GROSS, ql)), consumed=[MEAN_W, APT_NOUN, SIZE_W])
        if (m := re.search(THRESH_W, ql)) and is_count:
            word = m.group(1).lower()
            op_t = ("count_ge" if re.fullmatch(THRESH_GE, word) else
                    "count_lt" if re.fullmatch(THRESH_LT, word) else "count_gt")
            return Query("count", op_t, [Term("area_apartment", "<all>", 0, note="threshold over all apartments")],
                         "count", notes, include_outdoor=inc0, threshold=float(m.group(2).replace(",", ".")),
                         consumed=[THRESH_W, APT_NOUN, r"\b(?:are|is|have|has|sind|haben|sont|ont|sono|hanno)\b"])
    # "how many rooms are smaller than 5 m²" (no room list named): every numbered indoor room
    if is_count and not nums and not labels and re.search(ROOM_NOUN, ql) and (m := re.search(THRESH_W, ql)):
        word = m.group(1).lower()
        op_t = ("count_ge" if re.fullmatch(THRESH_GE, word) else
                "count_lt" if re.fullmatch(THRESH_LT, word) else "count_gt")
        return Query("count", op_t, [Term("area_room", "<all>", 0, note="threshold over all numbered indoor rooms",
                                          scope=[a for a, _ in apts] or None)],
                     "count", notes, include_outdoor=inc0, threshold=float(m.group(2).replace(",", ".")),
                     consumed=[THRESH_W, ROOM_NOUN, APT_RE.pattern, r"\b(?:are|is|have|has|sind|haben|sont|ont|sono|hanno)\b"])
    # room-type concepts named in the question (not inside "except balconies, loggias…", "including balconies",
    # "living area"): blank out exclusion/inclusion clauses first, keeping positions
    qc = re.sub(EXCL_CLAUSE, lambda m: " " * len(m.group(0)), ql)
    qc = re.sub(INCLUDE_OUT, lambda m: " " * len(m.group(0)), qc)
    concept_terms: list[Term] = []
    for c, (words, clabs) in CONCEPTS.items():
        if c == "room":
            continue
        for p in _find_words(words, qc)[:1]:
            if c == "living" and re.search(r"living\s+(?:space|area)|wohnfl[äa]che|surface\s+habitable", ql):
                continue
            concept_terms.append(Term("area_label", list(clabs), p, note=f"concept {c}"))
    # area questions -------------------------------------------------------------------------------
    if is_area and not (is_count and not re.search(r"m²|m2\b|square|ft|area|fl[äa]che|surface|superficie|yta\b|ytan\b|arean\b|oppervl", ql)):
        qtype = "area"
        if not labels and not nums:
            labels = bare_labels(q, vocab) or labels
        scoped_label = apts and (labels or concept_terms) and not re.search(NEG_APT_W, ql) and \
            not re.search(SHARE_W, ql) and not re.search(TIMES_W, ql) and len(apts) == 1
        two_apt_label = len(apts) == 2 and (labels or concept_terms) and len(labels or concept_terms) == 1 and \
            not re.search(NEG_APT_W, ql) and not re.search(SHARE_W, ql)
        if nums:
            terms = [Term("area_room", n, p) for n, p in nums]
        elif two_apt_label:
            l0 = (labels or [(t.arg, t.pos) for t in concept_terms])[0][0]
            terms = [Term("area_label", l0, p, note="per apartment", scope=[a]) for a, p in apts]
        elif scoped_label:
            # "the kitchen in apartment A": the label's rooms inside that apartment, not the whole apartment
            terms = [Term("area_label", lab, p, scope=[a for a, _ in apts]) for lab, p in labels] or \
                    [Term("area_label", t.arg, t.pos, note=t.note, scope=[a for a, _ in apts]) for t in concept_terms]
        elif apts:
            terms = [Term("area_apartment", a, p) for a, p in apts]
        elif labels:
            terms = [Term("area_label", lab, p) for lab, p in labels]
        elif concept_terms and not total_numbered:
            terms = concept_terms  # "the total area of all bathrooms" = the bathrooms, not the floor
        elif total_numbered or re.search(r"\btotal\b|gesamt|totale?|insgesamt|whole\s+floor|entire\s+floor", ql):
            terms = [Term("area_total", None, 0)]
        else:
            words, clabs = CONCEPTS["room"]
            for p in _find_words(words, ql)[:1]:
                terms.append(Term("area_label", list(clabs), p, note="concept room"))
            if not terms:
                terms = [Term("area_total", None, 0, note="no room/apartment/label named; assumed whole floor")]
        inc = bool(re.search(INCLUDE_OUT, ql))
        gross = bool(re.search(GROSS, ql))
        consumed: list[str] = []
        thr = None
        if apts and re.search(NEG_APT_W, ql) and (total_numbered or re.search(r"\btotal|gesamt|insgesamt|totale|tous|toutes|tutti|\balle\b|\balla\b|samtliga|"
                                                                      r"\ball\b|todas|todos|kaikki|wszystkie|overige|[öo]vriga|other", ql)):
            # "numbered indoor rooms that do NOT belong to apartment A" = floor total - apartment A
            terms = [Term("area_total", None, -1)] + [Term("area_apartment", a, p) for a, p in apts]
            op, rev = "diff", False
            consumed.append(NEG_APT_W)
        elif len(terms) == 2 and re.search(PCTDIFF_W, ql):
            op = "pctdiff_less" if re.search(PCTLESS_W, ql) else "pctdiff"
            consumed += [PCTDIFF_W, SHARE_W]
        elif len(apts) == 1 and re.search(SHARE_W, ql) and (labels or concept_terms):
            lab = [Term("area_label", l, p, scope=[apts[0][0]]) for l, p in labels] or \
                  [Term("area_label", t.arg, t.pos, note=t.note, scope=[apts[0][0]]) for t in concept_terms]
            terms = lab[:1] + [Term("area_apartment", apts[0][0], 10**6)]
            op = "pct"
            consumed.append(SHARE_W)
        elif apts and re.search(SHARE_W, ql):
            terms = [Term("area_apartment", a, p) for a, p in apts[:1]] + [Term("area_total", None, 10**6)]
            op = "pct"
            consumed.append(SHARE_W)
        elif len(terms) == 2 and re.search(TIMES_W, ql):
            op, rev = "ratio", False
            consumed.append(TIMES_W)
        elif len(terms) == 2 and op == "diff" and re.search(DIFF_BETWEEN, ql):
            consumed.append(r"\bbetween\b|\bzwischen\b|\bentre\b|\btra\b|\bfra\b|\btussen\b|\bmellan\b")
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
            op = "min" if re.search(r"smaller|kleiner|petit|piccol|mindre|peque[ñn]|pienempi|mniejsz", ql) else "max"
            qr = Query("text", op, terms, None, notes, include_outdoor=inc, gross=gross, consumed=consumed + [WHICH_CMP, r"\bwhich\b"])
            qr.terms.sort(key=lambda t: t.pos)
            return qr
        if op in ("max", "min") and len(terms) > 1 and not re.search(r"how\s+(?:large|big|much)|what\s+is\s+the\s+(?:net\s+)?(?:floor\s+)?area", ql):
            qtype = "text"
        unit_out = unit if qtype != "text" else None
        if op == "ratio":
            unit_out = None
        elif op in ("pct", "pctdiff", "pctdiff_less"):
            unit_out = "%"
        qr = Query(qtype, op, terms, unit_out, notes, include_outdoor=inc, gross=gross, consumed=consumed,
                   absolute=op == "diff" and len(terms) == 2 and bool(re.search(DIFF_BETWEEN, ql)))
        if op in ("pct", "pctdiff", "pctdiff_less") or (op == "diff" and consumed):
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
            terms = [Term("count_label", lab, p) for lab, p in bare_labels(q, vocab)]
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
    # "how many rooms does apartment B have": numbered indoor rooms inside the apartment (not a count of apartments)
    if apts and terms and all(t.kind == "count" and t.arg == "apartment" for t in terms) and \
            re.search(r"\brooms?\b|\br[äa]ume\b|\blocaux\b|\blocali\b|\bkamers\b|\bruimtes\b|\brum(?:men)?\b", ql):
        terms = [Term("count_label", "<numbered>", 0, note="all numbered indoor rooms", scope=[a for a, _ in apts])]
        return _finish(Query(qtype, "sum", terms, "count", notes), rev)
    if apts and terms and all(t.kind == "count" and t.arg == "apartment" for t in terms):
        # "How many bathrooms does apartment A have?" / "Wie viele Zimmer hat Wohnung A?": labelled rooms inside it
        cterms = [Term("count_label", list(clabs), ps[0], note=f"concept {c}", scope=[a for a, _ in apts])
                  for c, (words, clabs) in CONCEPTS.items() if (ps := _find_words(words, ql))]
        if cterms:
            return _finish(Query(qtype, "sum", cterms, "count", notes), rev)
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
    r"\b(which|welche[rs]?|lequel|laquelle|quale\s+(?:dei|delle)|average|mean|median|durchschnitt|moyenne|media|per\s+(?:apartment|unit|flat|room|dwelling|floor|storey|wohnung|logement|appartement)|each|jede[rs]?|"
    r"chaque|ogni|ratio|percent|percentage|proportion|share|anteil|with\s+(?:a|an|no|more|at)|without\s+(?:a|an|any|windows?|doors?)|that\s+ha(?:ve|s)|"
    r"ha(?:ve|s)\s+(?:a|an|no|any|more|at\s+least|\d+)\b|contain\w*|adjacent|next\s+to|neighbo\w+|between|at\s+least|at\s+most|is\s+there|are\s+there\s+any|do\s+any|"
    r"mit\s+(?:einem|einer|mehr)|ohne\s+(?:fenster|t[üu]r)|avec\s+(?:un|une|plus)|sans\s+(?:fen|porte)|senza|"
    r"perimeters?|umfang|p[ée]rim[èe]tre|perimetro|lengths?|l[äa]nge|longueur|lunghezza|long(?:er|est)?\s+side|"
    r"width|breite|largeur|larghezza|wide|dimensions?|abmessung\w*|how\s+long)\b|%|(?:more|less|larger|smaller)\s+than\s+\d",
    re.I)


def bare_labels(q: str, vocab: list[str]) -> list[tuple[str, int]]:
    """Drawing labels written WITHOUT quotes, capitalised as on the plan ("the Bad in apartment C"); not at the start
    of the sentence, at least 3 letters, generic 'Raum'/'Lift' left to the concept words. Used for area questions only."""
    out: list[tuple[str, int]] = []
    for name in sorted({v for v in vocab if len(v) >= 3 and v[:1].isupper() and v not in ("Raum", "Lift")},
                       key=len, reverse=True):
        for m in re.finditer(r"(?<![\w'])" + re.escape(name) + r"(?![\w])", q):
            if m.start() > 0 and q[:m.start()].strip() and not any(m.start() < e and s < m.end() for _, s, e in out):
                out.append((name, m.start(), m.end()))
    return [(n, s) for n, s, _ in sorted(out, key=lambda t: t[1])]


NUM_TOKEN = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?![\w])")


def unused_numbers(question: str, qr: "Query") -> list[str]:
    """Numbers stated in the question that the parse did not use: a price, rate, constant or percentage ("450 euros
    per door", "add 15 %"). A rule answer then answers the base quantity without the arithmetic (F, hard3: 30% of
    derived-quantity questions). Room numbers, apartment ids, thresholds, quoted labels, unit exponents, ordinals and
    "N decimal places" are not counted."""
    q = re.sub(r"[%s][^%s]{0,60}[%s]" % (QUOTES, QUOTES, QUOTES), " ", question)  # quoted labels
    q = re.sub(r"\b(?:m|ft|sq\.?\s*ft|qm|mq)\s*[2²³3]\b", " ", q, flags=re.I)  # m2, ft2
    q = re.sub(r"\b\d+\s*(?:st|nd|rd|th|er|e|ème|eme|te|ten|ter|°|º|ª|o|a)\b", " ", q, flags=re.I)  # ordinals
    q = re.sub(r"\b\d+\s+(?:decimal|decimals|dezimal\w*|décimal\w*|decimal\w*|nachkomma\w*|significant)\b", " ", q,
               flags=re.I)
    used = set()
    for t in qr.terms:
        for a in ([t.arg] if isinstance(t.arg, str) else list(t.arg or [])):
            used.add(str(a).strip().lower())
    if qr.threshold is not None:
        th = qr.threshold
        used |= {f"{th:g}", f"{th:g}".replace(".", ","), f"{th:.1f}", f"{th:.2f}", f"{th:.1f}".replace(".", ","),
                 f"{th:.2f}".replace(".", ",")}
    out = []
    for m in NUM_TOKEN.finditer(q):
        n = m.group(0)
        if n.lower() in used or n.rstrip(".,") in used:
            continue
        # a room number like 2.05 written with a label (room 2.05) that the parse resolved under another spelling
        if any(u.endswith(n) or n.endswith(u) for u in used if u and u[0].isdigit() and len(u) >= 3):
            continue
        out.append(n)
    return out


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
    if qr.op not in ("max", "min") and (re.search(SUPER_MAX, q, re.I) or re.search(SUPER_MIN, q, re.I)):
        return False  # a superlative the rules did not apply ("rooms of the largest apartment")
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
    q = _norm(question)
    for pat in qr.consumed:  # operators the parse applied (e.g. "not in apartment A" -> floor minus A) are fine
        q = re.sub(pat, " ", q, flags=re.I)
    if qr.op in ("sum", "diff") and (re.search(SUPER_MAX, q, re.I) or re.search(SUPER_MIN, q, re.I)):
        return True  # "largest"/"smallest" over something the rules did not pick
    return qr.op in ("sum", "diff") and bool(OPERATOR_HINT.search(q))


# --- what the question CALLS a numbered room ("room 2.23 ('Sauna')", "the küche, room 3.09") -------------------
# Q red team: a real room number with the wrong name was answered at 0.99 (the checks verified the number, never
# that it is the room the user means). The name is compared with the drawing's label; a mismatch lowers confidence.
_ROOM_LEAD = r"(?:rooms?|raum|zimmer|pi[èe]ces?|local[ei]?|stanza|vano|kamer|ruimte|rum(?:met)?|no\.?|nr\.?|n°|number|nummer)"
_GENERIC_NAME = re.compile(r"^(?:the|a|an|this|that|der|die|das|le|la|les|l'|il|lo|i|gli|de|het|of|room|rooms|space|"
                           r"area|floor|net|in|m²|m2|sq\.?\s*m|square\s+met(?:re|er)s?|ft²|ft2|sq\.?\s*ft|square\s+f(?:ee|oo)t)$", re.I)
# a bedroom in the Swiss drawings is usually just "Zimmer"/"Pièce"/"Stanza"; a hall is a corridor or a "Halle"
_NAME_ALIASES = {"bedroom": ["room"], "room": ["bedroom"], "corridor": ["Halle", "Entrée", "Eingang", "Vorplatz"],
                 "living": ["dining"], "dining": ["living"]}


def _concepts_of(text: str) -> set[str]:
    return {c for c, (words, _) in CONCEPTS.items() if _find_words(words, text)}


def _label_concepts(label: str) -> set[str]:
    parts = [p.strip().lower() for p in re.split(r"[/,]", label) if p.strip()] + [label.strip().lower()]
    out = {c for c, (_, labs) in CONCEPTS.items() if any(l.lower() in parts for l in labs)}
    out |= {c for c, (words, _) in CONCEPTS.items() if any(_find_words(words, p) for p in parts)}
    return out


def asked_room_names(question: str, qr: Query, vocab: list[str]) -> dict[str, str]:
    """{room number: the name the question gives it}, only for names that are quoted, in parentheses right after the
    number, or a known room word right before it ("the kitchen, room 3.16"). Unknown unquoted words are ignored."""
    q = _norm(question)
    ql = q.lower()
    known_names = sorted({v.lower() for v in vocab if v}, key=len, reverse=True)
    out: dict[str, str] = {}
    for t in qr.terms:
        if t.kind != "area_room" or not isinstance(t.arg, str):
            continue
        n = t.arg
        i = q.find(n, max(t.pos - 1, 0))
        if i < 0:
            i = q.find(n)
        if i < 0:
            continue
        after = q[i + len(n):i + len(n) + 60]
        m = re.match(r"\s*[(\[]\s*([^)\]]{1,50}?)\s*[)\]]", after) or \
            re.match(r"\s*[,:\-–]?\s*[%s]([^%s]{1,50})[%s]" % (QUOTES, QUOTES, QUOTES), after)
        cand = None
        if m:
            c = m.group(1).strip().strip(QUOTES).strip()
            quoted = bool(re.match(r"\s*[(\[]?\s*[%s]" % QUOTES, after)) or not m.group(0).lstrip().startswith(("(", "["))
            if c and not re.fullmatch(r"[\d.,\s%²]+|(?:in\s+)?(?:m²|m2|sq\.?\s*m|ft²|ft2|sq\.?\s*ft|square\s+\w+)", c, re.I) \
                    and not _GENERIC_NAME.match(c) and (quoted or c.lower() in known_names or _concepts_of(c)):
                cand = c
        if cand is None:
            before = ql[max(0, i - 50):i]
            before = re.sub(r"[\s,:(\-–]*(?:(?<![\w])" + _ROOM_LEAD + r")?[\s.:#]*$", "", before)
            for name in known_names:
                if re.search(r"(?<![\w])" + re.escape(name) + r"$", before):
                    cand = name
                    break
            if cand is None:
                for c, (words, _) in CONCEPTS.items():
                    for w in words:
                        mm = re.search(r"(?<![\w])(" + w + r")$", before, re.I)
                        if mm:
                            cand = mm.group(1)
                            break
                    if cand:
                        break
        if cand:
            out[n] = cand
    return out


def name_fits(label: str | None, asked: str) -> bool:
    """Does the drawing's label fit the name the question uses (same word, a translation, or a known alias)?"""
    if not label:
        return False
    a, l = asked.strip().lower(), label.strip().lower()
    fold = lambda s: unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()  # noqa: E731
    if a == l or fold(a) == fold(l):
        return True
    parts = [p.strip() for p in re.split(r"[/,]", l) if p.strip()]
    if any(fold(a) == fold(p) or (len(a) >= 4 and (fold(a) in fold(p) or fold(p) in fold(a))) for p in parts):
        return True
    ca, cl = _concepts_of(asked) | _label_concepts(asked), _label_concepts(label)
    if ca & cl:
        return True
    for c in ca:
        for alias in _NAME_ALIASES.get(c, []):
            if alias in cl or alias.lower() in parts:
                return True
    return False


# properties a DXF floor plan does not carry: answering them from room/door geometry is a false answer
ATTR_W = re.compile(r"\bfire\b|feuer|\bincendi|\bbrand(?:schutz|widerstand)|u-?value|u-?wert|valeur\s+u|\bmaterial|"
                    r"mat[ée]ria[lu]|werkstoff|\bheight\b|\bh[öo]he\b|hauteur|altezza|ceiling|decke|plafond|soffitto|"
                    r"thickness|\bdicke\b|[ée]paisseur|spessore|\bowner|\bowns?\b|eigent[üu]mer|propri[ée]taire|"
                    r"\bwho\b|\bwer\b|\bqui\b|\bchi\b|\bbuilt\b|\byear\b|\bbaujahr|\bcolou?r|\bfarbe|couleur|colore|"
                    r"\bbrand\b|manufactur|hersteller|fabricant|\brent\b|\bmiete\b|\bloyer\b|insulation|d[äa]mmung|"
                    r"isolation|temperature|acoustic|schall|\bvolume\b|\bvolumen\b|\bweight\b|gewicht|\bpoids\b|"
                    r"\bwidth\s+of\s+(?:the\s+)?(?:door|window)|\bopening\s+direction|\bswing\b|\bhinge|"
                    r"how\s+(?:tall|high)\b|\btall\b|\bfinish(?:es|ing)?\b|flooring|floor\s+covering|bodenbelag|"
                    r"rev[êe]tement|rivestimento", re.I)
