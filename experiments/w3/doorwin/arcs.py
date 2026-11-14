"""Door swing arcs on a raster plan by matched filtering: quarter rings of radius 0.55-1.35 m (from px_per_m) in 4
quadrants; score = ink on the ring - ink just inside/outside it. Evaluated against DXF arcs mapped to PNG px.
Usage: python experiments/w3/doorwin/arcs.py --gold $JUNCTION_SHARED/artifacts/W3/doorwin_gold_train.jsonl --n 20
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
import cv2

D = os.environ["STOA_DATA"]
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def ring_kernel(r: float, quad: int, width: float = 1.0, margin_deg: float = 10.0):
    """(on, off) kernels: on = pixels within `width` of radius r in quadrant `quad` (angles quad*90..quad*90+90, y
    down, minus a margin at both ends); off = rings at r +- 3 px over the same angles."""
    R = int(math.ceil(r + 5))
    yy, xx = np.mgrid[-R:R + 1, -R:R + 1].astype(float)
    rr = np.hypot(xx, yy)
    ang = (np.degrees(np.arctan2(yy, xx)) + 360) % 360
    a0, a1 = quad * 90 + margin_deg, quad * 90 + 90 - margin_deg
    sector = (ang >= a0) & (ang <= a1)
    on = (np.abs(rr - r) <= width) & sector
    off = ((np.abs(rr - (r - 3.5)) <= 0.8) | (np.abs(rr - (r + 3.5)) <= 0.8)) & sector
    return on.astype(np.float32), off.astype(np.float32)


def detect(png: str, px_per_m: float, r_m=(0.55, 1.35), work_ppm: float = 60.0, thr: float = 0.55,
           ink_lvl: int = 170, legend_frac: float = 0.0):
    im = Image.open(png).convert("L")
    k = min(1.0, work_ppm / px_per_m)
    if k < 1.0:
        im = im.resize((round(im.size[0] * k), round(im.size[1] * k)), Image.LANCZOS)
    g = np.asarray(im)
    ink = (g < ink_lvl).astype(np.float32)
    ppm = px_per_m * k
    radii = np.arange(r_m[0] * ppm, r_m[1] * ppm + 0.01, 1.0)
    best = np.full(ink.shape, -1.0, np.float32)
    best_r = np.zeros(ink.shape, np.float32)
    best_q = np.zeros(ink.shape, np.int8)
    # FFT once
    for r in radii:
        for q in range(4):
            on, off = ring_kernel(r, q)
            kern = on / on.sum() - off / off.sum()  # filter2D correlates (no flip)
            s = cv2.filter2D(ink, cv2.CV_32F, kern, borderType=cv2.BORDER_CONSTANT)
            m = s > best
            best[m], best_r[m], best_q[m] = s[m], r, q
    sz = int(max(5, 0.35 * ppm)) | 1
    peaks = (best >= cv2.dilate(best, np.ones((sz, sz), np.uint8))) & (best >= thr)
    ys, xs = np.nonzero(peaks)
    dets = [{"c": [float(x / k), float(y / k)], "r_px": float(best_r[y, x] / k), "q": int(best_q[y, x]),
             "score": float(best[y, x])} for y, x in zip(ys, xs)]
    # NMS: same quadrant & centre within 0.3 m
    dets.sort(key=lambda d: -d["score"])
    keep = []
    for d in dets:
        if all(math.dist(d["c"], e["c"]) > 0.3 * px_per_m for e in keep):
            keep.append(d)
    return keep


def match(dets, arcs, px_per_m, tol_m=0.2):
    used = set()
    tp = 0
    uniq = []
    for a in arcs:  # dedupe gold
        if all(math.dist(a["c"], b["c"]) > 2 or abs(a["r_px"] - b["r_px"]) > 2 or a["a"] != b["a"] for b in uniq):
            uniq.append(a)
    for d in dets:
        cand = [i for i, a in enumerate(uniq) if i not in used and math.dist(d["c"], a["c"]) < tol_m * px_per_m]
        if cand:
            used.add(min(cand, key=lambda i: math.dist(d["c"], uniq[i]["c"])))
            tp += 1
    return tp, len(dets), len(uniq)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--skip", type=int, default=0)
    ap.add_argument("--thr", type=float, default=0.55)
    ap.add_argument("--ink", type=int, default=170)
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.gold)][a.skip: a.skip + a.n]
    T = P = G = 0
    for r in rows:
        t0 = time.time()
        from stoa.solvers.raster import doorarcs as DA
        dets = DA.detect(os.path.join(D, r["png"]), r["px_per_m"], thr=a.thr, ink_lvl=a.ink)
        # drop legend (below the lowest gold object) only for the diagnostic
        tp, p, g = match(dets, r["arcs"], r["px_per_m"])
        T, P, G = T + tp, P + p, G + g
        print(f"{r['stem']:34s} ppm {r['px_per_m']:5.1f} gold_leaves {len(r['doors']):3d} uniq_arcs {g:3d} det {p:3d} "
              f"tp {tp:3d} ({time.time() - t0:.1f}s)", flush=True)
    print(f"TOTAL tp {T} det {P} gold {G}: recall {T / max(G, 1):.3f} precision {T / max(P, 1):.3f}")


if __name__ == "__main__":
    main()
