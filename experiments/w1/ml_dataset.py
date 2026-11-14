"""New ifc solve() (with its cross-language check) on the dataset's non-English ifc_models questions; compares
with the raw/tr columns of tr_agree.jsonl. Usage: PYTHONPATH=. python experiments/w1/ml_dataset.py IN.jsonl OUT.jsonl"""
import json, sys
from stoa.eval.splits import load_split
from stoa.eval.scoring import score
from stoa.solvers.ifc.solver import IfcSolver
qs = {q.qid: q for sp in ("train", "dev", "hard") for q in load_split(sp)}
S = IfcSolver()
rows = [json.loads(l) for l in open(sys.argv[1])]
out = open(sys.argv[2], "w")
n = ok = cw = lost = 0
for r in rows:
    q = qs[r["qid"]]
    a = S.solve(q.path, q.question)
    good = bool(score(q.type, q.answer, q.unit, a.value, a.unit))
    n += 1; ok += good; cw += (not good and a.confidence >= 0.8)
    if r["raw"]["ok"] and not good:
        lost += 1
        print("LOST", r["split"], r["lang"], a.value, a.confidence, "|", q.question[:90])
    if r["raw"]["ok"] and good and a.confidence < r["raw"]["c"] - 0.01:
        print("conf", r["split"], r["lang"], r["raw"]["c"], "->", a.confidence, "|", q.question[:90])
    out.write(json.dumps(dict(qid=q.qid, split=r["split"], lang=r["lang"], ok=good, c=a.confidence, v=str(a.value)[:60]), ensure_ascii=False) + "\n")
print(f"{ok}/{n} right, {cw} confident-wrong, {lost} lost vs raw")
