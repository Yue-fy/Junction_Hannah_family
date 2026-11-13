"""Count cubicasa symbols from cached CC5K segmentation maps (infer.py) and score them against the gold answers
and the per-template train prior, on leak-safe drawings only (original CC5K val = tune, test = report).

count(class) = number of 8-connected components of (icons == class) with area >= min_frac * H * W
(optionally after a morphological opening with a k×k kernel to split thin bridges).
One gold per (drawing, template): EN and FI twins have the same answer.

Run: $JUNCTION_VENV/bin/python -I count.py --tune val --report test [--tta]
"""
import argparse
import collections
import json
import math
import os
import re

import cv2
import numpy as np

SHARED = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")
DATA = os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")
SEG = os.path.join(SHARED, "artifacts", "R1", "cc5k_seg")
SPLITS = os.path.join(SHARED, "artifacts", "R1", "cc5k_split")
TEMPLATES = {
    "windows": r"How many windows are shown|Kuinka monta ikkunaa",
    "doors": r"How many doors are shown|Kuinka monta ovea",
    "wc_seats": r"How many toilet bowls|WC-istuinta",
    "sinks": r"How many sinks and wash basins|pesu- ja tiskiallasta",
    "shower_bath": r"How many showers and bathtubs|suihkua ja kylpyammetta",
}
CLS = {"windows": [1], "doors": [2], "wc_seats": [5], "sinks": [6], "shower_bath": [9]}
MIN_FRAC = [0, 1e-5, 2e-5, 5e-5, 1e-4, 2e-4, 3e-4, 5e-4, 8e-4, 1.2e-3]
KERNELS = [0, 3, 5]


def tpl(q):
    for k, rx in TEMPLATES.items():
        if re.search(rx, q):
            return k


def gold_table():
    g = collections.defaultdict(dict)
    for line in open(os.path.join(DATA, "questions.jsonl")):
        d = json.loads(line)
        if d["path"].startswith("data/cubicasa5k/"):
            t = tpl(d["question"])
            if t:
                g[os.path.basename(d["path"])[:-4]][t] = int(d["answer"])
    return g


def train_prior(gold):
    tr = {os.path.basename(json.loads(l)["path"])[:-4] for l in open(os.path.join(SHARED, "results", "splits", "train.jsonl"))}
    c = collections.defaultdict(collections.Counter)
    for st, d in gold.items():
        if st in tr:
            for t, v in d.items():
                c[t][v] += 1
    return {t: c[t].most_common(1)[0][0] for t in c}


def components(mask, min_area, k):
    m = mask.astype(np.uint8)
    if k:
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(m, connectivity=8)
    keep = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= min_area]
    return [(tuple(int(v) for v in stats[i, :4]), tuple(float(v) for v in cent[i])) for i in keep]


def counts(npz, t, min_frac, k):
    icons = npz["icons"]
    H, W = icons.shape
    return sum(len(components(icons == c, max(1, min_frac * H * W), k)) for c in CLS[t])


def load(stems, tta, scale=1.0):
    out = {}
    tag = ("tta_" if tta else "") + (f"s{scale:g}_" if scale != 1 else "")
    for st in stems:
        p = os.path.join(SEG, tag + st + ".npz")
        if os.path.exists(p):
            z = np.load(p)
            out[st] = {"icons": z["icons"]}
    return out


def stems_of(split):
    return [l.strip() for l in open(os.path.join(SPLITS, f"ours_in_original_{split}.txt")) if l.strip()]


def score(segs, gold, t, mf, k):
    hit = n = 0
    ratios = []
    for st, z in segs.items():
        if t in gold.get(st, {}):
            pred, g = counts(z, t, mf, k), gold[st][t]
            hit += pred == g
            n += 1
            if g:
                ratios.append(pred / g)
    return hit, n, (float(np.median(ratios)) if ratios else math.nan)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tune", default="val")
    ap.add_argument("--report", default="test")
    ap.add_argument("--tta", action="store_true")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--limit", type=int, default=0, help="first N drawings per list (quick checks)")
    a = ap.parse_args()
    gold = gold_table()
    prior = train_prior(gold)
    lim = (lambda L: L[: a.limit]) if a.limit else (lambda L: L)
    tune = load(lim(stems_of(a.tune)), a.tta, a.scale)
    rep = load(lim(stems_of(a.report)), a.tta, a.scale)
    print(f"drawings with seg: tune={len(tune)} report={len(rep)}; prior={prior}")
    result = {}
    for t in TEMPLATES:
        best = None
        for mf in MIN_FRAC:
            for k in KERNELS:
                h, n, r = score(tune, gold, t, mf, k)
                if n and (best is None or h > best[0]):
                    best = (h, n, r, mf, k)
        if not best:
            continue
        h, n, r, mf, k = best
        ph = sum(gold[s][t] == prior[t] for s in tune if t in gold.get(s, {}))
        rh, rn, rr = score(rep, gold, t, mf, k)
        rph = sum(gold[s][t] == prior[t] for s in rep if t in gold.get(s, {}))
        result[t] = dict(min_frac=mf, kernel=k, tune_acc=h / n, tune_prior=ph / n, tune_n=n, tune_ratio=r,
                         report_acc=rh / rn if rn else None, report_prior=rph / rn if rn else None,
                         report_n=rn, report_ratio=rr)
        print(f"{t:12s} tune {h}/{n}={h / n:.1%} (prior {ph / n:.1%}, med pred/gold {r:.2f}) min_frac={mf} k={k}"
              f" | report {rh}/{rn}={rh / max(rn, 1):.1%} (prior {rph / max(rn, 1):.1%}, ratio {rr:.2f})")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
