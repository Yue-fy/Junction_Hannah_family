"""Run doorarcs.detect on every gold floor; dump detections + red (unit boundary) pixel counts near each door."""
import json, os, sys, math
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import numpy as np
from PIL import Image
D = os.environ["STOA_DATA"]


def red_near(rgb, x, y, rad):
    H, W = rgb.shape[:2]
    x0, x1, y0, y1 = max(0, int(x - rad)), min(W, int(x + rad) + 1), max(0, int(y - rad)), min(H, int(y + rad) + 1)
    p = rgb[y0:y1, x0:x1].astype(int)
    m = (abs(p[..., 0] - 176) < 40) & (abs(p[..., 1] - 58) < 40) & (abs(p[..., 2] - 46) < 40)
    return int(m.sum())


def one(line):
    from stoa.solvers.raster import doorarcs as DA
    r = json.loads(line)
    png = os.path.join(D, r["png"])
    dets = DA.detect(png, r["px_per_m"])
    rgb = np.asarray(Image.open(png).convert("RGB"))
    for d in dets:
        x, y = d["c"]
        d["red_hinge"] = red_near(rgb, x, y, 0.12 * r["px_per_m"])
        bx = d["box"]
        d["red_box"] = red_near(rgb, (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2, d["r_px"] / 2 + 0.1 * r["px_per_m"])
    return {"stem": r["stem"], "px_per_m": r["px_per_m"], "gold": len(r["doors"]), "arcs": r["arcs"], "dets": dets}


if __name__ == "__main__":
    lines = open(sys.argv[1]).read().splitlines()
    with ProcessPoolExecutor(6) as ex, open(sys.argv[2], "w") as f:
        for o in ex.map(one, lines):
            f.write(json.dumps(o) + "\n")
            print(o["stem"], o["gold"], len(o["dets"]), flush=True)
