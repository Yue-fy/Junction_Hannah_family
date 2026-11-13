"""Offline: predict fixture counts (WC seats, sinks, showers+baths) from room labels (R1 cached v2 outputs).
Rooms imply fixtures: every WC room has a toilet, most bathrooms have a basin (+ often a toilet), a kitchen has a
sink. Scored on TRAIN drawings (dev printed for information only)."""
import collections, json
from pathlib import Path
from PIL import Image
from stoa.eval.splits import load_split
from stoa.data import abspath
from stoa.solvers.raster import class_prior
from stoa.solvers.raster.classes import question_class
from stoa.solvers.raster.vlm import R1_CACHE, parse_labels

prior = class_prior()
for split in ("train", "dev"):
    gold = collections.defaultdict(dict)
    for q in load_split(split):
        if q.source == "cubicasa5k":
            c = question_class(q.question)
            if c:
                gold[q.path][c] = q.answer
    S = collections.defaultdict(collections.Counter)
    for p, g in gold.items():
        f = R1_CACHE / (Path(p).name + ".labels.v2.json")
        if not f.exists():
            continue
        w, h = Image.open(abspath(p)).size
        items, looped = parse_labels(json.loads(f.read_text())["text"], w, h)
        if looped:
            continue
        n = collections.Counter(i.cls for i in items if i.cls)
        wc, bath, kit, sau = n["wc_room"], max(1, n["bathroom"]), max(1, n["kitchen"]), n["sauna"]
        cands = {
            "wc_seat": {"prior": prior["wc_seat"][0], "wc+1": wc + 1, "max(1,wc)": max(1, wc), "wc+bath": wc + bath,
                        "wc+(bath if wc==0)": wc + (bath if wc == 0 else 0)},
            "sink": {"prior": prior["sink"][0], "kit+bath": kit + bath, "kit+bath+wc": kit + bath + wc,
                     "1+bath": 1 + bath},
            "shower_bath": {"prior": prior["shower_bath"][0], "bath": bath, "bath+sauna": bath + (1 if sau else 0) * 0},
        }
        for c, preds in cands.items():
            if c not in g:
                continue
            S[c]["n"] += 1
            for m, v in preds.items():
                S[c][m] += (v == g[c])
    print(f"== {split} ==")
    for c, s in S.items():
        print(c, s["n"], {m: f"{v / s['n']:.0%}" for m, v in s.items() if m != "n"})
