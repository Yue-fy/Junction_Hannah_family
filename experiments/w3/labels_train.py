"""Read room labels (solver's R1-v2 method) on N TRAIN drawings and score label policies + fixture-from-rooms
rules per class. Choices for gate.json come from this TRAIN table.
    PYTHONPATH=$PWD $JUNCTION_VENV/bin/python experiments/w3/labels_train.py --n 200
"""
import argparse, collections, concurrent.futures as cf, contextvars, json, random, time
from pathlib import Path
from stoa import llm
from stoa.data import abspath
from stoa.eval.splits import load_split
from stoa.solvers.raster import class_prior
from stoa.solvers.raster.classes import ROOM_CLASSES, question_class, type_code
from stoa.solvers.raster import vlm

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=200)
ap.add_argument("--seed", type=int, default=7)
ap.add_argument("--split", default="train")
a = ap.parse_args()
prior = class_prior()
gold = collections.defaultdict(dict)
for q in load_split(a.split):
    if q.source == "cubicasa5k" and q.question.lower().startswith("how"):
        c = question_class(q.question)
        if c:
            gold[q.path][c] = q.answer
paths = sorted(p for p, d in gold.items() if len(d) >= 8)
random.Random(a.seed).shuffle(paths)
paths = paths[: a.n]


def run(p):
    items, log, _ = vlm.read_labels(llm.load_image(abspath(p)), p)
    return p, items, log


t0 = time.time()
out = {}
with cf.ThreadPoolExecutor(24) as ex:
    for p, items, log in ex.map(lambda p: contextvars.copy_context().run(run, p), paths):
        out[p] = (items, log)
print(f"{len(out)} drawings in {time.time() - t0:.0f}s")
dump = Path("/home/fangy4/work/projects/junction-shared/artifacts/W3/calib") / f"labels-{a.split}{a.n}.jsonl"
with open(dump, "w") as fh:
    for p, (items, log) in out.items():
        fh.write(json.dumps({"path": p, "gold": gold[p], "notes": log.notes, "tok": [log.tokens_in, log.tokens_out],
                             "s": round(log.seconds, 1),
                             "items": [(i.text, i.cls, round(i.x), round(i.y)) for i in items]}) + "\n")

S = collections.defaultdict(collections.Counter)
for p, (items, log) in out.items():
    g = gold[p]
    looped = any(n.startswith("LOOP") for n in log.notes)
    n = collections.Counter(i.cls for i in items if i.cls)
    tc = next((type_code(i.text) for i in items if type_code(i.text)), None)
    P = lambda c: prior[c][0]
    for c in ROOM_CLASSES:
        if c not in g:
            continue
        k = n[c]
        implied = (max(0, (tc["rooms"] or 1) - 1) if c == "bedroom" else int(c in tc["classes"])) if tc else 0
        preds = {"prior": P(c), "labels": k, "max1": max(1, k), "labels|prior0": k or P(c),
                 "labels_code": k or implied}
        if looped:
            preds = {m: P(c) for m in preds}
        S[c]["n"] += 1
        for m, v in preds.items():
            S[c][m] += v == g[c]
    wc, bath, kit = n["wc_room"], max(1, n["bathroom"]), max(1, n["kitchen"])
    fx = {"wc_seat": {"prior": P("wc_seat"), "max(1,wc)": max(1, wc), "wc+1": wc + 1,
                      "wc+(bath if wc==0)": wc + (bath if wc == 0 else 0), "wc+bath": wc + bath},
          "sink": {"prior": P("sink"), "kit+bath": kit + bath, "kit+bath+wc": kit + bath + wc},
          "shower_bath": {"prior": P("shower_bath"), "bath": bath}}
    for c, preds in fx.items():
        if c in g:
            if looped:
                preds = {m: P(c) for m in preds}
            S[c]["n"] += 1
            for m, v in preds.items():
                S[c][m] += v == g[c]
for c, s in S.items():
    print(f"{c:12s} n={s['n']:3d} " + "  ".join(f"{m}={v / s['n']:.0%}" for m, v in s.items() if m != "n"))
