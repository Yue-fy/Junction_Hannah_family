"""2D <-> 3D link for ifc_models plans: IFC GlobalId -> box on the rendered plan PDF, room -> label position.

Every `<model>_plan-NN-<level>.pdf` has an `.svg` twin written by IfcConvert, where each drawn IFC product is
`<g class="IfcDoor" data-guid="..." data-name="...">` with its paths, and room labels are `<text>` lines
(name, number) placed inside the room. The PDF is the SVG printed 1:1 (W5, KNOWLEDGE 00:20):

    pdf_pt = (svg_xy - viewBox[x0, y0]) * 72 / 25.4     (no y flip, rotation 0)

    from stoa.solvers.ifc.plan2d import plan_items, plans_of_model
    items = plan_items("data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf")
    items["2yu9t5gFecDw4PK0F5sh2s"]  # PlanItem(cls='IfcSpace', bbox=(x0,y0,x1,y1) in pdf_pt, label='KORIDOR 119', ...)
"""

from __future__ import annotations

import functools
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from stoa.data import abspath, data_root

MM_TO_PT = 72.0 / 25.4
_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_TOK = re.compile(r"[MmLlAaHhVvZzCcQqSsTt]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


@dataclass
class PlanItem:
    guid: str
    cls: str
    name: str | None
    bbox: tuple[float, float, float, float]  # pdf_pt
    polygon: list[tuple[float, float]] | None = None  # pdf_pt, first closed ring (spaces)
    label: str | None = None  # room label text found inside the polygon ("KORIDOR 119")
    label_bbox: tuple[float, float, float, float] | None = None  # pdf_pt


def _path_points(d: str) -> list[list[tuple[float, float]]]:
    """Absolute M/L/A/H/V paths -> list of rings (points only; arcs contribute their end points)."""
    toks = _TOK.findall(d)
    rings: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    i, cmd, x, y = 0, "M", 0.0, 0.0
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in "Zz":
                if cur:
                    rings.append(cur)
                cur = []
            continue
        try:
            if cmd in "ML":
                x, y = float(toks[i]), float(toks[i + 1])
                if cmd == "M" and cur:
                    rings.append(cur)
                    cur = []
                cur.append((x, y))
                i += 2
                cmd = "L" if cmd == "M" else cmd
            elif cmd in "ml":
                x, y = x + float(toks[i]), y + float(toks[i + 1])
                cur.append((x, y))
                i += 2
            elif cmd == "A":
                x, y = float(toks[i + 5]), float(toks[i + 6])
                cur.append((x, y))
                i += 7
            elif cmd == "H":
                x = float(toks[i])
                cur.append((x, y))
                i += 1
            elif cmd == "V":
                y = float(toks[i])
                cur.append((x, y))
                i += 1
            else:  # curves etc.: take the last pair of each segment roughly
                n = {"C": 6, "Q": 4, "S": 4, "T": 2}.get(cmd.upper(), 2)
                x, y = float(toks[i + n - 2]), float(toks[i + n - 1])
                cur.append((x, y))
                i += n
        except (IndexError, ValueError):
            break
    if cur:
        rings.append(cur)
    return rings


@functools.lru_cache(maxsize=256)
def plan_items(plan_path: str) -> dict[str, PlanItem]:
    """GUID -> PlanItem for a rendered plan (dataset-relative .pdf or .svg). {} if there is no SVG twin."""
    svg = abspath(str(Path(plan_path).with_suffix(".svg")))
    if not svg.exists():
        return {}
    root = ET.parse(svg).getroot()
    ns = "{http://www.w3.org/2000/svg}"
    vb = [float(v) for v in _NUM.findall(root.get("viewBox", "0 0 0 0"))]
    ox, oy = (vb[0], vb[1]) if len(vb) >= 2 else (0.0, 0.0)

    def to_pt(x: float, y: float) -> tuple[float, float]:
        return ((x - ox) * MM_TO_PT, (y - oy) * MM_TO_PT)

    items: dict[str, PlanItem] = {}
    for g in root.iter(f"{ns}g"):
        guid = g.get("data-guid")
        if not guid:
            continue
        rings = []
        for p in g.iter(f"{ns}path"):
            rings += _path_points(p.get("d", ""))
        pts = [to_pt(x, y) for r in rings for x, y in r]
        if not pts:
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        bbox = (min(xs), min(ys), max(xs), max(ys))
        cls = (g.get("class") or "").split()[0] if g.get("class") else ""
        poly = [to_pt(x, y) for x, y in max(rings, key=len)] if cls == "IfcSpace" and rings else None
        if guid in items:  # same product drawn twice (cut + projection): merge boxes
            b = items[guid].bbox
            bbox = (min(b[0], bbox[0]), min(b[1], bbox[1]), max(b[2], bbox[2]), max(b[3], bbox[3]))
            items[guid].bbox = bbox
            continue
        items[guid] = PlanItem(guid=guid, cls=cls, name=g.get("data-name"), bbox=bbox, polygon=poly)
    _attach_labels(root, ns, items, to_pt)
    return items


def _attach_labels(root, ns, items: dict[str, PlanItem], to_pt) -> None:
    from shapely.geometry import Point, Polygon

    texts = []
    for t in root.iter(f"{ns}text"):
        s = "".join(t.itertext()).strip()
        if not s:
            continue
        try:
            x, y = float(t.get("x")), float(t.get("y"))
            fs = float(t.get("font-size", "2"))
        except (TypeError, ValueError):
            continue
        texts.append((x, y, fs, s))
    if not texts:
        return
    spaces = [(it, Polygon(it.polygon)) for it in items.values() if it.cls == "IfcSpace" and it.polygon
              and len(it.polygon) >= 3]
    for it, poly in spaces:
        if not poly.is_valid:
            poly = poly.buffer(0)
        inside = [(x, y, fs, s) for x, y, fs, s in texts if poly.contains(Point(to_pt(x, y)))]
        if not inside:
            continue
        # prefer the text block that contains the space's number (data-name)
        anchor = next((t for t in inside if it.name and t[3] == it.name), inside[0])
        block = [t for t in inside if abs(t[0] - anchor[0]) < 0.5 and abs(t[1] - anchor[1]) <= 3 * anchor[2]]
        block.sort(key=lambda t: t[1])
        it.label = " ".join(t[3] for t in block)
        x0 = min(t[0] - 0.3 * t[2] * len(t[3]) for t in block)
        x1 = max(t[0] + 0.3 * t[2] * len(t[3]) for t in block)
        y0 = min(t[1] - t[2] for t in block)
        y1 = max(t[1] + 0.25 * t[2] for t in block)
        p0, p1 = to_pt(x0, y0), to_pt(x1, y1)
        it.label_bbox = (p0[0], p0[1], p1[0], p1[1])


@functools.lru_cache(maxsize=64)
def plans_of_model(model_path: str) -> dict[str, str]:
    """storey guid -> dataset-relative plan PDF for a model (via plan_storey on each plan file)."""
    from stoa.solvers.ifc.index import load_index
    from stoa.solvers.ifc.solver import plan_storey

    stem = Path(model_path).stem
    folder = Path(model_path).parent
    idx = load_index(model_path)
    out: dict[str, str] = {}
    for pdf in sorted((data_root() / folder).glob(f"{stem}_plan-*.pdf")):
        rel = str(folder / pdf.name)
        st, _ = plan_storey(rel, idx)
        if st is not None and st.guid not in out:
            out[st.guid] = rel
    return out
