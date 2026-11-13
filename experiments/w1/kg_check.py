"""Sanity check of stoa.kg.crosscheck: feed it the GOLD answer of dev questions; a sound cross-check says ✓
(agree) for nearly all of them, and gives a note on as many as possible (coverage).
PYTHONPATH=$PWD python experiments/w1/kg_check.py [split]"""
import collections, sys
from stoa.eval.splits import load_split
from stoa.kg import crosscheck
from stoa.router.intent import parse

split = sys.argv[1] if len(sys.argv) > 1 else "dev"
c = collections.Counter()
bad = []
for q in load_split(split):
    if q.source not in ("ifc_models", "swiss_dwellings") or q.type not in ("count", "area"):
        continue
    note = crosscheck(q.path, parse(q.question), {"value": q.answer})
    k = (q.source, q.type)
    c[k + ("n",)] += 1
    if note:
        c[k + ("noted",)] += 1
        if "✗" in note:
            c[k + ("disagree",)] += 1
            bad.append((q.path.split("/")[-1], q.question[:80], q.answer, note))
for k in sorted({x[:2] for x in c}):
    n = c[k + ("n",)]
    print(f"{k}: n={n} noted={c[k + ('noted',)]} ({c[k + ('noted',)] / n:.0%}) disagree-with-gold={c[k + ('disagree',)]}")
for b in bad[:12]:
    print("  ✗", b)
