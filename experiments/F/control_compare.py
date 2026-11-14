"""Within-run paired comparison: each probe wording vs the dataset wording of the same base (rows with wording
'dataset', added by experiments/F/add_controls.py). OPEN probes only (prints kinds, not questions).

    python experiments/F/control_compare.py PROBE.jsonl RUN.jsonl [--examples K]
"""
from __future__ import annotations

import argparse
import collections
import json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("split")
    ap.add_argument("run")
    ap.add_argument("--examples", type=int, default=0, help="print K lost examples per wording")
    args = ap.parse_args()
    meta = {}
    for l in open(args.split):
        if l.strip():
            r = json.loads(l)
            meta[r["qid"]] = r["meta"]
    run = [json.loads(l) for l in open(args.run) if l.strip()]
    ctrl = {(meta[r["qid"]]["base_qid"], meta[r["qid"]]["probe_kind"]): r for r in run
            if meta.get(r["qid"], {}).get("wording") == "dataset"}
    agg = collections.defaultdict(collections.Counter)
    ex = collections.defaultdict(list)
    for r in run:
        m = meta.get(r["qid"])
        if not m or m["wording"] == "dataset":
            continue
        c0 = ctrl.get((m["base_qid"], m["probe_kind"]))
        if c0 is None:
            continue
        a = agg[m["kind"]]
        a["n"] += 1
        a["ctrl"] += bool(c0["correct"])
        a["w"] += bool(r["correct"])
        a["cw"] += (not r["correct"]) and (r.get("confidence") or 0) >= 0.8
        a["won"] += bool(r["correct"]) and not c0["correct"]
        a["lost"] += bool(c0["correct"]) and not r["correct"]
        if c0["correct"] and not r["correct"]:
            ex[m["kind"]].append(r)
    print(f"{'kind':40s} {'n':>4s} {'ctrl%':>6s} {'word%':>6s} {'cw':>4s} {'won':>4s} {'lost':>4s}")
    tot = collections.Counter()
    for k in sorted(agg, key=lambda k: (agg[k]["w"] - agg[k]["ctrl"]) / agg[k]["n"]):
        a = agg[k]
        tot.update(a)
        print(f"{k[:40]:40s} {a['n']:4d} {100*a['ctrl']/a['n']:6.1f} {100*a['w']/a['n']:6.1f} {a['cw']:4d} {a['won']:4d} {a['lost']:4d}")
        for r in ex[k][: args.examples]:
            print(f"      {r['question'][:90]!r} gold {r['gold']} pred {r['value']} @{r.get('confidence')} {r.get('solver')}")
    if tot["n"]:
        print(f"{'TOTAL':40s} {tot['n']:4d} {100*tot['ctrl']/tot['n']:6.1f} {100*tot['w']/tot['n']:6.1f} {tot['cw']:4d} {tot['won']:4d} {tot['lost']:4d}")


if __name__ == "__main__":
    main()
