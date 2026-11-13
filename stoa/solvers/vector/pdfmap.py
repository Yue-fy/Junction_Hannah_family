"""Map DXF coordinates (metres, y up) onto the sibling PDF page (pdf_pt, y down) and PNG (image_px).

The swiss PDF, DXF and PNG are renderings of one drawing, so a similarity transform without rotation
    x_pdf = s * x_dxf + a        y_pdf = -s * y_dxf + b
maps one onto the other. We fit (s, a, b) by least squares on texts that occur exactly once in both the
DXF ROOM_TEXT layer and the PDF text layer (room numbers like "2.01" are ideal anchors: DXF TEXT is
centre/middle aligned, so the anchor is the centre of the PDF word box), drop outliers, refit.
The PNG is the PDF rendered at a fixed DPI, so image_px = pdf_pt * (png_width / page_width).
"""

from __future__ import annotations

import functools
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Transform:
    s: float
    a: float
    b: float
    n_anchors: int
    rms_pt: float
    page_w: float
    page_h: float

    def pt(self, x: float, y: float) -> tuple[float, float]:
        return self.s * x + self.a, -self.s * y + self.b

    def box(self, bb, pad_pt: float = 0.0) -> list[float]:
        x0, y0 = self.pt(bb[0], bb[3])
        x1, y1 = self.pt(bb[2], bb[1])
        return [round(x0 - pad_pt, 2), round(y0 - pad_pt, 2), round(x1 + pad_pt, 2), round(y1 + pad_pt, 2)]

    @property
    def scale_ratio(self) -> float:
        """Drawing scale denominator: 1 m in the DXF = s pt on paper -> 1:(72/0.0254/s)."""
        return 72 / 0.0254 / self.s


def _pdf_words(pdf_path: str):
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        page = doc[0]
        words = page.get_text("words")
        return [(w[4], (w[0] + w[2]) / 2, (w[1] + w[3]) / 2) for w in words], (page.rect.width, page.rect.height)


@functools.lru_cache(maxsize=256)
def fit_transform(pdf_path: str, dxf_path: str) -> Transform | None:
    from stoa.solvers.vector.floor import load_floor

    fm = load_floor(dxf_path)
    words, (pw, ph) = _pdf_words(pdf_path)
    dxf_by = {}
    for t in fm.texts:
        if " " in t.text:  # PDF splits multi-word labels into words; keep single tokens only
            continue
        dxf_by.setdefault(t.text, []).append(t)
    pdf_by = {}
    for w, x, y in words:
        pdf_by.setdefault(w, []).append((x, y))
    pairs = [(dxf_by[k][0], pdf_by[k][0]) for k in dxf_by if len(dxf_by[k]) == 1 and len(pdf_by.get(k, [])) == 1]
    if len(pairs) < 3:
        return None
    X = np.array([[t.x, t.y] for t, _ in pairs])
    P = np.array([p for _, p in pairs])
    keep = np.ones(len(pairs), bool)
    s = a = b = 0.0
    for _ in range(3):
        xs, ys, px, py = X[keep, 0], X[keep, 1], P[keep, 0], P[keep, 1]
        # unknowns (s, a, b): px = s*xs + a ; py = -s*ys + b
        n = len(xs)
        A = np.zeros((2 * n, 3))
        A[:n, 0], A[:n, 1] = xs, 1
        A[n:, 0], A[n:, 2] = -ys, 1
        rhs = np.concatenate([px, py])
        (s, a, b), *_ = np.linalg.lstsq(A, rhs, rcond=None)
        res = np.hypot(s * X[:, 0] + a - P[:, 0], -s * X[:, 1] + b - P[:, 1])
        new_keep = res < max(2.0, 3 * np.median(res[keep]))
        if new_keep.sum() < 3 or (new_keep == keep).all():
            break
        keep = new_keep
    res = np.hypot(s * X[keep, 0] + a - P[keep, 0], -s * X[keep, 1] + b - P[keep, 1])
    if s <= 0:
        return None
    return Transform(float(s), float(a), float(b), int(keep.sum()), float(np.sqrt(np.mean(res**2))), pw, ph)


@functools.lru_cache(maxsize=256)
def png_scale(png_path: str, page_w: float) -> float:
    from PIL import Image

    with Image.open(png_path) as im:
        return im.size[0] / page_w
