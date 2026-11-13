"""Does the solver know what it doesn't know? Calibration of Answer.confidence on scored questions.

Stoa (13 Nov): "you know what you don't know, but refusing is not useful". So every answer carries a
confidence, and we measure how much it can be trusted:

- ece:     expected calibration error, 10 equal-width bins (0 = confidence matches accuracy exactly)
- brier:   mean (confidence - correct)^2 (lower is better; 0.25 = always saying 0.5)
- auroc:   P(conf of a right answer > conf of a wrong one) (0.5 = confidence is noise, 1 = perfect ranking)
- aurc:    area under the risk-coverage curve, answering the most confident first (lower is better)
- hi_conf: share of answers with confidence >= 0.8 and their accuracy (what a user sees as "sure")
- bins:    accuracy / mean confidence / n per bin, for a reliability diagram

Abstentions (value None) count as wrong with their stated confidence. Rows without a numeric confidence
are skipped (reported as `n_missing_conf`).

    python -m stoa.eval.calibration RUN [RUN ...]      # compare runs (ids or predictions files)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from stoa.eval.splits import shared_root

SCORED_TYPES = ("count", "area", "length", "volume")  # = stoa.eval.runner.SCORED_TYPES (no import cycle)

HI = 0.8


def calibration(rows: list[dict], n_bins: int = 10) -> dict | None:
    pts = []
    missing = 0
    for r in rows:
        if r.get("type") not in SCORED_TYPES or r.get("correct") is None:
            continue
        c = r.get("confidence")
        if not isinstance(c, (int, float)):
            missing += 1
            continue
        pts.append((min(1.0, max(0.0, float(c))), 1.0 if r["correct"] else 0.0))
    if not pts:
        return None
    n = len(pts)
    bins = []
    ece = 0.0
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        sel = [(c, y) for c, y in pts if (lo <= c < hi) or (b == n_bins - 1 and c == 1.0)]
        if not sel:
            continue
        acc = sum(y for _, y in sel) / len(sel)
        conf = sum(c for c, _ in sel) / len(sel)
        ece += len(sel) / n * abs(acc - conf)
        bins.append({"lo": lo, "hi": hi, "n": len(sel), "acc": round(acc, 4), "conf": round(conf, 4)})
    brier = sum((c - y) ** 2 for c, y in pts) / n
    # AUROC by ranks (ties get the average rank)
    order = sorted(range(n), key=lambda i: pts[i][0])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and pts[order[j + 1]][0] == pts[order[i]][0]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    pos = [ranks[i] for i in range(n) if pts[i][1] == 1.0]
    n_pos, n_neg = len(pos), n - len(pos)
    auroc = (sum(pos) - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg) if n_pos and n_neg else None
    # risk-coverage: most confident first; ties broken pessimistically-neutral by keeping input order
    srt = sorted(pts, key=lambda p: -p[0])
    err = 0.0
    aurc = 0.0
    for k, (_, y) in enumerate(srt, 1):
        err += 1 - y
        aurc += err / k
    aurc /= n
    acc = sum(y for _, y in pts) / n
    # the best possible AURC for this accuracy (all right answers ranked first): makes runs comparable
    n_wrong = n - sum(y for _, y in pts)
    best = sum(max(0.0, k - (n - n_wrong)) / k for k in range(1, n + 1)) / n
    hi = [(c, y) for c, y in pts if c >= HI]
    return {
        "n": n, "n_missing_conf": missing, "accuracy": round(acc, 4),
        "mean_conf": round(sum(c for c, _ in pts) / n, 4),
        "ece": round(ece, 4), "brier": round(brier, 4),
        "auroc": round(auroc, 4) if auroc is not None else None,
        "aurc": round(aurc, 4), "e_aurc": round(aurc - best, 4),
        "hi_conf_share": round(len(hi) / n, 4),
        "hi_conf_acc": round(sum(y for _, y in hi) / len(hi), 4) if hi else None,
        "bins": bins,
    }


def _load(run: str) -> tuple[str, list[dict]]:
    p = Path(run)
    if not p.exists():
        p = shared_root() / "artifacts" / "eval" / (run if run.endswith(".jsonl") else f"{run}.jsonl")
    rows = [json.loads(line) for line in open(p, encoding="utf-8") if line.strip()]
    return p.stem, rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--by-source", action="store_true", help="one line per source too")
    a = ap.parse_args(argv)
    hdr = f"{'run':48s} {'scope':16s} {'n':>5s} {'acc':>6s} {'conf':>6s} {'ECE':>6s} {'Brier':>6s} {'AUROC':>6s} {'AURC':>6s} {'eAURC':>6s} {'conf>=.8':>9s} {'acc|.8':>7s}"
    print(hdr)

    def line(name, scope, c):
        if not c:
            print(f"{name:48s} {scope:16s}  (no confidences)")
            return
        f = lambda x: "   -  " if x is None else f"{x:6.3f}"  # noqa: E731
        print(f"{name:48s} {scope:16s} {c['n']:5d} {f(c['accuracy'])} {f(c['mean_conf'])} {f(c['ece'])} {f(c['brier'])} "
              f"{f(c['auroc'])} {f(c['aurc'])} {f(c['e_aurc'])} {100 * c['hi_conf_share']:8.1f}% {f(c['hi_conf_acc'])}")

    for run in a.runs:
        name, rows = _load(run)
        line(name, "all", calibration(rows))
        if a.by_source:
            for src in sorted({r["source"] for r in rows}):
                line("", src, calibration([r for r in rows if r["source"] == src]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
