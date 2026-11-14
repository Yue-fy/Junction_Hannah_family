"""Per-object door/window gold in PNG pixels for Swiss floors, from the sibling DXF (TRAIN floors only by default).

Doors = DXF 5-vertex DOOR leaves (the dxf solver's count), each with its arc (centre, radius) when one touches it;
windows = groups of 3 WINDOW polylines. Mapped DXF -> PDF pt -> PNG px with stoa.solvers.vector.pdfmap.
Usage: python experiments/w3/doorwin/gold.py --split train --n 60 --out $JUNCTION_SHARED/artifacts/W3/doorwin_gold_train.jsonl
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from stoa.eval.splits import load_split  # noqa: E402
from stoa.solvers.vector import floor as F  # noqa: E402
from stoa.solvers.vector import pdfmap as PM  # noqa: E402

D = os.environ["STOA_DATA"]


def gold(stem: str) -> dict | None:
    base = os.path.join(D, "data/swiss_dwellings", stem)
    if not all(os.path.exists(base + e) for e in (".dxf", ".pdf", ".png")):
        return None
    tr = PM.fit_transform(base + ".pdf", base + ".dxf")
    if tr is None:
        return None
    k = PM.png_scale(base + ".png", tr.page_w)
    fm = F.load_floor(base + ".dxf")

    def px(bb):
        b = tr.box(bb)
        return [round(v * k, 1) for v in b]

    # arcs straight from the DXF (centre + radius), for diagnostics
    import ezdxf
    doc = ezdxf.readfile(base + ".dxf")
    arcs = []
    for e in doc.modelspace():
        if e.dxftype() == "ARC" and e.dxf.layer == "DOOR":
            cx, cy = tr.pt(float(e.dxf.center[0]), float(e.dxf.center[1]))
            arcs.append({"c": [round(cx * k, 1), round(cy * k, 1)], "r_m": round(float(e.dxf.radius), 3),
                         "r_px": round(float(e.dxf.radius) * tr.s * k, 1),
                         "a": [round(float(e.dxf.start_angle), 1), round(float(e.dxf.end_angle), 1)]})
    return {"stem": stem, "png": f"data/swiss_dwellings/{stem}.png", "px_per_m": round(tr.s * k, 3),
            "rms_pt": round(tr.rms_pt, 3), "doors": [px(it.bbox) for it in fm.items["door"]],
            "windows": [px(it.bbox) for it in fm.items["window"]], "n_window_polys": fm.raw_counts.get("WINDOW:LWPOLYLINE", 0),
            "arcs": arcs, "warnings": fm.warnings}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    stems = sorted({Path(q.path).stem for q in load_split(a.split) if q.source == "swiss_dwellings"})
    random.Random(a.seed).shuffle(stems)
    n = 0
    with open(a.out, "w") as f:
        for s in stems:
            g = gold(s)
            if g is None:
                continue
            f.write(json.dumps(g) + "\n")
            n += 1
            if n >= a.n:
                break
    print(n, "floors ->", a.out)


if __name__ == "__main__":
    main()
