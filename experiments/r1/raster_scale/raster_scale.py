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


def door_variants(rec: dict) -> dict:
    """Pre-chosen alternatives to the median (compared once on the full set, not tuned)."""
    bx = rec.get("counts", {}).get("doors", {}).get("boxes", [])
    ls = sorted(max(b[2] - b[0], b[3] - b[1]) for b in bx)
    asp = sorted(max(b[2] - b[0], b[3] - b[1]) for b in bx
                 if max(b[2] - b[0], b[3] - b[1]) >= 2 * max(1, min(b[2] - b[0], b[3] - b[1])))
    out = {}
    if len(ls) >= 2:
        out["door_q40"] = q(ls, .4)
        k = len(ls) // 4
        mid = ls[k:len(ls) - k] or ls
        out["door_iqm"] = sum(mid) / len(mid)
    if len(asp) >= 2:
        out["door_aspect2"] = float(st.median(asp))
    return out


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
        dv = door_variants(counts.get(d["path"], {}))
        rows.append({**dv, "cc5k_list": counts.get(d["path"], {}).get("cc5k_list"), "path": d["path"], "size": d["size"], "style": stem.rsplit("-", 1)[0], "fit": fit_half(d["path"]),
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
        "door_q40": lambda r: r.get("door_q40") if r["n_doors"] >= a.min_doors else None,
        "door_iqm": lambda r: r.get("door_iqm") if r["n_doors"] >= a.min_doors else None,
        "door_aspect2": lambda r: r.get("door_aspect2"),
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
                       "within2_area": sum(e <= .02 for e in aerr) / len(aerr),
                       "within20_area": sum(e <= .2 for e in aerr) / len(aerr), "coverage80_crossfit": cov}
        chk = res
        unit = {"door": "m door width", "wall": "m wall thickness", "const": "px/m"}.get(name, "")
        print(f"{name:9s} constant {const_m if name != 'const' else 1 / const_m:.3f} {unit} | cross-fit n={len(chk)}: "
              f"area err p50 {100 * q(aerr, .5):.1f}%  within 10% {100 * sum(e <= .1 for e in aerr) / len(aerr):.0f}%  "
              f"within 20% {100 * sum(e <= .2 for e in aerr) / len(aerr):.0f}%  | 80% band, true area = est x"
              f"[{math.exp(2 * lo):.2f}, {math.exp(2 * hi):.2f}], cross-fit coverage {100 * cov:.0f}%")

    # ---- D8 leak check: is the door-scale error different on plans CC5K saw in pretraining (train list)?
    if "door" in calib:
        c = math.log(calib["door"]["const"])
        for lst in ("train", "val", "test"):
            e = [abs(math.exp(-2 * math.log(r["door_px"] / math.exp(c) / r["truth"])) - 1) for r in ok
                 if r["cc5k_list"] == lst and r["door_px"] and r["n_doors"] >= a.min_doors]
            if e:
                print(f"door-scale area err on CC5K-{lst} plans: n={len(e)} p50 {100 * q(e, .5):.1f}% "
                      f"within 20% {100 * sum(x <= .2 for x in e) / len(e):.0f}%")

    # ---- the 'typical apartment' guess (what a VLM does with no scale): median printed total of the other half
    tots = [r for r in ok if r["truth_kind"] == "total" and r["door_px"] and r["n_doors"] >= a.min_doors]
    blend_cal = {}
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
        # shrinkage: log-blend of the door estimate and the typical apartment (weight w on the door estimate)
        for w in (0.5, 0.7, 0.85, "var"):
            b_err, ws = [], []
            for half in (True, False):
                fit = [r for r in tots if r["fit"] == half]
                g = st.median([sum(r["totals"]) for r in fit])
                c = st.median([math.log(r["door_px"] / r["truth"]) for r in fit])
                if w == "var":
                    vd = st.pvariance([-2 * math.log(r["door_px"] / math.exp(c) / r["truth"]) for r in fit])
                    vg = st.pvariance([math.log(g / sum(r["totals"])) for r in fit])
                    wh = vg / (vg + vd)
                    ws.append(round(wh, 2))
                else:
                    wh = w
                for r in (r for r in tots if r["fit"] != half):
                    de = r["interior_px"] / (r["door_px"] / math.exp(c)) ** 2
                    b_err.append(abs(math.exp(wh * math.log(de) + (1 - wh) * math.log(g)) / sum(r["totals"]) - 1))
            print(f"  blend w={w}{ws if ws else ''}: err p50 {100 * q(b_err, .5):.1f}%, within 10% {100 * sum(e <= .1 for e in b_err) / len(b_err):.0f}%,"
                  f" within 20% {100 * sum(e <= .2 for e in b_err) / len(b_err):.0f}%")
        # final blend for calib.json: all plans; weight from variances; band = quantiles of log(true / blend)
        g_all = st.median([sum(r["totals"]) for r in tots])
        c_all = st.median([math.log(r["door_px"] / r["truth"]) for r in tots])
        vd = st.pvariance([-2 * math.log(r["door_px"] / math.exp(c_all) / r["truth"]) for r in tots])
        vg = st.pvariance([math.log(g_all / sum(r["totals"])) for r in tots])
        w_all = vg / (vg + vd)
        lres = [math.log(sum(r["totals"]) / math.exp(w_all * math.log(r["interior_px"] / (r["door_px"] / math.exp(c_all)) ** 2)
                                                      + (1 - w_all) * math.log(g_all))) for r in tots]
        blend_cal = {"typical_apartment_m2": round(g_all, 1), "blend_w": round(w_all, 3),
                     "blend_log_true_over_est_80": [round(q(lres, .1), 4), round(q(lres, .9), 4)],
                     "n_totals": len(tots)}
        print(f"  final blend: typical {g_all:.1f} m2, w {w_all:.2f}, 80% band true/est x[{math.exp(q(lres, .1)):.2f}, "
              f"{math.exp(q(lres, .9)):.2f}] (in-sample)")
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
               "within2_area_check": round(d["within2_area"], 3),
               "within20_area_check": round(d["within20_area"], 3), "area_err_p50_check": round(d["area_err_p50"], 4),
               "coverage80_crossfit": round(d["coverage80_crossfit"], 3), "min_doors": a.min_doors,
               "source": "experiments/r1/raster_scale/raster_scale.py on TRAIN cubicasa plans with printed areas",
               **blend_cal}
        Path(__file__).with_name("calib.json").write_text(json.dumps(out, indent=1) + "\n")
        print("wrote", Path(__file__).with_name("calib.json"), out)

    # ---- end-to-end: each printed ROOM's area = its CC5K region px / s², with a ROOM constant w0_room fitted on the
    # other half's printed rooms (regions are smaller than printed net areas, so the apartment constant is biased).
    def room_w(r, p):  # implied door opening (m) for one printed room
        return r["door_px"] / math.sqrt(p["px"] / p["m2"])
    pool = [r for r in rows if r["door_px"] and r["n_doors"] >= a.min_doors and r["per_room"]]
    errs, inband, seg, by_cls = [], 0, [], {}
    for half in (True, False):
        fit = [math.log(room_w(r, p)) for r in pool if r["fit"] == half for p in r["per_room"]]
        if len(fit) < 10:
            continue
        c = st.median(fit)
        lo, hi = q([x - c for x in fit], .1), q([x - c for x in fit], .9)
        for r in pool:
            if r["fit"] == half:
                continue
            s_est = r["door_px"] / math.exp(c)
            for p in r["per_room"]:
                ratio = p["px"] / s_est ** 2 / p["m2"]  # est / printed
                errs.append(abs(ratio - 1))
                by_cls.setdefault(p["cls"], []).append(abs(ratio - 1))
                inband += math.exp(2 * lo) <= 1 / ratio <= math.exp(2 * hi)  # true/est = exp(2r)
                if r.get("truth_kind") == "total":  # segmentation-only error at the plan's (non-circular) true scale
                    seg.append(abs(p["px"] / r["truth"] ** 2 / p["m2"] - 1))
    if errs:
        allw = [math.log(room_w(r, p)) for r in pool for p in r["per_room"]]
        print(f"end-to-end printed ROOM areas (cross-fit, {len(errs)} rooms on {len(pool)} plans; room constant "
              f"{math.exp(st.median(allw)):.3f} m): err p50 {100 * q(errs, .5):.1f}%, within 10% "
              f"{100 * sum(e <= .1 for e in errs) / len(errs):.0f}%, within 20% {100 * sum(e <= .2 for e in errs) / len(errs):.0f}%, "
              f"printed value inside the 80% band {100 * inband / len(errs):.0f}%")
        print("  by CC5K region class: " + ", ".join(f"{k} n={len(v)} p50 {100 * q(v, .5):.0f}%"
                                                      for k, v in sorted(by_cls.items(), key=lambda kv: -len(kv[1]))))
        if a.write_calib:
            cp = Path(__file__).with_name("calib.json")
            d = json.loads(cp.read_text()) if cp.exists() else {}
            cw = st.median(allw)
            d.update({"w0_room_m": round(math.exp(cw), 4), "log_resid_80_room":
                      [round(q([x - cw for x in allw], .1), 4), round(q([x - cw for x in allw], .9), 4)],
                      "n_rooms": len(allw), "room_err_p50_check": round(q(errs, .5), 4),
                      "room_within20_check": round(sum(e <= .2 for e in errs) / len(errs), 3),
                      "room_within2_check": round(sum(e <= .02 for e in errs) / len(errs), 3),
                      "room_band80_coverage_check": round(inband / len(errs), 3)})
            cp.write_text(json.dumps(d, indent=1) + "\n")
    if seg:
        print(f"  of which segmentation error alone (plans whose truth is a printed TOTAL, n={len(seg)} rooms): "
              f"p50 {100 * q(seg, .5):.1f}%, within 20% {100 * sum(e <= .2 for e in seg) / len(seg):.0f}%")


if __name__ == "__main__":
    main()
