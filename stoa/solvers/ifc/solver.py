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
from pathlib import Path

from stoa.contract import Answer, Evidence
from stoa.data import siblings, source_of
from stoa.solvers import register
from stoa.solvers.base import BaseSolver
from stoa.solvers.ifc.index import Element, IfcIndex, Storey, load_index
from stoa.solvers.ifc.parse import KIND_CLASSES, Intent, fold, parse
from stoa.solvers.ifc.resolve import match_model, match_space, match_storey, norm

FT2_PER_M2 = 10.763910416709722
FT_PER_M = 3.280839895013123
MAX_EVIDENCE = 2000

# quantity key suffixes, in order of preference, per (metric, kind)
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
    return siblings(path).get(".ifc")


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
        trace.append(f"parsed: metric={it.metric} kind={it.kind} scope={it.scope} names={it.names}"
                     + (" side-area" if it.side_area else "") + (" gross" if it.gross else ""))
        try:
            ans = self._answer(path, model, idx, it, trace)
        except Exception as ex:  # noqa: BLE001 - report as a refusal with the reason, never crash the eval
            ans = Answer.abstain(self.name, f"error: {type(ex).__name__}: {ex}", trace=trace)
        ans.solver = self.name
        ans.cost.wall_seconds = time.perf_counter() - t0
        return ans

    # ------------------------------------------------------------------------------------------------
    def _scope(self, path: str, idx: IfcIndex, it: Intent, trace: list[str], assumptions: list[str]):
        """-> (storey | None, room_name | None, conf_factor). storey None + scope model = whole model."""
        conf = 1.0
        storey = None
        room = None
        names = list(it.names)
        if it.scope == "room" and names:
            room = names[0]
            names = names[1:]
        if it.scope != "model":
            for n in reversed(names):
                m = match_storey(idx, n)
                if m:
                    storey = m.obj
                    trace.append(f"storey '{n}' -> '{m.label}' ({m.method}, {m.score:.0f}) guid {storey.guid}")
                    if m.method == "fuzzy":
                        conf *= 0.85
                        assumptions.append(f"storey name '{n}' matched fuzzily to '{m.label}'")
                    break
            if storey is None and names:
                mm = match_model(idx, names[-1])
                if mm and it.scope != "room":
                    trace.append(f"'{names[-1]}' matches the model name '{mm.label}': whole model")
                    it.scope = "model"
            if storey is None and it.scope != "model":
                ps, why = plan_storey(path, idx)
                if ps is not None:
                    storey = ps
                    trace.append(f"storey from the plan file: {why}")
                    if names:
                        conf *= 0.7
                        assumptions.append(f"no storey named {names[-1]!r}; used the plan's storey '{ps.name}'")
                elif it.scope == "storey":
                    trace.append(f"no storey resolved ({why}); counting the whole model")
                    assumptions.append("storey not found; counted the whole model")
                    conf *= 0.3
        elif it.names:
            mm = match_model(idx, it.names[-1])
            trace.append(f"model scope; model name '{it.names[-1]}' "
                         + (f"~ project '{mm.label}' ({mm.method})" if mm else "not in IfcProject/IfcBuilding names; "
                            "using the file's model"))
        return storey, room, conf

    def _answer(self, path: str, model: str, idx: IfcIndex, it: Intent, trace: list[str]) -> Answer:
        assumptions: list[str] = []
        missing: list[str] = []
        if it.metric == "text":
            return Answer.abstain(self.name, "free-text question: no deterministic rule", trace=trace,
                                  missing=["a quantity question (count/area/volume/length)"])
        if it.kind is None:
            return Answer.abstain(self.name, "no element kind recognised in the question", trace=trace,
                                  missing=["element kind (doors, walls, rooms, ...)"])
        storey, room, conf = self._scope(path, idx, it, trace, assumptions)
        sname = storey.name if storey else None

        # ---- single room area -----------------------------------------------------------------------
        if it.metric == "area" and room is not None:
            ms = match_space(idx, room, storey.guid if storey else None)
            if not ms:
                return Answer.abstain(self.name, f"room {room!r} not found", trace=trace,
                                      missing=[f"an IfcSpace named {room!r}"])
            m = ms[0]
            e: Element = m.obj
            trace.append(f"room '{room}' -> IfcSpace '{m.label}' ({m.method}, {m.score:.0f}) guid {e.guid}"
                         + (f"; {len(ms)} equally good matches, took the first" if len(ms) > 1 else ""))
            if m.method == "fuzzy":
                conf *= 0.8
                assumptions.append(f"room name '{room}' matched fuzzily to '{m.label}'")
            if len(ms) > 1:
                conf *= 0.6
            val, how = self._floor_area(e, it, trace)
            if val is None:
                return Answer.abstain(self.name, "space has no geometry or area quantity", trace=trace)
            assumptions.append(how)
            return self._final(val, "m2", it, conf * 0.97, [self._ev(model, e, f"{e.long_name or e.name} {val:.2f} m²")],
                               trace, assumptions, missing)

        classes = KIND_CLASSES.get(it.kind, ())
        if it.scope == "model" or storey is None:
            els = idx.by_class(*classes)
            where = "whole model"
        else:
            els = idx.in_storey(storey.guid, *classes)
            where = f"storey '{sname}'"
        trace.append(f"{len(els)} elements of {'/'.join(classes)} in {where}")

        if it.metric == "count":
            if it.kind == "wall":
                assumptions.append("walls = IfcWall + IfcWallStandardCase (curtain walls not counted)")
            if it.kind in ("sanitary", "light"):
                assumptions.append("IFC2X3 IfcFlowTerminal classified by its type object")
            if storey is not None and it.scope != "model":
                assumptions.append(f"elements whose spatial container is storey '{sname}'")
            ev = [self._ev(model, e, f"{e.eff_cls} {e.name or ''}".strip()) for e in els[:MAX_EVIDENCE]]
            conf_c = conf * (0.97 if els else 0.6)
            if not els:
                missing.append(f"no {it.kind} elements in the model: they may be modelled as proxies or not at all")
            return self._final(len(els), "count", it, conf_c, ev, trace, assumptions, missing)

        if not els:
            missing.append(f"no {it.kind} elements in {where}")
            return self._final(0.0, {"area": "m2", "volume": "m3", "length": "m"}[it.metric], it, conf * 0.3, [],
                               trace, assumptions, missing)

        # ---- aggregated quantities ------------------------------------------------------------------
        if it.metric == "area" and it.kind == "space":
            tot, ev = 0.0, []
            for e in els:
                v, _ = self._floor_area(e, it, [])
                if v is not None:
                    tot += v
                    ev.append(self._ev(model, e, f"{e.long_name or e.name} {v:.2f} m²"))
            assumptions.append("net floor area = sum of IfcSpace footprints (geometry) on the storey")
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
        for e in els:
            v = _qto(e, keys)
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
            tot += v
            ev.append(self._ev(model, e, f"{e.eff_cls} {e.name or ''} {label} {v:.3f}"))
        src = f"Qto {keys[0].split('.')[-1]}"
        trace.append(f"{label}: {n_q} from {src}, {n_geo} from geometry, {n_none} without either; total {tot:.3f}")
        if n_q and geo_tot:
            trace.append(f"cross-check: geometry-only total {geo_tot:.3f} ({(geo_tot - tot) / tot * 100:+.1f}% vs answer)"
                         if tot else "cross-check: n/a")
        if n_geo:
            assumptions.append(f"{n_geo} of {len(els)} elements have no {src}; used their geometry instead")
            conf *= 0.6 if n_q else 0.5
        if n_none:
            missing.append(f"{n_none} elements have neither quantities nor geometry")
            conf *= 0.7
        assumptions.append(f"{label} = sum of {src} over {it.kind}s of {where}")
        return self._final(tot, unit, it, conf * 0.95, ev, trace, assumptions, missing)

    # ------------------------------------------------------------------------------------------------
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
    def _geo_value(e: Element, qkey: str) -> float | None:
        g = e.geo
        if g is None:
            return None
        if qkey == "volume":
            return g.volume
        if qkey == "length" and g.bbox:
            return max(g.bbox[3] - g.bbox[0], g.bbox[4] - g.bbox[1])
        if qkey == "side" and g.lateral_area is not None:
            return g.lateral_area / 2.0
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
