"""Door swing arcs on a raster floor plan (matched filter), for door counts on plans without a vector twin.

A door is drawn as a leaf plus a quarter arc of radius = leaf width (0.35-1.35 m) centred on the hinge. With the
drawing's scale (px per metre, scalebar.py) the arc radius range in pixels is known, so a quarter-ring template per
radius and quadrant, scored as (ink on the ring) - (ink on rings 3.5 px inside and outside), finds arcs and ignores
straight lines and filled/hatched areas. Rejected: full circles (north arrow, round fixtures: >= 3 quadrants inked)
and anything below the legend / title-block rule (a horizontal line across most of the sheet in its lower half).
Measured on TRAIN Swiss floors against DXF arcs mapped to PNG px (experiments/w3/doorwin/arcs.py).

detect(png, px_per_m) -> [{"c": [x, y], "r_px", "q", "score", "box"}] in image px.
"""
from __future__ import annotations

import functools
import math

import numpy as np
from PIL import Image

CONF = 0.15  # exact on few TRAIN floors (count_rules.py); an estimate with per-door evidence
DUP_RED = 5  # red (apartment boundary) pixels around a door -> the source data counts it once per side
R_M = (0.55, 1.35)  # 0.35: +fixtures (toilets, basins) as FPs, precision 0.89 -> 0.58; DXF radii < 0.55 m are 3%
THR = 0.55
INK = 210


@functools.lru_cache(maxsize=512)
def ring_kernel(r: float, quad: int, width: float = 1.0, margin_deg: float = 10.0):
    """(on, off) masks: on = pixels within `width` of radius r in quadrant `quad` (image angles quad*90..+90, y
    down, minus a margin at both ends); off = rings at r -+ 3.5 px over the same angles."""
    R = int(math.ceil(r + 5))
    yy, xx = np.mgrid[-R:R + 1, -R:R + 1].astype(float)
    rr = np.hypot(xx, yy)
    ang = (np.degrees(np.arctan2(yy, xx)) + 360) % 360
    sector = (ang >= quad * 90 + margin_deg) & (ang <= quad * 90 + 90 - margin_deg)
    on = (np.abs(rr - r) <= width) & sector
    off = ((np.abs(rr - (r - 3.5)) <= 0.8) | (np.abs(rr - (r + 3.5)) <= 0.8)) & sector
    return on.astype(np.float32), off.astype(np.float32)


def _score_at(ink: np.ndarray, x: int, y: int, r: float, q: int) -> float:
    on, off = ring_kernel(round(r * 2) / 2, q)
    R = on.shape[0] // 2
    H, W = ink.shape
    if x - R < 0 or y - R < 0 or x + R + 1 > W or y + R + 1 > H:
        return 0.0
    patch = ink[y - R:y + R + 1, x - R:x + R + 1]
    return float((patch * on).sum() / on.sum() - (patch * off).sum() / off.sum())


def legend_cut(ink: np.ndarray) -> int:
    """y of the topmost horizontal rule across >= 70% of the width in the lower half (Swiss legend / title block);
    the image height when there is none."""
    H, W = ink.shape
    rows = ink[H // 2:].mean(axis=1)
    ys = np.nonzero(rows >= 0.7)[0]
    return int(H // 2 + ys[0]) if len(ys) else H


def detect(png: str, px_per_m: float, r_m: tuple[float, float] = R_M, thr: float = THR, ink_lvl: int = INK,
           max_side: int = 3600) -> list[dict]:
    import cv2

    im = Image.open(png).convert("L")
    k = min(1.0, max_side / max(im.size))
    if px_per_m * k < 45:  # 1:200 sheets (29.5 px/m): the filters are tuned at ~59 px/m; upscale (331 dets -> ?)
        k = min(59.0 / px_per_m, 2 * max_side / max(im.size))
    if k != 1.0:  # never below ~2 px line spacing: arcs vanish when downscaled (half-res recall 7% vs 91% full)
        im = im.resize((round(im.size[0] * k), round(im.size[1] * k)), Image.BICUBIC if k > 1 else Image.LANCZOS)
    g = np.asarray(im)
    ink = (g < ink_lvl).astype(np.float32)
    ppm = px_per_m * k
    cut = legend_cut(ink)
    work = ink[:cut]
    # search from 0.1 m below the smallest door: a straight wall / window line scores higher as the ring shrinks, so
    # its best radius is the search minimum; a real arc peaks at its own radius (1:200 FPs all sat at r_min)
    radii, r = [], max(6.0, (r_m[0] - 0.1) * ppm)
    while r <= r_m[1] * ppm + 0.01:  # step <= 2 px: the +-1 px ring still covers an arc between two radii
        radii.append(r)
        r += max(1.0, min(2.0, 0.04 * r))
    best = np.full(work.shape, -1.0, np.float32)
    best_r = np.zeros(work.shape, np.float32)
    best_q = np.zeros(work.shape, np.int8)
    for r in radii:
        for q in range(4):
            on, off = ring_kernel(float(r), q)
            kern = on / on.sum() - off / off.sum()  # filter2D correlates (no flip needed)
            s = cv2.filter2D(work, cv2.CV_32F, kern, borderType=cv2.BORDER_CONSTANT)
            m = s > best
            best[m], best_r[m], best_q[m] = s[m], r, q
    sz = int(max(5, 0.35 * ppm)) | 1
    peaks = (best >= cv2.dilate(best, np.ones((sz, sz), np.uint8))) & (best >= thr)
    ys, xs = np.nonzero(peaks)
    dets = []
    for y, x in zip(ys, xs):
        r, q = float(best_r[y, x]), int(best_q[y, x])
        if r < r_m[0] * ppm - 0.01:
            continue
        quads = [_score_at(ink, int(x), int(y), r, j) for j in range(4)]
        if sum(s >= 0.5 * thr for s in quads) >= 3:
            continue  # a full circle: north arrow, round table, fixture
        dets.append({"c": [float(x / k), float(y / k)], "r_px": r / k, "q": q, "score": float(best[y, x])})
    dets.sort(key=lambda d: -d["score"])
    keep: list[dict] = []
    for d in dets:
        if all(math.dist(d["c"], e["c"]) > 0.3 * px_per_m for e in keep):
            keep.append(d)
    for d in keep:  # the swept quarter disc, in image px
        (x, y), r, q = d["c"], d["r_px"], d["q"]
        sx, sy = (1 if q in (0, 3) else -1), (1 if q in (0, 1) else -1)
        xs_ = sorted([x, x + sx * r])
        ys_ = sorted([y, y + sy * r])
        d["box"] = [round(xs_[0], 1), round(ys_[0], 1), round(xs_[1], 1), round(ys_[1], 1)]
        d["r_m"] = round(r / px_per_m, 2)
    return keep


def red_near(rgb: np.ndarray, d: dict, px_per_m: float) -> int:
    """Pixels of the red dash-dot apartment boundary (176, 58, 46) within the door's swept quarter disc + 0.1 m."""
    bx = d["box"]
    x, y = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
    rad = d["r_px"] / 2 + 0.1 * px_per_m
    H, W = rgb.shape[:2]
    x0, x1, y0, y1 = max(0, int(x - rad)), min(W, int(x + rad) + 1), max(0, int(y - rad)), min(H, int(y + rad) + 1)
    p = rgb[y0:y1, x0:x1].astype(int)
    m = (abs(p[..., 0] - 176) < 40) & (abs(p[..., 1] - 58) < 40) & (abs(p[..., 2] - 46) < 40)
    return int(m.sum())
