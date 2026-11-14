"""Which per-room questions should go to room_graph.solve()?  Scores solve / pipeline / route policies on all probes.

    python experiments/r1/room_graph/route_policy.py
Policies: 'all' = every per_room() fire -> solve; 'no_area' = fires that do not ask for an area -> solve (areas stay
with the pipeline, whose VLM reads printed m2 next to the label).  Plan-cluster bootstrap CI + exact McNemar.
"""
import json
import random
import re
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from experiments.r1.room_graph.probe.run import correct, load_preds  # noqa: E402
from experiments.r1.room_graph.route import per_room  # noqa: E402

P = Path(__file__).parent / "probe"
E = Path("/home/fangy4/work/projects/junction-shared/artifacts/eval")
PIPE = {"v1": "20261114-081950-pipeline-probe_v1-e150", "v2": "20261114-082013-pipeline-probe_v2-1a17",
        "v3": "20261114-082042-pipeline-probe_v3-d9f7", "v4": "20261114-081658-pipeline-probe_v4-7aab"}
RG = {"v1": "20261114-082535-pipeline_rg-probe_v1-0a7c", "v2": "20261114-082543-pipeline_rg-probe_v2-3133",
      "v3": "20261114-082604-pipeline_rg-probe_v3-ba42", "v4": "20261114-082609-pipeline_rg-probe_v4-1586"}  # live
SOLVE = {"v1": "pred_v1_solve4", "v2": "pred_v2_solve4", "v3": "pred_v3_solve4", "v4": "pred_v4_solve"}
AREA = re.compile(r"\b(?:area|size|how\s+(?:big|large)|square\s+(?:met|feet|foot)|m2|m²|sq\.?\s*m|floor\s+space)\b", re.I)


def mcnemar(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n)


def main():
    recs = []
    for v in ("v1", "v2", "v3", "v4"):
        rows = [json.loads(line) for line in open(P / f"probe_{v}.jsonl")]
        pp, ps = load_preds(E / f"{PIPE[v]}.jsonl"), load_preds(P / f"{SOLVE[v]}.jsonl")
        prg = load_preds(E / f"{RG[v]}.jsonl")
        for r in rows:
            fire = per_room(r["question"], r["path"])["fire_any"]
            area = bool(AREA.search(r["question"]))
            a, b = correct(r, pp.get(r["qid"])), correct(r, ps.get(r["qid"]))
            recs.append(dict(v=v, plan=r["path"], type=r["type"], fire=fire, area=area, pipe=a, solve=b,
                             rg=correct(r, prg.get(r["qid"])),
                             all=b if fire else a, no_area=b if fire and not area else a))
    for name, sel in [("all 78", lambda x: True), ("v1-v3 (54)", lambda x: x["v"] != "v4"),
                      ("v4 untouched (24)", lambda x: x["v"] == "v4")]:
        rs = [x for x in recs if sel(x)]
        print(f"{name}: " + "  ".join(f"{k} {sum(x[k] for x in rs)}/{len(rs)}" for k in ("pipe", "solve", "all", "no_area", "rg")))
    print("by bucket (all 78): fired&area / fired&not-area / not fired")
    for nm, sel in [("fired, asks area", lambda x: x["fire"] and x["area"]),
                    ("fired, not area", lambda x: x["fire"] and not x["area"]), ("not fired", lambda x: not x["fire"])]:
        for v in ("v1-v3", "v4"):
            rs = [x for x in recs if sel(x) and ((x["v"] == "v4") == (v == "v4"))]
            print(f"  {nm:18s} {v:6s} n={len(rs):3d}  pipeline {sum(x['pipe'] for x in rs):3d}  solve {sum(x['solve'] for x in rs):3d}")
    # paired: no_area policy (simulated from the two runs) and pipeline_rg (live run) vs pipeline
    for key, name, sel in [(k, n, f) for k in ("no_area", "rg") for n, f in
                           [("all 78", lambda x: True), ("v4 untouched", lambda x: x["v"] == "v4")]]:
        rs = [x for x in recs if sel(x)]
        b = sum(x[key] and not x["pipe"] for x in rs)
        c = sum(x["pipe"] and not x[key] for x in rs)
        plans = sorted({x["plan"] for x in rs})
        by = {p: [x for x in rs if x["plan"] == p] for p in plans}
        rng = random.Random(0)
        ds = []
        for _ in range(4000):
            s = [x for p in rng.choices(plans, k=len(plans)) for x in by[p]]
            ds.append(100 * (sum(x[key] for x in s) - sum(x["pipe"] for x in s)) / len(s))
        ds.sort()
        d = 100 * (sum(x[key] for x in rs) - sum(x["pipe"] for x in rs)) / len(rs)
        print(f"{key} vs pipeline, {name}: {d:+.1f} pts [{ds[100]:+.1f}, {ds[3899]:+.1f}] ({len(plans)} plans), "
              f"McNemar {b} vs {c} p={mcnemar(b, c):.4f}")


if __name__ == "__main__":
    main()
