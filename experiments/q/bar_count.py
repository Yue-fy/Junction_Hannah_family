"""Chart bar for one build: confident misses (conf >= 0.8 wrong, or any >= 0.8 answer to a flag row) over every
family asked, the way plot_rounds.py counts them: v22 dataset-path / styled controls (cc-control, cc-styled) are not
counted; v26 (hashed copies) counts only misses whose dataset-path twin (same qid) is NOT already a confident miss.
    python3 experiments/q/bar_count.py MAIN_RUN [MAIN_RUN2 ...] --v26 V26_RUN
(run from the night-Q root; rescored with redteam/analyze.py and the current questions.jsonl)"""
import json, sys
from collections import Counter
sys.path.insert(0, "redteam")
from analyze import rescore

args = sys.argv[1:]
v26 = args[args.index("--v26") + 1] if "--v26" in args else None
mains = [a for a in args if a != "--v26" and a != v26]
def miss(r):
    c = r["confidence"] or 0
    return c >= 0.8 and (r["correct"] is False or r["meta"]["expect"] == "flag")
R = {}
for m in mains:
    for r in rescore([json.loads(l) for l in open(m)]):
        R[r["qid"]] = r
bad = {q for q, r in R.items() if miss(r) and r["meta"]["kind"] not in ("upload22:cc-control", "upload22:cc-styled")}
fam = Counter(R[q]["meta"]["kind"].split(":")[0] for q in bad)
extra = []
if v26:
    for r in rescore([json.loads(l) for l in open(v26)]):
        if "drawings belong" in r["question"]:
            continue
        if miss(r) and not (r["qid"] in R and miss(R[r["qid"]])):
            extra.append(r["question"][:70])
print("main", len(bad), dict(fam), "| v26 hashed-only", len(extra), extra, "| bar", len(bad) + len(extra))
