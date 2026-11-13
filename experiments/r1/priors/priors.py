"""Per-template answer priors: how often the most common answer is right (a floor every solver must beat).

Run: python3 experiments/r1/priors/priors.py  (stdlib only; reads $STOA_DATA/questions.jsonl)
"""
import collections
import json
import os
import re

D = os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")
by = collections.defaultdict(collections.Counter)
n_src = collections.Counter()
for line in open(os.path.join(D, "questions.jsonl")):
    d = json.loads(line)
    src = d["path"].split("/")[1]
    if d["type"] != "count":
        continue
    q = re.sub(r"'[^']*'", "'X'", d["question"])  # collapse room labels
    q = re.sub(r"\d+(\.\d+)?", "#", q)
    by[(src, q[:70])][d["answer"]] += 1
    n_src[src] += 1

tot_hit = collections.Counter()
for (src, q), c in sorted(by.items(), key=lambda kv: -sum(kv[1].values())):
    n = sum(c.values())
    mode, k = c.most_common(1)[0]
    tot_hit[src] += k
    if n >= 300:
        top = ", ".join(f"{a}:{v/n:.0%}" for a, v in c.most_common(4))
        print(f"{src:16s} n={n:5d} mode={mode!s:>3} acc={k/n:.1%} | {top} | {q}")
print()
for s in n_src:
    print(f"{s}: majority-per-template accuracy on counts = {tot_hit[s]/n_src[s]:.1%} (n={n_src[s]})")
