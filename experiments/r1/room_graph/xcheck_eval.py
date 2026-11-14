"""Area cross-check (pipeline_rg area_xcheck=1) vs without, on all by-eye probes: accuracy, evidence, calibration.

    python experiments/r1/room_graph/xcheck_eval.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from experiments.r1.room_graph.probe.run import correct  # noqa: E402

P = Path(__file__).parent / "probe"
E = Path("/home/fangy4/work/projects/junction-shared/artifacts/eval")
RUNS = {"pipeline": ["081950-pipeline-probe_v1-e150", "082013-pipeline-probe_v2-1a17", "082042-pipeline-probe_v3-d9f7",
                     "081658-pipeline-probe_v4-7aab"],
        "night W4-wired": ["084138-pipeline-probe_v1-74e3", "084146-pipeline-probe_v2-9163",
                           "084152-pipeline-probe_v3-51e3", "084156-pipeline-probe_v4-2fed"],
        "pipeline_rg": ["082535-pipeline_rg-probe_v1-0a7c", "082543-pipeline_rg-probe_v2-3133",
                        "082604-pipeline_rg-probe_v3-ba42", "082609-pipeline_rg-probe_v4-1586"],
        "pipeline_rg+xcheck": ["083916-pipeline_rg-probe_v1-81f3", "083923-pipeline_rg-probe_v2-4082",
                               "083938-pipeline_rg-probe_v3-fdf1", "083944-pipeline_rg-probe_v4-5291"]}


def auroc(pairs):
    pos = [c for c, y in pairs if y]
    neg = [c for c, y in pairs if not y]
    if not pos or not neg:
        return None
    s = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(s / (len(pos) * len(neg)), 3)


def main():
    for name, runs in RUNS.items():
        allr, area, tags = [], [], []
        for v, rid in zip(("v1", "v2", "v3", "v4"), runs):
            gold = {json.loads(line)["qid"]: json.loads(line) for line in open(P / f"probe_{v}.jsonl")}
            for line in open(E / f"20261114-{rid}.jsonl"):
                d = json.loads(line)
                if d.get("qid") not in gold:
                    continue
                r = gold[d["qid"]]
                ok = correct(r, d.get("value"))
                rec = (ok, float(d.get("confidence") or 0), bool(d.get("evidence")))
                allr.append(rec)
                tags.append(v)
                if r["type"] == "area":
                    area.append(rec)
        for lab, rs in (("all", allr), ("area", area)):
            n = len(rs)
            hi = [x for x in rs if x[1] >= 0.7]
            if lab == "all":
                v4 = [x for x, vv in zip(allr, tags) if vv == "v4"]
                print(f"{name:20s} v4   n={len(v4):2d} right {sum(x[0] for x in v4):2d}")
            print(f"{name:20s} {lab:4s} n={n:2d} right {sum(x[0] for x in rs):2d}  evidence {sum(x[2] for x in rs):2d}  "
                  f"AUROC {auroc([(x[1], x[0]) for x in rs])}  conf>=0.7: {len(hi)} ({sum(x[0] for x in hi)} right)")


if __name__ == "__main__":
    main()
