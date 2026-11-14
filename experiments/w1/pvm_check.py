"""Check stoa.solvers.ifc.plan_vs_model on every link question of the given probe files (rows on ifc_models paths
that R1's is_link_question fires on): fired / comparable (num or yes/no, the pipeline's _link_shape) / right / wrong.
Usage: python experiments/w1/pvm_check.py probe.jsonl [...]  (W1 c8)"""
import json
import sys

from experiments.r1.kg_qa.kgqa import is_link_question
from stoa.pipeline import _link_shape
from stoa.solvers.ifc import plan_vs_model

n = fired = right = wrong = 0
for f in sys.argv[1:]:
    for line in open(f):
        d = json.loads(line)
        if "ifc_models" not in d["path"] or not is_link_question(d["question"]).get("fire"):
            continue
        n += 1
        a = plan_vs_model(d["path"], d["question"])
        if a is None:
            continue
        fired += 1
        sa, sg = _link_shape(a.value), _link_shape(d["answer"])
        if sa is None or sg is None:
            continue
        if sa == sg:
            right += 1
        else:
            wrong += 1
            print("  WRONG", str(a.value)[:60], "| gold", d["answer"], "|", d["question"][:90], d["path"][-40:])
print(f"link rows {n}, plan_vs_model fired {fired}, comparable {right + wrong}: right {right}, wrong {wrong}")
