"""Per-kind paired comparison of two eval runs on a probe split whose rows carry meta.kind.

Usage: python experiments/F/kind_compare.py SPLIT.jsonl RUN_A.jsonl RUN_B.jsonl [--source S] [--min-n N]

Prints, per meta.kind: n, accuracy A / B, confident-wrong (conf >= 0.8) A / B, won / lost (B vs A).
Only for OPEN probe splits (it prints kinds, not questions).
"""
from __future__ import annotations

import argparse
import collections
import json


def load(path):
    return [json.loads(l) for l in open(path) if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("split")
    ap.add_argument("run_a")
    ap.add_argument("run_b")
    ap.add_argument("--source", default=None)
    ap.add_argument("--min-n", type=int, default=1)
    ap.add_argument("--level", choices=["kind", "probe_kind"], default="kind")
    args = ap.parse_args()

    meta = {r["qid"]: r.get("meta", {}) for r in load(args.split)}
    a = {r["qid"]: r for r in load(args.run_a)}
    b = {r["qid"]: r for r in load(args.run_b)}
    agg = collections.defaultdict(lambda: collections.Counter())
    for qid, rb in b.items():
        ra = a.get(qid)
        if ra is None or rb.get("gold") is None:
            continue
        if args.source and not rb.get("source", "").startswith(args.source):
            continue
        k = meta.get(qid, {}).get(args.level, "?")
        c = agg[k]
        c["n"] += 1
        c["a"] += bool(ra["correct"])
        c["b"] += bool(rb["correct"])
        c["cwa"] += (not ra["correct"]) and (ra.get("confidence") or 0) >= 0.8
        c["cwb"] += (not rb["correct"]) and (rb.get("confidence") or 0) >= 0.8
        c["won"] += (not ra["correct"]) and bool(rb["correct"])
        c["lost"] += bool(ra["correct"]) and (not rb["correct"])
    tot = collections.Counter()
    print(f"{'kind':48s} {'n':>4s} {'accA':>6s} {'accB':>6s} {'cwA':>4s} {'cwB':>4s} {'won':>4s} {'lost':>4s}")
    for k in sorted(agg, key=lambda k: (-(agg[k]["b"] / agg[k]["n"] - agg[k]["a"] / agg[k]["n"]), k)):
        c = agg[k]
        tot.update(c)
        if c["n"] < args.min_n:
            continue
        print(f"{k[:48]:48s} {c['n']:4d} {100*c['a']/c['n']:6.1f} {100*c['b']/c['n']:6.1f} {c['cwa']:4d} {c['cwb']:4d} {c['won']:4d} {c['lost']:4d}")
    if tot["n"]:
        print(f"{'TOTAL':48s} {tot['n']:4d} {100*tot['a']/tot['n']:6.1f} {100*tot['b']/tot['n']:6.1f} {tot['cwa']:4d} {tot['cwb']:4d} {tot['won']:4d} {tot['lost']:4d}")


if __name__ == "__main__":
    main()
