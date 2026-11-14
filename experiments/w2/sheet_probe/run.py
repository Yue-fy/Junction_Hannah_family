"""General (non-schedule) questions on opening_design sheets that have NO dataset questions: life-safety room tags,
egress table, title block, structural general notes. Gold read from the PDF text layer (field `verified`).
Usage: PYTHONPATH=. python experiments/w2/sheet_probe/run.py [solver] [file.jsonl ...]   (solver default: pipeline; 'schedule:text=0' passes options)"""
import json
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from stoa.solvers import get_solver

args = sys.argv[1:]
name = args.pop(0) if args and not args[0].endswith(".jsonl") else "pipeline"
files = args or sorted(str(p) for p in Path(__file__).parent.glob("*.jsonl"))
items = [json.loads(line) for f in files for line in open(f)]
name, _, opts = name.partition(":")  # e.g. schedule:text=0
solver = get_solver(name, **dict(kv.split("=") for kv in opts.split(",") if kv))


def norm(s):
    return re.sub(r"[\s'\"\-.,]", "", str(s).lower())


def right(it, v):
    g = it["gold"]
    if isinstance(g, str):
        return v is not None and norm(g) in norm(v)
    if isinstance(v, str):
        m = re.search(r"-?\d[\d,]*\.?\d*", v)
        v = float(m.group().replace(",", "")) if m else None
    if not isinstance(v, (int, float)):
        return False
    return abs(v - g) <= (0 if it["unit"] == "count" else 0.02 * abs(g))


def one(it):
    t = time.time()
    a = solver.solve(it["path"], it["question"])
    return right(it, a.value), it, a, time.time() - t


with ThreadPoolExecutor(4) as ex:
    res = list(ex.map(one, items))
by = defaultdict(lambda: [0, 0, 0])
for ok, it, a, dt in res:
    cw = (not ok) and a.value is not None and a.confidence >= 0.5
    b = by[it["kind"]]
    b[0] += 1; b[1] += ok; b[2] += cw
    print(("OK  " if ok else ("CW  " if cw else "xx  ")) + f"{it['question'][60:140]:80s} gold={it['gold']!s:12.12s} "
          f"got={a.value!s:40.40s} conf={a.confidence:.2f} ev={len(a.evidence)} {a.solver or ''} {dt:4.0f}s")
print("\nkind         n  right  conf-wrong(>=0.5)")
for k, (n, ok, cw) in sorted(by.items()):
    print(f"{k:<11} {n:3d} {ok:6d} {cw:6d}")
print(f"ALL         {len(res):3d} {sum(r[0] for r in res):6d} {sum(v[2] for v in by.values()):6d}")
