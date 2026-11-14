"""S0 (D15): ifc_models accuracy on a sealed test run, with and without the 'mechanism seen' model (bsc-molio).
Aggregates only. Usage: python3 experiments/s0/ifc_split.py <test predictions .jsonl> [model-substring]"""
import json, sys
from collections import Counter

path = sys.argv[1]
seen = sys.argv[2] if len(sys.argv) > 2 else "bsc-molio"
n, c = Counter(), Counter()
for line in open(path):
    r = json.loads(line)
    if r.get("source") != "ifc_models" or str(r.get("correct")) not in ("True", "False"):
        continue
    part = "seen" if seen in r["path"] else "rest"
    for k in (part, "all"):
        n[k] += 1
        c[k] += str(r["correct"]) == "True"
for k in ("all", "rest", "seen"):
    if n[k]:
        print(f"ifc_models {k:4s} ({'with' if k == 'all' else 'without' if k == 'rest' else 'only'} {seen}): "
              f"{c[k]}/{n[k]} = {100 * c[k] / n[k]:.1f}%")
