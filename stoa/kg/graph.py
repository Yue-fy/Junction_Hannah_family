"""Implementation of stoa.kg (see the package docstring)."""

from __future__ import annotations

import functools
import json
import os
import re
import threading
from pathlib import Path

from stoa.data import abspath, data_root, drawing_group, ifc_model_for, siblings, source_of

PT_TO_MM = 25.4 / 72.0
_LOCK = threading.Lock()

# W4 router targets / my parser kinds -> IFC classes drawn in the plan SVGs
_TARGET_CLASSES = {
    "door": ("IfcDoor",), "window": ("IfcWindow",), "wall": ("IfcWall", "IfcWallStandardCase"),
    "column": ("IfcColumn",), "stair": ("IfcStair", "IfcStairFlight"), "room": ("IfcSpace",),
    "space": ("IfcSpace",), "beam": ("IfcBeam",), "slab": ("IfcSlab",), "railing": ("IfcRailing",),
    "furniture": ("IfcFurnishingElement", "IfcFurniture"),
}
# buildings that appear in both ifc_bench and ifc_models (file-name tokens)
_SAME_BUILDING = [("duplex", "bsc-duplex"), ("fzk_house", "kit-fzk-haus"), ("smiley_west", "kit-smiley-west"),
                  ("molio", "bsc-molio"), ("digital_hub", "rwth-digitalhub"), ("ac20_arc", "kit-institute"),
                  ("dental_clinic", "bsc-clinic")]


def _cache_dir() -> Path:
    d = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")) / "artifacts" / "W1" / "kg"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sheet_kind(stem: str) -> str:
    m = re.search(r"_(plan|section|elevation)-", stem)
    return m.group(1) if m else "other"


def _target_of(intent) -> tuple[str | None, str | None, str | None]:
    """(task, target, scope) from W4's router Intent, W1's parse Intent, a dict, or None."""
    if intent is None:
        return None, None, None
    get = (lambda k: intent.get(k)) if isinstance(intent, dict) else (lambda k: getattr(intent, k, None))
    task = get("task") or get("metric")
    target = get("target") or get("kind")
    scope = get("scope")
    return task, target, scope


# ---------------------------------------------------------------------------------------------------------
# ifc_models project graph
# ---------------------------------------------------------------------------------------------------------
@functools.lru_cache(maxsize=64)
def _ifc_project(model: str) -> dict:
    """Full graph for one IFC model and every sheet rendered from it (cached as JSON)."""
    from stoa.solvers.ifc.index import load_index
    from stoa.solvers.ifc.plan2d import plan_items
    from stoa.solvers.ifc.solver import IfcSolver, plan_storey

    idx = load_index(model)
    stem = Path(model).stem
    folder = Path(model).parent
    files = [{"path": model, "kind": "model", "storey": None}]
    plan_of: dict[str, str] = {}
    for f in sorted((data_root() / folder).glob(f"{stem}_*.pdf")):
        rel = str(folder / f.name)
        kind = _sheet_kind(f.stem)
        st = None
        if kind == "plan":
            s, why = plan_storey(rel, idx)
            if s is not None:
                st = s.guid
                plan_of.setdefault(s.guid, rel)
        files.append({"path": rel, "kind": kind, "storey": st,
                      "svg": str(folder / (f.stem + ".svg")) if (data_root() / folder / (f.stem + ".svg")).exists() else None})
    # other models of the same project (discipline models / variants)
    proj = drawing_group(model)
    for m in sorted((data_root() / folder).glob("*.ifc")):
        rel = str(folder / m.name)
        if rel != model and drawing_group(rel) == proj:
            files.append({"path": rel, "kind": "discipline-model", "storey": None})

    storeys, rooms, checks = [], [], []
    for s in idx.storeys:
        on = idx.in_storey(s.guid)
        counts: dict[str, int] = {}
        for e in on:
            counts[e.eff_cls] = counts.get(e.eff_cls, 0) + 1
        plan = plan_of.get(s.guid)
        drawn: dict[str, int] = {}
        items = plan_items(plan) if plan else {}
        for it in items.values():
            drawn[it.cls] = drawn.get(it.cls, 0) + 1
        storeys.append({"guid": s.guid, "name": s.name, "elevation": s.elevation, "plan": plan,
                        "model_counts": counts, "drawn_counts": drawn})
        if plan:
            for label, classes in (("doors", ("IfcDoor",)), ("windows", ("IfcWindow",)), ("rooms", ("IfcSpace",)),
                                   ("walls", ("IfcWall", "IfcWallStandardCase")), ("columns", ("IfcColumn",))):
                mc = sum(counts.get(c, 0) for c in classes)
                dc = sum(drawn.get(c, 0) for c in classes)
                if mc or dc:
                    checks.append({"storey": s.name, "what": label, "model": mc, "drawn": dc, "ok": mc == dc,
                                   "plan": plan})
        for e in on:
            if e.cls != "IfcSpace":
                continue
            area, _ = IfcSolver._floor_area(e, _NoIntent, [])
            r = {"guid": e.guid, "name": e.name, "long_name": e.long_name, "storey": s.guid, "storey_name": s.name,
                 "area_m2": round(area, 3) if area is not None else None, "plan": plan}
            q = next((v for k, v in e.qto.items() if k.endswith(".NetFloorArea")), None)
            if q is not None:
                r["qto_net_floor_area"] = round(q, 3)
            it = items.get(e.guid)
            if it is not None:
                r["bbox_pt"] = [round(v, 2) for v in it.bbox]
                r["label"] = it.label
                r["label_bbox_pt"] = [round(v, 2) for v in it.label_bbox] if it.label_bbox else None
                if it.polygon and len(it.polygon) >= 3:
                    from shapely.geometry import Polygon

                    r["_drawn_pt2"] = Polygon(it.polygon).buffer(0).area
            rooms.append(r)
    # plan scale per plan: median over its rooms of sqrt(model area / drawn area) -> 1:N (N = m per paper mm * 1000)
    import statistics

    scale_of: dict[str, float] = {}
    for plan in {r["plan"] for r in rooms if r.get("_drawn_pt2")}:
        ratios = [((r["area_m2"] / r["_drawn_pt2"]) ** 0.5) / (PT_TO_MM / 1000.0)
                  for r in rooms if r["plan"] == plan and r.get("_drawn_pt2") and r.get("area_m2")]
        if ratios:
            scale_of[plan] = statistics.median(ratios)
    for s_ in storeys:
        if s_["plan"] in scale_of:
            s_["plan_scale"] = f"1:{scale_of[s_['plan']]:.0f}"
    for r in rooms:
        a = r.pop("_drawn_pt2", None)
        if a and r["plan"] in scale_of:
            k = scale_of[r["plan"]]
            r["drawn_area_m2"] = round(a * (PT_TO_MM / 1000.0 * k) ** 2, 3)
            r["plan_scale"] = f"1:{k:.0f}"
    same = [f"data/ifc_bench/{p.name}" for tok, pref in _SAME_BUILDING if stem.startswith(pref)
            for p in sorted((data_root() / "data" / "ifc_bench").glob(f"{tok}*.ifc"))]
    g = {"project": proj, "model": model, "schema": idx.schema, "project_name": idx.project_name,
         "files": files, "storeys": storeys, "rooms": rooms, "same_building": same, "crosschecks": checks}
    try:
        with _LOCK:
            (_cache_dir() / f"{proj.replace('/', '__')}__{stem}.json").write_text(json.dumps(g, ensure_ascii=False))
    except OSError:
        pass
    return g


class _NoIntent:  # stand-in for IfcSolver._floor_area(e, it, ...) which only reads `gross`
    gross = False


def project_graph(path: str) -> dict:
    """The whole project graph behind `path` (ifc_models / ifc_bench); {} for other sources."""
    src = source_of(path)
    if src == "ifc_models":
        model = path if path.endswith(".ifc") else ifc_model_for(path)
        return _ifc_project(model) if model else {}
    if src == "ifc_bench":
        return _bench_project(path)
    return {}


def _bench_project(path: str) -> dict:
    stem = Path(path).stem
    folder = data_root() / "data" / "ifc_bench"
    proj = drawing_group(path)
    files = [{"path": path, "kind": "model"}] + [
        {"path": f"data/ifc_bench/{p.name}", "kind": "discipline-model"} for p in sorted(folder.glob("*.ifc"))
        if p.stem != stem and drawing_group(f"data/ifc_bench/{p.name}") == proj]
    same = []
    for tok, pref in _SAME_BUILDING:
        if stem.startswith(tok):
            same += [f"data/ifc_models/{p.name}" for p in sorted((data_root() / "data" / "ifc_models").glob(f"{pref}_*.ifc"))]
    return {"project": proj, "model": path, "files": files, "same_building": same}


# ---------------------------------------------------------------------------------------------------------
# swiss_dwellings floor graph (uses W2's DXF reader and DXF->PDF transform, read-only)
# ---------------------------------------------------------------------------------------------------------
@functools.lru_cache(maxsize=128)
def _swiss_floor(pdf: str, dxf: str) -> dict:
    out: dict = {"rooms": [], "crosschecks": []}
    try:
        from stoa.solvers.vector.floor import load_floor
        from stoa.solvers.vector.pdfmap import fit_transform
    except Exception as ex:  # noqa: BLE001 - W2's code not available on this branch
        out["warning"] = f"vector solver not importable: {type(ex).__name__}"
        return out
    fm = load_floor(str(abspath(dxf)))
    tf = fit_transform(str(abspath(pdf)), str(abspath(dxf)))
    out["transform"] = None if tf is None else {"s": tf.s, "a": tf.a, "b": tf.b, "rms_pt": round(tf.rms_pt, 3),
                                                "scale": f"1:{tf.scale_ratio:.0f}"}
    for r in fm.rooms:
        if not (r.number or r.name):
            continue
        d = {"number": r.number, "name": r.name, "area_m2_dxf": round(r.area, 2), "apartment": r.unit}
        if r.printed_area is not None:
            d["area_m2_printed"] = r.printed_area
            d["printed_matches_dxf"] = abs(r.printed_area - r.area) <= 0.02 * max(r.area, 1e-9)
        if tf is not None:
            d["bbox_pt"] = tf.box(r.bbox)
        out["rooms"].append(d)
    out["counts_dxf"] = {k: len(v) for k, v in fm.items.items()}
    pr = [r for r in out["rooms"] if "area_m2_printed" in r]
    if pr:
        ok = sum(r["printed_matches_dxf"] for r in pr)
        out["crosschecks"].append({"what": "printed room areas vs DXF polygons", "model": len(pr), "drawn": ok,
                                   "ok": ok == len(pr)})
    return out


# ---------------------------------------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------------------------------------
def links(path: str) -> dict:
    """Everything linked to the drawing at `path` (dataset-relative). JSON-serialisable."""
    src = source_of(path)
    sib = siblings(path)
    out: dict = {"path": path, "source": src, "group": drawing_group(path), "siblings": sib}
    if src == "ifc_models":
        g = project_graph(path)
        if not g:
            return out
        this = next((f for f in g["files"] if f["path"] == path or f["path"] == str(Path(path).with_suffix(".pdf"))), None)
        storey = this.get("storey") if this else None
        out.update({"kind": this["kind"] if this else ("model" if path.endswith(".ifc") else "other"),
                    "model": g["model"], "storey": next((s for s in g["storeys"] if s["guid"] == storey), None),
                    "files": g["files"], "storeys": [{k: s[k] for k in ("guid", "name", "elevation", "plan")}
                                                     for s in g["storeys"]],
                    "rooms": [r for r in g["rooms"] if storey is None or r["storey"] == storey],
                    "same_building": g["same_building"],
                    "crosschecks": [c for c in g["crosschecks"] if storey is None or c["plan"] == this["path"]]})
        out["nodes"], out["edges"] = _as_graph(g, storey)
    elif src == "ifc_bench":
        out.update(project_graph(path))
    elif src == "swiss_dwellings" and ".dxf" in sib and ".pdf" in sib:
        out["kind"] = "floor"
        out["same_site"] = sorted({str(Path(path).parent / p.name) for p in
                                   (data_root() / Path(path).parent).glob(f"{out['group'].split('/')[-1]}_*.pdf")} - {sib[".pdf"]})
        out.update(_swiss_floor(sib[".pdf"], sib[".dxf"]))
    return out


def _as_graph(g: dict, storey: str | None) -> tuple[list[dict], list[dict]]:
    """Compact node/edge lists for the UI (files, storeys, rooms; elements stay implicit via GUIDs)."""
    nodes = [{"id": g["model"], "type": "model", "label": g.get("project_name") or Path(g["model"]).stem}]
    edges = []
    for f in g["files"]:
        if f["path"] == g["model"]:
            continue
        nodes.append({"id": f["path"], "type": f["kind"], "label": Path(f["path"]).stem.split("_")[-1]})
        edges.append({"from": g["model"], "to": f["path"], "rel": "rendered_as" if f["kind"] in
                      ("plan", "section", "elevation") else "same_project"})
    for s in g["storeys"]:
        nodes.append({"id": s["guid"], "type": "storey", "label": s["name"]})
        edges.append({"from": g["model"], "to": s["guid"], "rel": "has_storey"})
        if s["plan"]:
            edges.append({"from": s["guid"], "to": s["plan"], "rel": "drawn_on"})
    for r in g["rooms"]:
        if storey is not None and r["storey"] != storey:
            continue
        nodes.append({"id": r["guid"], "type": "room", "label": f"{r.get('long_name') or ''} ({r.get('name') or ''})"})
        edges.append({"from": r["storey"], "to": r["guid"], "rel": "contains"})
        if r.get("bbox_pt"):
            edges.append({"from": r["guid"], "to": r["plan"], "rel": "drawn_at", "bbox_pt": r["bbox_pt"]})
    for p in g["same_building"]:
        nodes.append({"id": p, "type": "same_building", "label": Path(p).stem})
        edges.append({"from": g["model"], "to": p, "rel": "same_building"})
    return nodes, edges


def crosscheck(path: str, intent, answer) -> str | None:
    """A short note comparing `answer` with an independent source for the same fact, or None.

    ifc_models: counts vs the IFC model AND the symbols drawn on the plan; room areas vs IFC geometry, Qto and
    the polygon drawn on the plan (1:100). swiss: room areas vs the DXF polygon and the printed area; counts vs
    the DXF layers. Works for any solver's answer (it does not trust the answer's own evidence)."""
    try:
        return _crosscheck(path, intent, answer)
    except Exception as ex:  # noqa: BLE001 - a cross-check must never break the pipeline
        return f"cross-check unavailable ({type(ex).__name__})"


def _val(answer):
    v = getattr(answer, "value", answer.get("value") if isinstance(answer, dict) else answer)
    return v


def _evidence_guids(answer) -> list[str]:
    ev = getattr(answer, "evidence", None) or (answer.get("evidence") if isinstance(answer, dict) else None) or []
    out = []
    for e in ev:
        g = getattr(e, "ifc_guid", None) if not isinstance(e, dict) else e.get("ifc_guid")
        if g and g not in out:
            out.append(g)
    return out


def _mark(a, b, tol=0.0) -> str:
    if a is None or b is None:
        return "?"
    ok = (abs(a - b) <= tol * max(abs(b), 1e-9)) if tol else (round(a) == round(b))
    return "✓" if ok else "✗"


def _crosscheck(path: str, intent, answer) -> str | None:
    src = source_of(path)
    task, target, scope = _target_of(intent)
    val = _val(answer)
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        return None
    if src == "ifc_models":
        from stoa.solvers.ifc.index import load_index
        from stoa.solvers.ifc.plan2d import plan_items
        from stoa.solvers.ifc.solver import IfcSolver, plan_storey

        g = project_graph(path)
        if not g:
            return None
        idx = load_index(g["model"])
        plan = str(Path(path).with_suffix(".pdf")) if "_plan-" in Path(path).stem else None
        st = plan_storey(plan, idx)[0] if plan else None
        guids = _evidence_guids(answer)
        if task == "count" and target in _TARGET_CLASSES and scope != "model":
            classes = _TARGET_CLASSES[target]
            model_classes = ("IfcStair",) if target == "stair" else classes
            if st is None and guids:  # .ifc question: take the storey of the answer's own elements
                sg = {idx.elements[x].storey for x in guids if x in idx.elements}
                st = idx.storey(next(iter(sg))) if len(sg) == 1 else None
            if st is None:
                return None
            mc = len(idx.in_storey(st.guid, *model_classes))
            sgraph = next((s for s in g["storeys"] if s["guid"] == st.guid), None)
            drawn_cls = {c for c, n in (sgraph["drawn_counts"] if sgraph else {}).items() if n}
            # only evidence if this plan's SVG tags this kind of element at all (some tag rooms only)
            has_drawing = bool(sgraph and sgraph["plan"] and (drawn_cls & set(classes) or drawn_cls - {"IfcSpace"}))
            dc = sum(sgraph["drawn_counts"].get(c, 0) for c in classes) if has_drawing else None
            if target == "stair" and dc is not None:
                # a stair is drawn as its flights; count distinct drawn stairs via the flights' parent
                drawn_guids = {gd for gd, it in plan_items(sgraph["plan"]).items() if it.cls in classes}
                dc = len({(idx.elements[gd].parent or gd) if gd in idx.elements else gd for gd in drawn_guids})
            parts = [f"IFC model: {mc} {'/'.join(model_classes)} on storey '{st.name}' {_mark(val, mc)}"]
            if dc is not None:
                parts.append(f"plan drawing: {dc} symbols {_mark(val, dc)}")
            return f"answer {int(round(val))} vs " + "; ".join(parts)
        if task == "count" and target in _TARGET_CLASSES and scope == "model":
            mcls = ("IfcStair",) if target == "stair" else _TARGET_CLASSES[target]
            mc = len(idx.by_class(*mcls))
            return f"answer {int(round(val))} vs IFC model total {mc} {'/'.join(mcls)} {_mark(val, mc)}"
        if task == "area":
            spaces = [idx.elements[x] for x in guids if x in idx.elements and idx.elements[x].cls == "IfcSpace"]
            filt = (intent.get("filters") if isinstance(intent, dict) else getattr(intent, "filters", None)) or {}
            if not spaces and isinstance(filt, dict) and filt.get("room"):
                from stoa.solvers.ifc.resolve import match_space, match_storey

                ms = match_storey(idx, filt["storey"]) if filt.get("storey") else None
                hits = match_space(idx, filt["room"], ms.obj.guid if ms else (st.guid if st else None))
                spaces = [hits[0].obj] if hits else []
            if len(spaces) == 1:
                e = spaces[0]
                geo = e.geo.footprint_area if e.geo else None
                q = next((v for k, v in e.qto.items() if k.endswith(".NetFloorArea")), None)
                parts = [f"IFC geometry {geo:.2f} m² {_mark(val, geo, 0.02)}"] if geo else []
                if q is not None:
                    parts.append(f"Qto NetFloorArea {q:.2f} m² {_mark(val, q, 0.02)}")
                room = next((r for r in g["rooms"] if r["guid"] == e.guid), None)
                if room and room.get("drawn_area_m2"):
                    parts.append(f"room polygon on the plan ({room['plan_scale']}, scale fitted on all rooms) "
                                 f"{room['drawn_area_m2']:.2f} m² {_mark(val, room['drawn_area_m2'], 0.02)}")
                return f"answer {val:.2f} m² vs " + "; ".join(parts) if parts else None
        return None
    if src == "swiss_dwellings":
        sib = siblings(path)
        if ".dxf" not in sib or ".pdf" not in sib:
            return None
        f = _swiss_floor(sib[".pdf"], sib[".dxf"])
        if task == "count" and target in ("door", "window", "wc", "washbasin", "bathtub", "shower"):
            key = {"wc": "toilet"}.get(target, target)
            n = f.get("counts_dxf", {}).get(key)
            if n is not None:
                return f"answer {int(round(val))} vs DXF layer count {n} {_mark(val, n)}"
        if task == "area":
            filt = (intent.get("filters") if isinstance(intent, dict) else getattr(intent, "filters", None)) or {}
            room = None
            if filt.get("room_no"):
                room = next((r for r in f.get("rooms", []) if r["number"] == filt["room_no"]), None)
            if room is None:  # the room whose pdf box overlaps the answer's evidence box most
                boxes = [e.get("bbox") if isinstance(e, dict) else e.bbox for e in
                         (getattr(answer, "evidence", None) or (answer.get("evidence") if isinstance(answer, dict) else None) or [])]
                boxes = [b for b in boxes if b]
                if boxes:
                    def ov(a, b):
                        w = min(a[2], b[2]) - max(a[0], b[0])
                        h = min(a[3], b[3]) - max(a[1], b[1])
                        return max(w, 0) * max(h, 0)
                    best = max(f.get("rooms", []), key=lambda r: ov(r.get("bbox_pt") or [0, 0, 0, 0], boxes[0]), default=None)
                    room = best if best and ov(best.get("bbox_pt") or [0, 0, 0, 0], boxes[0]) > 0 else None
            if room is None:
                return None
            s = (f"answer {val:.2f} m² vs DXF polygon of room {room['number'] or ''} '{room['name'] or ''}' "
                 f"{room['area_m2_dxf']:.2f} m² {_mark(val, room['area_m2_dxf'], 0.02)}")
            if "area_m2_printed" in room:
                s += f"; printed on the plan {room['area_m2_printed']:.2f} m² {_mark(val, room['area_m2_printed'], 0.02)}"
            return s
        return None
    return None
