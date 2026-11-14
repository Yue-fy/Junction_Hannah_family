"""VLM calls for the raster solver: room-label reading and symbol pointing, with per-image caching.

Every call goes through the shared server (`stoa.llm`, local Qwen3-VL by default). Output coordinates are
mapped back to ORIGINAL image pixels, so they can be used directly as Evidence(bbox_space="image_px").
"""

from __future__ import annotations

import collections
import concurrent.futures as cf
import contextvars
import json
import math
import os
import re
import threading
from pathlib import Path
from dataclasses import dataclass, field

from PIL import Image

from stoa import llm
from stoa.contract import record_cost
from stoa.solvers.raster.classes import SYMBOL_DEF, label_class


@dataclass
class Item:
    x: float  # original-image pixels
    y: float
    text: str  # label text or object name
    cls: str | None = None


@dataclass
class CallLog:
    raw: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0
    notes: list[str] = field(default_factory=list)


_cache: dict[tuple, tuple[list[Item], CallLog]] = {}
_locks: dict[tuple, threading.Lock] = {}
_glock = threading.Lock()


def _cached(key: tuple, fn):
    """Compute once per key even when several questions on the same image run concurrently.
    Callers that hit the cache are charged nothing (the work was already paid for)."""
    with _glock:
        lk = _locks.setdefault(key, threading.Lock())
    with lk:
        if key in _cache:
            return _cache[key], True
        val = fn()
        _cache[key] = val
        return val, False


def _charge(r: llm.ChatResult) -> None:
    """No-op: since night cac7ef8 (23:52) `llm.chat` itself reports every call (cache hits included, billed as
    computed, GPU time from the token estimate) to the caller's CostMeter. Recording here as well billed every raster
    call twice (measured 03:40: a 2,055-token call metered as 4,110 tokens and 2 calls)."""
    return None


def upscaled(img: Image.Image, target_px: int) -> tuple[Image.Image, float]:
    """Enlarge small drawings so thin symbols/text cover enough vision patches. Returns (image, factor)."""
    f = math.sqrt(target_px / max(1, img.width * img.height))
    if f <= 1.05:
        return img, 1.0
    f = min(f, 3.0)
    return img.resize((round(img.width * f), round(img.height * f)), Image.LANCZOS), f


# Room labels: R1's measured method (experiments/r1/room_labels/run.py on night-R1, prompt v2: no example codes,
# because v1 made the model echo examples back). Image upscaled 2x (max side 2400), one call per drawing,
# JSON boxes; duplicates (same text + IoU > 0.3) removed; output with one text repeated > 6x = a loop.
LABEL_PROMPT = ("Locate every room name or room code that is printed as text inside the rooms of this floor plan. "
                "Output a JSON list, one entry per printed label: "
                '[{"bbox_2d": [x1, y1, x2, y2], "text": "<label exactly as printed>"}]. '
                "Skip room areas (numbers with m2), dimensions and furniture.")
_ITEM = re.compile(r'\{[^{}]*?"bbox_2d"\s*:\s*\[([^\]]*)\][^{}]*?"text"\s*:\s*"([^"]*)"[^{}]*\}')
R1_CACHE = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")) / "artifacts" / \
    "R1" / "room_labels"
LOOP = 6


def _r1_image(img: Image.Image, scale: float = 2.0, max_side: int = 2400) -> Image.Image:
    s = min(scale, max_side / max(img.size))
    return img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS) if s != 1 else img


def _iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0


def parse_labels(text: str, w: int, h: int) -> tuple[list[Item], bool]:
    """-> (unique label items in original px, looped?). Boxes are 0..1000 relative to the image."""
    raw = []
    for m in _ITEM.finditer(text):
        try:
            box = [float(v) for v in m.group(1).split(",")]
        except ValueError:
            continue
        if len(box) == 4:
            raw.append((box, m.group(2)))
    reps = collections.Counter(t for _, t in raw)
    looped = bool(reps) and reps.most_common(1)[0][1] > LOOP
    kept: list[tuple] = []
    for box, t in raw:
        if re.search(r"m²|m2", t) or any(t == t2 and _iou(box, b2) > 0.3 for b2, t2 in kept):
            continue
        kept.append((box, t))
    items = []
    for box, t in kept:
        x0, y0, x1, y1 = box[0] / 1000 * w, box[1] / 1000 * h, box[2] / 1000 * w, box[3] / 1000 * h
        it = Item((x0 + x1) / 2, (y0 + y1) / 2, t, label_class(t))
        it.box = [x0, y0, x1, y1]  # type: ignore[attr-defined]
        items.append(it)
    return items, looped


def read_labels(img: Image.Image, key: str, backend: str = "local", target_px: int = 0,
                max_tokens: int = 1500, tiled_fix: bool = True) -> tuple[list[Item], CallLog, bool]:
    """Room labels of one drawing (cached per process; R1's on-disk outputs reused when present)."""
    def run():
        log = CallLog()
        f = R1_CACHE / (Path(key).name + ".labels.v2.json")
        from stoa.solvers.raster.textlayer import file_tag  # R1's outputs are keyed by name: dataset files only

        if backend == "local" and f.exists() and not file_tag(key):
            d = json.loads(f.read_text())
            text = d["text"]
            c = d.get("cost", {})
            log = CallLog(text, c.get("in", 0), c.get("out", 0), c.get("s", 0.0), ["reused R1 v2 label output"])
            record_cost(llm_tokens_in=log.tokens_in, llm_tokens_out=log.tokens_out, llm_calls=1,
                        gpu_seconds=log.seconds)
        else:
            r = llm.chat(LABEL_PROMPT, images=[_r1_image(img)], backend=backend, max_tokens=max_tokens,
                         max_pixels=6_000_000, cache=True)
            _charge(r)
            text = r.text
            log = CallLog(text, r.prompt_tokens or 0, r.completion_tokens or 0, r.latency_s)
            if r.finish_reason == "length":
                log.notes.append("label list truncated (max_tokens)")
        first_out = log.tokens_out  # truncation is judged on the first (one-shot) call only
        items, looped = parse_labels(text, img.width, img.height)
        if looped:  # R1 (inbox 00:22): a retry with repetition_penalty 1.15 fixes 26 of 28 loops on dev
            try:
                r = llm.chat(LABEL_PROMPT, images=[_r1_image(img)], backend=backend, max_tokens=max_tokens,
                             max_pixels=6_000_000, cache=True, extra_body={"repetition_penalty": 1.15})
                _charge(r)
                items2, looped2 = parse_labels(r.text, img.width, img.height)
                log.notes.append(f"loop retry with repetition_penalty 1.15: {'still looping' if looped2 else 'ok'}")
                log.tokens_in += r.prompt_tokens or 0
                log.tokens_out += r.completion_tokens or 0
                if not looped2:
                    items, looped = items2, False
            except Exception as e:  # noqa: BLE001
                log.notes.append(f"loop retry failed: {type(e).__name__}")
        if looped:
            log.notes.append("LOOP: one label text repeated > 6 times; label counts unreliable")
        truncated = any("truncated" in n for n in log.notes) or first_out >= max_tokens - 10
        if tiled_fix and (truncated or looped):
            # The one-shot list ran out of tokens / looped (24% of TRAIN drawings). Re-read in 2x2 tiles and take
            # the classes where that helped on those TRAIN drawings (experiments/w3/tiled_labels.py, n=119):
            # bedrooms 48 -> 58%, balconies 58 -> 70%; WC rooms (77 -> 75) and saunas (52 -> 53) keep the one-shot.
            try:
                t_items, t_log = read_labels_tiled(img, backend, max_tokens=max_tokens)
                log.tokens_in += t_log.tokens_in
                log.tokens_out += t_log.tokens_out
                log.seconds += t_log.seconds
                take = {"bedroom", "balcony"}
                items = [i for i in items if i.cls not in take] + [i for i in t_items if i.cls in take]
                log.notes.append(f"tiled re-read (one-shot list {'looped' if looped else 'truncated'}): bedroom/"
                                 f"balcony labels from the {len(t_items)} tiled items")
            except Exception as e:  # noqa: BLE001
                log.notes.append(f"tiled re-read failed: {type(e).__name__}")
        return items, log

    (items, log), hit = _cached(("labels", key, backend, tiled_fix), run)
    return items, log, hit


def read_labels_tiled(img: Image.Image, backend: str = "local", grid: int = 2, overlap: float = 0.15,
                      max_tokens: int = 1500) -> tuple[list[Item], CallLog]:
    """Room labels read tile by tile (grid x grid, overlapping), for drawings whose one-shot list loops or hits
    max_tokens. Each tile gets the same prompt at ~2x; items are mapped back to original pixels and duplicates in
    the overlaps (same text, centres closer than ~3% of the image) are dropped."""
    log = CallLog(notes=[f"tiled label reading {grid}x{grid}"])
    W, H = img.size
    tw, th = int(W / grid * (1 + overlap)), int(H / grid * (1 + overlap))
    boxes = []
    for gy in range(grid):
        for gx in range(grid):
            x0 = min(max(0, int(gx * W / grid - overlap * W / grid / 2)), max(0, W - tw))
            y0 = min(max(0, int(gy * H / grid - overlap * H / grid / 2)), max(0, H - th))
            boxes.append((x0, y0, min(W, x0 + tw), min(H, y0 + th)))
    merged: list[Item] = []
    tol = 0.03 * max(W, H)

    def read_tile(b):
        x0, y0, x1, y1 = b
        tile = img.crop((x0, y0, x1, y1))
        notes, t_in, t_out, secs = [], 0, 0, 0.0
        r = llm.chat(LABEL_PROMPT, images=[_r1_image(tile)], backend=backend, max_tokens=max_tokens,
                     max_pixels=6_000_000, cache=True)
        _charge(r)
        t_in, t_out, secs = r.prompt_tokens or 0, r.completion_tokens or 0, r.latency_s
        items, looped = parse_labels(r.text, tile.width, tile.height)
        if looped or r.finish_reason == "length":
            r = llm.chat(LABEL_PROMPT, images=[_r1_image(tile)], backend=backend, max_tokens=max_tokens,
                         max_pixels=6_000_000, cache=True, extra_body={"repetition_penalty": 1.15})
            _charge(r)
            t_in += r.prompt_tokens or 0
            t_out += r.completion_tokens or 0
            items2, looped2 = parse_labels(r.text, tile.width, tile.height)
            if not looped2:
                items, looped = items2, False
            notes.append(f"tile {x0},{y0}: retry {'ok' if not looped2 else 'still looping'}")
        if looped:  # keep the tile's items but drop the text that repeats
            top = collections.Counter(i.text for i in items).most_common(1)[0][0]
            items = [i for i in items if i.text != top]
        return b, items, notes, t_in, t_out, secs

    with cf.ThreadPoolExecutor(len(boxes)) as ex:  # tiles in parallel (latency), cost meter kept per thread
        ctxs = [contextvars.copy_context() for _ in boxes]  # copied HERE, in the caller's thread
        results = list(ex.map(lambda cb: cb[0].run(read_tile, cb[1]), zip(ctxs, boxes)))
    for (x0, y0, x1, y1), items, notes, t_in, t_out, secs in results:
        log.notes += notes
        log.tokens_in += t_in
        log.tokens_out += t_out
        log.seconds = max(log.seconds, secs)
        for i in items:
            i.x += x0
            i.y += y0
            if hasattr(i, "box"):
                i.box = [i.box[0] + x0, i.box[1] + y0, i.box[2] + x0, i.box[3] + y0]  # type: ignore[attr-defined]
            if any(m.text == i.text and abs(m.x - i.x) < tol and abs(m.y - i.y) < tol for m in merged):
                continue
            merged.append(i)
    return merged, log


POINT_PROMPT = (
    "This is an architectural floor plan. Find every {name} symbol: {definition}. "
    "Point to each one exactly once. Output JSON: [{{\"point_2d\": [x, y], \"label\": \"{name}\"}}] "
    "with coordinates 0-1000 relative to the image. Output [] if there are none."
)


def point_symbols(img: Image.Image, key: str, cls: str, backend: str = "local", target_px: int = 2_000_000,
                  max_tokens: int = 1500) -> tuple[list[Item], CallLog, bool]:
    name, definition = SYMBOL_DEF[cls]

    def run():
        big, f = upscaled(img, target_px)
        r = llm.chat(POINT_PROMPT.format(name=name, definition=definition), images=[big], backend=backend,
                     max_tokens=max_tokens, max_pixels=max(target_px, 1_000_000) + 500_000, cache=True)
        _charge(r)
        pts = llm.parse_points(r.text, r.images[0])
        if not pts:  # truncated JSON: salvage the complete entries
            pts = [llm.Point(*r.images[0].to_original(float(a) / 1000 * r.images[0].sent_w,
                                                      float(b) / 1000 * r.images[0].sent_h))
                   for a, b in re.findall(r"\[\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\]", r.text)]
        # de-duplicate points closer than ~1.5% of the image diagonal (model repeats)
        diag = math.hypot(img.width, img.height) * f
        pts = llm.nms_points(pts, 0.015 * diag)
        items = [Item(p.x / f, p.y / f, name, cls) for p in pts]
        log = CallLog(r.text, r.prompt_tokens or 0, r.completion_tokens or 0, r.latency_s)
        if r.finish_reason == "length":
            log.notes.append("point list truncated (max_tokens)")
        return items, log

    (items, log), hit = _cached(("points", key, cls, backend, target_px), run)
    return items, log, hit


DIRECT_PROMPT = "{question}\n\nReply with only the final count as a single integer, nothing else."


def direct_count(img: Image.Image, question: str, backend: str = "local") -> tuple[int | None, CallLog]:
    r = llm.chat(DIRECT_PROMPT.format(question=question.strip()), images=[img], backend=backend, max_tokens=16,
                 cache=True)
    _charge(r)
    m = re.search(r"-?\d+", r.text)
    return (int(m.group()) if m else None), CallLog(r.text, r.prompt_tokens or 0, r.completion_tokens or 0,
                                                    r.latency_s)
