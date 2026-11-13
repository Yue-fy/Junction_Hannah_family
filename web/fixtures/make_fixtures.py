"""Generate demo fixture Answers for the web mock API from REAL evidence (no gold answers are read).

Each fixture is computed the way a deterministic solver would do it (PDF text layer, IfcConvert SVG
GUID groups, IfcOpenShell quantities, DXF layers), so the boxes and GUIDs the UI draws are real and
the fixtures double as an end-to-end check of the coordinate conventions in docs/CONTRACT.md.

    $JUNCTION_VENV/bin/python web/fixtures/make_fixtures.py   # writes web/fixtures/answers.json
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pymupdf

ROOT = Path(os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset"))
OUT = Path(__file__).with_name("answers.json")
MM_TO_PT = 72 / 25.4


def cost(t0: float) -> dict:
    return {"llm_tokens_in": 0, "llm_tokens_out": 0, "gpu_seconds": 0.0, "api_calls": 0, "api_tokens_in": 0,
            "api_tokens_out": 0, "llm_calls": 0, "wall_seconds": round(time.perf_counter() - t0, 3)}


def rect(r) -> list[float]:
    return [round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)]


# --- ifc_models: SVG sibling (IfcConvert) gives GUID -> 2D shape on the plan ---------------------------
def path_points(d: str) -> list[tuple[float, float]]:
    """End points of an absolute M/L/A path (IfcConvert only emits these). Arc flags are not coordinates."""
    pts = []
    for cmd, args in re.findall(r"([MLAZmlaz])([^MLAZmlaz]*)", d):
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?(?:e-?\d+)?", args)]
        if cmd in "ML":
            pts += list(zip(nums[0::2], nums[1::2]))
        elif cmd == "A":
            pts += [(nums[i + 5], nums[i + 6]) for i in range(0, len(nums) - 6, 7)]
        elif cmd in "mla":
            raise ValueError(f"relative path command {cmd} not supported")
    return pts


def svg_groups(svg_path: Path) -> tuple[list[float], list[dict]]:
    svg = svg_path.read_text()
    vb = [float(v) for v in re.search(r'viewBox="([^"]*)"', svg).group(1).split()]
    groups = []
    for m in re.finditer(r'<g ([^>]*data-guid="[^"]*"[^>]*)>(.*?)</g>', svg, re.S):
        attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        cls, name, guid, body = attrs.get("class", ""), attrs.get("data-name"), attrs["data-guid"], m.group(2)
        pts = [p for d in re.findall(r' d="([^"]*)"', body) for p in path_points(d)]
        if len(pts) < 2:
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        bbox = [(min(xs) - vb[0]) * MM_TO_PT, (min(ys) - vb[1]) * MM_TO_PT,
                (max(xs) - vb[0]) * MM_TO_PT, (max(ys) - vb[1]) * MM_TO_PT]
        groups.append({"cls": cls.split()[-1], "name": name or "", "guid": guid,
                       "bbox": [round(v, 2) for v in bbox], "pts": pts})
    return vb, groups


def shoelace(pts) -> float:
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))) / 2


def esplanades() -> list[dict]:
    import ifcopenshell
    import ifcopenshell.util.element as ue

    model = "data/ifc_models/bsc-esplanades_1807-ep-ar-v18"
    plan, ifc = f"{model}_plan-01-1-korrus.pdf", f"{model}.ifc"
    out = []

    t0 = time.perf_counter()
    _, groups = svg_groups(ROOT / (plan[:-4] + ".svg"))
    f = ifcopenshell.open(str(ROOT / ifc))
    storey = next(s for s in f.by_type("IfcBuildingStorey") if s.Name == "1.korrus")
    ifc_doors = [d for d in f.by_type("IfcDoor") if ue.get_container(d) == storey]
    doors = [g for g in groups if g["cls"] == "IfcDoor"]
    same = {g["guid"] for g in doors} == {d.GlobalId for d in ifc_doors}
    ev = [{"file": plan, "page": 0, "bbox": g["bbox"], "bbox_space": "pdf_pt", "ifc_guid": g["guid"],
           "note": f"door {i + 1}"} for i, g in enumerate(doors)]
    ev.append({"file": ifc, "page": None, "bbox": None, "bbox_space": None, "ifc_guid": storey.GlobalId,
               "note": f"cross-check: plan {len(doors)} door symbols = IFC storey '1.korrus' {len(ifc_doors)} IfcDoor"
                       + (" ✓" if same else " ✗")})
    out.append({"path": plan, "question": "How many doors are shown on the floor plan of '1.korrus'?", "answer": {
        "value": len(doors), "unit": "count", "confidence": 0.97 if same else 0.6, "evidence": ev,
        "trace": ["parsed: count · target=door · storey='1.korrus'",
                  "plan .svg sibling (IfcConvert): %d groups class=IfcDoor" % len(doors),
                  "IFC: %d IfcDoor contained in IfcBuildingStorey '1.korrus'" % len(ifc_doors),
                  "cross-check: same %d GlobalIds in drawing and model %s" % (len(doors), "✓" if same else "✗")],
        "solver": "fixture:ifc_svg", "assumptions": ["each IfcDoor drawn on the plan is one door"],
        "missing": [], "cost": cost(t0)}})

    t0 = time.perf_counter()
    space = next(g for g in groups if g["cls"] == "IfcSpace" and g["name"] == "119")
    sp = f.by_guid(space["guid"])
    psets = ue.get_psets(sp)
    qto = next((v["NetFloorArea"] for v in psets.values() if "NetFloorArea" in v), None)
    prop = next((float(str(v[k]).replace(",", ".")) for v in psets.values() for k in v
                 if k.lower().endswith("pindala") or k.lower() in ("area", "netarea")), None)
    paper = shoelace(space["pts"]) * (100 / 1000) ** 2  # paper mm² at 1:100 -> m²
    ref = qto if qto is not None else prop
    ref_name = "Qto NetFloorArea" if qto is not None else "property AR_Ruum.120_Pindala"
    agree = ref is not None and abs(paper - ref) / ref < 0.02
    out.append({"path": plan, "question": "What is the net floor area of the room 'KORIDOR (119)' on '1.korrus', in m²?",
                "answer": {
                    "value": round(qto if qto is not None else paper, 2), "unit": "m2",
                    "confidence": 0.93 if agree else 0.6,
                    "evidence": [
                        {"file": plan, "page": 0, "bbox": space["bbox"], "bbox_space": "pdf_pt",
                         "ifc_guid": space["guid"], "note": "IfcSpace 119 KORIDOR outline on the plan"},
                        {"file": ifc, "page": None, "bbox": None, "bbox_space": None, "ifc_guid": space["guid"],
                         "note": f"cross-check: outline {paper:.2f} m² vs IFC {ref_name} {ref} m²"
                                 + (" ✓" if agree else " ✗")}],
                    "trace": ["parsed: area · room='KORIDOR (119)' · storey='1.korrus'",
                              "plan .svg: IfcSpace data-name=119 → GlobalId " + space["guid"],
                              f"outline polygon on the sheet × 100² (scale 1:100) = {paper:.2f} m²",
                              f"cross-check: IFC {ref_name} = {ref} m² {'✓' if agree else '✗'} (no Qto in this model)"],
                    "solver": "fixture:ifc_svg",
                    "assumptions": ["sheet scale 1:100 as printed in the title block",
                                    "IfcSpace outline at the 1.20 m cut = net floor outline"],
                    "missing": ["no Qto_SpaceBaseQuantities in the IFC; property value is rounded to 0.1 m²"],
                    "cost": cost(t0)}})
    return out


# --- swiss_dwellings: PDF text layer + DXF ROOM_TEXT cross-check -------------------------------------------
def swiss() -> list[dict]:
    import ezdxf

    path = "data/swiss_dwellings/site1000_bldg2082_floor9385.pdf"
    out = []
    t0 = time.perf_counter()
    page = pymupdf.open(ROOT / path)[0]
    words = page.get_text("words")
    hits = [w for w in words if w[4] == "Zimmer"]
    dxf = ezdxf.readfile(ROOT / (path[:-4] + ".dxf"))
    dxf_n = sum(1 for e in dxf.modelspace() if e.dxf.layer == "ROOM_TEXT" and e.dxftype() in ("TEXT", "MTEXT")
                and (e.dxf.text if e.dxftype() == "TEXT" else e.text).strip() == "Zimmer")
    ok = dxf_n == len(hits)
    ev = [{"file": path, "page": 0, "bbox": rect(pymupdf.Rect(w[:4])), "bbox_space": "pdf_pt", "ifc_guid": None,
           "note": f"'Zimmer' {i + 1}"} for i, w in enumerate(hits)]
    ev[0]["note"] += f" · cross-check: DXF ROOM_TEXT 'Zimmer' ×{dxf_n}" + (" ✓" if ok else " ✗")
    out.append({"path": path, "question": "How many rooms labelled 'Zimmer' are there on this floor?", "answer": {
        "value": len(hits), "unit": "count", "confidence": 0.96 if ok else 0.6, "evidence": ev,
        "trace": ["parsed: count · target=room label 'Zimmer' (whole word)",
                  f"PDF text layer: {len(hits)} words 'Zimmer'",
                  f"cross-check: DXF layer ROOM_TEXT has {dxf_n} × 'Zimmer' {'✓' if ok else '✗'}"],
        "solver": "fixture:pdf_text", "assumptions": ["one label per room"], "missing": [], "cost": cost(t0)}})

    t0 = time.perf_counter()
    num = next(w for w in words if w[4] == "2.10")
    # the printed area sits right under the room number: nearest 'm²' line below it
    cand = [w for w in words if re.fullmatch(r"\d+\.\d\d", w[4]) and w[1] > num[1] and abs(w[0] - num[0]) < 40]
    area = min(cand, key=lambda w: (w[1] - num[1]) ** 2 + (w[0] - num[0]) ** 2)
    out.append({"path": path, "question": "What is the net floor area of room 2.10 ('Zimmer') in m²?", "answer": {
        "value": float(area[4]), "unit": "m2", "confidence": 0.93,
        "evidence": [{"file": path, "page": 0, "bbox": rect(pymupdf.Rect(num[:4]) | pymupdf.Rect(area[:4])),
                      "bbox_space": "pdf_pt", "ifc_guid": None, "note": f"room 2.10 label, printed {area[4]} m²"}],
        "trace": ["parsed: area · room number 2.10 · label 'Zimmer'",
                  "PDF text layer: room number 2.10 found", f"printed net area below it: {area[4]} m²"],
        "solver": "fixture:pdf_text", "assumptions": ["the printed area is the net floor area"],
        "missing": ["DXF ROOM_OUTLINE polygon not measured in this fixture"], "cost": cost(t0)}})
    return out


# --- opening_design: rotated sheet (page /Rotate 90) schedule row ------------------------------------------
def opening_design() -> list[dict]:
    path = ("data/opening_design/Sports_Complex/Sheets - Current Set/"
            "A-801 - Door and Finish Schedules & Wall Types.pdf")
    t0 = time.perf_counter()
    page = pymupdf.open(ROOT / path)[0]
    val = page.search_for("29690")[0]
    room = [r for r in page.search_for("128") if abs(r.x0 - val.x0) < 400 and abs(r.y0 - val.y0) < 600]
    ev = [{"file": path, "page": 0, "bbox": rect(val), "bbox_space": "pdf_pt", "ifc_guid": None,
           "note": "finish schedule: area 29690"}]
    ev += [{"file": path, "page": 0, "bbox": rect(r), "bbox_space": "pdf_pt", "ifc_guid": None,
            "note": "room 128"} for r in room[:1]]
    q = ("On sheet A-801 of the Xcel Sports Complex drawings, what is the area of room 128 (Fieldhouse) in the "
         "finish room schedule, in square feet?")
    return [{"path": path, "question": q, "answer": {
        "value": 29690, "unit": "ft2", "confidence": 0.8, "evidence": ev,
        "trace": ["parsed: area · room 128 (Fieldhouse) · finish room schedule", "PDF text layer: row value 29690",
                  "sheet is rotated 90°: boxes are in unrotated pdf_pt (PyMuPDF), viewer applies /Rotate"],
        "solver": "fixture:pdf_text", "assumptions": ["schedule area column is in ft²"],
        "missing": ["row alignment of the value and room 128 not verified by a table parser"], "cost": cost(t0)}}]


def main() -> None:
    fixtures = esplanades() + swiss() + opening_design()
    OUT.write_text(json.dumps(fixtures, indent=1, ensure_ascii=False))
    for fx in fixtures:
        a = fx["answer"]
        print(f"{fx['path'].split('/')[-1][:50]:50} {a['value']} {a['unit']} ev={len(a['evidence'])} | {a['trace'][-1]}")


if __name__ == "__main__":
    main()
