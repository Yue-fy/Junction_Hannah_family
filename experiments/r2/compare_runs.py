"""Per-concept accuracy of several eval runs on the questions they share (owner: R2).

    $JUNCTION_VENV/bin/python experiments/r2/compare_runs.py RUN_A RUN_B [RUN_C ...] [--source cubicasa5k]

RUN = a run_id (prefix ok) or a predictions .jsonl path. Concepts pool a template with its translations
(stoa.data.concept_map) when available. Prints n, accuracy per run, and mean tokens/GPU-s/API calls per run.
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from stoa.eval.analyze import load, resolve  # noqa: E402


def concept_of(template: str) -> str:
    try:
        from stoa.data import concept_map

        return concept_map().get(template, template)
    except Exception:  # noqa: BLE001
        return template


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--source", default=None)
    a = ap.parse_args()
    runs = []
    for r in a.runs:
        p = Path(r) if r.endswith(".jsonl") else resolve(r)
        rows = {x["qid"]: x for x in load(p) if not a.source or x["source"] == a.source}
        runs.append((Path(p).stem[-40:], rows))
    common = set.intersection(*(set(r) for _, r in runs))
    print(f"{len(common)} shared questions")
    by = collections.defaultdict(list)
    for q in common:
        by[concept_of(runs[0][1][q]["template"])].append(q)
    hdr = "  ".join(f"{name[-22:]:>22}" for name, _ in runs)
    print(f"{'n':>4}  {hdr}  concept")
    tot = [0] * len(runs)
    for c, qs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        accs = []
        for i, (_, rows) in enumerate(runs):
            k = sum(bool(rows[q]["correct"]) for q in qs)
            tot[i] += k
            accs.append(f"{100 * k / len(qs):22.1f}")
        print(f"{len(qs):4d}  {'  '.join(accs)}  {c[:70]}")
    print(f"{len(common):4d}  " + "  ".join(f"{100 * t / max(1, len(common)):22.1f}" for t in tot) + "  ALL")
    for name, rows in runs:
        cs = [rows[q].get("cost") or {} for q in common]
        if cs and cs[0]:
            m = {k: statistics.fmean(c.get(k, 0) or 0 for c in cs) for k in
                 ("llm_tokens_in", "llm_tokens_out", "gpu_seconds", "api_calls")}
            print(f"cost {name[-30:]}: " + ", ".join(f"{k}={v:.3g}" for k, v in m.items()))


if __name__ == "__main__":
    main()
