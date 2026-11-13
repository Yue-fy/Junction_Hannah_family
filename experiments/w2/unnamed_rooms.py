"""Unnamed numbered rooms (number text but no name): does the reference include them in the floor total?
For each train 'total' question, gold - sum(named indoor numbered rooms) must equal the sum of a subset of
the unnamed rooms; find that subset exactly (|U| <= 14) and tabulate features of kept vs dropped rooms.
"""
import collections
import itertools
import sys

from stoa.data import abspath, siblings
from stoa.eval.splits import load_split
from stoa.solvers.vector.floor import load_floor

qs = [q for q in load_split("train") if q.source == "swiss_dwellings" and q.type == "area"
      and "total net floor area in m² of all numbered" in q.question][: int(sys.argv[1]) if len(sys.argv) > 1 else 300]
rows = []
amb = 0
for q in qs:
    fm = load_floor(str(abspath(siblings(q.path)[".dxf"])))
    named = [r for r in fm.rooms if r.number and r.name and not r.outdoor]
    U = [r for r in fm.rooms if r.number and not r.name]
    rest = float(q.answer) - sum(r.area for r in named)
    if len(U) > 14:
        continue
    sols = []
    for k in range(len(U) + 1):
        for combo in itertools.combinations(range(len(U)), k):
            if abs(sum(U[i].area for i in combo) - rest) <= 0.03:
                sols.append(set(combo))
    if len(sols) != 1:
        amb += bool(sols)
        continue
    for i, r in enumerate(U):
        th = [t.h for t in r.texts]
        mrr = r.poly.minimum_rotated_rectangle
        ex = mrr.exterior.coords
        import math
        sides = sorted([math.dist(ex[0], ex[1]), math.dist(ex[1], ex[2])])
        rows.append(dict(kept=i in sols[0], area=r.area, h=min(th) if th else 0, minside=sides[0], unit=r.unit is not None,
                         n_vert=len(r.poly.exterior.coords) - 1, fill=r.area / max(mrr.area, 1e-9)))
print("rooms", len(rows), "kept", sum(r["kept"] for r in rows), "ambiguous floors", amb)
for key in ("area", "minside", "h"):
    for kept in (True, False):
        v = sorted(r[key] for r in rows if r["kept"] == kept)
        if v:
            print(f"{key:8s} kept={kept!s:5s} n={len(v):4d} min {v[0]:.3f} p10 {v[len(v)//10]:.3f} med {v[len(v)//2]:.3f} p90 {v[9*len(v)//10]:.3f} max {v[-1]:.3f}")
print("unit:", collections.Counter((r["kept"], r["unit"]) for r in rows))
print("text h:", collections.Counter((r["kept"], round(r["h"], 3)) for r in rows).most_common(12))
