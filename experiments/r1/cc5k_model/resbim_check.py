"""Generality check of the CC5K counter on drawings from a different source and style: ResBIM raster plans
(data/ifc_models/resbim-N_plan.png, Revit exports, 7572×4189) whose IFC model gives the true number of
IfcDoor / IfcWindow (artifacts/R1/resbim/ifc_counts.json, made with stoa.solvers.ifc.index).
Preprocessing variants: 'full<L>' = whole image resized to long side L; 'crop<L>' = crop to the inked
bounding box (+2% margin) and resize to long side L.
Run: <torch-python> -I resbim_check.py
"""
import json
import os
import sys

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import net  # noqa: E402
from config import FROZEN  # noqa: E402
from predict import WEIGHTS, boxes  # noqa: E402

SHARED = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")
DATA = os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")
OUT = os.path.join(SHARED, "artifacts", "R1", "resbim")


def prep(im, mode, L):
    if mode == "crop":
        a = np.asarray(im.convert("L"))
        ys, xs = np.where(a < 200)
        m = int(0.02 * max(a.shape))
        im = im.crop((max(0, xs.min() - m), max(0, ys.min() - m), min(a.shape[1], xs.max() + m), min(a.shape[0], ys.max() + m)))
    s = L / max(im.size)
    return im.resize((max(1, round(im.size[0] * s)), max(1, round(im.size[1] * s))), Image.LANCZOS)


def run(m, im):
    a = np.asarray(im.convert("RGB"), np.float32)
    x = torch.from_numpy(2 * (a / 255.0) - 1).permute(2, 0, 1)[None]
    with torch.no_grad():
        y = F.interpolate(m(x)[:, 33:], size=a.shape[:2], mode="bilinear", align_corners=True)
    icons = y[0].argmax(0).numpy().astype(np.uint8)
    H, W = icons.shape
    return {t: len([b for c in cls for b in boxes(icons == c, max(1, mf * H * W), k)])
            for t, (cls, mf, k) in FROZEN.items() if t in ("doors", "windows")}


def main():
    torch.set_num_threads(8)
    m = net.load(WEIGHTS)
    gold = json.load(open(os.path.join(OUT, "ifc_counts.json")))
    variants = [("full", 2000), ("crop", 1000), ("crop", 1500), ("crop", 2000)]
    hits = {f"{v}{L}": {"doors": 0, "windows": 0} for v, L in variants}
    n = 0
    rows = []
    for stem, g in sorted(gold.items()):
        if "error" in g:
            continue
        im = Image.open(os.path.join(DATA, "data", "ifc_models", f"{stem}_plan.png"))
        row = {"stem": stem, "ifc": g}
        for v, L in variants:
            c = run(m, prep(im, v, L))
            row[f"{v}{L}"] = c
            for t in ("doors", "windows"):
                hits[f"{v}{L}"][t] += c[t] == g[t]
        rows.append(row)
        n += 1
    json.dump(rows, open(os.path.join(OUT, "cc5k_vs_ifc.json"), "w"))
    print(f"n={n} ResBIM plans (exact match with IFC counts)")
    for k, h in hits.items():
        print(f"  {k:9s} doors {h['doors'] / n:.0%}  windows {h['windows'] / n:.0%}")
    for r in rows[:6]:
        print(r)


if __name__ == "__main__":
    main()
