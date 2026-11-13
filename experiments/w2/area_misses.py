"""Which rooms does the reference drop when our apartment/total net area overshoots? (train split only)
Run from the worktree root: PYTHONPATH=$PWD $JUNCTION_VENV/bin/python experiments/w2/area_misses.py [n]
"""
import collections
import itertools
import sys

from stoa.data import abspath, siblings
from stoa.eval.splits import load_split
from stoa.solvers.vector import qparse
from stoa.solvers.vector.floor import load_floor

n = int(sys.argv[1]) if len(sys.argv) > 1 else 400
qs = [q for q in load_split("train") if q.source == "swiss_dwellings" and q.type == "area"]
qs = [q for q in qs if any(w in q.question for w in ("apartment ", "total net floor area in m² of all numbered"))]
qs = qs[:n]
tot = collections.Counter()
hit = collections.Counter()
dropped = collections.Counter()
dropped_feat = collections.Counter()
unexplained = []
for q in qs:
    fm = load_floor(str(abspath(siblings(q.path)[".dxf"])))
    qr = qparse.parse(q.question, fm.names())
    t = qr.terms[0]
    if t.kind == "area_apartment":
        rooms = [r for r in fm.rooms if r.unit == t.arg and r.number and not r.outdoor]
        key = "apt"
    elif t.kind == "area_total":
        rooms = [r for r in fm.rooms if r.number and not r.outdoor and not r.shaft]
        key = "total"
    else:
        continue
    pred = sum(r.area for r in rooms)
    gold = float(q.answer)
    tot[key] += 1
    if abs(pred - gold) <= 0.02 * gold:
        hit[key] += 1
        continue
    diff = pred - gold
    found = None
    for k in (1, 2, 3):
        for combo in itertools.combinations(rooms, k):
            if abs(sum(r.area for r in combo) - diff) <= 0.01 * gold:
                found = combo
                break
        if found:
            break
    if found:
        for r in found:
            dropped[r.name] += 1
            # features of the dropped room: inside a unit? printed area? number pattern? area size
            dropped_feat[(key, "unit" if r.unit else "no-unit", "printed" if r.printed_area else "-", r.number.split(".")[0] if r.number else "")] += 1
    else:
        unexplained.append((q.path[21:], key, round(gold, 2), round(pred, 2)))
print({k: f"{hit[k]}/{tot[k]} = {hit[k]/tot[k]:.1%}" for k in tot})
print("dropped room names:", dropped.most_common(20))
print("dropped feats:", dropped_feat.most_common(20))
print("unexplained:", len(unexplained), unexplained[:10])
