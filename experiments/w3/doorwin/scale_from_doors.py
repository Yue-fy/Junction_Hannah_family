"""Scale (px per m) WITHOUT a scale bar, from door swing arcs: search arcs over a wide pixel radius range, take the
median radius of the strongest arcs as a standard door leaf (0.86 m = median of the DXF door radii on 60 TRAIN
floors). Simulates unknown scales by resizing the PNG (factors below). Experiment only (not wired into raster).

Usage: python experiments/w3/doorwin/scale_from_doors.py [--n 12] [--factors 0.7,1.0,1.4]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from stoa.solvers.raster import doorarcs as DA  # noqa: E402

GOLD = "/home/fangy4/work/projects/junction-shared/artifacts/W3/doorwin_gold_train.jsonl"
DOOR_M = 0.86


def estimate(png: str, w_px: int) -> tuple[float | None, int]:
    """px/m from the median radius of the strongest arcs; the search spans 12..max(W,H)/25 px (a door leaf at most
    1/25 of the sheet's long side), expressed to detect() as metres at a nominal 1 px/m-per-unit scale."""
    lo, hi = 12.0, max(40.0, w_px / 25)
    # detect() needs px_per_m only to set the radius range and the NMS distance; pass a pseudo-scale of 46 px per
    # 'm' (r_m = px / 46) so the 1:200 upscale rule (px_per_m < 45) does not fire
    ps = 46.0
    dets = DA.detect(png, ps, r_m=(lo / ps, hi / ps))
    if len(dets) < 3:
        return None, len(dets)
    top = sorted(dets, key=lambda d: -d["score"])[: max(3, len(dets) // 2)]
    r = st.median(d["r_px"] for d in top)
    return r / DOOR_M, len(dets)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--factors", default="0.7,1.0,1.4")
    a = ap.parse_args()
    D = os.environ["STOA_DATA"]
    rows = [json.loads(line) for line in open(GOLD) if json.loads(line)["px_per_m"] >= 45][: a.n]
    errs: dict[float, list[float]] = {}
    with tempfile.TemporaryDirectory() as td:
        for r in rows:
            im = Image.open(os.path.join(D, r["png"])).convert("RGB")
            for f in (float(x) for x in a.factors.split(",")):
                p = os.path.join(td, f"{r['stem']}_{f}.png")
                im.resize((round(im.size[0] * f), round(im.size[1] * f)), Image.BICUBIC if f > 1 else Image.LANCZOS).save(p)
                t0 = time.time()
                est, n = estimate(p, max(im.size) * f)
                true = r["px_per_m"] * f
                e = None if est is None else est / true - 1
                errs.setdefault(f, []).append(e)
                print(f"{r['stem']:34s} x{f:.1f} true {true:6.1f} est {est if est is None else round(est, 1)} "
                      f"err {e if e is None else round(e, 3)} dets {n} {time.time() - t0:.1f}s", flush=True)
    for f, es in errs.items():
        ok = [e for e in es if e is not None]
        print(f"x{f}: {len(ok)}/{len(es)} estimated; within 10% {sum(abs(e) <= 0.1 for e in ok)}, within 15% "
              f"{sum(abs(e) <= 0.15 for e in ok)}; median err {st.median(ok) if ok else None}")


if __name__ == "__main__":
    main()
