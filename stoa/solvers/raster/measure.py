"""Room areas on raster plans by flood fill from the room's printed label, scaled by the graphic scale bar.

A VLM box around a room is far too rough to measure (Swiss PNG twins, 22 single-room questions: median error 47%,
0 within 2%; experiments/w3/measure_eval.py). Drawn plans have closed rooms: walls are ink, the room is the blank
region around its label. So:
  1. ink = dark pixels (red dash-dot unit outlines and light fills are not walls);
  2. door openings are closed with 1-D closings of ~1 m (from px per m), so the fill stays in the room;
  3. the blank component next to the label (number or name, from the text layer) is the room; its holes (text,
     furniture, fixtures) are filled; a component touching the image border is a leak -> no answer;
  4. area = pixels / (px per m)^2.

    room_area(path, label_box, px_per_m) -> {"m2", "box", "pixels", "notes"} or None
    find_label(layer, question) -> TextItem of the room named in the question ('room 2.32', «Bagno») or None
"""

from __future__ import annotations

import re

import cv2
import numpy as np
from PIL import Image

from stoa.solvers.raster import textlayer as T

_ROOM_ID = re.compile(r"(?<![\d.])(\d{1,3}\.\d{1,3}[a-z]?)(?![\d])")
_QUOTED = re.compile(r"[«\"'‘“„‚]([^«»\"'’”‘“]{2,40})[»\"'’”“]")


def find_label(layer: T.TextLayer, question: str) -> T.TextItem | None:
    """The text-layer item that names the room asked about: a room number (exact) first, else a unique quoted name."""
    for rid in _ROOM_ID.findall(question):
        hits = [i for i in layer.items if i.text.strip().rstrip(".") == rid]
        if len(hits) == 1:
            return hits[0]
    for name in _QUOTED.findall(question):
        hits = [i for i in layer.items if T.norm(i.text) == T.norm(name)]
        if len(hits) == 1:
            return hits[0]
    return None


def _ink(path: str) -> np.ndarray:
    rgb = np.asarray(Image.open(T._abspath(path)).convert("RGB"), dtype=np.int16)
    g = rgb.mean(axis=2)
    red = (rgb[..., 0] > 140) & (rgb[..., 1] < 120) & (rgb[..., 2] < 120)  # unit outlines, annotations
    return ((g < 190) & ~red).astype(np.uint8)


# Chosen on 71 Swiss PNG dev rooms (experiments/w3/room_fill_eval.py --door 0 --hull --clip 3): median error 6.5%,
# within 2% 7/71, 5% 30/71, 10% 44/71, 20% 51/71, pred/gold p10/p50/p90 0.61/0.96/1.12. Doors did not leak there
# (closing door gaps cut rooms at furniture instead: median 29%); the hull puts back counters/fixtures against walls.
FILL = {"door_m": 0.0, "hull": True, "clip": True, "clip_m2": 3.0}
WITHIN = {"2%": 7 / 71, "5%": 30 / 71, "10%": 44 / 71, "20%": 51 / 71}


def room_area(path: str, label_box: list[float], px_per_m: float, door_m: float = 1.05,
              ink: np.ndarray | None = None, wall_m: float = 0.0, hull: bool = False, clip: bool = False,
              clip_m2: float = 3.0) -> dict | None:
    ink = _ink(path) if ink is None else ink
    H, W = ink.shape
    if wall_m > 0:  # walls only: an opening removes thin lines (furniture, fixtures, door arcs, text strokes)
        w = max(2, int(round(wall_m * px_per_m)))
        ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (w, w)))
    k = max(3, int(round(door_m * px_per_m)))
    closed = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, 1)))
    closed = cv2.morphologyEx(closed, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, k)))
    free = (closed == 0).astype(np.uint8)
    n, lab = cv2.connectedComponents(free, connectivity=4)
    # the component around the label: the most common free component in a ring around the label box
    x0, y0, x1, y1 = (int(round(v)) for v in label_box)
    pad = max(4, int(0.15 * px_per_m))
    ring = lab[max(0, y0 - pad):min(H, y1 + pad), max(0, x0 - pad):min(W, x1 + pad)]
    ids, counts = np.unique(ring[ring > 0], return_counts=True)
    if not len(ids):
        return None
    cid = int(ids[np.argmax(counts)])
    comp = (lab == cid).astype(np.uint8)
    ys, xs = np.nonzero(comp)
    if ys.min() == 0 or xs.min() == 0 or ys.max() == H - 1 or xs.max() == W - 1:
        return None  # leaked to the sheet border: not a closed room
    cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(comp)
    if hull:
        cnts = [cv2.convexHull(np.concatenate(cnts))]
    cv2.drawContours(filled, cnts, -1, 1, thickness=cv2.FILLED)
    if hull and clip:
        # fixtures and counters against a wall are small separate blanks inside the hull: keep them; take out the
        # thick walls and any OTHER large blank (a neighbouring room the hull of an L-shaped room reaches into)
        sizes = np.bincount(lab.ravel())
        big = sizes > clip_m2 * px_per_m ** 2
        big[0] = False
        big[cid] = False
        other = big[lab]
        w = max(2, int(round(0.1 * px_per_m)))
        thick = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (w, w))) > 0
        filled[other | thick] = 0
    px = int(filled.sum())
    m2 = px / px_per_m ** 2
    box = [float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)]
    return {"m2": round(m2, 2), "box": box, "pixels": px,
            "notes": [f"flood fill from the label at ({(x0 + x1) / 2:.0f}, {(y0 + y1) / 2:.0f}) px"
                      + (f", door gaps closed at {k} px ({door_m:g} m)" if door_m > 0 else "")
                      + (", convex hull (fixtures against walls kept), walls and other rooms cut out" if hull else "")
                      + f": {px} px / {px_per_m:.2f}² px per m² = {m2:.2f} m²"]}
