"""Is a gain real? Paired comparison of two eval runs, plus calibration for one run.

Usage (stdlib only; any python3):
  python3 experiments/r1/stats/compare.py RUN_A [RUN_B] [--by bucket|template|source] [--min-n 20]

RUN_* is a predictions file written by `python -m stoa.eval` ($JUNCTION_SHARED/artifacts/eval/<run_id>.jsonl),
or just the run_id. Only scored types (count/area/length/volume) are compared.

One run:  accuracy with a 95% CI that resamples whole drawings (cluster bootstrap by `path`), plus a
          risk–coverage table and ECE from the `confidence` field.
Two runs: on the questions both runs answered (joined by qid), per group: accuracy A/B, delta with a
          cluster-bootstrap 95% CI, and an exact McNemar p-value on the discordant pairs.

Why cluster by drawing: every cubicasa question is asked in English AND Finnish on the same image with
the same answer, and several questions share one drawing. Treating them as independent makes CIs too
narrow and McNemar p-values too small (duplicates double b and c). The bootstrap resamples drawings.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import random
import sys

SCORED = {"count", "area", "length", "volume"}
SHARED = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")


def load(arg: str) -> dict[str, dict]:
    path = arg if os.path.exists(arg) else os.path.join(SHARED, "artifacts", "eval", arg.removesuffix(".jsonl") + ".jsonl")
    rows = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("type") in SCORED:
                rows[r["qid"]] = r
    return rows


def group_key(r: dict, by: str) -> str:
    if by == "template":
        return f"{r['source']}/{r.get('template', '?')}"[:90]
    if by == "source":
        return r["source"]
    return f"{r['source']}/{r['type']}"


def binom_two_sided(b: int, c: int) -> float:
    """Exact McNemar: two-sided binomial test of b vs c with p = 0.5."""
    n, k = b + c, min(b, c)
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def cluster_boot(rows: list[tuple[str, float]], n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    """95% CI of the mean of per-question values, resampling clusters (drawings)."""
    by = collections.defaultdict(list)
    for cl, v in rows:
        by[cl].append(v)
    clusters = list(by.values())
    if len(clusters) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    stats = []
    for _ in range(n_boot):
        s = n = 0
        for _ in range(len(clusters)):
            c = clusters[rng.randrange(len(clusters))]
            s += sum(c)
            n += len(c)
        stats.append(s / n)
    stats.sort()
    return stats[int(0.025 * n_boot)], stats[int(0.975 * n_boot) - 1]


def one_run(A: dict, by: str, min_n: int) -> None:
    groups = collections.defaultdict(list)
    for r in A.values():
        groups[group_key(r, by)].append(r)
    groups["ALL"] = list(A.values())
    print(f"{'group':60s} {'n':>6s} {'drawings':>8s} {'acc':>6s}  95% CI (cluster)")
    for g, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(rs) < min_n:
            continue
        acc = sum(bool(r["correct"]) for r in rs) / len(rs)
        lo, hi = cluster_boot([(r["path"], float(bool(r["correct"]))) for r in rs])
        print(f"{g:60s} {len(rs):6d} {len({r['path'] for r in rs}):8d} {acc:6.1%}  [{lo:.1%}, {hi:.1%}]")

    rs = [r for r in A.values() if not r.get("abstained") and r.get("confidence") is not None]
    if not rs:
        return
    rs.sort(key=lambda r: -float(r["confidence"]))
    print("\nrisk–coverage (answered questions sorted by confidence):")
    print(f"{'coverage':>9s} {'accuracy':>9s} {'min conf':>9s}")
    for cov in (0.1, 0.25, 0.5, 0.75, 0.9, 1.0):
        k = max(1, int(round(cov * len(rs))))
        acc = sum(bool(r["correct"]) for r in rs[:k]) / k
        print(f"{cov:9.0%} {acc:9.1%} {float(rs[k - 1]['confidence']):9.3f}")
    # area under the risk–coverage curve (lower is better) and expected calibration error
    risk, wrong = 0.0, 0
    for i, r in enumerate(rs, 1):
        wrong += not r["correct"]
        risk += wrong / i
    bins = collections.defaultdict(list)
    for r in rs:
        bins[min(9, int(float(r["confidence"]) * 10))].append(r)
    ece = sum(len(b) / len(rs) * abs(sum(bool(r["correct"]) for r in b) / len(b) -
                                       sum(float(r["confidence"]) for r in b) / len(b)) for b in bins.values())
    print(f"AURC = {risk / len(rs):.3f}   ECE (10 bins) = {ece:.3f}   n answered = {len(rs)}")


def two_runs(A: dict, B: dict, by: str, min_n: int) -> None:
    common = sorted(set(A) & set(B))
    print(f"joined on qid: {len(common)} common scored questions (A has {len(A)}, B has {len(B)})")
    groups = collections.defaultdict(list)
    for q in common:
        groups[group_key(A[q], by)].append(q)
    groups["ALL"] = common
    print(f"{'group':60s} {'n':>6s} {'acc A':>6s} {'acc B':>6s} {'B−A':>6s}  95% CI (cluster)   b(A✓B✗) c(A✗B✓)  McNemar p")
    for g, qs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(qs) < min_n:
            continue
        a = [bool(A[q]["correct"]) for q in qs]
        b_ = [bool(B[q]["correct"]) for q in qs]
        b = sum(x and not y for x, y in zip(a, b_))
        c = sum(y and not x for x, y in zip(a, b_))
        d = [(A[q]["path"], float(y) - float(x)) for q, x, y in zip(qs, a, b_)]
        lo, hi = cluster_boot(d)
        acc_a, acc_b = sum(a) / len(a), sum(b_) / len(b_)
        flag = "  *" if (lo > 0 or hi < 0) else ""
        print(f"{g:60s} {len(qs):6d} {acc_a:6.1%} {acc_b:6.1%} {acc_b - acc_a:+6.1%}  [{lo:+.1%}, {hi:+.1%}]"
              f"  {b:7d} {c:7d}  {binom_two_sided(b, c):9.3g}{flag}")
    print("\n* = cluster-bootstrap CI excludes 0. McNemar p treats questions as independent: with EN/FI "
          "duplicates it is too optimistic, so trust the cluster CI.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--by", default="bucket", choices=["bucket", "template", "source"])
    ap.add_argument("--min-n", type=int, default=20)
    a = ap.parse_args(argv)
    A = load(a.runs[0])
    if len(a.runs) == 1:
        one_run(A, a.by, a.min_n)
    else:
        two_runs(A, load(a.runs[1]), a.by, a.min_n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
