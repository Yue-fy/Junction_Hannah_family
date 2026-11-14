"""Run the c5 multilingual probe through ifc: raw question vs stoa.llm.to_english(force=True) first.

Usage: PYTHONPATH=. python experiments/w1/ml_run.py OUT.jsonl [raw|tr|both]"""
import json, sys, time
sys.path.insert(0, "experiments/w1/probes")
from c5_ml import ROWS, GOLD, PATHS  # noqa: E402
from stoa.solvers.ifc.solver import IfcSolver  # noqa: E402
from stoa import llm  # noqa: E402

S = IfcSolver()
out = open(sys.argv[1], "w")
modes = ["raw", "tr"] if (len(sys.argv) < 3 or sys.argv[2] == "both") else [sys.argv[2]]


def right(val, gold, kind, conf):
    if kind == "lowconf":
        return conf <= 0.5
    if kind == "text":
        return isinstance(val, str) and gold.lower() in val.lower() and len(val) < 40
    try:
        v = float(val)
    except (TypeError, ValueError):
        return False
    return abs(v - gold) <= max(0.02 * abs(gold), 1e-6) if not float(gold).is_integer() or gold > 50 else v == gold


for lang, i, q in ROWS:
    for mode in modes:
        qq, note = q, ""
        if mode == "tr":
            tr = llm.to_english(q, force=True)
            qq, note = tr.text, tr.note
        t = time.time()
        try:
            a = S.solve(PATHS[i], qq)
            val, conf, unit, trace = a.value, a.confidence, a.unit, (a.trace or [])[:3]
        except Exception as e:  # noqa: BLE001
            val, conf, unit, trace = None, 0.0, None, [f"ERR {type(e).__name__}: {e}"]
        g, kind = GOLD[i]
        ok = right(val, g, kind, conf)
        rec = dict(lang=lang, idx=i, mode=mode, q=q, q_used=qq, value=val if not isinstance(val, str) else val[:120],
                   unit=unit, conf=round(conf, 3), gold=g, ok=ok, cw=(not ok and conf >= 0.8), trace=[str(x)[:200] for x in trace],
                   sec=round(time.time() - t, 2))
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        out.flush()
        print(f"{lang} {i:2d} {mode:3s} {'OK ' if ok else ('CW ' if rec['cw'] else 'no ')} [{conf:.2f}] {str(val)[:30]:>30} | {qq[:90]}")
