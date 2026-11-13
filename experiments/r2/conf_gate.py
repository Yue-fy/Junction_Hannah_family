"""Confidence gate: use the VLM's answer when its answer-digit probability p >= T, else the prior (owner: R2).

    $JUNCTION_VENV/bin/python experiments/r2/conf_gate.py VLM_RUN PRIOR_RUN [--source cubicasa5k] [--fit-on OTHER]

Per concept (template + translations): n, prior acc, VLM acc, gated acc for several T, and the best T.
VLM_RUN must be vlm_direct with conf=raw or conf=logprob (p is read from the trace). Fit T on TRAIN runs only.
"""

from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.r2.compare_runs import concept_of  # noqa: E402
from experiments.r2.escalate import _rows  # noqa: E402

TS = (0.5, 0.9, 0.99, 0.999, 0.9999, 1.01)  # 1.01 = never use the VLM


def p_of(r: dict) -> float:
    m = re.search(r"p\(answer digits\) = ([0-9.]+)", " ".join(r.get("trace") or []))
    return float(m.group(1)) if m else -1.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("vlm")
    ap.add_argument("prior")
    ap.add_argument("--source")
    a = ap.parse_args()
    v = {r["qid"]: r for r in _rows(a.vlm) if not a.source or r["source"] == a.source}
    pr = {r["qid"]: r for r in _rows(a.prior)}
    by = collections.defaultdict(list)
    for q, r in v.items():
        if q in pr and r.get("correct") is not None:
            by[concept_of(r["template"])].append((p_of(r), bool(r["correct"]), bool(pr[q]["correct"])))
    print(f"{'n':>4} {'prior':>6} {'vlm':>6} " + " ".join(f"p>={t:<6}" for t in TS[:-1]) + "  best  concept")
    tot = collections.Counter()
    for c, xs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        n = len(xs)
        accs = [sum((vc if p >= t else pc) for p, vc, pc in xs) / n for t in TS]
        best = max(range(len(TS)), key=lambda i: (accs[i], TS[i]))  # ties -> higher T (prefer the prior: free)
        tot["n"] += n
        tot["prior"] += accs[-1] * n
        tot["vlm"] += sum(vc for _, vc, _ in xs)
        tot["best"] += accs[best] * n
        for i, t in enumerate(TS):
            tot[t] += accs[i] * n
        print(f"{n:4d} {accs[-1] * 100:6.1f} {sum(vc for _, vc, _ in xs) / n * 100:6.1f} "
              + " ".join(f"{x * 100:8.1f}" for x in accs[:-1])
              + f"  {('prior' if TS[best] > 1 else TS[best])!s:>6}  {c[:60]}")
    n = tot["n"]
    print(f"{n:4d} {tot['prior'] / n * 100:6.1f} {tot['vlm'] / n * 100:6.1f} "
          + " ".join(f"{tot[t] / n * 100:8.1f}" for t in TS[:-1]) + f"  per-concept best {tot['best'] / n * 100:.1f}  ALL")


if __name__ == "__main__":
    main()
