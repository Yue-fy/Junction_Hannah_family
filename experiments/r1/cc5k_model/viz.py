"""Overlay CC5K icon components (windows red, doors blue, toilets green, sinks magenta, bathtubs cyan) on a
drawing. Run: $JUNCTION_VENV/bin/python -I viz.py <stem> <out.png> [--tta] [--min-frac 2e-5]"""
import argparse
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import count as C  # noqa: E402

COL = {1: (0, 0, 255), 2: (255, 0, 0), 5: (0, 160, 0), 6: (255, 0, 255), 9: (255, 200, 0)}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stem")
    ap.add_argument("out")
    ap.add_argument("--tta", action="store_true")
    ap.add_argument("--min-frac", type=float, default=2e-5)
    a = ap.parse_args()
    im = cv2.imread(os.path.join(C.DATA, "data", "cubicasa5k", a.stem + ".png"))
    icons = np.load(os.path.join(C.SEG, ("tta_" if a.tta else "") + a.stem + ".npz"))["icons"]
    H, W = icons.shape
    over = im.copy()
    for c, col in COL.items():
        over[icons == c] = col
        for (x, y, w, h), _ in C.components(icons == c, max(1, a.min_frac * H * W), 0):
            cv2.rectangle(im, (x - 2, y - 2), (x + w + 2, y + h + 2), col, 2)
    cv2.imwrite(a.out, cv2.addWeighted(im, 0.6, over, 0.4, 0))
    g = C.gold_table().get(a.stem, {})
    print({t: (g.get(t), C.counts({"icons": icons}, t, a.min_frac, 0)) for t in C.TEMPLATES})
