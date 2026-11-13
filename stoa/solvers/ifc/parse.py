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
    "pipe_accessory": ("IfcPipeAccessory",), "duct_accessory": ("IfcDuctAccessory",),
    "meter": ("IfcFlowMeter", "IfcFlowInstrument", "IfcSensor"), "junction_box": ("IfcJunctionBox",),
    "alarm": ("IfcAlarm",), "appliance": ("IfcElectricAppliance",),
    "cable_fitting": ("IfcCableCarrierFitting", "IfcCableFitting"),
    "storey": ("IfcBuildingStorey",),
}

# When a kind's own classes are empty in a model: IFC2X3 has no IfcPipeAccessory/IfcDuctAccessory (Revit exports
# them as flow controllers typed as valves / dampers / terminal boxes), roofs are often slabs typed ROOF.
FALLBACK_CLASSES: dict[str, tuple[str, ...]] = {
    "pipe_accessory": ("IfcValve",), "duct_accessory": ("IfcDamper", "IfcAirTerminalBox"),
}
# Words to look for in proxy/generic element names when a kind has no elements of its classes at all
# ("Lighting Switches:Three Way" is an IfcBuildingElementProxy in Revit exports without an MEP mapping).
NAME_FALLBACK: dict[str, tuple[str, ...]] = {
    "switch": ("switch", "schalter", "schakelaar"), "outlet": ("receptacle", "outlet", "socket", "steckdose"),
    "sanitary": ("toilet", "urinal", "sink", "lavatory", "basin", "wc"), "light": ("light", "lamp", "luminaire"),
    "window": ("window", "fenster", "raam"), "door": ("door", "tuer", "deur"), "meter": ("meter", "sensor"),
    "alarm": ("alarm", "detector", "melder"), "pump": ("pump",), "valve": ("valve",),
}

# material filter ("concrete used in slabs", "steel beams"): family -> stems matched in material/type/element names
MATERIALS: dict[str, tuple[str, ...]] = {
    "concrete": ("concrete", "beton", "betong", "hormigon", "calcestruzzo", "betoni", "reinforced c", "c20/", "c25/",
                 "c30/", "c35/", "c40/", "c45/"),
    "steel": ("steel", "staal", "stalen", "stahl", "acier", "acero", "acciaio", "teras", "s235", "s275", "s355"),
    "timber": ("timber", "wood", "hout", "holz", "bois", "madera", "legno", "naaldhout", "multiplex", "glulam"),
    "insulation": ("insulation", "isolatie", "isolier", "daemm", "dammung", "isolation", "aislamiento", "isolamento",
                   "eriste", "mineral wool", "rigid insulation"),
    "brick": ("brick", "baksteen", "ziegel", "brique", "ladrillo", "mattone", "tiili", "kalkzandsteen",
              "kalksandstein", "masonry", "metselwerk", "mauerwerk", "cmu"),
    "gypsum": ("gypsum", "gips", "gyproc", "plaster", "platre", "yeso", "drywall"),
    "glass": ("glass", "glas", "verre", "vidrio", "vetro", "lasi"),
    "aluminium": ("aluminium", "aluminum"),
}
_STEEL_PROFILE = re.compile(r"(?<![a-z])(hea|heb|hem|ipe|upn|unp|shs|rhs|chs)[ _-]?\d")


def material_match(family: str, texts: list[str]) -> bool:
    """Does any of the element's material / type / name strings belong to the material family (word-start match)?"""
    t = " ".join(fold(x) for x in texts if x)
    if family == "steel" and _STEEL_PROFILE.search(t):
        return True
    return any(re.search(r"(?<![a-z])" + re.escape(st), t) for st in MATERIALS.get(family, ()))


# the question words that ask for the material filter (subset of the stems: short codes like 'hea' are not words)
_MATERIAL_Q = re.compile(r"\b(concrete|beton\w*|hormigon|calcestruzzo|steel|staal|stahl|acier|acero|acciaio|teras|"
                         r"timber|wood(en)?|hout|holz|bois|madera|legno|insulation|insulated|isolatie|isolier\w*|"
                         r"daemm\w*|dammung|brick|baksteen|ziegel|masonry|metselwerk|mauerwerk|gypsum|gips|"
                         r"plasterboard|drywall|glass|glazed|glas|aluminium|aluminum)\b")
_MATERIAL_OF = {w: fam for fam, ws in {
    "concrete": ("concrete", "beton", "hormigon", "calcestruzzo"), "steel": ("steel", "staal", "stahl", "acier",
    "acero", "acciaio", "teras"), "timber": ("timber", "wood", "hout", "holz", "bois", "madera", "legno"),
    "insulation": ("insulat", "isolatie", "isolier", "daemm", "dammung"), "brick": ("brick", "baksteen", "ziegel",
    "masonry", "metselwerk", "mauerwerk"), "gypsum": ("gypsum", "gips", "plasterboard", "drywall"),
    "glass": ("glass", "glazed", "glas"), "aluminium": ("alumin",)}.items() for w in ws}


def material_family(word: str) -> str | None:
    return next((fam for stem, fam in _MATERIAL_OF.items() if word.startswith(stem)), None)

# multilingual stems (matched at word starts on accent-folded lowercase text)
_LEX: list[tuple[str, tuple[str, ...]]] = [
    ("sanitary", ("sanitary fixture", "sanitary terminal", "sanitarobjekt", "sanitaerobjekt", "aparatos sanitario",
                  "aparato sanitario", "sanitair", "sanitet", "sanitar", "toilets and", "wc and")),
    ("light", ("light fixture", "lighting fixture", "luminaire", "leuchte", "luminaria", "lamp", "armatur",
               "verlichtingsarmatu", "valgusti", "oprawy oswietl", "corpuri de iluminat")),
    ("pipe_accessory", ("pipe accessor", "plumbing accessor", "leidingtoebehoren", "rohrzubehor")),
    ("duct_accessory", ("duct accessor", "kanaaltoebehoren", "luftkanalzubehor")),
    ("meter", ("measuring equipment", "measuring device", "measurement device", "measuring instrument", "flow meter",
               "energy meter", "water meter", "heat meter", "flowmeter", "sensor", "messgerat", "meetapparat")),
    ("junction_box", ("junction box", "aansluitdoos", "abzweigdose", "lasdoos")),
    ("cable_fitting", ("cable carrier fitting", "cable tray fitting", "conduit fitting", "cable fitting")),
    ("alarm", ("alarm", "smoke detector", "rookmelder", "brandmelder")),
    ("appliance", ("electric appliance", "electrical appliance", "appliance")),
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
_SUM = ("combined", "together", "in total", "sum of", " sum the ", " sum all ", "add up", "added up", "summiere",
        "addiere", "tel op", "suma ", "sumar", "additionne", "zusammen", "insgesamt", "samen", "totaal", "en total",
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
_NONLOADBEARING = re.compile(r"\b(non|not|nicht|niet|no|non ?-)[- ]?(load[- ]?bearing|structural|tragend\w*|dragend\w*|"
                             r"portant\w*)|\bnichttragend\w*|\bniet-?dragend\w*|\bnonstructural\b")
_ELEVATION = re.compile(r"\b(elevation|hohenkote|hoehenkote|hohe uber|peil|cota|kote|niveau|altitude|absolute height)\b")
_HEIGHT = re.compile(r"\b(height|high|hohe|hoehe|hoch|hoogte|altura|hojde|korgus|wysokosc|inaltime|hauteur|altezza|"
                     r"korkeus|hojd)\b")
# "floor area" compounds: they name the measured quantity of a ROOM, not a floor slab ("vloer", "Boden", "dæk")
_FLOOR_AREA = re.compile(r"(net(to)?[- ]?)?(floor ?area|floor ?space|vloer ?oppervlak\w*|grund ?flache|grundflaeche|"
                         r"boden ?flache|bodenflaeche|poranda ?pind|porandapind|gulvareal\w*|nettoareal\w*|"
                         r"superficie util|superficie de suelo|surface de plancher|surface utile|superficie utile|"
                         r"powierzchni\w* (netto|uzytkow\w*)|suprafata utila|lattiapinta-ala|golvarea)")
_GROSS = ("gross", "brutto", "bruto", "construida")

# operators the dataset templates never use but unseen questions do (F's hard2): average, share, threshold
_AVG = re.compile(r"\b(average|mean|avg|durchschnittlich\w*|durchschnitt\w*|mittlere\w*|gemiddeld\w*|promedio|media|"
                  r"medio|moyenne?|gennemsnit\w*|keskmi\w*|keskimaar\w*|sredni\w*|medie|genomsnitt\w*)\b")
_PER_ROOM = re.compile(r"\bper (room|space|raum|ruimte|habitacion|local|piece|pomieszczenie|huone)\b")
_SHARE = re.compile(r"%|\b(percent(age)?|per ?cent|share|proportion|fraction|anteil\w*|prozent\w*|procent\w*|"
                    r"porcentaje|percentuale|pourcentage|osuus|prosent\w*|udzia\w*|andel\w*|procentaj\w*)\b")
_THRESH = re.compile(r"\b(more|greater|larger|bigger|less|smaller|fewer|over|under|above|below|at least|at most|"
                     r"exceed\w*|surpass\w*|ueberschreit\w*|uberschreit\w*|overschrijd\w*|exced\w*|depass\w*|"
                     r"mehr|weniger|groesser|grosser|kleiner|meer|minder|groter|mas|menos|mayor|menor|plus|"
                     r"moins|piu|meno|yli|alle|wiecej|mniej|powyzej|ponizej|ueber|uber|unter|boven|onder|over)\b"
                     r"(?:\s+(?:than|als|dan|que|de|di|niz|kuin))?\s*(\d+(?:[.,]\d+)?)")
_EXCL = re.compile(r"\b(excluding|except( for)?|exclude[sd]?|without|not counting|not including|apart from|other than|"
                   r"ohne|ausser|ausgenommen|exkl\w*|abzuglich|sauf|hors|excepto|salvo|sin contar|zonder|behalve|"
                   r"uitgezonderd|exclusief|lukuun ottamatta|ilman|poza|oprocz|bez|bortsett fran|utom|uden|undtagen|"
                   r"valja arvatud|cu exceptia|fara|senza|tranne|escluso|esclusi)\b(.{0,80})")
_LOWER = ("less", "smaller", "fewer", "under", "below", "at most", "weniger", "kleiner", "minder", "menos", "menor",
          "moins", "meno", "alle", "mniej", "ponizej", "unter", "onder")


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
    material: str | None = None  # material family filter ("concrete", "steel", ...; see MATERIALS)
    attr: str | None = None  # storey attribute asked: "elevation" | "height"
    group_by: str | None = None  # "type" | "storey": answer with a breakdown (text) besides the total
    top_n: bool = False  # "which rooms are the largest" without names -> list the top rooms
    op: str | None = None  # None | sum | max | min | argmax | argmin | diff | more
    yes_no: bool = False  # "are there more X than Y?" -> "yes"/"no"
    mod: str | None = None  # operator on top of the atomic quantity: avg | share | threshold (see parse)
    threshold: tuple[str, float] | None = None  # ("gt"|"ge"|"lt"|"le", value in the asked unit)
    which: bool = False  # "which storey/room ..." -> answer with a name
    notes: list[str] = field(default_factory=list)
    question: str = ""  # the raw question (for unquoted storey mentions)

    @property
    def classes(self) -> tuple[str, ...]:
        return KIND_CLASSES.get(self.kind or "", ())


_LISTQ = re.compile(r"^\s*(what|which|list|could you|can you|please|provide|give|show|describe|summari[sz]e|break ?down|"
                    r"welche|was sind|wat zijn|welke|cuales|quels?|quelles?)\b")
_LISTW = re.compile(r"\b(are|were|with (their|the)|including|and their|breakdown|distribution|types?|list|composition|"
                    r"each|by (type|floor|level|storey|material|room|space)|describe|description|overview|summary|"
                    r"which)\b")
_SCALARQ = re.compile(r"^\s*(what is the (total|number|net|gross|sum|overall|combined|average)|how (many|much|long|large|big|"
                      r"high|tall)|what('s| is) the (area|volume|length|height|elevation|count)|"
                      r"what (is the )?(percentage|percent|share|proportion|fraction|ratio))\b")


def wants_list(question: str) -> bool:
    """A request for a listing/description ("What are the spaces on level 4, with their areas?"), whose
    answer is text, not one number. Scalar questions ("What is the total ...", "How many ...") are not."""
    t = fold(question)
    return bool(_LISTQ.search(t) and _LISTW.search(t) and not _SCALARQ.search(t))


_ORD = {"basement": -1, "ground": 0, "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
        "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12}


def storey_mention(question: str, storey_names: list[str]) -> tuple[int | None, str]:
    """Index into storey_names of an UNQUOTED storey mention ("on the 1.OG floor", "level 4", "second floor"),
    or (None, why). Names are matched as whole words (folded), numbers via the storey name's own number."""
    t = " " + fold(_QUOTED.sub(" ", question)) + " "
    hits = []
    for i, n in enumerate(storey_names):
        f = fold(n or "")
        if len(f) >= 2 and re.search(r"(?<![\w.])" + re.escape(f) + r"(?![\w])", t):
            hits.append((len(f), i))
    if hits:
        i = max(hits)[1]
        return i, f"storey '{storey_names[i]}' named in the question"
    num = None
    m = re.search(r"\b(?:level|floor|storey|story|etage|verdieping|geschoss|niveau|planta)\s*(-?\d+)\b", t) or \
        re.search(r"\b(-?\d+)(?:st|nd|rd|th|\.)?\s*(?:floor|level|storey|story|etage|verdieping)\b", t)
    if m:
        num = int(m.group(1))
    else:
        m = re.search(r"\b(" + "|".join(_ORD) + r")\s+(?:floor|level|storey|story)\b", t)
        if m:
            num = _ORD[m.group(1)]
    if num is None:
        return None, "no storey mentioned"
    lead = [i for i, n in enumerate(storey_names) if (mm := re.match(r"\s*(-?\d+)", n or "")) and int(mm.group(1)) == num]
    if len(lead) == 1:
        return lead[0], f"'{m.group(0).strip()}' -> storey '{storey_names[lead[0]]}' (its number)"
    word = {v: k for k, v in _ORD.items()}.get(num)
    named = [i for i, n in enumerate(storey_names) if word and re.search(r"\b" + word + r"\b", fold(n or ""))]
    if len(named) == 1:
        return named[0], f"'{m.group(0).strip()}' -> storey '{storey_names[named[0]]}' (ordinal word)"
    anyn = [i for i, n in enumerate(storey_names) if re.search(r"(?<![\d.])0*" + str(abs(num)) + r"(?![\d])", n or "")]
    if len(anyn) == 1:
        return anyn[0], f"'{m.group(0).strip()}' -> storey '{storey_names[anyn[0]]}' (number in its name)"
    return None, f"'{m.group(0).strip()}' matches no single storey"


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
    # drop the quoted spans, not every occurrence of their text: storey '1' must not eat the 1 of "13 m²"
    text = _QUOTED.sub(" ", question)  # room/storey names must not trigger the lexicon ("Bathroom", "Stair hall")
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
    # "How many feet of wall ...", "how many square metres ..." ask for a quantity in that unit, not a count
    if metric == "count" and re.search(r"\b(how many|wie viele|hoeveel|cuant\w+|combien|ile|kuinka monta)\s+"
                                       r"(square |cubic |sq\.? |running |linear |lineal )?(feet|foot|ft|metres|meters|"
                                       r"meter|metern|metros|m|m2|m3|yards)\b", t):
        u = re.search(r"(square|cubic|sq)", t)
        metric = "area" if (u and u.group(1) != "cubic") else "volume" if u else "length"
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
    if _NONLOADBEARING.search(t):
        it.filters["LoadBearing"] = False
    elif _LOADBEARING.search(t):
        it.filters["LoadBearing"] = True
    mm = _MATERIAL_Q.search(t)
    if mm and kind not in (None, "space", "storey") and metric in ("count", "area", "volume", "length"):
        it.material = material_family(mm.group(1))
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
    # operators on top of the atomic quantity (checked after op so they can override a mis-read "more than N")
    mt = _THRESH.search(t)
    if mt and (re.search(r"\b(how many|wie viele|hoeveel|cuant\w+|combien|quant\w|ile|kuinka monta|hur manga|"
                         r"hvor mange|mitu|cate)\b", t) and (metric in ("area", "volume", "length") or
                                                              _FLOOR_AREA.search(t) or _has(t, _AREA))):
        w = mt.group(1)
        it.threshold = ("lt" if w in _LOWER else "gt", float(mt.group(2).replace(",", ".")))
        if w in ("at least",):
            it.threshold = ("ge", it.threshold[1])
        elif w in ("at most",):
            it.threshold = ("le", it.threshold[1])
        it.mod, it.op, it.yes_no = "threshold", None, False
        it.metric = "area" if (metric in ("count", "text", "area") and (_FLOOR_AREA.search(t) or _has(t, _AREA))) else metric
        if it.kind in (None, "slab", "storey"):
            it.kind = "space"
    elif _SHARE.search(t) and metric != "text" or (_SHARE.search(t) and metric == "text" and kind):
        it.mod, it.op = "share", None
        if metric == "text":
            it.metric = "area" if _has(t, _AREA) else "count"
    elif _AVG.search(t) or (metric != "count" and _PER_ROOM.search(t)):
        it.mod = "avg"
        if it.op in ("sum", "max", "min"):
            it.op = None
    it.which = bool(which)
    mx = _EXCL.search(t)
    if mx:  # "... excluding external walls" / "doors and windows, not counting windows"
        clause = mx.group(mx.lastindex)
        done = False
        for rx, prop in ((_EXTERNAL, "IsExternal"), (_INTERNAL, "IsExternal"), (_LOADBEARING, "LoadBearing")):
            if rx.search(clause):
                want = (rx is _INTERNAL) if prop == "IsExternal" else False
                it.filters[prop] = want
                done = True
                break
        if not done:
            ex_kinds = [h[2] for h in _kind_hits(clause) if h[2] in it.kinds and len(it.kinds) > 1]
            if ex_kinds:
                it.kinds = [k for k in it.kinds if k not in ex_kinds]
                it.kind = it.kinds[0]
                done = True
        it.notes.append(("exclusion applied: " if done else "exclusion NOT applied: ") + mx.group(0).strip()[:60])
    if which and it.kind == "storey":  # "Which storey has more doors, 'A' or 'B'?" -> compare storeys by doors
        hs = [h[2] for h in _kind_hits(t) if h[2] != "storey"]
        if hs:
            it.kind, it.kinds = hs[0], [hs[0]]
            it.attr = None
            if it.metric in ("text", "length") and not (_has(t, _AREA) or _has(t, _VOLUME)):
                metric = it.metric = "count"
            it.op = "argmin" if re.search(r"\b(fewer|less|least|fewest|weniger|minder|menos|moins|meno|mniej|vahem)\b", t) \
                else "argmax"
            it.yes_no = False
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
