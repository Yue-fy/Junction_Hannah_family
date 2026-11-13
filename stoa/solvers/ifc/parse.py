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
    "storey": ("IfcBuildingStorey",),
}

# multilingual stems (matched at word starts on accent-folded lowercase text)
_LEX: list[tuple[str, tuple[str, ...]]] = [
    ("sanitary", ("sanitary fixture", "sanitary terminal", "sanitarobjekt", "sanitaerobjekt", "aparatos sanitario",
                  "aparato sanitario", "sanitair", "sanitet", "sanitar", "toilets and", "wc and")),
    ("light", ("light fixture", "lighting fixture", "luminaire", "leuchte", "luminaria", "lamp", "armatur",
               "verlichtingsarmatu", "valgusti", "oprawy oswietl", "corpuri de iluminat")),
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

_COUNT = ("how many", "number of", "count of", "wie viele", "wieviele", "anzahl", "numero de", "cuantos",
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
_NET = ("net", "netto", "util", "neto", "nett")
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
    if metric == "area" and kind is None and not side:
        kind = "space"
    if side and kind is None:
        kind = "wall"
    # "wie groß" folds to "wie gross" (= how big), which is not a gross quantity
    tg = re.sub(r"\b(wie|so|how|wieviel|zu) gross", " ", t)
    gross = bool(re.search(r"\b(gross|brutto|bruto|construida)\b", tg))
    it = Intent(metric=metric, kind=kind, names=names, side_area=side,
                total=_has(t, _TOTAL) or (metric != "count" and len(names) <= 1),
                net=not gross, gross=gross, asked_unit=asked_unit)
    if _has(t, _MODEL) and not _has(t, ("floor plan", "grundriss", "plattegrond", "plantegning", "plaan")):
        it.scope = "model"
    elif metric == "area" and kind == "space" and len(names) >= 2 and not it.total:
        it.scope = "room"
    elif _has(t, _PLAN) or names:
        it.scope = "storey" if metric != "count" or not _has(t, _MODEL) else "model"
    return it
