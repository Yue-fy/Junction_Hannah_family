"""Score link-question probes: kg_qa standalone, a pipeline run, and 'pipeline + kg_qa when is_link_question fires'.

    python experiments/r1/kg_qa/run.py PROBE.jsonl [PIPELINE_RUN_ID] [--out pred.jsonl]
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from experiments.r1.kg_qa.kgqa import is_link_question, solve  # noqa: E402

E = Path("/home/fangy4/work/projects/junction-shared/artifacts/eval")
YES = r"^(yes|ja|kyllä|oui|si|sì|jah)\b"
NO = r"^(no|nein|ei|non|nej|nee)\b"


def correct(r, v):
    g = r["answer"]
    if v is None:
        return False
    s = str(v).strip().lower()
    if r["type"] == "count":
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        return bool(m) and abs(float(m.group()) - float(g)) < 1e-6
    if str(g).lower() in ("yes", "no"):
        return bool(re.search(YES if g == "yes" else NO, s))
    acc = r.get("meta", {}).get("accept_re")
    if acc:
        return bool(re.search(acc, str(v)))
    items = r.get("meta", {}).get("items")  # Q's red-team rows: every item regex must match (two-part answers)
    if items and all(isinstance(p, str) for p in items):
        return all(re.search(p, str(v), re.I) for p in items)
    return str(g).lower() in s


def main():
    probe = sys.argv[1]
    rows = [json.loads(x) for x in open(probe)]
    base = {}
    if len(sys.argv) > 2 and not sys.argv[2].startswith("--"):
        for line in open(E / f"{sys.argv[2]}.jsonl"):
            d = json.loads(line)
            base[d["qid"]] = d
    with ThreadPoolExecutor(4) as ex:
        preds = list(ex.map(lambda r: solve(r["path"], r["question"]), rows))
    out = []
    tot = {"kg": 0, "base": 0, "combo": 0, "fire": 0, "kg_hi": 0, "kg_hi_ok": 0, "base_hi": 0, "base_hi_ok": 0,
           "combo_hi": 0, "combo_hi_ok": 0}
    for r, a in zip(rows, preds):
        fire = is_link_question(r["question"])
        ok = correct(r, a.value)
        b = base.get(r["qid"], {})
        okb = correct(r, b.get("value"))
        cb = float(b.get("confidence") or 0)
        combo_ok, combo_c = (ok, a.confidence) if fire["fire"] and a.value is not None else (okb, cb)
        tot["kg"] += ok
        tot["base"] += okb
        tot["combo"] += combo_ok
        tot["fire"] += fire["fire"]
        for k, o, c in (("kg", ok, a.confidence), ("base", okb, cb), ("combo", combo_ok, combo_c)):
            if c >= 0.8:
                tot[k + "_hi"] += 1
                tot[k + "_hi_ok"] += o
        print(f"{r['qid']:14s} {'OK ' if ok else 'BAD'} kg={str(a.value)[:60]!s:62s} @{a.confidence:.2f} | "
              f"base {'OK ' if okb else 'BAD'} {str(b.get('value'))[:30]} @{cb:.2f} | fire={fire['why'] or '-'} | "
              f"gold {r['answer']}")
        out.append({"qid": r["qid"], "value": a.value, "confidence": a.confidence, "correct": ok,
                    "fire": fire, "trace": a.trace, "cost": a.cost.model_dump()})
    n = len(rows)
    print(f"n={n} kg_qa {tot['kg']}/{n} (conf>=0.8: {tot['kg_hi']}, {tot['kg_hi_ok']} right) | pipeline {tot['base']}/{n} "
          f"(conf>=0.8: {tot['base_hi']}, {tot['base_hi_ok']} right) | pipeline+kg_qa-on-trigger {tot['combo']}/{n} "
          f"(conf>=0.8: {tot['combo_hi']}, {tot['combo_hi_ok']} right) | trigger fires {tot['fire']}/{n}")
    toks = sum(o["cost"]["llm_tokens_in"] + o["cost"]["llm_tokens_out"] for o in out)
    print(f"kg_qa tokens/Q {toks / n:.0f}, calls/Q {sum(o['cost']['llm_calls'] for o in out) / n:.2f}")
    if "--out" in sys.argv:
        with open(sys.argv[sys.argv.index("--out") + 1], "w") as f:
            for o in out:
                f.write(json.dumps(o, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
