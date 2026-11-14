"""Runtime helper: metric scale of a raster floor plan that prints none, from its doors (no torch, cache only).

    from experiments.r1.raster_scale.scale import door_scale, room_regions, region_area_m2
    sc = door_scale("data/cubicasa5k/high_quality_architectural-7532.png")
    # {'px_per_m': 151.2, 'px_per_m_80': [..], 'area_factor_80': [lo, hi], 'n_doors': 3, 'door_px': 139.0,
    #  'boxes': [[x0,y0,x1,y1], ...], 'assumptions': [...], 'missing': [...], 'confidence': ...}
    regs = room_regions(path)                    # CC5K room regions: cls, px, bbox (image px), centroid
    region_area_m2(regs[0], sc)                  # -> (best, lo80, hi80) in m²

Inputs are precomputed for all 4,787 cubicasa drawings: door boxes in artifacts/R1/cc5k_counts.jsonl and room maps in
artifacts/R1/cc5k_seg/<stem>.npz (pretrained CubiCasa5K model, CC BY-NC 4.0; D8: cc5k=1 path only).
The constant W0 (median door opening in metres) and the 80% band come from raster_scale.py, fitted on TRAIN plans
whose printed room areas give the true scale (FIT half), and checked on the other half; see research/methods.md 8e.
Prefer a printed scale, dimension strings or printed room areas when the plan has them; this is the fallback.
"""

from __future__ import annotations

import json
import math
import os
import statistics as st
from functools import lru_cache
from pathlib import Path

SHARED = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
ART = SHARED / "artifacts" / "R1"
CALIB = Path(__file__).with_name("calib.json")
INTERIOR = {3: "kitchen", 4: "living", 5: "bedroom", 6: "bath", 7: "entry", 9: "storage", 10: "garage",
            11: "undefined"}


@lru_cache(maxsize=1)
def _calib() -> dict:
    return json.loads(CALIB.read_text())


@lru_cache(maxsize=1)
def _counts() -> dict:
    out = {}
    p = ART / "cc5k_counts.jsonl"
    if p.exists():
        for line in open(p):
            r = json.loads(line)
            out[r["path"]] = r
    return out


def _rel(path: str) -> str:
    p = str(path)
    i = p.rfind("data/cubicasa5k/")
    return p[i:] if i >= 0 else p


LIVE_MAPS = ART / "cc5k_seg_live"


def _record(path: str, live: bool = True) -> dict | None:
    """Cached CC5K record, else (live=True) one CPU run of predict.py via the adapter (also saves the room map)."""
    rec = _counts().get(_rel(path))
    if rec or not live:
        return rec
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cc5k_model"))
    try:
        import adapter
        os.environ.setdefault("CC5K_SAVE_MAPS", str(LIVE_MAPS))
        return adapter.counts_for(str(path))
    except Exception:  # noqa: BLE001  (no torch env / weights: no estimate)
        return None


def door_scale(path: str, min_doors: int = 2, room: bool = False) -> dict | None:
    """px per metre from the median CC5K door opening, or None (not a cached plan, or fewer than min_doors).

    room=False: constant + band fitted on printed APARTMENT totals (use for whole-plan areas and lengths).
    room=True: constant + band fitted on printed ROOM areas vs single CC5K regions (wider: region matching is noisy).
    """
    rec = _record(path)
    if not rec:
        return None
    boxes = rec.get("counts", {}).get("doors", {}).get("boxes", [])
    if len(boxes) < min_doors:
        return None
    c = _calib()
    w_px = float(st.median(max(b[2] - b[0], b[3] - b[1]) for b in boxes))
    w0 = c["w0_room_m"] if room else c["w0_m"]
    s = w_px / w0
    lo, hi = c["log_resid_80_room"] if room else c["log_resid_80"]  # log(s_est / s_true) band, cross-fit checked
    hit2 = c["room_within2_check"] if room else c["within2_area_check"]
    return {
        "px_per_m": round(s, 2),
        "px_per_m_80": [round(s / math.exp(hi), 2), round(s / math.exp(lo), 2)],
        "area_factor_80": [round(math.exp(2 * lo), 3), round(math.exp(2 * hi), 3)],  # true/est area multiplier
        "length_factor_80": [round(math.exp(lo), 3), round(math.exp(hi), 3)],
        "n_doors": len(boxes),
        "door_px": w_px,
        "boxes": boxes,
        "confidence": round(max(0.02, hit2), 3),  # P(area within the 2% scoring tolerance), measured
        "assumptions": [f"no scale printed; assumed the median door opening is {w0:.2f} m "
                        f"(fitted on {c['n_rooms'] if room else c['n_fit']} printed {'rooms' if room else 'apartment areas'}"
                        f" of training plans), {len(boxes)} doors measured"],
        "missing": ["a scale bar, dimension strings or printed room areas"],
    }


def room_regions(path: str, min_px: int = 200) -> list[dict]:
    """CC5K room regions (connected components of each interior class) with px area, bbox and centroid."""
    import cv2  # in $JUNCTION_VENV
    import numpy as np

    npz = ART / "cc5k_seg" / f"{Path(path).stem}.npz"
    if not npz.exists():
        npz = LIVE_MAPS / f"{Path(path).stem}.npz"
    if not npz.exists():
        return []
    rooms = np.load(npz)["rooms"]
    out = []
    for c, name in INTERIOR.items():
        m = (rooms == c).astype(np.uint8)
        if not m.any():
            continue
        n, lab, stats, cent = cv2.connectedComponentsWithStats(m, connectivity=4)
        for k in range(1, n):
            a = int(stats[k, cv2.CC_STAT_AREA])
            if a < min_px:
                continue
            x, y, w, h = (int(v) for v in stats[k, :4])
            out.append({"cls": name, "px": a, "bbox": [x, y, x + w, y + h],
                        "centroid": [round(float(cent[k][0]), 1), round(float(cent[k][1]), 1)]})
    return sorted(out, key=lambda r: -r["px"])


def region_area_m2(region: dict, sc: dict) -> tuple[float, float, float]:
    """Best estimate and 80% band (m²) of a region's area under the door scale."""
    a = region["px"] / sc["px_per_m"] ** 2
    lo, hi = sc["area_factor_80"]
    return round(a, 2), round(a * lo, 2), round(a * hi, 2)


ROOM_WORDS = {  # question word -> CC5K room class (sauna/WC are drawn inside 'bath' regions in CC5K)
    "kitchen": "kitchen", "keittiö": "kitchen", "living": "living", "olohuone": "living", "bedroom": "bedroom",
    "makuuhuone": "bedroom", "bath": "bath", "bathroom": "bath", "kylpyhuone": "bath", "entry": "entry",
    "hall": "entry", "eteinen": "entry", "storage": "storage", "varasto": "storage", "garage": "garage",
}


def estimate_area(path: str, target: str = "apartment") -> dict | None:
    """Best estimate + 80% band of the apartment's (or one room class's) floor area on a plan with no scale.

    target 'apartment' sums every interior region (no balconies); a room word sums that class's regions and
    reports each region separately (the caller picks one when the question names it). Returns None if the plan is
    not cached or has fewer than 2 detected doors. Evidence: the measured regions and the doors used for scale.
    """
    cls = None if target == "apartment" else ROOM_WORDS.get(target.lower(), target.lower())
    sc = door_scale(path, room=cls is not None)
    if not sc:
        return None
    regs = room_regions(path)
    use = [r for r in regs if cls is None or r["cls"] == cls]
    if not use:
        return None
    px = sum(r["px"] for r in use)
    best = px / sc["px_per_m"] ** 2
    lo, hi = sc["area_factor_80"]
    what = "all interior rooms (balconies excluded)" if cls is None else f"{len(use)} '{cls}' region(s)"
    c = _calib()
    shrink = []
    if cls is None and "blend_w" in c:  # whole apartment: shrink toward the typical apartment (cross-fit: less error)
        door_only = best
        w, g = c["blend_w"], c["typical_apartment_m2"]
        best = math.exp(w * math.log(best) + (1 - w) * math.log(g))
        lo, hi = (math.exp(v) for v in c["blend_log_true_over_est_80"])
        shrink = [f"door-scale area {door_only:.1f} m² shrunk toward the typical training apartment ({g:.0f} m²) "
                  f"with weight {1 - w:.2f}, because the door scale alone errs by ~{100 * c['area_err_p50_check']:.0f}% (median)"]
    return {
        "value": round(best, 1), "unit": "m2", "interval80": [round(best * lo, 1), round(best * hi, 1)],
        "confidence": sc["confidence"],
        "regions": [{"cls": r["cls"], "m2": round(r["px"] / sc["px_per_m"] ** 2, 1), "bbox": r["bbox"]} for r in use],
        "door_boxes": sc["boxes"],
        "assumptions": sc["assumptions"] + [f"area = pixel area of {what} from the CubiCasa5K room segmentation"]
        + shrink,
        "missing": sc["missing"],
    }


def printed_areas(path: str, backend: str = "local") -> list[dict]:
    """Areas printed on the plan ('12,5 m²', '3h+k+s 85 m2') with image-px boxes: ONE local VLM call (cached).

    When the plan prints the asked area, that number is the answer (exact) and its box is the evidence; the door
    estimate above is then only a cross-check ('door scale says 79 m², 80%: 59–120 ✓'). Each item gets the CC5K
    room class under its box when the map is cached ('room'), and 'total' when it looks like an apartment total.
    """
    import sys
    from PIL import Image

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from stoa import llm
    from experiments.r1.raster_scale.find_areas import PROMPT, parse, upscale
    from experiments.r1.raster_scale.raster_scale import TOTAL, instances, room_at

    data = Path(os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset"))
    p = Path(path) if Path(path).is_absolute() else data / _rel(path)
    img = Image.open(p).convert("RGB")
    r = llm.chat(PROMPT, images=[upscale(img)], backend=backend, max_tokens=600, max_pixels=6_000_000, cache=True,
                 extra_body={"repetition_penalty": 1.05})
    items = parse(r.text, *img.size)
    npz = ART / "cc5k_seg" / f"{Path(path).stem}.npz"
    if npz.exists():
        import numpy as np
        inst, meta = instances(np.load(npz)["rooms"])
        for it in items:
            rid = room_at(inst, it["box"])
            it["room"] = meta[rid]["cls"] if rid else None
    for it in items:
        it["total"] = bool(TOTAL.search(it["text"])) or it["m2"] >= 40
    return items
