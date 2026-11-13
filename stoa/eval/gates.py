"""Per-template gate table from two runs on the SAME questions (use `--split train_gate`, never dev; S0 D4).

    python -m stoa.eval.gates RUN_CHEAP RUN_CHALLENGER [--margin 0.10] [--name NAME]

For every question template (and every (source, type) bucket as a fallback) it reports n, accuracy of
both runs, and a choice: the challenger only if it beats the cheap run by more than `margin` (absolute)
AND by at least 2 questions; otherwise the cheap run (ties go to the cheaper path).
Writes $JUNCTION_SHARED/results/gates/<NAME>.json:
    {"cheap": solver, "challenger": solver, "margin": m, "templates": {template: {...}}, "buckets": {...}}
A router looks up `stoa.data.template_of(question)`, then the bucket, then defaults to the challenger
(unseen templates should take the general path, per D4).
"""

from __future__ import annotations

import argparse
import collections
import json

from stoa.eval.analyze import load, resolve
from stoa.eval.runner import SCORED_TYPES
from stoa.eval.splits import shared_root


def table(cheap: list[dict], chal: list[dict], margin: float) -> dict:
    cm = {r["qid"]: r for r in cheap}
    rows = [(cm[r["qid"]], r) for r in chal if r["qid"] in cm and r["type"] in SCORED_TYPES]

    def decide(pairs):
        n = len(pairs)
        a = sum(1 for c, _ in pairs if c["correct"])
        b = sum(1 for _, x in pairs if x["correct"])
        choice = "challenger" if (b - a) / n > margin and b - a >= 2 else "cheap"
        cost_b = sum(x.get("cost", {}).get("usd", 0) for _, x in pairs) / n
        return {"n": n, "acc_cheap": round(a / n, 3), "acc_challenger": round(b / n, 3), "choice": choice,
                "challenger_usd_per_q": round(cost_b, 6)}

    tpl, bucket = collections.defaultdict(list), collections.defaultdict(list)
    for c, x in rows:
        tpl[x["template"]].append((c, x))
        bucket[f"{x['source']}/{x['type']}"].append((c, x))
    return {"templates": {t: decide(v) for t, v in sorted(tpl.items())},
            "buckets": {b: decide(v) for b, v in sorted(bucket.items())}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m stoa.eval.gates", description=__doc__)
    ap.add_argument("cheap")
    ap.add_argument("challenger")
    ap.add_argument("--margin", type=float, default=0.10)
    ap.add_argument("--name", default=None)
    a = ap.parse_args(argv)
    cheap, chal = load(a.cheap), load(a.challenger)
    t = table(cheap, chal, a.margin)
    out = {"cheap": cheap[0].get("solver"), "challenger": chal[0].get("solver"), "margin": a.margin,
           "runs": [resolve(a.cheap).stem, resolve(a.challenger).stem], **t}
    name = a.name or f"{out['challenger']}_vs_{out['cheap']}"
    d = shared_root() / "results" / "gates"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"| template | n | {out['cheap']} | {out['challenger']} | choice |")
    print("|---|---:|---:|---:|---|")
    for k, v in list(t["buckets"].items()) + list(t["templates"].items()):
        print(f"| {k[:90]} | {v['n']} | {100*v['acc_cheap']:.0f}% | {100*v['acc_challenger']:.0f}% | "
              f"{out['cheap'] if v['choice'] == 'cheap' else out['challenger']} |")
    # what the gate would score on these questions (optimistic: chosen on the same sample)
    cm = {r["qid"]: r for r in cheap}
    tot = ok = 0
    for r in chal:
        if r["qid"] in cm and r["type"] in SCORED_TYPES:
            g = t["templates"][r["template"]]["choice"]
            ok += (r if g == "challenger" else cm[r["qid"]])["correct"]
            tot += 1
    print(f"\nwritten {d / (name + '.json')}; gated accuracy on this sample (optimistic, in-sample): {100*ok/max(1,tot):.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
