"""Offline rule search: fixture counts from room labels on 200 TRAIN drawings (labels-train200.jsonl), with 2-fold
selection so the reported number is not best-of-many. python experiments/w3/cv/fixture_rules.py"""
import collections, json, os, random, statistics
from pathlib import Path
from stoa.solvers.raster import class_prior
from stoa.solvers.raster.classes import label_class, type_code
SHARED = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
LABELS = os.environ.get("LABELS", "labels-train200.jsonl")
rows = [json.loads(l) for l in open(SHARED / "artifacts/W3/calib" / LABELS)]
prior = class_prior()

def feats(r):
    items = [(t, label_class(t)) for t, c, *_ in (r.get("items") or [])]  # runtime classifier
    n = collections.Counter(c for _, c in items if c)
    looped = any(x.startswith("LOOP") for x in r.get("notes", []))  # as at runtime (retry fixed the rest)
    return n, looped

RULES = {
    "sink": {
        "prior": lambda n: prior["sink"][0],
        "1+max(1,bath)": lambda n: 1 + max(1, n["bathroom"]),
        "1+max(1,bath)+wc": lambda n: 1 + max(1, n["bathroom"]) + n["wc_room"],
        "1+bath+wc": lambda n: 1 + n["bathroom"] + n["wc_room"],
        "max(prior,1+max1bath+wc)": lambda n: max(prior["sink"][0], 1 + max(1, n["bathroom"]) + n["wc_room"]),
        "1+max(1,bath+wc)": lambda n: 1 + max(1, n["bathroom"] + n["wc_room"]),
    },
    "wc_seat": {
        "prior": lambda n: prior["wc_seat"][0],
        "max(1,wc)": lambda n: max(1, n["wc_room"]),
        "wc+1": lambda n: n["wc_room"] + 1,
        "max(1,wc+bath)": lambda n: max(1, n["wc_room"] + n["bathroom"]),
        "wc + (1 if no wc)": lambda n: n["wc_room"] if n["wc_room"] else 1,
        "max(prior,wc)": lambda n: max(prior["wc_seat"][0], n["wc_room"]),
        "max(prior,wc+1 if wc else prior)": lambda n: n["wc_room"] + 1 if n["wc_room"] else prior["wc_seat"][0],
    },
    "shower_bath": {
        "prior": lambda n: prior["shower_bath"][0],
        "max(1,bath)": lambda n: max(1, n["bathroom"]),
        "max(prior,bath)": lambda n: max(prior["shower_bath"][0], n["bathroom"]),
    },
}
for cls, rules in RULES.items():
    data = []
    for r in rows:
        if cls not in r["gold"]:
            continue
        n, looped = feats(r)
        data.append((n, looped, float(r["gold"][cls])))
    def acc(rule, d):  # loop -> prior
        return sum((prior[cls][0] if lp else rules[rule](n)) == g for n, lp, g in d) / max(1, len(d))
    full = {k: acc(k, data) for k in rules}
    print(f"\n{cls}: n={len(data)} (looped {sum(lp for _, lp, _ in data)}); prior value {prior[cls][0]}")
    for k, v in sorted(full.items(), key=lambda kv: -kv[1]):
        print(f"   {v:6.1%}  {k}")
    gains = []
    for seed in range(20):
        d = data[:]; random.Random(seed).shuffle(d); h = len(d) // 2
        for A, B in ((d[:h], d[h:]), (d[h:], d[:h])):
            best = max(rules, key=lambda k: (acc(k, A), k == "prior"))
            gains.append(acc(best, B) - acc("prior", B))
    print(f"   2-fold selected rule vs prior on held-out half: mean gain {statistics.mean(gains):+.1%} "
          f"(min {min(gains):+.1%}, max {max(gains):+.1%})")
