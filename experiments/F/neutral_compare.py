"""Neutral-path probe report (F c226): per source x variant, accuracy, paired vs the dataset path, confident-wrong,
LLM calls / tokens / wall per question, and which solver answered. OPEN probe (dev drawings).

    python3 experiments/F/neutral_compare.py RUN.jsonl [--examples K] [--source S]
"""
from __future__ import annotations

import argparse
import collections
import json

VARIANTS = ("dataset", "twins_name", "twins_hash", "srcdir_lone", "lone_hash")


def _f(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--examples", type=int, default=0)
    ap.add_argument("--source")
    args = ap.parse_args()
    run = [json.loads(l) for l in open(args.run) if l.strip()]
    ctrl = {r["meta"]["base_qid"]: r for r in run if r["meta"]["wording"] == "dataset"}
    agg = collections.defaultdict(collections.Counter)
    solv = collections.defaultdict(collections.Counter)
    ex = collections.defaultdict(list)
    for r in run:
        m = r["meta"]
        if args.source and m["source"] != args.source:
            continue
        key = (m["kind"].split(":")[0], m["wording"])
        c0 = ctrl.get(m["base_qid"])
        a = agg[key]
        ok = bool(r["correct"]) and r["correct"] != "False"
        ok0 = c0 is not None and bool(c0["correct"]) and c0["correct"] != "False"
        conf = _f(r.get("confidence"))
        cost = r.get("cost") or {}
        a["n"] += 1
        a["ok"] += ok
        a["ctrl"] += ok0
        a["cw"] += (not ok) and conf >= 0.8
        a["won"] += ok and not ok0
        a["lost"] += ok0 and not ok
        a["calls"] += _f(cost.get("llm_calls"))
        a["tok"] += _f(cost.get("llm_tokens_in")) + _f(cost.get("llm_tokens_out"))
        a["wall"] += _f(r.get("latency_s"))
        a["conf"] += conf
        a["err"] += bool(r.get("error"))
        solv[key][str(r.get("solver"))] += 1
        if ok0 and not ok:
            ex[key].append(r)
    print(f"{'source/type':24s} {'variant':12s} {'n':>4s} {'acc%':>6s} {'ctrl%':>6s} {'won':>4s} {'lost':>4s} {'cw':>4s} "
          f"{'conf':>5s} {'calls':>5s} {'tok':>6s} {'wall':>5s}  top solvers")
    tot = collections.defaultdict(collections.Counter)
    for key in sorted(agg, key=lambda k: (k[0], VARIANTS.index(k[1]) if k[1] in VARIANTS else 9)):
        a = agg[key]
        n = a["n"]
        tot[key[1]].update(a)
        top = ", ".join(f"{s.replace('pipeline/', '')} {c}" for s, c in solv[key].most_common(3))
        print(f"{key[0]:24s} {key[1]:12s} {n:4d} {100*a['ok']/n:6.1f} {100*a['ctrl']/n:6.1f} {a['won']:4d} {a['lost']:4d} "
              f"{a['cw']:4d} {a['conf']/n:5.2f} {a['calls']/n:5.2f} {a['tok']/n:6.0f} {a['wall']/n:5.1f}  {top}")
        for r in ex[key][: args.examples]:
            print(f"      {r['question'][:80]!r} gold {r['gold']} pred {str(r['value'])[:40]} @{r.get('confidence')} "
                  f"{r.get('solver')}")
    print()
    for v in VARIANTS:
        a = tot.get(v)
        if not a:
            continue
        n = a["n"]
        print(f"{'TOTAL':24s} {v:12s} {n:4d} {100*a['ok']/n:6.1f} {100*a['ctrl']/n:6.1f} {a['won']:4d} {a['lost']:4d} "
              f"{a['cw']:4d} {a['conf']/n:5.2f} {a['calls']/n:5.2f} {a['tok']/n:6.0f} {a['wall']/n:5.1f}")


if __name__ == "__main__":
    main()
