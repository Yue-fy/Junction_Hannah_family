"""Classical CV door counter for cubicasa raster plans: door = quarter-circle swing arc + leaf line.

Chamfer matching: thin-ink mask -> distance transform -> for each radius r and each of 8 door variants
(4 quadrants x leaf on either edge) the mean distance of the template points (filter2D). Low mean distance = the
arc and leaf are drawn there. Then NMS, a full-circle reject (other quadrants also drawn) and a radius-consistency
filter (all doors of one plan have similar widths).

    PYTHONPATH=$PWD $JUNCTION_VENV/bin/python experiments/w3/cv/doors.py viz data/cubicasa5k/high_quality_architectural-3127.png
    PYTHONPATH=$PWD $JUNCTION_VENV/bin/python experiments/w3/cv/doors.py eval --n 200
TRAIN only.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import math
import os
import random
import sys
import time
from pathlib import Path

import cv2
import numpy as np

SHARED = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
OUT = SHARED / "artifacts/W3/cv"


def ink_masks(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(ink, thin) uint8 0/1 masks. thin = ink minus thick strokes (walls, fills)."""
    _, ink = cv2.threshold(gray, 0, 1, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    thick = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((4, 4), np.uint8))
    thin = ink & (1 - cv2.dilate(thick, np.ones((3, 3), np.uint8)))
    return ink, thin


def _pts(k, pts):
    m = np.zeros((k, k), np.float32)
    for x, y in pts:
        m[int(round(y)), int(round(x))] = 1
    return m / max(1.0, m.sum())


def templates(r: int):
    """8 door variants for radius r: (name, arc, leaf, inner, outer, q). Kernels are (2r+3)^2 with the hinge at the
    centre; quadrant q spans angles [q*90, q*90+90] deg (image y down). inner = the swing area (must be empty),
    outer = a band just outside the arc (mostly empty)."""
    R = int(1.45 * r) + 2
    k = 2 * R + 1
    c = R
    out = []
    n_arc = max(8, int(math.pi * r / 2))
    for q in range(4):
        a0 = q * math.pi / 2
        arc = _pts(k, [(c + r * math.cos(a), c + r * math.sin(a))
                       for a in (a0 + (i + 0.5) / n_arc * math.pi / 2 for i in range(n_arc))])
        inner = _pts(k, [(c + rr * math.cos(a), c + rr * math.sin(a))
                         for rr in np.linspace(0.3 * r, 0.8 * r, max(3, r // 3))
                         for a in np.linspace(a0 + 0.3, a0 + math.pi / 2 - 0.3, max(4, r // 2))])
        outer = _pts(k, [(c + rr * math.cos(a), c + rr * math.sin(a))
                         for rr in (1.2 * r, 1.35 * r)
                         for a in np.linspace(a0 + 0.2, a0 + math.pi / 2 - 0.2, max(4, r // 2))])
        for e, ang in enumerate((a0, a0 + math.pi / 2)):
            leaf = _pts(k, [(c + t * r * math.cos(ang), c + t * r * math.sin(ang))
                            for t in np.linspace(0.15, 1.0, max(6, r))])
            out.append((f"q{q}e{e}", arc, leaf, inner, outer, q))
    return out


def detect(gray: np.ndarray, rmin: int | None = None, rmax: int | None = None, thr: float = 1.0, leaf_thr: float = 1.3,
           inner_max: float = 0.35, outer_max: float = 0.2):
    """Return list of dicts {x,y (hinge), r, q, score}. Radius range defaults to 2.2-8% of the longer image side."""
    m = max(gray.shape)
    rmin = rmin or max(8, int(0.022 * m))
    rmax = rmax or max(rmin + 4, int(0.08 * m))
    ink, thin = ink_masks(gray)
    dt = cv2.distanceTransform((1 - thin).astype(np.uint8), cv2.DIST_L2, 3).astype(np.float32)
    dt = np.minimum(dt, 6.0)
    P = int(1.45 * rmax) + 4  # pad with 'far from ink' so the image border never matches
    dt = cv2.copyMakeBorder(dt, P, P, P, P, cv2.BORDER_CONSTANT, value=6.0)
    inkf = cv2.copyMakeBorder(ink.astype(np.float32), P, P, P, P, cv2.BORDER_CONSTANT, value=0.0)
    H, W = gray.shape
    cands = []
    radii = sorted({int(round(rmin * 1.1 ** i)) for i in range(60) if rmin * 1.1 ** i <= rmax})
    for r in radii:
        tps = templates(r)
        arc_s, inner_s, outer_s = {}, {}, {}
        for name, arc, leaf, inner, outer, q in tps:
            if q not in arc_s:
                arc_s[q] = cv2.filter2D(dt, -1, arc, borderType=cv2.BORDER_CONSTANT)
                inner_s[q] = cv2.filter2D(inkf, -1, inner, borderType=cv2.BORDER_CONSTANT)
                outer_s[q] = cv2.filter2D(inkf, -1, outer, borderType=cv2.BORDER_CONSTANT)
        for name, arc, leaf, inner, outer, q in tps:
            ok = (arc_s[q] < thr) & (inner_s[q] < inner_max) & (outer_s[q] < outer_max)
            if not ok.any():
                continue
            s_leaf = cv2.filter2D(dt, -1, leaf, borderType=cv2.BORDER_CONSTANT)
            # closed circle (toilet, stove, table): the opposite and a side quadrant are drawn too
            circ = (arc_s[(q + 2) % 4] < thr * 1.5) & (np.minimum(arc_s[(q + 1) % 4], arc_s[(q + 3) % 4]) < thr * 1.5)
            ok &= (s_leaf < leaf_thr) & ~circ
            if not ok.any():
                continue
            comb = arc_s[q] + s_leaf
            win = max(3, r // 2) | 1
            locmin = comb <= cv2.erode(comb, np.ones((win, win), np.uint8))
            ys, xs = np.nonzero(ok & locmin)
            for y, x in zip(ys - P, xs - P):
                if not (0 <= y < H and 0 <= x < W):
                    continue
                cands.append(dict(x=int(x), y=int(y), r=r, q=q, e=name, score=float(comb[y + P, x + P]),
                                  inner=float(inner_s[q][y + P, x + P])))
    keep = cands
    # NMS by arc mid-point distance
    keep.sort(key=lambda c: c["score"])
    final = []
    for c in keep:
        a = c["q"] * math.pi / 2 + math.pi / 4
        mx, my = c["x"] + c["r"] * math.cos(a) * 0.7, c["y"] + c["r"] * math.sin(a) * 0.7
        c["mx"], c["my"] = mx, my
        if all(math.hypot(mx - f["mx"], my - f["my"]) > 0.6 * max(c["r"], f["r"]) for f in final):
            final.append(c)
    return final


def consistent(dets, lo=0.65, hi=1.5):
    """Keep detections whose radius is near the plan's dominant door radius (weighted median)."""
    if len(dets) < 3:
        return dets
    rs = sorted(d["r"] for d in dets)
    med = rs[len(rs) // 2]
    return [d for d in dets if lo * med <= d["r"] <= hi * med]


def load_gray(path: str, scale: float = 1.0) -> np.ndarray:
    from stoa.data import abspath
    g = cv2.imread(str(abspath(path)), cv2.IMREAD_GRAYSCALE)
    if scale != 1.0:
        g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return g


def viz(path: str, out: Path, **kw):
    g = load_gray(path)
    dets = consistent(detect(g, **kw))
    im = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
    for d in dets:
        a0 = d["q"] * 90
        cv2.ellipse(im, (d["x"], d["y"]), (d["r"], d["r"]), 0, a0, a0 + 90, (0, 0, 255), 2)
        cv2.circle(im, (d["x"], d["y"]), 3, (255, 0, 0), -1)
    cv2.imwrite(str(out), im)
    return dets


def gold_doors(split="train"):
    from stoa.eval.splits import load_split
    from stoa.solvers.raster.classes import question_class
    gold = {}
    for q in load_split(split):
        if q.source == "cubicasa5k" and q.question.lower().startswith("how") and question_class(q.question) == "door":
            gold[q.path] = float(q.answer)
    return gold


def _one(args):
    p, kw = args
    t0 = time.time()
    try:
        g = load_gray(p)
        f = min(1.0, 1000 / max(g.shape))
        if f < 1.0:
            g = cv2.resize(g, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        raw = detect(g, **kw)
        dets = consistent(raw)
        return dict(path=p, n=len(dets), n_raw=len(raw), s=round(time.time() - t0, 2), shape=list(g.shape),
                    raw=[(d["x"], d["y"], d["r"], d["q"], round(d["score"], 3), round(d["inner"], 3)) for d in raw])
    except Exception as e:  # noqa: BLE001
        return dict(path=p, err=repr(e))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["viz", "eval"])
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--tag", default="")
    ap.add_argument("--paths-from", default="", help="jsonl with a 'path' field (e.g. a calib file): use these drawings")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.mode == "viz":
        for p in a.paths:
            dets = viz(p, OUT / (Path(p).stem + "-doors.png"))
            print(p, len(dets), [(d["x"], d["y"], d["r"], d["q"], round(d["score"], 2)) for d in dets])
        return
    gold = gold_doors()
    paths = sorted(gold)
    random.Random(a.seed).shuffle(paths)
    if a.paths_from:
        want = {json.loads(l)["path"] for l in open(a.paths_from)}
        paths = [p for p in paths if p in want]
    paths = paths[: a.n]
    with cf.ProcessPoolExecutor(a.workers) as ex:
        rows = list(ex.map(_one, [(p, {}) for p in paths]))
    out = OUT / f"doors-{time.strftime('%H%M%S')}{a.tag}.jsonl"
    with open(out, "w") as f:
        for r in rows:
            r["gold"] = gold[r["path"]]
            f.write(json.dumps(r) + "\n")
    ok = [r for r in rows if "err" not in r]
    prior = collections.Counter(gold[p] for p in paths).most_common(1)[0][0]
    ex_ = sum(r["n"] == r["gold"] for r in ok) / len(ok)
    w1 = sum(abs(r["n"] - r["gold"]) <= 1 for r in ok) / len(ok)
    pr = sum(prior == r["gold"] for r in ok) / len(ok)
    ratio = np.median([r["n"] / max(1, r["gold"]) for r in ok])
    print(f"{len(ok)} drawings ({len(rows)-len(ok)} errors): exact {ex_:.1%}  within1 {w1:.1%}  prior({prior}) {pr:.1%}  "
          f"median pred/gold {ratio:.2f}  -> {out}")


if __name__ == "__main__":
    main()
