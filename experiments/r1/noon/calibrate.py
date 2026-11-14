"""Calibrate triage.py's 'new kind' threshold: nearest-TRAIN-question similarity of open splits.
dev = the same templates on other drawings (should look 'seen'), hard = rewordings/translations/compositions,
hard2 = new operators, Q's red team (artifacts/Q/v*.jsonl) = hand-written new kinds. Sealed splits are not read.

    $JUNCTION_VENV/bin/python experiments/r1/noon/calibrate.py
"""
import glob
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from experiments.r1.noon.triage import NN  # noqa: E402
from stoa.eval.splits import load_split  # noqa: E402
from stoa.router.prior import known_template  # noqa: E402

SH = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")
train = [{"question": q.question, "path": q.path, "type": q.type} for q in load_split("train")]
nn = NN(train)
print(f"index: {len(nn.rows)} distinct train questions")
rng = random.Random(0)
sets = {s: [q.question for q in load_split(s)] for s in ("dev", "hard", "hard2")}
qrows = []
for f in sorted(glob.glob(f"{SH}/artifacts/Q/v[0-9]*.jsonl")):
    if any(x in f for x in ("snap", "night", "6025963", "_in")):
        continue
    qrows += [json.loads(x)["question"] for x in open(f) if x.strip()]
sets["Q redteam"] = qrows
for s in list(sets):
    xs = sets[s]
    sets[s] = rng.sample(xs, min(400, len(xs)))
ths = (0.4, 0.5, 0.6, 0.7)
print(f"{'set':10s} {'n':>4s} {'median':>6s} " + " ".join(f"<{t:.1f}" for t in ths) + "  template  new@0.5&!tmpl  new@0.6&!tmpl")
for s, xs in sets.items():
    sims = sorted(nn.query(q)[0][0] for q in xs)
    tm = [known_template(q) for q in xs]
    sq = [nn.query(q)[0][0] for q in xs]
    n = len(xs)
    new5 = sum(1 for a, t in zip(sq, tm) if a < 0.5 and not t)
    new6 = sum(1 for a, t in zip(sq, tm) if a < 0.6 and not t)
    print(f"{s:10s} {n:4d} {sims[n // 2]:6.2f} " + " ".join(f"{100 * sum(x < t for x in sims) / n:4.0f}%" for t in ths)
          + f"  {100 * sum(tm) / n:6.0f}%  {100 * new5 / n:8.0f}%  {100 * new6 / n:8.0f}%")
