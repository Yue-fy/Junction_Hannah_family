"""Rough quality proxy for ifc_bench free-text answers: share of answered questions where the FIRST number in
the gold answer appears (within 2%) among the numbers of our answer. Usage: python bench_numcheck.py RUN.jsonl"""
import json, re, sys
NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def nums(s):
    out = []
    for m in NUM.findall(str(s)):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


rows = [json.loads(l) for l in open(sys.argv[1])]
ans = [r for r in rows if r["value"] is not None]
hit = 0
for r in ans:
    g = nums(r["gold"])
    mine = nums(r["value"])
    if g and any(abs(m - g[0]) <= 0.02 * max(abs(g[0]), 1e-9) for m in mine):
        hit += 1
print(f"answered {len(ans)}/{len(rows)}; gold headline number found in our answer: {hit}/{len(ans)} = {hit / max(len(ans), 1):.0%}")
