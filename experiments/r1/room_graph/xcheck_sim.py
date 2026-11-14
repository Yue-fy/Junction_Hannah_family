"""Offline: apply the room-graph area cross-check rule (pipeline_rg.area_crosscheck) to ANOTHER run's area answers,
reusing the text-layer graph values that the pipeline_rg+xcheck runs logged in their traces (no model calls).

    python experiments/r1/room_graph/xcheck_sim.py 085051-pipeline-probe_v1-4a93 ... (one run id per probe v1..v4)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from experiments.r1.room_graph.probe.run import correct  # noqa: E402
from experiments.r1.room_graph.xcheck_eval import RUNS, auroc  # noqa: E402

P = Path(__file__).parent / "probe"
E = Path("/home/fangy4/work/projects/junction-shared/artifacts/eval")
AGREE, DISAGREE = 0.75, 0.3


def graph_values():
    out = {}
    for rid in RUNS["pipeline_rg+xcheck"]:
        for line in open(E / f"20261114-{rid}.jsonl"):
            d = json.loads(line)
            for t in d.get("trace") or []:
                m = re.search(r"room-graph area cross-check: ([\d.]+) [=≠]", str(t))
                if m:
                    out[d["qid"]] = float(m.group(1))
    return out


def num(v):
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v if v is not None else ""))
    return float(m.group().replace(",", ".")) if m else None


def main(runs):
    gv = graph_values()
    before, after, after2, swap, rows = [], [], [], [], []
    for v, rid in zip(("v1", "v2", "v3", "v4"), runs):
        gold = {json.loads(x)["qid"]: json.loads(x) for x in open(P / f"probe_{v}.jsonl")}
        for line in open(E / f"20261114-{rid}.jsonl"):
            d = json.loads(line)
            r = gold.get(d.get("qid"))
            if r is None or r["type"] != "area":
                continue
            ok = correct(r, d.get("value"))
            c = float(d.get("confidence") or 0)
            before.append((c, ok))
            a, b = num(d.get("value")), gv.get(d["qid"])
            c1 = c2 = c
            if a is not None and b is not None:
                c1 = c2 = max(c, AGREE) if abs(a - b) <= 0.02 * max(abs(a), 1e-9) else min(c, DISAGREE)
            elif b is not None:  # a non-numeric answer to an area question ('bedroom', 'not specified')
                c2 = min(c, DISAGREE)
            after.append((c1, ok))
            after2.append((c2, ok))
            # 'graph answers': the text-layer graph's value when it has one (conf 0.75 if the pipeline agrees, else 0.5)
            if b is not None:
                okb = correct(r, b)
                swap.append((AGREE if (a is not None and abs(a - b) <= 0.02 * max(abs(a), 1e-9)) else 0.5, okb))
            else:
                okb = ok
                swap.append((c, ok))
            rows.append((d["qid"], ok, okb))
    for lab, rs in (("before", before), ("after xcheck", after), ("+non-numeric", after2), ("graph answers", swap)):
        hi = [x for x in rs if x[0] >= 0.7]
        print(f"{lab:13s} area n={len(rs)} right {sum(o for _, o in rs)} AUROC {auroc(rs)} "
              f"conf>=0.7: {len(hi)} ({sum(o for _, o in hi)} right)")
    w = sum(1 for _, o, g in rows if g and not o)
    lo = sum(1 for _, o, g in rows if o and not g)
    print(f"graph answers vs before: won {w} lost {lo} (McNemar exact p = {mcnemar(w, lo):.3f})")


def mcnemar(b, c):
    from math import comb
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


if __name__ == "__main__":
    main(sys.argv[1:] or RUNS["W4 4d4187f+W3 ac981b3"])
