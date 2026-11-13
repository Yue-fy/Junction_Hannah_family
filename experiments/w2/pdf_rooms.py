"""PDF-only swiss rooms: polygons = filled paths stroked grey 0.54 (width 0.37), scale from the printed title block
("Massstab 1:200 (A3)"), room number = text span inside. Compare each room's PDF-only area with the DXF polygon.
Run: PYTHONPATH=$PWD $JUNCTION_VENV/bin/python experiments/w2/pdf_rooms.py [n_floors]
"""
import os
import re
import sys

import pymupdf
from shapely.geometry import Point, Polygon

from stoa.solvers.vector.floor import load_floor

D = os.environ["STOA_DATA"] + "/data/swiss_dwellings/"
n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
stems = sorted(f[:-4] for f in os.listdir(D) if f.endswith(".dxf"))[5::31][:n]
NUM = re.compile(r"^[A-Z]{0,2}\d+(?:\.\d+)+$")


def pdf_rooms(pdf):
    page = pymupdf.open(pdf)[0]
    words = page.get_text("words")
    txt = " ".join(w[4] for w in words)
    m = re.search(r"1\s*:\s*(\d+)", txt)
    if not m:
        return None, []
    s = 72 / 0.0254 / int(m.group(1))  # pt per metre on paper
    polys = []
    for d in page.get_drawings():
        col = tuple(round(x, 2) for x in (d.get("color") or ()))
        if d["type"] != "fs" or col != (0.54, 0.54, 0.54) or round(d.get("width") or 0, 2) != 0.37:
            continue
        pts = []
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
        if len(pts) >= 3:
            p = Polygon(pts)
            if p.is_valid and p.area > 0:
                polys.append(p)
    rooms = []
    for w in words:
        if NUM.match(w[4]):
            c = Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)
            inside = [p for p in polys if p.contains(c)]
            if inside:
                p = min(inside, key=lambda p: p.area)
                rooms.append((w[4], p.area / s**2))
    return s, rooms


tot = ok = 0
bad = []
for st in stems:
    s, rooms = pdf_rooms(D + st + ".pdf")
    fm = load_floor(D + st + ".dxf")
    dx = {r.number: r.area for r in fm.rooms if r.number}
    for num, a in rooms:
        if num in dx:
            tot += 1
            if abs(a - dx[num]) <= 0.02 * dx[num]:
                ok += 1
            elif len(bad) < 8:
                bad.append((st, num, round(a, 2), round(dx[num], 2)))
    missing = len(set(dx) - {r[0] for r in rooms})
    if missing:
        bad.append((st, "rooms without PDF polygon", missing, len(dx)))
print(f"PDF-only room area within 2% of DXF: {ok}/{tot}")
for b in bad[:12]:
    print(b)
