"""Multilingual question parser for IFC questions -> Intent (what to measure, on what, where).

Deliberately template-free: it looks for (1) a metric word (count / area / volume / length), (2) an element
kind from a multilingual lexicon, (3) quoted names, which the solver resolves against the model's storeys,
rooms and project name. Languages seen in the data: EN, DE, NL, ES, DA, ET, PL, RO (+ FR, IT, FI, SV for
robustness). Unknown phrasings degrade gracefully: the solver records what it assumed.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# kind -> IFC classes. Order matters for the lexicon scan (more specific first).
KIND_CLASSES: dict[str, tuple[str, ...]] = {
    "space": ("IfcSpace",),
    "door": ("IfcDoor",),
    "window": ("IfcWindow",),
    "curtain_wall": ("IfcCurtainWall",),
    "wall": ("IfcWall", "IfcWallStandardCase", "IfcWallElementedCase"),
    "stair": ("IfcStair",),
    "stair_flight": ("IfcStairFlight",),
    "ramp": ("IfcRamp",),
    "column": ("IfcColumn", "IfcColumnStandardCase"),
    "beam": ("IfcBeam", "IfcBeamStandardCase"),
    "slab": ("IfcSlab", "IfcSlabStandardCase", "IfcSlabElementedCase"),
    "roof": ("IfcRoof",),
    "covering": ("IfcCovering",),
    "railing": ("IfcRailing",),
    "furniture": ("IfcFurnishingElement", "IfcFurniture"),
    "sanitary": ("IfcSanitaryTerminal",),  # IFC2X3: IfcFlowTerminal typed IfcSanitaryTerminalType (eff_cls)
    "light": ("IfcLightFixture",),
    "plate": ("IfcPlate",),
    "member": ("IfcMember",),
    "footing": ("IfcFooting",),
    "pile": ("IfcPile",),
    "opening": ("IfcOpeningElement",),
    # MEP (IFC2X3 generic flow classes resolve to these through their type object, see index.effective_class)
    "duct_fitting": ("IfcDuctFitting",), "duct": ("IfcDuctSegment",), "pipe_fitting": ("IfcPipeFitting",),
    "pipe": ("IfcPipeSegment",), "air_terminal": ("IfcAirTerminal",), "outlet": ("IfcOutlet",),
    "switch": ("IfcSwitchingDevice",), "valve": ("IfcValve",), "damper": ("IfcDamper",), "pump": ("IfcPump",),
    "cable": ("IfcCableSegment", "IfcCableCarrierSegment"), "fire_terminal": ("IfcFireSuppressionTerminal",),
    "storey": ("IfcBuildingStorey",),
}

# multilingual stems (matched at word starts on accent-folded lowercase text)
_LEX: list[tuple[str, tuple[str, ...]]] = [
    ("sanitary", ("sanitary fixture", "sanitary terminal", "sanitarobjekt", "sanitaerobjekt", "aparatos sanitario",
                  "aparato sanitario", "sanitair", "sanitet", "sanitar", "toilets and", "wc and")),
    ("light", ("light fixture", "lighting fixture", "luminaire", "leuchte", "luminaria", "lamp", "armatur",
               "verlichtingsarmatu", "valgusti", "oprawy oswietl", "corpuri de iluminat")),
    ("duct_fitting", ("duct fitting", "luftkanalformteil", "formstuck", "kanaalhulpstuk")),
    ("pipe_fitting", ("pipe fitting", "rohrformteil", "fitting")),
    ("air_terminal", ("air terminal", "diffuser", "grille", "luftauslass", "luchtrooster")),
    ("fire_terminal", ("sprinkler", "fire suppression")),
    ("duct", ("duct", "luftkanal", "luchtkanaal")),
    ("pipe", ("pipe", "rohr", "leiding", "tuberia")),
    ("outlet", ("outlet", "receptacle", "socket", "steckdose", "wandcontactdoos")),
    ("switch", ("switch", "schalter", "schakelaar")),
    ("valve", ("valve", "ventil", "klep", "valvula")),
    ("damper", ("damper", "klappe")),
    ("pump", ("pump", "pumpe", "pomp")),
    ("cable", ("cable", "kabel", "cable tray")),
    ("curtain_wall", ("curtain wall", "vorhangfassade", "muro cortina", "gardinvaeg", "vliesgevel")),
    ("stair_flight", ("stair flight", "treppenlauf", "tramo de escalera", "trappelob")),
    ("space", ("room", "space", "raum", "raeume", "rume", "local", "rum", "ruimte", "ruum", "pomieszcz",
               "camer", "incaper", "stanz", "piece", "salle", "huone", "tila", "rom ")),
    ("door", ("door", "tur", "tuer", "puerta", "dor", "doer", "deur", "uks", "ust", "drzwi", "usi", "porte",
              "porta", "ovi", "ovet", "dorr")),
    ("window", ("window", "fenster", "ventana", "vindu", "raam", "ramen", "aken", "akna", "okien", "okn",
                "ferestr", "fenetre", "finestr", "ikkun", "fonster")),
    ("wall", ("wall", "wand", "waend", "wande", "muro", "muros", "vaeg", "vag", "seina", "sein", "scian",
              "sciana", "perete", "pereti", "mur", "murs", "paret", "parete", "sein", "seinä", "vagg")),
    ("stair", ("stair", "trepp", "escalera", "trappe", "trap", "scari", "scara", "schod", "escalier", "scal",
               "porras", "portaat", "trapp")),
    ("ramp", ("ramp", "rampa", "rampe")),
    ("column", ("column", "stutz", "stuetz", "saule", "saeule", "pilar", "columna", "sojle", "soejle", "kolom",
                "post", "stalp", "slup", "poteau", "pilastr", "colonn", "pilari", "pelar")),
    ("beam", ("beam", "trager", "traeger", "viga", "bjaelk", "bjalk", "balk", "tala", "grinz", "grinda",
              "belk", "belek", "poutre", "trav", "palkki", "balk")),
    ("slab", ("slab", "floor slab", "decke", "bodenplatte", "losa", "forjado", "daek", "dæk", "plade", "vloer",
              "plaat", "plaad", "plyt", "placa", "placi", "dalle", "solai", "laatta", "bjalklag", "platte")),
    ("roof", ("roof", "dach", "cubierta", "tejado", "tag ", "dak", "katus", "dach", "acoperis", "toit", "tetto")),
    ("covering", ("covering", "belag", "revestimiento", "bekleding")),
    ("railing", ("railing", "gelander", "gelaender", "barandilla", "rackvaerk", "reling", "balustrad")),
    ("furniture", ("furniture", "furnishing", "mobel", "moebel", "mueble", "mobiliar", "mobler", "meubel",
                   "moobel", "mebl", "mobil")),
    ("footing", ("footing", "foundation", "fundament", "cimentac", "fundering")),
    ("pile", ("pile", "pfahl", "pilote", "pael", "paal")),
    ("plate", ("plate", "platte", "placa")),
    ("member", ("member", "stab", "profil")),
    ("storey", ("storey", "storeys", "floors", "levels", "geschosse", "plantas", "etager", "verdiepingen",
                "korrus", "kondygnac", "niveluri")),
]

_COUNT = ("how many", "number of", "count of", " count the ", " count all ", " count ", "tally", "zahle", "zaehle",
          "tel de ", "tel alle", "cuenta ", "cuente ", "tael ", "loenda", "policz", "numarati", "comptez", "conta ", "wie viele", "wieviele", "anzahl", "numero de", "cuantos",
          "cuantas", "el numero", "hvor mange", "antal", "hoeveel", "aantal", "mitu", "ile ", "numarul",
          "combien", "nombre de", "quanti", "quante", "numero di", "kuinka monta", "montako", "hur manga")
_AREA = ("area", "flache", "flaeche", "superficie", "areal", "oppervlak", "pind", "powierzchn", "suprafat",
         "surface", "pinta-ala", "yta", "m2", "m²", "sq m", "ft2", "ft²", "square")
_SIDE = ("side area", "seitenflache", "seitenflaeche", "sideareal", "zijoppervlak", "superficie lateral",
         "kuljepind", "wall area", "facade area")
_VOLUME = ("volume", "volumen", "rumfang", "maht", "objetosc", "m3", "m³", "cubic", "tilavuus", "volym")
_LENGTH = ("length", "lang ", "lange", "laenge", "longitud", "laengde", "lengte", "pikkus", "dlugosc",
           "lungime", "longueur", "lunghezza", "pituus", "langd", "metres", "meters", "metern", "meter",
           "metros", "metrow", "metri")
_TOTAL = ("total", "all ", "gesamt", "alle", "todos", "todas", "samlede", "totale", "kokku", "koigi",
          "wszystkich", "laczna", "toate", "tous", "toutes", "tutti", "kaikki", "zusammen", "summe")
_MODEL = ("in the model", "the model", "modell", "modelo", "modellen", "het model", "mudel", "modelu",
          "modelul", "modele", "modello", "malli")
_PLAN = ("floor plan", "plan of", "grundriss", "plano", "plantegning", "plattegrond", "plaan", "rzuc",
         "planul", "plan de", "pianta", "pohjapiirro", "on the level", "on level", "storey", "geschoss",
         "planta", "etage", "verdieping", "korrus", "kondygnac", "nivel")
_MAX = ("largest", "biggest", "greatest", "maximum", "max ", "most ", "bigger", "larger", "greater", "grosser",
        "groesser", "groter", "storre", "suurem", "wiekszy", "wieksze", "mai mare", "mas grande", "piu grand", "grosste", "groesste", "grosster", "groesster",
        "grootste", "mayor ", "mas grande", "storste", "suurim", "najwieksz", "cel mai mare", "plus grand",
        "piu grande", "suurin", "storsta")
_MIN = ("smallest", "least", "minimum", "min ", "smaller", "kleiner", "kleiner", "mindre", "vaiksem", "mniejsz",
        "mai mic", "mas pequeno", "plus petit", "kleinste", "menor ", "mas pequen", "mindste", "vaikseim",
        "najmniejsz", "cel mai mic", "plus petit", "piu piccol", "pienin", "minsta")
_WHICH = ("which", "what room", "welche", "welcher", "welches", "welke", "cual ", "hvilk", "milline", "ktory",
          "ktora", "care ", "quel", "quale", "mika", "vilk")
_SUM = ("combined", "together", "in total", "sum of", "zusammen", "insgesamt", "samen", "totaal", "en total",
        "juntas", "juntos", "tilsammen", "i alt", "kokku", "lacznie", "razem", "in total", "au total", "in totale",
        "yhteensa", "sammanlagt", " plus ", " + ")
_DIFF = ("difference", "minus", "larger than", "bigger than", "smaller than", "more than", "fewer than",
         "less than", "unterschied", "differenz", "mehr als", "verschil", "meer dan", "diferencia", "mas que",
         "forskel", "flere end", "erinevus", "roznica", "wiecej niz", "diferenta", "difference", "plus que",
         "differenza", "piu di")
_CONJ = re.compile(r"\b(and|und|en|y|e|og|ja|i|si|et|och|plus|or|oder|of|o|eller|sau|ou)\b|[+&,/]")
_NET = ("net", "netto", "util", "neto", "nett")
_EXTERNAL = re.compile(r"\b(external|exterior|outer|outside|facade|aussen\w*|ausseren|buiten\w*|exterior\w*|ydre|udvendig\w*|"
                       r"valis\w*|zewnetrzn\w*|exterieur\w*|estern\w*|ulko\w*|yttre)\b")
_INTERNAL = re.compile(r"\b(internal|interior|inner|inside|innen\w*|inneren|binnen\w*|interior\w*|indvendig\w*|indre|"
                       r"sise\w*|wewnetrzn\w*|interieur\w*|intern\w*|sisa\w*|inre)\b")
_LOADBEARING = re.compile(r"\b(load[- ]?bearing|structural|tragend\w*|dragend\w*|portant\w*|baerende|kandev\w*|nosn\w*|"
                          r"kantav\w*|barande)\b")
_ELEVATION = re.compile(r"\b(elevation|hohenkote|hoehenkote|hohe uber|peil|cota|kote|niveau|altitude|absolute height)\b")
_HEIGHT = re.compile(r"\b(height|high|hohe|hoehe|hoch|hoogte|altura|hojde|korgus|wysokosc|inaltime|hauteur|altezza|"
                     r"korkeus|hojd)\b")
# "floor area" compounds: they name the measured quantity of a ROOM, not a floor slab ("vloer", "Boden", "dæk")
_FLOOR_AREA = re.compile(r"(net(to)?[- ]?)?(floor ?area|floor ?space|vloer ?oppervlak\w*|grund ?flache|grundflaeche|"
                         r"boden ?flache|bodenflaeche|poranda ?pind|porandapind|gulvareal\w*|nettoareal\w*|"
                         r"superficie util|superficie de suelo|surface de plancher|surface utile|superficie utile|"
                         r"powierzchni\w* (netto|uzytkow\w*)|suprafata utila|lattiapinta-ala|golvarea)")
_GROSS = ("gross", "brutto", "bruto", "construida")

_QUOTED = re.compile(r"«([^»]{1,120})»|„([^“”\"]{1,120})[“”\"]|“([^”]{1,120})”|‘([^’]{1,120})’|(?<!\w)'(.{1,120}?)'(?!\w)|\"([^\"]{1,120})\"")


def fold(s: str) -> str:
    """Lowercase, strip accents, map ß/æ/ø/ł, squash spaces."""
    s = s.lower().replace("ß", "ss").replace("æ", "ae").replace("ø", "o").replace("ł", "l").replace("đ", "d")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class Intent:
    metric: str  # count | area | volume | length | text
    kind: str | None  # key of KIND_CLASSES (target elements), or None
    names: list[str] = field(default_factory=list)  # quoted strings, in order
    scope: str = "auto"  # storey | model | room | auto (decided by name resolution)
    side_area: bool = False  # wall side area rather than floor area
    total: bool = False  # aggregate over several elements
    net: bool = True
    gross: bool = False
    asked_unit: str | None = None  # unit the question asks for (m2, ft2, m3, m, ft, ...)
    kinds: list[str] = field(default_factory=list)  # coordinated kinds ("doors and windows") -> summed
    filters: dict[str, bool] = field(default_factory=dict)  # {"IsExternal": True, "LoadBearing": True}
    attr: str | None = None  # storey attribute asked: "elevation" | "height"
    group_by: str | None = None  # "type" | "storey": answer with a breakdown (text) besides the total
    top_n: bool = False  # "which rooms are the largest" without names -> list the top rooms
    op: str | None = None  # None | sum | max | min | argmax | argmin | diff | more
    yes_no: bool = False  # "are there more X than Y?" -> "yes"/"no"
    notes: list[str] = field(default_factory=list)

    @property
    def classes(self) -> tuple[str, ...]:
        return KIND_CLASSES.get(self.kind or "", ())


def quoted_names(question: str) -> list[str]:
    out = []
    for m in _QUOTED.finditer(question):
        g = next((x for x in m.groups() if x), None)
        if g:
            out.append(g.strip())
    return out


def _has(text: str, words) -> bool:
    return any(w in text for w in words)


def _kind_hits(text: str) -> list[tuple[int, int, str]]:
    """All (start, end, kind) lexicon hits, first hit per kind, sorted by position."""
    hits: dict[str, tuple[int, int, int]] = {}
    for prio, (kind, stems) in enumerate(_LEX):
        for st in stems:
            m = re.search(r"(?<![a-z])" + re.escape(st), text)
            if m:
                end = m.start() + len(re.match(r"[\w-]*", text[m.start():]).group(0) or st)
                key = (m.start(), prio, end)
                if kind not in hits or key < hits[kind]:
                    hits[kind] = key
    return sorted(((v[0], v[2], k) for k, v in hits.items()), key=lambda x: (x[0], x[1]))


def coordinated_kinds(text: str) -> list[str]:
    """['door', 'window'] for "doors and windows", ['door'] for "doors on storey X"."""
    hits = [h for h in _kind_hits(text) if h[2] != "storey"] or _kind_hits(text)
    if not hits:
        return []
    out = [hits[0][2]]
    prev_end = hits[0][1]
    for start, end, kind in hits[1:]:
        gap = text[prev_end:start]
        if len(gap) <= 25 and _CONJ.search(gap) and kind not in out:
            out.append(kind)
            prev_end = end
        elif start - prev_end > 25:
            break
    return out


def _find_kind(text: str) -> str | None:
    """Earliest-occurring lexicon stem wins (the counted noun comes first in all our languages), ties broken
    by lexicon order (specific before generic)."""
    best = None
    for prio, (kind, stems) in enumerate(_LEX):
        for st in stems:
            for m in re.finditer(r"(?<![a-z])" + re.escape(st), text):
                key = (m.start(), prio)
                if best is None or key < best[0]:
                    best = (key, kind)
                break
    return best[1] if best else None


def parse(question: str) -> Intent:
    names = quoted_names(question)
    text = question
    for n in names:  # don't let room/storey names trigger the lexicon ("Bathroom", "Stair hall")
        text = text.replace(n, " ")
    t = " " + fold(text) + " "
    asked_unit = None
    if re.search(r"ft2|ft²|sq\.? ?ft|square f", t):
        asked_unit = "ft2"
    elif re.search(r"m2|m²|sq\.? ?m|square met", t):
        asked_unit = "m2"
    elif re.search(r"m3|m³|cubic", t):
        asked_unit = "m3"
    elif re.search(r"\b(feet|ft)\b", t):
        asked_unit = "ft"
    elif re.search(r"\b(metres|meters|metern|meter|metros|metrow|metri|m)\b", t):
        asked_unit = "m"

    if _has(t, _SIDE):
        metric = "area"
    elif _has(t, _VOLUME) or asked_unit == "m3":
        metric = "volume"
    elif _has(t, _AREA) or asked_unit in ("m2", "ft2"):
        metric = "area"
    elif _has(t, _COUNT):
        metric = "count"
    elif _has(t, _LENGTH) or asked_unit in ("m", "ft"):
        metric = "length"
    else:
        metric = "text"
    # "how long are all walls" style length questions also contain count-ish words; length wins when no count
    if metric == "count" and _has(t, ("length", "how long", "wie lang", "longitud", "laengde", "lengte")):
        metric = "length"

    side = _has(t, _SIDE)
    floor_area = bool(_FLOOR_AREA.search(t)) and not side
    kind = _find_kind(_FLOOR_AREA.sub(" ", t) if floor_area else t)
    if floor_area and kind in (None, "slab", "storey"):
        kind = "space"
    kinds = coordinated_kinds(_FLOOR_AREA.sub(" ", t) if floor_area else t) if metric == "count" else []
    if kinds and kind in kinds and kinds[0] != kind:
        kinds = [kind] + [k for k in kinds if k != kind]
    if metric == "area" and kind is None and not side:
        kind = "space"
    if side and kind is None:
        kind = "wall"
    # "wie groß" folds to "wie gross" (= how big), which is not a gross quantity
    tg = re.sub(r"\b(wie|so|how|wieviel|zu) gross", " ", t)
    gross = bool(re.search(r"\b(gross|brutto|bruto|construida)\b", tg))
    it = Intent(metric=metric, kind=kind, names=names, side_area=side,
                total=_has(t, _TOTAL) or (metric != "count" and len(names) <= 1),
                net=not gross, gross=gross, asked_unit=asked_unit, kinds=kinds or ([kind] if kind else []))
    if _EXTERNAL.search(t):
        it.filters["IsExternal"] = True
    elif _INTERNAL.search(t):
        it.filters["IsExternal"] = False
    if _LOADBEARING.search(t):
        it.filters["LoadBearing"] = True
    if kind == "storey" or (kind is None and names and (_ELEVATION.search(t) or _HEIGHT.search(t))):
        if _ELEVATION.search(t):
            it.metric, it.kind, it.attr = "length", "storey", "elevation"
        elif _HEIGHT.search(t) and metric != "count":
            it.metric, it.kind, it.attr = "length", "storey", "height"
    if re.search(r"\b(types?|typen|tipos?|typer|tuubid|typy|tipuri)\b", t) and not names:
        it.group_by = "type"
    if re.search(r"\b(by|per|for each|each|on each|across( all)?)\b.{0,12}\b(level|floor|storey|story|geschoss|etage)s?\b"
                 r"|\b(level|floor|storey)[- ]by[- ](level|floor|storey)\b|\bbreakdown\b.{0,20}\b(level|floor|storey)", t):
        it.group_by = "storey"
    which = _has(t, _WHICH)
    comparative_which = which and re.search(r"\b(bigger|larger|greater|smaller|grosser|groesser|kleiner|groter|"
                                            r"kleiner|storre|mindre|mayor|menor)\b", t)
    if comparative_which:
        it.op = "argmin" if re.search(r"\b(smaller|kleiner|mindre|menor)\b", t) else "argmax"
    elif _has(t, _DIFF) or re.search(r"\b(more|fewer|less|mehr|weniger|meer|minder|mas|menos|flere|faerre|wiecej|mniej|"
                                   r"mai multe|plus|moins|piu|meno)\b.{1,40}\b(than|als|dan|que|end|niz|decat|di)\b", t):
        it.op = "diff"
        it.yes_no = bool(re.match(r"\s*(are|is|do|does|gibt|sind|hay|er|zijn|kas|czy|sunt|y a)\b", t))
    elif _has(t, _MAX):
        it.op = "argmax" if which else "max"
    elif _has(t, _MIN):
        it.op = "argmin" if which else "min"
    elif _has(t, _SUM) or len(it.kinds) > 1:
        it.op = "sum"
    if it.op == "diff" and metric == "text" and len(_kind_hits(t)) >= 2:
        metric = it.metric = "count"  # "Are there more doors than windows on X?"
    if it.op == "diff" and metric == "count" and len(it.kinds) < 2:
        hs = [h[2] for h in _kind_hits(_FLOOR_AREA.sub(" ", t) if floor_area else t) if h[2] != "storey"]
        if len(hs) >= 2:
            it.kinds = hs[:2]
            it.kind = hs[0]
    if it.op in ("argmax", "argmin"):
        it.metric = "area" if metric in ("text", "area") else metric
        if not names and (kind in (None, "space")):
            it.top_n, it.kind = True, "space"
    if _has(t, _MODEL) and not _has(t, ("floor plan", "grundriss", "plattegrond", "plantegning", "plaan")):
        it.scope = "model"
    elif metric == "area" and kind == "space" and len(names) >= 2 and not it.total:
        it.scope = "room"
    elif _has(t, _PLAN) or names:
        it.scope = "storey" if metric != "count" or not _has(t, _MODEL) else "model"
    return it
