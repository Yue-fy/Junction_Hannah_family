"""Held-out check of the CV door counter on TRAIN drawings (never dev).

Fit on 2/3 of the drawings: (a) the threshold setting with the best exact accuracy, (b) a mapping
detected-count -> most frequent gold count (falls back to the prior for rare detected counts).
Test on the other 1/3 against the prior. Repeats over 5 random splits.

    python experiments/w3/cv/heldout_doors.py <raw.jsonl> [<raw.jsonl> ...]
"""
import collections, itertools, json, random, statistics, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from sweep_doors import nms  # noqa: E402

rows = []
seen = set()
for f in sys.argv[1:]:
    for l in open(f):
        r = json.loads(l)
        if r["path"] not in seen and "raw" in r:
            seen.add(r["path"]); rows.append(r)
SETTINGS = list(itertools.product((0.25, 0.35, 0.5, 0.7, 1.0), (0.2, 0.35), (0.022, 0.03, 0.04)))


def count(r, s):
    sthr, ithr, rfrac = s
    m = max(r["shape"])
    return len(nms([d for d in r["raw"] if d[4] <= sthr and d[5] <= ithr and d[2] >= rfrac * m]))


cnt = {s: [count(r, s) for r in rows] for s in SETTINGS}
gold = [r["gold"] for r in rows]
print(len(rows), "drawings")
out = []
for seed in range(5):
    idx = list(range(len(rows))); random.Random(seed).shuffle(idx)
    k = len(idx) * 2 // 3
    tr, te = idx[:k], idx[k:]
    prior = collections.Counter(gold[i] for i in tr).most_common(1)[0][0]
    best = max(SETTINGS, key=lambda s: sum(cnt[s][i] == gold[i] for i in tr))
    # mapping detected -> gold mode (min support 8)
    best_map, best_map_acc = None, -1
    for s in SETTINGS:
        by = collections.defaultdict(collections.Counter)
        for i in tr:
            by[cnt[s][i]][gold[i]] += 1
        mp = {d: c.most_common(1)[0][0] for d, c in by.items() if sum(c.values()) >= 8}
        acc = sum(mp.get(cnt[s][i], prior) == gold[i] for i in tr)
        if acc > best_map_acc:
            best_map, best_map_acc, ms = mp, acc, s
    te_prior = sum(prior == gold[i] for i in te) / len(te)
    te_raw = sum(cnt[best][i] == gold[i] for i in te) / len(te)
    te_map = sum(best_map.get(cnt[ms][i], prior) == gold[i] for i in te) / len(te)
    te_w1 = sum(abs(cnt[best][i] - gold[i]) <= 1 for i in te) / len(te)
    out.append((te_prior, te_raw, te_map, te_w1))
    print(f"split {seed}: n_test {len(te)} prior {te_prior:.1%} raw {te_raw:.1%} (setting {best}, within1 {te_w1:.1%}) "
          f"mapped {te_map:.1%} (setting {ms}, map {dict(sorted(best_map.items()))})")
m = [statistics.mean(x[j] for x in out) for j in range(4)]
print(f"MEAN over splits: prior {m[0]:.1%} raw {m[1]:.1%} mapped {m[2]:.1%} raw-within1 {m[3]:.1%}")
