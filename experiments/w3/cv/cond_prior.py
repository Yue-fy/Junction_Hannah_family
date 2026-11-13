"""Conditional prior for symbol counts: mode of doors/windows given room counts (bedrooms, WC rooms, ...).
Table learned from TRAIN gold answers (drawings in the label sample excluded), applied to the room counts READ from
the labels on 200 TRAIN drawings (labels-train200.jsonl). Compared with the plain prior on the same drawings.

    PYTHONPATH=$PWD $JUNCTION_VENV/bin/python experiments/w3/cv/cond_prior.py [--write]
--write saves the chosen tables to stoa/solvers/raster/cond_prior.json.
"""
import argparse, collections, json, os, random, statistics
from pathlib import Path
from stoa.eval.splits import load_split
from stoa.solvers.raster.classes import label_class, type_code, question_class

SHARED = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
ap = argparse.ArgumentParser(); ap.add_argument("--write", action="store_true"); ap.add_argument("--min-support", type=int, default=10)
a = ap.parse_args()

gold = collections.defaultdict(dict)
for q in load_split("train"):
    if q.source != "cubicasa5k" or not q.question.lower().startswith("how"):
        continue
    c = question_class(q.question)
    if c:
        try:
            gold[q.path][c] = float(q.answer)
        except ValueError:
            pass
LABELS = os.environ.get("LABELS", "labels-train200.jsonl")
rows = [json.loads(l) for l in open(SHARED / "artifacts/W3/calib" / LABELS)]
sample = {r["path"] for r in rows}


def read_counts(r):
    items = [t for t, *_ in (r.get("items") or [])]
    n = collections.Counter(label_class(t) for t in items)
    codes = [type_code(t) for t in items if type_code(t)]
    feats = {"bedroom": n["bedroom"], "wc_room": n["wc_room"], "balcony": n["balcony"],
             "sauna": n["sauna"] or int(bool(codes and "sauna" in codes[0]["classes"])),
             "bathroom": max(1, n["bathroom"])}
    return {k: float(v) for k, v in feats.items()}


FEATS = [("bedroom",), ("bedroom", "wc_room"), ("bedroom", "sauna"), ("bedroom", "wc_room", "sauna"),
         ("bedroom", "wc_room", "balcony"), ("bedroom", "wc_room", "sauna", "balcony")]
results = {}
for tgt in ("door", "window", "wc_seat", "sink", "shower_bath"):
    learn = [p for p in gold if p not in sample and tgt in gold[p]]
    prior = collections.Counter(gold[p][tgt] for p in learn).most_common(1)[0][0]
    test = [(read_counts(r), gold[r["path"]][tgt]) for r in rows if tgt in gold.get(r["path"], {})]
    print(f"\n{tgt}: prior {prior}, n_test {len(test)}, prior acc {sum(prior == g for _, g in test) / len(test):.1%}")
    for feats in FEATS:
        tab = collections.defaultdict(collections.Counter)
        for p in learn:
            g = gold[p]
            if all(f in g for f in feats):
                tab[tuple(g[f] for f in feats)][g[tgt]] += 1
        def pred(fx):
            k = tuple(fx[f] for f in feats)
            c = tab.get(k)
            return c.most_common(1)[0][0] if c and sum(c.values()) >= a.min_support else prior
        acc = sum(pred(fx) == g for fx, g in test) / len(test)
        print(f"   {acc:6.1%}  | {feats}")
        results[(tgt, feats)] = (acc, {",".join(str(int(x)) for x in k): c.most_common(1)[0][0]
                                       for k, c in tab.items() if sum(c.values()) >= a.min_support}, prior)
CHOICE = {"door": ("bedroom", "wc_room", "sauna"), "window": ("bedroom", "wc_room", "sauna"), "wc_seat": ("bedroom",)}
if a.write:  # feature sets fixed from the 2-fold selection below (majority / consistent choice), not best-of-6
    out = {"_about": "Conditional prior: mode of the count given room counts read from labels. Tables from TRAIN gold "
                     "(cubicasa, excluding the 200 label-sample drawings); support >= %d drawings per cell, else the "
                     "plain prior. experiments/w3/cv/cond_prior.py" % a.min_support}
    for tgt, feats in CHOICE.items():
        learn = [p for p in gold if p not in sample and tgt in gold[p]]
        tab = collections.defaultdict(collections.Counter)
        for p in learn:
            g = gold[p]
            if all(f in g for f in feats):
                tab[tuple(g[f] for f in feats)][g[tgt]] += 1
        acc, _, prior = results[(tgt, feats)]
        out[tgt] = {"features": list(feats), "prior": prior, "train_acc_read_labels": round(acc, 3),
                    "table": {",".join(str(int(x)) for x in k): {"mode": c.most_common(1)[0][0], "n": sum(c.values()),
                                                                 "hit": round(c.most_common(1)[0][1] / sum(c.values()), 3)}
                              for k, c in sorted(tab.items()) if sum(c.values()) >= a.min_support}}
    Path("stoa/solvers/raster/cond_prior.json").write_text(json.dumps(out, indent=1))
    print("wrote stoa/solvers/raster/cond_prior.json")

# 2-fold selection over FEATS (choose on half A of the 200 read-label drawings, test on half B), 20 splits
print("\n2-fold selection of the feature set (unbiased gain vs prior):")
for tgt in ("door", "window", "wc_seat", "sink"):
    learn = [p for p in gold if p not in sample and tgt in gold[p]]
    prior = collections.Counter(gold[p][tgt] for p in learn).most_common(1)[0][0]
    tabs = {}
    for feats in FEATS:
        tab = collections.defaultdict(collections.Counter)
        for p in learn:
            g = gold[p]
            if all(f in g for f in feats):
                tab[tuple(g[f] for f in feats)][g[tgt]] += 1
        tabs[feats] = tab
    test = [(read_counts(r), gold[r["path"]][tgt]) for r in rows if tgt in gold.get(r["path"], {})]
    def pred(feats, fx):
        c = tabs[feats].get(tuple(fx[f] for f in feats))
        return c.most_common(1)[0][0] if c and sum(c.values()) >= a.min_support else prior
    def acc(feats, d):
        return sum((prior if feats is None else pred(feats, fx)) == g for fx, g in d) / len(d)
    gains, chosen = [], collections.Counter()
    for s in range(20):
        d = test[:]; random.Random(s).shuffle(d); h = len(d) // 2
        for A, B in ((d[:h], d[h:]), (d[h:], d[:h])):
            best = max(FEATS, key=lambda f: acc(f, A))
            chosen[best] += 1
            gains.append(acc(best, B) - acc(None, B))
    print(f"  {tgt}: mean held-out gain {statistics.mean(gains):+.1%} (min {min(gains):+.1%}); chosen {chosen.most_common(2)}")
