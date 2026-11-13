"""Does a lower per-class probability threshold (P(class) >= tau instead of argmax) recover the thin windows
the argmax misses? Grid over tau, min_frac, kernel on CC5K VAL (p_*.npz from infer.py --probs); with
--report, apply the val-best setting to CC5K TEST.
Run: $JUNCTION_VENV/bin/python -I prob_thresh.py [--report]
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import count as C  # noqa: E402

CH = {"windows": "p1", "doors": "p2", "wc_seats": "p5", "sinks": "p6"}
TAUS = [None, 0.15, 0.25, 0.35, 0.45]
MF = [5e-5, 1e-4, 2e-4, 3e-4]
KS = [0, 3, 5]


def load(split):
    out = {}
    for st in C.stems_of(split):
        p = os.path.join(C.SEG, "p_" + st + ".npz")
        if os.path.exists(p):
            out[st] = dict(np.load(p))
    return out


def n_comp(z, t, tau, mf, k):
    m = (z["icons"] == C.CLS[t][0]) if tau is None else (z[CH[t]] >= int(tau * 255))
    H, W = m.shape
    return len(C.components(m, max(1, mf * H * W), k))


def acc(S, gold, t, cfg):
    r = [n_comp(z, t, *cfg) == gold[s][t] for s, z in S.items() if t in gold.get(s, {})]
    return sum(r) / max(len(r), 1), len(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    gold = C.gold_table()
    V = load("val")
    T = load("test") if a.report else {}
    print(f"val drawings with probs: {len(V)}; test: {len(T)}")
    for t in CH:
        base = max(((acc(V, gold, t, (None, mf, k))[0], (None, mf, k)) for mf in MF for k in KS))
        best = max(((acc(V, gold, t, (tau, mf, k))[0], (tau, mf, k)) for tau in TAUS[1:] for mf in MF for k in KS))
        line = f"{t:9s} val argmax {base[0]:.1%} {base[1]} | threshold {best[0]:.1%} {best[1]}"
        if T:
            line += f" || test argmax {acc(T, gold, t, base[1])[0]:.1%} vs threshold {acc(T, gold, t, best[1])[0]:.1%}"
        print(line)


if __name__ == "__main__":
    main()
