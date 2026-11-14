"""LoRA-only 90% count range (R2, 11:2x day-team item): residual quantiles of the cc-v2 counting LoRA, fitted on
train_gate (never dev/test), checked for coverage on dev. Used when the pipeline's CubiCasa5K detector cross-check
did not run (that path already has R1's interval). Changes no value or confidence; it fills Answer.missing.

    python experiments/r2/interval/lora_interval.py FIT.jsonl CHECK.jsonl [--max-conf 0.8] [--json OUT]
"""
import argparse
import json
import math

BINS = [(0, 0), (1, 2), (3, 5), (6, 10), (11, 10**6)]


def rows(path, max_conf):
    out = []
    for line in open(path):
        r = json.loads(line)
        if r.get("source") != "cubicasa5k" or r.get("type") != "count" or r.get("value") is None:
            continue
        if r.get("gold") is None or not isinstance(r["value"], (int, float)) or r["confidence"] >= max_conf:
            continue
        out.append((int(r["value"]), int(r["gold"]), float(r["confidence"])))
    return out


def bin_of(v):
    return next(i for i, (lo, hi) in enumerate(BINS) if lo <= v <= hi)


def q(xs, p):
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, math.ceil(p * len(xs)) - 1)) if p > 0 else 0
    return xs[k]


def fit(data, lo_p=0.05, hi_p=0.95, min_n=15):
    table = {}
    for i in range(len(BINS)):
        res = [g - v for v, g, _ in data if bin_of(v) == i]
        j = i
        while len(res) < min_n and j > 0:  # borrow from the neighbour below, scaled by the bin's own size
            j -= 1
            res += [g - v for v, g, _ in data if bin_of(v) == j]
        table[i] = (q(res, lo_p), q(res, hi_p), len(res)) if res else (0, 0, 0)
    return table


def interval(table, v):
    lo, hi, _ = table[bin_of(v)]
    return max(0, v + lo), v + hi


def check(table, data):
    cov = [interval(table, v)[0] <= g <= interval(table, v)[1] for v, g, _ in data]
    width = [interval(table, v)[1] - interval(table, v)[0] for v, g, _ in data]
    point = sum(lo == hi for lo, hi in (interval(table, v) for v, _, _ in data))
    return sum(cov) / max(1, len(cov)), sum(width) / max(1, len(width)), point, len(cov)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("fit")
    ap.add_argument("check")
    ap.add_argument("--max-conf", type=float, default=0.8)
    ap.add_argument("--json")
    a = ap.parse_args()
    tr, dv = rows(a.fit, a.max_conf), rows(a.check, a.max_conf)
    t = fit(tr)
    print(f"fit rows {len(tr)} (conf < {a.max_conf}); check rows {len(dv)}")
    for i, (lo, hi) in enumerate(BINS):
        print(f"  pred {lo}-{hi if hi < 10**6 else '∞'}: residual 90% [{t[i][0]:+d}, {t[i][1]:+d}] (n={t[i][2]})")
    for name, d in (("fit", tr), ("check", dv)):
        c, w, p, n = check(t, d)
        print(f"{name}: coverage {c:.1%}  mean width {w:.2f}  point intervals {p}/{n}")
    if a.json:
        json.dump({"bins": BINS, "table": {str(k): v for k, v in t.items()}, "fit": a.fit, "max_conf": a.max_conf},
                  open(a.json, "w"), indent=1)
