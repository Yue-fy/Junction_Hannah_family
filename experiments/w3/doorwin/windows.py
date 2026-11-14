"""Window symbols on Swiss-style PNG floor plans: a wall band whose fill is replaced by 4 equally spaced parallel
lines (outer 2 = the wall faces, dark; inner 2 = the glass, grey ~59; white between). Profile scan per column
(horizontal walls) and per row (vertical walls), then runs of matching columns = one window (a mullion breaks the
run). Evaluated against the DXF window items mapped to PNG px (gold.py -> artifacts/W3/doorwin_gold_train.jsonl).

Usage: python experiments/w3/doorwin/windows.py [--n 60] [--show STEM]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

WHITE = 200
DARK = 40          # a wall face line: min value < DARK
GREY = (41, 120)   # (unused since the ink-mass test)
LINE_MAX = 4       # px: a thin line crossed at up to ~60 degrees
INNER_MIN = 110    # ink mass of a glass line (grey 59 1-px line = 196; antialiased the same)
INNER_RATIO = 1.5  # the two glass lines carry similar ink
OUTER_K = 1.12     # a wall face (black 1-px = 255..275) carries more ink than a glass line (~197)
OUTER_MIN_V = 100  # a wall face reaches at least this dark somewhere
GOLD = "/home/fangy4/work/projects/junction-shared/artifacts/W3/doorwin_gold_train.jsonl"


def _runs(prof: np.ndarray):
    """Non-white runs along a 1-D profile: (start, end_exclusive, min value, ink mass = sum(255 - v))."""
    nw = prof < WHITE
    if not nw.any():
        return []
    d = np.diff(np.concatenate([[0], nw.astype(np.int8), [0]]))
    st, en = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
    inv = 255 - prof.astype(np.int32)
    return [(int(s), int(e), int(prof[s:e].min()), int(inv[s:e].sum())) for s, e in zip(st, en)]


def _hits(g: np.ndarray, smin: float, smax: float, ratio: float = 1.35):
    """For every column of g: (col, c0, c3) where the column crosses 4 thin lines with near-equal white gaps, the
    outer two (wall faces) carrying more ink than the inner two (glass, grey ~59). Ink mass rather than the min value:
    a tilted 1-px line is antialiased over 2 px (dark 64+173, grey 238+75), so its min says little."""
    out = []
    for x in range(g.shape[1]):
        rs = _runs(g[:, x])
        if len(rs) < 4:
            continue
        cen = [(r[0] + r[1] - 1) / 2 for r in rs]
        for i in range(len(rs) - 3):
            q = rs[i:i + 4]
            if any(r[1] - r[0] > LINE_MAX for r in q):
                continue
            m = [r[3] for r in q]
            if min(m[1], m[2]) < INNER_MIN or max(m[1], m[2]) > INNER_RATIO * min(m[1], m[2]):
                continue
            if min(m[0], m[3]) < OUTER_K * max(m[1], m[2]) or min(q[0][2], q[3][2]) > OUTER_MIN_V:
                continue
            gaps = [cen[i + 1] - cen[i], cen[i + 2] - cen[i + 1], cen[i + 3] - cen[i + 2]]
            if min(gaps) >= smin and max(gaps) <= smax and max(gaps) <= ratio * min(gaps):
                out.append((x, cen[i], cen[i + 3]))
    return out


def _segments(hits, min_len: int, tol: float = 1.5, max_gap: int = 1):
    """Group hits in adjacent columns at the same band position -> [(x0, x1, c0, c3)]."""
    hits = sorted(hits, key=lambda h: (round(h[1]), h[0]))
    open_: list[list] = []
    done = []
    by_x: dict[int, list] = {}
    for h in hits:
        by_x.setdefault(h[0], []).append(h)
    for x in sorted(by_x):
        nxt = []
        used = set()
        for seg in open_:
            if x - seg[1] > max_gap + 1:
                done.append(seg)
                continue
            m = None
            for j, h in enumerate(by_x[x]):
                if j not in used and abs(h[1] - seg[2]) <= tol and abs(h[2] - seg[3]) <= tol:
                    m = j
                    break
            if m is None:
                nxt.append(seg)
            else:
                used.add(m)
                seg[1] = x
                h = by_x[x][m]
                seg[2], seg[3] = h[1], h[2]  # follow a tilted wall
                seg[4], seg[5] = min(seg[4], h[1]), max(seg[5], h[2])
                nxt.append(seg)
        for j, h in enumerate(by_x[x]):
            if j not in used:
                nxt.append([x, x, h[1], h[2], h[1], h[2]])
        open_ = nxt
    done += open_
    return [(s[0], s[1], s[4], s[5]) for s in done if s[1] - s[0] + 1 >= min_len]


def detect(png: str, px_per_m: float, min_m: float = 0.3, gap_m: tuple[float, float] = (0.03, 0.35)) -> list[dict]:
    from stoa.solvers.raster.doorarcs import legend_cut

    g = np.asarray(Image.open(png).convert("L"))
    cut = legend_cut((g < 210).astype(np.float32))
    g = g[:cut]
    smin, smax = max(2.0, gap_m[0] * px_per_m), gap_m[1] * px_per_m
    min_len = max(4, int(min_m * px_per_m))
    dets = []
    for x0, x1, c0, c3 in _segments(_hits(g, smin, smax), min_len):  # horizontal walls: x along, y across
        dets.append({"box": [x0, c0, x1 + 1, c3 + 1], "dir": "h"})
    for y0, y1, c0, c3 in _segments(_hits(g.T, smin, smax), min_len):  # vertical walls
        b = [c0, y0, c3 + 1, y1 + 1]
        if not any(_overlap(b, d["box"]) > 0.3 for d in dets if d["dir"] == "h"):
            dets.append({"box": b, "dir": "v"})
    return dets


def _overlap(a, b) -> float:
    """Intersection over the smaller box."""
    iw = min(a[2], b[2]) - max(a[0], b[0])
    ih = min(a[3], b[3]) - max(a[1], b[1])
    if iw <= 0 or ih <= 0:
        return 0.0
    sm = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return iw * ih / max(1e-6, sm)


def _match(dets, gold, px_per_m):
    """Greedy: a det matches a gold box when their centres are within 0.4 m and boxes overlap."""
    used = set()
    tp = 0
    for d in dets:
        bx = d["box"]
        cx, cy = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
        best, bd = None, 1e9
        for j, gb in enumerate(gold):
            if j in used:
                continue
            gx, gy = (gb[0] + gb[2]) / 2, (gb[1] + gb[3]) / 2
            dist = np.hypot(cx - gx, cy - gy)
            ov = min(bx[2], gb[2]) - max(bx[0], gb[0]) > -2 and min(bx[3], gb[3]) - max(bx[1], gb[1]) > -2
            if ov and dist < bd and dist < 0.6 * px_per_m:
                best, bd = j, dist
        if best is not None:
            used.add(best)
            tp += 1
    return tp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--show", default="")
    ap.add_argument("--min_m", type=float, default=0.3)
    a = ap.parse_args()
    D = os.environ["STOA_DATA"]
    rows = [json.loads(l) for l in open(GOLD)][: a.n]
    T = P = G = ex = pm1 = 0
    errs = []
    for r in rows:
        if a.show and r["stem"] != a.show:
            continue
        png = os.path.join(D, r["png"])
        dets = detect(png, r["px_per_m"], min_m=a.min_m)
        gold = r["windows"]
        tp = _match(dets, gold, r["px_per_m"])
        T += tp
        P += len(dets)
        G += len(gold)
        ex += len(dets) == len(gold)
        pm1 += abs(len(dets) - len(gold)) <= 1
        errs.append(len(dets) - len(gold))
        print(f"{r['stem']:36s} ppm {r['px_per_m']:5.1f} gold {len(gold):3d} det {len(dets):3d} tp {tp:3d}")
        if a.show:
            sc = os.environ.get("SC", ".")
            im = Image.open(png).convert("RGB")
            from PIL import ImageDraw
            dr = ImageDraw.Draw(im)
            for gb in gold:
                dr.rectangle(gb, outline=(0, 200, 0), width=3)
            for d in dets:
                dr.rectangle(d["box"], outline=(255, 0, 255), width=2)
            im.save(f"{sc}/win_{r['stem']}.png")
    n = len(errs)
    print(f"floors {n}: exact {ex} ({100 * ex / max(1, n):.0f}%), ±1 {pm1}; recall {T}/{G} = {T / max(1, G):.3f}, "
          f"precision {T}/{P} = {T / max(1, P):.3f}; median err {float(np.median(errs)) if errs else 0:+.1f}")


if __name__ == "__main__":
    main()
