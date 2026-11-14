"""Same probes through the whole pipeline (end-to-end effect). Usage: PYTHONPATH=. python ... probe1.jsonl probe2.jsonl"""
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from experiments.w2.op_probe.run import right
from stoa.solvers import get_solver

rows = [json.loads(l) for f in sys.argv[1:] for l in open(f)]
s = get_solver("pipeline")
with ThreadPoolExecutor(4) as ex:
    answers = list(ex.map(lambda r: s.solve(r["path"], r["question"]), rows))
by = defaultdict(lambda: [0, 0, 0])
for r, a in zip(rows, answers):
    ok = right(r["gold"], r["unit"], a)
    cw = (not ok) and a.value is not None and a.confidence >= 0.5
    b = by[r["kind"].split("-")[0]]
    b[0] += 1; b[1] += ok; b[2] += cw
    print(f"{'OK ' if ok else ('CW ' if cw else 'xx ')} {a.value!s:>18.18} {a.unit!s:>5} {a.confidence:4.2f} {a.solver:<22.22} | gold {r['gold']!s:>8.8} | {r['question'][:70]}")
print("\nkind            n  right  conf-wrong(>=0.5)")
for k, (n, ok, cw) in sorted(by.items()):
    print(f"{k:<14} {n:3d} {ok:6d} {cw:6d}")
print(f"{'ALL':<14} {sum(v[0] for v in by.values()):3d} {sum(v[1] for v in by.values()):6d} {sum(v[2] for v in by.values()):6d}")
