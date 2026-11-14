"""Two independent answerers as a cross-check: how often they agree, and how right they are when they do (owner: R2).

    $JUNCTION_VENV/bin/python experiments/r2/agree.py RUN_A RUN_B [--source cubicasa5k] [--by concept|none]

RUN = a run_id (prefix ok) or a predictions .jsonl path. Values agree when equal (numbers: within 2% relative, the
scoring tolerance; counts: exact). Prints per concept: n, agree share, accuracy of A when they agree, of A and of B
when they disagree, and "either right" (an upper bound for any picker). Use it to decide whether a second model is
worth calling as a confidence signal (high agree-accuracy, low disagree-accuracy) or as a replacement.
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.r2.compare_runs import concept_of  # noqa: E402
from stoa.eval.analyze import load, resolve  # noqa: E402


def same(a, b, typ: str | None) -> bool:
    if a is None or b is None:
        return False
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return str(a).strip().lower() == str(b).strip().lower()
    if typ == "count":
        return round(fa) == round(fb)
    return abs(fa - fb) <= 0.02 * max(abs(fa), abs(fb), 1e-9)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--source")
    ap.add_argument("--by", default="concept", choices=["concept", "none"])
    x = ap.parse_args()
    A = {r["qid"]: r for r in load(resolve(x.a))}
    B = {r["qid"]: r for r in load(resolve(x.b))}
    qs = [q for q in A if q in B and (not x.source or A[q].get("source") == x.source)
          and A[q].get("correct") is not None and B[q].get("correct") is not None]
    groups: dict[str, list[str]] = collections.defaultdict(list)
    for q in qs:
        key = concept_of(A[q].get("template") or A[q]["question"]) if x.by == "concept" else "all"
        groups[key].append(q)
        if x.by == "concept":
            groups["ALL"].append(q)

    def pct(k: int, n: int) -> str:
        return f"{100 * k / n:5.0f}" if n else "    -"

    print(f"A = {x.a}\nB = {x.b}\nshared scored questions: {len(qs)}")
    print(f"{'concept':40s} {'n':>4s} {'accA':>5s} {'accB':>5s} {'agree':>6s} {'A|agr':>6s} {'n_dis':>5s} "
          f"{'A|dis':>6s} {'B|dis':>6s} {'either':>6s}")
    for key in sorted(groups, key=lambda k: (k != "ALL", -len(groups[k]))):
        g = groups[key]
        agr = [q for q in g if same(A[q].get("value"), B[q].get("value"), A[q].get("type"))]
        dis = [q for q in g if q not in set(agr)]
        print(f"{key[:40]:40s} {len(g):4d} {pct(sum(A[q]['correct'] for q in g), len(g))} "
              f"{pct(sum(B[q]['correct'] for q in g), len(g))} {pct(len(agr), len(g)):>6s} "
              f"{pct(sum(A[q]['correct'] for q in agr), len(agr)):>6s} {len(dis):5d} "
              f"{pct(sum(A[q]['correct'] for q in dis), len(dis)):>6s} "
              f"{pct(sum(B[q]['correct'] for q in dis), len(dis)):>6s} "
              f"{pct(sum(A[q]['correct'] or B[q]['correct'] for q in g), len(g)):>6s}")


if __name__ == "__main__":
    main()
