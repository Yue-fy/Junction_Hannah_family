"""Do the reference apartment areas drop unnamed 4-corner rooms that stick out of the UNIT_OUTLINE? (F 09:16: two
apartments ~3% high in every wording, each by exactly one such room.) Train split only.
Usage: PYTHONPATH=. python experiments/w2/op_probe/apt_unnamed.py [max_questions]"""
import re
import sys
from collections import Counter

from stoa.eval.splits import load_split
from stoa.solvers.vector.dxf_solver import DxfSolver

s = DxfSolver(llm=0)
qs = [q for q in load_split("train") if q.source == "swiss_dwellings" and
      re.match(r"What is the net floor area of apartment ([A-Z])\b", q.question)]
qs = qs[: int(sys.argv[1]) if len(sys.argv) > 1 else 600]
c = Counter()
cache = {}
for q in qs:
    apt = re.match(r"What is the net floor area of apartment ([A-Z])\b", q.question).group(1)
    if q.path not in cache:
        cache[q.path] = s._load(q.path)[0]
    fm = cache[q.path]
    u = next((u for u in fm.units if u.label == apt), None)
    if u is None or u.poly is None:
        continue
    rooms = [r for r in fm.rooms if r.unit == apt and r.number and not r.outdoor]
    gold = float(q.answer)
    ok = lambda v: abs(v - gold) <= 0.02 * gold  # noqa: E731
    base = sum(r.area for r in rooms)
    feats = {}
    for r in rooms:
        if r.name:
            continue
        inside = r.poly.intersection(u.poly).area / r.poly.area
        feats[r.number] = (len(r.poly.exterior.coords) == 5, inside < 0.95)
    rule = [r for r in rooms if not (not r.name and feats[r.number][0] and feats[r.number][1])]
    rule_rect = [r for r in rooms if not (not r.name and feats[r.number][0])]
    rule_out = [r for r in rooms if not (not r.name and feats[r.number][1])]
    rule_all = [r for r in rooms if r.name]
    c["n"] += 1
    for k, rs in (("base", rooms), ("rect&out", rule), ("rect", rule_rect), ("out", rule_out), ("named_only", rule_all)):
        c[k] += ok(sum(r.area for r in rs))
    if feats:
        c["has_unnamed"] += 1
        c["has_unnamed_base_ok"] += ok(base)
        c["has_unnamed_rule_ok"] += ok(sum(r.area for r in rule))
print(dict(c))
