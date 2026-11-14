"""Is the raster second reader worth its cost as a CONFIDENCE signal for LoRA counts? (owner: R2)

S0 (03:56): the pipeline calls raster's VLM label reader on every cubicasa LoRA answer (~2 LLM calls, ~590 output
tokens per question; cubicasa $0.02 -> $0.4 per 1k) to set the confidence from LoRA/raster agreement. The LoRA's own
answer-digit probability p is free. This fits a per-concept p-bin calibration on train_gate (LoRA cc-v2 run; drawings
the LoRA never saw) and compares, on a dev pipeline run, the confidence the pipeline gave (agreement-based) with the
free p-based one and with the two combined (p-bin x agree).

    $JUNCTION_VENV/bin/python experiments/r2/conf_cost.py [--fit RUN] [--dev RUN]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from stoa.eval.analyze import load, resolve  # noqa: E402
from stoa.router.intent import parse  # noqa: E402

BINS = [0.5, 0.9, 0.99, 0.999]
P_RX = re.compile(r"p\(answer digits\) = ([0-9.]+)")
AGREE_RX = re.compile(r"cross-check: vlm_lora \S+ (=|≠) raster")


def pbin(p: float) -> int:
    return sum(p > b for b in BINS)


def signals(r: dict) -> tuple[float | None, bool | None]:
    p = agree = None
    for t in r.get("trace") or []:
        m = P_RX.search(t)
        if m:
            p = float(m.group(1))
        m = AGREE_RX.search(t)
        if m:
            agree = m.group(1) == "="
    return p, agree


def auroc(conf: list[float], ok: list[bool]) -> float:
    pos = [c for c, o in zip(conf, ok) if o]
    neg = [c for c, o in zip(conf, ok) if not o]
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def ece(conf: list[float], ok: list[bool], nb: int = 10) -> float:
    b = collections.defaultdict(list)
    for c, o in zip(conf, ok):
        b[min(int(c * nb), nb - 1)].append((c, o))
    return sum(abs(sum(c for c, _ in v) / len(v) - sum(o for _, o in v) / len(v)) * len(v) for v in b.values()) / len(conf)


def report(name: str, conf: list[float], ok: list[bool]) -> None:
    hi = [o for c, o in zip(conf, ok) if c >= 0.8]
    brier = sum((c - o) ** 2 for c, o in zip(conf, ok)) / len(ok)
    print(f"{name:44s} AUROC {auroc(conf, ok):.3f}  ECE {ece(conf, ok):.3f}  Brier {brier:.3f}  "
          f"conf>=0.8 on {100 * len(hi) / len(ok):4.1f}% at {100 * sum(hi) / max(len(hi), 1):5.1f}% right")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", default="20261114-012403-vlm_direct-train_gate-ee1b")  # cc-v2 on train_gate cubicasa
    ap.add_argument("--dev", default="20261114-031320-pipeline-dev-bb98")  # pipeline dev with the raster cross-check
    x = ap.parse_args()

    tab: dict = collections.defaultdict(lambda: [0, 0])  # (concept, bin) -> [right, n]
    glob_: dict = collections.defaultdict(lambda: [0, 0])
    for r in load(resolve(x.fit)):
        p, _ = signals(r)
        if p is None or r.get("correct") is None:
            continue
        k = (parse(r["question"]).target, pbin(p))
        tab[k][0] += bool(r["correct"]); tab[k][1] += 1
        glob_[pbin(p)][0] += bool(r["correct"]); glob_[pbin(p)][1] += 1

    def conf_p(concept: str, p: float) -> float:
        k, n = tab.get((concept, pbin(p)), [0, 0])
        g, gn = glob_.get(pbin(p), [0, 0])
        prior = (g + 1) / (gn + 2)
        return (k + 4 * prior) / (n + 4)  # shrink small cells toward the bin's global rate

    rows = [r for r in load(resolve(x.dev)) if r.get("solver", "").endswith("vlm_lora") and r.get("correct") is not None]
    have = [(r, *signals(r)) for r in rows]
    have = [(r, p, a) for r, p, a in have if p is not None]
    ok = [bool(r["correct"]) for r, _, _ in have]
    print(f"dev LoRA answers with p: {len(have)} (accuracy {100 * sum(ok) / len(ok):.1f}%), with a raster cross-check: "
          f"{sum(a is not None for _, _, a in have)}")
    report("pipeline today (train hit rate x agreement)", [r["confidence"] for r, _, _ in have], ok)
    cp = [conf_p(parse(r["question"]).target, p) for r, p, _ in have]
    report("free: per-concept p-bin (fit train_gate)", cp, ok)
    # combined, fitted on dev halves would be leaky; show the agree/disagree split of the free confidence instead
    for flag in (True, False):
        sub = [(c, o) for c, o, (_, _, a) in zip(cp, ok, have) if a is flag]
        if sub:
            print(f"   raster {'agrees   ' if flag else 'disagrees'}: n {len(sub):3d}, mean free conf {sum(c for c, _ in sub) / len(sub):.2f}, "
                  f"right {100 * sum(o for _, o in sub) / len(sub):.1f}%")
    by = collections.defaultdict(list)
    for (r, p, a), o, c in zip(have, ok, cp):
        by[parse(r["question"]).target].append((r["confidence"], c, o))
    print(f"{'concept':12s} {'n':>4s} {'acc':>5s} {'AUROC today':>12s} {'AUROC free':>11s}")
    for k, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
        print(f"{str(k):12s} {len(v):4d} {100 * sum(o for *_, o in v) / len(v):5.1f} "
              f"{auroc([a for a, _, _ in v], [o for *_, o in v]):12.3f} {auroc([b for _, b, _ in v], [o for *_, o in v]):11.3f}")


if __name__ == "__main__":
    main()
