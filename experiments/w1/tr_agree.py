"""Raw vs translated-first ifc answers on the DATASET's non-English ifc_models questions (train sample/dev/hard).

Measures what translating inside ifc would cost on wordings the parser already reads: how often the two readings
disagree, and which one is right then. Usage: PYTHONPATH=. python experiments/w1/tr_agree.py OUT.jsonl"""
import json, random, sys
from concurrent.futures import ThreadPoolExecutor
from stoa.eval.splits import load_split
from stoa.eval.scoring import score
from stoa import llm
from stoa.router.prior import known_template
from stoa.solvers.ifc.solver import IfcSolver

rows = []
for sp, cap in (("dev", 999), ("hard", 999), ("train", 160)):
    qs = [q for q in load_split(sp) if q.source == "ifc_models" and llm.lang_guess(q.question) != "en"]
    random.Random(7).shuffle(qs)
    rows += [(sp, q) for q in qs[:cap]]
print(len(rows), "questions", file=sys.stderr)
with ThreadPoolExecutor(8) as ex:
    trs = list(ex.map(lambda r: llm.to_english(r[1].question, force=True), rows))
S = IfcSolver()
out = open(sys.argv[1], "w")
for (sp, q), tr in zip(rows, trs):
    rec = dict(split=sp, qid=q.qid, q=q.question, tr=tr.text, translated=tr.translated, lang=tr.lang,
               known=known_template(q.question), gold=q.answer)
    for tag, text in (("raw", q.question), ("tr", tr.text)):
        try:
            a = S.solve(q.path, text)
            ok = bool(score(q.type, q.answer, q.unit, a.value, a.unit))
            rec[tag] = dict(v=a.value if not isinstance(a.value, str) else a.value[:80], u=a.unit, c=round(a.confidence, 3), ok=ok)
        except Exception as e:  # noqa: BLE001
            rec[tag] = dict(v=None, u=None, c=0.0, ok=False, err=str(e)[:100])
    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
