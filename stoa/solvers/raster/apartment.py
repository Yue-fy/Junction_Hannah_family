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
_Q_UNIT = re.compile(rf"(?i:\b{_UNIT_WORD})\s*['\"«“]?([A-Z])['\"»”]?(?![\w])")
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
                 not _LABEL.match(i.text) and not re.search(r"\d", i.text) and abs(i.cx - rid.cx) < 3 * h and -2.6 * h < i.cy - rid.cy < 0]
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


_LABELLED = re.compile(r"(?:labell?ed|named|called|marked|bezeichnet|beschriftet|mit der bezeichnung|intitulées?|"
                       r"étiquetées?|nommées?|denominat[eia]|etichettat[eia]|chiamat[eia]|nimetty|merkitty|märkt[a]?)"
                       r"\s*[«'\"‘“„]([^'\"’”»“]{1,40})[»'\"’”“]", re.I)
_FLOOR_SUM = re.compile(r"\b(total|sum|summe|gesamt\w*|insgesamt|somme|totale|somma|complessiv\w*|yhteensä|"
                        r"all (?:numbered )?(?:indoor )?rooms|aller? |toutes les|tutt[ei] le)\b", re.I)
_SHAFT_Q = re.compile(r"shaft|void|schächt|schacht|luftr[aä]um|gaine|\bvides?\b|cavedi|vuot|kuilu", re.I)
_SHAFT_NAME = re.compile(r"schacht|luftraum|gaine|^vide|cavedio|vuoto|shaft|void|kuilu", re.I)
_TOTAL_LINE = re.compile(r"total|gesamt|summe|yht|yhteensä|asuinpinta|wohnfl|nutzfl|bgf|ngf|gfa|nfa|somme|totale|"
                         r"surface habitable|superficie utile|bostadsyta|boyta|net area|gross", re.I)
_NUMBERED_Q = re.compile(r"numbered|nummeriert|numérotées?|numerat[ei]|numeroid", re.I)


def labelled_name(question: str) -> str | None:
    m = _LABELLED.search(question)
    return m.group(1).strip() if m else None


def room_set(path: str, layer: T.TextLayer, question: str, px_per_m: float | None,
             grow_m: float = 0.15, mode: str = "hybrid") -> dict | None:
    """The rooms a summed-area question is about, with their areas: one unit's rooms ('apartment B': inside its drawn
    boundary), the rooms labelled X ('all rooms labelled «Bad»'), or every (numbered) indoor room of the floor. Outdoor
    rooms (and shafts/voids) are dropped when the question excludes them; rooms with a number but no printed area are
    measured by flood fill when a scale is known (mode 'hybrid'). None when the question is none of these."""
    letter = unit_letter(question)
    name = labelled_name(question)
    labels = unit_labels(layer)
    comp, lab, scope = None, None, "floor"
    rgb = np.asarray(Image.open(T._abspath(path)).convert("RGB"))
    H, W = rgb.shape[:2]
    if letter:
        if letter not in labels:
            return None
        lab = labels[letter]
        # dash-dot gaps: 3-7 px on 2480-px A3 renders (29.6 px/m); growing by 3-5 px closed all 4 units of Q's plan
        grow = max(3, int(round(grow_m * px_per_m))) if px_per_m else 4
        comp = region(rgb, (int(lab.cx), int(lab.cy)), grow)
        if comp is None:
            return None
        if any(k != letter and comp[int(it.cy), int(it.cx)] for k, it in labels.items()):
            return None  # the region holds another unit's label: the boundary has a gap
        scope = "unit"
    elif not (name or _FLOOR_SUM.search(question)):
        return None
    all_rooms = _rooms(layer)
    if scope == "floor" and sum(r["label"] is not None for r in all_rooms) < 2:
        # a floor sum needs numbered rooms: on other sheets (scans, uploads) printed areas may be site or total areas
        return None
    excl = bool(_OUTDOOR_Q.search(question))
    excl_shaft = bool(_SHAFT_Q.search(question))
    numbered = bool(_NUMBERED_Q.search(question))
    rooms, dropped, unmeasured, measured = [], [], [], []
    from stoa.solvers.raster import measure as M
    ink = None
    for r in all_rooms:
        if r["area"] is not None and _TOTAL_LINE.search(r["area"]["line"]):
            continue  # a printed total ('Wohnfläche 81 m²', 'yht. 56 m²') is not a room
        if scope == "floor" and r["label"] is None and not name:
            continue
        cx, cy = (r["label"].cx, r["label"].cy) if r["label"] is not None else (r["cx"], r["cy"])
        if not (0 <= int(cy) < H and 0 <= int(cx) < W):
            continue
        if comp is not None and not comp[int(cy), int(cx)]:
            continue
        if numbered and r["label"] is None:
            continue
        if name and not (r["name"] and (T.norm(r["name"]) == T.norm(name) or T.match_score(name, r["name"]) >= 0.9)):
            continue
        if not name and ((excl and r["name"] and _OUTDOOR_NAME.search(r["name"])) or
                         (excl_shaft and r["name"] and _SHAFT_NAME.search(r["name"]))):
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
    out = {"scope": scope, "letter": letter, "name": name, "label": lab, "value": round(total, 2), "rooms": rooms,
           "dropped": dropped, "unmeasured": unmeasured, "measured": measured, "region_box": None, "region_m2": None}
    if comp is not None:
        ys, xs = np.nonzero(comp)
        out["region_box"] = [float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)]
        out["region_m2"] = round(comp.sum() / px_per_m ** 2, 2) if px_per_m else None
    return out


def unit_region(path: str, layer: T.TextLayer, letter: str, px_per_m: float | None = None,
                grow_m: float = 0.15) -> tuple[np.ndarray | None, T.TextItem | None]:
    """(mask of the unit's region, its label) or (None, label-or-None) when the label or a closed boundary is missing."""
    labels = unit_labels(layer)
    lab = labels.get(letter)
    if lab is None:
        return None, None
    rgb = np.asarray(Image.open(T._abspath(path)).convert("RGB"))
    grow = max(3, int(round(grow_m * px_per_m))) if px_per_m else 4
    comp = region(rgb, (int(lab.cx), int(lab.cy)), grow)
    if comp is not None and any(k != letter and comp[int(it.cy), int(it.cx)] for k, it in labels.items()):
        comp = None
    return comp, lab


def net_area(path: str, layer: T.TextLayer, question: str, px_per_m: float | None, **kw) -> dict | None:
    """One unit's net area (room_set with a unit letter)."""
    return room_set(path, layer, question, px_per_m, **kw) if unit_letter(question) else None
