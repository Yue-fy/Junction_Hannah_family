"""Paired comparison of two runs on a link probe with R1's scorer (stoa.eval does not score text answers).

    python experiments/r1/kg_qa/compare.py PROBE RUN_BASE RUN_NEW
"""
import json
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from experiments.r1.kg_qa.run import correct  # noqa: E402

E = Path("/home/fangy4/work/projects/junction-shared/artifacts/eval")


def load(probe, rid):
    gold = {json.loads(x)["qid"]: json.loads(x) for x in open(probe)}
    out = {}
    for line in open(E / f"{rid}.jsonl"):
        d = json.loads(line)
        out[d["qid"]] = (correct(gold[d["qid"]], d.get("value")), float(d.get("confidence") or 0),
                         bool(d.get("evidence")), d.get("value"), d.get("cost") or {})
    return out


def main(probe, a, b):
    A, B = load(probe, a), load(probe, b)
    for tag, R in (("base", A), ("new", B)):
        xs = list(R.values())
        hi = [x for x in xs if x[1] >= 0.8]
        tok = sum((x[4].get("llm_tokens_in", 0) + x[4].get("llm_tokens_out", 0)) for x in xs) / max(len(xs), 1)
        print(f"{tag:5s} {sum(x[0] for x in xs)}/{len(xs)} right; conf>=0.8: {len(hi)} ({sum(x[0] for x in hi)} right); "
              f"evidence {sum(x[2] for x in xs)}; tokens/Q {tok:.0f}")
    w = sum(1 for q in A if B[q][0] and not A[q][0])
    lo = sum(1 for q in A if A[q][0] and not B[q][0])
    p = min(1.0, 2 * sum(comb(w + lo, i) for i in range(min(w, lo) + 1)) / 2 ** (w + lo)) if w + lo else 1.0
    print(f"won {w} lost {lo} (McNemar exact p = {p:.4f})")
    for q in B:
        if not B[q][0]:
            print("  still wrong:", q, str(B[q][3])[:70], B[q][1])


if __name__ == "__main__":
    main(*sys.argv[1:4])
