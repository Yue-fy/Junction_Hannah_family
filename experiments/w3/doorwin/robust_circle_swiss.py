"""Is the +-4 px full-circle test (ifc_plan_doors.robust_filter; rejects grid bubbles found 3 px off-centre) neutral on
the Swiss door path at the bar scale? Reads a raster doors run (bar scale from the trace), CPU only.
Usage: W3_ROBUST=1 python experiments/w3/doorwin/robust_circle_swiss.py <raster doors run>"""
import json
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
D = os.environ["STOA_DATA"]


def one(r):
    import numpy as np
    from PIL import Image
    from ifc_plan_doors import robust_filter

    from stoa.solvers.raster import doorarcs as DA
    s = None
    for t in r.get("trace") or []:
        m = re.search(r"door arcs: \d+ swing arcs \(scale ([\d.]+) px/m\)", t)
        if m:
            s = float(m.group(1))
    if s is None:
        return None
    p = os.path.join(D, r["path"])
    dets = DA.detect(p, s)
    rob = robust_filter(p, dets)
    rgb = np.asarray(Image.open(p).convert("RGB"))
    cnt = lambda ds: len(ds) + sum(DA.red_near(rgb, d, s) >= DA.DUP_RED for d in ds)  # noqa: E731
    return {"gold": r["gold"], "base": cnt(dets), "robust": cnt(rob), "dropped": len(dets) - len(rob)}


rows = [json.loads(line) for line in open(sys.argv[1])]
with ProcessPoolExecutor(16) as ex:
    res = [x for x in ex.map(one, rows) if x]
for k in ("base", "robust"):
    e = [abs(x[k] - x["gold"]) for x in res]
    print(f"{k}: n {len(res)} exact {sum(v == 0 for v in e)} +-1 {sum(v <= 1 for v in e)} +-2 {sum(v <= 2 for v in e)}")
print("floors with dropped arcs", sum(x["dropped"] > 0 for x in res), "arcs dropped", sum(x["dropped"] for x in res))
