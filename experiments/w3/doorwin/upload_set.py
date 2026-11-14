"""Door-count questions on every Swiss DEV floor with a PNG, gold = the DXF's door leaves (the dxf solver's count,
= the dataset's door answers; checked against the dev door questions below). For comparing raster door arcs with the
counting LoRA on the upload path (a Swiss PNG with no twin and no known source: Q 10:08). DEV only: cc-v3 was
trained on Swiss TRAIN counts.
Usage: python experiments/w3/doorwin/upload_set.py --split dev --out <file.jsonl>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from stoa.eval.splits import load_split  # noqa: E402
from stoa.solvers.vector import floor as F  # noqa: E402

D = os.environ["STOA_DATA"]
Q = "How many doors (interior doors and entrance doors together) are drawn on this floor plan?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    qs = [q for q in load_split(a.split) if q.source == "swiss_dwellings"]
    stems = sorted({Path(q.path).stem for q in qs})
    known = {Path(q.path).stem: q.answer for q in qs if "doors (interior doors and entrance" in q.question}
    n = agree = 0
    with open(a.out, "w") as f:
        for s in stems:
            base = os.path.join(D, "data/swiss_dwellings", s)
            if not all(os.path.exists(base + e) for e in (".dxf", ".png")):
                continue
            try:
                g = len(F.load_floor(base + ".dxf").items["door"])
            except Exception as e:  # noqa: BLE001
                print("skip", s, type(e).__name__)
                continue
            if s in known:
                agree += int(str(known[s]).strip() == str(g))
                if str(known[s]).strip() != str(g):
                    print("gold mismatch", s, known[s], g)
            f.write(json.dumps({"qid": f"dup-{s}", "path": f"data/swiss_dwellings/{s}.png", "question": Q,
                                "type": "count", "source": "swiss_dwellings", "answer": g, "unit": "count"}) + "\n")
            n += 1
    print(n, "floors ->", a.out, f"; dataset door questions agreeing with the DXF count: {agree}/{len(known)}")


if __name__ == "__main__":
    main()
