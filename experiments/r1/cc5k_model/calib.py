"""Calibrated confidence + prior gate for CC5K-model counts, fit on CC5K val drawings, checked on CC5K test.

For each template and predicted-count bucket b (0,1,2,...,>=B), on val:
  conf_model(b) = (hits + 1) / (n + 2)            P(gold == pred | bucket), Laplace-smoothed
  conf_prior(b) = P(gold == prior mode | bucket)
Answer = model count if conf_model >= conf_prior else prior mode; confidence = the larger one.
Also reports ±1 interval coverage (for 'assumptions/missing' style answers) and ECE on test.

Run: $JUNCTION_VENV/bin/python -I calib.py [--tta] [--scale 1] [--json out.json]
"""
import argparse
import collections
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import count as C  # noqa: E402
from offline_preds import FROZEN  # noqa: E402

BUCKETS = {"windows": 16, "doors": 16, "wc_seats": 4, "sinks": 6}


def bucket(k, t):
    return min(k, BUCKETS[t])


def preds(segs, gold, t, mf, k):
    out = []
    for st, z in segs.items():
        if t in gold.get(st, {}):
            out.append((C.counts(z, t, mf, k), gold[st][t]))
    return out


def ece(pairs, bins=10):
    pairs = np.array(pairs, float)
    if not len(pairs):
        return float("nan")
    e = 0.0
    for i in range(bins):
        m = (pairs[:, 0] >= i / bins) & (pairs[:, 0] < (i + 1) / bins + (i == bins - 1))
        if m.any():
            e += m.mean() * abs(pairs[m, 0].mean() - pairs[m, 1].mean())
    return e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tta", action="store_true")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    gold = C.gold_table()
    prior = C.train_prior(gold)
    val = C.load(C.stems_of("val"), a.tta, a.scale)
    test = C.load(C.stems_of("test"), a.tta, a.scale)
    table = {}
    for t, (mf, k) in FROZEN.items():
        P = preds(val, gold, t, mf, k)
        hits, n, phit = collections.Counter(), collections.Counter(), collections.Counter()
        for p, g in P:
            b = bucket(p, t)
            n[b] += 1
            hits[b] += p == g
            phit[b] += g == prior[t]
        tab = {}
        for b in range(BUCKETS[t] + 1):
            cm = (hits[b] + 1) / (n[b] + 2)
            cp = (phit[b] + 1) / (n[b] + 2) if n[b] else 0.0
            tab[b] = {"n": n[b], "conf_model": round(cm, 3), "conf_prior": round(cp, 3), "use": "model" if cm >= cp else "prior"}
        table[t] = {"prior": prior[t], "min_frac": mf, "kernel": k, "buckets": tab}
        T = preds(test, gold, t, mf, k)
        raw = sum(p == g for p, g in T)
        gated, conf_pairs, cov1 = 0, [], 0
        for p, g in T:
            row = tab[bucket(p, t)]
            ans, cf = (p, row["conf_model"]) if row["use"] == "model" else (prior[t], row["conf_prior"])
            gated += ans == g
            conf_pairs.append((cf, ans == g))
            cov1 += abs(p - g) <= 1
        npr = sum(g == prior[t] for _, g in T)
        uses_prior = [b for b, r in tab.items() if r["use"] == "prior" and r["n"]]
        print(f"{t:9s} test n={len(T)}: prior {npr / len(T):.1%} | model {raw / len(T):.1%} | gated {gated / len(T):.1%}"
              f" | ±1 coverage {cov1 / len(T):.1%} | ECE {ece(conf_pairs):.3f} | prior used for buckets {uses_prior}")
    if a.json:
        json.dump(table, open(a.json, "w"), indent=1)
        print("wrote", a.json)


if __name__ == "__main__":
    main()
