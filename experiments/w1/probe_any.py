"""Probe the ifc solver with self-written questions (not from any split) and print value / unit / conf / trace tail.

Usage: python experiments/w1/probe.py [file_with_questions]  (one question per line; '#' lines = comments;
a line 'PATH <file>' switches the drawing/model)."""
import sys, time
import os
from stoa.solvers import get_solver

S = get_solver(os.environ.get("SOLVER", "ifc"))
D = "data/ifc_models/"
path = D + "bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf"
lines = open(sys.argv[1]).read().splitlines() if len(sys.argv) > 1 else []
for q in lines:
    q = q.strip()
    if not q or q.startswith("#"):
        continue
    if q.startswith("PATH "):
        path = D + q[5:].strip()
        print("==", path.rsplit("/", 1)[-1])
        continue
    t = time.time()
    try:
        a = S.solve(path, q)
        v = a.value if not isinstance(a.value, str) else a.value.replace("\n", " | ")[:160]
        print(f"[{a.confidence:.2f}] {v!s:>12} {a.unit or ''}  <- {q}")
        if a.missing:
            print("      missing:", "; ".join(a.missing)[:200])
        print("      trace:", " / ".join(str(x) for x in (a.trace or [])[-3:])[:260], f"({time.time() - t:.1f}s)")
    except Exception as e:
        print(f"[ERR] {type(e).__name__}: {e} <- {q}")
