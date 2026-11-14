"""Diff two eval prediction files question by question (value or confidence changed)."""
import json
import sys

A = {json.loads(l)["qid"]: json.loads(l) for l in open(sys.argv[1])}
B = {json.loads(l)["qid"]: json.loads(l) for l in open(sys.argv[2])}
n = 0
for q in A:
    a, b = A[q], B.get(q)
    if b is None:
        continue
    if a["value"] != b["value"] or abs((a["confidence"] or 0) - (b["confidence"] or 0)) > 0.01:
        n += 1
        f = lambda x: str(x)[:70].replace("\n", " ")
        print(round(a["confidence"] or 0, 2), round(b["confidence"] or 0, 2), a.get("correct"), b.get("correct"), "|",
              f(a["value"]), "=>", f(b["value"]), "|", a["question"][:90], "| gold", f(a["gold"])[:50])
print(n, "changed of", len(A))
