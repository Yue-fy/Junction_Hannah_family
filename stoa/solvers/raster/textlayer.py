"""A text layer for raster drawings (PNG/JPEG floor plans, historical scans): every printed text with its box.

PDFs have a text layer (PyMuPDF) that tools like the agent's `find_text` search; scans and PNG plans have none, so
for them the agent had only `look` (one VLM call on the whole, downscaled image: small print on a 3000 px HABS sheet
is unreadable at that size). This module reads the text tile by tile with the shared VLM (Qwen3-VL text spotting:
JSON list of {bbox_2d, text}), maps every box back to ORIGINAL image pixels, merges duplicates from the tile
overlaps, and caches the result per image. On top of it, deterministic helpers:

    layer = text_layer(path)                -> TextLayer (items with image_px boxes; cost charged once)
    find_text(path, "sauna")                -> hits (text, box, score), fuzzy and accent/case-insensitive
    scales(layer) / dimensions(layer) / areas(layer)  -> parsed "1:100", 1/4" = 1'-0" (1:48), 12'-6", 14.5 m²
    summary(path)                           -> a compact text table for an LLM (the agent's `table` tool)

No new dependency: the VLM is the OCR engine (no tesseract/paddle/rapidocr in $JUNCTION_VENV).
"""

from __future__ import annotations

import concurrent.futures as cf
import contextvars
import difflib
import json
import math
import os
import re
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image

from stoa import llm
from stoa.contract import Evidence, record_cost

Image.MAX_IMAGE_PIXELS = None

OCR_PROMPT = ("Read ALL text printed on this image of a technical drawing: titles, room names, notes, dimensions, "
              "scale notes, sheet numbers, legends. Output a JSON list with one entry per line of text: "
              '[{"bbox_2d": [x1, y1, x2, y2], "text": "<text exactly as printed>"}]. '
              "Coordinates are 0-1000 relative to this image. Output [] if there is no text.")
VERSION = "tl1"
_ITEM = re.compile(r'\{[^{}]*?"bbox_2d"\s*:\s*\[([^\]]*)\][^{}]*?"text"\s*:\s*"((?:[^"\\]|\\.)*)"[^{}]*\}')
CACHE_DIR = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")) / "artifacts" / \
    "W3" / "textlayer"


@dataclass
class TextItem:
    text: str
    box: list[float]  # original-image pixels [x0, y0, x1, y1]
    tile: int = 0

    @property
    def cx(self) -> float:
        return (self.box[0] + self.box[2]) / 2

    @property
    def cy(self) -> float:
        return (self.box[1] + self.box[3]) / 2


@dataclass
class TextLayer:
    path: str
    size: tuple[int, int]
    items: list[TextItem] = field(default_factory=list)
    tiles: int = 1
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0
    notes: list[str] = field(default_factory=list)

    def text(self) -> str:
        return "\n".join(i.text for i in self.items)


# -- tiling ---------------------------------------------------------------------------------------------------------

def tile_boxes(w: int, h: int, tile: int = 1100, overlap: float = 0.12) -> list[tuple[int, int, int, int]]:
    """Grid of overlapping crops so that each crop is at most ~tile px per side (1x1 for small images)."""
    nx, ny = max(1, math.ceil(w / tile)), max(1, math.ceil(h / tile))
    tw = min(w, int(w / nx * (1 + overlap))) if nx > 1 else w
    th = min(h, int(h / ny * (1 + overlap))) if ny > 1 else h
    out = []
    for gy in range(ny):
        for gx in range(nx):
            x0 = 0 if nx == 1 else round(gx * (w - tw) / (nx - 1))
            y0 = 0 if ny == 1 else round(gy * (h - th) / (ny - 1))
            out.append((x0, y0, x0 + tw, y0 + th))
    return out


def _unescape(s: str) -> str:
    try:
        return json.loads(f'"{s}"')
    except ValueError:
        return s.replace('\\"', '"')


def parse_items(text: str, w: int, h: int, max_repeat: int = 6) -> list[TextItem]:
    """Qwen bbox_2d JSON (0..1000 relative) -> items in this image's pixels; drops loops (text repeated > N times)."""
    raw = []
    for m in _ITEM.finditer(text):
        try:
            b = [float(v) for v in m.group(1).split(",")]
        except ValueError:
            continue
        t = _unescape(m.group(2)).strip()
        if len(b) == 4 and t:
            raw.append(TextItem(t, [b[0] / 1000 * w, b[1] / 1000 * h, b[2] / 1000 * w, b[3] / 1000 * h]))
    counts: dict[str, int] = {}
    for i in raw:
        counts[i.text] = counts.get(i.text, 0) + 1
    return [i for i in raw if counts[i.text] <= max_repeat]


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0


def _overlap_small(a, b) -> float:
    """Intersection over the smaller box (a text cut at a tile border lies inside the full one)."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    s = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return ix * iy / s if s > 0 else 0.0


def merge_items(items: list[TextItem]) -> list[TextItem]:
    """De-duplicate texts read twice in tile overlaps: same/contained text with overlapping boxes -> keep the longer."""
    kept: list[TextItem] = []
    for it in sorted(items, key=lambda i: -len(i.text)):
        n = norm(it.text)
        dup = False
        for k in kept:
            nk = norm(k.text)
            if (n == nk and _iou(it.box, k.box) > 0.2) or (n and n in nk and _overlap_small(it.box, k.box) > 0.5):
                dup = True
                break
        if not dup:
            kept.append(it)
    return sorted(kept, key=lambda i: (round(i.cy / 25), i.cx))


# -- reading --------------------------------------------------------------------------------------------------------

_mem: dict[str, TextLayer] = {}
_locks: dict[str, threading.Lock] = {}
_glock = threading.Lock()


def _abspath(path: str) -> Path:
    p = Path(path)
    if p.is_absolute() or p.exists():
        return p
    return Path(os.environ.get("STOA_DATA", ".")) / path


def _disk_key(path: str, tile: int, backend: str) -> Path:
    import hashlib

    h = hashlib.sha1(f"{VERSION}|{Path(path).name}|{tile}|{backend}".encode()).hexdigest()[:16]
    return CACHE_DIR / f"{Path(path).stem[:60]}.{h}.json"


def text_layer(path: str, backend: str = "local", tile: int = 1100, upscale_to: int = 2000,
               max_tokens: int = 2500, workers: int = 6) -> TextLayer:
    """All printed text of a raster drawing with image_px boxes. Cached in memory and on disk (artifacts/W3/textlayer);
    the cost of the reading is charged to the caller every time (cold-run accounting, as elsewhere in raster)."""
    key = f"{path}|{backend}|{tile}"
    with _glock:
        lk = _locks.setdefault(key, threading.Lock())
    with lk:
        if key in _mem:  # read earlier in this process (another question on the same drawing): already paid
            return _mem[key]
        f = _disk_key(path, tile, backend)
        if f.exists():
            d = json.loads(f.read_text())
            d["items"] = [TextItem(**i) for i in d["items"]]
            d["size"] = tuple(d["size"])
            tl = TextLayer(**d)
            # persisted from an earlier run: bill it as computed, so warm and cold runs cost the same
            record_cost(llm_tokens_in=tl.tokens_in, llm_tokens_out=tl.tokens_out, llm_calls=tl.calls or tl.tiles,
                        gpu_seconds=llm.gpu_seconds_estimate(tl.tokens_in, tl.tokens_out))
        else:
            tl = _read(path, backend, tile, upscale_to, max_tokens, workers)  # llm.chat bills each call itself
            try:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(json.dumps(asdict(tl)))
            except OSError:
                pass
        _mem[key] = tl
        return tl


def _read(path: str, backend: str, tile: int, upscale_to: int, max_tokens: int, workers: int) -> TextLayer:
    t0 = time.perf_counter()
    img = Image.open(_abspath(path)).convert("RGB")
    W, H = img.size
    boxes = tile_boxes(W, H, tile)
    tl = TextLayer(path=path, size=(W, H), tiles=len(boxes))

    def read_one(i_b, split: bool = True):
        i, (x0, y0, x1, y1) = i_b
        crop = img.crop((x0, y0, x1, y1))
        s = min(3.0, upscale_to / max(crop.size))
        if s > 1.05:
            crop = crop.resize((round(crop.width * s), round(crop.height * s)), Image.LANCZOS)
        r = llm.chat(OCR_PROMPT, images=[crop], backend=backend, max_tokens=max_tokens,
                     max_pixels=upscale_to * upscale_to, max_side=max(upscale_to, 1024), cache=True)
        notes, tin, tout, ncalls = [], 0, 0, 1
        items = parse_items(r.text, x1 - x0, y1 - y0)
        if r.finish_reason == "length" and len(items) < 3:  # looping output: one retry with a repetition penalty
            r2 = llm.chat(OCR_PROMPT, images=[crop], backend=backend, max_tokens=max_tokens,
                          max_pixels=upscale_to * upscale_to, max_side=max(upscale_to, 1024), cache=True,
                          extra_body={"repetition_penalty": 1.1})
            items2 = parse_items(r2.text, x1 - x0, y1 - y0)
            ncalls = 2  # both tries are billed: `extra` = the one that is not kept in `r`
            if len(items2) > len(items):
                tin, tout = r.prompt_tokens or 0, r.completion_tokens or 0
                items, r = items2, r2
            else:
                tin, tout = r2.prompt_tokens or 0, r2.completion_tokens or 0
            notes.append(f"tile {i}: retry with repetition_penalty")
        elif r.finish_reason == "length":
            notes.append(f"tile {i}: text list truncated at {max_tokens} tokens")
        if r.finish_reason == "length" and split and min(x1 - x0, y1 - y0) >= 300:
            # a dense tile (R1 08:45: 9 of 20 CubiCasa tiles hit the cap, one plan came back with 3 texts): read its
            # 2x2 sub-tiles too (each upscaled more) and merge; boxes go through the same overlap merge
            mx, my = (x0 + x1) // 2, (y0 + y1) // 2
            ox, oy = int(0.06 * (x1 - x0)), int(0.06 * (y1 - y0))
            for it in items:
                it.box = [round(it.box[0] + x0, 1), round(it.box[1] + y0, 1), round(it.box[2] + x0, 1),
                          round(it.box[3] + y0, 1)]
                it.tile = i
            for sb in [(x0, y0, mx + ox, my + oy), (mx - ox, y0, x1, my + oy), (x0, my - oy, mx + ox, y1),
                       (mx - ox, my - oy, x1, y1)]:
                sub, snotes, sti, sto, snc = read_one((i, sb), split=False)  # boxes come back in image px
                items += sub
                tin, tout, ncalls = tin + sti, tout + sto, ncalls + snc
            notes.append(f"tile {i}: truncated -> re-read as 2x2 sub-tiles")
            return items, notes, tin + (r.prompt_tokens or 0), tout + (r.completion_tokens or 0), ncalls
        for it in items:
            it.box = [round(it.box[0] + x0, 1), round(it.box[1] + y0, 1), round(it.box[2] + x0, 1),
                      round(it.box[3] + y0, 1)]
            it.tile = i
        return items, notes, tin + (r.prompt_tokens or 0), tout + (r.completion_tokens or 0), ncalls

    with cf.ThreadPoolExecutor(min(workers, len(boxes))) as ex:
        ctxs = [contextvars.copy_context() for _ in boxes]
        res = list(ex.map(lambda cb: cb[0].run(read_one, cb[1]), zip(ctxs, enumerate(boxes))))
    allitems = []
    for items, notes, ti, to, nc in res:
        allitems += items
        tl.notes += notes
        tl.tokens_in += ti
        tl.tokens_out += to
        tl.calls += nc
    tl.items = merge_items(allitems)
    tl.seconds = round(time.perf_counter() - t0, 2)
    return tl


# -- search ---------------------------------------------------------------------------------------------------------

def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s/:.'\"=-]", " ", s)).strip()


def match_score(query: str, text: str) -> float:
    """1.0 = query contained in text (normalised); else the best fuzzy ratio of the query vs a same-length window."""
    q, t = norm(query), norm(text)
    if not q or not t:
        return 0.0
    if q in t:
        return 1.0
    qw, tw = q.split(), t.split()
    best = 0.0
    for i in range(max(1, len(tw) - len(qw) + 1)):
        win = " ".join(tw[i:i + len(qw)])
        best = max(best, difflib.SequenceMatcher(None, q, win).ratio())
    return best


def find_text(path: str, query: str, threshold: float = 0.8, layer: TextLayer | None = None, **kw) -> list[dict]:
    """Hits of `query` in the drawing's text layer, best first: [{text, box, score}] (boxes in image px)."""
    tl = layer or text_layer(path, **kw)
    hits = [{"text": i.text, "box": i.box, "score": round(match_score(query, i.text), 2)} for i in tl.items]
    return sorted([h for h in hits if h["score"] >= threshold], key=lambda h: -h["score"])


def evidence(path: str, hits: list[dict], note: str, limit: int = 6) -> list[Evidence]:
    return [Evidence(file=path, page=0, bbox=[round(v, 1) for v in h["box"]], bbox_space="image_px",
                     note=f"{note}: '{h['text'][:60]}'") for h in hits[:limit]]


# -- parsers: scale, dimensions, areas -------------------------------------------------------------------------------

_FRAC = r"(\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)"
_RATIO = re.compile(r"(?<![\d/.])1\s*[:]\s*(\d{1,3}(?:[ ,.]\d{3})+|\d{1,6})(?![\d])")
_IMPERIAL = re.compile(_FRAC + r"\s*(?:\"|”|''|in\.?|inch(?:es)?)\s*=\s*(\d+)\s*(?:'|’|ft\.?|feet|foot)\s*-?\s*(\d+)?\s*(?:\"|”)?",
                       re.I)
_SCALE_WORD = re.compile(r"scale|mittakaava|mittak\.|maßstab|massstab|échelle|echelle|skala|scala|escala|schaal|"
                         r"\bm\s*1\s*:|\bm\.?\s?k\.?(?=\s*1\s*[:/])|\bmst\.?(?=\s*1\s*[:/])", re.I)
# '1/500' is a scale only next to a scale word (ASEMAPIIRROS M.K. 1/500, Skala 1/100): bare '1/16' is a fraction
_STD_SCALES = {20, 25, 50, 100, 200, 250, 400, 500, 1000, 2000, 2500, 5000, 10000, 20000, 25000, 50000}
_SLASH = re.compile(r"(?<![\d/.])1\s*/\s*(\d{1,3}(?:[ ,.]\d{3})+|\d{2,6})(?![\d/\"”'’])")


def _frac(s: str) -> float:
    s = s.strip()
    if " " in s:
        a, b = s.split(None, 1)
        return float(a) + _frac(b)
    if "/" in s:
        a, b = s.split("/")
        return float(a) / float(b)
    return float(s)


def parse_scales(text: str) -> list[dict]:
    """Scale notes in one text line -> [{ratio, kind, text}] ('1:100' -> 100; 1/4" = 1'-0" -> 48)."""
    out = []
    for m in _IMPERIAL.finditer(text):
        try:
            inch = _frac(m.group(1))
            real_in = int(m.group(2)) * 12 + (int(m.group(3)) if m.group(3) else 0)
        except (ValueError, ZeroDivisionError):
            continue
        if inch > 0 and real_in > 0:
            out.append({"ratio": round(real_in / inch, 2), "kind": "imperial", "text": m.group(0).strip()})
    if not out:
        for m in _RATIO.finditer(text):
            n = int(re.sub(r"[ ,.]", "", m.group(1)))
            if 1 <= n <= 1_000_000:
                out.append({"ratio": float(n), "kind": "ratio", "text": m.group(0)})
    if not out:
        worded = bool(_SCALE_WORD.search(text))
        for m in _SLASH.finditer(text):
            n = int(re.sub(r"[ ,.]", "", m.group(1)))
            if (worded and 10 <= n <= 1_000_000) or n in _STD_SCALES:  # 'POHJA 1/100' (Finnish plan title)
                out.append({"ratio": float(n), "kind": "ratio", "text": m.group(0)})
    return out


def scales(tl: TextLayer) -> list[dict]:
    """Scale notes of the drawing; lines that say 'scale'/'mittakaava'/... rank first. Each hit carries its box."""
    out = []
    for it in tl.items:
        for s in parse_scales(it.text):
            s.update(box=it.box, line=it.text, labelled=bool(_SCALE_WORD.search(it.text)))
            out.append(s)
    return sorted(out, key=lambda s: (not s["labelled"], s["kind"] != "imperial"))


_FTIN = re.compile(r"(?<![\d.])(\d{1,3})\s*(?:'|’|ft)\s*-?\s*(\d{1,2}(?:\s+\d/\d+|\.\d+)?)?\s*(?:\"|”)?")
_AREA = re.compile(r"(\d+(?:[.,]\d+)?)\s*(m²|m2|m\^2|sq\.?\s*ft|ft²|sf)\b", re.I)


def dimensions(tl: TextLayer) -> list[dict]:
    """Imperial dimension strings (12'-6" -> 12.5 ft) with boxes. Metric dimension numbers are too ambiguous to
    parse without context (a bare '3600' may be mm, a room number or a year), so they are left to the reader."""
    out = []
    for it in tl.items:
        if parse_scales(it.text):
            continue
        for m in _FTIN.finditer(it.text):
            ft = int(m.group(1)) + (_frac(m.group(2)) / 12 if m.group(2) else 0)
            out.append({"feet": round(ft, 3), "text": m.group(0).strip(), "box": it.box})
    return out


def areas(tl: TextLayer) -> list[dict]:
    out = []
    for it in tl.items:
        for m in _AREA.finditer(it.text):
            v = float(m.group(1).replace(",", "."))
            unit = "m2" if m.group(2).lower().startswith("m") else "ft2"
            out.append({"value": v, "unit": unit, "text": m.group(0), "line": it.text, "box": it.box})
    return out


def summary(path: str, max_lines: int = 80, **kw) -> str:
    """Compact table of the text layer for an LLM: texts with their positions (x%, y%), then parsed facts."""
    tl = text_layer(path, **kw)
    W, H = tl.size
    lines = [f"text layer of {Path(path).name} ({W}x{H} px, {len(tl.items)} texts read by a VLM in {tl.tiles} "
             f"tile(s); positions in % of width/height):"]
    for it in tl.items[:max_lines]:
        lines.append(f"- ({100 * it.cx / W:.0f}%, {100 * it.cy / H:.0f}%) {it.text[:90]}")
    if len(tl.items) > max_lines:
        lines.append(f"... {len(tl.items) - max_lines} more (use find_text)")
    sc = scales(tl)
    if sc:
        lines.append("scale notes: " + "; ".join(f"'{s['line'][:50]}' -> 1:{s['ratio']:g}" for s in sc[:3]))
    else:
        lines.append("scale notes: none found (lengths/areas need a scale bar, a dimension string or an assumption)")
    try:  # graphic scale bars (CPU only here: labels from this layer, snapped to the drawn bar)
        from stoa.solvers.raster import scalebar

        for b in scalebar.bars(path, reread=False, layer=tl)[:2]:
            lines.append(b.describe())
    except Exception:  # noqa: BLE001 - optional fact
        pass
    ds = dimensions(tl)
    if ds:
        lines.append(f"dimension strings ({len(ds)}): " + ", ".join(f"{d['text']}={d['feet']:g} ft" for d in ds[:12]))
    ar = areas(tl)
    if ar:
        lines.append(f"printed areas ({len(ar)}): " + ", ".join(f"{a['line'][:30]}" for a in ar[:12]))
    return "\n".join(lines)
