"""ResBIM raster plans (resbim-N_plan.png, no SVG twin): model XY (m) -> image px by matching the extent of the
walls. The PNG fills walls with grey 192; the model gives the wall footprints. Fit px = s*(x - x0) + u0,
py = -s*(y - y1) + v0 (y up in the model, down in the image) from the two bounding boxes, check that the x and
y scales agree and that the drawn wall mask covers the projected footprints.
PYTHONPATH=$PWD python experiments/w1/resbim_fit.py [N models]"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw
from stoa.solvers.ifc.index import load_index

Image.MAX_IMAGE_PIXELS = None
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
root = os.path.expandvars("$STOA_DATA")
rows = []
for i in range(1, 501):
    if len(rows) >= N:
        break
    png = f"{root}/data/ifc_models/resbim-{i}_plan.png"
    rel = f"data/ifc_models/resbim-{i}_model.ifc"
    if not os.path.exists(png):
        continue
    idx = load_index(rel)
    walls = [e for e in idx.by_class("IfcWall", "IfcWallStandardCase") if e.geo and e.geo.footprint]
    if not walls:
        continue
    xs = [p[0] for e in walls for r in e.geo.footprint for p in r]
    ys = [p[1] for e in walls for r in e.geo.footprint for p in r]
    a = np.asarray(Image.open(png))
    m = a == 192
    vy, vx = np.nonzero(m)
    if len(vx) == 0:
        continue
    sx = (vx.max() - vx.min()) / (max(xs) - min(xs))
    sy = (vy.max() - vy.min()) / (max(ys) - min(ys))
    s = (sx + sy) / 2
    # coverage: rasterise projected footprints, share of them on drawn wall pixels (dilated mask)
    img = Image.new("1", (a.shape[1], a.shape[0]), 0)
    d = ImageDraw.Draw(img)
    for e in walls:
        for r in e.geo.footprint:
            d.polygon([((x - min(xs)) * s + vx.min(), (max(ys) - y) * s + vy.min()) for x, y in r], fill=1)
    proj = np.asarray(img)
    from PIL import ImageFilter
    drawn = np.asarray(Image.fromarray(((m | (a < 60)) * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(9))) > 0
    cov = (proj & drawn).sum() / max(proj.sum(), 1)
    rows.append((i, len(walls), round(sx, 2), round(sy, 2), round(abs(sx - sy) / s * 100, 2), round(cov, 3)))
    print(rows[-1], flush=True)
ok = [r for r in rows if r[4] < 1.0 and r[5] > 0.9]
print(f"{len(ok)}/{len(rows)} fits with |sx-sy| < 1% and coverage > 90%")
