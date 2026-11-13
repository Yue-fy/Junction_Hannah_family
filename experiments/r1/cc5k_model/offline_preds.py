"""Offline 'raster_cc5k' predictions in the eval-file format: start from a base run (e.g. the prior or the
pipeline on cc5k_heldout) and replace the answers of the symbol templates (windows, doors, WC seats, sinks)
by CC5K-model counts with the settings frozen on CC5K *val* drawings (count.py). Evidence = component boxes.
The output can be compared with the base run by experiments/r1/stats/compare.py (paired, cluster bootstrap).

Run: $JUNCTION_VENV/bin/python -I offline_preds.py BASE_RUN.jsonl OUT.jsonl [--tta] [--scale 1]
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import count as C  # noqa: E402

from config import FROZEN as _F  # noqa: E402

FROZEN = {t: (mf, k) for t, (_, mf, k) in _F.items()}  # frozen on CC5K val (count.py --tune val), plain, scale 1
NAMES = {"windows": "window", "doors": "door", "wc_seats": "toilet", "sinks": "sink"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("out")
    ap.add_argument("--tta", action="store_true")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--frozen", default="", help="JSON dict template -> [min_frac, kernel] overriding FROZEN")
    a = ap.parse_args()
    frozen = dict(FROZEN, **({k: tuple(v) for k, v in json.loads(a.frozen).items()} if a.frozen else {}))
    tag = ("tta_" if a.tta else "") + (f"s{a.scale:g}_" if a.scale != 1 else "")
    n_rep = 0
    with open(a.out, "w") as fo:
        for line in open(a.base):
            r = json.loads(line)
            t = C.tpl(r.get("question", ""))
            stem = os.path.basename(r["path"])[:-4]
            seg = os.path.join(C.SEG, tag + stem + ".npz")
            if t in frozen and r["source"] == "cubicasa5k" and os.path.exists(seg):
                icons = np.load(seg)["icons"]
                H, W = icons.shape
                mf, k = frozen[t]
                comps = [b for c in C.CLS[t] for b, _ in C.components(icons == c, max(1, mf * H * W), k)]
                r.update(value=len(comps), correct=(len(comps) == r["gold"]), solver="raster_cc5k(offline)",
                         evidence=[{"file": r["path"], "page": None, "bbox": [x, y, x + w, y + h],
                                    "note": f"{NAMES[t]} {i + 1}"} for i, (x, y, w, h) in enumerate(comps)],
                         trace=[f"CC5K multi-task model (pretrained, CC BY-NC), icon class {t}: "
                                f"{len(comps)} connected components (min_frac={mf}, open={k})"],
                         assumptions=["pretrained CubiCasa5K model; evaluated only on drawings outside its training list"],
                         confidence=None)
                n_rep += 1
            fo.write(json.dumps(r) + "\n")
    print(f"replaced {n_rep} answers -> {a.out}")


if __name__ == "__main__":
    main()
