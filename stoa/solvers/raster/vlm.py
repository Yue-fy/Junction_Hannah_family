"""VLM calls for the raster solver: room-label reading and symbol pointing, with per-image caching.

Every call goes through the shared server (`stoa.llm`, local Qwen3-VL by default). Output coordinates are
mapped back to ORIGINAL image pixels, so they can be used directly as Evidence(bbox_space="image_px").
"""

from __future__ import annotations

import collections
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
    # Charged as if computed, even on a disk-cache hit (the cache is a dev convenience; the cost score should
    # reflect a cold run). Latency under a shared, busy server overstates GPU time: an upper bound.
    record_cost(llm_tokens_in=r.prompt_tokens or 0, llm_tokens_out=r.completion_tokens or 0, llm_calls=1,
                gpu_seconds=r.latency_s if r.backend == "local" else 0.0,
                **({"api_calls": 1, "api_tokens_in": r.prompt_tokens or 0,
                    "api_tokens_out": r.completion_tokens or 0} if r.backend != "local" else {}))


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
                max_tokens: int = 1500) -> tuple[list[Item], CallLog, bool]:
    """Room labels of one drawing (cached per process; R1's on-disk outputs reused when present)."""
    def run():
        log = CallLog()
        f = R1_CACHE / (Path(key).name + ".labels.v2.json")
        if backend == "local" and f.exists():
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
        items, looped = parse_labels(text, img.width, img.height)
        if looped:
            log.notes.append("LOOP: one label text repeated > 6 times; label counts unreliable")
        return items, log

    (items, log), hit = _cached(("labels", key, backend), run)
    return items, log, hit


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
