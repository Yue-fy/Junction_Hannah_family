"""Run probe files (experiments/w1/probes/*.txt) through the ifc solver and write one JSON line per question
(value, unit, confidence, missing) to stdout. Used to compare two commits on self-written wordings."""
import json
import sys

from stoa.solvers.ifc.solver import IfcSolver

S = IfcSolver()
D = "data/ifc_models/"
for fn in sys.argv[1:]:
    path = D + "bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf"
    for q in open(fn).read().splitlines():
        q = q.strip()
        if not q or q.startswith("#"):
            continue
        if q.startswith("PATH "):
            path = D + q[5:].strip()
            continue
        try:
            a = S.solve(path, q)
            out = dict(file=fn.rsplit("/", 1)[-1], path=path, q=q, value=a.value, unit=a.unit,
                       conf=round(a.confidence, 3), missing=a.missing[:2])
        except Exception as e:  # noqa: BLE001
            out = dict(file=fn, path=path, q=q, error=f"{type(e).__name__}: {e}")
        print(json.dumps(out, ensure_ascii=False, default=str))
