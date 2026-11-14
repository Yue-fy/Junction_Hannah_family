"""Measure the drawn dimension line of a printed dimension string ('187'-0"') on a raster drawing.

A printed dimension is the drawing's own answer to a length question; measuring the line it labels with the graphic
scale bar (scalebar.py) cross-checks both the reading and the scale: printed 187'-0" vs drawn 186.6 ft ✓.
Or, with no bar, the printed dimension calibrates px per unit for the rest of the drawing.

    dim_line(img, text_box) -> {x0, x1, y, px, ticks, mode} or None   (horizontal text: horizontal line near it;
                                                                       vertical text: vertical line, transposed)
    cross_check(path, text_box, value_units, bar) -> (measured_units, rel_diff, Evidence) or None

The line is the longest dark run, across the text's centre, in rows within ~2 text heights of the box; the text may
sit in a gap of the line (bridged). Ticks/extension lines along the run (ink reaching >= 0.6 text heights above or
below the line) bound the segment that holds the text (chained dimensions: 10'-0" | 12'-6" | ...).
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from stoa.contract import Evidence

from . import textlayer as T


def _dark(img: Image.Image, thr: int = 150) -> np.ndarray:
    return np.asarray(img.convert("L")) < thr


def _runs_through(row: np.ndarray, xc: int, gap: int) -> tuple[int, int] | None:
    """Longest dark run (gaps <= `gap` bridged) that contains column xc, or None if xc is not on one."""
    n = len(row)
    if not row[max(0, xc - gap):min(n, xc + gap + 1)].any():
        return None
    # walk left / right from xc, allowing small gaps
    x0 = x = xc
    miss = 0
    while x > 0:
        x -= 1
        if row[x]:
            x0, miss = x, 0
        else:
            miss += 1
            if miss > gap:
                break
    x1 = x = xc
    miss = 0
    while x < n - 1:
        x += 1
        if row[x]:
            x1, miss = x, 0
        else:
            miss += 1
            if miss > gap:
                break
    return x0, x1


def _horizontal(d: np.ndarray, box: list[float]) -> dict | None:
    H, W = d.shape
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    h = max(6, y1 - y0)
    w = max(1, x1 - x0)
    xc = (x0 + x1) // 2
    gap = max(3, h // 3)
    best = None
    for y in range(max(0, y0 - 2 * h), min(H, y1 + 2 * h + 1)):
        row = d[y].copy()
        if y0 - 2 <= y <= y1 + 2:  # the text may sit in a gap of the line: bridge its box on rows it covers
            row[max(0, x0 - gap):min(W, x1 + gap)] = True
        r = _runs_through(row, xc, gap)
        if r is None:
            continue
        length = r[1] - r[0]
        if length < 3 * w:
            continue
        dist = 0 if y0 <= y <= y1 else min(abs(y - y0), abs(y - y1))
        # rows inside the text box are trusted only when the line continues on both sides of the text
        if y0 - 2 <= y <= y1 + 2 and not (d[y, max(0, x0 - 4 * gap):max(1, x0 - gap)].mean() > 0.5 and
                                          d[y, min(W - 1, x1 + gap):min(W, x1 + 4 * gap)].mean() > 0.5):
            continue
        key = (length, -dist)
        if best is None or key > best[0]:
            best = (key, y, r)
    if best is None:
        return None
    _, y, (a, b) = best
    # ticks / extension lines: columns on the run where ink reaches >= 0.6 h above or below the line
    reach = max(4, int(0.6 * h))
    ticks = []
    for x in range(a, b + 1):
        up = d[max(0, y - reach):max(0, y - 2), max(0, x - 1):x + 2].any(axis=1).sum()
        dn = d[min(H, y + 3):min(H, y + reach + 1), max(0, x - 1):x + 2].any(axis=1).sum()
        if (up >= reach - 3 or dn >= reach - 3) and not (x0 - gap <= x <= x1 + gap):
            ticks.append(x)
    # group adjacent tick columns
    groups: list[list[int]] = []
    for x in ticks:
        if groups and x - groups[-1][-1] <= 3:
            groups[-1].append(x)
        else:
            groups.append([x])
    tk = [int(round(sum(g) / len(g))) for g in groups]
    left = [t for t in tk if t < xc]
    right = [t for t in tk if t > xc]
    seg = (left[-1] if left else a, right[0] if right else b)
    return {"x0": a, "x1": b, "y": y, "px": float(b - a), "ticks": tk, "seg": seg, "seg_px": float(seg[1] - seg[0])}


def dim_line(img: Image.Image | np.ndarray, box: list[float]) -> dict | None:
    """The dimension line labelled by the text in `box` (image px). Vertical text -> the image is transposed."""
    d = img if isinstance(img, np.ndarray) else _dark(img)
    if (box[3] - box[1]) > 1.5 * (box[2] - box[0]):  # rotated text: a vertical dimension
        r = _horizontal(d.T, [box[1], box[0], box[3], box[2]])
        if r:
            r["vertical"] = True
        return r
    r = _horizontal(d, box)
    if r:
        r["vertical"] = False
    return r


def evidence(path: str, r: dict, note: str) -> Evidence:
    if r.get("vertical"):
        bb = [r["y"] - 3, r["seg"][0], r["y"] + 3, r["seg"][1]]
    else:
        bb = [r["seg"][0], r["y"] - 3, r["seg"][1], r["y"] + 3]
    return Evidence(file=path, page=0, bbox=[float(v) for v in bb], bbox_space="image_px", note=note)
