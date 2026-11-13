"""Test drop rules for unnamed numbered rooms on train 'total' + 'apartment' questions (exact subset solutions)."""
import collections
import itertools
import sys

from stoa.data import abspath, siblings
from stoa.eval.splits import load_split
from stoa.solvers.vector.floor import load_floor

qs = [q for q in load_split("train") if q.source == "swiss_dwellings" and q.type == "area"
      and "total net floor area in m² of all numbered" in q.question][: int(sys.argv[1]) if len(sys.argv) > 1 else 300]
rows = []
for q in qs:
    fm = load_floor(str(abspath(siblings(q.path)[".dxf"])))
    named = [r for r in fm.rooms if r.number and r.name and not r.outdoor]
    U = [r for r in fm.rooms if r.number and not r.name]
    rest = float(q.answer) - sum(r.area for r in named)
    if not U or len(U) > 14:
        continue
    sols = [set(c) for k in range(len(U) + 1) for c in itertools.combinations(range(len(U)), k)
            if abs(sum(U[i].area for i in c) - rest) <= 0.03]
    if len(sols) != 1:
        continue
    doors = fm.items["door"]
    fx = [it for k in ("toilet", "washbasin", "bathtub", "shower") for it in fm.items[k]]
    from shapely.geometry import box
    for i, r in enumerate(U):
        buf = r.poly.buffer(0.12)
        nd = sum(1 for d in doors if buf.intersects(box(*d.bbox)))
        nf = sum(1 for d in fx if r.poly.intersects(box(*d.bbox)))
        mrr = r.poly.minimum_rotated_rectangle.exterior.coords
        import math
        ms = min(math.dist(mrr[0], mrr[1]), math.dist(mrr[1], mrr[2]))
        rows.append(dict(kept=i in sols[0], area=r.area, nd=nd, nf=nf, ms=ms))
print(len(rows), collections.Counter(r["kept"] for r in rows))
print("doors adj:", sorted(collections.Counter((r["kept"], min(r["nd"], 2)) for r in rows).items()))
print("fixtures:", sorted(collections.Counter((r["kept"], min(r["nf"], 1)) for r in rows).items()))
for r in rows:
    if r["nd"] == 0:
        print(("KEEP" if r["kept"] else "DROP"), f"a={r['area']:.2f} ms={r['ms']:.2f} nf={r['nf']}")
