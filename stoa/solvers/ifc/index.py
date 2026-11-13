"""Parse an IFC model once into a small, picklable index (storeys, elements, quantities, geometry).

    from stoa.solvers.ifc.index import load_index, ifc_index
    idx = load_index("data/ifc_models/bsc-duplex_duplex-a-20110907.ifc")
    idx.storeys            # [Storey(guid, name, elevation, ...)]
    idx.elements           # {guid: Element(guid, cls, name, long_name, storey, qto, geo)}
    ifc_index(path)        # JSON-friendly dict for the API / 3D viewer (W4, W5)

Geometry (world coordinates, metres) is computed with ifcopenshell.geom for the classes whose quantities
are asked about (spaces, walls, slabs, ...): footprint area (union of the mesh projected to XY), closed-mesh
volume, bounding box and a simplified footprint polygon (for 2D mapping onto rendered plans).

Cache: one pickle per model under $JUNCTION_SHARED/artifacts/W1/ifc_index/ (keyed by file size+mtime and
INDEX_VERSION). Thread-safe: one lock per model path.
"""

from __future__ import annotations

import hashlib
import os
import pickle
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from stoa.data import abspath

INDEX_VERSION = 6

# classes whose geometry we compute (quantities are asked about them or the viewer highlights them)
GEOM_CLASSES = (
    "IfcSpace", "IfcWall", "IfcWallStandardCase", "IfcCurtainWall", "IfcSlab", "IfcRoof", "IfcCovering",
    "IfcColumn", "IfcBeam", "IfcDoor", "IfcWindow", "IfcStair", "IfcStairFlight", "IfcRamp", "IfcRailing",
    "IfcPlate", "IfcMember", "IfcFooting",
)
# elements we index (everything physical + spaces); openings/annotations are skipped
SKIP_CLASSES = {"IfcOpeningElement", "IfcAnnotation", "IfcGrid", "IfcVirtualElement", "IfcSite", "IfcBuilding",
                "IfcBuildingStorey", "IfcProject", "IfcSpatialZone", "IfcVoidingFeature"}


@dataclass
class Storey:
    guid: str
    name: str
    long_name: str | None
    elevation: float | None  # metres (project units converted)
    building: str | None = None


@dataclass
class Geo:
    footprint_area: float | None = None  # m², union of mesh triangles projected on XY
    volume: float | None = None  # m³, signed volume of the closed mesh (abs)
    bbox: tuple[float, float, float, float, float, float] | None = None  # xmin, ymin, zmin, xmax, ymax, zmax
    footprint: list[list[tuple[float, float]]] | None = None  # simplified outer rings (XY, metres)
    lateral_area: float | None = None  # m², area of (near-)vertical faces
    top_area: float | None = None  # m², area of upward-facing faces


@dataclass
class Element:
    guid: str
    cls: str
    name: str | None
    long_name: str | None = None  # IfcSpace.LongName etc.
    object_type: str | None = None
    predefined_type: str | None = None
    type_name: str | None = None  # name of the IfcTypeObject
    type_cls: str | None = None  # class of the IfcTypeObject ("IfcSanitaryTerminalType")
    eff_cls: str = ""  # effective class: IFC2X3 generic flow classes resolved through their type
    storey: str | None = None  # storey guid (walks containment + aggregation)
    parent: str | None = None  # aggregate parent guid (stair flight -> stair, panel -> curtain wall)
    qto: dict[str, float] = field(default_factory=dict)  # "Qto_SpaceBaseQuantities.NetFloorArea" -> value (SI)
    props: dict[str, object] = field(default_factory=dict)  # selected pset props ("Pset_*.IsExternal", ...)
    geo: Geo | None = None
    axis_length: float | None = None  # m, length of the 'Axis' representation (walls), if modelled
    materials: list[str] | None = None  # material names (layers/constituents/profiles), max 6


@dataclass
class IfcIndex:
    path: str  # dataset-relative
    schema: str
    unit_scale: float  # project length unit -> metres
    project_name: str | None
    project_long_name: str | None
    building_names: list[str]
    storeys: list[Storey]
    elements: dict[str, Element]
    build_seconds: float = 0.0
    version: int = INDEX_VERSION
    application: str | None = None  # authoring tool from IfcApplication ("ARCHICAD 20.0.0 (GRAPHISOFT)")

    def by_class(self, *classes: str) -> list[Element]:
        cs = set(classes)
        return [e for e in self.elements.values() if e.eff_cls in cs or e.cls in cs]

    def in_storey(self, storey_guid: str, *classes: str) -> list[Element]:
        cs = set(classes)
        return [e for e in self.elements.values()
                if e.storey == storey_guid and (not cs or e.eff_cls in cs or e.cls in cs)]

    def storey(self, guid: str) -> Storey | None:
        return next((s for s in self.storeys if s.guid == guid), None)


# IFC2X3 models MEP terminals as generic IfcFlowTerminal/IfcFlowSegment/...; the real kind is on the type
# object (IfcSanitaryTerminalType, IfcLightFixtureType). IFC4 has the specific classes directly.
_GENERIC = {"IfcFlowTerminal", "IfcFlowSegment", "IfcFlowFitting", "IfcFlowController", "IfcFlowMovingDevice",
            "IfcFlowStorageDevice", "IfcFlowTreatmentDevice", "IfcEnergyConversionDevice", "IfcDistributionControlElement",
            "IfcDistributionFlowElement", "IfcBuildingElementProxy"}


def effective_class(cls: str, type_cls: str | None) -> str:
    if cls in _GENERIC and type_cls and type_cls.endswith("Type") and type_cls not in (
            "IfcBuildingElementProxyType", "IfcTypeObject", "IfcTypeProduct", "IfcElementType"):
        return type_cls[:-4]
    return cls


# --- cache -----------------------------------------------------------------------------------------------
def _cache_dir() -> Path:
    root = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")
    d = Path(root) / "artifacts" / "W1" / "ifc_index"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_key(p: Path) -> str:
    st = p.stat()
    h = hashlib.sha1(f"{p.name}|{st.st_size}|{int(st.st_mtime)}|v{INDEX_VERSION}".encode()).hexdigest()[:10]
    return f"{p.stem}-{h}.pkl"


_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_LOCK = threading.Lock()
_MEM: dict[str, IfcIndex] = {}


def load_index(path: str, geometry: bool = True, use_cache: bool = True) -> IfcIndex:
    """Index of the IFC at dataset-relative `path` (memory cache → pickle cache → parse)."""
    with _LOCKS_LOCK:
        lock = _LOCKS.setdefault(path, threading.Lock())
    with lock:
        if path in _MEM:
            return _MEM[path]
        p = abspath(path)
        cf = _cache_dir() / _cache_key(p)
        idx = None
        if use_cache and cf.exists():
            try:
                with open(cf, "rb") as f:
                    idx = pickle.load(f)
            except Exception:  # noqa: BLE001 - stale/corrupt cache: rebuild
                idx = None
        if idx is None:
            idx = build_index(path, geometry=geometry)
            if use_cache:
                tmp = cf.with_suffix(f".tmp{os.getpid()}")
                with open(tmp, "wb") as f:
                    pickle.dump(idx, f, protocol=pickle.HIGHEST_PROTOCOL)
                os.replace(tmp, cf)
        _MEM[path] = idx
        return idx


# --- build -----------------------------------------------------------------------------------------------
def _storey_of(el, cache: dict) -> tuple[str | None, str | None]:
    """(storey guid, aggregate parent guid) walking ContainedInStructure / Decomposes / VoidsElements / FillsVoids."""
    import ifcopenshell.util.element as ue

    parent_guid = None
    agg = ue.get_aggregate(el)
    if agg is not None and not agg.is_a("IfcSpatialStructureElement") and not agg.is_a("IfcSpatialElement"):
        parent_guid = agg.GlobalId
    cur, seen = el, 0
    while cur is not None and seen < 12:
        seen += 1
        if cur.id() in cache:
            return cache[cur.id()], parent_guid
        if cur.is_a("IfcBuildingStorey"):
            cache[el.id()] = cur.GlobalId
            return cur.GlobalId, parent_guid
        nxt = ue.get_container(cur)
        if nxt is None:
            nxt = ue.get_aggregate(cur)
        if nxt is None and hasattr(cur, "FillsVoids") and cur.FillsVoids:  # door/window in an opening
            opening = cur.FillsVoids[0].RelatingOpeningElement
            nxt = opening.VoidsElements[0].RelatingBuildingElement if opening.VoidsElements else None
        if nxt is None and cur.is_a("IfcSpace") is False and getattr(cur, "ContainedInStructure", None) == ():
            pass
        cur = nxt
    cache[el.id()] = None
    return None, parent_guid


_QTY_KIND = {"IfcQuantityLength": "LENGTHUNIT", "IfcQuantityArea": "AREAUNIT", "IfcQuantityVolume": "VOLUMEUNIT"}
_KEEP_PROPS = {"IsExternal", "LoadBearing", "Reference", "Level", "Number", "Name", "Category", "Family", "Type",
               "Status", "Description", "FireRating", "ThermalTransmittance", "AcousticRating", "Combustible",
               "SurfaceSpreadOfFlame", "FireExit", "HandicapAccessible", "OccupancyType", "Material"}


def _qtos(el, scales: dict[str, float]) -> tuple[dict[str, float], dict[str, object]]:
    """Quantities (converted to SI with the project's length/area/volume units) and a few useful props."""
    import ifcopenshell.util.element as ue

    qto: dict[str, float] = {}
    props: dict[str, object] = {}
    for rel in getattr(el, "IsDefinedBy", ()) or ():
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        d = rel.RelatingPropertyDefinition
        if d.is_a("IfcElementQuantity"):
            for q in d.Quantities or ():
                kind = _QTY_KIND.get(q.is_a())
                if kind is None:
                    continue
                val = q[3]  # LengthValue / AreaValue / VolumeValue
                if isinstance(val, (int, float)):
                    qto[f"{d.Name}.{q.Name}"] = float(val) * scales[kind]
        elif d.is_a("IfcPropertySet"):
            for pr in d.HasProperties or ():
                if pr.is_a("IfcPropertySingleValue") and pr.NominalValue is not None:
                    v = pr.NominalValue.wrappedValue
                    if pr.Name in _KEEP_PROPS and isinstance(v, (str, bool, int, float)):
                        props[f"{d.Name}.{pr.Name}"] = v
                    elif isinstance(v, float) and any(w in pr.Name.lower() for w in ("area", "volume", "length")):
                        kind = ("AREAUNIT" if "area" in pr.Name.lower() else
                                "VOLUMEUNIT" if "volume" in pr.Name.lower() else "LENGTHUNIT")
                        qto[f"{d.Name}.{pr.Name}"] = v * scales[kind]
    _ = ue
    return qto, props


def _axis_length(el, scale: float) -> float | None:
    """Length of an element's 'Axis' shape representation (IfcPolyline / IfcTrimmedCurve on a line or circle /
    IfcIndexedPolyCurve / IfcCompositeCurve), in metres. Placement doesn't change lengths."""
    import math

    rep = getattr(el, "Representation", None)
    if rep is None:
        return None

    def curve_len(c) -> float | None:
        if c.is_a("IfcPolyline"):
            pts = [tuple(p.Coordinates) for p in c.Points]
            return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
        if c.is_a("IfcIndexedPolyCurve"):
            pts = [tuple(p) for p in c.Points.CoordList]
            return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
        if c.is_a("IfcTrimmedCurve"):
            b = c.BasisCurve
            t1 = next((x for x in c.Trim1 if x.is_a("IfcCartesianPoint")), None)
            t2 = next((x for x in c.Trim2 if x.is_a("IfcCartesianPoint")), None)
            p1 = next((x for x in c.Trim1 if x.is_a("IfcParameterValue")), None)
            p2 = next((x for x in c.Trim2 if x.is_a("IfcParameterValue")), None)
            if b.is_a("IfcLine"):
                if t1 is not None and t2 is not None:
                    return math.dist(tuple(t1.Coordinates), tuple(t2.Coordinates))
                if p1 is not None and p2 is not None:
                    mag = float(b.Dir.Magnitude) if b.Dir.Magnitude else 1.0
                    return abs(float(p2.wrappedValue) - float(p1.wrappedValue)) * mag
            if b.is_a("IfcCircle") and p1 is not None and p2 is not None:
                a = abs(float(p2.wrappedValue) - float(p1.wrappedValue))
                a = math.radians(a) if a > 2 * math.pi + 1e-6 else a  # degrees or radians, depending on units
                return float(b.Radius) * a
            return None
        if c.is_a("IfcCompositeCurve"):
            parts = [curve_len(seg.ParentCurve) for seg in c.Segments]
            return sum(parts) if parts and None not in parts else None
        return None

    for r in rep.Representations:
        if (r.RepresentationIdentifier or "").lower() != "axis":
            continue
        tot = 0.0
        for it in r.Items:
            v = curve_len(it)
            if v is None:
                return None
            tot += v
        return tot * scale if tot > 0 else None
    return None


def _materials(el) -> list[str] | None:
    import ifcopenshell.util.element as ue

    try:
        m = ue.get_material(el, should_skip_usage=True)
    except Exception:  # noqa: BLE001
        return None
    if m is None:
        return None
    names: list[str] = []
    if m.is_a("IfcMaterial"):
        names = [m.Name]
    elif m.is_a("IfcMaterialLayerSet"):
        names = [ly.Material.Name for ly in m.MaterialLayers if ly.Material]
    elif m.is_a("IfcMaterialConstituentSet"):
        names = [c.Material.Name for c in (m.MaterialConstituents or ()) if c.Material]
    elif m.is_a("IfcMaterialProfileSet"):
        names = [pr.Material.Name for pr in (m.MaterialProfiles or ()) if pr.Material]
    elif m.is_a("IfcMaterialList"):
        names = [x.Name for x in m.Materials]
    names = [n for n in names if n]
    return names[:6] or None


def _mesh_stats(verts, faces):
    import numpy as np
    from shapely import make_valid
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    v = np.asarray(verts, dtype=float).reshape(-1, 3)
    f = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if len(f) == 0:
        return Geo()
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    vol = float(abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum()) / 6.0)
    n = np.cross(b - a, c - a)
    tri_area = np.linalg.norm(n, axis=1) / 2.0
    with np.errstate(invalid="ignore", divide="ignore"):
        nz = np.where(tri_area > 0, n[:, 2] / (2.0 * tri_area), 0.0)
    lateral = float(tri_area[np.abs(nz) < 0.1].sum())
    top = float(tri_area[nz > 0.9].sum())
    polys = []
    for t in f:
        p = Polygon(v[t][:, :2])
        if p.area > 1e-10:
            polys.append(p)
    fp_area, rings = None, None
    if polys:
        u = None
        for attempt in (lambda: unary_union(polys), lambda: unary_union([make_valid(p) for p in polys]),
                        lambda: unary_union([p.buffer(1e-6) for p in polys]).buffer(-1e-6)):
            try:
                u = attempt()
                break
            except Exception:  # noqa: BLE001 - GEOS TopologyException on degenerate meshes: try the next repair
                continue
        if u is None:
            mn, mx = v.min(axis=0), v.max(axis=0)
            return Geo(footprint_area=None, volume=vol, bbox=(*map(float, mn), *map(float, mx)), footprint=None,
                       lateral_area=lateral, top_area=top)
        fp_area = float(u.area)
        geoms = getattr(u, "geoms", [u])
        rings = []
        for g in geoms:
            if g.geom_type != "Polygon" or g.area < 1e-4:
                continue
            s = g.simplify(0.02)
            rings.append([(round(x, 3), round(y, 3)) for x, y in s.exterior.coords])
    mn, mx = v.min(axis=0), v.max(axis=0)
    return Geo(footprint_area=fp_area, volume=vol, bbox=(*map(float, mn), *map(float, mx)), footprint=rings,
               lateral_area=lateral, top_area=top)


def _application(f) -> str | None:
    apps = []
    for a in f.by_type("IfcApplication"):
        s = " ".join(x for x in (a.ApplicationFullName, a.Version) if x)
        dev = a.ApplicationDeveloper.Name if a.ApplicationDeveloper and hasattr(a.ApplicationDeveloper, "Name") else None
        apps.append(s + (f" ({dev})" if dev else ""))
    return "; ".join(dict.fromkeys(apps)) or None


def build_index(path: str, geometry: bool = True, geom_classes=GEOM_CLASSES, threads: int | None = None) -> IfcIndex:
    import ifcopenshell
    import ifcopenshell.util.element as ue
    import ifcopenshell.util.unit as uu

    t0 = time.perf_counter()
    f = ifcopenshell.open(str(abspath(path)))
    scale = float(uu.calculate_unit_scale(f))
    scales = {k: float(uu.calculate_unit_scale(f, k)) for k in ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT")}
    proj = (f.by_type("IfcProject") or [None])[0]
    storeys = []
    for s in f.by_type("IfcBuildingStorey"):
        b = ue.get_aggregate(s)
        storeys.append(Storey(s.GlobalId, s.Name or "", getattr(s, "LongName", None),
                              (float(s.Elevation) * scale) if s.Elevation is not None else None,
                              b.Name if b is not None and b.is_a("IfcBuilding") else None))
    storeys.sort(key=lambda s: (s.elevation is None, s.elevation or 0.0))
    cache: dict = {}
    elements: dict[str, Element] = {}
    for el in f.by_type("IfcProduct"):
        cls = el.is_a()
        if cls in SKIP_CLASSES or el.is_a("IfcSpatialStructureElement") and not el.is_a("IfcSpace"):
            continue
        storey, parent = _storey_of(el, cache)
        qto, props = _qtos(el, scales)
        t = ue.get_type(el)
        elements[el.GlobalId] = Element(
            guid=el.GlobalId, cls=cls, name=el.Name, long_name=getattr(el, "LongName", None),
            object_type=getattr(el, "ObjectType", None),
            predefined_type=str(getattr(el, "PredefinedType", None)) if getattr(el, "PredefinedType", None) else None,
            type_name=t.Name if t is not None else None, type_cls=t.is_a() if t is not None else None,
            eff_cls=effective_class(cls, t.is_a() if t is not None else None),
            storey=storey, parent=parent, qto=qto, props=props,
            axis_length=_axis_length(el, scale) if el.is_a("IfcWall") or el.is_a("IfcMember") or el.is_a("IfcBeam") else None,
            materials=_materials(el) if not el.is_a("IfcSpace") else None)
    if geometry:
        _add_geometry(f, elements, geom_classes, threads)
    return IfcIndex(path=path, schema=f.schema, unit_scale=scale, project_name=proj.Name if proj else None,
                    project_long_name=getattr(proj, "LongName", None) if proj else None,
                    building_names=[b.Name or "" for b in f.by_type("IfcBuilding")], storeys=storeys,
                    elements=elements, build_seconds=time.perf_counter() - t0, application=_application(f))


def _add_geometry(f, elements: dict[str, Element], geom_classes, threads: int | None) -> None:
    import multiprocessing

    import ifcopenshell.geom

    targets = [e for e in f.by_type("IfcProduct") if e.GlobalId in elements and e.is_a() in geom_classes]
    if not targets:
        return
    st = ifcopenshell.geom.settings()
    st.set("use-world-coords", True)
    try:
        st.set("weld-vertices", False)
    except Exception:  # noqa: BLE001
        pass
    nthreads = threads or int(os.environ.get("IFC_GEOM_THREADS", 0)) or max(1, min(16, multiprocessing.cpu_count() // 3))
    it = ifcopenshell.geom.iterator(st, f, nthreads, include=targets)
    if not it.initialize():
        return
    while True:
        sh = it.get()
        try:
            g = sh.geometry
            e = elements.get(sh.guid)
            if e is not None:
                e.geo = _mesh_stats(g.verts, g.faces)
        except Exception as ex:  # noqa: BLE001
            print(f"[ifc.index] geometry failed for {sh.guid}: {ex}", file=sys.stderr)
        if not it.next():
            break


# --- public view for W4/W5 --------------------------------------------------------------------------------
def ifc_index(path: str) -> dict:
    """JSON-friendly summary for the API and the 3D viewer:
    {"path", "schema", "project", "storeys": [{guid, name, elevation, n_elements}],
     "elements": [{guid, class, name, long_name, storey, storey_name, bbox}]}"""
    idx = load_index(path)
    names = {s.guid: s.name for s in idx.storeys}
    counts: dict[str, int] = {}
    for e in idx.elements.values():
        if e.storey:
            counts[e.storey] = counts.get(e.storey, 0) + 1
    return {
        "path": idx.path, "schema": idx.schema, "project": idx.project_name,
        "storeys": [{**asdict(s), "n_elements": counts.get(s.guid, 0)} for s in idx.storeys],
        "elements": [{"guid": e.guid, "class": e.cls, "name": e.name, "long_name": e.long_name,
                      "storey": e.storey, "storey_name": names.get(e.storey), "parent": e.parent,
                      "bbox": list(e.geo.bbox) if e.geo and e.geo.bbox else None}
                     for e in idx.elements.values()],
    }


if __name__ == "__main__":  # python -m stoa.solvers.ifc.index data/ifc_models/x.ifc [...]
    for a in sys.argv[1:]:
        t = time.perf_counter()
        ix = load_index(a)
        print(a, ix.schema, f"scale={ix.unit_scale}", f"{len(ix.elements)} elements", f"{len(ix.storeys)} storeys",
              f"build={ix.build_seconds:.1f}s total={time.perf_counter() - t:.1f}s")
