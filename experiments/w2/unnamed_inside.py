"""What lies inside kept vs dropped unnamed numbered rooms (other DXF layers)?"""
import collections
import itertools
import sys

import ezdxf
from ezdxf import bbox as ezbbox
from shapely.geometry import Point

from stoa.data import abspath, siblings
from stoa.eval.splits import load_split
from stoa.solvers.vector.floor import load_floor

qs = [q for q in load_split("train") if q.source == "swiss_dwellings" and q.type == "area"
      and "total net floor area in m² of all numbered" in q.question][: int(sys.argv[1]) if len(sys.argv) > 1 else 200]
stats = {True: collections.Counter(), False: collections.Counter()}
nrooms = collections.Counter()
examples = []
for q in qs:
    dxf = str(abspath(siblings(q.path)[".dxf"]))
    fm = load_floor(dxf)
    named = [r for r in fm.rooms if r.number and r.name and not r.outdoor]
    U = [r for r in fm.rooms if r.number and not r.name]
    rest = float(q.answer) - sum(r.area for r in named)
    if not U or len(U) > 14:
        continue
    sols = [set(c) for k in range(len(U) + 1) for c in itertools.combinations(range(len(U)), k)
            if abs(sum(U[i].area for i in c) - rest) <= 0.03]
    if len(sols) != 1:
        continue
    msp = ezdxf.readfile(dxf).modelspace()
    ents = []
    for e in msp:
        if e.dxf.layer in ("ROOM_OUTLINE", "ROOM_TEXT", "UNIT_OUTLINE"):
            continue
        try:
            b = ezbbox.extents([e])
            c = ((b.extmin.x + b.extmax.x) / 2, (b.extmin.y + b.extmax.y) / 2)
        except Exception:
            continue
        ents.append((f"{e.dxf.layer}:{e.dxftype()}", c))
    for i, r in enumerate(U):
        kept = i in sols[0]
        nrooms[kept] += 1
        inside = collections.Counter(k for k, c in ents if r.poly.contains(Point(c)))
        for k in inside:
            stats[kept][k] += 1
        stats[kept]["<empty>"] += not inside
        if not kept and len(examples) < 8:
            examples.append((q.path[21:], r.number, round(r.area, 2), dict(inside)))
print(nrooms)
for kept in (True, False):
    print("kept" if kept else "DROPPED", {k: f"{v/nrooms[kept]:.0%}" for k, v in stats[kept].most_common(12)})
for e in examples:
    print(e)
