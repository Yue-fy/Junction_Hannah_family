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
    base = re.sub(r"_model$", "", stem)
    for f in sorted((data_root() / folder).glob(f"{base}_plan.png")):
        files.append({"path": str(folder / f.name), "kind": "raster-plan", "storey": None})
    # other models of the same project (discipline models / variants)
    proj = drawing_group(model)
    for m in sorted((data_root() / folder).glob("*.ifc")):
        rel = str(folder / m.name)
        if rel != model and drawing_group(rel) == proj:
            files.append({"path": rel, "kind": "discipline-model", "storey": None})

    storeys, rooms, checks = [], [], []
    zoff = floor_offset(idx)
    sname = {s.guid: s.name for s in idx.storeys}
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
        cut_z = (s.elevation or 0.0) + zoff + CUT_HEIGHT
        sg = {"guid": s.guid, "name": s.name, "elevation": s.elevation, "plan": plan,
              "model_counts": counts, "drawn_counts": drawn, "cut_z": round(cut_z, 3)}
        storeys.append(sg)
        if plan:
            sg["cut"] = {}
            for label, classes in _CHECK_KINDS:
                c = _cut_compare(idx, s.guid, items, classes, cut_z, sname)
                sg["cut"][label] = c
                if c["model"] or c["drawn_all"]:
                    checks.append({"storey": s.name, "what": label, "plan": plan, **c})
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


# The ifc_models plans are horizontal cuts at storey floor + 1.2 m; they draw every element (of ANY storey) whose
# z-range crosses that plane. Measured on all 268 plan x class rows (experiments/w1/cut_check.py): the crossing
# set equals the drawn same-storey set in 244 rows at 1.2 m (1.0 m: 234, 1.5 m: 215; "all elements of the
# storey": 181). Elements entirely above or below the plane (Revit lintel 'walls', clerestory windows,
# foundations) are in the storey but not drawn, and a plan cut just below the next floor draws that floor.
CUT_HEIGHT = 1.2
_CHECK_KINDS = (("doors", ("IfcDoor",)), ("windows", ("IfcWindow",)), ("rooms", ("IfcSpace",)),
                ("walls", ("IfcWall", "IfcWallStandardCase")), ("columns", ("IfcColumn",)))
_FLOOR_CLASSES = ("IfcWall", "IfcWallStandardCase", "IfcColumn", "IfcDoor")


def floor_offset(idx) -> float:
    """World z of a storey's floor minus its Elevation attribute (0 for most models; esplanades: +14.3 m).
    Median over storeys of (median bottom z of its walls/columns/doors - elevation)."""
    import statistics

    offs = []
    for s in idx.storeys:
        if s.elevation is None:
            continue
        zs = [e.geo.bbox[2] for e in idx.in_storey(s.guid, *_FLOOR_CLASSES) if e.geo and e.geo.bbox]
        if len(zs) >= 5:
            offs.append(statistics.median(zs) - s.elevation)
    return round(statistics.median(offs), 3) if offs else 0.0


def _crosses(e, z: float) -> bool | None:
    b = e.geo.bbox if e.geo else None
    if not b:
        return None
    return b[2] - 1e-6 <= z <= b[5] + 1e-6


def _cut_compare(idx, storey_guid: str, items: dict, classes: tuple[str, ...], cut_z: float, sname: dict) -> dict:
    """Model vs drawing for one storey plan and one kind, aware of the cut plane.
    model: all elements of the kind contained in the storey; model_cut: those crossing the cut plane;
    drawn: drawn elements of this storey (by GUID); drawn_all: everything of the kind on the sheet;
    drawn_other: {storey name: n} drawn from other storeys; ok: drawn == model_cut, None when the SVG tags
    no element of this kind at all (no data, e.g. sheets that tag only rooms)."""
    on = [e for e in idx.in_storey(storey_guid) if e.cls in classes or e.eff_cls in classes]
    model_cut = sum(1 for e in on if _crosses(e, cut_z) is not False)
    drawn, drawn_all, other = 0, 0, {}
    for g, it in items.items():
        if it.cls not in classes:
            continue
        drawn_all += 1
        e = idx.elements.get(g)
        if e is not None and e.storey == storey_guid:
            drawn += 1
        else:
            k = sname.get(e.storey, "?") if e is not None else "not in model"
            other[k] = other.get(k, 0) + 1
    if drawn_all == 0:
        ok = None if model_cut else True  # sheet tags none of this kind: no data (some sheets tag rooms only)
    elif drawn == 0 and model_cut == 0:
        ok = None  # only other storeys' elements are drawn here: informational
    else:
        ok = drawn == model_cut
    return {"model": len(on), "model_cut": model_cut, "drawn": drawn, "drawn_all": drawn_all,
            "drawn_other": other, "ok": ok, "cut_z": round(cut_z, 3)}


def project_graph(path: str) -> dict:
    """The whole project graph behind `path` (ifc_models / ifc_bench); {} for other sources."""
    src = source_of(path)
    if src == "ifc_models":
        from stoa.solvers.ifc.solver import model_for

        model = path if path.endswith(".ifc") else (ifc_model_for(path) or model_for(path))
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
        d = {"number": r.number, "name": r.name, "area_m2_dxf": round(r.area, 2), "apartment": r.unit,
             "outdoor": bool(r.outdoor), "shaft": bool(r.shaft)}
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
        if this is None and not path.endswith(".ifc"):  # e.g. ResBIM raster plan of a one-storey unit
            this = {"path": path, "kind": "raster-plan", "storey": None}
            g = {**g, "files": g["files"] + [this]}
        storey = this.get("storey") if this else None
        out.update({"kind": this["kind"] if this else ("model" if path.endswith(".ifc") else "other"),
                    "model": g["model"], "storey": next((s for s in g["storeys"] if s["guid"] == storey), None),
                    "files": g["files"], "storeys": [{k: s[k] for k in ("guid", "name", "elevation", "plan")}
                                                     for s in g["storeys"]],
                    "rooms": [r for r in g["rooms"] if storey is None or r["storey"] == storey],
                    "same_building": g["same_building"],
                    "crosschecks": [c for c in g["crosschecks"] if storey is None or c["plan"] == this["path"]]})
        gn, ge = _as_graph(g, storey)
        out["graph"] = {"nodes": gn, "edges": ge}
    elif src == "ifc_bench":
        out.update(project_graph(path))
    elif src == "swiss_dwellings" and ".dxf" in sib and ".pdf" in sib:
        out["kind"] = "floor"
        out["same_site"] = sorted({str(Path(path).parent / p.name) for p in
                                   (data_root() / Path(path).parent).glob(f"{out['group'].split('/')[-1]}_*.pdf")} - {sib[".pdf"]})
        out.update(_swiss_floor(sib[".pdf"], sib[".dxf"]))
    out["project"] = out.get("project") or out["group"]
    out["nodes"] = _file_nodes(path, out)
    out["checks"] = _checks(out)
    return out


def _kind(p: str) -> str:
    return Path(p).suffix.lower().lstrip(".")


def _file_nodes(path: str, out: dict) -> list[dict]:
    """W5's 'linked sources' strip: [{path, kind, label, relation}] for every other file about this building."""
    nodes, seen = [], {path}

    def add(p: str, relation: str, label: str | None = None):
        if p and p not in seen:
            seen.add(p)
            nodes.append({"path": p, "kind": _kind(p), "label": label or Path(p).stem, "relation": relation})

    for ext, p in (out.get("siblings") or {}).items():
        add(p, {".svg": "vector twin of this sheet (IFC GUIDs per element)", ".dxf": "CAD source of this drawing",
                ".png": "raster rendering of this drawing", ".pdf": "PDF of this drawing",
                ".ifc": "model this sheet was cut from"}.get(ext, "same drawing, other format"))
    src = out.get("source")
    if src == "ifc_models" and out.get("model"):
        add(out["model"], "model this sheet was cut from" if not path.endswith(".ifc") else "model", "IFC model")
        sto = {s["guid"]: s["name"] for s in out.get("storeys", [])}
        for f in out.get("files", []):
            k = f["kind"]
            if k == "plan":
                rel = "plan of this storey" if f.get("storey") and out.get("storey") and \
                    f["storey"] == out["storey"]["guid"] else "other storey plan"
                add(f["path"], rel, f"plan {sto.get(f.get('storey'), '')}".strip())
                if f.get("svg"):
                    add(f["svg"], f"vector twin of the {sto.get(f.get('storey'), '')} plan".replace("  ", " "))
            elif k in ("section", "elevation"):
                add(f["path"], f"{k} cut from the same model", Path(f["path"]).stem.split("_")[-1])
            elif k == "discipline-model":
                add(f["path"], "other discipline model of the same project")
            elif k == "raster-plan":
                add(f["path"], "raster plan of this model")
        for p in out.get("same_building", []):
            add(p, "same building, other dataset (ifc_bench)")
    elif src == "ifc_bench":
        for f in out.get("files", []):
            if f["kind"] == "discipline-model":
                add(f["path"], "other discipline model of the same project")
        for p in out.get("same_building", []):
            add(p, "same building, other dataset (ifc_models)")
    elif src == "swiss_dwellings":
        for p in out.get("same_site", []):
            add(p, "other floor of the same site")
    return nodes


def _checks(out: dict) -> list[dict]:
    """Cross-checks as UI badges: [{text, ok}] (ok None = no data / informational)."""
    res = []
    for c in out.get("crosschecks", []) or []:
        where = f" on '{c['storey']}'" if c.get("storey") else ""
        if "printed" in c.get("what", ""):
            res.append({"text": f"{c['drawn']}/{c['model']} printed room areas match the DXF polygons",
                        "ok": bool(c.get("ok"))})
            continue
        res.append({"text": cut_text(c, where), "ok": c.get("ok")})
    return res


def cut_text(c: dict, where: str = "") -> str:
    """One readable line for a _cut_compare row."""
    what = c["what"]
    if c["ok"] is None and c["drawn_all"] == 0:
        return (f"{what}{where}: IFC model {c['model']}, but this sheet tags no {what} (no 2D data to compare)")
    head = f"{what}{where}: IFC model {c['model']}"
    if c["model_cut"] != c["model"]:
        head += f" ({c['model_cut']} cut by the plan plane at floor +{CUT_HEIGHT:g} m, " \
                f"{c['model'] - c['model_cut']} entirely above/below it)"
    s = f"{head}, drawn {c['drawn']}"
    if c["ok"] is True:
        s += " ✓"
    elif c["ok"] is False:
        s += f" ≠ {c['model_cut']}"
    if c.get("drawn_other"):
        s += "; the sheet also shows " + ", ".join(f"{n} of '{k}'" for k, n in c["drawn_other"].items()) \
             + " (crossing this cut plane)"
    return s


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


def _swiss_total_check(val: float, scope, filt: dict, rooms: list[dict]) -> str | None:
    """Totals (apartment / all numbered indoor rooms / rooms labelled X): compare with the sum of the PRINTED
    room areas of the same rooms (independent of the DXF polygons) and the DXF polygon sum. Room sets follow
    the dataset's definitions (numbered, indoor; floor totals also drop shafts). None if no set is known."""
    if filt.get("apartment"):
        sel = [r for r in rooms if r.get("apartment") == filt["apartment"] and r["number"] and not r.get("outdoor")]
        what = f"apartment {filt['apartment']}"
    elif filt.get("label"):
        lab = filt["label"] if isinstance(filt["label"], str) else str(filt["label"])
        sel = [r for r in rooms if r["name"] == lab] or [r for r in rooms if (r["name"] or "").lower() == lab.lower()]
        what = f"rooms labelled '{lab}'"
    elif scope in ("floor_total", "storey_total"):
        sel = [r for r in rooms if r["number"] and not r.get("outdoor") and not r.get("shaft")]
        what = "numbered indoor rooms"
    else:
        return None
    if not sel:
        return None
    dxf = sum(r["area_m2_dxf"] for r in sel)
    named = [r for r in sel if r["name"]]
    dxf_named = sum(r["area_m2_dxf"] for r in named)
    if _mark(val, dxf, 0.02) != "✓" and len(named) < len(sel) and _mark(val, dxf_named, 0.02) == "✓":
        # numbered rooms without a name (shafts/voids/storage?) are the dataset's one ambiguity: say which reading
        parts = [f"DXF polygons of the {len(named)} named {what} {dxf_named:.2f} m² ✓ (with the "
                 f"{len(sel) - len(named)} unnamed numbered rooms: {dxf:.2f} m²)"]
        sel = named
    else:
        parts = [f"DXF polygons of the {len(sel)} {what} {dxf:.2f} m² {_mark(val, dxf, 0.02)}"]
    printed = [r["area_m2_printed"] for r in sel if "area_m2_printed" in r]
    if printed and len(printed) == len(sel):
        pv = sum(printed)
        parts.append(f"sum of their printed areas {pv:.2f} m² {_mark(val, pv, 0.02)}")
    elif printed:
        parts.append(f"{len(printed)}/{len(sel)} rooms have a printed area")
    return f"answer {val:.2f} m² vs " + "; ".join(parts)


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
        # only a count over the whole storey/plan compares with the storey's model/plan totals (W5 04:12: "doors of the
        # room 'KORIDOR (119)'" = 12 got a false ✗ against the storey's 46)
        if task == "count" and target in _TARGET_CLASSES and scope in (None, "drawing", "storey"):
            classes = _TARGET_CLASSES[target]
            model_classes = ("IfcStair",) if target == "stair" else classes
            sg = {idx.elements[x].storey for x in guids if x in idx.elements}
            if st is None and guids:  # .ifc question: take the storey of the answer's own elements
                st = idx.storey(next(iter(sg))) if len(sg) == 1 else None
            elif st is not None and len(sg) == 1 and next(iter(sg)) != st.guid and idx.storey(next(iter(sg))) is not None:
                # 'How many walls are there on the ground floor?' asked on the 1.OG sheet: the answer (81, EG's walls)
                # was checked against the SHEET's storey (70) -> false ✗, 0.97 -> 0.68 (W1 c8); check the asked storey
                st = idx.storey(next(iter(sg)))
            if st is None:
                return None
            mc = len(idx.in_storey(st.guid, *model_classes))
            sgraph = next((s for s in g["storeys"] if s["guid"] == st.guid), None)
            drawn_cls = {c for c, n in (sgraph["drawn_counts"] if sgraph else {}).items() if n}
            # only evidence if this plan's SVG tags this kind of element at all (some tag rooms only)
            has_drawing = bool(sgraph and sgraph["plan"] and (drawn_cls & set(classes) or drawn_cls - {"IfcSpace"}))
            dc = sum(sgraph["drawn_counts"].get(c, 0) for c in classes) if has_drawing else None
            parts = [f"IFC model: {mc} {'/'.join(model_classes)} on storey '{st.name}' {_mark(val, mc)}"]
            cut = (sgraph or {}).get("cut", {}).get(next((k for k, cl in _CHECK_KINDS if set(cl) == set(classes)), ""))
            if cut is not None and dc is not None:
                # the sheet draws only what its cut plane (floor + 1.2 m) crosses: compare like with like
                if cut["drawn_all"] == 0 and cut["model_cut"]:
                    parts.append(f"plan drawing: the sheet tags no {'/'.join(classes)} (no 2D data to compare)")
                elif cut["model_cut"] == cut["model"]:
                    parts.append(f"plan drawing: {cut['drawn']} symbols {_mark(val, cut['drawn'])}")
                else:
                    m = "✓" if cut["drawn"] == cut["model_cut"] else "≠"
                    parts.append(f"plan drawing: {cut['drawn']} symbols = the {cut['model_cut']} the cut plane at "
                                 f"floor +{CUT_HEIGHT:g} m crosses {m} ({cut['model'] - cut['model_cut']} lie "
                                 f"entirely above/below it, so they are not drawn)")
            elif dc is not None:
                if target == "stair":
                    # a stair is drawn as its flights; count distinct drawn stairs via the flights' parent
                    drawn_guids = {gd for gd, it in plan_items(sgraph["plan"]).items() if it.cls in classes
                                   and gd in idx.elements and idx.elements[gd].storey == st.guid}
                    dc = len({idx.elements[gd].parent or gd for gd in drawn_guids})
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
        if task == "count" and target in ("door", "window", "wc", "washbasin", "bathtub", "shower") and \
                scope in (None, "drawing"):  # the DXF layer count is the whole floor's, not one apartment's/room's
            key = {"wc": "toilet"}.get(target, target)
            n = f.get("counts_dxf", {}).get(key)
            if n is not None:
                return f"answer {int(round(val))} vs DXF layer count {n} {_mark(val, n)}"
        if task == "area":
            filt = (intent.get("filters") if isinstance(intent, dict) else getattr(intent, "filters", None)) or {}
            rooms = f.get("rooms", [])
            agg = scope in ("apartment", "floor_total", "storey_total", "label_total") or (
                not filt.get("room_no") and (filt.get("apartment") or filt.get("label")))
            if agg:
                return _swiss_total_check(val, scope, filt, rooms)
            room = None
            if filt.get("room_no"):
                room = next((r for r in rooms if r["number"] == filt["room_no"]), None)
            if room is None:  # single-room question without a number: the room under the ONE evidence box
                boxes = [e.get("bbox") if isinstance(e, dict) else e.bbox for e in
                         (getattr(answer, "evidence", None) or (answer.get("evidence") if isinstance(answer, dict) else None) or [])]
                boxes = [b for b in boxes if b]
                if len(boxes) == 1 and scope in (None, "room", "drawing"):
                    def ov(a, b):
                        w = min(a[2], b[2]) - max(a[0], b[0])
                        h = min(a[3], b[3]) - max(a[1], b[1])
                        return max(w, 0) * max(h, 0)
                    best = max(rooms, key=lambda r: ov(r.get("bbox_pt") or [0, 0, 0, 0], boxes[0]), default=None)
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
