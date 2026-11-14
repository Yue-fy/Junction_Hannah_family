"""'Nothing printed' end-to-end: white out every printed area on plans whose truth is a printed apartment total, then
compare (a) what the pipeline does today for such a question (the base VLM's answer, vlm_direct) with (b) the door
estimate (cross-fit constant) and (c) the shrunk door estimate. Gold = the printed total(s) we removed.

    python experiments/r1/raster_scale/masked_eval.py make    # masked PNGs + ad-hoc question file
    python -m stoa.eval --solver vlm_direct --split <questions.jsonl> --no-leaderboard --workers 4
    python experiments/r1/raster_scale/masked_eval.py score artifacts/eval/<run>.jsonl
"""

from __future__ import annotations

import json
import math
import os
import statistics as st
import sys
from pathlib import Path

from PIL import Image, ImageDraw

SHARED = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
DATA = Path(os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset"))
ART = SHARED / "artifacts" / "R1" / "raster_scale"
MASKED = ART / "masked"
QFILE = ART / "masked_questions.jsonl"
Q = "What is the total floor area of this apartment in square metres?"


def q(xs, p):
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def truth_rows():
    return [r for r in map(json.loads, open(ART / "truth.jsonl"))
            if r.get("s_tot") and r["totals"] and r["door_px"] and r["n_doors"] >= 2]


def make():
    areas = {d["path"]: d for d in map(json.loads, open(ART / "areas.jsonl")) if d.get("areas")}
    MASKED.mkdir(parents=True, exist_ok=True)
    rows = truth_rows()
    with open(QFILE, "w") as f:
        for r in rows:
            img = Image.open(DATA / r["path"]).convert("RGB")
            dr = ImageDraw.Draw(img)
            for a in areas[r["path"]]["areas"]:
                x0, y0, x1, y1 = a["box"]
                dr.rectangle([x0 - 4, y0 - 4, x1 + 4, y1 + 4], fill="white")
            out = MASKED / Path(r["path"]).name
            img.save(out)
            f.write(json.dumps({"qid": "r1m-" + Path(r["path"]).stem, "path": str(out), "question": Q,
                                "answer": round(sum(r["totals"]), 2), "type": "area", "unit": "m2"}) + "\n")
    print(f"{len(rows)} masked plans → {QFILE}")


def score(run: str):
    rows = {r["path"]: r for r in truth_rows()}
    by_name = {Path(p).name: r for p, r in rows.items()}
    preds = {Path(p["path"]).name: p for p in map(json.loads, open(run))}
    # cross-fit door constant (halves by path hash, as raster_scale.py) + typical apartment for the blend
    halves = {h: [r for r in rows.values() if r["fit"] == h] for h in (True, False)}
    cal = {}
    for h, rs in halves.items():
        c = st.median([math.log(r["door_px"] / r["s_tot"]) for r in rs])
        g = st.median([sum(r["totals"]) for r in rs])
        vd = st.pvariance([-2 * math.log(r["door_px"] / math.exp(c) / r["s_tot"]) for r in rs])
        vg = st.pvariance([math.log(g / sum(r["totals"])) for r in rs])
        cal[h] = (c, g, vg / (vg + vd))
    e_vlm, e_door, e_blend, n_none = [], [], [], 0
    for name, r in by_name.items():
        p = preds.get(name)
        gold = sum(r["totals"])
        c, g, w = cal[not r["fit"]]
        door = r["interior_px"] / (r["door_px"] / math.exp(c)) ** 2
        blend = math.exp(w * math.log(door) + (1 - w) * math.log(g))
        e_door.append(abs(door / gold - 1))
        e_blend.append(abs(blend / gold - 1))
        v = p.get("value") if p else None
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = None
        if v is None or v <= 0:
            n_none += 1
            e_vlm.append(1.0)
        else:
            e_vlm.append(abs(v / gold - 1))
    for name, e in (("base VLM on the masked plan", e_vlm), ("door scale (cross-fit)", e_door),
                    ("door scale shrunk (cross-fit)", e_blend)):
        print(f"{name:32s} n={len(e)}  err p50 {100 * q(e, .5):5.1f}%  within 2% {100 * sum(x <= .02 for x in e) / len(e):4.0f}%  "
              f"within 10% {100 * sum(x <= .1 for x in e) / len(e):4.0f}%  within 20% {100 * sum(x <= .2 for x in e) / len(e):4.0f}%")
    print(f"(VLM gave no number on {n_none})")




def paired(run: str, reps: int = 2000):
    """Paired bootstrap (plans are independent): within-20% rate, shrunk door estimate minus base VLM."""
    import random
    rows = {Path(r["path"]).name: r for r in truth_rows()}
    preds = {Path(p["path"]).name: p for p in map(json.loads, open(run))}
    halves = {h: [r for r in rows.values() if r["fit"] == h] for h in (True, False)}
    cal = {}
    for h, rs in halves.items():
        c = st.median([math.log(r["door_px"] / r["s_tot"]) for r in rs])
        g = st.median([sum(r["totals"]) for r in rs])
        vd = st.pvariance([-2 * math.log(r["door_px"] / math.exp(c) / r["s_tot"]) for r in rs])
        vg = st.pvariance([math.log(g / sum(r["totals"])) for r in rs])
        cal[h] = (c, g, vg / (vg + vd))
    d = []
    for n, r in rows.items():
        gold = sum(r["totals"])
        c, g, w = cal[not r["fit"]]
        door = r["interior_px"] / (r["door_px"] / math.exp(c)) ** 2
        b = math.exp(w * math.log(door) + (1 - w) * math.log(g))
        try:
            v = float(preds[n]["value"])
        except (KeyError, TypeError, ValueError):
            v = -1
        d.append((abs(b / gold - 1) <= .2) - (v > 0 and abs(v / gold - 1) <= .2))
    rng = random.Random(0)
    bs = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(reps))
    print(f"within-20% gain, shrunk door − base VLM: {100 * sum(d) / len(d):+.1f} pts "
          f"[{100 * bs[int(.025 * reps)]:+.1f}, {100 * bs[int(.975 * reps)]:+.1f}] (n={len(d)})")


if __name__ == "__main__":
    {"make": lambda: make(), "score": lambda: score(sys.argv[2]), "paired": lambda: paired(sys.argv[2])}[sys.argv[1]]()
