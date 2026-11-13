"""Link a swiss DXF to its PDF and PNG (Stoa: "linking heterogeneous data earns points").

Fit the affine map DXF (metres) -> PDF (points) per floor by least squares on text that occurs exactly once
in both: DXF ROOM_TEXT room numbers ("7.01") <-> PyMuPDF words with the same string (centre of the word
box vs DXF text insertion point). Then PDF -> PNG is a fixed scale: the PNG is the page at 150 dpi
(2480 px / 1190.55 pt = 2.0833 = 150/72).
Reports the residual (pt) per floor and the share of floors with a good fit; with the map, every DXF entity
(door polyline, fixture ellipse, room polygon) becomes an evidence box on the PDF and PNG.
Run: $JUNCTION_VENV/bin/python -I fit_affine.py [n_floors]
"""
import os
import re
import statistics
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
import fitz  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "swiss_area_def"))
from minidxf import read_entities  # noqa: E402

D = os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")
SW = os.path.join(D, "data", "swiss_dwellings")
PX_PER_PT = 150 / 72
NUM = re.compile(r"^[A-Z]{0,2}\d+(\.\d+)+$")


def fit(stem):
    E = read_entities(os.path.join(SW, stem + ".dxf"))
    dxf = {}
    for e in E:
        if e["layer"] == "ROOM_TEXT" and e["text"] and NUM.match(e["text"].strip()) and e["x"]:
            dxf.setdefault(e["text"].strip(), []).append((e["x"][0], e["y"][0]))
    words = fitz.open(os.path.join(SW, stem + ".pdf"))[0].get_text("words")
    pdf = {}
    for w in words:
        if NUM.match(w[4]):
            pdf.setdefault(w[4], []).append(((w[0] + w[2]) / 2, (w[1] + w[3]) / 2))
    keys = [k for k in dxf if len(dxf[k]) == 1 and len(pdf.get(k, [])) == 1]
    if len(keys) < 3:
        return None
    X = np.array([[*dxf[k][0], 1.0] for k in keys])
    U = np.array([pdf[k][0] for k in keys])
    A, *_ = np.linalg.lstsq(X, U, rcond=None)  # 3x2: [x y 1] @ A = [u v]
    res = np.linalg.norm(X @ A - U, axis=1)
    return {"n": len(keys), "rmse_pt": float(np.sqrt((res ** 2).mean())), "max_pt": float(res.max()), "A": A.tolist()}


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    stems = sorted(f[:-4] for f in os.listdir(SW) if f.endswith(".dxf"))[:n]
    R = {s: fit(s) for s in stems}
    ok = [r for r in R.values() if r]
    print(f"floors {len(stems)}; fitted {len(ok)} (>=3 unique room numbers in both)")
    rm = sorted(r["rmse_pt"] for r in ok)
    print(f"RMSE pt: median {statistics.median(rm):.2f}, 90th pct {rm[int(0.9 * len(rm))]:.2f}, max {rm[-1]:.2f}; "
          f"share with max residual < 3 pt (~6 px on the PNG): {sum(r['max_pt'] < 3 for r in ok) / len(ok):.1%}")
    import collections
    # pt per metre -> drawing scale 1:N with N = 1000 mm / (pt_per_m * 25.4/72 mm)
    scales = collections.Counter(round(1000 / (float(np.hypot(*np.array(r["A"])[0])) * 25.4 / 72)) for r in ok)
    print("drawing scale 1:N distribution:", scales.most_common(6))
    s = next(iter(ok))
    A = np.array(s["A"])
    print("example map (metres -> pt):", np.round(A.T, 3).tolist(), " scale pt/m:", round(float(np.hypot(*A[0])), 3))
