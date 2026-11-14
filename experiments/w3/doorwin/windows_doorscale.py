"""Window counts on plans WITHOUT a scale bar: px/m from the door arcs (scale_from_doors.estimate, standard leaf
0.86 m) instead of the bar, then windows.detect at that scale. Compares with the bar-scale answers of a raster eval run
(trace 'window symbols: N (scale X px/m)') and the gold. CPU only, 0 tokens.
Usage: python experiments/w3/doorwin/windows_doorscale.py <raster run on swiss_png_windows_dev.jsonl> [--workers 16]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

D = os.environ["STOA_DATA"]


def one(r):
    from scale_from_doors import estimate

    from stoa.solvers.raster import windows as WS
    p = os.path.join(D, r["path"])
    w = max(Image.open(p).size)
    s, n_arcs = estimate(p, w)
    bar = None
    for t in r.get("trace") or []:
        m = re.search(r"window symbols: \d+ \(scale ([\d.]+) px/m\)|window symbols: ([\d.]+) px/m is too coarse", t)
        if m:
            bar = float(m.group(1) or m.group(2))
    n = None
    if s and s >= WS.MIN_PX_PER_M and WS.prescan(p):
        n = len(WS.detect(p, s))
    return {"path": r["path"], "gold": r["gold"], "bar_px_m": bar, "door_px_m": s, "arcs": n_arcs, "n_door": n,
            "n_bar": r.get("value")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    rows = [json.loads(line) for line in open(a.run)]
    with ProcessPoolExecutor(a.workers) as ex:
        res = list(ex.map(one, rows))
    out = "/home/fangy4/work/projects/junction-shared/artifacts/W3/windows_doorscale.jsonl"
    with open(out, "w") as f:
        for x in res:
            f.write(json.dumps(x) + "\n")
    both = [x for x in res if x["bar_px_m"] and x["door_px_m"]]
    rel = sorted(abs(x["door_px_m"] / x["bar_px_m"] - 1) for x in both)
    print(f"scale: {len(both)} floors with both; within 10% {sum(r <= .10 for r in rel)}, 15% {sum(r <= .15 for r in rel)}")
    ans_d = [x for x in res if x["n_door"] is not None]
    ans_b = [x for x in res if x["n_bar"] is not None]
    ex_d = sum(x["n_door"] == x["gold"] for x in ans_d)
    ex_b = sum(x["n_bar"] == x["gold"] for x in ans_b)
    pm1 = sum(abs(x["n_door"] - x["gold"]) <= 1 for x in ans_d)
    print(f"bar scale:  answered {len(ans_b)}, exact {ex_b}")
    print(f"door scale: answered {len(ans_d)}, exact {ex_d}, +-1 {pm1}")
    same = sum(x["n_door"] == x["n_bar"] for x in res if x["n_door"] is not None and x["n_bar"] is not None)
    print(f"door-scale count == bar-scale count on {same} of "
          f"{sum(x['n_door'] is not None and x['n_bar'] is not None for x in res)}; out {out}")


if __name__ == "__main__":
    main()
