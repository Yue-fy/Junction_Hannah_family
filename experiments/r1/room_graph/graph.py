"""Room graph of a raster floor plan (CubiCasa-style) from cached CC5K maps: rooms, openings, fixtures, links.

    from experiments.r1.room_graph.graph import room_graph, graph_text
    g = room_graph("data/cubicasa5k/high_quality_architectural-7532.png")
    # {'rooms': [{'id': 'R1', 'cls': 'living', 'px', 'bbox', 'centroid', 'm2', 'm2_80', 'label',
    #             'windows': [box..], 'doors': ['D3', ...], 'fixtures': {'toilet': [box], ...},
    #             'door_to': ['R4', 'outside'], 'open_to': ['R3'], 'wall_to': ['R2', ...]}, ...],
    #  'doors': [{'id': 'D1', 'box', 'between': ['R1', 'R4'] | ['R1', 'outside']}], 'windows': [{'box', 'room', 'side'}],
    #  'scale': door_scale(...) | None, 'unassigned': {...}, 'notes': [...]}
    print(graph_text(g))          # compact text for an LLM tool call / the demo card

Per-room questions the dataset never asks but a harder test may ("how many windows does the kitchen have?",
"which rooms open onto the hall?", "is the bathroom next to a bedroom?", "area of the largest bedroom?") become
lookups with evidence (region box + icon boxes). No torch, no LLM: it reads artifacts/R1/cc5k_seg/<stem>.npz
(maps from the pretrained CubiCasa5K model, CC BY-NC 4.0; D8: cc5k=1 path only) and the door boxes in
artifacts/R1/cc5k_counts.jsonl. Icon components use the FROZEN counting settings, so per-room counts sum to the
drawing-level detector counts. Room names come from the printed labels when a cached label read exists.

Assignment rules (geometry only, no tuning on any gold):
- fixture (toilet, sink, bathtub, sauna bench) -> the room under it (majority of room pixels under/around the icon);
- window -> the interior room that touches the window's wall ring most; side = 'exterior' if the ring also touches
  background/outdoor, else 'interior' (glazed partition);
- door -> the two rooms its wall ring touches most (edge), or one room + 'outside' (entrance / balcony door);
- open_to -> rooms whose regions touch directly over > ~half a wall length (open plan: kitchen <-> living);
- wall_to -> otherwise, rooms whose regions come within ~1.5 wall thicknesses of each other (share a wall).
Validation: validate.py (label <-> region agreement, plausibility rates); research/methods.md 8h.
"""

from __future__ import annotations

import json
import os
import statistics as st
from collections import Counter
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

SHARED = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
ART = SHARED / "artifacts" / "R1"
ROOM_CLS = {1: "outdoor", 3: "kitchen", 4: "living", 5: "bedroom", 6: "bath", 7: "entry", 9: "storage",
            10: "garage", 11: "undefined"}
INTERIOR = {k for k, v in ROOM_CLS.items() if v != "outdoor"}
# minimum region size as a fraction of H*W. Bedrooms keep the frozen room-count setting (CC5K val); baths/WCs and
# balconies use a small one because WC rooms are small (with 1.2e-2, 49 of 167 printed KH/PH/WC labels fell on no
# region: validate.py run 1); everything else 3e-3.
ROOM_MIN = {1: 5e-3, 5: 1.2e-2, 6: 2e-3}
ROOM_MIN_DEFAULT = 3e-3
# icon class -> (name, min area fraction, opening kernel); windows/doors/toilets/sinks = experiments/r1/cc5k_model/config.FROZEN
ICONS = {1: ("window", 2e-4, 5), 2: ("door", 2e-4, 0), 5: ("toilet", 2e-4, 5), 6: ("sink", 2e-5, 5),
         7: ("sauna_bench", 2e-4, 0), 9: ("bathtub", 2e-4, 0)}
FIXTURES = ("toilet", "sink", "bathtub", "sauna_bench")


def _rel(path: str) -> str:
    p = str(path)
    i = p.rfind("data/cubicasa5k/")
    return p[i:] if i >= 0 else p


def _npz(path: str, live: bool = False) -> Path | None:
    """Cached map with rooms + icons; live=True runs the CC5K model once on an uncached image (torch env, ~3-10 s
    CPU) and saves its maps to artifacts/R1/cc5k_seg_live/ (new drawings, e.g. a hidden test plan)."""
    for d in (ART / "cc5k_seg", ART / "cc5k_seg_live"):
        f = d / f"{Path(path).stem}.npz"
        if f.exists():
            with np.load(f) as z:
                if "icons" in z.files:
                    return f
    if not live:
        return None
    import subprocess
    import sys
    here = Path(__file__).resolve().parents[1] / "cc5k_model"
    py = os.environ.get("CC5K_PYTHON", "/data/User/fangy4/envs/junction-train/bin/python")
    data = Path(os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset"))
    full = Path(path) if Path(path).is_absolute() else data / path
    if not (Path(py).exists() and full.exists()):
        return None
    env = dict(os.environ, CC5K_SAVE_MAPS=str(ART / "cc5k_seg_live"))
    try:
        subprocess.run([py, "-I", str(here / "predict.py"), str(full)], env=env, capture_output=True, timeout=300,
                       check=True)
    except Exception as e:  # noqa: BLE001
        print(f"room_graph: live CC5K run failed: {type(e).__name__}", file=sys.stderr)
        return None
    return _npz(path, live=False)


def _components(mask: np.ndarray, min_area: float, k: int) -> list[tuple[np.ndarray, list[int]]]:
    m = mask.astype(np.uint8)
    if k:
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    out = []
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < min_area:
            continue
        x, y, w, h = (int(v) for v in stats[i, :4])
        out.append((lab[y:y + h, x:x + w] == i, [x, y, x + w, y + h]))
    return out


def _ring_labels(inst: np.ndarray, rooms: np.ndarray, comp: np.ndarray, box: list[int], r: int):
    """Room ids and outside-pixel count within r px of one component (cropped for speed)."""
    H, W = inst.shape
    x0, y0, x1, y1 = max(0, box[0] - r), max(0, box[1] - r), min(W, box[2] + r), min(H, box[3] + r)
    m = np.zeros((y1 - y0, x1 - x0), np.uint8)
    m[box[1] - y0:box[3] - y0, box[0] - x0:box[2] - x0] = comp.astype(np.uint8)
    ring = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))).astype(bool)
    ids = inst[y0:y1, x0:x1][ring]
    cls = rooms[y0:y1, x0:x1][ring]
    outside = int(((cls == 0) | (cls == 1)).sum())
    return Counter(int(v) for v in ids[ids > 0]), outside


def _wall_thickness(rooms: np.ndarray) -> float | None:
    m = (rooms == 2).astype(np.uint8)
    if m.sum() < 100:
        return None
    d = cv2.distanceTransform(m, cv2.DIST_L2, 5)
    ridge = (d >= cv2.dilate(d, np.ones((3, 3), np.uint8))) & (d >= 1.0)
    v = d[ridge]
    return float(2 * np.median(v)) if v.size else None


@lru_cache(maxsize=1)
def _labels_index() -> dict:
    """stem -> cached printed room labels [(text, cls, box)] from the label reader (R1 v2 outputs), if any."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    out = {}
    d = ART / "room_labels"
    if not d.exists():
        return out
    try:
        from stoa.solvers.raster.vlm import parse_labels
    except Exception:  # noqa: BLE001
        return out
    from PIL import Image
    data = Path(os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset"))
    for f in d.glob("*.labels.v2.json"):
        name = f.name.replace(".labels.v2.json", "")
        img = data / "data" / "cubicasa5k" / name
        if not img.exists():
            continue
        try:
            w, h = Image.open(img).size
            items, looped = parse_labels(json.loads(f.read_text())["text"], w, h)
        except Exception:  # noqa: BLE001
            continue
        if not looped:
            out[Path(name).stem] = [(i.text, i.cls, [round(v) for v in i.box]) for i in items]
    return out


def room_graph(path: str, labels: list | None = None, live: bool = True, printed: bool = False) -> dict | None:
    """Room graph of one plan, or None (no cached map and no live CC5K run). labels: optional [(text, cls, box)].

    printed=True also reads the areas printed on the plan (scale.printed_areas: ONE local VLM call, cached) and
    attaches each to the room under it ("printed_m2"); apartment totals go to g["printed_total"]."""
    f = _npz(path, live=live)
    if f is None:
        return None
    z = np.load(f)
    rooms, icons = z["rooms"], z["icons"]
    H, W = rooms.shape
    notes = []

    # ---- rooms: connected components of each room class -------------------------------------------------------
    inst = np.zeros(rooms.shape, np.int32)
    meta: dict[int, dict] = {}
    nid = 0
    for c, name in ROOM_CLS.items():
        m = (rooms == c).astype(np.uint8)
        if not m.any():
            continue
        n, lab, stats, cent = cv2.connectedComponentsWithStats(m, connectivity=4)
        for k in range(1, n):
            a = int(stats[k, cv2.CC_STAT_AREA])
            if a < ROOM_MIN.get(c, ROOM_MIN_DEFAULT) * H * W:
                continue
            nid += 1
            inst[lab == k] = nid
            x, y, w, h = (int(v) for v in stats[k, :4])
            meta[nid] = {"cls": name, "px": a, "bbox": [x, y, x + w, y + h],
                         "centroid": [round(float(cent[k][0])), round(float(cent[k][1]))],
                         "windows": [], "doors": [], "fixtures": {}, "door_to": [], "open_to": [], "wall_to": []}

    # ---- scale (door widths) and wall thickness ---------------------------------------------------------------
    sc = None
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from experiments.r1.raster_scale.scale import door_scale
        sc = door_scale(path, room=True)
    except Exception as e:  # noqa: BLE001
        notes.append(f"no door scale: {type(e).__name__}")
    wall = _wall_thickness(rooms) or 8.0
    r_open = int(max(4, round(1.0 * wall)))  # openings sit in walls: one wall thickness reaches both sides

    # ---- icons -------------------------------------------------------------------------------------------------
    doors, windows = [], []
    unassigned = Counter()
    for c, (name, frac, k) in ICONS.items():
        for comp, box in _components(icons == c, max(1, frac * H * W), k):
            if name in FIXTURES:
                ids, _ = _ring_labels(inst, rooms, comp, box, 3)
                ids = Counter({i: v for i, v in ids.items() if meta[i]["cls"] != "outdoor"}) or ids
                if not ids:
                    ids, _ = _ring_labels(inst, rooms, comp, box, 3 * r_open)
                if not ids:
                    unassigned[name] += 1
                    continue
                rid = ids.most_common(1)[0][0]
                meta[rid]["fixtures"].setdefault(name, []).append(box)
            elif name == "window":
                ids, outside = _ring_labels(inst, rooms, comp, box, r_open)
                inner = [(i, v) for i, v in ids.most_common() if meta[i]["cls"] != "outdoor"]
                side = "exterior" if outside > 0 or any(meta[i]["cls"] == "outdoor" for i in ids) else "interior"
                rid = inner[0][0] if inner else (ids.most_common(1)[0][0] if ids else None)
                windows.append({"box": box, "room": f"R{rid}" if rid else None, "side": side})
                if rid:
                    meta[rid]["windows"].append(box)
                else:
                    unassigned["window"] += 1
            else:  # door
                ids, outside = _ring_labels(inst, rooms, comp, box, r_open)
                top = [i for i, v in ids.most_common() if v >= max(3, 0.1 * max(ids.values()))][:2]
                did = f"D{len(doors) + 1}"
                between = [f"R{i}" for i in top]
                if len(between) == 1 and outside > 0:
                    between.append("outside")
                doors.append({"id": did, "box": box, "between": between})
                if not top:
                    unassigned["door"] += 1
                for i in top:
                    meta[i]["doors"].append(did)
                    others = [b for b in between if b != f"R{i}"]
                    meta[i]["door_to"].extend(o for o in others if o not in meta[i]["door_to"])

    # CC5K has no sauna class: saunas come out 'undefined' (38 of 44 printed SAUNA labels). A region with a sauna
    # bench in it is a sauna.
    for mt in meta.values():
        if mt["fixtures"].get("sauna_bench") and mt["cls"] in ("undefined", "bath"):
            mt["cls"] = "sauna" if mt["cls"] == "undefined" else mt["cls"]

    # ---- shared walls and open connections ----------------------------------------------------------------------
    r_wall = int(max(3, round(0.75 * wall)))  # each side grows 0.75 wall -> regions 1.5 walls apart meet
    r_touch = 2                               # regions that touch directly (no wall between): open plan

    def grow(r):
        out = {}
        for i, mt in meta.items():
            x0, y0, x1, y1 = mt["bbox"]
            x0, y0, x1, y1 = max(0, x0 - r), max(0, y0 - r), min(W, x1 + r), min(H, y1 + r)
            m = (inst[y0:y1, x0:x1] == i).astype(np.uint8)
            g = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
            out[i] = ((x0, y0, x1, y1), g.astype(bool))
        return out

    def overlap(ga_, gb_) -> int:
        (ax0, ay0, ax1, ay1), ga = ga_
        (bx0, by0, bx1, by1), gb = gb_
        x0, y0, x1, y1 = max(ax0, bx0), max(ay0, by0), min(ax1, bx1), min(ay1, by1)
        if x0 >= x1 or y0 >= y1:
            return 0
        return int((ga[y0 - ay0:y1 - ay0, x0 - ax0:x1 - ax0] & gb[y0 - by0:y1 - by0, x0 - bx0:x1 - bx0]).sum())

    g_wall, g_touch = grow(r_wall), grow(r_touch)
    ids = sorted(meta)
    for a_i, a in enumerate(ids):
        for b in ids[a_i + 1:]:
            if overlap(g_touch[a], g_touch[b]) >= 2 * r_touch * max(10.0, 0.5 * wall):  # open edge, no wall
                meta[a]["open_to"].append(f"R{b}")
                meta[b]["open_to"].append(f"R{a}")
            elif overlap(g_wall[a], g_wall[b]) >= 2 * wall:  # contact ~2 wall thicknesses long, not a corner
                meta[a]["wall_to"].append(f"R{b}")
                meta[b]["wall_to"].append(f"R{a}")

    # ---- names from printed labels -----------------------------------------------------------------------------
    if labels is None:
        labels = _labels_index().get(Path(path).stem)
    if labels:
        for text, lcls, box in labels:
            cx, cy = int((box[0] + box[2]) / 2), int((box[1] + box[3]) / 2)
            if 0 <= cx < W and 0 <= cy < H and inst[cy, cx]:
                meta[int(inst[cy, cx])].setdefault("labels", []).append(text)

    # ---- merged regions: two printed labels of the same room kind inside one region (a thin partition the
    # segmentation missed, e.g. 'MH 10.5' + 'MH 8.5' in one bedroom region) -> say so instead of answering per room
    try:
        from experiments.r1.room_graph.validate import expected
    except Exception:  # noqa: BLE001
        expected = None
    if expected:
        for mt in meta.values():
            kinds = Counter(expected(t) for t in mt.get("labels", []))
            kinds.pop(None, None)
            multi = {k: n for k, n in kinds.items() if n >= 2 and k not in ("entry", "storage", "outdoor")}
            if multi:
                mt["merged"] = multi

    # ---- printed label kind beats the CC5K class when they disagree (CC5K has no sauna class; thin rooms get
    # 'undefined'; e.g. a bedroom 'H' segmented as undefined). Only when the region's labels agree on one kind.
    if expected:
        import re as _re
        from experiments.r1.room_graph.validate import norm as _norm
        # codes validate.py leaves out because they are ambiguous for a label<->class check, but fine for naming
        extra = [(r"^(H|AH|HUONE|ASUINH(UONE)?|MAKUUHUONE\d*)$", "bedroom"), (r"^(HV|VAATEHUONE)$", "storage"),
                 (r"^(L\.?H\.?|LOYLYHUONE)$", "sauna"), (r"^(SUIHKU|SUIHKUH(UONE)?|PH/KHH|KPH/KHH)$", "bath")]

        def kind(t):
            k = expected(t)
            if k:
                return k
            for n in (_norm(t), _re.sub(r"[\s\d,]+(M2|M²)?$", "", t.upper().replace("Ö", "O"))):
                k = next((c for rx, c in extra if _re.match(rx, n.replace(" ", ""))), None)
                if k:
                    return k
            return None

        for mt in meta.values():
            kinds = {kind(t) for t in mt.get("labels", [])} - {None}
            if len(kinds) == 1 and not mt.get("merged"):
                k = kinds.pop()
                if k != mt["cls"]:
                    mt["cls_cc5k"], mt["cls"] = mt["cls"], k

    # ---- areas printed on the plan (exact when present; the door estimate is only a cross-check) -----------------
    printed_total = []
    if printed:
        try:
            from experiments.r1.raster_scale.scale import printed_areas
            for it in printed_areas(path):
                b = it["box"]
                cx, cy = int((b[0] + b[2]) / 2), int((b[1] + b[3]) / 2)
                if it.get("total"):
                    printed_total.append({"m2": it["m2"], "text": it["text"], "box": b})
                elif 0 <= cx < W and 0 <= cy < H and inst[cy, cx]:
                    mt = meta[int(inst[cy, cx])]
                    mt.setdefault("printed", []).append({"m2": it["m2"], "text": it["text"], "box": b,
                                                        "unitless": bool(it.get("unitless"))})
        except Exception as e:  # noqa: BLE001
            notes.append(f"printed areas not read: {type(e).__name__}")
        # labels often carry the area without a unit ('MAKUUHUONE 13,1', 'MH 9.5'): use it when the reader found none
        import re as _re2
        for mt in meta.values():
            if mt.get("printed"):
                continue
            for t in mt.get("labels", []):
                m = _re2.search(r"(?<![\d.,])(\d{1,3}[.,]\d)(?![\d.,])", t)
                if m and 1.0 <= float(m.group(1).replace(",", ".")) <= 200:
                    mt.setdefault("printed", []).append({"m2": float(m.group(1).replace(",", ".")), "text": t,
                                                        "box": None, "from": "label", "unitless": True})
        for mt in meta.values():  # two printed room areas in one region = a partition the segmentation missed
            if len(mt.get("printed", [])) >= 2 and not mt.get("merged"):
                mt["merged"] = {mt["cls"]: len(mt["printed"])}

    # ---- separate drawings on one sheet (two floors side by side): components of the dilated footprint holding
    # >= 15% of it (6007 / 4828: two parts of 52/48% and 57/43%; single plans: one part of 99-100%)
    k = max(3, int(0.02 * max(H, W)))
    foot = cv2.dilate((rooms > 0).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    n_p, lab_p, st_p, _ = cv2.connectedComponentsWithStats(foot, connectivity=8)
    tot = float(st_p[1:, cv2.CC_STAT_AREA].sum()) if n_p > 1 else 0.0
    big = [i for i in range(1, n_p) if tot and st_p[i, cv2.CC_STAT_AREA] >= 0.15 * tot]
    parts = []
    if len(big) >= 2:
        wide = (max(st_p[i, 0] + st_p[i, 2] for i in big) - min(st_p[i, 0] for i in big)) >= \
               (max(st_p[i, 1] + st_p[i, 3] for i in big) - min(st_p[i, 1] for i in big))
        big.sort(key=lambda i: st_p[i, 0] if wide else st_p[i, 1])
        name = {}
        for j, i in enumerate(big):
            x, y, w_, h_ = (int(v) for v in st_p[i, :4])
            letter = chr(65 + j)
            name[i] = letter
            parts.append({"part": letter, "bbox": [x, y, x + w_, y + h_],
                          "where": (["left", "right"] if wide else ["top", "bottom"])[min(j, 1)] if len(big) == 2
                          else f"{j + 1} of {len(big)}"})
        for mt in meta.values():
            cx, cy = mt["centroid"]
            mt["part"] = name.get(int(lab_p[min(H - 1, max(0, cy)), min(W - 1, max(0, cx))]))

    # ---- areas -------------------------------------------------------------------------------------------------
    out_rooms = []
    for i in sorted(meta, key=lambda j: -meta[j]["px"]):
        mt = meta[i]
        rec = {"id": f"R{i}", **{k: v for k, v in mt.items()}}
        rec["label"] = " / ".join(mt.get("labels", [])) or None
        rec.pop("labels", None)
        if sc:
            a = mt["px"] / sc["px_per_m"] ** 2
            lo, hi = sc["area_factor_80"]
            rec["m2"], rec["m2_80"] = round(a, 1), [round(a * lo, 1), round(a * hi, 1)]
        out_rooms.append(rec)
    if not sc:
        notes.append("no scale (fewer than 2 doors detected): areas not estimated")
    return {"path": _rel(path), "size": [W, H], "wall_px": round(wall, 1), "rooms": out_rooms, "doors": doors,
            "windows": windows, "scale": ({k: sc[k] for k in ("px_per_m", "px_per_m_80", "area_factor_80",
                                                                "n_doors", "assumptions", "missing")} if sc else None),
            "unassigned": dict(unassigned), "notes": notes, "printed_total": printed_total, "parts": parts,
            "source": "pretrained CubiCasa5K multi-task model (Kalervo et al. 2019, CC BY-NC 4.0) segmentation; "
                      "geometry rules in experiments/r1/room_graph/graph.py"}


def graph_text(g: dict, show_parts: bool = False) -> str:
    """Compact, LLM-readable summary (one line per room) for an agent tool or the answer card.

    show_parts=True prefixes rooms with their drawing ([A]/[B], two floors side by side). Off by default: on the
    probe it changed 2 answers on the one two-storey v3 plan for the worse and fixed none (methods 8i)."""
    if not g:
        return "no room graph (plan not segmented)"
    anyp = any(r.get("printed") for r in g["rooms"]) or bool(g.get("printed_total"))
    lines = [f"Room graph of {g['path']} (CubiCasa5K segmentation; 'printed' areas are read from the plan and exact; "
             f"'estimated' areas come from door widths and can be off by 50%"
             + ("; this plan prints areas, so a room without a printed area may be outside the apartment or a "
                "segmentation fragment" if anyp else "") + "):"]
    if g.get("parts") and show_parts:
        lines.append(f"This sheet shows {len(g['parts'])} separate drawings, usually the floors of one building "
                     "(the ground floor normally has the main entrance and the kitchen): "
                     + "; ".join(f"[{p['part']}] = {p['where']} drawing, box {p['bbox']}" for p in g["parts"])
                     + ". Each room line starts with its drawing.")
    for r in g["rooms"]:
        fx = ", ".join(f"{len(v)} {k}{'s' if len(v) > 1 else ''}" for k, v in r["fixtures"].items())
        if r.get("printed"):
            area = " printed " + " + ".join(f"{p['m2']} m²" for p in r["printed"])
            if any(p.get("unitless") for p in r["printed"]):
                area += " (number printed without a unit)"
        else:
            area = f" ~{r['m2']} m² ({r['m2_80'][0]}–{r['m2_80'][1]}, estimated)" if "m2" in r else ""
        name = f" '{r['label']}'" if r.get("label") else ""
        if r.get("cls_cc5k"):
            name += f" (segmentation said {r['cls_cc5k']})"
        part = f"[{r['part']}] " if r.get("part") and show_parts else ""
        lines.append(f"- {part}{r['id']} {r['cls']}{name}{area}; {len(r['windows'])} window(s); "
                     f"doors to: {', '.join(r['door_to']) or 'none'}; open to: {', '.join(r['open_to']) or 'none'}; shares walls with: {', '.join(r['wall_to']) or 'none'}"
                     + (f"; fixtures: {fx}" if fx else "")
                     + (f"; WARNING holds {', '.join(f'{n} {k} labels' for k, n in r['merged'].items())} (probably "
                        f"{max(r['merged'].values())} rooms merged)" if r.get("merged") else "") + f"; box {r['bbox']}")
    for t in g.get("printed_total") or []:
        lines.append(f"Printed apartment total: {t['m2']} m² ('{t['text']}')")
    ext = [d for d in g["doors"] if "outside" in d["between"]]
    lines.append(f"{len(g['doors'])} doors ({len(ext)} to outside), {len(g['windows'])} windows "
                 f"({sum(w['side'] == 'exterior' for w in g['windows'])} exterior)."
                 + (f" Unassigned: {g['unassigned']}." if g["unassigned"] else ""))
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print(graph_text(room_graph(p)))
