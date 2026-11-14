"""Per-concept combination rules for LoRA (cc-v2) + CC5K detector counts, with drawing-cluster bootstrap CIs.
Rules: lora, cc5k, mean (round half up of the mean), and 'agree->value else X'.  Fit on train_gate, report dev.
  python ensemble.py FIT.jsonl EVAL.jsonl"""
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agree import load_cache, rows  # noqa: E402

RULES = {
    "lora": lambda r: r["lora"],
    "cc5k": lambda r: r["det"],
    "mean_up": lambda r: int((r["lora"] + r["det"]) / 2 + 0.5) if r["lora"] is not None else r["det"],
    "mean_dn": lambda r: int((r["lora"] + r["det"]) / 2) if r["lora"] is not None else r["det"],
    "max": lambda r: max(r["lora"] or 0, r["det"]),
}


def acc(g, f):
    return sum(f(r) == r["gold"] for r in g) / len(g)


def paired_ci(g, fa, fb, B=2000, seed=0):
    by = defaultdict(list)
    for r in g:
        by[r["path"]].append((f := (fa(r) == r["gold"]) - (fb(r) == r["gold"])))
    keys = list(by)
    rnd = random.Random(seed)
    d0 = sum(sum(v) for v in by.values()) / len(g)
    ds = []
    for _ in range(B):
        s = n = 0
        for k in (rnd.choice(keys) for _ in keys):
            s += sum(by[k]); n += len(by[k])
        ds.append(s / n)
    ds.sort()
    return d0, ds[int(0.025 * B)], ds[int(0.975 * B)]


if __name__ == "__main__":
    cache = load_cache()
    fit, ev = rows([sys.argv[1]], cache), rows([sys.argv[2]], cache)
    for name, g in (("FIT " + os.path.basename(sys.argv[1]), fit), ("EVAL " + os.path.basename(sys.argv[2]), ev)):
        by = defaultdict(list)
        for r in g:
            by[r["tgt"]].append(r)
        print(f"\n== {name}")
        print(f"{'concept':9} {'n':>4} " + " ".join(f"{k:>8}" for k in RULES) + "   cc5k-lora [95% CI]")
        for t in ("window", "door", "wc", "sink", "bedroom", "balcony", "bathroom", "kitchen"):
            if t not in by:
                continue
            gg = by[t]
            d, lo, hi = paired_ci(gg, RULES["cc5k"], RULES["lora"])
            print(f"{t:9} {len(gg):4d} " + " ".join(f"{100*acc(gg, f):8.1f}" for f in RULES.values())
                  + f"   {100*d:+.1f} [{100*lo:+.1f}, {100*hi:+.1f}]")
