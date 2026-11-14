"""Unseen-style raster plans with NO vector/IFC twin (what the hidden set's "different" drawings may look like).

Simulation: R2's swiss PNG-twin count questions (artifacts/R2/swiss_png_counts_dev.jsonl), with the pipeline's sibling
lookup patched to return nothing, so route() sees a bare raster image. Compares the pipeline with the LoRA routed
first for such images (lora=1) against lora=0 (raster, then the base VLM).

    python experiments/w4/offdomain.py [--limit 60] [--workers 3]
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
from pathlib import Path

import stoa.pipeline as pl
from stoa.eval.scoring import score
from stoa.solvers import get_solver

SPLIT = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")) / \
    "artifacts/R2/swiss_png_counts_dev.jsonl"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    rows = [json.loads(line) for line in open(SPLIT)][: a.limit]
    pl.siblings = lambda path: set()  # a bare raster plan: no PDF/DXF/IFC twin
    out = {}
    for lora in (1, 0):
        p = get_solver("pipeline", lora=lora)

        def one(r):
            ans = p.solve(r["path"], r["question"])
            ok = score(r.get("type", "count"), r["answer"], r.get("unit"), ans.value, ans.unit)
            return ok, ans.confidence, ans.solver

        with cf.ThreadPoolExecutor(a.workers) as ex:
            res = list(ex.map(one, rows))
        n = len(res)
        hi = [ok for ok, c, _ in res if c >= 0.8]
        solvers = {}
        for _, _, s in res:
            solvers[s] = solvers.get(s, 0) + 1
        out[lora] = res
        print(f"lora={lora}: acc {100 * sum(ok for ok, _, _ in res) / n:.1f}% (n={n}), conf>=0.8 on "
              f"{100 * len(hi) / n:.0f}% at {100 * sum(hi) / max(1, len(hi)):.0f}% right; solvers {solvers}")
    w = sum(1 for x, y in zip(out[1], out[0]) if x[0] and not y[0])
    lo = sum(1 for x, y in zip(out[1], out[0]) if y[0] and not x[0])
    print(f"paired: lora=1 wins {w}, loses {lo}")


if __name__ == "__main__":
    main()
