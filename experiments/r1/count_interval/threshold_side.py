"""Yes/no threshold questions ("at least N toilets?", "more than N windows?") answered from a LoRA count: confidence
from whether the CC5K detector's count is on the SAME side of N. Pooled over thresholds N = 1..10 per group
(openings: window, door; fixtures: wc, sink; rooms), fitted on train_gate, checked on dev (run 272e).
  python threshold_side.py [--write crosscheck_calib.json]"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cc5k_evidence"))
from agree import load_cache, rows  # noqa: E402

GROUP = {"window": "openings", "door": "openings", "wc": "fixtures", "sink": "fixtures",
         "bedroom": "rooms", "balcony": "rooms", "bathroom": "rooms", "kitchen": "rooms"}
EV = "/home/fangy4/work/projects/junction-shared/artifacts/eval/"


def cells(rs):
    c = collections.defaultdict(lambda: [0, 0])
    for r in rs:
        for n in range(1, 11):
            if max(r["lora"], r["det"], r["gold"]) < n - 1:  # thresholds far above every count say nothing
                continue
            ls, ds, gs = r["lora"] >= n, r["det"] >= n, r["gold"] >= n
            k = (GROUP[r["tgt"]], "same" if ls == ds else "straddle")
            c[k][0] += ls == gs
            c[k][1] += 1
    return c


if __name__ == "__main__":
    cache = load_cache()
    tr = [r for r in rows([EV + "20261114-012403-vlm_direct-train_gate-ee1b.jsonl"], cache) if r["lora"] is not None]
    dv = [r for r in rows([EV + "20261114-015159-pipeline-dev-272e.jsonl"], cache) if r["lora"] is not None]
    ct, cd = cells(tr), cells(dv)
    tab = {}
    for k in sorted(set(ct) | set(cd)):
        a, n = ct.get(k, [0, 0])
        p = round(min(0.97, (a + 1) / (n + 2)), 3)
        b, m = cd.get(k, [0, 0])
        tab[f"{k[0]}|{k[1]}"] = p
        print(f"{k[0]:9} {k[1]:8} train_gate {a}/{n} -> conf {p:.2f}   dev right {100*b/max(1,m):.0f}% of {m}")
    if "--write" in sys.argv:
        p = sys.argv[sys.argv.index("--write") + 1]
        d = json.load(open(p))
        d["threshold_side"] = {"rule": "P(LoRA's yes/no to 'count >= N?' is right | CC5K count on the same side of N "
                                       "or not), pooled over N = 1..10 per group, (k+1)/(n+2) capped 0.97, fitted on "
                                       "train_gate", "groups": GROUP, "table": tab}
        json.dump(d, open(p, "w"), indent=1)
