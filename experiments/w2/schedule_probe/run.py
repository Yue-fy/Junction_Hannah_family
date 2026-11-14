"""Self-written, hand-verified questions on opening_design sheets that have NO dataset questions (a held-out check for
the schedule solver's table rebuilding). Gold values were read from the PDF text rows and checked against the sheet's
printed totals. Usage: PYTHONPATH=. python experiments/w2/schedule_probe/run.py [file.jsonl ...]"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from stoa.solvers.vector.schedule_solver import ScheduleSolver

files = sys.argv[1:] or sorted(str(p) for p in Path(__file__).parent.glob("*.jsonl"))
items = [json.loads(line) for f in files for line in open(f)]
solver = ScheduleSolver()


def one(it):
    a = solver.solve(it["path"], it["question"])
    g, v = it["gold"], a.value
    if isinstance(g, str):
        ok = isinstance(v, str) and g.lower().replace(" ", "") in v.lower().replace(" ", "")
    else:
        ok = isinstance(v, (int, float)) and abs(v - g) <= (0 if it["unit"] == "count" else 0.02 * abs(g))
    return ok, it, a


with ThreadPoolExecutor(4) as ex:
    res = list(ex.map(one, items))
for ok, it, a in res:
    print(("OK  " if ok else "BAD ") + f"{it['question'][:70]:70s} gold={it['gold']!s:28.28s} got={a.value!s:34.34s} "
          f"conf={a.confidence:.2f} ev={len(a.evidence)}")
print(f"{sum(r[0] for r in res)}/{len(res)} right")
