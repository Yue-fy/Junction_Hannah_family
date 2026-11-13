"""Measure the dxf table-QA fallback on questions the rule parser does NOT cover, with gold derived only from
dataset answers (never from our own DXF tables):
  avg   "What is the average net floor area of the rooms labelled 'X'?"  = gold area(X) / gold count(X)
  which "Which apartment has the larger net floor area, A or B?"          = argmax of gold apartment areas
  yesno "Is there a room labelled 'X' on this floor?"                     = gold count(X) > 0
Dev drawings only. Run: PYTHONPATH=$PWD $JUNCTION_VENV/bin/python experiments/w2/fallback_eval.py [n_per_kind]
"""
import collections
import json
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from stoa.data import load_questions
from stoa.eval.splits import load_split
from stoa.solvers import get_solver
from stoa.solvers.vector import qparse

n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
dev_paths = {q.path for q in load_split("dev") if q.source == "swiss_dwellings"}
G = collections.defaultdict(lambda: {"cnt": {}, "area": {}, "apt": {}})
for q in load_questions():
    if q.path not in dev_paths:
        continue
    if m := re.match(r"How many rooms labelled '(.+)' are there", q.question):
        G[q.path]["cnt"][m.group(1)] = q.answer
    elif m := re.match(r"What is the total net area in m² of all rooms labelled '(.+)' on", q.question):
        G[q.path]["area"][m.group(1)] = q.answer
    elif m := re.match(r"What is the net floor area of apartment (\w) in m²", q.question):
        G[q.path]["apt"][m.group(1)] = q.answer
rng = random.Random(0)
items = []
paths = sorted(G)
rng.shuffle(paths)
for p in paths:
    g = G[p]
    both = [x for x in g["cnt"] if x in g["area"] and g["cnt"][x] > 0]
    if both and sum(1 for i in items if i[0] == "avg") < n:
        x = both[0]
        items.append(("avg", p, f"What is the average net floor area of the rooms labelled '{x}' on this floor?",
                      g["area"][x] / g["cnt"][x]))
    if "A" in g["apt"] and "B" in g["apt"] and sum(1 for i in items if i[0] == "which") < n:
        items.append(("which", p, "Which apartment has the larger net floor area, A or B?",
                      "A" if g["apt"]["A"] > g["apt"]["B"] else "B"))
    if g["cnt"] and sum(1 for i in items if i[0] == "yesno") < n:
        x = rng.choice(sorted(g["cnt"]))
        items.append(("yesno", p, f"Is there a room labelled '{x}' on this floor?", "yes" if g["cnt"][x] > 0 else "no"))
s = get_solver("dxf")


def run(it):
    kind, p, q, gold = it
    assert not qparse.covered(q, qparse.parse(q)), q
    a = s.solve(p, q)
    if kind == "avg":
        ok = isinstance(a.value, (int, float)) and abs(a.value - gold) <= 0.02 * gold
    else:
        ok = str(a.value).strip().lower() == gold.lower()
    return kind, ok, q, gold, a.value, len(a.evidence)


with ThreadPoolExecutor(8) as ex:
    res = list(ex.map(run, items))
acc = collections.Counter()
tot = collections.Counter()
for kind, ok, q, gold, v, ne in res:
    tot[kind] += 1
    acc[kind] += ok
    if not ok:
        print("MISS", kind, q, "gold", gold, "pred", v)
print({k: f"{acc[k]}/{tot[k]}" for k in tot}, "overall", f"{sum(acc.values())}/{sum(tot.values())}")
