"""Generality test of the door-arc counter on an UNSEEN render style without a scale bar: the resbim IFC plan PNGs
(Revit-style exports, 7572x4189 px, mm dimension strings, no bar). Gold = IfcDoor count of the model (all on Level 0).
Each PNG is cropped to its ink (+60 px) and downscaled to <= MAX_SIDE px (speed), the scale comes from the arcs
themselves (doorarcs.scale_from_arcs, leaf 0.86 m), then doorarcs.detect at that scale. CPU only, 0 tokens.
Usage: python experiments/w3/doorwin/ifc_plan_doors.py [--n 40] [--workers 16]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

D = os.environ["STOA_DATA"]
MAX_SIDE = 1800
DIV = float(os.environ.get("W3_ARC_DIV", "10"))  # radius ceiling = long side / DIV (stoa uses 25: sheet, not crop)


LO_DIV = float(os.environ.get("W3_ARC_LO_DIV", "0"))  # radius floor = long side / LO_DIV (0 = 12 px)
ROBUST = os.environ.get("W3_ROBUST", "0") == "1"  # full-circle test over r +- 4 px (grid bubbles found off-centre)


def robust_filter(png, dets):
    """Drop detections whose ring is inked in >= 3 quadrants at ANY radius within +-4 px (stoa tests only r)."""
    import numpy as np
    from PIL import Image

    from stoa.solvers.raster import doorarcs as DA
    if not ROBUST:
        return dets
    ink = (np.asarray(Image.open(png).convert("L")) < DA.INK).astype(np.float32)
    keep = []
    for d in dets:
        x, y, r = int(round(d["c"][0])), int(round(d["c"][1])), d["r_px"]
        qs = [max(DA._score_at(ink, x, y, r + dr, j) for dr in range(-4, 5)) for j in range(4)]
        if sum(v >= 0.5 * DA.THR for v in qs) < 3:
            keep.append(d)
    return keep


def estimate(png, w, div):
    """doorarcs.scale_from_arcs with a configurable radius ceiling."""
    import statistics

    from stoa.solvers.raster import doorarcs as DA
    lo, hi, ps = (w / LO_DIV if LO_DIV else 12.0), max(40.0, w / div), 46.0
    dets = robust_filter(png, DA.detect(png, ps, r_m=(lo / ps, hi / ps)))
    if LO_DIV:  # an arc peaking at the search floor is a fragment (bubble lens, glyph), not a door at its own radius
        dets = [d for d in dets if d["r_px"] >= 1.1 * lo]
    if len(dets) < 3:
        return None, len(dets)
    top = sorted(dets, key=lambda d: -d["score"])[: max(3, len(dets) // 2)]
    return statistics.median(d["r_px"] for d in top) / DA.DOOR_LEAF_M, len(dets)


def one(png):
    import ifcopenshell
    import numpy as np
    from PIL import Image

    from stoa.solvers.raster import doorarcs as DA
    from stoa.solvers.raster import windows as WS
    t = time.time()
    gold = len(ifcopenshell.open(png.replace("_plan.png", "_model.ifc")).by_type("IfcDoor"))
    gwin = len(ifcopenshell.open(png.replace("_plan.png", "_model.ifc")).by_type("IfcWindow"))
    im = Image.open(png).convert("RGB")
    g = np.asarray(im.convert("L"))
    ys, xs = np.nonzero(g < 200)
    box = (max(0, xs.min() - 60), max(0, ys.min() - 60), min(im.width, xs.max() + 60), min(im.height, ys.max() + 60))
    crop = im.crop(box)
    f = min(1.0, MAX_SIDE / max(crop.size))
    crop = crop.resize((round(crop.width * f), round(crop.height * f)), Image.LANCZOS)
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "plan.png")
        crop.save(p)
        clean = WS.clean_render(p)[0]
        s, n_arcs = estimate(p, max(crop.size), DIV)
        n = len(robust_filter(p, DA.detect(p, s))) if s else None
    return {"png": os.path.basename(png), "gold": gold, "windows": gwin, "clean": clean, "px_m": s and round(s, 1),
            "arcs_wide": n_arcs, "n": n, "f": round(f, 3), "s": round(time.time() - t, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    pngs = sorted(glob.glob(f"{D}/data/ifc_models/resbim-*_plan.png"))[: a.n]
    with ProcessPoolExecutor(a.workers) as ex:
        res = list(ex.map(one, pngs))
    out = "/home/fangy4/work/projects/junction-shared/artifacts/W3/ifc_plan_doors.jsonl"
    with open(out, "w") as fh:
        for x in res:
            fh.write(json.dumps(x) + "\n")
    ans = [x for x in res if x["n"] is not None]
    e = [x["n"] - x["gold"] for x in ans]
    print(f"{len(res)} plans, answered {len(ans)}: exact {sum(v == 0 for v in e)}, +-1 {sum(abs(v) <= 1 for v in e)}, "
          f"mean err {sum(e) / max(1, len(e)):+.2f}; median px/m "
          f"{sorted(x['px_m'] for x in ans)[len(ans) // 2] if ans else None}; mean {sum(x['s'] for x in res) / len(res):.1f} s; "
          f"prior (mode of gold) exact {max(sum(x['gold'] == k for x in res) for k in {x['gold'] for x in res})}; out {out}")


if __name__ == "__main__":
    main()
