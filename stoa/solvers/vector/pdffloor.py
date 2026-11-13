"""PDF-only floor model for Swiss-Dwellings-style vector PDFs (no DXF needed).

The PDF renderer draws each layer with its own style, found by matching PDF paths to DXF entities on 10 floors
(experiments/w2/pdf_style_layers.py):
- rooms     = filled paths stroked grey 0.54, width 0.37 (fill colour varies by room type)   222/222 ROOM_OUTLINE
- apartments= strokes (0.69, 0.23, 0.18), width ~1.2-1.3 (dash-dot)                         37/37 UNIT_OUTLINE
- doors     = strokes grey 0.27, width 0.37 (the leaf)                                       = DXF door count 20/20 floors
- texts     = text spans (each DXF TEXT is one span)
Scale from the printed title block ("Massstab 1:200 (A3)" / "Échelle 1:100" / "Scala 1:100"): s = 72/0.0254/N pt per
metre on paper. Coordinates are converted to metres with y up (x_m = x_pt/s, y_m = -y_pt/s), so the same rules
(floor.assemble) and evidence mapping (x_pt = s*x_m, y_pt = -s*y_m) apply.
Measured: room areas from the PDF alone are within 2% of the DXF polygons for 796/797 rooms on 30 floors
(experiments/w2/pdf_rooms.py). Windows and fixtures share styles with other symbols: not identified here.
"""

from __future__ import annotations

import functools
import re

from stoa.solvers.vector.floor import FloorModel, Text, assemble
from stoa.solvers.vector.pdfmap import Transform

ROOM_STYLE = ("fs", (0.54, 0.54, 0.54), 0.37)
DOOR_STYLE = ("s", (0.27, 0.27, 0.27), 0.37)
UNIT_COLOR = (0.69, 0.23, 0.18)
SUPPORTED = frozenset({"door", "apartment"})


def _pts(d) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for it in d["items"]:
        if it[0] == "l":
            if not pts:
                pts.append((it[1].x, it[1].y))
            pts.append((it[2].x, it[2].y))
        elif it[0] == "re":
            r = it[1]
            pts = [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
        elif it[0] == "qu":
            q = it[1]
            pts = [(q.ul.x, q.ul.y), (q.ur.x, q.ur.y), (q.lr.x, q.lr.y), (q.ll.x, q.ll.y)]
        elif it[0] == "c":  # bezier: keep end points
            if not pts:
                pts.append((it[1].x, it[1].y))
            pts.append((it[4].x, it[4].y))
    return pts


@functools.lru_cache(maxsize=128)
def load_pdf_floor(pdf_abspath: str) -> tuple[FloorModel | None, Transform | None, str]:
    """-> (FloorModel in metres, Transform metres->pdf_pt, note). (None, None, reason) if not a supported drawing."""
    import pymupdf

    with pymupdf.open(pdf_abspath) as doc:
        page = doc[0]
        text = page.get_text("text")
        m = re.search(r"(?:Massstab|Masstab|Échelle|Echelle|Scala|Scale)\s*1\s*:\s*(\d+)", text, re.I) or \
            re.search(r"\b1\s*:\s*(50|100|200|250|500)\b", text)
        if not m:
            return None, None, "no printed scale (1:N) on the sheet"
        s = 72 / 0.0254 / int(m.group(1))
        to_m = lambda x, y: (x / s, -y / s)  # noqa: E731
        room_pts, unit_pts, door_boxes = [], [], []
        for d in page.get_drawings():
            col = tuple(round(x, 2) for x in (d.get("color") or ()))
            w = round(d.get("width") or 0, 2)
            if (d["type"], col, w) == ROOM_STYLE:
                pts = _pts(d)
                if len(pts) >= 3:
                    room_pts.append([to_m(*p) for p in pts])
            elif col == UNIT_COLOR and w >= 1.1:
                pts = _pts(d)
                if len(pts) >= 3:
                    unit_pts.append([to_m(*p) for p in pts])
            elif (d["type"], col, w) == DOOR_STYLE:
                r = d["rect"]
                (x0, y1), (x1, y0) = to_m(r.x0, r.y0), to_m(r.x1, r.y1)
                door_boxes.append((x0, y0, x1, y1))
        texts, annotations = [], []
        for b in page.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                for sp in line["spans"]:
                    t = sp["text"].strip()
                    if not t:
                        continue
                    x0, y0, x1, y1 = sp["bbox"]
                    cx, cy = to_m((x0 + x1) / 2, (y0 + y1) / 2)
                    texts.append(Text(t, cx, cy, (y1 - y0) / s, "ROOM_TEXT"))
        pw, ph = page.rect.width, page.rect.height
    if not room_pts:
        return None, None, "no room polygons in the PDF's vector layer"
    # long title-block lines are annotations, not room labels
    room_texts = [t for t in texts if len(t.text) <= 40]
    annotations = [Text(t.text, t.x, t.y, t.h, "ANNOTATION") for t in texts if len(t.text) > 40 or re.search(r"1\s*:\s*\d+", t.text)]
    fm = assemble(pdf_abspath, room_pts, unit_pts, room_texts, annotations, door_boxes, [], [], [], [],
                  {"DOOR:LWPOLYLINE": len(door_boxes)}, None,
                  [f"PDF-only model, scale 1:{m.group(1)} from the title block"], supported=SUPPORTED)
    tf = Transform(s=s, a=0.0, b=0.0, n_anchors=0, rms_pt=0.0, page_w=pw, page_h=ph)
    return fm, tf, f"PDF-only: scale 1:{m.group(1)}, {len(fm.rooms)} room polygons, {len(door_boxes)} doors"
