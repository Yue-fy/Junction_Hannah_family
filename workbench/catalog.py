"""Drawings the expert can pick from: human names, licence credit lines, safe paths, renders.

Only files under $STOA_DATA/data are ever opened, and only renderable drawing formats (raster images, PDF, SVG).
Drawings of the sealed `test` split are left out of the picker (D15: test drawings are never opened for
development, and the expert's questions become a development split).
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import random
import re
from pathlib import Path

from stoa.data import data_root, source_of

RASTER_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".bmp"}
VECTOR_EXT = {".pdf", ".svg"}
RENDER_EXT = RASTER_EXT | VECTOR_EXT

SOURCE_LABEL = {
    "cubicasa5k": "Finnish apartment plans (CubiCasa5K)",
    "swiss_dwellings": "Swiss apartment floors",
    "ifc_models": "BIM model sheets (from IFC models)",
    "ifc_bench": "IFC benchmark models",
    "opening_design": "US permit drawing sets (OpeningDesign)",
    "habs": "Historic American drawings (HABS/HAER)",
    "finna": "Helsinki archive drawings (Finna)",
    "europeana": "European archive drawings (Europeana)",
    "wikimedia": "Wikimedia Commons drawings",
}
HISTORICAL = ("habs", "finna", "europeana", "wikimedia")


class BadPath(ValueError):
    pass


def data_dir() -> Path:
    return (data_root() / "data").resolve()


HUMAN_PREFIX = "human/drawings/"


def human_drawings_dir() -> Path:
    """$JUNCTION_SHARED/human/drawings: drawings that are not in the dataset (Stoa's examples, the expert's uploads).
    Flat folder; each drawing may have a sidecar '<file>.json' with title / credit / license."""
    from workbench.store import human_dir

    return human_dir() / "drawings"


def is_added(rel: str) -> bool:
    return rel.startswith(HUMAN_PREFIX)


def canon(path: str) -> str:
    """Any accepted spelling of a drawing path -> the workbench key: 'data/...' (dataset) or 'human/drawings/<name>'.
    An absolute path is accepted only when it points into one of those two folders (predictions and saved
    questions carry absolute paths for added drawings, because the solvers need a real file)."""
    if not path or "\x00" in path:
        raise BadPath("empty path")
    p = Path(path)
    if not p.is_absolute():
        return path
    rp = p.resolve()
    hd = human_drawings_dir().resolve()
    if rp.parent == hd:
        return HUMAN_PREFIX + rp.name
    if data_dir() in rp.parents:
        return str(rp.relative_to(data_dir().parent))
    raise BadPath("path outside the dataset")


def solver_path(rel: str) -> str:
    """Workbench key -> the path the pipeline gets: dataset-relative as is, an added drawing as its absolute path."""
    return str(safe_file(rel, exts=None)) if is_added(rel) else rel


def safe_file(rel: str, exts: set[str] | None = RENDER_EXT) -> Path:
    """Dataset-relative 'data/...' path (or 'human/drawings/<name>') -> absolute file, or BadPath. Blocks '..',
    absolute paths, NUL bytes, symlinks that leave the folder, and (by default) anything that is not a drawing format."""
    if rel and is_added(rel) and "\x00" not in rel:
        name = rel[len(HUMAN_PREFIX):]
        if not name or "/" in name or "\\" in name or name.startswith(".") or name.endswith(".json"):
            raise BadPath("bad name for an added drawing")
        hd = human_drawings_dir().resolve()
        p = (hd / name).resolve()
        if p.parent != hd:
            raise BadPath("path outside the added-drawings folder")
        if not p.is_file():
            raise FileNotFoundError(rel)
        if exts is not None and p.suffix.lower() not in exts:
            raise BadPath(f"not a drawing file ({p.suffix})")
        return p
    if not rel or "\x00" in rel or rel.startswith(("/", "\\")) or not rel.startswith("data/"):
        raise BadPath("path must be dataset-relative and start with data/")
    if ".." in Path(rel).parts or "\\" in rel:
        raise BadPath("'..' is not allowed")
    p = (data_root() / rel).resolve()
    if data_dir() not in p.parents:
        raise BadPath("path outside the dataset")
    if not p.is_file():
        raise FileNotFoundError(rel)
    if exts is not None and p.suffix.lower() not in exts:
        raise BadPath(f"not a drawing file ({p.suffix})")
    return p


# --- licences and titles ---------------------------------------------------------------------------------
@functools.lru_cache(maxsize=16)
def _licence_table(source: str) -> tuple[tuple[str, str] | None, dict[str, dict]]:
    p = data_root() / "data" / source / "LICENSE.md"
    default, per = None, {}
    if not p.exists():
        return default, per
    text = p.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"All files:\s*(.+?)\.\s+Credit:\s*(.+)", text)
    if m:
        default = (m.group(1).strip(), m.group(2).strip())
    cols = None
    for line in text.splitlines():
        if not line.startswith("|"):
            cols = None if not line.strip() else cols
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        low = [c.lower() for c in cells]
        if any(c in ("file", "model", "files") for c in low) and any("licen" in c for c in low):
            def col(pred):
                return next((i for i, c in enumerate(low) if pred(c)), None)
            cols = {"file": col(lambda c: c in ("file", "model", "files")), "lic": col(lambda c: "licen" in c),
                    "credit": col(lambda c: "credit" in c or "copyright" in c), "title": col(lambda c: c == "title"),
                    "src": col(lambda c: c == "source")}
            continue
        if cols and not set(line) <= set("|-: ") and len(cells) > cols["lic"]:
            def get(k):
                i = cols[k]
                return cells[i] if i is not None and i < len(cells) else ""
            f = get("file").strip("`")
            row = {"license": get("lic"), "credit": get("credit"), "title": get("title"), "url": get("src")}
            per[f] = row
            per.setdefault(Path(f).stem, row)
    return default, per


def meta_of(rel: str) -> dict:
    """{'license', 'credit', 'title', 'url'} for a dataset file (best effort)."""
    if is_added(rel):
        side = human_drawings_dir() / (rel[len(HUMAN_PREFIX):] + ".json")
        m = {}
        try:
            m = json.loads(side.read_text(encoding="utf-8")) if side.is_file() else {}
        except (OSError, ValueError):
            pass
        return {"license": m.get("license") or "", "title": m.get("title") or "", "url": m.get("url") or "",
                "credit": m.get("credit") or "added by our team (not part of the Stoa dataset)"}
    src = source_of(rel)
    default, per = _licence_table(src)
    sub = rel.split("/", 2)[2] if rel.count("/") >= 2 else rel
    for k in (sub, Path(rel).name, Path(rel).stem):
        if k in per:
            return per[k]
    if src == "ifc_models":
        from stoa.data import ifc_model_for

        model = ifc_model_for(rel)
        if model and Path(model).name in per:
            return {**per[Path(model).name], "title": per[Path(model).name]["title"] + " - " + Path(rel).stem}
    lic, credit = default or ("see LICENSE.md", f"data/{src}/LICENSE.md")
    return {"license": lic, "credit": credit, "title": "", "url": ""}


def human_name(rel: str) -> str:
    src = source_of(rel)
    stem = Path(rel).stem
    m = meta_of(rel)
    if src == "cubicasa5k":
        mm = re.match(r"([a-z_]+)-(\d+)", stem)
        return f"Apartment plan {mm.group(2)} ({mm.group(1).replace('_', ' ')})" if mm else f"Apartment plan {stem}"
    if src == "swiss_dwellings":
        mm = re.match(r"site(\d+)_bldg(\d+)_floor(\d+)", stem)
        return f"Swiss site {mm.group(1)}, building {mm.group(2)}, floor {mm.group(3)}" if mm else stem
    if m.get("title"):
        t = m["title"]
        return t if len(t) <= 110 else t[:107] + "..."
    return stem.replace("_", " ")


def credit_line(rel: str) -> str:
    m = meta_of(rel)
    bits = [b for b in (m.get("credit"), m.get("license")) if b]
    return " · ".join(bits) if bits else f"see data/{source_of(rel)}/LICENSE.md"


def added_drawings() -> list[dict]:
    """Cards for the drawings in human/drawings (newest first)."""
    d = human_drawings_dir()
    if not d.is_dir():
        return []
    files = [p for p in d.iterdir() if p.is_file() and p.suffix.lower() in RENDER_EXT and not p.name.startswith(".")]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [card(HUMAN_PREFIX + p.name) for p in files]


# --- the picker -------------------------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def _test_groups() -> frozenset[str]:
    # no try/except on purpose: if the splits cannot be read, the picker must fail, not show test drawings
    from stoa.eval.splits import split_of_group

    return frozenset(g for g, s in split_of_group().items() if s == "test")


def is_sealed(rel: str) -> bool:
    from stoa.data import drawing_group

    if is_added(rel):
        return False
    return drawing_group(rel) in _test_groups()


@functools.lru_cache(maxsize=1)
def all_drawings() -> tuple[str, ...]:
    root = data_root()
    out = []
    for dirpath, _dirs, files in os.walk(root / "data"):
        for f in files:
            if Path(f).suffix.lower() in RENDER_EXT:
                rel = str((Path(dirpath) / f).relative_to(root))
                out.append(rel)
    out.sort()
    return tuple(r for r in out if not is_sealed(r))


@functools.lru_cache(maxsize=1)
def _questions_per_path() -> dict[str, int]:
    from collections import Counter

    from stoa.data import load_questions

    return dict(Counter(q.path for q in load_questions()))


def _pick(rows: list[str], n: int, seed: str) -> list[str]:
    rows = sorted(rows)
    random.Random(seed).shuffle(rows)
    return sorted(rows[:n])


@functools.lru_cache(maxsize=1)
def curated() -> list[dict]:
    """The default visual list: a few drawings per source, dev drawings with questions + historical scans."""
    from stoa.eval.splits import load_split

    dev_paths = sorted({q.path for q in load_split("dev")})
    by_src: dict[str, list[str]] = {}
    for p in dev_paths:
        if Path(p).suffix.lower() in RENDER_EXT:
            by_src.setdefault(source_of(p), []).append(p)
    every = all_drawings()
    for src in HISTORICAL:
        by_src[src] = [p for p in every if source_of(p) == src and Path(p).suffix.lower() in RASTER_EXT]
    if "opening_design" in by_src:  # all question sheets, then other PDFs of those sets
        extra = [p for p in every if source_of(p) == "opening_design" and p.lower().endswith(".pdf")]
        by_src["opening_design"] = sorted(set(by_src["opening_design"])) + \
            _pick([p for p in extra if p not in by_src["opening_design"]], 12, "od")
    n_per = {"cubicasa5k": 24, "swiss_dwellings": 16, "ifc_models": 16, "opening_design": 24,
             "habs": 12, "finna": 12, "europeana": 8, "wikimedia": 8}
    groups = []
    for src in ("cubicasa5k", "swiss_dwellings", "ifc_models", "opening_design", *HISTORICAL):
        rows = by_src.get(src, [])
        if src == "ifc_models":  # one sheet per model (dev models first, then other non-test models), plans first
            others = [p for p in every if source_of(p) == "ifc_models" and p.lower().endswith(".pdf")]
            seen, keep = set(), []
            pref = re.compile(r"ground|level-?0?1|floor-?0?1|1st|first|eg|erdgeschoss", re.I)
            for p in sorted(rows, key=lambda r: ("plan" not in r, not pref.search(r), r)) + \
                    sorted(others, key=lambda r: ("plan" not in r, not pref.search(r), r)):
                model = re.split(r"_(plan|section|elev)", Path(p).stem)[0]
                if model not in seen:
                    seen.add(model)
                    keep.append(p)
            rows = keep
        rows = rows if src in ("opening_design", "ifc_models") else _pick(rows, n_per[src], src)
        rows = rows[: n_per[src]]
        groups.append({"source": src, "label": SOURCE_LABEL.get(src, src),
                       "historical": src in HISTORICAL,
                       "drawings": [card(p) for p in rows]})
    return groups


def card(rel: str) -> dict:
    return {"path": rel, "name": human_name(rel), "source": source_of(rel),
            "n_questions": _questions_per_path().get(rel, 0), "credit": credit_line(rel)}


def search(q: str, limit: int = 60) -> list[dict]:
    words = [w for w in re.split(r"\s+", q.lower().strip()) if w]
    if not words:
        return []
    out = []
    for p in all_drawings():
        hay = (p + " " + (meta_of(p).get("title") or "")).lower()
        if all(w in hay for w in words):
            out.append(card(p))
            if len(out) >= limit:
                break
    return out


# --- rendering --------------------------------------------------------------------------------------------
def cache_dir() -> Path:
    d = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")) / "artifacts" / "H" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def render(rel: str, page: int = 0, maxside: int = 2400) -> dict:
    """Render a drawing page to an image file in the cache. Returns
    {'file': Path, 'mime', 'w', 'h', 'n_pages', 'kind': 'raster'|'vector', 'scale' (img px per source px),
     'zoom' (img px per pdf pt), 'rot': [a,b,c,d,e,f] (PyMuPDF rotation_matrix)}."""
    p = safe_file(rel)
    st = p.stat()
    key = hashlib.sha1(f"{rel}|{page}|{maxside}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:20]
    meta_p = cache_dir() / f"{key}.json"
    if meta_p.exists():
        meta = json.loads(meta_p.read_text())
        meta["file"] = cache_dir() / meta["file"]
        if meta["file"].exists():
            return meta
    ext = p.suffix.lower()
    if ext in RASTER_EXT:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = 400_000_000
        with Image.open(p) as im:
            W, H = im.size
            im = im.convert("RGB") if im.mode not in ("RGB", "L") else im
            s = min(1.0, maxside / max(W, H))
            if s < 1.0:
                im = im.resize((max(1, round(W * s)), max(1, round(H * s))), Image.LANCZOS)
            w, h = im.size
            jpeg = ext in (".jpg", ".jpeg")
            fname = f"{key}.{'jpg' if jpeg else 'png'}"
            im.save(cache_dir() / fname, **({"quality": 88} if jpeg else {"optimize": False}))
        meta = {"file": fname, "mime": "image/jpeg" if jpeg else "image/png", "w": w, "h": h, "n_pages": 1,
                "kind": "raster", "scale": w / W, "src_w": W, "src_h": H, "zoom": None, "rot": None}
    else:
        import pymupdf as fitz

        with fitz.open(p) as doc:
            n = doc.page_count
            pg = doc[min(max(page, 0), n - 1)]
            r = pg.rect
            zoom = min(maxside / max(r.width, r.height), 8.0)
            pix = pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            fname = f"{key}.png"
            pix.save(cache_dir() / fname)
            rm = pg.rotation_matrix
            meta = {"file": fname, "mime": "image/png", "w": pix.width, "h": pix.height, "n_pages": n,
                    "kind": "vector", "scale": None, "zoom": zoom, "rot": [rm.a, rm.b, rm.c, rm.d, rm.e, rm.f],
                    "page_w": r.width, "page_h": r.height}
    meta_p.write_text(json.dumps(meta))
    meta["file"] = cache_dir() / meta["file"]
    return meta


def to_img_box(meta: dict, bbox: list[float], space: str | None) -> list[float] | None:
    """Evidence bbox -> pixel box on the rendered image."""
    if not bbox or len(bbox) != 4:
        return None
    x0, y0, x1, y1 = (float(v) for v in bbox)
    if meta["kind"] == "raster":
        s = meta["scale"]
        return [x0 * s, y0 * s, x1 * s, y1 * s]
    a, b, c, d, e, f = meta["rot"]
    z = meta["zoom"]
    pts = [(x * a + y * c + e, x * b + y * d + f) for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
    xs, ys = [p[0] * z for p in pts], [p[1] * z for p in pts]
    return [min(xs), min(ys), max(xs), max(ys)]


def from_img_box(meta: dict, box: list[float]) -> tuple[list[float], str] | None:
    """Pixel box on the rendered image -> (bbox, bbox_space) in the contract's Evidence coordinates."""
    if not box or len(box) != 4:
        return None
    x0, y0, x1, y1 = (float(v) for v in box)
    if meta["kind"] == "raster":
        s = meta["scale"]
        return [round(v / s, 1) for v in (x0, y0, x1, y1)], "image_px"
    import pymupdf as fitz

    inv = ~fitz.Matrix(*meta["rot"])
    z = meta["zoom"]
    pts = [fitz.Point(x / z, y / z) * inv for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
    xs, ys = [p.x for p in pts], [p.y for p in pts]
    return [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)], "pdf_pt"


def views_for(path: str, evidence: list[dict]) -> tuple[list[dict], list[dict]]:
    """Group evidence into drawable views ({path, page, img url, w, h, boxes}) and a list of evidence that
    cannot be drawn (IFC elements, DXF entities, ...). The question's own drawing always comes first."""
    views: dict[tuple, dict] = {}
    other: list[dict] = []

    def view(rel: str, page: int) -> dict | None:
        k = (rel, page)
        if k not in views:
            try:
                meta = render(rel, page)
            except Exception:  # noqa: BLE001
                return None
            views[k] = {"path": rel, "page": page, "n_pages": meta["n_pages"], "w": meta["w"], "h": meta["h"],
                        "img": f"api/img?path={_q(rel)}&page={page}", "name": human_name(rel),
                        "credit": credit_line(rel), "boxes": [], "_meta": meta}
        return views[k]

    def _key(f):
        try:
            return canon(f)
        except BadPath:
            return f

    if Path(path).suffix.lower() in RENDER_EXT:
        pages = sorted({int(e.get("page") or 0) for e in evidence
                        if _key(e.get("file") or path) == path and e.get("bbox")}) or [0]
        for pg in pages:
            view(path, pg)
    for i, e in enumerate(evidence):
        f = e.get("file") or path
        try:
            f = canon(f)  # an added drawing's evidence carries its absolute path
        except BadPath:
            pass
        bbox = e.get("bbox")
        if bbox and Path(f).suffix.lower() in RENDER_EXT:
            v = view(f, int(e.get("page") or 0))
            box = to_img_box(v["_meta"], bbox, e.get("bbox_space")) if v else None
            if box:
                v["boxes"].append({"i": i, "box": box, "note": e.get("note", ""),
                                   "point": bbox[0] == bbox[2] and bbox[1] == bbox[3]})
                continue
        other.append({"i": i, **{k: e.get(k) for k in ("file", "page", "ifc_guid", "note", "bbox")}})
    out = []
    for v in views.values():
        v.pop("_meta", None)
        out.append(v)
    return out, other


def _q(s: str) -> str:
    from urllib.parse import quote

    return quote(s, safe="")
