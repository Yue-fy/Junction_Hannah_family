"""One question through the pipeline with its full trace (W4 debugging aid).

    python experiments/w4/ask.py <dataset-relative path> "<question>" [key=value solver args ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stoa.contract import CostMeter  # noqa: E402
from stoa.solvers import get_solver  # noqa: E402

if __name__ == "__main__":
    path, q, *kv = sys.argv[1:]
    s = get_solver("pipeline", **dict(x.split("=", 1) for x in kv))
    with CostMeter() as m:
        a = s.solve(path, q)
    print(f"ANSWER {a.value!r} {a.unit} conf {a.confidence} solver {a.solver}")
    for t in a.trace:
        print("  ", str(t)[:300])
    print("assumptions", a.assumptions)
    print("missing", a.missing)
    print("evidence", [(e.file[-40:], e.page, e.bbox, getattr(e, "ifc_guid", None), e.note[:60]) for e in a.evidence[:5]])
    print("cost", m.cost)
