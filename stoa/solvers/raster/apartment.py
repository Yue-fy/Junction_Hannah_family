"""Apartment (unit) net floor area on a raster plan: the unit's drawn boundary + the printed room areas inside it.

Swiss-style plans draw each apartment's boundary as a coloured dash-dot line ('Wohnungsgrenze') and print the unit's
name ('Whg. B', 'App. A') inside it. A question like "net floor area of apartment B, summing all its rooms except
balconies" is then: the region enclosed by the boundary around the label -> the rooms whose labels lie inside ->
their printed areas (read), outdoor rooms dropped, rooms with no printed area measured by flood fill (measure.py).
No VLM call beyond the cached text layer.

    unit_letter(question) -> 'B' or None           (apartment/Wohnung/appartement/appartamento/asunto/lägenhet B)
    unit_labels(layer) -> {'A': TextItem, ...}
    net_area(path, layer, question, px_per_m) -> dict(value, rooms, region_box, notes, measured) or None
"""

from __future__ import annotations

import re

import cv2
import numpy as np
from PIL import Image

from stoa.solvers.raster import textlayer as T

_UNIT_WORD = (r"(?:apartments?|apartment|appartements?|appartamento|appartamenti|wohnung|whg\.?|app\.?|appt\.?|"
              r"apt\.?|unit|logement|asunto|huoneisto|lägenhet|lagenhet|dwelling|flat)")
_Q_UNIT = re.compile(rf"\b{_UNIT_WORD}\s*['\"«“]?([A-Z])['\"»”]?(?![\w])", re.I)
_LABEL = re.compile(r"^\s*(?:Whg|Wohnung|App|Appt|Apt|Appartement|Appartamento|Apartment|Unit|Logement|Lgt|"
                    r"Wohneinheit|WE|Asunto|As)\.?\s*([A-Z])\s*$", re.I)
_NET_Q = re.compile(r"net|netto|nette?|summ|somme|somma|sum|total|gesamt|insgesamt|wohnfl|floor area|surface|"
                    r"superficie|pinta-ala|area|fläche", re.I)
_OUTDOOR_Q = re.compile(r"balcon|balkon|loggia|terrass|terrace|terrazz|outdoor|aussen|außen|extérieur|esterno|"
                        r"parveke|parvek|veranda|sitzplatz|patio", re.I)
_OUTDOOR_NAME = re.compile(r"balcon|balkon|loggia|terrass|terrace|terrazz|veranda|sitzplatz|patio|parveke|"
                           r"vorplatz aussen|aussen", re.I)
_ROOM_ID = re.compile(r"^\d{1,3}\.\d{1,3}[a-z]?$")


def unit_letter(question: str) -> str | None:
    m = _Q_UNIT.search(question)
    return m.group(1).upper() if m else None


def unit_labels(layer: T.TextLayer) -> dict[str, T.TextItem]:
    out: dict[str, T.TextItem] = {}
    for it in layer.items:
        m = _LABEL.match(it.text)
        if m:
            out.setdefault(m.group(1).upper(), it)
    return out


def boundary_mask(rgb: np.ndarray) -> np.ndarray:
    """Coloured (red/orange) line pixels: the unit boundary. Grey walls, black text and light fills are not."""
    r, g, b = (rgb[..., k].astype(np.int16) for k in range(3))
    return ((r - g > 60) & (r - b > 60) & (r > 120)).astype(np.uint8)


def region(rgb: np.ndarray, seed: tuple[int, int], grow_px: int) -> np.ndarray | None:
    """The component around the seed bounded by the unit boundary (dash-dot gaps bridged by growing the line by
    `grow_px`); None if it leaks to the image border."""
    bnd = boundary_mask(rgb)
    if bnd.sum() < 50:
        return None
    grown = cv2.dilate(bnd, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow_px + 1, 2 * grow_px + 1)))
    free = (grown == 0).astype(np.uint8)
    x, y = seed
    if not free[y, x]:
        return None
    n, lab = cv2.connectedComponents(free, connectivity=4)
    comp = lab == lab[y, x]
    if comp[0].any() or comp[-1].any() or comp[:, 0].any() or comp[:, -1].any():
        return None
    return comp


def _rooms(layer: T.TextLayer) -> list[dict]:
    """Room records: number label (if any), name above it, printed area under it."""
    ids = [i for i in layer.items if _ROOM_ID.match(i.text.strip())]
    areas = T.areas(layer)
    used: set[int] = set()
    out = []

    def near(a, b, hx=1.2, hy=3.0):
        h = max(8.0, b.box[3] - b.box[1])
        return abs(a.cx - b.cx) < hx * max(b.box[2] - b.box[0], h * 3) and abs(a.cy - b.cy) < hy * h

    for rid in ids:
        h = max(8.0, rid.box[3] - rid.box[1])
        cands = [(k, a) for k, a in enumerate(areas) if k not in used and
                 abs((a["box"][0] + a["box"][2]) / 2 - rid.cx) < 3 * h and 0 < (a["box"][1] + a["box"][3]) / 2 - rid.cy < 2.6 * h]
        # an area belongs to the nearest number (a neighbour's area can sit as close)
        best = None
        for k, a in sorted(cands, key=lambda ka: abs((ka[1]["box"][1] + ka[1]["box"][3]) / 2 - rid.cy)):
            acx, acy = (a["box"][0] + a["box"][2]) / 2, (a["box"][1] + a["box"][3]) / 2
            nearest = min(ids, key=lambda j: (acx - j.cx) ** 2 + (acy - j.cy) ** 2)
            if nearest is rid:
                best = (k, a)
                break
        names = [i for i in layer.items if i is not rid and not _ROOM_ID.match(i.text.strip()) and
                 not re.search(r"\d", i.text) and abs(i.cx - rid.cx) < 3 * h and -2.6 * h < i.cy - rid.cy < 0]
        name = min(names, key=lambda i: rid.cy - i.cy).text if names else ""
        if best:
            used.add(best[0])
        out.append({"id": rid.text.strip(), "label": rid, "name": name,
                    "area": best[1] if best else None})
    for k, a in enumerate(areas):  # printed areas with no room number (plans without numbering)
        if k in used:
            continue
        cx, cy = (a["box"][0] + a["box"][2]) / 2, (a["box"][1] + a["box"][3]) / 2
        h = max(8.0, a["box"][3] - a["box"][1])
        names = [i for i in layer.items if not re.search(r"\d", i.text) and abs(i.cx - cx) < 3 * h and
                 -2.6 * h < i.cy - cy < 0]
        name = min(names, key=lambda i: cy - i.cy).text if names else ""
        out.append({"id": None, "label": None, "name": name, "area": a, "cx": cx, "cy": cy})
    return out


def net_area(path: str, layer: T.TextLayer, question: str, px_per_m: float | None,
             grow_m: float = 0.15, mode: str = "hybrid") -> dict | None:
    """Sum of the printed areas of the rooms inside the unit's boundary (outdoor rooms dropped when the question
    excludes them); rooms with a number but no printed area are measured by flood fill when a scale is known."""
    letter = unit_letter(question)
    labels = unit_labels(layer)
    if not letter or letter not in labels:
        return None
    lab = labels[letter]
    rgb = np.asarray(Image.open(T._abspath(path)).convert("RGB"))
    H, W = rgb.shape[:2]
    # dash-dot gaps: 3-7 px on 2480-px A3 renders (29.6 px/m); growing by 3-5 px closed all 4 units of the Q plan
    grow = max(3, int(round(grow_m * px_per_m))) if px_per_m else 4
    comp = region(rgb, (int(lab.cx), int(lab.cy)), grow)
    if comp is None:
        return None
    others = [k for k, it in labels.items() if k != letter and comp[int(it.cy), int(it.cx)]]
    if others:  # the region holds another unit's label: the boundary has a gap
        return None
    excl = bool(_OUTDOOR_Q.search(question))
    rooms, dropped, unmeasured, measured = [], [], [], []
    from stoa.solvers.raster import measure as M
    ink = None
    for r in _rooms(layer):
        cx, cy = (r["label"].cx, r["label"].cy) if r["label"] is not None else (r["cx"], r["cy"])
        if not (0 <= int(cy) < H and 0 <= int(cx) < W) or not comp[int(cy), int(cx)]:
            continue
        if excl and r["name"] and _OUTDOOR_NAME.search(r["name"]):
            dropped.append(r)
            continue
        if r["area"] is None:
            got = None
            if px_per_m and r["label"] is not None and mode == "hybrid":
                ink = M._ink(path) if ink is None else ink
                ids = [i.box for i in layer.items if _ROOM_ID.match(i.text.strip()) and i is not r["label"]]
                got = M.room_area(path, r["label"].box, px_per_m, ink=ink, others=ids, **M.FILL)
                if got is not None and (got["wall_frac"] < 0.05 or got["m2"] > 60):
                    got = None
            if got is None:
                unmeasured.append(r)
                continue
            r = {**r, "measured": got}
            measured.append(r)
        rooms.append(r)
    if not rooms:
        return None
    total = sum(r["area"]["value"] if r["area"] else r["measured"]["m2"] for r in rooms)
    ys, xs = np.nonzero(comp)
    reg_m2 = comp.sum() / px_per_m ** 2 if px_per_m else None
    return {"letter": letter, "label": lab, "value": round(total, 2), "rooms": rooms, "dropped": dropped,
            "unmeasured": unmeasured, "measured": measured,
            "region_box": [float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)],
            "region_m2": round(reg_m2, 2) if reg_m2 else None}
