"""dxf apartment areas vs UNLABELED numbered rooms (F c227). For each Swiss "net floor area of apartment X" question:
is the dxf sum right (within 2%), and does dropping its unlabeled rooms >= 4 m2 make it right?

    PYTHONPATH=. $JUNCTION_VENV/bin/python experiments/F/unlabeled_rooms.py train 1500
c227 result: train 1497 Qs: with an unlabeled room >= 4 m2 dxf is right 34/50 (dropping it: 11/50); otherwise 1407/1447.
"""
import json, re, random, sys, concurrent.futures as cf
from stoa.eval.splits import load_split
from stoa.solvers import get_solver
split = sys.argv[1]; N = int(sys.argv[2])
qs = [q for q in load_split(split) if q.source == "swiss_dwellings" and q.path.endswith(".pdf")
      and re.match(r"^What is the net floor area of apartment [A-Z] in m², summing all its rooms except", q.question)]
random.Random(1).shuffle(qs); qs = qs[:N]
s = get_solver("dxf")
def one(q):
    try:
        a = s.solve(q.path, q.question)
    except Exception as e:
        return None
    rooms = []
    for e in a.evidence:
        m = re.match(r"room (\S+)(?: '([^']*)')?: ([\d.]+) m²", e.note or "")
        if m: rooms.append((m.group(1), m.group(2), float(m.group(3))))
    return q, a.value, a.confidence, rooms
out = []
with cf.ThreadPoolExecutor(8) as ex:
    for r in ex.map(one, qs):
        if r: out.append(r)
def ok(v, g): return v is not None and abs(v - g) <= 0.02 * abs(g)
import collections
c = collections.Counter()
for q, v, conf, rooms in out:
    g = float(q.answer)
    unl = [x for x in rooms if not x[1]]
    big = [x for x in unl if x[2] >= 4]
    has = "unlab>=4" if big else "no_unlab>=4"
    cur = ok(v, g)
    alt = ok((v or 0) - sum(x[2] for x in big), g) if big else None
    c[(has, "cur_ok" if cur else "cur_wrong", "alt_ok" if alt else ("alt_wrong" if big else "-"))] += 1
for k, n in sorted(c.items()): print(k, n)
print("n", len(out))
