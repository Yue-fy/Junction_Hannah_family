"""Append the dataset wording of every base question to a wording-probe file (kind '<probe_kind>:dataset').

    python experiments/F/add_controls.py PROBE.jsonl
"""
import json
import sys

from stoa.eval.splits import load_split

p = sys.argv[1]
rows = [json.loads(l) for l in open(p)]
if any(r["meta"]["wording"] == "dataset" for r in rows):
    sys.exit("controls already present")
dev = {q.qid: q for q in load_split("dev")}
seen, extra = set(), []
for r in rows:
    b, k = r["meta"]["base_qid"], r["meta"]["probe_kind"]
    if (b, k) in seen:
        continue
    seen.add((b, k))
    q = dev[b]
    extra.append({"qid": "awbase" + b[:8] + k[-4:], "path": q.path, "question": q.question, "answer": q.answer,
                  "unit": q.unit, "type": q.type,
                  "meta": {"kind": f"{k}:dataset", "wording": "dataset", "probe_kind": k, "ambiguous": False,
                           "base_qid": b}})
with open(p, "a", encoding="utf-8") as f:
    for d in extra:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")
print(len(rows), "+", len(extra), "controls")
