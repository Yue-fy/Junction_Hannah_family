"""Offline: label-count policies per room class on R1's cached v2 label outputs, scored on TRAIN (and dev, for
information only; choices are made on train). No GPU.
    PYTHONPATH=$PWD $JUNCTION_VENV/bin/python experiments/w3/label_policy.py
"""
import collections, json, sys
from pathlib import Path
from PIL import Image
from stoa.eval.splits import load_split
from stoa.data import abspath
from stoa.solvers.raster import class_prior
from stoa.solvers.raster.classes import ROOM_CLASSES, question_class, label_class, label_classes, type_code
from stoa.solvers.raster.vlm import R1_CACHE, parse_labels

prior = class_prior()
for split in ("train", "dev"):
    gold = collections.defaultdict(dict)
    for q in load_split(split):
        if q.source == "cubicasa5k":
            c = question_class(q.question)
            if c in ROOM_CLASSES:
                gold[q.path][c] = q.answer
    S = collections.defaultdict(collections.Counter)
    for p, g in gold.items():
        f = R1_CACHE / (Path(p).name + ".labels.v2.json")
        if not f.exists():
            continue
        text = json.loads(f.read_text())["text"]
        w, h = Image.open(abspath(p)).size
        items, looped = parse_labels(text, w, h)
        mine = collections.Counter(i.cls for i in items if i.cls)
        r1 = collections.Counter(c for i in items for c in label_classes(i.text))
        codes = [type_code(i.text) for i in items if type_code(i.text)]
        tc = codes[0] if codes else None
        for c, ans in g.items():
            pr = prior[c][0]
            k = mine.get(c, 0)
            preds = {
                "prior": pr,
                "r1_labels": pr if looped else r1.get(c, 0),
                "labels": pr if looped else k,
                "max1": pr if looped else max(1, k),
                "labels|prior0": pr if looped else (k if k else pr),
            }
            if tc:
                if c == "bedroom":
                    preds["labels|code"] = pr if looped else (k if k else max(0, tc["rooms"] - 1))
                else:
                    preds["labels|code"] = pr if looped else (k if k else int(c in tc["classes"]))
            else:
                preds["labels|code"] = preds["labels"]
            S[c]["n"] += 1
            S[c]["loop"] += looped
            S[c]["code"] += bool(tc)
            for m, v in preds.items():
                S[c][m] += (v == ans)
    ms = ["prior", "r1_labels", "labels", "max1", "labels|prior0", "labels|code"]
    print(f"\n== {split} ==\n{'class':10s} {'n':>4s} {'loop':>4s} {'code':>4s} " + " ".join(f"{m:>13s}" for m in ms))
    tot = collections.Counter()
    for c in ROOM_CLASSES:
        s = S[c]; tot.update(s)
        if s["n"]:
            print(f"{c:10s} {s['n']:4d} {s['loop']:4d} {s['code']:4d} " + " ".join(f"{s[m]/s['n']:13.1%}" for m in ms))
