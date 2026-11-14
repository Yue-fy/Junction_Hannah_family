"""Scale of a raster floor plan that prints no scale: door widths and wall thickness vs printed room areas.

Ground truth (no dataset labels): areas printed on the plan (find_areas.py, VLM OCR with boxes) matched to CC5K room
regions (artifacts/R1/cc5k_seg/<stem>.npz, 'rooms' map at image resolution):
  room-level   s = sqrt(region_px / printed_m2) for an area text inside one room region
  total-level  s = sqrt(all interior px / printed_m2) for one apartment total ("3h+k+s 85 m2")
Estimators (px per metre), each a feature divided by a constant fitted on the FIT half (hash of path):
  door   median long side of CC5K door boxes (artifacts/R1/cc5k_counts.jsonl) / w0
  wall   median wall thickness on the wall map's ridge (2 x distance transform) / t0
  const  one px/m for every plan (the 'typical scan resolution' baseline)
End-to-end: area of each printed room from its region and the door scale vs the printed m².

    python experiments/r1/raster_scale/raster_scale.py [--areas PATH] [--dump PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics as st
from pathlib import Path

import cv2
import numpy as np

SHARED = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
ART = SHARED / "artifacts" / "R1"
INTERIOR = (3, 4, 5, 6, 7, 9, 10, 11)  # kitchen living bed bath entry storage garage undefined
NAMES = {1: "outdoor", 2: "wall", 3: "kitchen", 4: "living", 5: "bedroom", 6: "bath", 7: "entry", 8: "railing",
         9: "storage", 10: "garage", 11: "undefined"}
TOTAL = re.compile(r"\d\s*[hH]\s*\+|yht|total|asunto|huoneisto|=\s*\d", re.I)


def fit_half(path: str) -> bool:
    return int(hashlib.md5(path.encode()).hexdigest(), 16) % 2 == 0


def instances(rooms: np.ndarray, min_px: int = 30):
    inst = np.zeros(rooms.shape, np.int32)
    meta = {}
    nid = 0
    for c in INTERIOR:
        m = (rooms == c).astype(np.uint8)
        if not m.any():
            continue
        n, lab, stats, cent = cv2.connectedComponentsWithStats(m, connectivity=4)
        for k in range(1, n):
            a = int(stats[k, cv2.CC_STAT_AREA])
            if a < min_px:
                continue
            nid += 1
            inst[lab == k] = nid
            x, y, w, h = (int(v) for v in stats[k, :4])
            meta[nid] = {"cls": NAMES[c], "px": a, "bbox": [x, y, x + w, y + h],
                         "c": [round(float(cent[k][0]), 1), round(float(cent[k][1]), 1)]}
    return inst, meta


def room_at(inst: np.ndarray, box, r: int = 12) -> int:
    cx, cy = int((box[0] + box[2]) / 2), int((box[1] + box[3]) / 2)
    h, w = inst.shape
    if not (0 <= cx < w and 0 <= cy < h):
        return 0
    if inst[cy, cx]:
        return int(inst[cy, cx])
    win = inst[max(0, cy - r):cy + r + 1, max(0, cx - r):cx + r + 1].ravel()
    win = win[win > 0]
    return int(np.bincount(win).argmax()) if win.size else 0


def wall_thickness(rooms: np.ndarray) -> float | None:
    m = (rooms == 2).astype(np.uint8)
    if m.sum() < 100:
        return None
    d = cv2.distanceTransform(m, cv2.DIST_L2, 5)
    ridge = (d >= cv2.dilate(d, np.ones((3, 3), np.uint8))) & (d >= 1.0)
    v = d[ridge]
    return float(2 * np.median(v)) if v.size else None


def door_width(rec: dict) -> tuple[float | None, int]:
    bx = rec.get("counts", {}).get("doors", {}).get("boxes", [])
    ls = [max(b[2] - b[0], b[3] - b[1]) for b in bx]
    return (float(st.median(ls)), len(ls)) if ls else (None, 0)


def q(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--areas", default=str(ART / "raster_scale" / "areas.jsonl"))
    ap.add_argument("--dump", default=str(ART / "raster_scale" / "truth.jsonl"))
    ap.add_argument("--max-spread", type=float, default=1.35)
    ap.add_argument("--min-doors", type=int, default=2)
    ap.add_argument("--write-calib", action="store_true", help="write the door constant + band to calib.json")
    a = ap.parse_args()

    counts = {}
    for l in open(ART / "cc5k_counts.jsonl"):
        r = json.loads(l)
        counts[r["path"]] = r

    rows = []
    for l in open(a.areas):
        d = json.loads(l)
        if not d.get("areas"):
            continue
        stem = Path(d["path"]).stem
        npz = ART / "cc5k_seg" / f"{stem}.npz"
        if not npz.exists():
            continue
        rooms = np.load(npz)["rooms"]
        inst, meta = instances(rooms)
        interior_px = int(sum(m["px"] for m in meta.values()))
        per_room, totals, used = [], [], {}
        for ar in d["areas"]:
            if not (0.5 <= ar["m2"] <= 1000):
                continue
            if TOTAL.search(ar["text"]) or ar["m2"] >= 40:  # "3h+k+s 85 m2", or too big for one room
                totals.append(ar)
                continue
            rid = room_at(inst, ar["box"])
            if rid:
                used.setdefault(rid, []).append(ar)
            elif ar["m2"] >= 20:  # printed outside every room region: a plan/apartment total
                totals.append(ar)
        for rid, ars in used.items():
            if len(ars) != 1 or meta[rid]["px"] < 200:
                continue
            m2 = ars[0]["m2"]
            per_room.append({"rid": rid, "cls": meta[rid]["cls"], "px": meta[rid]["px"], "m2": m2,
                             "s": math.sqrt(meta[rid]["px"] / m2), "text": ars[0]["text"], "box": ars[0]["box"]})
        # robust room-level scale: median, keep rooms within 15% of it, need >= 2 kept and >= half kept
        s_room, spread = None, None
        if len(per_room) >= 2:
            med = st.median([p["s"] for p in per_room])
            kept = [p for p in per_room if abs(math.log(p["s"] / med)) <= math.log(1.15)]
            for p in per_room:
                p["kept"] = p in kept
            if len(kept) >= 2 and 2 * len(kept) >= len(per_room):
                s_room = st.median([p["s"] for p in kept])
                spread = max(p["s"] for p in kept) / min(p["s"] for p in kept)
        uniq = []  # one total per printed position (OCR may repeat a line); several apartments -> their sum
        for t in totals:
            c = ((t["box"][0] + t["box"][2]) / 2, (t["box"][1] + t["box"][3]) / 2)
            if all(abs(c[0] - u[0]) > 10 or abs(c[1] - u[1]) > 10 for u, _ in uniq):
                uniq.append((c, t["m2"]))
        s_tot = math.sqrt(interior_px / sum(m for _, m in uniq)) if uniq else None
        totals = [m for _, m in uniq]
        dw, nd = door_width(counts.get(d["path"], {}))
        wt = wall_thickness(rooms)
        rows.append({"path": d["path"], "size": d["size"], "style": stem.rsplit("-", 1)[0], "fit": fit_half(d["path"]),
                     "per_room": per_room, "s_room": s_room, "spread": spread, "s_tot": s_tot,
                     "totals": totals, "interior_px": interior_px, "door_px": dw, "n_doors": nd, "wall_px": wt})

    Path(a.dump).parent.mkdir(parents=True, exist_ok=True)
    with open(a.dump, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    # ---- ground truth sanity: room-level vs total-level where both exist
    both = [r for r in rows if r["s_room"] and r["s_tot"] and r["spread"] <= a.max_spread]
    if both:
        lr = [math.log(r["s_tot"] / r["s_room"]) for r in both]
        print(f"truth check: {len(both)} plans with both room-level and total-level scale; "
              f"total/room scale median {math.exp(st.median(lr)):.3f}, |log| p50 {q([abs(x) for x in lr], .5):.3f} "
              f"p80 {q([abs(x) for x in lr], .8):.3f}")

    for r in rows:
        if r["s_room"] and r["spread"] <= a.max_spread:
            r["truth"], r["truth_kind"] = r["s_room"], "room"
        elif r["s_tot"]:
            r["truth"], r["truth_kind"] = r["s_tot"], "total"
        else:
            r["truth"], r["truth_kind"] = None, None
    ok = [r for r in rows if r["truth"]]
    print(f"{len(rows)} plans with a printed area; {len(ok)} with a usable true scale "
          f"(room-level {sum(r['truth_kind'] == 'room' for r in ok)}, total-level {sum(r['truth_kind'] == 'total' for r in ok)})")
    if not ok:
        return
    print("true px/m: p10 %.1f p50 %.1f p90 %.1f (spread of plan resolutions)" %
          (q([r["truth"] for r in ok], .1), q([r["truth"] for r in ok], .5), q([r["truth"] for r in ok], .9)))

    feats = {
        "door": lambda r: r["door_px"],
        "wall": lambda r: r["wall_px"],
        "door+wall": lambda r: math.sqrt(r["door_px"] * r["wall_px"]) if r["door_px"] and r["wall_px"] else None,
        "const": lambda r: 1.0,
    }
    calib = {}
    for name, fn in feats.items():
        usable = [r for r in ok if fn(r) and (name != "door" or r["n_doors"] >= a.min_doors)]
        if sum(r["fit"] for r in usable) < 5 or sum(not r["fit"] for r in usable) < 5:
            print(f"{name}: too few ({len(usable)})")
            continue
        res, cov_hits = [], 0
        for half in (True, False):  # 2-fold cross-fit: constant + band from one half, errors on the other
            fit = [r for r in usable if r["fit"] == half]
            chk = [r for r in usable if r["fit"] != half]
            c = st.median([math.log(fn(r) / r["truth"]) for r in fit])  # feature = e^c * s
            rf = [math.log(fn(r) / math.exp(c) / r["truth"]) for r in fit]
            lo_h, hi_h = q(rf, .1), q(rf, .9)
            rc = [math.log(fn(r) / math.exp(c) / r["truth"]) for r in chk]
            res += rc
            cov_hits += sum(lo_h <= x <= hi_h for x in rc)
        c = st.median([math.log(fn(r) / r["truth"]) for r in usable])  # final constant: all plans
        rall = [math.log(fn(r) / math.exp(c) / r["truth"]) for r in usable]
        lo, hi = q(rall, .1), q(rall, .9)
        aerr = [abs(math.exp(-2 * x) - 1) for x in res]
        cov = cov_hits / len(res)
        const_m = math.exp(c)
        calib[name] = {"const": const_m, "log_resid_80": [lo, hi], "n": len(usable),
                       "area_err_p50": q(aerr, .5), "within10_area": sum(e <= .1 for e in aerr) / len(aerr),
                       "within20_area": sum(e <= .2 for e in aerr) / len(aerr), "coverage80_crossfit": cov}
        chk = res
        unit = {"door": "m door width", "wall": "m wall thickness", "door+wall": "", "const": "px/m"}[name]
        print(f"{name:9s} constant {const_m if name != 'const' else 1 / const_m:.3f} {unit} | cross-fit n={len(chk)}: "
              f"area err p50 {100 * q(aerr, .5):.1f}%  within 10% {100 * sum(e <= .1 for e in aerr) / len(aerr):.0f}%  "
              f"within 20% {100 * sum(e <= .2 for e in aerr) / len(aerr):.0f}%  | 80% interval from fit: area x"
              f"[{math.exp(-2 * hi):.2f}, {math.exp(-2 * lo):.2f}], cross-fit coverage {100 * cov:.0f}%")

    # ---- the 'typical apartment' guess (what a VLM does with no scale): median printed total of the other half
    tots = [r for r in ok if r["truth_kind"] == "total" and r["door_px"] and r["n_doors"] >= a.min_doors]
    if len(tots) >= 10:
        g_err, d_err = [], []
        for half in (True, False):
            fit = [r for r in tots if r["fit"] == half]
            chk = [r for r in tots if r["fit"] != half]
            g = st.median([sum(r["totals"]) for r in fit])
            c = st.median([math.log(r["door_px"] / r["truth"]) for r in fit])
            for r in chk:
                v = sum(r["totals"])
                g_err.append(abs(g / v - 1))
                d_err.append(abs(r["interior_px"] / (r["door_px"] / math.exp(c)) ** 2 / v - 1))
        print(f"apartment total area, {len(tots)} plans (cross-fit): typical-apartment guess err p50 "
              f"{100 * q(g_err, .5):.1f}% (within 10% {100 * sum(e <= .1 for e in g_err) / len(g_err):.0f}%) vs door "
              f"scale p50 {100 * q(d_err, .5):.1f}% (within 10% {100 * sum(e <= .1 for e in d_err) / len(d_err):.0f}%, "
              f"within 20% {100 * sum(e <= .2 for e in d_err) / len(d_err):.0f}%)")
    kinds = {}
    for r in ok:
        if r["door_px"] and r["n_doors"] >= a.min_doors:
            kinds.setdefault(r["truth_kind"], []).append(r["door_px"] / r["truth"])
    for k, v in kinds.items():
        print(f"implied door opening (m) from {k}-level truth: n={len(v)} p25 {q(v, .25):.2f} p50 {q(v, .5):.2f} "
              f"p75 {q(v, .75):.2f}")
    if a.write_calib and "door" in calib:
        d = calib["door"]
        out = {"w0_m": round(d["const"], 4), "log_resid_80": [round(d["log_resid_80"][0], 4), round(d["log_resid_80"][1], 4)],
               "n_fit": d["n"], "within10_area_check": round(d["within10_area"], 3),
               "within20_area_check": round(d["within20_area"], 3), "area_err_p50_check": round(d["area_err_p50"], 4),
               "coverage80_crossfit": round(d["coverage80_crossfit"], 3), "min_doors": a.min_doors,
               "source": "experiments/r1/raster_scale/raster_scale.py on TRAIN cubicasa plans with printed areas"}
        Path(__file__).with_name("calib.json").write_text(json.dumps(out, indent=1) + "\n")
        print("wrote", Path(__file__).with_name("calib.json"), out)

    # ---- end-to-end: each printed room's area from its CC5K region and the door scale (fit constant from FIT half)
    fit = [r for r in ok if r["fit"] and r["door_px"]]
    c = st.median([math.log(r["door_px"] / r["truth"]) for r in fit])
    errs, errs_true = [], []
    for r in rows:
        if r["fit"] or not r["door_px"]:
            continue
        s = r["door_px"] / math.exp(c)
        for p in r["per_room"]:
            errs.append(abs(p["px"] / s ** 2 / p["m2"] - 1))
            if r.get("truth"):
                errs_true.append(abs(p["px"] / r["truth"] ** 2 / p["m2"] - 1))
    if errs:
        print(f"end-to-end room area (CHECK half, {len(errs)} printed rooms): door scale -> err p50 {100 * q(errs, .5):.1f}%, "
              f"within 10% {100 * sum(e <= .1 for e in errs) / len(errs):.0f}%, within 20% "
              f"{100 * sum(e <= .2 for e in errs) / len(errs):.0f}%")
    if errs_true:
        print(f"  segmentation-only error (true scale of the same plan; optimistic, the room is part of its own "
              f"truth): p50 {100 * q(errs_true, .5):.1f}%")


if __name__ == "__main__":
    main()
