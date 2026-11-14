"""Swiss Dwellings DXF -> FloorModel.

Layers (Stoa's rendering of Swiss Dwellings v3.0.0, CC BY 4.0): ROOM_OUTLINE (one LWPOLYLINE per room),
ROOM_TEXT (name / number / printed area / "Whg. A"), UNIT_OUTLINE (apartments), DOOR, WINDOW, FIXTURE,
WALL, ANNOTATION. DXF units are metres ($INSUNITS = 6).

Rules (measured by R1/S0 on 200-1000 floors, re-measured by W2 with this code; see README.md):
- door     = 5-vertex DOOR LWPOLYLINE (the leaf). Arcs overcount (double doors, duplicates).
- window   = 3 WINDOW LWPOLYLINEs; grouped by touching bboxes for evidence, count = n / 3.
- bathtub  = 69-vertex FIXTURE LWPOLYLINE; shower = 5-vertex FIXTURE LWPOLYLINE.
- toilet / washbasin = 48-vertex FIXTURE ellipse; a washbasin has a small drain CIRCLE (r < 0.05 m)
  inside its ellipse, a toilet bowl does not.
- apartment = "Whg. X" / "App. X" ROOM_TEXT label.
- room     = ROOM_OUTLINE polygon; texts inside it (smallest containing polygon) give number/name/printed area.
"""

from __future__ import annotations

import functools
import math
import re
import threading
from dataclasses import dataclass, field

import ezdxf
from ezdxf import bbox as ezbbox
from shapely.geometry import Point, Polygon
from shapely.validation import make_valid

NUM_RE = re.compile(r"^[A-Z]{0,2}\d+(?:\.\d+)+$|^[A-Z]{1,2}\d+$")
AREA_RE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*m(?:²|2)$")
APT_RE = re.compile(r"^(?:Whg|App|Appartement|Appartamento|Wohnung|Apt)\.?\s*([A-Z0-9]{1,3})$")

# outdoor room names (excluded from net floor area of apartments / totals)
OUTDOOR = {"balkon", "balcon", "balcone", "loggia", "terrasse", "terrazza", "sitzplatz", "dachterrasse",
           "laubengang", "garten", "jardin", "giardino", "veranda", "wintergarten", "terrace", "balcony",
           "patio", "porch"}
# shafts / voids (excluded from the "total net floor area ... shafts and voids" template)
SHAFT = {"schacht", "gaine", "cavedio", "luftraum", "vide", "vuoto", "shaft", "void"}


BBox = tuple[float, float, float, float]  # x0, y0, x1, y1 in DXF metres (y up)


@dataclass
class Text:
    text: str
    x: float
    y: float
    h: float
    layer: str

    @property
    def bbox(self) -> BBox:
        w = max(len(self.text), 1) * self.h * 0.6
        return (self.x - w / 2, self.y - self.h / 2, self.x + w / 2, self.y + self.h / 2)


@dataclass
class Room:
    idx: int
    poly: Polygon
    bbox: BBox
    area: float
    number: str | None = None
    name: str | None = None
    printed_area: float | None = None
    texts: list[Text] = field(default_factory=list)
    unit: str | None = None  # apartment label ("A") whose UNIT_OUTLINE holds this room

    @property
    def anchor(self) -> tuple[float, float]:
        if self.texts:
            return self.texts[0].x, self.texts[0].y
        p = self.poly.representative_point()
        return p.x, p.y

    @property
    def net(self) -> float:
        """Net area: the printed area when the DXF polygon disagrees with it by > 2%, else the polygon (W2 10:25: the
        reference totals follow the printed labels, e.g. a Treppenhaus polygon 35.38 m² printed 29.03; dev 'all
        numbered rooms' totals 31 -> 34/35, train 207 -> 209/216, 0 lost). Single-room answers did this already."""
        if self.printed_area is not None and abs(self.printed_area - self.area) > 0.02 * self.printed_area and \
                0.7 <= self.printed_area / max(self.area, 1e-9) <= 1.43:
            # outside that band the printed number belongs to another label (F 10:53: a 6.06 m² 'Balkon' polygon
            # picked up a printed 86.23): keep the polygon
            return self.printed_area
        return self.area

    @property
    def outdoor(self) -> bool:
        return (self.name or "").strip().lower() in OUTDOOR

    @property
    def shaft(self) -> bool:
        return (self.name or "").strip().lower() in SHAFT

    def label(self) -> str:
        bits = [b for b in (self.number, f"'{self.name}'" if self.name else None) if b]
        return " ".join(bits) or f"polygon #{self.idx}"


@dataclass
class Unit:
    label: str | None
    poly: Polygon | None
    bbox: BBox
    text: Text | None = None


@dataclass
class Item:
    kind: str  # door | window | toilet | washbasin | bathtub | shower
    bbox: BBox
    note: str = ""


@dataclass
class FloorModel:
    path: str
    rooms: list[Room]
    units: list[Unit]
    items: dict[str, list[Item]]
    texts: list[Text]
    annotations: list[Text]
    raw_counts: dict[str, int]
    insunits: int | None
    warnings: list[str] = field(default_factory=list)
    supported: frozenset | None = None  # object kinds this model can count (None = all; PDF-only models: fewer)

    def names(self) -> list[str]:
        return sorted({r.name for r in self.rooms if r.name} | {t.text for t in self.texts if _is_name(t.text)})

    def scale_text(self) -> str | None:
        for t in self.annotations:
            if re.search(r"1\s*:\s*\d+", t.text):
                return t.text
        return None


def _is_name(s: str) -> bool:
    s = s.strip()
    return bool(s) and not NUM_RE.match(s) and not AREA_RE.match(s) and not APT_RE.match(s)


def _bbox_pts(pts) -> BBox:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _union(a: BBox, b: BBox) -> BBox:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _touch(a: BBox, b: BBox, tol: float) -> bool:
    return not (a[2] + tol < b[0] or b[2] + tol < a[0] or a[3] + tol < b[1] or b[3] + tol < a[1])


def _cluster(boxes: list[BBox], tol: float) -> list[list[int]]:
    """Union-find over touching boxes -> groups of indices."""
    parent = list(range(len(boxes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if _touch(boxes[i], boxes[j], tol):
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(len(boxes)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _polygon(pts) -> Polygon | None:
    if len(pts) < 3:
        return None
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = make_valid(poly)
        if poly.geom_type != "Polygon":
            polys = [g for g in getattr(poly, "geoms", []) if g.geom_type == "Polygon"]
            if not polys:
                return None
            poly = max(polys, key=lambda g: g.area)
    return poly


def load_floor(dxf_abspath: str) -> FloorModel:
    return _load_floor_cached(str(dxf_abspath))


_LOCK = threading.Lock()


@functools.lru_cache(maxsize=256)
def _load_floor_cached(path: str) -> FloorModel:
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    warnings: list[str] = []
    raw: dict[str, int] = {}
    texts, annotations = [], []
    room_pts, unit_pts = [], []
    door_leaves, door_arcs, window_boxes = [], [], []
    fx_polys, fx_circles = [], []
    for e in msp:
        t, layer = e.dxftype(), e.dxf.layer
        raw[f"{layer}:{t}"] = raw.get(f"{layer}:{t}", 0) + 1
        if t in ("TEXT", "MTEXT"):
            s = e.dxf.text if t == "TEXT" else e.plain_text()
            ins = e.dxf.insert
            # TEXT with halign/valign set is positioned by align_point
            if t == "TEXT" and (e.dxf.get("halign", 0) or e.dxf.get("valign", 0)) and e.dxf.hasattr("align_point"):
                ins = e.dxf.align_point
            tx = Text(s.strip(), float(ins[0]), float(ins[1]), float(e.dxf.get("height", 0.25) or 0.25), layer)
            (texts if layer == "ROOM_TEXT" else annotations).append(tx)
        elif t == "LWPOLYLINE":
            pts = [(float(p[0]), float(p[1])) for p in e.get_points("xy")]
            if not pts:
                continue
            if layer == "ROOM_OUTLINE":
                room_pts.append(pts)
            elif layer == "UNIT_OUTLINE":
                unit_pts.append(pts)
            elif layer == "DOOR":
                if len(pts) == 5:
                    door_leaves.append(_bbox_pts(pts))
            elif layer == "WINDOW":
                window_boxes.append(_bbox_pts(pts))
            elif layer == "FIXTURE":
                fx_polys.append((len(pts), _bbox_pts(pts)))
        elif t == "ARC" and layer == "DOOR":
            try:
                ext = ezbbox.extents([e])
                door_arcs.append((float(e.dxf.center[0]), float(e.dxf.center[1]),
                                  (ext.extmin.x, ext.extmin.y, ext.extmax.x, ext.extmax.y)))
            except Exception:  # noqa: BLE001
                pass
        elif t == "CIRCLE" and layer == "FIXTURE":
            fx_circles.append((float(e.dxf.center[0]), float(e.dxf.center[1]), float(e.dxf.radius)))

    insunits = doc.header.get("$INSUNITS")
    if insunits not in (6, None):
        warnings.append(f"$INSUNITS={insunits}, expected 6 (metres)")
    return assemble(path, room_pts, unit_pts, texts, annotations, door_leaves, door_arcs, window_boxes, fx_polys,
                    fx_circles, raw, insunits, warnings)


def assemble(path, room_pts, unit_pts, texts, annotations, door_leaves, door_arcs, window_boxes, fx_polys, fx_circles,
             raw, insunits, warnings, supported=None) -> FloorModel:
    """Geometry (metres, y up) -> FloorModel. Shared by the DXF reader and the PDF-only reader (pdffloor.py)."""
    # rooms ---------------------------------------------------------------------------------------
    rooms: list[Room] = []
    for i, pts in enumerate(room_pts):
        poly = _polygon(pts)
        if poly is None or poly.area <= 0:
            continue
        rooms.append(Room(idx=i, poly=poly, bbox=_bbox_pts(pts), area=poly.area))
    for tx in texts:
        pt = Point(tx.x, tx.y)
        cands = [r for r in rooms if r.bbox[0] <= tx.x <= r.bbox[2] and r.bbox[1] <= tx.y <= r.bbox[3]
                 and r.poly.contains(pt)]
        if not cands:
            continue
        r = min(cands, key=lambda r: r.area)  # innermost polygon
        r.texts.append(tx)
    for r in rooms:
        for tx in r.texts:
            s = tx.text.strip()
            if NUM_RE.match(s):
                r.number = r.number or s
            elif m := AREA_RE.match(s):
                r.printed_area = r.printed_area or float(m.group(1).replace(",", "."))
            elif APT_RE.match(s):
                pass
            elif s and r.name is None:
                r.name = s

    # units (apartments) ---------------------------------------------------------------------------
    apt_texts = [tx for tx in texts if APT_RE.match(tx.text.strip())]
    units: list[Unit] = []
    unit_polys = [(_polygon(p), _bbox_pts(p)) for p in unit_pts]
    unit_polys = [(p, b) for p, b in unit_polys if p is not None]
    used = set()
    for tx in apt_texts:
        lab = APT_RE.match(tx.text.strip()).group(1)
        pt = Point(tx.x, tx.y)
        cands = [(i, p, b) for i, (p, b) in enumerate(unit_polys) if p.contains(pt)]
        if cands:
            i, p, b = min(cands, key=lambda c: c[1].area)
            used.add(i)
            units.append(Unit(lab, p, b, tx))
        else:
            units.append(Unit(lab, None, tx.bbox, tx))
            warnings.append(f"apartment label {tx.text!r} lies in no UNIT_OUTLINE")
    for r in rooms:
        ax, ay = r.anchor
        pt = Point(ax, ay)
        for u in units:
            if u.poly is not None and u.poly.contains(pt):
                r.unit = u.label
                break

    # doors: leaf + its swing arc for the evidence box ------------------------------------------------
    items: dict[str, list[Item]] = {k: [] for k in ("door", "window", "toilet", "washbasin", "bathtub", "shower")}
    for k, b in enumerate(door_leaves):
        box = b
        for cx, cy, ab in door_arcs:
            if _touch(b, (cx, cy, cx, cy), 0.05):
                box = _union(box, ab)
                break
        items["door"].append(Item("door", box, f"door {k + 1}"))

    # windows: 3 polylines each -> cluster touching boxes --------------------------------------------
    groups = []
    for g in _cluster(window_boxes, 0.01):
        # adjacent windows touch: a cluster of 3k lines along a wall = k windows side by side; split it
        # into runs of 3 along the cluster's long axis (a window's own 3 lines are stacked across it)
        if len(g) > 3 and len(g) % 3 == 0:
            gb = window_boxes[g[0]]
            for i in g[1:]:
                gb = _union(gb, window_boxes[i])
            ax = 0 if gb[2] - gb[0] >= gb[3] - gb[1] else 1
            g = sorted(g, key=lambda i: (window_boxes[i][ax] + window_boxes[i][ax + 2]) / 2)
            groups += [g[k:k + 3] for k in range(0, len(g), 3)]
        else:
            groups.append(g)
    n_win_polys = len(window_boxes)
    exp = round(n_win_polys / 3)
    if len(groups) != exp:
        warnings.append(f"window polylines {n_win_polys} -> {len(groups)} touching groups (expected {exp})")
    for k, g in enumerate(sorted(groups, key=lambda g: (window_boxes[g[0]][1], window_boxes[g[0]][0]))):
        box = window_boxes[g[0]]
        for i in g[1:]:
            box = _union(box, window_boxes[i])
        items["window"].append(Item("window", box, f"window {k + 1} ({len(g)} lines)"))

    # fixtures ------------------------------------------------------------------------------------
    for nv, b in fx_polys:
        if nv == 69:
            items["bathtub"].append(Item("bathtub", b))
        elif nv == 5:
            items["shower"].append(Item("shower", b))
        elif nv == 48:
            drain = any(r < 0.05 and b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for cx, cy, r in fx_circles)
            kind = "washbasin" if drain else "toilet"
            items[kind].append(Item(kind, b))
    for kind, lst in items.items():
        if kind == "window":
            continue
        lst.sort(key=lambda it: (-it.bbox[3], it.bbox[0]))
        for k, it in enumerate(lst):
            it.note = f"{kind} {k + 1}"

    return FloorModel(path=path, rooms=rooms, units=units, items=items, texts=texts, annotations=annotations,
                      raw_counts=raw, insunits=insunits, warnings=warnings, supported=supported)


def window_count(fm: FloorModel) -> int:
    n = fm.raw_counts.get("WINDOW:LWPOLYLINE", 0)
    return int(round(n / 3))


def fmt_area(a: float) -> str:
    return f"{a:.2f} m²"


def angle_deg(a: float) -> float:
    return math.degrees(a)
