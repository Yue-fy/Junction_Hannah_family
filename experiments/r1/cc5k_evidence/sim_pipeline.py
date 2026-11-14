"""Offline: apply stoa.solvers.raster_cc5k.crosscheck.check() to every cubicasa answer of a stored pipeline run
(no model calls), rescore, and print weighted/micro accuracy, evidence rates and calibration before/after, plus
the per-question file for experiments/r1/stats/compare.py.
  python sim_pipeline.py RUN.jsonl OUT.jsonl [--no-arbitrate]"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from stoa.contract import Answer  # noqa: E402
from stoa.eval.runner import summarize  # noqa: E402
from stoa.eval.scoring import score  # noqa: E402
from stoa.router.intent import parse  # noqa: E402
from stoa.solvers.raster_cc5k.crosscheck import check  # noqa: E402

FIELDS = ("value", "unit", "confidence", "evidence", "solver", "trace", "assumptions", "missing")


def main(run, out, arbitrate=True):
    rows = [json.loads(l) for l in open(run)]
    new = []
    n_touch = n_switch = 0
    for r in rows:
        r2 = copy.deepcopy(r)
        if r["source"] == "cubicasa5k" and r["type"] == "count" and r["value"] is not None:
            key = parse(r["question"]).key
            a = Answer(**{k: r[k] for k in FIELDS if r.get(k) is not None})
            b = check(r["path"], key, a, source=(r["solver"] or "").replace("pipeline/", ""), arbitrate=arbitrate)
            if b.trace != a.trace:
                n_touch += 1
                n_switch += b.value != a.value
                d = json.loads(b.model_dump_json())
                for k in FIELDS:
                    r2[k] = d.get(k)
                r2["correct"] = score(r["type"], r["gold"], r.get("gold_unit"), r2["value"], r2["unit"])
        new.append(r2)
    with open(out, "w") as f:
        for r in new:
            f.write(json.dumps(r) + "\n")
    print(f"touched {n_touch} answers, switched value on {n_switch}")
    for name, rs in (("before", rows), ("after", new)):
        m = summarize(copy.deepcopy(rs))
        c = m["by_bucket"].get("cubicasa5k/count", {})
        print(f"{name:6} weighted {m['weighted_acc']:.4f}  micro {m['accuracy']:.4f}  cubicasa/count acc {c.get('accuracy')} "
              f"ev {c.get('evidence_rate')} ev2d {c.get('evidence_2d_rate')} count_match {c.get('evidence_count_match')} "
              f"(n {c.get('evidence_count_n')})  ALL ev2d {m.get('evidence_2d_rate')} ece {m.get('ece')}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--no-arbitrate" not in sys.argv)
