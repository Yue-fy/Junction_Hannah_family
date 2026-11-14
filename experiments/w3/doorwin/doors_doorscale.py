"""Door counts on plans WITHOUT a scale bar: px/m from the door arcs themselves (doorarcs.scale_from_arcs, standard
leaf 0.86 m), then the normal door path (detect at that scale + boundary doors x2). Compared with the bar-scale
answers of a raster eval run and the gold. CPU only, 0 tokens. Experiment only (not wired).
Usage: python experiments/w3/doorwin/doors_doorscale.py <raster doors run> [--workers 16]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

D = os.environ["STOA_DATA"]


def one(r):
    import numpy as np
    from PIL import Image

    from stoa.solvers.raster import doorarcs as DA
    p = r["path"] if r["path"].startswith("/") else os.path.join(D, r["path"])
    s, n_arcs = DA.scale_from_arcs(p)
    n = None
    if s:
        dets = DA.detect(p, s)
        if dets:
            rgb = np.asarray(Image.open(p).convert("RGB"))
            n = len(dets) + sum(DA.red_near(rgb, d, s) >= DA.DUP_RED for d in dets)
    return {"path": r["path"], "gold": r["gold"], "door_px_m": s, "arcs": n_arcs, "n_door": n, "n_bar": r.get("value")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    rows = [json.loads(line) for line in open(a.run)]
    with ProcessPoolExecutor(a.workers) as ex:
        res = list(ex.map(one, rows))
    out = "/home/fangy4/work/projects/junction-shared/artifacts/W3/doors_doorscale.jsonl"
    with open(out, "w") as f:
        for x in res:
            f.write(json.dumps(x) + "\n")
    for k in ("n_bar", "n_door"):
        ans = [x for x in res if x[k] is not None]
        e = [abs(x[k] - x["gold"]) for x in ans]
        print(f"{k}: answered {len(ans)}, exact {sum(v == 0 for v in e)}, +-1 {sum(v <= 1 for v in e)}, "
              f"+-2 {sum(v <= 2 for v in e)}")
    both = [x for x in res if x["n_bar"] is not None and x["n_door"] is not None]
    print(f"same count as the bar scale on {sum(x['n_bar'] == x['n_door'] for x in both)} of {len(both)}; out {out}")


if __name__ == "__main__":
    main()
