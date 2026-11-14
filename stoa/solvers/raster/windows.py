"""Window symbols on clean rendered floor plans (Swiss dwellings style), for window counts on plans without a vector
twin: a window is a stretch of wall whose fill is replaced by 4 equally spaced thin parallel lines (the 2 wall faces,
dark, and 2 glass lines, grey ~59) on white. Profile scan per column (horizontal walls) and per row (vertical walls),
lines told apart by ink mass (a tilted 1-px line is antialiased over 2 px, so its min value says little), then runs of
matching columns = one window (a mullion breaks the run; tilted walls are followed).
TRAIN Swiss floors at 1:100 (experiments/w3/doorwin/windows.py; DXF window items mapped to PNG px): thresholds set on
20 floors; held-out 32 floors exact 10 (31%), +-1 15, within 10% 18; all 51: recall 0.85, precision 0.93.
1:200 sheets (~30 px/m): recall 0.65, 0/9 exact (the glass lines render as dark as the faces; relaxing the ink test
and rejecting a 5th equally spaced line (stairs) cost 1:100 3 exact floors and did not fix 1:200): None there.

detect(png, px_per_m) -> [{"box": [x0, y0, x1, y1], "dir": "h"|"v"}] in image px.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

CONF = 0.4          # exact where answered: TRAIN held-out 10/32, Swiss dev (twins=0) 34/75 -> pooled 0.41
MIN_PX_PER_M = 45   # below this (1:200 renders) the window lines merge
WHITE = 200
LINE_MAX = 4        # px: a thin line crossed at up to ~60 degrees
INNER_MIN = 110     # ink mass of a glass line (grey 59 1-px line = 196; antialiased the same)
INNER_RATIO = 1.5   # the two glass lines carry similar ink
OUTER_K = 1.12      # a wall face (black 1-px = 255..275) carries more ink than a glass line (~197)
OUTER_MIN_V = 100   # a wall face reaches at least this dark somewhere


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


def detect(png: str, px_per_m: float, min_m: float = 0.3, gap_m: tuple[float, float] = (0.03, 0.35),
           red: bool = True) -> list[dict]:
    from stoa.solvers.raster.doorarcs import legend_cut

    rgb = np.asarray(Image.open(png).convert("RGB")).astype(np.int16)
    g = np.asarray(Image.fromarray(rgb.astype(np.uint8)).convert("L")).copy()
    if red:  # the red apartment boundary runs along wall faces and merges with them: drop coloured ink
        g[(rgb[..., 0] - np.maximum(rgb[..., 1], rgb[..., 2])) > 60] = 255
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
