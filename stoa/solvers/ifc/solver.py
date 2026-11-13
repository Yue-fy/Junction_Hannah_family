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
from stoa.solvers.ifc.parse import (_MATERIAL_Q, FALLBACK_CLASSES, KIND_CLASSES, NAME_FALLBACK, Intent, fold,
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
        trace: list[str] = []
        model = model_for(path)
        if model is None:
            return Answer.abstain(self.name, "no IFC model for this drawing", missing=["an IFC model of the building"])
        if model != path:
            trace.append(f"asked on {Path(path).name}; answering from its source model {Path(model).name}")
        idx = load_index(model)
        trace.append(f"model {Path(model).name}: {idx.schema}, {len(idx.storeys)} storeys, {len(idx.elements)} elements"
                     f" (index {idx.build_seconds:.1f}s, cached)")
        it = parse(question)
        it.question = question
        trace.append(f"parsed: metric={it.metric} kind={it.kind} scope={it.scope} names={it.names}"
                     + (" side-area" if it.side_area else "") + (" gross" if it.gross else ""))
        ctx: dict = {"question": question}
        try:
            ans = self._answer(path, model, idx, it, trace, ctx)
        except Exception as ex:  # noqa: BLE001 - report as a refusal with the reason, never crash the eval
            ans = Answer.abstain(self.name, f"error: {type(ex).__name__}: {ex}", trace=trace)
        if ans.value is not None and it.kind == "space" and it.metric == "area" and isinstance(ans.value, (int, float)):
            from stoa.solvers.ifc.factcard import placeholder_spaces

            if placeholder_spaces(idx):
                ans.confidence = min(ans.confidence, 0.15)
                ans.missing.append("real room areas: this model's IfcSpaces are ~1 m² placeholders (geometry and "
                                   "quantity sets), so the value is not a floor area")
        if ans.value is not None and not it.mod and not it.which and it.op is None:
            # an operator word the parse did not turn into an operator: the atomic value may not be what was asked
            w = _OPERATOR_WORD.search(fold(question))
            if w and ans.confidence > 0.5:
                ans.confidence = 0.5
                ans.missing.append(f"the question has an operator word ('{w.group(0)}') the rules did not apply")
                ans.trace.append(f"guard: operator word '{w.group(0)}' not modelled -> confidence capped at 0.5")
        for note in it.notes:
            if note.startswith("exclusion"):
                ans.trace.append(note)
                if note.startswith("exclusion NOT") and ans.value is not None:
                    ans.confidence = min(ans.confidence, 0.3)
                    ans.missing.append(f"the question excludes something the rules can't apply ({note[23:]}); "
                                       "the value ignores the exclusion")
        if ctx.get("material_unknown") and ans.value is not None:
            ans.confidence = min(ans.confidence, 0.3)
        if ans.value is not None and any("proxy/generic elements named like" in x for x in ans.trace):
            ans.confidence = min(ans.confidence, 0.6)  # counted by name, not by class: names can over/under-match
        llm_on = str(self.options.get("llm", "1")) != "0"
        if ans.value is None and llm_on and not any("error:" in t for t in ans.trace):
            ans = self._llm_fallback(model, idx, question, it, ans, storey=ctx.get("storey"))
        elif llm_on and isinstance(ans.value, (int, float)) and wants_list(question):
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
        if ans.value is not None and self.options.get("plan2d", "1") != "0":
            try:
                self._add_2d(path, model, it, ans, ctx.get("storey"))
            except Exception as ex:  # noqa: BLE001 - 2D evidence is a bonus; never lose the answer over it
                ans.trace.append(f"2D link failed: {type(ex).__name__}: {ex}")
        ans.solver = self.name
        ans.cost.wall_seconds = time.perf_counter() - t0
        return ans

    # ------------------------------------------------------------------------------------------------
    def _roles(self, path: str, idx: IfcIndex, it: Intent, trace: list[str], assumptions: list[str]):
        """Give every quoted name a role by resolving it against the model (not by its position):
        -> (storey | None, rooms: list[(asked_name, [Match])], conf_factor)."""
        conf = 1.0
        storey, storey_name, rooms, model_named = None, None, [], False
        groups: list[tuple[str, list[Element]]] = []
        cands = []
        for n in it.names:
            ms = match_storey(idx, n)
            sp = match_space(idx, n) if it.kind == "space" or it.metric == "area" else []
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
            if it.kind == "space" or it.metric == "area":
                grp = label_group(idx, n, storey.guid if storey else None)
                sp2 = match_space(idx, n, storey.guid if storey else None)
                if sp2 and (len(grp) <= 1 or (sp2[0].score >= 99 and it.metric != "count")):
                    rooms.append((n, sp2))
                    continue
                if grp:
                    groups.append((n, grp))
                    trace.append(f"'{n}' is a room type: {len(grp)} spaces labelled so"
                                 + (f" on '{storey.name}'" if storey else ""))
                    continue
            if it.scope == "model" or (mm and mm.score >= 60):
                model_named = True
                trace.append(f"'{n}' taken as the model's name" + (f" (~'{mm.label}')" if mm else
                             " (not in IfcProject/IfcBuilding names; the file is the model)"))
            else:
                trace.append(f"'{n}': no storey, room or model of that name")
                assumptions.append(f"could not resolve '{n}'")
                conf *= 0.6
        if storey is None and not it.names and it.scope != "model" and getattr(it, "question", ""):
            i, why = storey_mention(it.question, [s.name for s in idx.storeys])
            if i is not None:
                storey = idx.storeys[i]
                trace.append(f"{why} (unquoted)")
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
        ctx_groups = groups
        return storey, rooms, conf, ctx_groups

    def _answer(self, path: str, model: str, idx: IfcIndex, it: Intent, trace: list[str], ctx: dict) -> Answer:
        assumptions: list[str] = []
        missing: list[str] = []
        if ctx.get("compose", True) and not it.names:
            dim = self._dims_answer(model, idx, it, trace, ctx)
            if dim is not None:
                return dim
        if it.metric == "text":
            if it.kind is not None and it.names:
                it.metric = "count"  # "Count the walls on storey X." style imperatives without a count word
                trace.append("no metric word; assuming a count")
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
                ev = [Evidence(file=model, ifc_guid=st.guid, note=f"IfcBuildingStorey {st.name}") for st in idx.storeys]
                trace.append("storeys: " + ", ".join(f"{st.name} ({st.elevation:.2f} m)" if st.elevation is not None
                                                      else st.name for st in idx.storeys))
                assumptions.append("storeys = IfcBuildingStorey entities (incl. foundation/roof levels if modelled)")
                return self._final(len(idx.storeys), "count", it, conf * 0.85, ev, trace, assumptions, missing)
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
        if not groups and not rooms and it.kind is None:
            lab, grp = vocabulary_group(idx, ctx.get("question", ""), it.names)
            if lab:
                if storey is not None and it.scope != "model":
                    grp = [e for e in grp if e.storey == storey.guid]
                groups = [(lab, grp)]
                it.kind = "space"
                trace.append(f"room type '{lab}' from the model's room labels: {len(grp)} spaces {where_s}")
        if groups and it.kind in ("space", None) and it.metric in ("count", "area"):
            els = [e for _, g in groups for e in g]
            it.kind = "space"
            assumptions.append("room type = IfcSpace LongName/Name without its numbering")
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

        if it.kind is None:
            return Answer.abstain(self.name, "no element kind recognised in the question", trace=trace,
                                  missing=["element kind (doors, walls, rooms, ...)"])
        if it.metric == "area" and it.kind == "space" and not rooms and len(it.names) > (1 if storey else 0):
            return Answer.abstain(self.name, f"rooms {it.names} not found", trace=trace,
                                  missing=[f"IfcSpaces named {it.names}"])

        where = "whole model" if (it.scope == "model" or storey is None) else f"storey '{sname}'"

        def elements_of(kind: str) -> list[Element]:
            classes = KIND_CLASSES.get(kind, ())
            els = idx.by_class(*classes) if where == "whole model" else idx.in_storey(storey.guid, *classes)
            trace.append(f"{len(els)} elements of {'/'.join(classes)} in {where}")
            if not els and not idx.by_class(*classes):  # the model has none of this class at all
                els = self._kind_fallback(idx, kind, storey if where != "whole model" else None, trace, assumptions)
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
            return self._final(n, "count", it, conf_c, ev, trace, assumptions, missing)

        els = elements_of(it.kind)
        if not els:
            missing.append(f"no {it.kind} elements in {where}")
            return self._final(0.0, {"area": "m2", "volume": "m3", "length": "m"}[it.metric], it, conf * 0.3, [],
                               trace, assumptions, missing)

        # ---- aggregated quantities ------------------------------------------------------------------
        if it.top_n and it.kind == "space":
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
        if it.metric == "area" and it.kind == "space":
            tot, ev = 0.0, []
            for e in els:
                v, _ = self._floor_area(e, it, [])
                if v is not None:
                    tot += v
                    ev.append(self._ev(model, e, f"{e.long_name or e.name} {v:.2f} m²"))
            assumptions.append(f"net floor area = sum of IfcSpace footprints (geometry) in {where}")
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
        multi = len(storeys) >= 2 and not others and (it.op in ("sum", "argmax", "argmin", "diff", "max", "min")
                                                     or it.which)
        if not (multi or it.mod):
            return None
        if it.mod == "threshold" and it.metric not in ("area", "volume", "length"):
            return None

        def sub(names: list[str], **kw) -> tuple[Answer, list[str]]:
            args = dict(names=list(names), op=None, mod=None, threshold=None, which=False, yes_no=False, notes=[],
                        filters=dict(it.filters), kinds=list(it.kinds), group_by=None, top_n=False)
            args.update(kw)
            sit = dataclasses.replace(it, **args)
            st: list[str] = []
            a = self._answer(path, model, idx, sit, st, {"question": ctx.get("question", ""), "compose": False})
            return a, st

        def done(val, unit, parts: list[Answer], steps: list[str], how: str, conf_k: float = 0.95) -> Answer:
            conf = conf_k
            ev, asm, miss = [], [how], []
            for a in parts:
                conf *= a.confidence if a.value is not None else 0.0
                ev += a.evidence
                asm += [x for x in a.assumptions if x not in asm]
                miss += [x for x in a.missing if x not in miss]
            trace.extend(steps)
            if isinstance(val, str):
                return Answer(value=val, unit=None, confidence=max(0.0, min(1.0, conf)), evidence=ev[:MAX_EVIDENCE],
                              trace=trace, solver=self.name, assumptions=asm, missing=miss)
            if isinstance(val, float):
                val = round(val, 3)
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
                tie = sum(1 for _, v in vals if v == pick[1]) > 1
                return done(pick[0] if not tie else "equal (" + ", ".join(f"{n} {v:g}" for n, v in vals) + ")",
                            None, [a for _, a, _ in parts], steps + [f"{it.op} over storeys -> {pick[0]}"],
                            f"compared {it.metric} per storey", 0.95 if not tie else 0.6)
            if it.op == "diff" and len(vals) == 2:
                return done(abs(vals[0][1] - vals[1][1]), unit, [a for _, a, _ in parts],
                            steps + [f"|{vals[0][1]:g} - {vals[1][1]:g}|"], "difference between two storeys")
            if it.op in ("max", "min"):
                v = (max if it.op == "max" else min)(v for _, v in vals)
                return done(v, unit, [a for _, a, _ in parts], steps + [f"{it.op} = {v:g}"], f"{it.op} over storeys")
            tot = sum(v for _, v in vals)
            return done(int(tot) if unit == "count" else tot, unit, [a for _, a, _ in parts],
                        steps + ["sum = " + " + ".join(f"{v:g}" for _, v in vals)], "sum over the named storeys")

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
            elif storeys:  # "share of the model's doors on storey S"
                part, t1 = sub([n for n, _ in storeys])
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
            op, thr = it.threshold
            if it.asked_unit == "ft2":
                thr /= FT2_PER_M2
            elif it.asked_unit == "ft":
                thr /= FT_PER_M
            cmp = {"gt": lambda v: v > thr, "ge": lambda v: v >= thr, "lt": lambda v: v < thr, "le": lambda v: v <= thr}[op]
            sn = [n for n, _ in storeys]
            if others:
                parts = [(n, *sub([n] + sn)) for n in others]
            else:  # every room of the storey
                if not storeys or it.kind != "space":
                    return None
                els = idx.in_storey(storeys[0][1].guid, "IfcSpace")
                parts = []
                for e in els:
                    v, _ = self._floor_area(e, it, [])
                    parts.append((e.long_name or e.name, Answer(value=v, unit="m2", confidence=0.97,
                                                                evidence=[self._ev(model, e, f"{e.long_name or e.name} {v or 0:.2f} m²")]), []))
            if any(a.value is None or isinstance(a.value, str) for _, a, _ in parts):
                return None
            unit_si = {"area": "m2", "volume": "m3", "length": "m"}[it.metric]
            # sub-answers came back in the asked unit; compare in SI
            def si(a: Answer) -> float:
                v = float(a.value)
                return v / FT2_PER_M2 if a.unit == "ft2" else v / FT_PER_M if a.unit == "ft" else v
            hit = [(n, si(a)) for n, a, _ in parts if cmp(si(a))]
            sym = {"gt": ">", "ge": ">=", "lt": "<", "le": "<="}[op]
            steps = [f"{n}: {si(a):.2f} {unit_si} {'✓' if cmp(si(a)) else '-'}" for n, a, _ in parts]
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
        storey = idx.storeys[i] if i is not None else None
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
            return (e.dims or {}).get(attr)

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
        groups: dict[str, list[float]] = {}
        members: dict[str, list[Element]] = {}
        type_key = _type_key_fn(els)
        for e in els:
            if it.group_by == "storey":
                key = idx.storey(e.storey).name if e.storey and idx.storey(e.storey) else "(no storey)"
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
        for k in order[:25]:
            sub = sum(groups[k])
            share = f" ({sub / total * 100:.1f}%)" if total else ""
            cnt = f", {len(groups[k])} elements" if value_of is not None else ""
            lines.append(f"- {k}: {fmt(sub)}{share}{cnt}")
            if want_mat:
                combos = Counter(tuple(m for m in (e.materials or []) if m and m.strip() and "<unnamed>" not in m.lower())
                                 for e in members[k])
                best = next((c for c, _ in combos.most_common() if c), None)
                if best:
                    lines.append("    materials: " + ", ".join(best))
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
        ans.evidence = (ev2d + ans.evidence) if asked_plan else (ans.evidence + ev2d)

    @staticmethod
    def _floor_area(e: Element, it: Intent, trace: list[str]) -> tuple[float | None, str]:
        geo = e.geo.footprint_area if e.geo else None
        q_net = _qto(e, QTO_KEYS[("floor", "net")])
        if it.gross:
            q = _qto(e, QTO_KEYS[("floor", "gross")])
            if q is not None:
                return q, "gross floor area = Qto GrossFloorArea"
        if geo is not None and geo > 0:
            if q_net is not None:
                trace.append(f"cross-check: Qto NetFloorArea {q_net:.2f} vs geometry {geo:.2f}"
                             + (" ✓" if abs(q_net - geo) <= 0.02 * geo else f" ({(q_net - geo) / geo * 100:+.1f}%)"))
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
            val = round(val, 3)
        return Answer(value=val, unit=unit, confidence=max(0.0, min(1.0, conf)), evidence=ev, trace=trace,
                      solver=self.name, assumptions=assumptions, missing=missing)


_ = fold  # re-exported helpers used by tests
