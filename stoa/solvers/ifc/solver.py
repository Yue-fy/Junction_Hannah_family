"""`ifc` solver: answer quantity questions about IFC models (and plans rendered from them) from the model.

Pipeline: parse the question (multilingual, template-free) -> find the model (.ifc itself, or the parent
model of an ifc_models plan PDF/SVG) -> resolve quoted names to storeys / rooms / the model -> compute ->
Answer with one Evidence per element (ifc_guid), trace, assumptions and cross-checks.

Definitions (measured on the TRAIN split, experiments/w1/explore_defs.py, all 100% except where noted):
- count of X on a storey's plan  = IFC elements of the class(es) of X whose spatial container (walking
  aggregation/fills) is that storey. IFC2X3 IfcFlowTerminal is classified through its type object.
- count of X in the model        = all elements of the class(es) in the file.
- room net floor area            = area of the IfcSpace body geometry projected on the floor (footprint).
- total net floor area (storey)  = sum of the footprints of the storey's spaces.
- wall/slab net volume           = sum of Qto *.NetVolume (fallback: closed-mesh volume of the geometry).
- wall length                    = sum of Qto *.Length (fallback: longest bbox side per wall).
- wall net side area             = sum of Qto *.NetSideArea (fallback: lateral mesh area / 2).
"""

from __future__ import annotations

import re
import time
from collections import Counter
from pathlib import Path

from stoa.contract import Answer, Evidence
from stoa.data import abspath, siblings, source_of
from stoa.solvers import register
from stoa.solvers.base import BaseSolver
from stoa.solvers.ifc.index import Element, IfcIndex, Storey, load_index
from stoa.solvers.ifc.index import strip_id, type_key_fn as _type_key_fn
from stoa.solvers.ifc.parse import (_MATERIAL_Q, _QUOTED as _QUOTED_RX, FALLBACK_CLASSES, KIND_CLASSES, NAME_FALLBACK, Intent, fold,
                                   material_family, material_match, parse, storey_mention, wants_list)
from stoa.solvers.ifc.resolve import match_model, match_space, match_storey, norm

# share of storey totals within 2% when computed from geometry only (no Qto), measured on train+dev
# questions with `--solver-arg qto=0` (00:30): wall volume 69%, slab volume 85%, wall length 62%, wall side 43%
GEO_HIT_RATE = {"volume": 0.75, "length": 0.62, "side": 0.43, "floor": 0.95}
FT2_PER_M2 = 10.763910416709722
FT_PER_M = 3.280839895013123
MAX_EVIDENCE = 2000
# words that signal an aggregation/comparison; if the parse found no operator, the plain value is suspect
_OPERATOR_WORD = re.compile(r"\b(exceed\w*|surpass\w*|average|mean|median|ratio|times as|percent\w*|proportion|share of|"
                            r"per (room|space|storey|floor|level|unit|apartment)|at least|at most|more than \d|"
                            r"less than \d|fewer than \d|greater than \d|smaller than \d|over \d|under \d|"
                            r"durchschnitt\w*|gemiddeld\w*|promedio|moyenne|keskimaar\w*|sredni\w*|prozent\w*|procent\w*|"
                            r"porcentaje|pourcentage|anteil)\b|%")

# quantity key suffixes, in order of preference, per (metric, kind)
_DIM_WORD = re.compile(r"\b(widths?|wide|wider|widest|narrower|narrowest|broader|taller|thicker|thinner|breite\w*|breedte\w*|largeur\w*|ancho\w*|larghezza|"
                       r"heights?|tall\w*|hoehe|hohe|hoogte\w*|hauteur\w*|altura\w*|altezza|"
                       r"thickness\w*|thick|thickest|thinnest|dicke\w*|dikte\w*|epaisseur\w*|espesor\w*|spessore\w*)\b")
_DIM_THRESHOLD = re.compile(
    r"(?P<cmp>wider|broader|taller|higher|thicker|longer|larger|bigger|greater|more|over|above|exceed\w*|at least|"
    r"minimum|narrower|smaller|thinner|shorter|lower|less|under|below|at most|breiter|hoher|hoeher|dicker|grosser|"
    r"groesser|mehr|uber|ueber|mindestens|schmaler|kleiner|dunner|duenner|weniger|breder|hoger|dikker|groter|meer|"
    r"minstens|smaller|lager|dunner|minder|plus|moins)\b[^0-9]{0,25}?(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>mm|cm|m)?\b")
_FOUNDATION_NAME = re.compile(r"(?<![a-z])(foundation|footing|fundament|fundering|fundbalk|fundatie|pad[: ]|pile|"
                              r"strip footing|grondbalk|poer)")
_GENERIC_CLASSES = {"IfcBuildingElementProxy", "IfcFlowTerminal", "IfcFlowController", "IfcFlowFitting",
                    "IfcFlowSegment", "IfcDistributionControlElement", "IfcDistributionFlowElement",
                    "IfcEnergyConversionDevice", "IfcFlowMovingDevice", "IfcFlowStorageDevice",
                    "IfcFlowTreatmentDevice", "IfcFurnishingElement", "IfcDistributionElement"}

QTO_KEYS = {
    ("volume", "net"): ("Quantities.NetVolume", ".NetVolume"),
    ("volume", "gross"): ("Quantities.GrossVolume", ".GrossVolume"),
    ("length", "net"): ("Quantities.Length", ".Length"),
    ("side", "net"): ("Quantities.NetSideArea", ".NetSideArea"),
    ("side", "gross"): ("Quantities.GrossSideArea", ".GrossSideArea"),
    ("floor", "net"): (".NetFloorArea",),
    ("floor", "gross"): (".GrossFloorArea",),
}


def model_for(path: str) -> str | None:
    """Dataset-relative .ifc behind `path` (the path itself, or the parent model of a rendered plan)."""
    if Path(path).suffix.lower() == ".ifc":
        return path
    m = siblings(path).get(".ifc")
    if m:
        return m
    # ResBIM pairs: data/ifc_models/resbim-N_plan.png <-> resbim-N_model.ifc (stoa.data.siblings misses them)
    p = Path(path)
    stem = re.sub(r"_(plan|drawing|image|render)$", "", p.stem)
    for cand in (f"{stem}_model.ifc", f"{stem}.ifc"):
        if abspath(str(p.parent / cand)).exists():
            return str(p.parent / cand)
    return None


# languages the parser has (template) vocabulary for, besides English: the dataset's ifc question languages
PARSER_LANGS = ("de", "nl", "pl", "et", "it", "ro", "fi", "fr")
_KNOWN_WORDINGS: set[str] | None = None
_AUX_LEVEL = re.compile(r"\b(roof\w*|dach\w*|dak\w*|toit\w*|tetto|katto|katus|tak|cubierta|telhado|foundation\w*|"
                        r"fundament\w*|vundament\w*|fdn|t/fdn|footing\w*|fondation\w*|fondazion\w*|cimentaci\w*|"
                        r"perustu\w*|site|terrain|gelande|maaiveld)\b")


def used_storeys(idx, sts=None) -> list:
    """Storeys people call floors: they hold a door, or rooms while not named as a roof/foundation level (the
    duplex 'Roof' holds one roof space; esplanades 'Katus' / 'Vundament', smiley 'Dach' hold no room or door).
    IFC-Bench smiley_west: 'number of levels' gold 4 = KG, EG, 1.OG, 2.OG (not 'Dach')."""
    sts = list(idx.storeys if sts is None else sts)
    out = []
    for st in sts:
        if idx.in_storey(st.guid, "IfcDoor"):
            out.append(st)
        elif idx.in_storey(st.guid, "IfcSpace") and not _AUX_LEVEL.search(fold(st.name or "")):
            out.append(st)
    return out


def _known_wording(question: str) -> bool:
    """True if the question's template (quoted names and numbers masked) is a dataset wording the rules were built
    and checked on: train, dev, hard, hard2 (never the sealed or held-out splits). Dutch and Polish ifc questions
    exist only on dev/hard models, so a train-only check sent all 152 of them through the cross-language LLM call
    (S0 05:03: ifc cost $0.002 -> $0.027 per 1k, p95 2 s) although the parser reads them 100%."""
    global _KNOWN_WORDINGS
    if _KNOWN_WORDINGS is None:
        from stoa.data import template_of
        from stoa.eval.splits import load_split

        ks: set[str] = set()
        for sp in ("train", "dev", "hard", "hard2"):
            try:
                ks |= {template_of(q.question) for q in load_split(sp)}
            except Exception:  # noqa: BLE001 - a split missing on this machine
                continue
        _KNOWN_WORDINGS = ks
    from stoa.data import template_of

    return template_of(question) in _KNOWN_WORDINGS


def _same_value(a: Answer, b: Answer) -> bool:
    """Two rule answers say the same thing (numbers within 0.5% in the same unit, or the same text)."""
    if isinstance(a.value, (int, float)) and isinstance(b.value, (int, float)):
        x, y = float(a.value), float(b.value)
        return (a.unit or "") == (b.unit or "") and abs(x - y) <= 0.005 * max(abs(x), abs(y), 1e-9)
    return str(a.value).strip().lower() == str(b.value).strip().lower()


def buildings_of(idx: IfcIndex) -> list[str | None]:
    """Distinct IfcBuilding names that own storeys (more than one = neighbours / context buildings in the model)."""
    return list(dict.fromkeys(st.building for st in idx.storeys))


def main_building(idx: IfcIndex) -> str | None:
    """The building whose storeys hold the most elements (the designed building, not context massing)."""
    by_guid = {st.guid: st.building for st in idx.storeys}
    cnt = Counter(by_guid[e.storey] for e in idx.elements.values() if e.storey in by_guid)
    return cnt.most_common(1)[0][0] if cnt else None


def own_storeys(idx: IfcIndex) -> list[Storey]:
    """The storeys a question about 'the building' ranges over: the main building's when the model has several."""
    if len(buildings_of(idx)) > 1:
        mb = main_building(idx)
        return [st for st in idx.storeys if st.building == mb]
    return list(idx.storeys)


def _level_key(name: str | None) -> str:
    """'2. Erdgeschoss' / 'Erdgeschoss' -> 'erdgeschoss' (a storey name without its running number)."""
    return re.sub(r"^\s*-?\d+\s*[.)]?\s*", "", fold(name or "")).strip()


def _ascii_drop(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower().encode("ascii", "ignore").decode())


def plan_storey(path: str, idx: IfcIndex) -> tuple[Storey | None, str]:
    """Storey shown on a rendered plan `<model>_plan-NN-<level-slug>.pdf` (slug match, NN breaks ties)."""
    m = re.search(r"_plan-(\d+)-(.+)$", Path(path).stem)
    if not m:
        return None, "not a plan file"
    nn, slug = int(m.group(1)), m.group(2)
    for key in (norm, _ascii_drop):
        hits = [s for s in idx.storeys if key(s.name) == key(slug)]
        if len(hits) == 1:
            return hits[0], f"plan slug '{slug}' = storey '{hits[0].name}'"
        if len(hits) > 1:
            ranked = sorted(hits, key=lambda s: abs(idx.storeys.index(s) - (nn - 1)))
            return ranked[0], f"plan slug '{slug}' ambiguous {[h.name for h in hits]}; plan #{nn} -> '{ranked[0].name}'"
    from rapidfuzz import fuzz

    best = max(idx.storeys, key=lambda s: fuzz.ratio(norm(slug), norm(s.name)), default=None)
    if best is not None and fuzz.ratio(norm(slug), norm(best.name)) >= 75:
        return best, f"plan slug '{slug}' ~ storey '{best.name}' (fuzzy)"
    if 0 < nn <= len(idx.storeys):
        return idx.storeys[nn - 1], f"plan #{nn} -> storey '{idx.storeys[nn - 1].name}' (by order; slug unmatched)"
    return None, f"plan slug '{slug}' unmatched"


def _qto(e: Element, keys: tuple[str, ...]) -> float | None:
    for suf in keys:
        for k, v in e.qto.items():
            if k.endswith(suf) and (k.startswith("Qto_") or "BaseQuantities" in k or suf.startswith("Quantities")):
                return v
    for suf in keys:
        for k, v in e.qto.items():
            if k.endswith(suf):
                return v
    return None


def _label_key(s: str | None) -> str:
    """'Bathroom 2' -> 'bathroom', 'TUALETTRUUM' -> 'tualettruum' (room type label without numbering)."""
    t = fold(s or "")
    t = re.sub(r"[\s\-_.]*\(?[a-z]?\d+[\w.\-]*\)?$", "", t)
    return re.sub(r"[^a-z0-9]+", "", t)


def label_group(idx: IfcIndex, label: str, storey_guid: str | None = None) -> list[Element]:
    """All spaces whose type label (LongName, or Name, without numbering) equals `label`."""
    key = _label_key(label)
    if len(key) < 2:
        return []
    out = []
    for e in idx.elements.values():
        if e.cls != "IfcSpace" or (storey_guid and e.storey != storey_guid):
            continue
        if key in (_label_key(e.long_name), _label_key(e.name)):
            out.append(e)
    return out


_STOP = {"floor", "floors", "plan", "plans", "level", "levels", "storey", "storeys", "area", "total", "model",
         "building", "drawing", "sheet", "room", "rooms", "space", "spaces", "many", "there", "shown", "number",
         "what", "which", "how", "the", "are", "this", "that", "with", "all", "net", "gross"}


def _singulars(word: str) -> list[str]:
    out = [word]
    for suf in ("ies", "es", "s", "en", "er", "e", "n", "t"):
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            out.append(word[: -len(suf)] + ("y" if suf == "ies" else ""))
    return out


def vocabulary_group(idx: IfcIndex, question: str, names: list[str]) -> tuple[str | None, list[Element]]:
    """A bare room-type noun in the question ('How many bathrooms are on Level 1?') matched against the model's
    own room labels. Returns (label, spaces) or (None, [])."""
    text = question
    for n in names:
        text = text.replace(n, " ")
    labels: dict[str, list[Element]] = {}
    for e in idx.elements.values():
        if e.cls == "IfcSpace":
            for k in {_label_key(e.long_name), _label_key(e.name)}:
                if len(k) >= 3 and not k.isdigit():
                    labels.setdefault(k, []).append(e)
    for w in re.findall(r"[a-z]{3,}", fold(text)):
        if w in _STOP:
            continue
        for cand in _singulars(w):
            if cand in labels:
                return cand, labels[cand]
    return None, []


_OUTLINE_CLASSES = ("IfcSpace", "IfcWall", "IfcWallStandardCase", "IfcColumn", "IfcCurtainWall")


def storey_outline(idx: IfcIndex, storey_guid: str | None):
    """Outer outline of one storey (or of the whole building when None): union of the plan footprints of its
    rooms, walls, columns and curtain walls, small gaps closed, holes (courtyards excluded) filled. A shapely
    (Multi)Polygon, or None when there is no geometry."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    polys = []
    for e in idx.elements.values():
        if e.cls not in _OUTLINE_CLASSES or (storey_guid and e.storey != storey_guid) or not (e.geo and e.geo.footprint):
            continue
        for ring in e.geo.footprint:
            if len(ring) >= 3:
                p = Polygon(ring)
                if not p.is_valid:
                    p = p.buffer(0)
                if p.area > 1e-4:
                    polys.append(p)
    if not polys:
        return None
    u = unary_union(polys).buffer(0.05, join_style=2).buffer(-0.05, join_style=2)
    parts = [u] if u.geom_type == "Polygon" else list(getattr(u, "geoms", []))
    parts = [Polygon(p.exterior) for p in parts if p.area > 1.0]
    return unary_union(parts) if parts else None


def external_by_outline(idx: IfcIndex, walls: list[Element]) -> list[Element]:
    """Walls lying on the outer outline of their storey (for models without Pset_WallCommon.IsExternal)."""
    from shapely.geometry import Polygon

    out, cache = [], {}
    for e in walls:
        if not (e.geo and e.geo.footprint):
            continue
        if e.storey not in cache:
            ol = storey_outline(idx, e.storey)
            cache[e.storey] = ol.boundary if ol is not None else None
        b = cache[e.storey]
        if b is None:
            continue
        p = Polygon(e.geo.footprint[0])
        if not p.is_valid:
            p = p.buffer(0)
        r = p.minimum_rotated_rectangle
        xs = list(r.exterior.coords)
        sides = sorted(((xs[i][0] - xs[i + 1][0]) ** 2 + (xs[i][1] - xs[i + 1][1]) ** 2) ** 0.5 for i in range(4))
        long_side = sides[-1]
        if long_side > 0 and b.intersection(p.buffer(0.08)).length >= max(0.3, 0.5 * long_side):
            out.append(e)
    return out


_PARTS: dict[str, dict[str, str]] = {}


def _parts_of(model: str) -> dict[str, str]:
    if model not in _PARTS:
        from stoa.solvers.ifc.index import nested_parts

        try:
            _PARTS[model] = nested_parts(model)
        except Exception:  # noqa: BLE001 - no parts info is the old behaviour
            _PARTS[model] = {}
    return _PARTS[model]


def _poly(e: Element):
    from shapely.geometry import Polygon

    if not (e.geo and e.geo.footprint and len(e.geo.footprint[0]) >= 3):
        return None
    p = Polygon(e.geo.footprint[0])
    return p if p.is_valid else p.buffer(0)


_ZONE_NAME = re.compile(r"\b(brutto\w*|bruttoareal|nettoareal|gross (floor )?area|gfa|bta|bgf|nfa|area zone|"
                        r"arealsone|flachenzone|zone)\b")


def zone_spaces(spaces: list[Element]) -> set[str]:
    """IfcSpaces that are area zones, not rooms: named as a gross/net area zone, or whose footprint holds >= 3 other
    spaces of the set (hitos 'Bruttoareal uetg' 1618 m² over 59 rooms). Used to keep them out of 'largest room'
    only: the dataset's room totals include every IfcSpace (W1 c5)."""
    out = {e.guid for e in spaces if _ZONE_NAME.search(fold(f"{e.name or ''} {e.long_name or ''}"))}
    polys = [(e, _poly(e)) for e in spaces if e.guid not in out]
    polys = [(e, g) for e, g in polys if g is not None and g.area > 0.5]
    if len(polys) > 400:
        return out
    for z, gz in polys:
        n = 0
        for o, go in polys:
            if o is z or o.storey != z.storey or go.area >= 0.8 * gz.area:
                continue
            try:
                if gz.intersection(go).area > 0.8 * go.area:
                    n += 1
            except Exception:  # noqa: BLE001 - invalid geometry: skip the pair
                continue
            if n >= 3:
                out.add(z.guid)
                break
    return out


def adjacent(idx: IfcIndex, space: Element, classes: tuple[str, ...], reach: float = 0.35) -> list[Element]:
    """Doors/windows (or any elements) of `classes` that touch a room: their plan footprint is within `reach` m of the
    room's footprint and their heights overlap. A door in a wall touches both rooms it connects; a window touches the
    room behind its wall. Geometric, so it works without IfcRelSpaceBoundary."""
    sp = _poly(space)
    if sp is None or not (space.geo and space.geo.bbox):
        return []
    z0, z1 = space.geo.bbox[2], space.geo.bbox[5]
    zone = sp.buffer(reach)
    out = []
    for e in idx.by_class(*classes):
        p = _poly(e)
        if p is None or not e.geo.bbox or e.geo.bbox[5] < z0 + 0.1 or e.geo.bbox[2] > z1 - 0.1:
            continue
        if zone.intersects(p):
            out.append(e)
    return out


@register("ifc")
class IfcSolver(BaseSolver):
    sources = ("ifc_models", "ifc_bench", "opening_design")
    extensions = (".ifc", ".pdf", ".svg", ".png")

    def can_handle(self, path: str, question: str) -> bool:
        if Path(path).suffix.lower() == ".ifc":
            return True
        return source_of(path) == "ifc_models" and Path(path).suffix.lower() in (".pdf", ".svg", ".png")

    # ------------------------------------------------------------------------------------------------
    def solve(self, path: str, question: str) -> Answer:
        t0 = time.perf_counter()
        model = model_for(path)
        if model is None:
            return Answer.abstain(self.name, "no IFC model for this drawing", missing=["an IFC model of the building"])
        idx = load_index(model)
        llm_on = str(self.options.get("llm", "1")) != "0"
        ans, it, ctx = self._core(path, model, idx, question)
        if llm_on and str(self.options.get("translate", "1")) != "0":
            ans, it, ctx = self._cross_language(path, model, idx, question, ans, it, ctx)
        if llm_on and ctx.get("two_questions"):
            ans = self._multi_part(path, model, idx, ctx.get("question_en") or ctx.get("question", question), ans)
        if llm_on:
            ans = self._llm_stage(model, idx, question, it, ans, ctx)
        if ans.value is not None and self.options.get("plan2d", "1") != "0":
            try:
                self._add_2d(path, model, it, ans, ctx.get("storey"))
            except Exception as ex:  # noqa: BLE001 - 2D evidence is a bonus; never lose the answer over it
                ans.trace.append(f"2D link failed: {type(ex).__name__}: {ex}")
        ans.solver = self.name
        ans.cost.wall_seconds = time.perf_counter() - t0
        return ans

    # ------------------------------------------------------------------------------------------------
    def _cross_language(self, path: str, model: str, idx: IfcIndex, question: str, ans: Answer, it: Intent,
                        ctx: dict) -> tuple[Answer, Intent, dict]:
        """A non-English question in a wording the dataset does not use: read it twice, as is and translated to
        English (stoa.llm.to_english, one local-LLM call), and compare the two rule answers (W1 c5, 04:50).

        Why: the parser has operator words for English and only template words for de/nl/pl/et/it/ro, so a fresh
        wording in another language loses its operator ("in feet", "what percent", "how many more", "which ... or")
        and the base template answers at train confidence (W1 c5 probe: 11 of 108 confident-wrong in pl/et/es/
        cs/hu/sv; S0/F 04:01 hard2r: Estonian ifc 20%). Translating alone is not safe either: on the dataset's own
        non-English questions it changed 7 of 364 answers, all for the worse ('vloeren' -> floors, 'belek' ->
        balconies). Rule, measured on both sets: agree -> keep; disagree on the operator/unit with the same element
        kind -> the English reading (the raw parse missed a word); disagree on the element kind -> the parser's
        own reading for a language it has vocabulary for, else the English one; both low confidence."""
        from stoa import llm
        from stoa.router.prior import known_template

        lang = llm.lang_guess(question)
        if lang == "en" or not fold(_QUOTED_RX.sub(" ", question)).strip():
            return ans, it, ctx
        try:
            if known_template(question) or _known_wording(question):
                ans.trace.append(f"language: {lang}, a dataset wording; parsed as is (no translation)")
                return ans, it, ctx
        except Exception:  # noqa: BLE001 - no train split on this machine: treat as unseen
            pass
        tr = llm.to_english(question, force=True)
        own = lang in PARSER_LANGS
        if not tr.translated or not tr.ok:
            if tr.lang == "en":
                return ans, it, ctx
            if ans.value is not None and ans.confidence > (0.75 if own else 0.5):
                ans.confidence = 0.75 if own else 0.5
                ans.missing.append(f"an English reading of this {lang} question to cross-check the parse "
                                   f"({tr.note or 'translation unavailable'})")
                ans.trace.append(f"language: {lang} wording not seen in train and not translated -> confidence "
                                 f"{ans.confidence}")
            return ans, it, ctx
        eng, it2, ctx2 = self._core(path, model, idx, tr.text)
        eng.assumptions.append(tr.note)
        if ans.value is None and eng.value is None:
            return ans, it, ctx
        if ans.value is not None and eng.value is not None and _same_value(ans, eng):
            if eng.confidence < ans.confidence:  # a guard fired on the English reading (operator, number, relation)
                ans.confidence = eng.confidence
                ans.missing += [m for m in eng.missing if m not in ans.missing]
            if ctx2.get("two_questions"):
                ctx["two_questions"], ctx["question_en"] = True, tr.text
            ans.trace.append(f"language check: the English reading \"{tr.text}\" gives the same answer ✓")
            return ans, it, ctx
        if ans.value is None:
            eng.confidence = min(eng.confidence, 0.75)
            eng.trace.insert(0, f"the {lang} question was not understood by the rules; answered its English "
                                f"translation \"{tr.text}\" (confidence <= 0.75: the translation is a model's)")
            return eng, it2, ctx2
        if eng.value is None:
            cap = 0.75 if own else 0.5
            if ans.confidence > cap:
                ans.confidence = cap
                ans.missing.append(f"the English translation (\"{tr.text}\") could not be read by the rules; the "
                                   f"{lang} wording is not one seen in train")
            ans.trace.append(f"language check: English reading not parsed -> confidence <= {cap}")
            return ans, it, ctx
        # element kinds of the two readings ('storey' is what a floor word alone parses to: no element kind)
        rk = {k for k in ([it.kind] + list(it.kinds or [])) if k not in (None, "storey")}
        ek = {k for k in ([it2.kind] + list(it2.kinds or [])) if k not in (None, "storey")}
        rv = f"{ans.value} {ans.unit or ''}".strip()
        ev_ = f"{eng.value} {eng.unit or ''}".strip()
        use_eng = rk == ek or (ek and not rk) or (not own and bool(ek))
        # one reading used every number of the question and the other left one unused ('Wenn eine Tür 1.200 € kostet'
        # -> raw 55,200 EUR; the translation 'If a door 1.200 € costs' kept the German word order and lost the price):
        # the reading that used the numbers wins
        g_raw = any("not used -> confidence" in str(t) for t in ans.trace)
        g_eng = any("not used -> confidence" in str(t) for t in eng.trace)
        if g_raw != g_eng:
            use_eng = g_raw
        if use_eng:
            why = ("same element kind, so the raw parse missed an operator/unit word" if rk == ek else
                   "the raw parse found no element kind" if not rk else "the parser has no vocabulary for this language")
            eng.confidence = min(eng.confidence, 0.75 if (rk == ek or not rk) else 0.5)
            eng.trace.insert(0, f"language check: the {lang} wording read as is gives {rv[:60]}, its English "
                                f"translation \"{tr.text}\" gives {ev_[:60]}; {why}: using the English reading")
            eng.missing.append(f"the {lang} wording read without translation gives {rv[:60]}")
            return eng, it2, ctx2
        cap = (0.75 if not ek else 0.6) if own else 0.5
        if g_eng and not g_raw:
            cap = 0.75
        ans.confidence = min(ans.confidence, cap)
        ans.trace.append(f"language check: the English translation \"{tr.text}\" reads "
                         + (f"a different element kind ({', '.join(sorted(ek))} vs {', '.join(sorted(rk))})" if ek else
                            "no element kind") + f" and gives {ev_[:60]}; kept the {lang} reading (confidence <= {cap})")
        ans.missing.append(f"a reading both ways agree on: the English translation gives {ev_[:60]}")
        return ans, it, ctx

    _SPLIT_SYSTEM = ("Split a question about a building model into self-contained questions, one per quantity asked. "
                     "Repeat the place (storey, room, model) and the element kind in every part, replacing pronouns "
                     "('their', 'them', 'it') by what they refer to. Keep quoted names and numbers verbatim. If only "
                     "one thing is asked, return just that question. Answer with JSON {\"questions\": [...]}.")

    def _multi_part(self, path: str, model: str, idx: IfcIndex, question: str, ans: Answer) -> Answer:
        """'How many rooms are on X and what is their total area?': one local-LLM call splits it into
        self-contained questions, the rules answer each, the answer is the parts joined as text (W1 c5)."""
        from stoa import llm

        try:
            r = llm.chat(question, system=self._SPLIT_SYSTEM, max_tokens=250, temperature=0.0,
                         json_schema={"type": "object", "properties": {"questions": {"type": "array",
                                      "items": {"type": "string"}}}, "required": ["questions"]})
            parts = [str(x).strip() for x in ((llm.extract_json(r.text) or {}).get("questions") or []) if str(x).strip()]
        except Exception as ex:  # noqa: BLE001 - keep the guarded single answer
            ans.trace.append(f"multi-part split failed: {type(ex).__name__}")
            return ans
        if not 2 <= len(parts) <= 4:
            return ans
        subs = []
        for q_ in parts:
            a_, _, ctx_ = self._core(path, model, idx, q_)
            if a_.value is None or ctx_.get("two_questions"):
                ans.trace.append(f"multi-part: '{q_}' not answered by the rules; kept the single value")
                return ans
            subs.append((q_, a_))
        def fmt(a_):
            v = a_.value
            v = (f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v))
            return f"{v} {a_.unit}".strip() if a_.unit and a_.unit != "count" else v
        text = "; ".join(f"{fmt(a_)} ({q_.rstrip('?')})" for q_, a_ in subs)
        seen, ev = set(), []
        for _, a_ in subs:
            for e in a_.evidence:
                k = e.ifc_guid or e.note
                if k not in seen:
                    seen.add(k)
                    ev.append(e)
        out = Answer(value=text, unit=None, confidence=round(min(min(a_.confidence for _, a_ in subs) * 0.9, 0.8), 3),
                     evidence=ev[:300], solver=self.name,
                     trace=[f"multi-part: split into {len(subs)} questions by the local LLM"]
                     + [f"part {i + 1}: '{q_}' -> {fmt(a_)} (conf {a_.confidence:.2f})" for i, (q_, a_) in enumerate(subs)]
                     + [t for _, a_ in subs for t in a_.trace[-3:]],
                     assumptions=[x for _, a_ in subs for x in a_.assumptions][:8],
                     missing=[m for _, a_ in subs for m in a_.missing][:6])
        return out

    _VDIST = re.compile(r"\b(floor[- ]to[- ]floor|vertical(ly)?|height difference|difference in (height|elevation|level)|"
                        r"elevation difference|level difference|how far apart|distance between|hohenunterschied|"
                        r"hoogteverschil|korkeusero)\b")

    def _storey_distance(self, model: str, idx: IfcIndex, question: str, trace: list[str]) -> Answer | None:
        """'Floor-to-floor height / vertical distance / height difference between storeys A and B' = |z_B - z_A|
        from IfcBuildingStorey elevations (W1 c5: was the difference of the two storey heights at 0.69)."""
        qf = fold(question)
        if not self._VDIST.search(qf) or re.search(r"\b(room|space|window|door|wall|ceiling|raum|ruimte)s?\b", qf):
            return None
        found: list[Storey] = []
        for g in _QUOTED_RX.findall(question):
            n = next((x for x in g if x), "") if isinstance(g, tuple) else g
            ms = match_storey(idx, n.strip()) if n.strip() else None
            if ms is not None and ms.score >= 90 and ms.obj not in found:
                found.append(ms.obj)
        if len(found) < 2:
            bare = fold(_QUOTED_RX.sub(" ", question))
            for st in sorted(own_storeys(idx), key=lambda st: -len(st.name or "")):
                k = fold(st.name or "")
                if k and len(k) >= 2 and re.search(r"(?<![\w.])" + re.escape(k) + r"(?![\w])", bare) and st not in found:
                    found.append(st)
                    bare = bare.replace(k, " ")
        if len(found) != 2 or any(st.elevation is None for st in found):
            return None
        a, b = sorted(found, key=lambda st: st.elevation)
        d = b.elevation - a.elevation
        trace.append(f"vertical distance: '{b.name}' at {b.elevation:.3f} m - '{a.name}' at {a.elevation:.3f} m = {d:.3f} m")
        ev = [Evidence(file=model, ifc_guid=st.guid, note=f"IfcBuildingStorey {st.name} elevation {st.elevation:.3f} m")
              for st in (a, b)]
        return Answer(value=round(d, 4), unit="m", confidence=0.85, evidence=ev, trace=trace, solver=self.name,
                      assumptions=["vertical distance = difference of the IfcBuildingStorey elevations (finished floor "
                                   "levels as modelled)"])

    # ------------------------------------------------------------------------------------------------
    def _core(self, path: str, model: str, idx: IfcIndex, question: str) -> tuple[Answer, Intent, dict]:
        """Rules + guards for one wording of the question (no LLM call)."""
        trace: list[str] = []
        if model != path:
            trace.append(f"asked on {Path(path).name}; answering from its source model {Path(model).name}")
        trace.append(f"model {Path(model).name}: {idx.schema}, {len(idx.storeys)} storeys, {len(idx.elements)} elements"
                     f" (index {idx.build_seconds:.1f}s, cached)")
        it = parse(question)
        it.question = question
        trace.append(f"parsed: metric={it.metric} kind={it.kind} scope={it.scope} names={it.names}"
                     + (" side-area" if it.side_area else "") + (" gross" if it.gross else ""))
        self._repair_intent(path, idx, it, question, trace)
        ctx: dict = {"question": question, "threshold_sum": "threshold_sum" in it.notes,
                     "threshold_list": "threshold_list" in it.notes, "rank": next((int(n[5:]) for n in it.notes
                                                                                    if n.startswith("rank:")), 1)}
        try:
            ans = self._storey_distance(model, idx, question, trace)
            if ans is None:
                ans = self._relation(path, model, idx, it, question, trace, ctx)
            if ans is None:
                ans = self._outer(path, model, idx, it, question, trace, ctx)
            if ans is None:
                ans = self._answer(path, model, idx, it, trace, ctx)
        except Exception as ex:  # noqa: BLE001 - report as a refusal with the reason, never crash the eval
            ans = Answer.abstain(self.name, f"error: {type(ex).__name__}: {ex}", trace=trace)
        if ans.value is not None and it.kind == "space" and it.metric == "area" and isinstance(ans.value, (int, float)):
            from stoa.solvers.ifc.factcard import placeholder_spaces

            if placeholder_spaces(idx):
                ans.confidence = min(ans.confidence, 0.15)
                ans.missing.append("real room areas: this model's IfcSpaces are ~1 m² placeholders (geometry and "
                                   "quantity sets), so the value is not a floor area")
        if ans.value is not None and not it.mod and not it.which and it.op is None and not ctx.get("outer"):
            # an operator word the parse did not turn into an operator: the atomic value may not be what was asked
            w = _OPERATOR_WORD.search(fold(question))
            if w and it.group_by == "storey" and re.fullmatch(r"per (storey|floor|level)", w.group(0)):
                w = None  # "how many doors per storey?" IS the per-storey breakdown the rules gave
            if w and ans.confidence > 0.5:
                ans.confidence = 0.5
                ans.missing.append(f"the question has an operator word ('{w.group(0)}') the rules did not apply")
                ans.trace.append(f"guard: operator word '{w.group(0)}' not modelled -> confidence capped at 0.5")
        n_bad = 0
        if ans.value is not None and it.metric == "area" and it.kind == "space":
            for ev_ in ans.evidence:
                e_ = idx.elements.get(ev_.ifc_guid) if ev_.ifc_guid else None
                if e_ is not None and e_.cls == "IfcSpace":
                    q_ = _qto(e_, QTO_KEYS[("floor", "net")])
                    g_ = e_.geo.footprint_area if e_.geo else None
                    if q_ and g_ and abs(q_ - g_) > 0.02 * g_:
                        n_bad += 1
            if n_bad:
                ans.trace.append(f"cross-check: {n_bad} room(s) with explicit NetFloorArea ≠ shape area (> 2%) ✗")
        if ans.value is not None and n_bad and ans.confidence > 0.85:
            # explicit quantity and shape disagree for some rooms: say so and be less sure. 0.85, not lower: the gold
            # convention is the explicit quantity (S0 D15 B: the test model's gold follows Qto; test 2 197/197 on it;
            # F's unseen-model area probe 78/78 with 32 right answers held at the old 0.7 cap)
            ans.confidence = 0.85
            ans.missing.append(f"{n_bad} room(s): explicit NetFloorArea and the room shape differ by > 2%; "
                               "used the explicit quantity")
        if ans.value is not None:
            # a number in the question that no rule used ("if each door costs 450 EUR", "minus 5"): the answer
            # ignores part of the question, so it is not what was asked (W5's probes, 01:49)
            from stoa.solvers.ifc.arith import leftover_numbers

            thr_vals = [float(x) for x in (it.threshold[1:] if it.threshold else ())]
            left = [x for x in leftover_numbers(question, ctx.get("outer_spans", []), None, dims=bool(ctx.get("dims_used")))
                    if not any(abs(float(x.replace(",", ".")) - t) < 1e-9 for t in thr_vals)]
            if ctx.get("rank", 1) > 1:
                left = [x for x in left if x not in ("2", "3", "4", "5")]
            if left and ans.confidence > 0.3:
                ans.confidence = 0.3
                ans.missing.append(f"the question gives the number(s) {', '.join(left[:3])}, which the rules did not use")
                ans.trace.append(f"guard: number(s) {', '.join(left[:3])} in the question not used -> confidence 0.3")
        if ans.value is not None and ctx.get("assumed_count") and ans.unit == "count" and ans.confidence > 0.3:
            ans.confidence = 0.3
            ans.missing.append("the question has no counting word; a count was assumed")
        if ans.value is not None and ctx.get("room_type_missing") and it.kind in (None, "space") \
                and ans.confidence > 0.3:
            ans.confidence = 0.3
            ans.missing.append(f"no room in the model is labelled as a {ctx['room_type_missing']} (any language); "
                               "the value covers rooms of every type")
            ans.trace.append(f"guard: room type '{ctx['room_type_missing']}' not found among the room labels -> 0.3")
        if ans.value is not None and not ctx.get("outer") and it.op != "diff" and it.mod != "share":
            # "How many rooms have no window?", "doors leading to the kitchen": a relation between two element
            # kinds that the rules do not model (they answer for one kind only)
            from stoa.solvers.ifc.arith import text_of
            from stoa.solvers.ifc.parse import _kind_hits

            tq = text_of(question)
            hits = [h for h in _kind_hits(tq) if h[2] != "storey"]
            hits = [h for h in hits if not any(o is not h and o[0] <= h[0] and h[1] <= o[1] and (o[1] - o[0]) > (h[1] - h[0])
                                               for o in hits)]  # "pipe" inside "pipe fittings" is not a 2nd kind
            used = set(it.kinds or []) | {it.kind}
            rel = None
            for h0, h1, k in hits:
                if k in used:
                    continue
                mrel = re.search(r"\b(with|without|have|has|having|no|containing|contains?|lead\w* (?:to|into)|"
                                 r"(?:has|have|with) the (?:most|fewest|least|largest number of)|"
                                 r"connect\w* (?:to|with)|adjacent to|next to|ohne|mit|zonder|met|sans|avec|senza|bez|"
                                 r"ilman)\s+(?:(?:a|an|any|no|the|one|two|\d+|at least \w+|more than \w+)\s+)?$",
                                 tq[max(0, h0 - 30):h0])
                if mrel:
                    rel = (mrel.group(1), k)
                    break
            if rel and len({h[2] for h in hits}) >= 2 and ans.confidence > 0.3:
                ans.confidence = 0.3
                ans.missing.append(f"the relation '{rel[0]} {rel[1]}' between element kinds is not modelled; the "
                                   "value counts one kind only")
                ans.trace.append(f"guard: relation '{rel[0]} {rel[1]}' not modelled -> confidence 0.3")
        m2q = re.search(r"\b(how many|how much|what|which|wie viele|hoeveel)\b[^?]{3,80}?\band\s+(how many|how much|what|which|"
                        r"how (?:big|large|long|tall|high|wide)|wie viel\w*|hoeveel)\b", fold(_QUOTED_RX.sub(" ", question)))
        if ans.value is not None and m2q and not isinstance(ans.value, str) and ans.confidence > 0.5:
            # "How many windows and what total window area ...": two questions, one number
            ctx["two_questions"] = True
            ans.confidence = 0.5
            ans.missing.append("the question asks two things; the value answers only one of them "
                               f"({ans.unit or 'value'})")
            ans.trace.append("guard: two questions in one -> confidence 0.5")
        mo = re.search(r"\b(north|south|east|west|northern|southern|eastern|western|nord|sud|sued|ost|noord|zuid|oost|"
                       r"norte|oeste|este|pohjois|etela|ita|lansi)\w*[- ]?(facing|facade|side|elevation|wall|fassade|"
                       r"gevel|fachada|julkisivu)?\b", fold(_QUOTED_RX.sub(" ", question)))
        if ans.value is not None and mo and (mo.group(2) or re.search(r"\b(facade|fassade|gevel|elevation|facing|side)\b",
                                                                     fold(question))) and ans.confidence > 0.3:
            ans.confidence = 0.3
            ans.missing.append(f"orientation ('{mo.group(0).strip()}') is not applied: the value covers every side")
            ans.trace.append(f"guard: orientation '{mo.group(0).strip()}' not modelled -> confidence 0.3")
        for note in it.notes:
            if note.startswith("exclusion"):
                if note.startswith("exclusion NOT") and ctx.get("rest_applied"):
                    continue  # the rest rule applied it (W4 05:02: the trace said 'NOT applied' on right answers)
                ans.trace.append(note)
                if note.startswith("exclusion NOT") and ans.value is not None and not ctx.get("rest_applied"):
                    ans.confidence = min(ans.confidence, 0.3)
                    ans.missing.append(f"the question excludes something the rules can't apply ({note[23:]}); "
                                       "the value ignores the exclusion")
        if ans.value is not None and len(buildings_of(idx)) > 1 and ans.confidence > 0.75:
            ans.confidence = 0.75
            ans.missing.append(f"which building is meant: the model holds {len(buildings_of(idx))} buildings "
                               f"({', '.join(str(b) for b in buildings_of(idx)[:4])}); "
                               + ("answered for the main one" if any(t.startswith("multi-building") for t in ans.trace)
                                  else "the value covers all of them"))
        tf = next((n for n in it.notes if n.startswith("top_floor_skip:")), None)
        if tf and ans.value is not None and ans.confidence > 0.85:
            ans.confidence = 0.85
            ans.missing.append("which storey is meant: read as the highest/lowest storey with rooms or doors; the model "
                               f"also has the level(s) {tf[15:]} beyond it")
        role = next((n for n in it.notes if n.startswith("storey_by_role")), None)
        if role and ans.value is not None:
            cap = 0.6 if role.endswith(":elevation") else 0.85
            if ans.confidence > cap:
                ans.confidence = cap
                ans.missing.append("which storey is meant: none is named; picked "
                                   + ("by elevation (highest below 0)" if cap == 0.6 else "by its basement name"))
        if ctx.get("geo_external") and ans.value is not None:
            ans.confidence = min(ans.confidence, 0.6)
        if ctx.get("material_unknown") and ans.value is not None:
            ans.confidence = min(ans.confidence, 0.3)
        if ans.value is not None and any("proxy/generic elements named like" in x for x in ans.trace):
            ans.confidence = min(ans.confidence, 0.6)  # counted by name, not by class: names can over/under-match
        return ans, it, ctx

    def _llm_stage(self, model: str, idx: IfcIndex, question: str, it: Intent, ans: Answer, ctx: dict) -> Answer:
        """At most one local-LLM call: free text when the rules found nothing, or a listing that was asked for."""
        if ans.value is None and not any("error:" in t for t in ans.trace):
            ans = self._llm_fallback(model, idx, question, it, ans, storey=ctx.get("storey"))
        elif isinstance(ans.value, (int, float)) and (wants_list(question) or wants_list(ctx.get("question", question))):
            # a listing/description was asked; one number is not an answer. Give the LLM the rule's value as a
            # verified fact (with its scope) plus the fact card, and keep the rule's evidence.
            rule = ans
            fact = (f"{rule.value} {rule.unit or ''} -- " + "; ".join(rule.assumptions[:3]))[:400]
            ans = self._llm_fallback(model, idx, question, it, rule, storey=ctx.get("storey"),
                                     extra=f"Computed exactly by a rule for this question: {fact}")
            if ans.value is None:
                ans = rule
            else:
                ans.evidence = rule.evidence or ans.evidence
                ans.confidence = 0.4
                ans.trace.insert(0, f"list request: rule value {rule.value} {rule.unit or ''} passed to the LLM as a fact")
        return ans

    # ------------------------------------------------------------------------------------------------
    def _roles(self, path: str, idx: IfcIndex, it: Intent, trace: list[str], assumptions: list[str]):
        """Give every quoted name a role by resolving it against the model (not by its position):
        -> (storey | None, rooms: list[(asked_name, [Match])], conf_factor)."""
        conf = 1.0
        storey, storey_name, rooms, model_named = None, None, [], False
        groups: list[tuple[str, list[Element]]] = []
        cands = []
        def digits_ok(asked: str, label: str | None) -> bool:
            # '7. Level' is not '1. Level', 'KORIDOR (219)' is not 'KORIDOR (119)' (Q red team 04:13)
            return re.findall(r"\d+", asked) == re.findall(r"\d+", label or "") or not re.findall(r"\d+", asked)

        for n in it.names:
            ms = match_storey(idx, n)
            if ms is not None and ms.method == "fuzzy" and not digits_ok(n, ms.label):
                trace.append(f"'{n}': fuzzy storey match '{ms.label}' rejected (numbers differ)")
                ms = None
            sp = match_space(idx, n) if it.kind == "space" or it.metric == "area" or it.attr == "room_height" else []
            sp = [m_ for m_ in sp if m_.method != "fuzzy" or digits_ok(n, m_.label)]
            mm = match_model(idx, n)
            cands.append((n, ms, sp, mm))
        # storey: the best exact/normalised storey match, else the best fuzzy one that isn't a better room match
        st_c = [(n, ms) for n, ms, sp, mm in cands if ms and (not sp or ms.score >= sp[0].score)]
        if st_c:
            n, ms = max(st_c, key=lambda x: x[1].score)
            storey, storey_name = ms.obj, n
            trace.append(f"storey '{n}' -> '{ms.label}' ({ms.method}, {ms.score:.0f}) guid {storey.guid}")
            if ms.method == "fuzzy":
                conf *= 0.85
                assumptions.append(f"storey name '{n}' matched fuzzily to '{ms.label}'")
        for n, ms, sp, mm in cands:
            if n == storey_name:
                continue
            if mm and (not sp or mm.score > sp[0].score) and mm.score >= 85:
                model_named = True
                trace.append(f"'{n}' = the model ('{mm.label}', {mm.method})")
                continue
            if it.kind == "space" or it.metric == "area" or it.attr == "room_height":
                grp = label_group(idx, n, storey.guid if storey else None)
                sp2 = match_space(idx, n, storey.guid if storey else None)
                if sp2 and (len(grp) <= 1 or (sp2[0].score >= 99 and it.metric != "count")):
                    rooms.append((n, sp2))
                    continue
                if grp:
                    groups.append((n, grp))
                    trace.append(f"'{n}' is a room type: {len(grp)} spaces labelled so"
                                 + (f" on '{storey.name}'" if storey else ""))
                    if re.search(r"\d", n) and len(grp) > 1:  # 'KORIDOR (219)' asked, only 'KORIDOR' rooms exist
                        conf *= 0.4
                        assumptions.append(f"no room is named exactly '{n}'; took every room labelled like it")
                    continue
            if it.scope == "model" or (mm and mm.score >= 60):
                model_named = True
                trace.append(f"'{n}' taken as the model's name" + (f" (~'{mm.label}')" if mm else
                             " (not in IfcProject/IfcBuilding names; the file is the model)"))
                stem_words = set(re.findall(r"[a-z]{3,}", fold(" ".join([idx.path, path, idx.project_name or "",
                                                                          idx.project_long_name or "",
                                                                          *(idx.building_names or [])]))))
                asked_words = set(re.findall(r"[a-z]{3,}", fold(n))) - {"the", "model", "building", "house", "project"}
                if not (mm and mm.score >= 60) and asked_words and not (asked_words & stem_words):
                    # 'Empire State Building' asked on smiley-west: a false premise, not a nickname (Q 04:13)
                    conf = min(conf, 0.3)
                    assumptions.append(f"the question names the model '{n}', which matches no project/building name; "
                                       "answered for this file")
            else:
                trace.append(f"'{n}': no storey, room or model of that name")
                assumptions.append(f"could not resolve '{n}'; the model's storeys are: "
                                   + ", ".join(st_.name for st_ in idx.storeys[:12]))
                conf = min(conf * 0.6, 0.3)
        if storey is None and not it.names and it.scope != "model" and getattr(it, "question", ""):
            i, why = storey_mention(it.question, [s.name for s in idx.storeys])
            if i is not None:
                storey = idx.storeys[i]
                trace.append(f"{why} (unquoted)")
            elif "matches no single storey" in why and it.kind != "storey" and \
                    not re.search(r"\b(ground|basement)\b", why.split(" matches")[0]):
                # "doors on the 7th floor" on a 5-storey model: never answer the sheet's storey with confidence
                # (Q 04:58 bug 13b: 46 @ 0.985; a quoted '7.korrus' was already flagged)
                conf = min(conf, 0.3)
                trace.append(f"guard: {why} -> confidence 0.3")
                assumptions.append(f"{why.split(' matches')[0]} matches no storey of this model (storeys: "
                                   + ", ".join(st_.name for st_ in idx.storeys[:12]) + "); answered for the plan's storey")
        if it.scope == "model" or (model_named and storey is None):
            it.scope = "model"
        elif storey is None and it.metric != "text":
            ps, why = plan_storey(path, idx)
            if ps is not None and not (it.metric == "area" and rooms and not it.total):
                storey = ps
                trace.append(f"storey from the plan file: {why}")
            elif ps is not None:
                trace.append(f"plan file shows {why}")
            elif not rooms and len({e.storey for e in idx.elements.values()
                                    if e.storey and e.cls not in ("IfcSpace",) and e.geo is not None}) == 1:
                only = next(e.storey for e in idx.elements.values()
                            if e.storey and e.cls not in ("IfcSpace",) and e.geo is not None)
                storey = idx.storey(only)
                trace.append(f"all building elements are on storey '{storey.name}': the plan shows that storey")
            elif not rooms:
                trace.append(f"no storey named or implied ({why}); whole model")
                assumptions.append("no storey given; answered for the whole model")
                it.scope = "model"
                if it.names or (it.kind != "storey" and Path(path).suffix.lower() != ".ifc"):
                    conf *= 0.5
        if storey is not None and len(buildings_of(idx)) > 1:
            # several IfcBuildings own storeys (city_house_munich: the house + 2 neighbour massings with storeys of
            # the same names): a storey named in the question means the designed building's level
            mb = main_building(idx)
            if storey.building != mb:
                same = [st for st in idx.storeys if st.building == mb and _level_key(st.name) == _level_key(storey.name)]
                same = same or [st for st in idx.storeys if st.building == mb and st.elevation is not None
                                and storey.elevation is not None and abs(st.elevation - storey.elevation) < 0.05]
                if same:
                    trace.append(f"multi-building: '{storey.name}' of building '{storey.building}' -> '{same[0].name}' of "
                                 f"the main building '{mb}' (most elements)")
                    assumptions.append(f"the model has {len(buildings_of(idx))} buildings; '{storey.name}' read as the "
                                       f"level of the main building '{mb}' ('{same[0].name}')")
                    storey = same[0]
        ctx_groups = groups
        return storey, rooms, conf, ctx_groups

    def _answer(self, path: str, model: str, idx: IfcIndex, it: Intent, trace: list[str], ctx: dict) -> Answer:
        assumptions: list[str] = []
        missing: list[str] = []
        st_n, oth_n = self._storey_names(idx, it) if it.names else ([], [])
        if ctx.get("compose", True) and not oth_n and len(st_n) <= 1 and not ctx.get("no_dims"):
            ctx["dims_storey"] = st_n[0][1] if st_n else None
            dim = self._dims_answer(model, idx, it, trace, ctx)
            if dim is not None:
                ctx["dims_used"] = True
                return dim
        if it.metric == "text":
            if it.kind is not None and it.names:
                it.metric = "count"  # "Count the walls on storey X." style imperatives without a count word
                trace.append("no metric word; assuming a count")
                ctx["assumed_count"] = True
            else:
                return Answer.abstain(self.name, "free-text question: no deterministic rule", trace=trace,
                                      missing=["a quantity question (count/area/volume/length)"])
        if ctx.get("compose", True):
            comp = self._compose(path, model, idx, it, trace, ctx)
            if comp is not None:
                return comp
        storey, rooms, conf, groups = self._roles(path, idx, it, trace, assumptions)
        sname = storey.name if storey else None
        ctx["storey"] = storey
        where_s = f"on '{sname}'" if storey is not None and it.scope != "model" else "in the model"

        # ---- storeys themselves: count, elevation, height ---------------------------------------------
        if it.kind == "storey":
            if it.metric == "count":
                qg = fold(ctx.get("question", ""))
                sts = idx.storeys
                elevs = [st.elevation for st in idx.storeys if st.elevation is not None]
                # elevations relative to a site datum (hitos: 17.3 .. 40.3 m): 'ground' is not elevation 0, so name the
                # below-ground levels by their names (basement / foundation words) and say so
                datum = bool(elevs) and min(elevs) > 0.5 and not any(abs(z) < 0.5 for z in elevs)
                below_name = re.compile(r"\b(kjeller|keller\w*|kelder\w*|basement\w*|cellar|sous[- ]sol|kellari|"
                                        r"fundament\w*|foundation\w*|untergeschoss|souterrain|interrato|seminterrato|"
                                        r"piwnica|podziemi\w*|kelder|b\d+|u\d+|ug\d*|-\d+)\b")
                if re.search(r"\b(above[- ](ground|grade)|oberirdisch\w*|bovengronds\w*|maanpaall\w*)\b", qg):
                    if datum:
                        sts = [st for st in idx.storeys if not below_name.search(fold(st.name or ""))]
                        assumptions.append("storey elevations are relative to a datum, not to the ground; above ground = "
                                           "storeys not named as basement/foundation")
                        conf = min(conf, 0.6 / 0.85)
                    else:
                        sts = [st for st in idx.storeys if st.elevation is None or st.elevation > -0.01]
                        assumptions.append("above ground = storeys with elevation >= 0 (incl. a roof level if modelled)")
                elif re.search(r"\b(below[- ](ground|grade)|underground|basements?|unterirdisch\w*|ondergronds\w*|"
                               r"kelder\w*|keller\w*)\b", qg):
                    if datum:
                        sts = [st for st in idx.storeys if below_name.search(fold(st.name or ""))]
                        assumptions.append(f"storey elevations are relative to a datum ({min(elevs):.2f}..{max(elevs):.2f} "
                                           "m), not to the ground; below ground = storeys named as basement/foundation")
                        missing.append("the ground level: the model gives no storey at elevation 0")
                        conf = min(conf, 0.6 / 0.85)
                    else:
                        sts = [st for st in idx.storeys if st.elevation is not None and st.elevation < -0.01]
                        assumptions.append("below ground = storeys with elevation < 0")
                if len(buildings_of(idx)) > 1:
                    mb = main_building(idx)
                    sts = [st for st in sts if st.building == mb]
                    assumptions.append(f"the model has {len(buildings_of(idx))} buildings with storeys; counted the "
                                       f"main building '{mb}' (most elements)")
                    trace.append(f"multi-building: storeys of '{mb}' only")
                generic = "storeys = IfcBuildingStorey entities (incl. foundation/roof levels if modelled)"
                if len(sts) > 1 and not re.search(r"\b(above|below)[- ](ground|grade)|underground|basements?|"
                                                  r"oberirdisch|bovengronds|maanpaall|unterirdisch|ondergronds|kelder|"
                                                  r"keller", qg):
                    # "How many floors does this building have?" on esplanades: 7 IfcBuildingStorey levels, but
                    # 'Vundament' (foundation) and 'Katus' (roof) hold no room and no door; a person says 5 (Q 04:55)
                    occ = used_storeys(idx, sts)
                    aux = [st for st in sts if st not in occ]
                    if occ and aux:
                        names_aux = ", ".join(f"'{st.name}'" for st in aux[:6])
                        # IFC-Bench smiley_west: "number of levels" gold = 4 storeys (5 IfcBuildingStorey, the roof
                        # level 'Dach' holds no room or door) -> levels / floors / storeys all mean the used ones
                        if re.search(r"\bifcbuildingstorey\w*|\bbuilding ?storey (entities|objects|elements)\b", qg):
                            generic = (f"storeys = IfcBuildingStorey entities: {len(sts)}, of which {len(occ)} hold rooms or "
                                       f"doors ({names_aux} hold neither)")
                            conf = min(conf, 0.75 / 0.85)
                        else:
                            generic = (f"floors = the {len(occ)} storeys that hold rooms or doors; the model has {len(sts)} "
                                       f"IfcBuildingStorey levels, incl. {names_aux} with no room or door")
                            missing.append(f"whether roof/foundation levels and levels without rooms or doors count as "
                                           f"floors ({names_aux}); with them: {len(sts)}")
                            trace.append(f"floors with rooms or doors: {len(occ)} of {len(sts)} storeys")
                            sts = occ
                            conf = min(conf, 0.6 / 0.85)
                ev = [Evidence(file=model, ifc_guid=st.guid, note=f"IfcBuildingStorey {st.name}") for st in sts]
                trace.append("storeys: " + ", ".join(f"{st.name} ({st.elevation:.2f} m)" if st.elevation is not None
                                                      else st.name for st in idx.storeys))
                assumptions.append(generic)
                if storey is not None and any(t.startswith("storey '") and f"-> '{storey.name}'" in t for t in trace):
                    # "How many <unread word> are on 'Level 1'?" -> the counted kind was not recognised and fell back
                    # to storeys; storeys ON a named storey is not a question anyone asks (W1 c5: 'sammast' = columns)
                    conf = min(conf, 0.3 / 0.85)
                    missing.append(f"what to count on '{storey.name}': the counted element kind was not recognised "
                                   "(the value is the model's storey count)")
                    trace.append("guard: storeys counted although the question names one storey -> confidence 0.3")
                return self._final(len(sts), "count", it, conf * 0.85, ev, trace, assumptions, missing)
            if storey is None:
                return Answer.abstain(self.name, "storey not found", trace=trace, missing=["a storey name"])
            ev = [Evidence(file=model, ifc_guid=storey.guid, note=f"IfcBuildingStorey {storey.name}")]
            if it.attr == "elevation" or storey.elevation is None:
                if storey.elevation is None:
                    missing.append("storey has no Elevation attribute")
                    return Answer.abstain(self.name, "no elevation", trace=trace, missing=missing)
                assumptions.append("elevation = IfcBuildingStorey.Elevation (project units -> m)")
                return self._final(float(storey.elevation), "m", it, conf * 0.95, ev, trace, assumptions, missing)
            i = idx.storeys.index(storey)
            above = next((s2 for s2 in idx.storeys[i + 1:] if s2.elevation is not None
                          and s2.elevation > storey.elevation + 1e-6), None)
            if above is not None:
                h = above.elevation - storey.elevation
                assumptions.append(f"storey height = elevation of the next storey '{above.name}' minus this one's")
                return self._final(h, "m", it, conf * 0.85, ev, trace, assumptions, missing)
            tops = [e.geo.bbox[5] for e in idx.in_storey(storey.guid) if e.geo and e.geo.bbox]
            if tops:
                h = max(tops) - storey.elevation
                assumptions.append("top storey: height = highest element top minus the storey elevation")
                return self._final(h, "m", it, conf * 0.5, ev, trace, assumptions, missing)
            return Answer.abstain(self.name, "no storey above and no geometry", trace=trace)

        # ---- room types: 'Bathroom' -> every space labelled so ------------------------------------------
        if not groups and not rooms and it.kind in (None, "space") and not ctx.get("no_room_type"):
            from stoa.solvers.ifc.arith import label_has_type, room_type_in_question

            # quoted names are resolved by _roles; a sub-question of a composed answer must not pick them up here
            q_unq = ctx.get("question", "") if it.kind is None else _QUOTED_RX.sub(" ", ctx.get("question", ""))
            lab, grp = vocabulary_group(idx, q_unq, it.names)
            concept = room_type_in_question(q_unq) if not lab else None
            if concept:
                grp = [e for e in idx.by_class("IfcSpace") if label_has_type(e.long_name, concept)
                       or label_has_type(e.name, concept)]
                if grp:
                    lab = concept
                    labs = sorted({e.long_name or e.name or "" for e in grp})
                    assumptions.append(f"'{concept}' = spaces labelled " + ", ".join(f"'{x}'" for x in labs[:6])
                                       + (" ..." if len(labs) > 6 else ""))
                else:
                    ctx["room_type_missing"] = concept
            if lab:
                if storey is not None and it.scope != "model":
                    on_st = [e for e in grp if e.storey == storey.guid]
                    if not on_st and grp and not it.names and \
                            storey_mention(ctx.get("question", ""), [s_.name for s_ in idx.storeys])[0] is None:
                        # the storey only came from the plan sheet, and it has none of them: the model's
                        assumptions.append(f"the sheet's storey '{storey.name}' has no {lab}; answered for the whole model")
                        trace.append(f"no '{lab}' on the sheet's storey '{storey.name}': whole model")
                        it.scope, storey, where_s = "model", None, "in the model"
                    else:
                        grp = on_st
                groups = [(lab, grp)]
                it.kind = "space"
                trace.append(f"room type '{lab}' from the model's room labels: {len(grp)} spaces {where_s}")
        if not groups and not rooms and it.kind == "space" and it.metric in ("count", "area"):
            # unquoted room labels: "rooms named KORIDOR", "spaces called Bathroom"
            mq = re.search(r"\b(?:named|called|labell?ed|titled)\s+([^\s,?.;:'\"‘’“”]+(?:\s+[^\s,?.;:'\"‘’“”]+)?)",
                           ctx.get("question", ""))
            if mq:
                sg = storey.guid if (storey is not None and it.scope != "model") else None
                for cand in dict.fromkeys((mq.group(1), mq.group(1).split()[0])):
                    grp = label_group(idx, cand, sg)
                    if grp:
                        groups = [(cand, grp)]
                        trace.append(f"rooms labelled '{cand}' (unquoted): {len(grp)} spaces {where_s}")
                        break
        if groups and it.kind in ("space", None) and it.metric in ("count", "area", "text"):
            els = [e for _, g in groups for e in g]
            it.kind = "space"
            assumptions.append("room type = IfcSpace LongName/Name without its numbering")
            if it.op in ("max", "min", "argmax", "argmin", "range", "median") and els:
                vals = [(v, e) for e in els for v in [self._floor_area(e, it, [])[0]] if v]
                if vals:
                    return self._superlative(model, it, vals, conf, trace, assumptions, missing, where_s, ctx.get("rank", 1))
            if it.metric == "text":
                it.metric = "count"
            if it.metric == "count":
                ev = [self._ev(model, e, f"{e.long_name or ''} {e.name or ''}".strip()) for e in els]
                return self._final(len(els), "count", it, conf * 0.85, ev, trace, assumptions, missing)
            tot, ev = 0.0, []
            for e in els:
                v, how = self._floor_area(e, it, [])
                if v is not None:
                    tot += v
                    ev.append(self._ev(model, e, f"{e.long_name or e.name} {v:.2f} m²"))
            trace.append(f"sum over {len(ev)} spaces")
            return self._final(tot, "m2", it, conf * 0.85, ev, trace, assumptions, missing)

        # ---- named rooms: area of one, or sum/max/min/argmax/diff over several ----------------------
        if it.attr == "room_height" or (it.metric == "volume" and it.kind == "space"):
            if rooms:
                sp_els = [ms[0].obj for _, ms in rooms]
            else:
                sp_els = [e for _, g in groups for e in g] or (
                    idx.in_storey(storey.guid, "IfcSpace") if storey is not None and it.scope != "model"
                    else idx.by_class("IfcSpace"))
            if sp_els:
                if it.attr == "room_height":
                    def hv(e: Element) -> float | None:
                        q = _qto(e, (".FinishCeilingHeight", ".Height"))
                        if q:
                            return float(q)
                        return (e.geo.bbox[5] - e.geo.bbox[2]) if e.geo and e.geo.bbox else None
                    hs = [(hv(e), e) for e in sp_els]
                    hs = [(h, e) for h, e in hs if h]
                    if hs:
                        lo, hi = min(h for h, _ in hs), max(h for h, _ in hs)
                        mean = sum(h for h, _ in hs) / len(hs)
                        assumptions.append("room height = Qto FinishCeilingHeight/Height, else the space's vertical extent")
                        trace.append(f"room heights over {len(hs)} rooms {where_s}: min {lo:.2f} max {hi:.2f} mean {mean:.2f} m")
                        same = hi - lo < 0.011
                        if not same:
                            missing.append(f"rooms differ in height ({lo:.2f}-{hi:.2f} m); the value is the mean")
                        return self._final(hs[0][0] if same else mean, "m", it, conf * (0.85 if same else 0.5),
                                           [self._ev(model, e, f"{e.long_name or e.name} height {h:.2f} m") for h, e in hs],
                                           trace, assumptions, missing)
                else:
                    tot, ev, n_geo = 0.0, [], 0
                    for e in sp_els:
                        v = _qto(e, (".NetVolume", ".GrossVolume", ".Volume"))
                        if v is None and e.geo is not None and e.geo.volume:
                            v, n_geo = e.geo.volume, n_geo + 1
                        if v:
                            tot += float(v)
                            ev.append(self._ev(model, e, f"{e.long_name or e.name} {float(v):.2f} m³"))
                    if ev:
                        assumptions.append("room volume = Qto NetVolume, else the closed-mesh volume of the IfcSpace")
                        trace.append(f"volume of {len(ev)} rooms {where_s}: {tot:.3f} m³ ({n_geo} from geometry)")
                        return self._final(tot, "m3", it, conf * (0.9 if not n_geo else 0.75), ev, trace,
                                           assumptions, missing)
        if it.metric == "area" and rooms and not it.side_area:
            vals, ev = [], []
            for asked, ms in rooms:
                m = ms[0]
                e: Element = m.obj
                trace.append(f"room '{asked}' -> IfcSpace '{m.label}' ({m.method}, {m.score:.0f}) guid {e.guid}"
                             + (f"; {len(ms)} equally good matches, took the first" if len(ms) > 1 else ""))
                if m.method == "fuzzy":
                    conf *= 0.8
                    assumptions.append(f"room name '{asked}' matched fuzzily to '{m.label}'")
                if len(ms) > 1:
                    conf *= 0.6
                v, how = self._floor_area(e, it, trace)
                if v is None:
                    missing.append(f"room '{asked}' has no geometry or area quantity")
                    continue
                vals.append((asked, v, e))
                ev.append(self._ev(model, e, f"{e.long_name or e.name} {v:.2f} m²"))
                if how not in assumptions:
                    assumptions.append(how)
            if not vals:
                return Answer.abstain(self.name, "no area for the named rooms", trace=trace, missing=missing)
            op = it.op if len(vals) > 1 else None
            if op in ("argmax", "argmin"):
                pick = (max if op == "argmax" else min)(vals, key=lambda x: x[1])
                trace.append(f"{op}: " + ", ".join(f"{a} {v:.2f}" for a, v, _ in vals) + f" -> {pick[0]}")
                return Answer(value=pick[0], unit=None, confidence=conf * 0.9, evidence=ev, trace=trace,
                              solver=self.name, assumptions=assumptions, missing=missing)
            if op in ("max", "min"):
                val = (max if op == "max" else min)(v for _, v, _ in vals)
            elif op == "diff" and len(vals) == 2:
                val = abs(vals[0][1] - vals[1][1])
                trace.append(f"difference |{vals[0][1]:.2f} - {vals[1][1]:.2f}|")
            else:
                val = sum(v for _, v, _ in vals)
                if len(vals) > 1:
                    trace.append("sum of " + " + ".join(f"{v:.2f}" for _, v, _ in vals))
            return self._final(val, "m2", it, conf * 0.97, ev, trace, assumptions, missing)

        # ---- the largest / smallest room of a storey or the model (no room names given) ------------------
        if (it.kind == "space" and not rooms and not groups and not it.top_n and not it.group_by
                and it.op in ("max", "min", "argmax", "argmin", "range", "median") and it.metric in ("area", "text", "count")
                and idx.by_class("IfcSpace")):
            sp_els = (idx.in_storey(storey.guid, "IfcSpace") if storey is not None and it.scope != "model"
                      else idx.by_class("IfcSpace"))
            vals = [(v, e) for e in sp_els for v in [self._floor_area(e, it, [])[0]] if v]
            if vals:
                return self._superlative(model, it, vals, conf, trace, assumptions, missing, where_s, ctx.get("rank", 1))

        if it.kind is None:
            return Answer.abstain(self.name, "no element kind recognised in the question", trace=trace,
                                  missing=["element kind (doors, walls, rooms, ...)"])
        if it.metric == "area" and it.kind == "space" and not rooms and len(it.names) > (1 if storey else 0):
            return Answer.abstain(self.name, f"rooms {it.names} not found", trace=trace,
                                  missing=[f"IfcSpaces named {it.names}"])

        where = "whole model" if (it.scope == "model" or storey is None) else f"storey '{sname}'"
        if (it.kind == "space" or "space" in it.kinds) and not idx.by_class("IfcSpace"):
            # rooms are not modelled (e.g. ResBIM: walls/doors/windows only): 0 rooms / 0 m² is never a sensible
            # estimate; let the cascade read the drawing instead
            return Answer.abstain(self.name, "the model has no IfcSpace (rooms are not modelled)", trace=trace,
                                  missing=["rooms (IfcSpace) in the IFC model; read them from the drawing"])

        def elements_of(kind: str) -> list[Element]:
            nonlocal conf
            classes = KIND_CLASSES.get(kind, ())
            els = idx.by_class(*classes) if where == "whole model" else idx.in_storey(storey.guid, *classes)
            if where == "whole model" and els and len(buildings_of(idx)) > 1:
                qb = fold(_QUOTED_RX.sub(" ", ctx.get("question", "")))
                if re.search(r"\b(building|house|gebaude|haus|gebouw|huis|rakennus|talo|hoone|maja|batiment|edificio)\b", qb) \
                        and not re.search(r"\b(model|project|site|file|ifc|projekt|modell)\b", qb):
                    own = {st.guid for st in own_storeys(idx)}
                    mine = [e for e in els if e.storey is None or e.storey in own]
                    if len(mine) != len(els):
                        trace.append(f"multi-building: 'the building' = the main building '{main_building(idx)}': "
                                     f"{len(mine)} of {len(els)} elements ({len(els) - len(mine)} in the other buildings)")
                        assumptions.append(f"'the building' read as the main building '{main_building(idx)}'; the "
                                           f"model's other buildings hold {len(els) - len(mine)} more")
                        els = mine
            trace.append(f"{len(els)} elements of {'/'.join(classes)} in {where}")
            if not els and not idx.by_class(*classes):  # the model has none of this class at all
                els = self._kind_fallback(idx, kind, storey if where != "whole model" else None, trace, assumptions)
            if it.metric == "count" and els:
                # parts of an assembly of the same kind (stair parts exported as IfcStair under a parent IfcStair):
                # a person counts the assembly once (S0 D15 mechanism A)
                parts = _parts_of(model)
                same = set(classes)
                drop = {e.guid for e in els if parts.get(e.guid) in same}
                if drop:
                    els = [e for e in els if e.guid not in drop]
                    trace.append(f"{len(drop)} {kind} elements are parts of another {kind} (IfcRelAggregates): "
                                 f"counted once per assembly, {len(els)} left")
                    assumptions.append(f"{kind}s nested inside another {kind} are parts of it, not separate {kind}s")
                    if len(drop) < len(els):
                        # a few nested ones (4351: 1 of 4 IfcStair under another stair; F's plain count = 4) may be
                        # separate stairs; when most are nested (the D15 test model: tens per storey) they are parts
                        conf = min(conf, 0.875)
                        missing.append(f"whether the {len(drop)} nested {kind}(s) are separate {kind}s: counting every "
                                       f"{'/'.join(classes)} entity gives {len(els) + len(drop)}")
            if kind == "slab" and re.search(r"\bfloor[- ]?slabs?\b|\bfloors? (slab|plate)", fold(ctx.get("question", ""))):
                keep = [e for e in els if (e.predefined_type or "").upper() not in ("ROOF", "LANDING", "BASESLAB")
                        and not _FOUNDATION_NAME.search(fold(f"{e.name or ''} {e.type_name or ''} {e.object_type or ''}"))]
                if len(keep) < len(els):
                    trace.append(f"floor slabs: dropped {len(els) - len(keep)} roof/landing/foundation slabs "
                                 "(PredefinedType or 'pad/foundation' in the name)")
                    assumptions.append("floor slabs exclude roof slabs, stair landings and foundation pads")
                    els = keep
            if it.material == "concrete" and kind == "footing" and els:
                assumptions.append("foundations taken as concrete (the usual case; their material is not checked)")
            elif it.material and els:
                def names_of(e: Element) -> list[str]:
                    return [e.type_name or "", e.object_type or "", e.name or ""]
                by_name = [e for e in els if material_match(it.material, names_of(e))]
                by_layer = [e for e in els if material_match(it.material, list(e.materials or []))]
                if by_name:
                    trace.append(f"material '{it.material}': {len(by_name)} of {len(els)} elements name it in their "
                                 f"type/name ({len(by_layer)} have a layer of it)")
                    assumptions.append(f"{it.material} {kind}s = elements whose type or name says {it.material} "
                                       "(a layer of it inside a composite element is not counted)")
                    els = by_name
                elif by_layer:
                    fr = {}
                    for e in by_layer:
                        tot_t = sum(th for _, th in (e.layers or []))
                        if tot_t > 0:
                            fr[e.guid] = sum(th for nm, th in e.layers if material_match(it.material, [nm])) / tot_t
                    trace.append(f"material '{it.material}': {len(by_layer)} of {len(els)} elements have a layer of it"
                                 + (f"; {len(fr)} with layer thicknesses" if fr else ""))
                    if fr and it.metric == "volume":
                        ctx["layer_frac"] = fr
                        assumptions.append(f"{it.material} volume = element volume x ({it.material} layer thickness / "
                                           "total layer thickness), per element")
                    else:
                        assumptions.append(f"{it.material} {kind}s = elements with a {it.material} material layer; "
                                           "the whole element quantity is counted, not just that layer")
                    els = by_layer
                else:
                    trace.append(f"material '{it.material}': no {kind} names it in a material, type or name; kept all")
                    missing.append(f"which {kind}s are {it.material}: no material, type or name says so")
                    ctx["material_unknown"] = True
            for prop, want in it.filters.items():
                vals = [(e, next((v for k, v in e.props.items() if k.endswith("." + prop)), None)) for e in els]
                unknown = sum(1 for _, v in vals if v is None)
                if prop == "IsExternal" and els and unknown == len(els) and kind == "wall":
                    ext = external_by_outline(idx, els)
                    ext_g = {e.guid for e in ext}
                    els = [e for e in els if (e.guid in ext_g) == want]
                    trace.append(f"no wall has IsExternal: {len(ext)} walls lie on the storey outline (geometry); "
                                 f"kept {len(els)} {'external' if want else 'internal'}")
                    assumptions.append("external walls = walls on the outer outline of their storey (the model has no "
                                       "IsExternal property)")
                    ctx["geo_external"] = True
                    continue
                els = [e for e, v in vals if v is not None and bool(v) == want]
                trace.append(f"filter {prop}={want}: {len(els)} kept, {unknown} without the property")
                assumptions.append(f"{prop}={want} from Pset_*Common.{prop}")
                if unknown:
                    missing.append(f"{unknown} {kind} elements have no {prop} property (excluded)")
            return els

        if it.metric == "count":
            kinds = it.kinds or [it.kind]
            per = {k: elements_of(k) for k in kinds}
            if "wall" in kinds:
                assumptions.append("walls = IfcWall + IfcWallStandardCase (curtain walls not counted)")
            if {"sanitary", "light"} & set(kinds):
                assumptions.append("IFC2X3 IfcFlowTerminal classified by its type object")
            if where != "whole model":
                assumptions.append(f"elements whose spatial container is storey '{sname}'")
            ev = [self._ev(model, e, f"{e.eff_cls} {e.name or ''}".strip()) for k in kinds for e in per[k]][:MAX_EVIDENCE]
            for k in kinds:
                if not per[k]:
                    missing.append(f"no {k} elements found: they may be modelled as proxies or not at all")
            if it.op == "diff" and len(kinds) >= 2:
                a, b = len(per[kinds[0]]), len(per[kinds[1]])
                trace.append(f"{kinds[0]}={a}, {kinds[1]}={b}")
                if it.yes_no:
                    return Answer(value="yes" if a > b else "no", unit=None, confidence=conf * 0.9, evidence=ev,
                                  trace=trace, solver=self.name, assumptions=assumptions, missing=missing)
                return self._final(abs(a - b), "count", it, conf * 0.95, ev, trace, assumptions, missing)
            n = sum(len(v) for v in per.values())
            if it.group_by:
                return self._breakdown(idx, it, [e for k in kinds for e in per[k]], None, ev, trace, assumptions,
                                       missing, conf, where)
            if len(kinds) > 1:
                trace.append("sum: " + " + ".join(f"{k} {len(per[k])}" for k in kinds))
            conf_c = conf * (0.97 if n else 0.6)
            if n == 0 and not any(idx.by_class(*KIND_CLASSES.get(k, ())) for k in kinds):
                conf_c = min(conf_c, 0.3)  # the model has none of this class at all: maybe not modelled
                missing.append("the model has no element of this class anywhere; it may not be modelled")
            return self._final(n, "count", it, conf_c, ev, trace, assumptions, missing)

        els = elements_of(it.kind)
        if not els:
            missing.append(f"no {it.kind} elements in {where}")
            return self._final(0.0, {"area": "m2", "volume": "m3", "length": "m"}[it.metric], it, conf * 0.3, [],
                               trace, assumptions, missing)

        # ---- door / window opening area: width x height (or the Qto Area), not the footprint -------------
        if it.metric == "area" and it.kind in ("window", "door") and not it.side_area and not it.group_by:
            def opening(e: Element) -> tuple[float | None, str]:
                q = next((v for k, v in e.qto.items() if k.endswith(".Area") and v), None)
                if q:
                    return float(q), "Qto Area"
                d = e.dims or {}
                if d.get("OverallWidth") and d.get("OverallHeight"):
                    return d["OverallWidth"] * d["OverallHeight"], "OverallWidth x OverallHeight"
                return None, ""
            got = [(v, how, e) for e in els for v, how in [opening(e)] if v]
            if got:
                hows = sorted({h for _, h, _ in got})
                assumptions.append(f"{it.kind} area = opening area ({' / '.join(hows)}), not the plan footprint")
                if len(got) < len(els):
                    missing.append(f"{len(els) - len(got)} of {len(els)} {it.kind}s have no size")
                c = conf * 0.9 * len(got) / len(els)
                if it.op in ("max", "min"):
                    v0, _, e0 = (max if it.op == "max" else min)(got, key=lambda x: x[0])
                    trace.append(f"{it.op} opening area over {len(got)} {it.kind}s: {e0.name or e0.guid} {v0:.3f} m²")
                    return self._final(v0, "m2", it, c, [self._ev(model, e0, f"{e0.name or ''} {v0:.3f} m²")],
                                       trace, assumptions, missing)
                tot = sum(v for v, _, _ in got)
                trace.append(f"opening area of {len(got)} {it.kind}s = {tot:.3f} m²")
                return self._final(tot, "m2", it, c, [self._ev(model, e, f"{e.name or ''} {v:.3f} m²") for v, _, e in got],
                                   trace, assumptions, missing)

        # ---- aggregated quantities ------------------------------------------------------------------
        if it.top_n and it.kind == "space":
            zs = zone_spaces(els) if len(els) >= 3 else set()
            if zs and len(zs) < len(els):
                assumptions.append(f"{len(zs)} space(s) are area zones over other rooms (e.g. "
                                   f"'{next(e.long_name or e.name for e in els if e.guid in zs)}'), not rooms: left out")
                trace.append(f"{len(zs)} area-zone space(s) left out of the ranking")
                els = [e for e in els if e.guid not in zs]
                conf = min(conf, 0.9)
            vals = sorted(((self._floor_area(e, it, [])[0] or 0.0, e) for e in els), key=lambda x: -x[0])
            if it.op == "argmin":
                vals = vals[::-1]
            top = vals[:5]
            lines = [f"{'Largest' if it.op != 'argmin' else 'Smallest'} rooms ({where}, net floor area from geometry):"]
            lines += [f"- {e.long_name or e.name} ({e.name}) on {idx.storey(e.storey).name if e.storey else '?'}: "
                      f"{v:.2f} m²" for v, e in top]
            ev = [self._ev(model, e, f"{e.long_name or e.name} {v:.2f} m²") for v, e in top]
            assumptions.append("room size = net floor area (IfcSpace footprint)")
            return Answer(value="\n".join(lines), unit=None, confidence=conf * 0.8, evidence=ev, trace=trace,
                          solver=self.name, assumptions=assumptions, missing=missing)
        if it.metric == "area" and it.kind == "space" and it.group_by:
            ev = [self._ev(model, e, e.long_name or e.name or "") for e in els]
            return self._breakdown(idx, it, els, lambda e: self._floor_area(e, it, [])[0], ev, trace, assumptions,
                                   missing, conf, where, unit="m²")
        if it.metric == "area" and it.kind == "space" and it.gross and not it.group_by:
            # a space's own GrossFloorArea is the room's area (ArchiCAD: = net), not the storey's gross area
            stored = [_qto(e, (".GrossFloorArea",)) or next((v for k, v in e.qto.items() if k.endswith("Area")
                                                             and "Net" not in k and v), None) for e in els]
            if any(v is not None for v in stored):
                missing.append(f"the rooms' stored areas sum to {sum(v for v in stored if v):.2f} m²; the value is "
                               "the area inside the outer wall outline (gross floor area incl. walls)")
            sts = [storey.guid] if (storey is not None and where != "whole model") else \
                [st.guid for st in idx.storeys]
            outs = [(g, storey_outline(idx, g)) for g in sts]
            outs = [(g, o) for g, o in outs if o is not None]
            if outs:
                gfa = sum(o.area for _, o in outs)
                net = sum(self._floor_area(e, it, [])[0] or 0.0 for e in els)
                trace.append("gross floor area: " + ", ".join(f"{idx.storey(g).name} {o.area:.2f} m²" for g, o in outs)
                             + f" (net rooms {net:.2f} m²)")
                assumptions.append("gross floor area = area inside the outer outline of each storey's walls and rooms "
                                   "(plan footprints from the model geometry)")
                ev = [Evidence(file=model, ifc_guid=g, note=f"storey {idx.storey(g).name} outline {o.area:.2f} m²")
                      for g, o in outs]
                return self._final(gfa, "m2", it, conf * 0.6, ev, trace, assumptions, missing)
        if it.metric == "area" and it.kind == "space":
            tot, ev, srcs = 0.0, [], {}
            for e in els:
                v, how_ = self._floor_area(e, it, [])
                if v is not None:
                    tot += v
                    ev.append(self._ev(model, e, f"{e.long_name or e.name} {v:.2f} m²"))
                    k_ = "Qto" if "Qto" in how_ else "geometry"
                    srcs[k_] = srcs.get(k_, 0) + 1
            # say which source the sum used (F 04:27: an all-Qto storey total said 'footprints (geometry)')
            src_txt = (" and ".join(f"{n} from {'the explicit Qto NetFloorArea' if k_ == 'Qto' else 'the IfcSpace geometry'}"
                                    for k_, n in sorted(srcs.items(), key=lambda x: -x[1])) or "no room areas")
            assumptions.append(f"net floor area = sum of the rooms' net floor areas in {where} ({src_txt})")
            return self._final(tot, "m2", it, conf * 0.95, ev, trace, assumptions, missing)

        if it.metric == "area":
            qkey, unit, label = ("side", "m2", "side area") if (it.side_area or it.kind == "wall") else ("floor", "m2", "area")
        elif it.metric == "volume":
            qkey, unit, label = "volume", "m3", "volume"
        else:
            qkey, unit, label = "length", "m", "length"
        keys = QTO_KEYS.get((qkey, "gross" if it.gross else "net"), QTO_KEYS.get((qkey, "net")))
        tot, ev, n_q, n_geo, n_none = 0.0, [], 0, 0, 0
        geo_tot = 0.0
        use_qto = str(self.options.get("qto", "1")) != "0"
        for e in els:
            v = _qto(e, keys) if use_qto else None
            g = self._geo_value(e, qkey)
            if g is not None:
                geo_tot += g
            if v is not None:
                n_q += 1
            elif g is not None:
                v = g
                n_geo += 1
            else:
                n_none += 1
                continue
            if ctx.get("layer_frac") and e.guid in ctx["layer_frac"]:
                v *= ctx["layer_frac"][e.guid]
            tot += v
            ev.append(self._ev(model, e, f"{e.eff_cls} {e.name or ''} {label} {v:.3f}"))
        src = f"Qto {keys[0].split('.')[-1]}"
        trace.append(f"{label}: {n_q} from {src}, {n_geo} from geometry, {n_none} without either; total {tot:.3f}")
        if n_q and geo_tot and tot:
            trace.append(f"cross-check: geometry-only total {geo_tot:.3f} ({(geo_tot - tot) / tot * 100:+.1f}% vs answer)")
        if n_geo:
            how = {"volume": "closed-mesh volume", "length": "long side of the footprint's rotated bounding box",
                   "side": "volume / footprint width"}.get(qkey, "geometry")
            assumptions.append(f"{n_geo} of {len(els)} elements have no {src}; used their geometry ({how})")
            rate = GEO_HIT_RATE.get(qkey, 0.5)
            conf *= (n_q + n_geo * rate) / (n_q + n_geo)
        if n_none:
            missing.append(f"{n_none} elements have neither quantities nor geometry")
            conf *= 0.7
        assumptions.append(f"{label} = sum of {src} over {it.kind}s of {where}")
        if it.group_by:
            vals = {e.guid: (_qto(e, keys) if use_qto else None) for e in els}
            return self._breakdown(idx, it, els, lambda e: vals[e.guid] if vals[e.guid] is not None
                                   else self._geo_value(e, qkey), ev, trace, assumptions, missing, conf, where,
                                   unit={"m2": "m²", "m3": "m³", "m": "m"}[unit])
        return self._final(tot, unit, it, conf * 0.95, ev, trace, assumptions, missing)

    # ------------------------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------------------------
    _BUILDING = re.compile(r"\b(whole|entire|complete) (building|house|model|project)\b|\b(in|of|for) the (building|house)\b|"
                           r"\b(all|every) (floors|storeys|stories|levels|floor|storey|level)\b|\bbuilding[- ]wide\b|"
                           r"\bacross (all|the) (floors|storeys|levels|building)\b|\b(ganzen|gesamten) (gebaude|haus)\b|"
                           r"\bim gebaude\b|\bhele gebouw\b|\bin het gebouw\b|\btodo el edificio\b|\bdans le batiment\b")

    @staticmethod
    def _room_type_asked(idx: IfcIndex, question: str) -> bool:
        from stoa.solvers.ifc.arith import room_type_in_question

        return bool(room_type_in_question(question) or vocabulary_group(idx, _QUOTED_RX.sub(" ", question), [])[0])

    def _relation(self, path: str, model: str, idx: IfcIndex, it: Intent, question: str, trace: list[str],
                  ctx: dict) -> Answer | None:
        """Room <-> door/window relations by plan geometry (`adjacent`): "How many doors does room 'X' have?",
        "How many rooms on S have no window?", "Which rooms have a door to the corridor?" (not the last one)."""
        import dataclasses

        from stoa.solvers.ifc.arith import text_of
        from stoa.solvers.ifc.parse import _kind_hits

        tq = text_of(question)
        kinds = {"door": KIND_CLASSES["door"], "window": KIND_CLASSES["window"]}
        m = re.search(r"\b(rooms?|spaces?)\b[^?]{0,40}?\b(have|has|having|with|without|contain\w*|lack\w*)\s+"
                      r"(no|not any|any|a|an|at least one|one or more|more than one|two or more)?\s*"
                      r"(?P<k>doors?|windows?|deur\w*|tur\w*|tuer\w*|fenster\w*|ramen|raam)\b", tq)
        if m and it.kind in ("space", None, "door", "window"):
            kb = "door" if re.match(r"door|deur|tur|tuer", m.group("k")) else "window"
            q = m.group(3) or ""
            none_ = m.group(2).startswith(("without", "lack")) or q in ("no", "not any")
            many = q in ("more than one", "two or more")
            it2 = dataclasses.replace(it, metric="count", kind="space", kinds=["space"], op=None, mod=None,
                                      threshold=None, which=False, yes_no=False, top_n=False, group_by=None)
            asm: list[str] = []
            storey, rooms, conf, _g = self._roles(path, idx, it2, trace, asm)
            sp_els = (idx.in_storey(storey.guid, "IfcSpace") if storey is not None and it2.scope != "model"
                      else idx.by_class("IfcSpace"))
            if not sp_els:
                return None
            res = [(e, adjacent(idx, e, kinds[kb])) for e in sp_els]
            hit = [(e, a) for e, a in res if (len(a) == 0 if none_ else len(a) >= (2 if many else 1))]
            where_s = f"on '{storey.name}'" if storey is not None and it2.scope != "model" else "in the model"
            cond = f"{'no' if none_ else 'more than one' if many else 'at least one'} {kb}"
            trace.append(f"relation by geometry: {len(hit)} of {len(sp_els)} rooms {where_s} have {cond} "
                         f"(a {kb} footprint within 0.35 m of the room)")
            lab = lambda e: (f"{e.long_name} ({e.name})" if e.long_name and e.name and e.long_name != e.name
                             else (e.long_name or e.name or e.guid))
            ev = [self._ev(model, e, f"{lab(e)}: {len(a)} {kb}(s)") for e, a in hit][:MAX_EVIDENCE]
            asm += [f"a room has a {kb} when the {kb}'s plan footprint is within 0.35 m of the room's (geometry; "
                    "no IfcRelSpaceBoundary used)"]
            ctx["outer"] = True
            if re.match(r"\s*(which|list|name|what rooms|show)\b", tq):
                txt = f"{len(hit)} rooms {where_s} with {cond}: " + "; ".join(lab(e) for e, _ in hit[:40])
                return Answer(value=txt, unit=None, confidence=conf * 0.6, evidence=ev, trace=trace, solver=self.name,
                              assumptions=asm, missing=[])
            return self._final(len(hit), "count", it2, conf * 0.65, ev, trace, asm, [])
        # "How many doors does the room 'X' have?" / "windows in room 'X'"
        hits = [h[2] for h in _kind_hits(tq) if h[2] in kinds]
        if hits and it.names and re.search(r"\b(room|space|raum|ruimte|kamer|piece|huone)\b", tq) and \
                re.search(r"\b(how many|number of|count)\b", tq):
            sts, others = self._storey_names(idx, it)
            sg = sts[0][1].guid if sts else None
            if len(others) == 1:
                ms = match_space(idx, others[0], sg)
                if ms and ms[0].score >= 90 and ms[0].method != "fuzzy":
                    e0 = ms[0].obj
                    adj = adjacent(idx, e0, kinds[hits[0]])
                    trace.append(f"room '{others[0]}' -> {ms[0].label}; {len(adj)} {hits[0]}s within 0.35 m of its "
                                 "footprint (geometry)")
                    ctx["outer"] = True
                    return self._final(len(adj), "count", it, 0.65 * (1.0 if len(ms) == 1 else 0.6),
                                       [self._ev(model, x, f"{x.eff_cls} {x.name or ''}") for x in adj] +
                                       [self._ev(model, e0, f"room {ms[0].label}")], trace,
                                       [f"{hits[0]}s of a room = {hits[0]}s whose plan footprint is within 0.35 m of "
                                        "the room's (doors count for both rooms they connect)"], [])
        return None

    def _rest(self, path: str, model: str, idx: IfcIndex, it: Intent, question: str, trace: list[str],
              ctx: dict) -> Answer | None:
        """"All the other rooms on 'A', leaving out 'B'" / "rooms on 'A' except 'B' and 'C'": the storey's total
        minus the excluded rooms (W4 03:53: without this the excluded room's own area came back at 0.97)."""
        import dataclasses

        from stoa.solvers.ifc.parse import _EXCL

        if not it.names or it.metric not in ("area", "count") or it.kind not in ("space", None):
            return None
        qf = fold(question)
        m = _EXCL.search(qf)
        if not m:
            return None
        # by POSITION of the quoted name, not by substring: the storey 'Attic' is inside the excluded room's name
        # 'Attic (414B-11-004-011)' (W4 05:02: the storey's namesake room was subtracted too)
        qpos = [(mq.start(), fold(next((g for g in mq.groups() if g), "")).strip()) for mq in _QUOTED_RX.finditer(qf)]
        after = [n for n in it.names if any(pos >= m.start() and q_ == fold(n).strip() for pos, q_ in qpos)]
        if not qpos:
            after = [n for n in it.names if fold(n) in qf[m.start():]]
        before = [n for n in it.names if n not in after]
        st_b, oth_b = self._storey_names(idx, dataclasses.replace(it, names=before))
        if not after or oth_b:
            return None
        sg = st_b[0][1].guid if st_b else None
        ex = []
        for n in after:
            ms = match_space(idx, n, sg)
            if not ms or ms[0].score < 90:
                return None
            ex.append((n, ms[0].obj))
        base = dict(op=None, mod=None, threshold=None, which=False, yes_no=False, top_n=False, group_by=None, notes=[])
        st: list[str] = []
        whole = self._answer(path, model, idx, dataclasses.replace(it, names=before, kind="space", kinds=["space"],
                                                                   **base), st, {"question": "", "compose": False})
        if whole.value is None or isinstance(whole.value, str):
            return None
        if it.metric == "count":
            val = float(whole.value) - len(ex)
            exs = [f"{n}" for n, _ in ex]
        else:
            areas = [(n, self._floor_area(e, it, [])[0]) for n, e in ex]
            if any(a is None for _, a in areas):
                return None
            val = float(whole.value) - sum(a for _, a in areas)
            exs = [f"{n} {a:.2f} m²" for n, a in areas]
        trace.extend(st[-2:])
        trace.append(f"rest: {whole.value} {whole.unit} minus excluded {', '.join(exs)} = {val:.3f}")
        ctx["outer"] = ctx["rest_applied"] = True
        keep = {e.guid for _, e in ex}
        ev = [x for x in whole.evidence if x.ifc_guid not in keep]
        return self._final(int(val) if it.metric == "count" else val, whole.unit, it, whole.confidence * 0.95, ev,
                           trace, whole.assumptions + [f"excluded: {', '.join(n for n, _ in ex)}"], whole.missing)

    def _superlative(self, model: str, it: Intent, vals: list, conf: float, trace: list[str], assumptions: list[str],
                     missing: list[str], where_s: str, rank: int = 1) -> Answer:
        """Largest / smallest room (its area, or its name for 'which'/'name of'), or largest minus smallest."""
        def lab_of(e: Element) -> str:
            return (f"{e.long_name} ({e.name})" if e.long_name and e.name and e.long_name != e.name
                    else (e.long_name or e.name or e.guid))
        assumptions.append("room size = net floor area (IfcSpace footprint)")
        if it.op == "range":
            (v1, e1), (v0, e0) = max(vals, key=lambda x: x[0]), min(vals, key=lambda x: x[0])
            trace.append(f"largest {lab_of(e1)} {v1:.2f} m² - smallest {lab_of(e0)} {v0:.2f} m² {where_s}")
            ev = [self._ev(model, e1, f"largest {lab_of(e1)} {v1:.2f} m²"), self._ev(model, e0, f"smallest {lab_of(e0)} {v0:.2f} m²")]
            return self._final(v1 - v0, "m2", it, conf * 0.9, ev, trace, assumptions, missing)
        if it.op == "median":
            import statistics

            med = statistics.median(v for v, _ in vals)
            trace.append(f"median of {len(vals)} room areas {where_s} = {med:.3f} m²")
            return self._final(float(med), "m2", it, conf * 0.9, [self._ev(model, e, f"{lab_of(e)} {v:.2f} m²")
                                                                  for v, e in vals], trace, assumptions, missing)
        big = it.op in ("max", "argmax")
        rank = max(1, int(rank))
        zs = zone_spaces([e for _, e in vals]) if len(vals) >= 3 else set()
        if zs and len(zs) < len(vals):
            assumptions.append(f"{len(zs)} space(s) are area zones over other rooms (e.g. "
                               f"'{next(lab_of(e) for _, e in vals if e.guid in zs)}'), not rooms: left out")
            trace.append(f"{len(zs)} area-zone space(s) left out of the ranking")
            vals = [(v, e) for v, e in vals if e.guid not in zs]
            conf = min(conf, 0.85)
        order = sorted(vals, key=lambda x: x[0], reverse=big)
        v0, e0 = order[min(rank, len(order)) - 1]
        lab = lab_of(e0)
        trace.append(f"{'largest' if big else 'smallest'}{f' #{rank}' if rank > 1 else ''} of {len(vals)} rooms "
                     f"{where_s}: {lab} {v0:.2f} m²")
        ev = [self._ev(model, e0, f"{lab} {v0:.2f} m²")]
        if it.op.startswith("arg") or it.which:
            return Answer(value=f"{lab} ({v0:.2f} m²)", unit=None, confidence=conf * 0.9, evidence=ev,
                          trace=trace, solver=self.name, assumptions=assumptions, missing=missing)
        return self._final(v0, "m2", it, conf * 0.95, ev, trace, assumptions, missing)

    def _repair_intent(self, path: str, idx: IfcIndex, it: Intent, question: str, trace: list[str]) -> None:
        """Small parse repairs for wordings the templates never use (W1 probes, cycle 4)."""
        qf = fold(_QUOTED_RX.sub(" ", question))
        # two or more storeys named WITHOUT quotes ("doors on 1.korrus and 2.korrus together"): read them as if quoted
        # (Q 04:55: answered 2.korrus alone, 42 @ 0.68; gold 88)
        if not it.names and idx.storeys:
            hits = []
            for st in own_storeys(idx):
                f = fold(st.name or "")
                if (len(f) >= 3 or re.search(r"\d", f) and re.search(r"[a-z]", f)) and \
                        (mh := re.search(r"(?<![\w.])" + re.escape(f) + r"(?![\w])", qf)):
                    hits.append((mh.start(), st.name))
                elif len(f) == 2 and (st.name or "").isupper() and \
                        re.search(r"(?<![\w.])" + re.escape(st.name) + r"(?![\w])", _QUOTED_RX.sub(" ", question)):
                    # 'EG', 'KG', 'OG' as written (upper case) in the question; never a lower-case word like 'eg'
                    mh = re.search(r"(?<![\w.])" + re.escape(f) + r"(?![\w])", qf)
                    hits.append((mh.start() if mh else 0, st.name))
            hits = sorted(set(hits))
            if len(hits) >= 2 and len({n for _, n in hits}) >= 2:
                it.names = [n for _, n in hits]
                if it.op is None and not it.mod and re.search(r"\b(and|together|combined|in total|total|sum|plus|und|en|"
                                                              r"et|ja|och|i|e|y)\b", qf):
                    it.op = "sum"
                trace.append("storeys named without quotes: " + ", ".join(it.names))
        # "on all storeys above 'kjeller'", "below '2.etg'": the storeys strictly above/below the named one, summed
        # (W1 c5: answered the named storey itself at 0.97)
        if len(it.names) == 1 and it.kind not in (None, "storey") and not it.mod:
            mr = re.search(r"\b(above|over|higher than|below|under|beneath|lower than|oberhalb|uber|unterhalb|unter|boven|"
                           r"onder)\s+(?:the\s+)?(?:storey|story|floor|level|geschoss|verdieping)?\s*['\"‘’“”„«»]",
                           fold(question))
            ms_ = match_storey(idx, it.names[0]) if mr else None
            if ms_ is not None and ms_.score >= 90 and ms_.obj.elevation is not None:
                up = mr.group(1) in ("above", "over", "higher than", "oberhalb", "uber", "boven")
                z0 = ms_.obj.elevation
                rng = [st for st in own_storeys(idx) if st.elevation is not None
                       and ((st.elevation > z0 + 0.01) if up else (st.elevation < z0 - 0.01))]
                if len(rng) >= 1:
                    it.names = [st.name for st in rng] if len(rng) > 1 else [rng[0].name]
                    if len(rng) > 1:
                        it.op = "sum"
                    trace.append(f"storeys {'above' if up else 'below'} '{ms_.obj.name}' ({z0:.2f} m): "
                                 + ", ".join(st.name for st in rng))
        # "in the whole building" asked on a plan sheet, no storey named: the whole model, not the sheet's storey
        # (asked on the .ifc itself, the scope is already the whole model)
        if (Path(path).suffix.lower() != ".ifc" and it.scope != "model" and not it.names and it.mod != "share" and it.kind != "storey"
                and self._BUILDING.search(qf) and storey_mention(question, [s.name for s in idx.storeys])[0] is None):
            it.scope = "model"
            trace.append(f"scope: '{self._BUILDING.search(qf).group(0)}' -> whole model")
        # "Which floor has the fewest windows?": a superlative over elements other than rooms is a count unless an
        # area word says otherwise
        if (it.op in ("argmax", "argmin") and it.metric == "area" and it.kind not in (None, "space")
                and not re.search(r"\b(area|areas|m2|square|surface|sq|flache|flaeche|oppervlak\w*|superficie|pind)\b", qf)):
            it.metric = "count"
            trace.append("superlative without an area word: compared by count")
        # "ceiling height of the rooms", "how high is room X": the rooms' own height
        if re.search(r"\b(ceiling height|room height|clear height|height of (the )?(room|space)s?|headroom|"
                     r"(how high|how tall) is (the )?(room|space))\b", qf) or (
                it.kind == "space" and re.search(r"\b(height|high|tall)\b", qf) and
                not re.search(r"\b(how many|number of|count)\b", qf)):
            it.attr, it.kind, it.metric, it.mod, it.op = "room_height", "space", "length", None, None
        # two named storeys compared: "Does A or B contain more doors?", "By how many doors does A exceed B?",
        # "How many times larger is the room area on A than on B?", "ratio between A and B"
        st2 = [n for n in it.names if (ms_ := match_storey(idx, n)) is not None and ms_.score >= 90]
        if len(st2) == 2 and len(it.names) == 2 and not it.mod and it.kind in (None, "storey"):
            # "Has storey '-1' fewer doors than storey '0'?": the word 'storey' came first; the counted kind is doors
            from stoa.solvers.ifc.parse import _kind_hits

            ks_ = [h[2] for h in _kind_hits(qf) if h[2] != "storey"]
            if ks_:
                it.kind, it.kinds = ks_[0], [ks_[0]]
                if it.metric == "text":
                    it.metric = "count"
                trace.append(f"two storeys compared: counted kind '{ks_[0]}' (not the storeys)")
        if len(st2) == 2 and len(it.names) == 2 and not it.mod:
            if re.search(r"\b(ratio|times (larger|bigger|more|as \w+|greater|smaller)|divided by)\b", qf):
                it.op, it.which = "ratio", False
            elif re.match(r"\s*(is|are|does|do|has|have|was|were|will|would|can)\b", qf) and re.search(
                    r"\b(more|fewer|less|bigger|larger|greater|smaller|higher|lower|longer|shorter)\b[^?]{0,40}\bthan\b",
                    qf) and not re.search(r"\b(by how|how (many|much)|which|times)\b", qf):
                # "Does 'A' have more windows than 'B'?", "Are there more doors on 'A' than on 'B'?": a yes/no
                # comparison, not the difference (W5 05:10: answered |55 - 60| = 5)
                it.op, it.which, it.yes_no = ("lt2" if re.search(r"\b(fewer|less|smaller|lower|shorter)\b", qf)
                                              else "gt2"), False, True
            elif re.search(r"\b(by how (many|much)|how (many|much) (more|fewer|less)|difference|exceed\w*|"
                           r"(\w+ )?more \w+ than|than)\b", qf) and not re.search(r"\bwhich\b", qf):
                it.op, it.which, it.yes_no = "diff", False, False
            elif re.search(r"\b(more|fewer|less|bigger|larger|greater|smaller|higher|lower)\b", qf) and \
                    re.search(r"\b(or|which|what)\b", qf):
                it.which = True
                it.op = "argmin" if re.search(r"\b(fewer|less|smaller|lower)\b", qf) else "argmax"
            if it.metric == "text" and it.kind not in (None, "storey", "space"):
                it.metric = "count"
        # "Divide the total room area of S by its number of rooms"
        if not it.mod and re.search(r"\bdivid\w* .{0,60}\bby (its|the|their) (number|count) of\b", qf):
            it.mod, it.op = "avg", None
        # "Count the rooms among 'A', 'B' whose area is above 4 m²" (no 'how many')
        if not it.mod and re.search(r"\b(count|number of|how many)\b", qf) and re.search(r"\b(rooms?|spaces?)\b", qf):
            from stoa.solvers.ifc.parse import _LOWER as _LOW1, _THRESH as _TH1

            mt1 = _TH1.search(qf)
            if mt1 and re.search(r"\b(area|m2|square|size)\b", qf):
                w = mt1.group(1)
                it.threshold = ("lt" if w in _LOW1 else "gt", float(mt1.group(2).replace(",", ".")))
                it.mod, it.op, it.kind, it.metric, it.yes_no = "threshold", None, "space", "area", False
        # "How big is the room 'X'?", "what size is …": an area, not a count (Q 04:18)
        if it.metric in ("text", "count") and not re.search(r"\b(how many|number of|count)\b", qf) and re.search(
                r"\bhow (big|large)\b|\bwhat size\b|\bsize of\b|\bwie gross\b|\bhoe groot\b|\bkui suur\b|"
                r"\bjak duz\w*\b|\bque tamano\b|\bquanto (e )?grande\b|\bquelle (est la )?taille\b|\bkuinka iso\b", qf):
            it.metric = "area"
            if it.kind in (None, "storey"):
                it.kind = "space"
        # "How much bigger is the largest room than the smallest?" -> largest minus smallest
        if re.search(r"\b(largest|biggest)\b.{0,60}\b(than|and|vs|minus)\b.{0,30}\b(smallest|tiniest)\b|"
                     r"\b(difference|range)\b.{0,30}\b(largest|biggest)\b.{0,30}\b(smallest)\b", qf):
            it.op, it.kind, it.which, it.top_n = "range", "space", False, False
            if it.metric in ("text", "count"):
                it.metric = "area"
        # "How many doors are there on each floor?" (no storey named): every storey of the model
        if it.group_by == "storey" and not it.names and \
                storey_mention(question, [s.name for s in idx.storeys])[0] is None:
            it.scope = "model"
        # "What is the smallest bedroom?" names a room
        if it.op in ("max", "min") and it.metric == "text" and re.search(r"^\s*(what|which) is the (largest|biggest|"
                                                                        r"smallest|tiniest)\b", qf):
            it.op, it.which, it.metric = "arg" + it.op, True, "area"
        # "Which rooms on X are larger than 40 m²?", "rooms between 10 and 20 m²": thresholds over rooms
        from stoa.solvers.ifc.parse import _LOWER as _LOW0, _THRESH as _TH0

        mb = re.search(r"\bbetween (\d+(?:[.,]\d+)?) and (\d+(?:[.,]\d+)?)", qf)
        if mb and it.kind in ("space", None) and re.search(r"\b(rooms?|spaces?)\b", qf):
            it.threshold = ("between", float(mb.group(1).replace(",", ".")), float(mb.group(2).replace(",", ".")))
            it.mod, it.op, it.kind, it.yes_no, it.metric = "threshold", None, "space", False, "area"
            it.notes.append("between")
        mt0 = _TH0.search(qf)
        if (mt0 or mb) and it.kind in ("space", None) and re.search(r"^\s*(which|what|list|name|show|give)\b", qf) and \
                re.search(r"\b(rooms|spaces)\b", qf) and not re.search(r"\b(how many|number of|total|sum)\b", qf):
            if not mb:
                w = mt0.group(1)
                it.threshold = ("lt" if w in _LOW0 else "gt", float(mt0.group(2).replace(",", ".")))
            it.mod, it.op, it.kind, it.yes_no, it.which, it.top_n = "threshold", None, "space", False, False, False
            it.metric = "area"
            it.notes.append("threshold_list")
            trace.append("threshold list: which rooms pass")
        # ranks and medians: "the second largest room", "median room area"
        mr = re.search(r"\b(second|third|fourth|fifth|2nd|3rd|4th|5th)[- ](largest|biggest|smallest)\b", qf)
        if mr and it.kind in ("space", None):
            k = {"second": 2, "third": 3, "fourth": 4, "fifth": 5, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5}[mr.group(1)]
            it.op = ("argmax" if it.which or it.metric == "text" else "max") if mr.group(2) != "smallest" else \
                ("argmin" if it.which or it.metric == "text" else "min")
            it.kind, it.top_n = "space", False
            if it.metric in ("text", "count"):
                it.metric = "area"
            it.notes.append(f"rank:{k}")
        if re.search(r"\bmedian\b", qf) and it.kind in ("space", None) and it.metric in ("area", "text"):
            it.op, it.kind, it.metric, it.top_n, it.mod = "median", "space", "area", False, None
        # "the top / highest storey", "the lowest storey": name it
        mt_ = re.search(r"\b(top|highest|uppermost|upper ?most|lowest|bottom)\s+(storey|story|floor|level)\b", qf)
        if mt_ and not it.names and idx.storeys:
            sts = [st for st in own_storeys(idx) if st.elevation is not None] or own_storeys(idx)
            # a floor people use: the top / lowest storey that holds rooms or doors, not a roof or foundation level
            # (Q 04:55: 'top floor' on esplanades -> 'Katus' (roof), 0 doors; a person means 5.korrus)
            occ = used_storeys(idx, sts)
            top = mt_.group(1) in ("top", "highest", "uppermost", "upper most")
            asks_level = it.kind in (None, "storey")  # elevation / height / name of the level itself: the literal top
            pool = occ if occ and not asks_level else sts
            pick = (max if top else min)(pool, key=lambda st: st.elevation or 0.0)
            it.names = [pick.name]
            if it.kind is None or it.kind == "storey":
                it.kind = "storey"
            skipped = [st.name for st in sts if st not in pool and ((st.elevation or 0.0) > (pick.elevation or 0.0)) == top
                       and st is not pick]
            if skipped:
                it.notes.append("top_floor_skip:" + ", ".join(repr(x) for x in skipped))
            trace.append(f"'{mt_.group(0)}' -> storey '{pick.name}'" + (
                f" (highest/lowest storey with rooms or doors; {', '.join(repr(x) for x in skipped)} hold none)"
                if skipped else ""))
        if it.kind == "storey" and it.metric in ("count", "text") and it.names and (
                re.search(r"\bhow tall\b", qf) or (re.search(r"\bhow high\b", qf)
                                                   and re.search(r"\b(storey|story|floor|level)\b", qf))):
            it.metric = "length"
            trace.append("'how tall/high' + a storey -> storey height")
        # "the basement", "the underground level", "the cellar": the storey named so, else the highest storey below 0
        mb_ = re.search(r"\b(basement|cellar|underground|below[- ]ground|kellari\w*|keller\w*|kelder\w*|kallare\w*|"
                        r"sous[- ]sol|piwnic\w*|cantina|seminterrato|sotano|untergeschoss\w*|souterrain|kjeller\w*|"
                        r"suterena\w*|kelder)(?:\s+(?:storey|story|floor|level))?\b", qf)
        if mb_ and not it.names and idx.storeys and it.kind != "storey" and \
                storey_mention(question, [s_.name for s_ in idx.storeys])[0] is None:
            named = [st for st in own_storeys(idx) if re.search(
                r"\b(kjeller|keller\w*|kelder\w*|basement\w*|cellar|sous[- ]sol|kellari|untergeschoss|souterrain|"
                r"interrato|seminterrato|piwnica)\b|^\d+\.?\s*(ug|kg)\b|^(ug|kg)\b", fold(st.name or ""))]
            neg = sorted([st for st in own_storeys(idx) if st.elevation is not None and st.elevation < -0.5],
                         key=lambda st: -st.elevation)
            pick = named[0] if len(named) == 1 else (neg[0] if not named and neg else None)
            if pick is not None:
                it.names = [pick.name]
                it.notes.append("storey_by_role" + ("" if named else ":elevation"))
                trace.append(f"'{mb_.group(0)}' -> storey '{pick.name}' ("
                             + ("named as a basement" if named else f"highest storey below 0: {pick.elevation:.2f} m") + ")")
        # "compared to": show both values
        if re.search(r"\b(compared (to|with)|versus|vs\.?)\b", qf) and len(it.names) >= 2 and it.op in (None, "sum"):
            it.op = "compare"
        # "total floor area of the rooms smaller than 10 m²": a threshold, then a sum
        if not it.mod and it.kind in ("space", None) and it.metric == "area" and \
                re.search(r"\b(total|sum|combined|together|overall|add up)\b", qf):
            from stoa.solvers.ifc.parse import _LOWER as _LOW, _THRESH as _TH

            mt = _TH.search(qf)
            if mt and re.search(r"\b(rooms?|spaces?)\b[^.?]{0,30}" + re.escape(mt.group(0)), qf):
                w = mt.group(1)
                it.threshold = ("lt" if w in _LOW else "gt", float(mt.group(2).replace(",", ".")))
                it.mod, it.op, it.kind, it.yes_no = "threshold", None, "space", False
                it.notes.append("threshold_sum")
                trace.append(f"threshold sum: rooms {it.threshold[0]} {it.threshold[1]:g}")
        # "the name of the largest room" asks for a name, not a count
        if it.op in ("max", "min") and it.kind in ("space", None) and re.search(
                r"\bname of\b|\bwhich\b|\bwhat (room|space)\b|\bcalled\b", qf):
            it.op, it.which = "arg" + it.op, True
            it.kind = "space"
            if it.metric in ("text", "count"):
                it.metric = "area"

    def _outer(self, path: str, model: str, idx: IfcIndex, it: Intent, question: str, trace: list[str],
               ctx: dict) -> Answer | None:
        """Arithmetic around one or two atomic quantities (arith.detect): a factor or rate given in the question,
        add/remove N, a ratio, or a numeric yes/no. The atomic parts come from `_answer` (same rules, same
        evidence); the arithmetic is done here, in code. None = no outer operation (or a part failed)."""
        import dataclasses

        from stoa.solvers.ifc.arith import detect

        rest = self._rest(path, model, idx, it, question, trace, ctx)
        if rest is not None:
            return rest
        o = detect(question)
        if o is None:
            return None
        base = dict(op=None, mod=None, threshold=None, which=False, yes_no=False, top_n=False, group_by=None,
                    notes=[])

        def run(it2: Intent, q2: str | None = None) -> tuple[Answer, list[str]]:
            st: list[str] = []
            a = self._answer(path, model, idx, it2, st, {"question": q2 or question})
            return a, st

        def num(a: Answer) -> bool:
            return a.value is not None and isinstance(a.value, (int, float)) and not isinstance(a.value, bool)

        def out(val, unit, parts: list[tuple[Answer, list[str]]], steps: list[str], how: str, k: float = 0.95) -> Answer:
            conf = k
            ev, asm, miss = [], [how], []
            for a, st in parts:
                conf *= a.confidence
                ev += a.evidence
                asm += [x for x in a.assumptions if x not in asm]
                miss += [x for x in a.missing if x not in miss]
                trace.extend(st[-3:])
            trace.extend(steps)
            if isinstance(val, float):
                val = int(round(val)) if unit == "count" and abs(val - round(val)) < 1e-9 else round(val, 3)
            ctx["outer"], ctx["outer_spans"] = True, o.spans
            return Answer(value=val, unit=unit, confidence=max(0.0, min(1.0, conf)), evidence=ev[:MAX_EVIDENCE],
                          trace=trace, solver=self.name, assumptions=asm, missing=miss)

        trace.append(f"outer operation: {o.why}")
        if o.op == "mul" and o.basis is None:  # "+10%": scale the asked quantity itself
            it2 = dataclasses.replace(it, **base)
            if it2.metric == "text" and it2.kind:
                it2.metric = "count"
            if it2.kind is None:
                return None
            st: list[str] = []
            a = self._answer(path, model, idx, it2, st, {"question": question, "no_dims": True})
            if not num(a):
                return None
            val = float(a.value) * o.n
            return out(val, a.unit, [(a, st)], [f"{a.value} {a.unit} x {o.n:g} = {val:.3f}"],
                       f"{o.why}: the model quantity scaled as the question says", 0.9)
        if o.op == "wwr":
            itw = dataclasses.replace(it, metric="area", kind="window", kinds=["window"], side_area=False, filters={},
                                      material=None, asked_unit=None, **base)
            a, sa = run(itw)
            itx = dataclasses.replace(it, metric="area", kind="wall", kinds=["wall"], side_area=True, gross=True,
                                      net=False, filters={"IsExternal": True}, material=None, asked_unit=None, **base)
            b, sb = run(itx)
            if not (num(a) and num(b)) or float(b.value) <= 0:
                return None
            val = float(a.value) / float(b.value) * 100.0
            return out(val, "%", [(a, sa), (b, sb)],
                       [f"window area {a.value} m² / external wall gross side area {b.value} m² = {val:.2f}%"],
                       "window-to-wall ratio = window opening area / gross side area of the external walls", 0.85)
        if o.op in ("height", "perimeter"):
            if o.op == "height":
                tops = [(e.geo.bbox[5], e) for e in idx.elements.values() if e.geo and e.geo.bbox
                        and e.cls not in ("IfcSite", "IfcSpace", "IfcAnnotation", "IfcGrid", "IfcOpeningElement")]
                if not tops:
                    return None
                z, e0 = max(tops, key=lambda x: x[0])
                els_st = [st for st in idx.storeys if st.elevation is not None]
                g = min(els_st, key=lambda st: abs(st.elevation)) if els_st else None
                base_z = g.elevation if g is not None else min(e.geo.bbox[2] for _, e in tops)
                val = z - base_z
                trace.append(f"highest point {z:.3f} m ({e0.cls} {e0.name or e0.guid}) - ground level {base_z:.3f} m"
                             + (f" (storey '{g.name}')" if g is not None else ""))
                if o.cmp:
                    res = val > o.n
                    trace.append(f"{val:.2f} m > {o.n:g} m? -> {'yes' if res else 'no'}")
                    ans = Answer(value="yes" if res else "no", unit=None, confidence=0.7 if abs(val - o.n) > 0.5 else 0.4,
                                 evidence=[self._ev(model, e0, f"highest element, top {z:.2f} m")], trace=trace,
                                 solver=self.name, assumptions=[f"building height {val:.2f} m = highest point above "
                                                                "the ground-floor level"], missing=[])
                    ctx["outer"], ctx["outer_spans"] = True, o.spans
                    return ans
                ans = self._final(val, "m", it, 0.7, [self._ev(model, e0, f"highest element, top {z:.2f} m")], trace,
                                  [f"building height = highest point of any element above the ground-floor level "
                                   f"({'storey ' + repr(g.name) if g is not None else 'lowest element'}, "
                                   f"{base_z:.2f} m)"], [])
            else:
                storey, _r, _c, _g = self._roles(path, idx, dataclasses.replace(it, metric="length"), [], [])
                gid = storey.guid if (storey is not None and it.scope != "model") else None
                ol = storey_outline(idx, gid)
                if ol is None:
                    return None
                val = ol.length if ol.geom_type == "Polygon" else sum(p.exterior.length for p in ol.geoms)
                trace.append(f"outline of {'storey ' + repr(storey.name) if gid else 'the building'}: "
                             f"{val:.2f} m perimeter, {ol.area:.2f} m² inside")
                ans = self._final(val, "m", it, 0.6, [Evidence(file=model, ifc_guid=gid, note="outline")] if gid else [],
                                  trace, ["perimeter = length of the outer outline of the walls and rooms (plan "
                                          "footprints from the model geometry)"], [])
            ctx["outer"], ctx["outer_spans"] = True, o.spans
            return ans
        if o.op == "mul":
            if o.basis == "count":
                k = o.basis_kind or it.kind
                if k in (None, "storey"):
                    return None
                it2 = dataclasses.replace(it, metric="count", kind=k, kinds=[k], asked_unit=None, **base)
            else:
                k = o.basis_kind or (it.kind if it.kind not in (None, "storey") else ("space" if o.basis == "area" else None))
                if k is None:
                    return None
                it2 = dataclasses.replace(it, metric=o.basis, kind=k, kinds=[k], asked_unit=o.basis_unit,
                                          side_area=o.basis == "area" and (it.side_area or k == "wall"), **base)
            a, st = run(it2)
            if not num(a):
                return None
            val = float(a.value) * o.n
            unit = o.unit or a.unit
            if o.rate:  # "15 metres of wall per day": quantity / rate
                return out(val, unit, [(a, st)], [f"{a.value} {a.unit} / {o.rate:g} {o.basis_unit} per {o.per} = "
                                                  f"{val:.2f} {unit}"],
                           f"{o.why}: model quantity / the rate given in the question (constant rate assumed)", 0.9)
            return out(val, unit, [(a, st)], [f"{a.value} {a.unit} x {o.n:g} = {val:.2f} {unit or ''}"],
                       f"{o.why}: model quantity x the factor given in the question")
        if o.op in ("add", "sub"):
            it2 = dataclasses.replace(it, **base)
            if it2.metric == "text" and it2.kind:
                it2.metric = "count"
            if it2.kind is None:
                return None
            a, st = run(it2)
            if not num(a):
                return None
            val = float(a.value) + (o.n if o.op == "add" else -o.n)
            if val < 0:
                return None
            return out(val, a.unit, [(a, st)], [f"{a.value} {'+' if o.op == 'add' else '-'} {o.n:g} = {val:g}"],
                       f"model quantity {'plus' if o.op == 'add' else 'minus'} the {o.n:g} given in the question")
        if o.op == "div":
            ka, kb = o.kinds
            if ka is not None:
                ita = dataclasses.replace(it, metric="count", kind=ka, kinds=[ka], **base)
                a, sa = run(ita)
            else:
                from stoa.solvers.ifc.parse import parse as _parse

                ita = _parse(o.num_text)
                ita.question = o.num_text
                ita = dataclasses.replace(ita, **base)
                if ita.metric == "text" and ita.kind:
                    ita.metric = "count"
                if ita.kind is None or ita.kind == kb:
                    return None
                a, sa = run(ita, o.num_text)
            itb = dataclasses.replace(it, metric="count", kind=kb, kinds=[kb], filters={}, material=None,
                                      asked_unit=None, **base)
            b, sb = run(itb)
            if not (num(a) and num(b)) or float(b.value) == 0:
                return None
            val = float(a.value) / float(b.value)
            unit = None if a.unit == "count" else a.unit
            return out(val, unit, [(a, sa), (b, sb)],
                       [f"{a.value} {a.unit} / {b.value} {kb}s = {val:.4f}"], f"ratio: {o.why}")
        if o.op == "cmp":
            it2 = dataclasses.replace(it, **base)
            if it2.metric == "text" and it2.kind:
                it2.metric = "count"
            if it2.kind is None and not it2.names:
                return None
            a, st = run(it2)
            if not num(a):
                return None
            v, n = float(a.value), o.n
            res = {"gt": v > n, "ge": v >= n, "lt": v < n, "le": v <= n,
                   "eq": abs(v - n) < (1e-9 if a.unit == "count" else 0.005 * max(abs(n), 1e-9))}[o.cmp]
            sym = {"gt": ">", "ge": ">=", "lt": "<", "le": "<=", "eq": "="}[o.cmp]
            ans = out("yes" if res else "no", None, [(a, st)],
                      [f"{v:g} {a.unit or ''} {sym} {n:g}? -> {'yes' if res else 'no'}"],
                      f"yes/no: is the model quantity ({v:g} {a.unit or ''}) {sym} {n:g}")
            if a.unit != "count" and abs(v - n) <= 0.02 * max(abs(n), 1e-9):
                ans.confidence *= 0.6
                ans.missing.append(f"the value {v:g} is within 2% of {n:g}; the yes/no depends on the definition")
            return ans
        return None

    def _storey_names(self, idx: IfcIndex, it: Intent) -> tuple[list[tuple[str, Storey]], list[str]]:
        """Split the quoted names into storeys (exact/normalised match that no room matches better) and others."""
        st, other = [], []
        for n in it.names:
            ms = match_storey(idx, n)
            sp = match_space(idx, n)
            if ms is not None and ms.score >= 90 and (not sp or ms.score >= sp[0].score):
                st.append((n, ms.obj))
            else:
                other.append(n)
        return st, other

    def _compose(self, path: str, model: str, idx: IfcIndex, it: Intent, trace: list[str], ctx: dict) -> Answer | None:
        """Operators over atomic answers, for question kinds the dataset templates never use (F's hard2):
        several storeys (sum / which has more / difference), average per element, share of a total, and
        threshold counts. Each part is answered by `_answer` itself, so it keeps its own evidence and rules;
        the arithmetic happens here, in code. Returns None when no operator applies."""
        import dataclasses

        storeys, others = self._storey_names(idx, it)
        qf_ = fold(ctx.get("question", ""))
        if (not it.names and not it.mod and it.kind not in (None, "storey") and it.op in ("argmax", "argmin")
                and re.search(r"\b(which|what|welche[smr]?|welk[e]?|quel(le)?|cual|qual[e]?|mika|vilken)\s+(storey|story|"
                              r"floor|level|geschoss|stockwerk|etage|verdieping|korrus|niveau|planta|piano|kerros|vaning)",
                              qf_)
                and re.search(r"\b(most|fewest|least|largest|smallest|highest|lowest|meisten|wenigsten|meeste|minste|"
                              r"more|fewer|less|larger|bigger|greater|smaller)\b", qf_)
                and storey_mention(ctx.get("question", ""), [s_.name for s_ in idx.storeys])[0] is None):
            # "Which storey has the most doors?": every storey of the model is a candidate
            cand = [s_ for s_ in own_storeys(idx) if s_.name]
            used = used_storeys(idx, cand) if it.kind not in (None, "storey", "space") or it.metric == "count" else []
            if used and len(used) < len(cand):
                # "Which floor has the fewest doors?" -> not the roof/foundation level with 0 (Q 04:55: 'Vundament and
                # Katus (tie, 0)'); the levels left out are named in the trace
                trace.append("which-storey over the floors with rooms or doors; left out: "
                             + ", ".join(s_.name for s_ in cand if s_ not in used))
                cand = used
            storeys = [(s_.name, s_) for s_ in cand]
            it = dataclasses.replace(it, names=[n for n, _ in storeys], top_n=False)
            trace.append(f"which-storey over all {len(storeys)} storeys")
        multi = len(storeys) >= 2 and not others and (it.op in ("sum", "argmax", "argmin", "diff", "max", "min", "compare",
                                                                "ratio", "gt2", "lt2")
                                                     or it.which or (it.op is None and not it.mod
                                                                     and it.metric in ("count", "area", "volume", "length")))
        if not (multi or it.mod):
            return None
        if it.mod == "threshold" and it.metric not in ("area", "volume", "length"):
            return None

        def sub(names: list[str], ctx_extra: dict | None = None, **kw) -> tuple[Answer, list[str]]:
            args = dict(names=list(names), op=None, mod=None, threshold=None, which=False, yes_no=False, notes=[],
                        filters=dict(it.filters), kinds=list(it.kinds), group_by=None, top_n=False)
            args.update(kw)
            sit = dataclasses.replace(it, **args)
            st: list[str] = []
            a = self._answer(path, model, idx, sit, st, {"question": ctx.get("question", ""), "compose": False,
                                                         **(ctx_extra or {})})
            return a, st

        def done(val, unit, parts: list[Answer], steps: list[str], how: str, conf_k: float = 0.95) -> Answer:
            conf = conf_k
            ev, asm, miss = [], [how], []
            if len(parts) > 3:  # one rule applied to many rooms: their confidences are not independent
                conf *= min((a.confidence if a.value is not None else 0.0) for a in parts)
            for a in parts:
                if len(parts) <= 3:
                    conf *= a.confidence if a.value is not None else 0.0
                ev += a.evidence
                asm += [x for x in a.assumptions if x not in asm]
                miss += [x for x in a.missing if x not in miss]
            trace.extend(steps)
            if isinstance(val, str):
                return Answer(value=val, unit=None, confidence=max(0.0, min(1.0, conf)), evidence=ev[:MAX_EVIDENCE],
                              trace=trace, solver=self.name, assumptions=asm, missing=miss)
            if isinstance(val, float):
                val = int(round(val)) if unit == "count" and abs(val - round(val)) < 1e-9 else round(val, 3)
            return Answer(value=val, unit=unit, confidence=max(0.0, min(1.0, conf)), evidence=ev[:MAX_EVIDENCE],
                          trace=trace, solver=self.name, assumptions=asm, missing=miss)

        if multi and not it.mod:
            parts = [(n, *sub([n])) for n, _ in storeys]
            if any(a.value is None or isinstance(a.value, str) for _, a, _ in parts):
                return None
            steps = [f"{n}: {a.value} {a.unit or ''} ({'; '.join(t[-1:])})" for n, a, t in parts]
            vals = [(n, float(a.value)) for n, a, _ in parts]
            unit = parts[0][1].unit
            if it.which or it.op in ("argmax", "argmin"):
                low = it.op in ("argmin", "min") or bool(re.search(
                    r"\b(fewer|less|least|fewest|smaller|smallest|lower|weniger|kleiner|minder|kleiner|menos|menor|moins|"
                    r"meno|mniej|vahem|mindre)\b", fold(getattr(it, "question", ""))))
                pick = (min if low else max)(vals, key=lambda x: x[1])
                tied = [n for n, v in vals if v == pick[1]]
                tie = len(tied) > 1
                if tie and len(vals) > 2:
                    tie_txt = " and ".join(tied) + f" (tie, {pick[1]:g} {unit or ''} each)"
                else:
                    tie_txt = "equal (" + ", ".join(f"{n} {v:g}" for n, v in vals) + ")"
                pparts = [a for _, a, _ in parts]
                if "which-storey over all" in " ".join(trace):
                    # every storey is a candidate: empty ones are legitimate, and only the winner and the runner-up
                    # decide the answer
                    for a in pparts:
                        a.missing = [x for x in a.missing if not x.startswith("no ")]
                    order = sorted(range(len(vals)), key=lambda i: vals[i][1], reverse=not low)
                    pparts = [parts[i][1] for i in order[:2]]
                return done(pick[0] if not tie else tie_txt,
                            None, pparts, steps + [f"{it.op} over storeys -> {pick[0]}"],
                            f"compared {it.metric} per storey", 0.95 if not tie else 0.6)
            if it.op == "ratio" and len(vals) == 2 and vals[1][1]:
                r_ = vals[0][1] / vals[1][1]
                return done(r_, None, [a for _, a, _ in parts], steps + [f"{vals[0][1]:g} / {vals[1][1]:g} = {r_:.4f}"],
                            f"ratio of {it.metric} {vals[0][0]} / {vals[1][0]}")
            if it.op == "compare":
                txt = ", ".join(f"{n}: {v:g} {unit if unit != 'count' else ''}".strip() for n, v in vals)
                if len(vals) == 2:
                    d = vals[0][1] - vals[1][1]
                    txt += (f" (equal)" if abs(d) < 1e-9 else f" ({vals[0][0]} has {abs(d):g} "
                            f"{'more' if d > 0 else 'fewer' if unit == 'count' else 'less'})")
                return done(txt, None, [a for _, a, _ in parts], steps, f"compared {it.metric} per storey", 0.95)
            if it.op in ("gt2", "lt2") and len(vals) == 2:
                (na, va), (nb, vb) = vals
                res = va > vb if it.op == "gt2" else va < vb
                u_ = f" {unit}" if unit and unit != "count" else ""
                rel = "more than" if va > vb else "fewer than" if va < vb else "the same as"
                if unit != "count" and va != vb:
                    rel = "more than" if va > vb else "less than"
                txt = f"{'yes' if res else 'no'} ({na}: {va:g}{u_}, {rel} {nb}: {vb:g}{u_})"
                return done(txt, None, [a for _, a, _ in parts],
                            steps + [f"{va:g} {'>' if it.op == 'gt2' else '<'} {vb:g}? -> {'yes' if res else 'no'}"],
                            "yes/no comparison of two storeys", 0.95)
            if it.op == "diff" and len(vals) == 2:
                return done(abs(vals[0][1] - vals[1][1]), unit, [a for _, a, _ in parts],
                            steps + [f"|{vals[0][1]:g} - {vals[1][1]:g}|"], "difference between two storeys")
            if it.op in ("max", "min"):
                v = (max if it.op == "max" else min)(v for _, v in vals)
                return done(v, unit, [a for _, a, _ in parts], steps + [f"{it.op} = {v:g}"], f"{it.op} over storeys")
            tot = sum(v for _, v in vals)
            return done(int(tot) if unit == "count" else tot, unit, [a for _, a, _ in parts],
                        steps + ["sum = " + " + ".join(f"{v:g}" for _, v in vals)], "sum over the named storeys")

        if it.mod == "avg" and it.metric == "count":
            # an average of a COUNT needs a denominator other than the elements themselves ("per storey")
            if not re.search(r"\bper (storey|story|floor|level|etage|geschoss|verdieping)\b", fold(ctx.get("question", ""))):
                return None
            tot, t1 = sub(it.names, scope="model" if not it.names else it.scope)
            if tot.value is None or isinstance(tot.value, str):
                return None
            n_st = len(idx.storeys)
            return done(float(tot.value) / n_st, None, [tot],
                        [f"total {tot.value} ({t1[-1] if t1 else ''})", f"{n_st} storeys",
                         f"average = {tot.value} / {n_st}"],
                        f"average per storey = total / number of IfcBuildingStoreys ({n_st}, incl. any foundation/roof levels)",
                        0.8)
        if it.mod == "avg":
            tot, t1 = sub(it.names)
            cnt, t2 = sub(it.names, metric="count")
            if tot.value is None or cnt.value in (None, 0) or isinstance(tot.value, str):
                return None
            return done(float(tot.value) / float(cnt.value), tot.unit, [tot, cnt],
                        [f"total {tot.value} {tot.unit} ({t1[-1] if t1 else ''})", f"count {cnt.value}",
                         f"average = {tot.value} / {cnt.value}"], f"average = total {it.metric} / number of {it.kind} elements")

        if it.mod == "share":
            if others and storeys:  # "share of storey S's area that room R takes"
                part, t1 = sub(others + [n for n, _ in storeys])
                whole, t2 = sub([n for n, _ in storeys], total=True, kind="space" if it.metric == "area" else it.kind)
                wdesc = f"all {it.kind or 'rooms'} on '{storeys[0][0]}'"
            elif it.filters and not others:  # "percentage of wall volume that is load-bearing"
                part, t1 = sub([n for n, _ in storeys])
                whole, t2 = sub([n for n, _ in storeys], filters={})
                wdesc = f"all {it.kind}s" + (f" on '{storeys[0][0]}'" if storeys else "")
            elif storeys and it.kind in (None, "space") and self._room_type_asked(idx, ctx.get("question", "")):
                # "what percentage of the rooms (area) on S are bathrooms": part = that type on S, whole = all rooms on S
                part, t1 = sub([n for n, _ in storeys])
                whole, t2 = sub([n for n, _ in storeys], ctx_extra={"no_room_type": True}, kind="space")
                wdesc = f"all rooms on '{storeys[0][0]}'"
            elif storeys:  # "share of the model's doors on storey S"
                part, t1 = sub([n for n, _ in storeys], scope="storey")
                whole, t2 = sub([], scope="model")
                wdesc = f"the whole model"
            else:
                return None
            if part.value is None or whole.value in (None, 0) or isinstance(part.value, str) or isinstance(whole.value, str):
                return None
            pct = float(part.value) / float(whole.value) * 100.0
            return done(pct, "%", [part, whole], [f"part {part.value} {part.unit}", f"whole ({wdesc}) {whole.value} {whole.unit}",
                                                  f"share = {part.value} / {whole.value} x 100 = {pct:.2f}%"],
                        f"share = part / {wdesc} x 100")

        if it.mod == "threshold":
            op, thr = it.threshold[0], it.threshold[1]
            if it.asked_unit == "ft2":
                thr /= FT2_PER_M2
            elif it.asked_unit == "ft":
                thr /= FT_PER_M
            hi_thr = it.threshold[2] if len(it.threshold) > 2 else None
            if hi_thr is not None and it.asked_unit == "ft2":
                hi_thr /= FT2_PER_M2
            cmp = {"gt": lambda v: v > thr, "ge": lambda v: v >= thr, "lt": lambda v: v < thr, "le": lambda v: v <= thr,
                   "between": lambda v: thr <= v <= (hi_thr if hi_thr is not None else thr)}[op]
            sn = [n for n, _ in storeys]
            if others:
                parts = [(n, *sub([n] + sn)) for n in others]
            else:  # every room of the storey (named, or the sheet's), or of the whole model
                if it.kind != "space":
                    return None
                if storeys:
                    els = idx.in_storey(storeys[0][1].guid, "IfcSpace")
                else:
                    ps, _ = plan_storey(path, idx)
                    whole_m = it.scope == "model" or ps is None
                    els = idx.by_class("IfcSpace") if whole_m else idx.in_storey(ps.guid, "IfcSpace")
                    trace.append("threshold over every room " + ("of the model" if whole_m else f"on the sheet's storey '{ps.name}'"))
                parts = []
                for e in els:
                    v, _ = self._floor_area(e, it, [])
                    lab_e = (f"{e.long_name} ({e.name})" if e.long_name and e.name and e.long_name != e.name
                             else (e.long_name or e.name))
                    parts.append((lab_e, Answer(value=v, unit="m2", confidence=0.97,
                                                                evidence=[self._ev(model, e, f"{e.long_name or e.name} {v or 0:.2f} m²")]), []))
            if any(a.value is None or isinstance(a.value, str) for _, a, _ in parts):
                return None
            unit_si = {"area": "m2", "volume": "m3", "length": "m"}[it.metric]
            # sub-answers came back in the asked unit; compare in SI
            def si(a: Answer) -> float:
                v = float(a.value)
                return v / FT2_PER_M2 if a.unit == "ft2" else v / FT_PER_M if a.unit == "ft" else v
            hit = [(n, si(a)) for n, a, _ in parts if cmp(si(a))]
            sym = {"gt": ">", "ge": ">=", "lt": "<", "le": "<=", "between": "between"}[op]
            steps = [f"{n}: {si(a):.2f} {unit_si} {'✓' if cmp(si(a)) else '-'}" for n, a, _ in parts]
            if ctx.get("threshold_list"):
                names_hit = [n for n, a, _ in parts if cmp(si(a))]
                txt = (f"{len(names_hit)} rooms with {it.metric} {sym} {thr:g} {unit_si}"
                       + (": " + "; ".join(f"{n} ({v:.2f} {unit_si})" for n, v in hit[:40]) if hit else "")
                       + (" ..." if len(hit) > 40 else ""))
                ans = done(txt, None, [a for _, a, _ in parts], steps + [f"{len(hit)} of {len(parts)} listed"],
                           f"rooms with {it.metric} {sym} {thr:g} {unit_si}")
                ans.evidence = [ev for (n, a, _) in parts if cmp(si(a)) for ev in a.evidence] or ans.evidence
                return ans
            if ctx.get("threshold_sum"):
                tot = sum(v for _, v in hit)
                ans = done(tot, unit_si, [a for _, a, _ in parts], steps + [f"sum of the {len(hit)} of {len(parts)} with "
                                                                          f"{sym} {thr:g} {unit_si} = {tot:.3f}"],
                           f"total {it.metric} of the rooms with {it.metric} {sym} {thr:g} {unit_si}")
                ans.evidence = [ev for (n, a, _) in parts if cmp(si(a)) for ev in a.evidence] or ans.evidence
                return ans
            ans = done(len(hit), "count", [a for _, a, _ in parts], steps + [f"{len(hit)} of {len(parts)} have {sym} {thr:g} {unit_si}"],
                       f"count of the {len(parts)} {'named ' if others else ''}rooms with {it.metric} {sym} {thr:g} {unit_si}")
            ans.evidence = [ev for (n, a, _) in parts if cmp(si(a)) for ev in a.evidence] or ans.evidence
            return ans
        return None

    # ------------------------------------------------------------------------------------------------
    def _llm_fallback(self, model: str, idx: IfcIndex, question: str, it: Intent, refusal: Answer,
                      storey: Storey | None = None, extra: str | None = None) -> Answer:
        """Free-text questions the rules can't answer: local LLM over a deterministic fact card of the model."""
        from stoa.solvers.ifc.factcard import answer_free_text

        if storey is None:
            i, _ = storey_mention(question, [s.name for s in idx.storeys])
            storey = idx.storeys[i] if i is not None else None
        text, card, info = answer_free_text(idx, question, it, storey=storey, extra=extra)
        trace = list(refusal.trace) + ["rules could not answer; asking the local LLM with a fact card of the model "
                                       f"({len(card.splitlines())} lines, {len(card)} chars)"]
        if text is None:
            trace.append(f"LLM unavailable: {info.get('error')}")
            return Answer(value=None, solver=self.name, trace=trace, missing=refusal.missing)
        trace.append("fact card (first lines): " + " | ".join(card.splitlines()[:4])[:400])
        ev = []
        if it.kind:
            ev = [self._ev(model, e, f"{e.eff_cls} {e.name or ''}".strip())
                  for e in idx.by_class(*KIND_CLASSES.get(it.kind, ()))[:50]]
        if not ev:
            ev = [Evidence(file=model, note="IFC model (fact card source)")]
        return Answer(value=text, unit=None, confidence=0.3, evidence=ev, trace=trace, solver=self.name,
                      assumptions=["answered by the local LLM from facts extracted from the IFC (counts, types, "
                                   "materials, fire ratings, rooms); not verified by a rule"],
                      missing=list(refusal.missing))

    # ------------------------------------------------------------------------------------------------
    def _dims_answer(self, model: str, idx: IfcIndex, it: Intent, trace: list[str], ctx: dict) -> Answer | None:
        """Door/window width or height (IfcDoor/IfcWindow OverallWidth/OverallHeight) and wall/slab thickness
        (sum of the material layer thicknesses): largest / smallest (+ which type) / average / distribution."""
        q = fold(ctx.get("question", ""))
        m = _DIM_WORD.search(q)
        if not m or it.kind not in ("door", "window", "wall", "slab", "roof", "covering"):
            return None
        word = m.group(1)
        attr = ("thickness" if re.match(r"thick|thin|dick|dikte|epaisseur|espesor|spessore|paksuus|tjock", word)
                else "OverallHeight" if re.match(r"heigh|tall|hoh|hoeh|hoogte|haut|alt|korkeus|hojd", word)
                else "OverallWidth")
        if attr == "thickness" and it.kind in ("door", "window"):
            return None
        if attr != "thickness" and it.kind not in ("door", "window"):
            return None
        assumptions: list[str] = []
        missing: list[str] = []
        i, _ = storey_mention(ctx.get("question", ""), [s.name for s in idx.storeys])
        storey = ctx.get("dims_storey") or (idx.storeys[i] if i is not None else None)
        els = idx.by_class(*KIND_CLASSES[it.kind])
        if storey is not None:
            els = [e for e in els if e.storey == storey.guid]
        where = f"on '{storey.name}'" if storey is not None else "in the model"
        for prop, want in it.filters.items():
            els = [e for e in els if next((v for k, v in e.props.items() if k.endswith("." + prop)), None) is not None
                   and bool(next(v for k, v in e.props.items() if k.endswith("." + prop))) == want]
            assumptions.append(f"{prop}={want} from Pset_*Common.{prop}")
        tk = _type_key_fn(els)
        layer_fam = None
        if attr == "thickness":
            mq = _MATERIAL_Q.search(q)
            layer_fam = it.material or (material_family(mq.group(1)) if mq else None)

        def value(e: Element) -> float | None:
            if attr == "thickness":
                if not e.layers:
                    w = next((v for k, v in e.qto.items() if k.endswith(".Width")), None)
                    return w if (w and not layer_fam) else None
                if layer_fam:
                    t = sum(th for nm, th in e.layers if material_match(layer_fam, [nm]))
                    return t or None
                return sum(th for _, th in e.layers) or None
            d = e.dims or {}
            if attr in ("OverallWidth", "OverallHeight") and e.guid in swapped:
                return d.get("OverallHeight" if attr == "OverallWidth" else "OverallWidth")
            return d.get(attr)

        # width/height exported swapped on some instances of a type (digital_hub: 4 of 8 escape doors 2.27 x 0.95,
        # the other 4 0.95 x 2.27): if a sibling of the same type has the transposed size and the element is a
        # door lying on its side (width > height), read it the sibling's way (W1 c5)
        swapped: set[str] = set()
        if attr in ("OverallWidth", "OverallHeight"):
            by_type: dict[str, list[tuple[float, float]]] = {}
            for e in els:
                d = e.dims or {}
                if d.get("OverallWidth") and d.get("OverallHeight"):
                    by_type.setdefault(tk(e), []).append((round(d["OverallWidth"], 3), round(d["OverallHeight"], 3)))
            for e in els:
                d = e.dims or {}
                w_, h_ = d.get("OverallWidth"), d.get("OverallHeight")
                if w_ and h_ and e.cls.startswith("IfcDoor") and w_ > h_ and \
                        (round(h_, 3), round(w_, 3)) in by_type.get(tk(e), []):
                    swapped.add(e.guid)
            if swapped:
                trace.append(f"{len(swapped)} door(s) have width and height swapped against other doors of their type: "
                             "read transposed")
                assumptions.append(f"{len(swapped)} door(s) export OverallWidth/OverallHeight swapped (same type, "
                                   "transposed size elsewhere); read as their siblings")

        vals = [(value(e), e) for e in els]
        vals = [(v, e) for v, e in vals if v is not None and v > 0]
        what = {"OverallWidth": "width", "OverallHeight": "height", "thickness": "thickness"}[attr]
        whats = what + ("es" if what.endswith("s") else "s")

        def label(e: Element) -> str:  # type key, plus the shared element name when it says something else
            t, nm = tk(e), strip_id(e.name)
            return f"{t} / {nm}" if nm and nm != t and nm not in t and t not in nm else t
        noun = it.kind.replace("_", " ")
        src = ("IfcDoor/IfcWindow Overall" + ("Width" if attr == "OverallWidth" else "Height")) if attr != "thickness" \
            else ("thickness of the " + layer_fam + " layer(s)" if layer_fam else "sum of the material layer thicknesses")
        trace.append(f"dimension question: {noun} {what} from {src}; {len(vals)} of {len(els)} {noun}s {where} have it")
        assumptions.append(f"{what} = {src}")
        if not vals:
            return Answer.abstain(self.name, f"no {noun} {what} in the model", trace=trace,
                                  missing=[f"{noun} {what} ({src})"])
        conf = 0.9 * (0.7 if len(vals) < 0.8 * len(els) else 1.0)
        if len(vals) < len(els):
            missing.append(f"{len(els) - len(vals)} {noun}s have no {what}")
        ev_all = [self._ev(model, e, f"{tk(e)} {what} {v * 1000:.0f} mm") for v, e in vals][:MAX_EVIDENCE]
        mm = lambda v: f"{v * 1000:.0f} mm"  # noqa: E731
        asks_type = bool(re.search(r"\b(type|types|which|what kind|family)\b", q))
        thr = _DIM_THRESHOLD.search(q)
        if thr and (it.metric == "count" or re.search(r"\b(how many|number of|count|wie viele|hoeveel|combien)\b", q)):
            num = float(thr.group("num").replace(",", "."))
            u = thr.group("unit") or ""
            lim = num / 1000 if u == "mm" or (not u and num > 20) else num / 100 if u == "cm" else num
            gt = not re.match(r"(narrow|small|less|under|below|thinn|short|lower|schmal|klein|wenig|minder|smal|"
                              r"moins|meno|menos|at most|no more)", thr.group("cmp"))
            ge = bool(re.match(r"(at least|minimum|min\.?|mindestens|minstens|au moins|no less)", thr.group("cmp")))
            hit = [(v, e) for v, e in vals if ((v > lim + 5e-4) or (ge and abs(v - lim) <= 5e-4))] if gt else \
                [(v, e) for v, e in vals if (v < lim - 5e-4)]
            trace.append(f"threshold: {what} {'>=' if ge else '>' if gt else '<'} {lim:.3f} m -> {len(hit)} of "
                         f"{len(vals)} {noun}s")
            ev = [self._ev(model, e, f"{label(e)} {what} {mm(v)}") for v, e in hit][:MAX_EVIDENCE]
            return self._final(len(hit), "count", it, conf * 0.95, ev, trace, assumptions, missing)
        if re.search(r"\b(average|mean|typical|durchschnitt\w*|gemiddeld\w*|moyenne|media|promedio)\b", q):
            avg = sum(v for v, _ in vals) / len(vals)
            trace.append(f"average over {len(vals)}: {avg:.4f} m")
            return self._final(avg, "m", it, conf * 0.95, ev_all, trace, assumptions, missing)
        op = ("max" if re.search(r"\b(largest|widest|biggest|maximum|max|tallest|highest|thickest|greatest|largest)\b", q)
              else "min" if re.search(r"\b(smallest|narrowest|minimum|min|lowest|shortest|thinnest|least)\b", q)
              else None)
        nm_ = re.search(r"\b(top|largest|biggest|widest|tallest|highest|thickest|smallest|narrowest|thinnest|lowest|first)"
                        r"\s+(\d+|two|three|four|five|six|seven|eight|nine|ten)\b|\b(\d+|two|three|four|five|six|seven|"
                        r"eight|nine|ten)\s+(largest|biggest|widest|tallest|highest|thickest|smallest|narrowest|thinnest|"
                        r"lowest)\b", q)
        top_k = 1
        if nm_:
            w = nm_.group(2) or nm_.group(3)
            top_k = int(w) if w.isdigit() else ["two", "three", "four", "five", "six", "seven", "eight", "nine",
                                                 "ten"].index(w) + 2
        if op and top_k > 1:
            distinct = sorted({round(v, 4) for v, _ in vals}, reverse=(op == "max"))[:top_k]
            lines = [f"{'Largest' if op == 'max' else 'Smallest'} {top_k} {noun} {whats} {where} ({src}):"]
            ev = []
            for r_, v0 in enumerate(distinct, 1):
                hit = [e for v, e in vals if abs(v - v0) < 5e-4]
                types = Counter(label(e) for e in hit)
                lines.append(f"{r_}. {mm(v0)}: " + "; ".join(f"{t} ({n})" for t, n in types.most_common(3)))
                ev += [self._ev(model, e, f"{label(e)} {what} {mm(v0)}") for e in hit][:20]
            trace.append(f"top {top_k} distinct {whats} ({op})")
            return Answer(value="\n".join(lines), unit=None, confidence=conf * 0.9, evidence=ev, trace=trace,
                          solver=self.name, assumptions=assumptions, missing=missing)
        if op:
            v0 = (max if op == "max" else min)(v for v, _ in vals)
            hit = [e for v, e in vals if abs(v - v0) < 5e-4]
            types = Counter(label(e) for e in hit)
            trace.append(f"{op} {what}: {v0:.4f} m on {len(hit)} {noun}s; types {dict(types.most_common(4))}")
            ev = [self._ev(model, e, f"{tk(e)} {what} {mm(v0)}") for e in hit][:200]
            if not asks_type:
                return self._final(v0, "m", it, conf, ev, trace, assumptions, missing)
            label = {"max": "Largest", "min": "Smallest"}[op]
            lines = [f"{label} {noun} {what} {where}: {mm(v0)} ({v0:.3f} m)",
                     f"{noun.capitalize()} type{'s' if len(types) > 1 else ''} with this {what}: "
                     + "; ".join(f"{t} ({n} {noun}{'s' if n > 1 else ''})" for t, n in types.most_common(5))]
            return Answer(value="\n".join(lines), unit=None, confidence=conf, evidence=ev, trace=trace,
                          solver=self.name, assumptions=assumptions, missing=missing)
        if re.search(r"\btypes?\b", q):  # "wall types and their thicknesses": one line per type (all elements)
            per: dict[str, list[float | None]] = {}
            for e in els:
                per.setdefault(label(e), []).append(value(e))
            lines = [f"{noun.capitalize()} types {where} with their {what} ({len(per)} types, {len(els)} {noun}s; "
                     f"{what} from {src}):"]
            for t, vs in sorted(per.items(), key=lambda x: (-len(x[1]), x[0]))[:60]:
                got = [v for v in vs if v]
                if got:
                    lo, hi = min(got), max(got)
                    rng = mm(lo) if abs(hi - lo) < 5e-4 else f"{lo * 1000:.0f}-{hi * 1000:.0f} mm"
                else:
                    rng = f"{what} not in the model"
                lines.append(f"- {t}: {len(vs)} {noun}{'s' if len(vs) > 1 else ''} ({len(vs) / len(els) * 100:.1f}%), {rng}")
            if len(per) > 60:
                lines.append(f"- ... {len(per) - 60} more types")
            return Answer(value="\n".join(lines), unit=None, confidence=conf * 0.85, evidence=ev_all, trace=trace,
                          solver=self.name, assumptions=assumptions, missing=missing)
        # distribution: "different wall thicknesses and how many walls have each"
        dist = Counter(round(v * 1000) for v, _ in vals)
        by_t: dict[int, Counter] = {}
        for v, e in vals:
            by_t.setdefault(round(v * 1000), Counter())[tk(e)] += 1
        lines = [f"{noun.capitalize()} {whats} {where} ({len(vals)} {noun}s, {len(dist)} distinct values; {src}):"]
        for t_mm, n in sorted(dist.items(), key=lambda x: -x[0])[:30]:
            tps = by_t[t_mm]
            lines.append(f"- {t_mm} mm: {n} {noun}{'s' if n > 1 else ''}"
                         + (f" ({'; '.join(f'{t} x{c}' for t, c in tps.most_common(3))})" if asks_type or len(tps) <= 3 else ""))
        if len(dist) > 30:
            lines.append(f"- ... {len(dist) - 30} more values")
        return Answer(value="\n".join(lines), unit=None, confidence=conf * 0.85, evidence=ev_all, trace=trace,
                      solver=self.name, assumptions=assumptions, missing=missing)

    # ------------------------------------------------------------------------------------------------
    @staticmethod
    def _kind_fallback(idx: IfcIndex, kind: str, storey: Storey | None, trace: list[str],
                       assumptions: list[str]) -> list[Element]:
        """The model has no element of the kind's classes: try where exporters usually put them instead."""
        def scoped(els: list[Element]) -> list[Element]:
            return [e for e in els if storey is None or e.storey == storey.guid]

        fb = FALLBACK_CLASSES.get(kind)
        if fb and idx.by_class(*fb):
            els = scoped(idx.by_class(*fb))
            trace.append(f"no {'/'.join(KIND_CLASSES.get(kind, ()))} in the model; {kind} -> {'/'.join(fb)}: {len(els)}")
            assumptions.append(f"{kind.replace('_', ' ')}s = {'/'.join(fb)} (the model has no "
                               f"{'/'.join(KIND_CLASSES.get(kind, ()))}; IFC2X3 exports them so)")
            return els
        if kind == "roof":
            els = scoped([e for e in idx.by_class("IfcSlab", "IfcCovering")
                          if (e.predefined_type or "").upper() in ("ROOF", "ROOFING")])
            if els:
                trace.append(f"no IfcRoof; slabs/coverings typed ROOF/ROOFING: {len(els)}")
                assumptions.append("roof = IfcSlab ROOF / IfcCovering ROOFING (the model has no IfcRoof)")
                return els
        if kind == "footing":
            els = scoped([e for e in idx.by_class("IfcSlab", "IfcWall", "IfcWallStandardCase", "IfcBeam", "IfcPile",
                                                   "IfcBuildingElementProxy")
                          if (e.predefined_type or "").upper() == "BASESLAB" or _FOUNDATION_NAME.search(
                              fold(f"{e.name or ''} {e.type_name or ''} {e.object_type or ''}"))])
            if els:
                trace.append(f"no IfcFooting; elements named/typed as foundation: {len(els)}")
                assumptions.append("foundation = elements typed BASESLAB or named foundation/footing/pad (no IfcFooting)")
                return els
        words = NAME_FALLBACK.get(kind)
        if words:
            pat = re.compile(r"(?<![a-z])(" + "|".join(re.escape(w) for w in words) + ")")
            pool = [e for e in idx.elements.values() if e.cls in _GENERIC_CLASSES]
            els = scoped([e for e in pool if pat.search(fold(f"{e.name or ''} {e.type_name or ''} {e.object_type or ''}"))])
            if els:
                trace.append(f"no {'/'.join(KIND_CLASSES.get(kind, ()))} in the model; {len(els)} proxy/generic "
                             f"elements named like '{words[0]}'")
                assumptions.append(f"{kind}s = proxy/generic elements whose name says '{words[0]}' (the model has no "
                                   f"{'/'.join(KIND_CLASSES.get(kind, ()))})")
            return els
        return []

    # ------------------------------------------------------------------------------------------------
    def _breakdown(self, idx: IfcIndex, it: Intent, els: list[Element], value_of, ev, trace, assumptions, missing,
                   conf: float, where: str, unit: str | None = None) -> Answer:
        """Text answer: total + breakdown by type name or by storey (IFC-Bench style)."""
        if not els:  # nothing matched (a filter the elements lack, a broad question): let the fact card answer
            return Answer.abstain(self.name, f"breakdown of {it.kind} in {where}: no matching elements", trace=trace,
                                  missing=missing or [f"{it.kind} elements matching the question"])
        groups: dict[str, list[float]] = {}
        members: dict[str, list[Element]] = {}
        type_key = _type_key_fn(els)
        for e in els:
            if it.group_by == "storey":
                st_ = idx.storey(e.storey) if e.storey else None
                key = st_.name if st_ else "(no storey)"
                if st_ is not None and len(buildings_of(idx)) > 1 and st_.building != main_building(idx):
                    key = f"{st_.name} ({st_.building})"  # neighbours' storeys share the main building's names
            else:
                key = type_key(e)
            v = 1.0 if value_of is None else (value_of(e) or 0.0)
            groups.setdefault(key, []).append(v)
            members.setdefault(key, []).append(e)
        if it.group_by == "type" and len(groups) > 3 and sum(len(v) == 1 for v in groups.values()) > len(groups) / 2:
            merged: dict[str, list[float]] = {}
            merged_m: dict[str, list[Element]] = {}
            for k, v in groups.items():  # per-instance names 'EG-Treppe-01'..'-10' -> 'EG-Treppe'
                k2 = re.sub(r"[\s\-_.:]*\d+$", "", k) or k
                merged.setdefault(k2, []).extend(v)
                merged_m.setdefault(k2, []).extend(members[k])
            trace.append(f"type names look per-instance ({len(groups)} groups); merged numbering -> {len(merged)}")
            groups, members = merged, merged_m
        total = sum(sum(v) for v in groups.values())
        noun = (it.kinds[0] if it.kinds else it.kind or "element").replace("_", " ")
        plural = (noun[:-1] + "ies" if noun.endswith("y") and noun[-2:-1] not in "aeiou"
                  else noun + "es" if noun.endswith(("s", "x", "ch", "sh")) else noun + "s")
        fmt = (lambda x: f"{int(round(x))}") if value_of is None else (lambda x: f"{x:.2f} {unit or ''}".strip())
        if it.group_by == "storey":
            order = [s.name for s in idx.storeys if s.name in groups] + [k for k in groups if k not in
                                                                        {s.name for s in idx.storeys}]
        else:
            order = sorted(groups, key=lambda k: -sum(groups[k]))
        lines = [f"Total {plural} ({where}): {fmt(total)}", f"By {'storey' if it.group_by == 'storey' else 'type'}:"]
        q = fold(it.question or "")
        want_mat = bool(re.search(r"\bmaterials?\b|made of|composition|composed|layers?\b|build[- ]?up|materia\w*|"
                                  r"werkstoff|baustoff", q))
        list_rooms = (it.kind == "space" and value_of is not None and len(els) <= 60)
        want_size = bool(re.search(r"\b(sizes?|dimensions?|widths?|heights?|grosse|abmessung\w*|afmeting\w*|maat)\b", q)
                         and it.kind in ("door", "window"))
        for k in order[:25]:
            sub = sum(groups[k])
            share = f" ({sub / total * 100:.1f}%)" if total else ""
            cnt = f", {len(groups[k])} elements" if value_of is not None else ""
            shown = f"'{k}'" if k != k.strip() else k  # trailing spaces: a different name in the model
            lines.append(f"- {shown}: {fmt(sub)}{share}{cnt}")
            if want_mat:
                combos = Counter(tuple(m for m in (e.materials or []) if m and m.strip() and "<unnamed>" not in m.lower())
                                 for e in members[k])
                best = next((c for c, _ in combos.most_common() if c), None)
                if best:
                    lines.append("    materials: " + ", ".join(best))
            if want_size:
                sizes = Counter(f"{e.dims['OverallWidth']:.2f} m x {e.dims['OverallHeight']:.2f} m" for e in members[k]
                                if e.dims and "OverallWidth" in e.dims and "OverallHeight" in e.dims)
                for sz, c in sizes.most_common(12):
                    lines.append(f"    {sz} (W x H): {c} ({c / len(members[k]) * 100:.0f}%)")
            if list_rooms:
                for e in sorted(members[k], key=lambda e: -(value_of(e) or 0.0)):
                    nm = e.long_name or e.name or "(unnamed)"
                    lab = f"{nm} ({e.name})" if e.long_name and e.name and e.name != e.long_name else nm
                    lines.append(f"    - {lab}: {fmt(value_of(e) or 0.0)}")
        if len(order) > 25:
            lines.append(f"- ... {len(order) - 25} more groups")
        if want_mat:
            uniq = sorted({m for e in els for m in (e.materials or []) if m and m.strip() and "<unnamed>" not in m.lower()})
            if uniq:
                lines.append(f"Unique materials ({len(uniq)}): " + ", ".join(uniq[:40]) + (" ..." if len(uniq) > 40 else ""))
        trace.append(f"breakdown by {it.group_by}: {len(groups)} groups")
        assumptions.append(f"type = {getattr(type_key, 'how', 'type name')}" if it.group_by == "type"
                           else "storey = the element's spatial container")
        if it.group_by == "type" and re.search(r"\bhow many (different |distinct |unique )?(\w+ ){0,2}(types|kinds)\b|"
                                              r"\bnumber of (different |distinct |unique )(\w+ ){0,2}(types|kinds)\b", q) \
                and not re.search(r"\bof each\b|\beach type\b|\bper type\b", q):
            # "How many different door types are used?": the number of types, the breakdown is the evidence
            trace.append(f"count of distinct types: {len(groups)}")
            assumptions.append("breakdown: " + "; ".join(lines[2:12])[:400])
            return Answer(value=len(groups), unit="count", confidence=conf * 0.8, evidence=ev, trace=trace,
                          solver=self.name, assumptions=assumptions, missing=missing)
        return Answer(value="\n".join(lines), unit=None, confidence=conf * 0.85, evidence=ev, trace=trace,
                      solver=self.name, assumptions=assumptions, missing=missing)

    # ------------------------------------------------------------------------------------------------
    def _add_2d(self, path: str, model: str, it: Intent, ans: Answer, storey: Storey | None) -> None:
        """Add a pdf_pt box on the plan for every IFC element in the evidence (same GUID in 2D and 3D) and
        cross-check counts against what the drawing shows."""
        from stoa.solvers.ifc.plan2d import plan_items, plans_of_model

        asked_plan = Path(path).suffix.lower() in (".pdf", ".svg") and "_plan-" in Path(path).stem
        model_scope = it.scope == "model" or storey is None
        plans: list[str] = []
        if asked_plan:
            plans.append(str(Path(path).with_suffix(".pdf")))
        if model_scope:
            plans += [p for p in plans_of_model(model).values() if p not in plans]
        elif storey is not None and not asked_plan:
            p = plans_of_model(model).get(storey.guid)
            if p:
                plans.append(p)
        plans = [p for p in plans if plan_items(p)]
        if not plans:
            return
        ev2d, seen = [], set()
        for plan in plans:
            items = plan_items(plan)
            for ev in ans.evidence:
                g = ev.ifc_guid or ""
                itm = items.get(g)
                if itm is None or g in seen:
                    continue
                seen.add(g)
                note = ev.note + (f" | label '{itm.label}'" if itm.label else "")
                ev2d.append(Evidence(file=plan, page=0, bbox=[round(v, 2) for v in itm.bbox], bbox_space="pdf_pt",
                                     ifc_guid=g, note=note[:160]))
        n_proj = 0
        if not model_scope:  # same-storey elements the cut plan doesn't draw (slabs, beams): projected box
            from stoa.solvers.ifc.index import load_index
            from stoa.solvers.ifc.plan2d import project_box

            idx = load_index(model)
            for ev in ans.evidence:
                g = ev.ifc_guid or ""
                if not g or g in seen or g not in idx.elements:
                    continue
                b = project_box(model, plans[0], idx.elements[g])
                if b is None:
                    continue
                seen.add(g)
                n_proj += 1
                ev2d.append(Evidence(file=plans[0], page=0, bbox=[round(v, 2) for v in b], bbox_space="pdf_pt",
                                     ifc_guid=g, note=(ev.note + " | projected: not drawn on this plan")[:160]))
        n3d = len([e for e in ans.evidence if e.ifc_guid])
        files = sorted({e.file for e in ev2d})
        if n_proj:
            ans.trace.append(f"{n_proj} elements not drawn on the cut plan: boxed by projecting the model footprint "
                             "with a model->plan transform fitted on the drawn elements")
        ans.trace.append(f"2D link: {len(ev2d)}/{n3d} evidence elements drawn on "
                         + (", ".join(Path(f).name for f in files) if files else Path(plans[0]).name)
                         + ("" if asked_plan or model_scope else " (plan of the same storey)"))
        if it.metric == "count" and ans.unit == "count" and it.op is None and not model_scope:
            classes = set()
            for k in it.kinds or [it.kind]:
                classes |= set(KIND_CLASSES.get(k, ()))
            drawn = [i for i in plan_items(plans[0]).values() if i.cls in classes]
            if drawn and isinstance(ans.value, int):
                mark = "✓" if len(drawn) == ans.value else f"(differs by {len(drawn) - ans.value:+d})"
                ans.trace.append(f"cross-check: the plan drawing shows {len(drawn)} "
                                 f"{'/'.join(sorted({i.cls for i in drawn}))} symbols; model count {ans.value} {mark}")
                if len(drawn) != ans.value and ans.confidence > 0.75:
                    # two derivations disagree (S0 D15 C): on train/dev/hard this happens on 2 of 407 correct counts
                    ans.confidence = 0.75
                    ans.missing.append(f"the plan drawing shows {len(drawn)} symbols where the model counts "
                                       f"{ans.value}")
        ans.evidence = (ev2d + ans.evidence) if asked_plan else (ans.evidence + ev2d)

    @staticmethod
    def _floor_area(e: Element, it: Intent, trace: list[str]) -> tuple[float | None, str]:
        geo = e.geo.footprint_area if e.geo else None
        q_net = _qto(e, QTO_KEYS[("floor", "net")])
        if it.gross:
            q = _qto(e, QTO_KEYS[("floor", "gross")])
            if q is not None:
                return q, "gross floor area = Qto GrossFloorArea"
        if q_net is not None and q_net > 0:
            # an explicit quantity wins (S0 D15 mechanism B: a test model's gold follows Qto where it differs from the
            # shape by 5-15%; on every train/dev room asked, Qto and geometry agree, so this changes nothing there)
            if geo is not None and geo > 0:
                ok = abs(q_net - geo) <= 0.02 * geo
                trace.append(f"cross-check: Qto NetFloorArea {q_net:.2f} vs geometry {geo:.2f}"
                             + (" ✓" if ok else f" ✗ ({(q_net - geo) / geo * 100:+.1f}%)"))
            return q_net, "net floor area = the space's explicit Qto NetFloorArea (geometry as cross-check)"
        if geo is not None and geo > 0:
            return geo, "net floor area = footprint of the IfcSpace geometry"
        if q_net is not None:
            return q_net, "net floor area = Qto NetFloorArea (no geometry)"
        return None, ""

    @staticmethod
    def _obb(e: Element) -> tuple[float, float] | None:
        """(long side, short side) of the minimum rotated rectangle around the element's footprint."""
        if not e.geo or not e.geo.footprint:
            return None
        import math

        from shapely.geometry import MultiPolygon, Polygon

        polys = [Polygon(r) for r in e.geo.footprint if len(r) >= 3]
        if not polys:
            return None
        g = MultiPolygon(polys) if len(polys) > 1 else polys[0]
        c = list(g.minimum_rotated_rectangle.exterior.coords)
        a, b = math.dist(c[0], c[1]), math.dist(c[1], c[2])
        return max(a, b), min(a, b)

    @classmethod
    def _geo_value(cls, e: Element, qkey: str) -> float | None:
        """Geometry fallbacks, calibrated against Qto on the 20-28 models that have both (experiments/w1/
        calib_geo.py, per wall within 2%): volume = closed-mesh volume (88%), length = long side of the
        footprint's min rotated rectangle (62%), side area = volume / footprint width (82%)."""
        g = e.geo
        if g is None:
            # walls modelled with an 'Axis' curve only (no Body, e.g. 225/307 tuwien walls): length = axis length
            # (within 2% of Qto Length on 94/223 of them); no area or volume without a body
            return e.axis_length if (qkey == "length" and getattr(e, "axis_length", None)) else None
        if qkey == "volume":
            return g.volume
        # NOTE: the wall 'Axis' representation length (index.axis_length) matches Qto Length on only 44% of
        # walls vs 55-62% for the footprint OBB (experiments/w1/calib_geo.py, 00:35), so it is not used here.
        if qkey in ("length", "side"):
            o = cls._obb(e)
            if o is None:
                return max(g.bbox[3] - g.bbox[0], g.bbox[4] - g.bbox[1]) if (qkey == "length" and g.bbox) else None
            if qkey == "length":
                return o[0]
            return g.volume / o[1] if o[1] > 1e-3 and g.volume else None
        if qkey == "floor":
            return g.footprint_area
        return None

    @staticmethod
    def _ev(model: str, e: Element, note: str) -> Evidence:
        return Evidence(file=model, ifc_guid=e.guid, note=note[:120])

    def _final(self, val, unit, it: Intent, conf, ev, trace, assumptions, missing) -> Answer:
        if isinstance(val, float) and unit != "count":
            if it.asked_unit == "ft2" and unit == "m2":
                val, unit = val * FT2_PER_M2, "ft2"
                trace.append("converted m² -> ft² as asked")
            elif it.asked_unit == "ft" and unit == "m":
                val, unit = val * FT_PER_M, "ft"
                trace.append("converted m -> ft as asked")
            elif it.asked_unit == "ft3" and unit == "m3":
                val, unit = val * FT_PER_M ** 3, "ft3"
                trace.append("converted m³ -> ft³ as asked")
            elif it.asked_unit in ("mm", "cm") and unit == "m":
                val, unit = val * (1000.0 if it.asked_unit == "mm" else 100.0), it.asked_unit
                trace.append(f"converted m -> {unit} as asked")
            elif it.asked_unit == "l" and unit == "m3":
                val, unit = val * 1000.0, "l"
                trace.append("converted m³ -> litres as asked")
            val = round(val, 3)
        return Answer(value=val, unit=unit, confidence=max(0.0, min(1.0, conf)), evidence=ev, trace=trace,
                      solver=self.name, assumptions=assumptions, missing=missing)


_ = fold  # re-exported helpers used by tests
