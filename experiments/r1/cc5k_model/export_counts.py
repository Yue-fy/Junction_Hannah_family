"""Export CC5K-model counts for every cached cubicasa drawing to one JSONL (for W3's raster solver / the demo).

Line: {"path", "cc5k_list": "train"|"val"|"test"|"unknown", "size": [W, H],
       "counts": {"windows"|"doors"|"wc_seats"|"sinks": {"count", "confidence", "boxes": [[x0,y0,x1,y1],...]}}}
cc5k_list = which ORIGINAL CubiCasa5K list the drawing is in. "train" means the model saw its labels:
accuracy measured on those drawings is inflated (D3); report on val/test only.
Run: $JUNCTION_VENV/bin/python -I export_counts.py [OUT.jsonl]
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import count as C  # noqa: E402
from config import FROZEN, confidence  # noqa: E402


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(C.SHARED, "artifacts", "R1", "cc5k_counts.jsonl")
    lists = {}
    for s in ("train", "val", "test"):
        for st in C.stems_of(s):
            lists[st] = s
    n = 0
    with open(out, "w") as fo:
        for f in sorted(os.listdir(C.SEG)):
            if not f.endswith(".npz") or not f.startswith(("colorful", "high")):
                continue  # skip tta_/s2_ variants
            st = f[:-4]
            icons = np.load(os.path.join(C.SEG, f))["icons"]
            H, W = icons.shape
            counts = {}
            for t, (cls, mf, k) in FROZEN.items():
                bx = [[x, y, x + w, y + h] for c in cls for (x, y, w, h), _ in C.components(icons == c, max(1, mf * H * W), k)]
                counts[t] = {"count": len(bx), "confidence": confidence(t, len(bx)), "boxes": bx}
            fo.write(json.dumps({"path": f"data/cubicasa5k/{st}.png", "cc5k_list": lists.get(st, "unknown"),
                                 "size": [W, H], "counts": counts}) + "\n")
            n += 1
    print(f"wrote {n} drawings -> {out}")


if __name__ == "__main__":
    main()
