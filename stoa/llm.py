"""Shared LLM / VLM client for every agent (owner: R2).

Backends, all OpenAI-compatible ("local2" = a second local vLLM, $LLM2_BASE_URL, default :8002):
  - "local"  : our vLLM server ($LLM_BASE_URL, default http://127.0.0.1:8001/v1). Model alias "default"
               always points at whatever serving/start.sh launched (see `served_model()`).
  - "nvidia" : NVIDIA hosted API (https://integrate.api.nvidia.com/v1, key in $NVIDIA_API_KEY).
               Default model nvidia/nemotron-3.5-super-vl-120b-a12b. Rate-limited across *all* processes
               on this machine through a file lock (env NVIDIA_RPM, default 30 requests/minute).
  - "gemini" : Google Gemini API, OpenAI-compatible endpoint (key in $GEMINI_API_KEY, from Sat 10:50). Default model
               $GEMINI_MODEL or gemini-3-flash-preview (gemini-3.1-pro-preview for hard cases). Google's rules: no
               abuse, so it is for visible, high-value steps only (demo, low-confidence escalation), NEVER in bulk eval
               loops. Enforced here: a per-agent daily call cap ($GEMINI_MAX_CALLS_PER_DAY, default 200; agent =
               $STOA_AGENT), every request logged with its purpose ($JUNCTION_SHARED/logs/gemini_calls.jsonl; pass
               chat(..., purpose="...") or $STOA_GEMINI_PURPOSE), GEMINI_RPM (default 10/min) across processes.
               Boxes: Gemini answers box_2d as [ymin, xmin, ymax, xmax] in 0..1000 (swap before parse_boxes).

Quick start:
    from stoa.llm import chat, parse_boxes
    r = chat("How many doors are in this floor plan? Answer with one integer.", images=["plan.png"])
    print(r.text)
    r = chat('Locate every door. Output JSON [{"bbox_2d":[x1,y1,x2,y2],"label":"door"}].', images=[img])
    boxes = parse_boxes(r.text, r.images[0])          # -> boxes in ORIGINAL image pixels

Coordinates: Qwen3-VL / Qwen3.5 / Qwen3.6 answer grounding prompts in relative 0..1000 coordinates of the
image they saw. `parse_boxes/parse_points` map them back to the original image's pixels (and through tiles,
see `tile_image`). Never print or log API keys.
"""

from __future__ import annotations

import base64
import contextlib
import contextvars
import fcntl
import hashlib
import io
import json
import math
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # drawings can be huge; we downscale ourselves

SHARED = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))

BACKENDS: dict[str, dict[str, Any]] = {
    "local": {
        "base_url": os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8001/v1"),
        "api_key_env": None,
        "model": os.environ.get("LLM_MODEL", "default"),
        "coords": "rel1000",
        "timeout": 300.0,
    },
    # A second local vLLM (e.g. a bigger reasoning model on :8002 next to the shared :8001), billed like "local".
    # Lets one component (the agent's planner) use another model while every atomic solver stays on :8001.
    "local2": {
        "base_url": os.environ.get("LLM2_BASE_URL", "http://127.0.0.1:8002/v1"),
        "api_key_env": None,
        "model": os.environ.get("LLM2_MODEL", "default"),
        "coords": "rel1000",
        "timeout": 300.0,
    },
    "nvidia": {
        "base_url": os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        "api_key_env": "NVIDIA_API_KEY",
        "model": os.environ.get("NVIDIA_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b"),
        "coords": "rel1000",  # verify per model with experiments/r2/grounding_check.py
        "timeout": 300.0,
    },
    "gemini": {
        "base_url": os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
        "api_key_env": "GEMINI_API_KEY",
        "model": os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview"),
        "coords": "yx1000",  # box_2d = [ymin, xmin, ymax, xmax], 0..1000
        "timeout": 300.0,
    },
}

def is_local(backend: str) -> bool:
    """Our own GPU (billed in GPU seconds), as opposed to a hosted API (billed per call)."""
    return backend in ("local", "local2")


# Default pixel budget per image. Qwen3-VL: 1 visual token per 32x32 px => 3.1 Mpx ~ 3,000 tokens.
DEFAULT_MAX_PIXELS = int(os.environ.get("LLM_MAX_PIXELS", 3_200_000))
DEFAULT_MAX_SIDE = 4096


# --------------------------------------------------------------------------------------------- images
@dataclass
class ImageInfo:
    """How an image was sent, so model coordinates can be mapped back to the original file's pixels.

    original pixel = offset + sent pixel / scale
    `offset` is non-zero when the image is a tile cut out of a bigger image (see `tile_image`).
    """

    orig_w: int
    orig_h: int
    sent_w: int
    sent_h: int
    scale: float = 1.0  # sent / original (<= 1 when downscaled)
    offset: tuple[float, float] = (0.0, 0.0)  # top-left of this image inside the parent image (parent px)

    def to_original(self, x: float, y: float) -> tuple[float, float]:
        return (self.offset[0] + x / self.scale, self.offset[1] + y / self.scale)


@dataclass
class Tile:
    image: Image.Image
    x0: int
    y0: int  # top-left in the parent image's pixels


def load_image(src: Any) -> Image.Image:
    """Accept a PIL image, a path, raw bytes, or a numpy array (HxW[xC], uint8)."""
    if isinstance(src, Image.Image):
        img = src
    elif isinstance(src, (str, Path)):
        img = Image.open(src)
        img.load()
    elif isinstance(src, (bytes, bytearray)):
        img = Image.open(io.BytesIO(src))
        img.load()
    else:  # numpy
        img = Image.fromarray(src)
    if img.mode not in ("RGB", "L"):
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            rgba = img.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")
    return img


def downscale(img: Image.Image, max_pixels: int = DEFAULT_MAX_PIXELS, max_side: int = DEFAULT_MAX_SIDE
              ) -> tuple[Image.Image, float]:
    """Shrink (never enlarge) to fit the pixel budget. Returns (image, scale = new/old)."""
    w, h = img.size
    s = min(1.0, math.sqrt(max_pixels / max(1, w * h)), max_side / max(w, h))
    if s >= 0.999:
        return img, 1.0
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    return img.resize((nw, nh), Image.LANCZOS), nw / w


def tile_image(img: Image.Image, tile: int = 1280, overlap: int = 160) -> list[Tile]:
    """Cut an image into overlapping square-ish tiles (parent pixel offsets kept for mapping back).

    Counting tip: de-duplicate detections in the overlap zones (e.g. by box IoU / point distance in
    parent pixels) before counting.
    """
    w, h = img.size
    step = max(1, tile - overlap)
    xs = list(range(0, max(1, w - overlap), step)) or [0]
    ys = list(range(0, max(1, h - overlap), step)) or [0]
    tiles = []
    for y0 in ys:
        for x0 in xs:
            x1, y1 = min(w, x0 + tile), min(h, y0 + tile)
            # shift the last row/column back so every tile is full-size when possible
            x0b, y0b = max(0, x1 - tile), max(0, y1 - tile)
            tiles.append(Tile(img.crop((x0b, y0b, x1, y1)), x0b, y0b))
    # drop exact duplicates created by the shift
    seen, out = set(), []
    for t in tiles:
        if (t.x0, t.y0) not in seen:
            seen.add((t.x0, t.y0))
            out.append(t)
    return out


def render_pdf_page(path: str | Path, page: int = 0, dpi: int = 150, max_pixels: int | None = None
                    ) -> tuple[Image.Image, float]:
    """Render a PDF page to RGB. Returns (image, px_per_pt) so pixel boxes map to PDF points: pt = px / px_per_pt.

    If max_pixels is given, the dpi is lowered so the render fits the budget.
    """
    import pymupdf

    with pymupdf.open(path) as doc:
        pg = doc[page]
        zoom = dpi / 72.0
        if max_pixels:
            w_pt, h_pt = pg.rect.width, pg.rect.height
            zoom = min(zoom, math.sqrt(max_pixels / max(1.0, w_pt * h_pt)))
        pix = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return img, zoom


def _encode(img: Image.Image, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    if fmt.upper() == "JPEG":
        img.convert("RGB").save(buf, format="JPEG", quality=92)
        mime = "image/jpeg"
    else:
        img.save(buf, format="PNG", optimize=False)
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(buf.getvalue()).decode()}"


def prepare_image(src: Any, max_pixels: int = DEFAULT_MAX_PIXELS, max_side: int = DEFAULT_MAX_SIDE,
                  offset: tuple[float, float] = (0.0, 0.0), fmt: str = "PNG") -> tuple[dict, ImageInfo]:
    """-> (OpenAI image_url content part, ImageInfo). Pass a `Tile` to keep its parent offset."""
    if isinstance(src, Tile):
        offset = (float(src.x0), float(src.y0))
        src = src.image
    img = load_image(src)
    small, scale = downscale(img, max_pixels, max_side)
    info = ImageInfo(img.width, img.height, small.width, small.height, scale, offset)
    return {"type": "image_url", "image_url": {"url": _encode(small, fmt)}}, info


# --------------------------------------------------------------------------------------------- cost
@dataclass
class Cost:
    """Cost of the LLM calls made inside a `cost_meter()` block (Stoa scores cost: lower is better).

    gpu_seconds = amortised estimate from tokens (see PREFILL_TPS / DECODE_TPS), not HTTP wall time;
    api_calls counts hosted (nvidia) calls only. Cache hits are billed like computed calls.
    """

    llm_tokens_in: int = 0
    llm_tokens_out: int = 0
    gpu_seconds: float = 0.0
    api_calls: int = 0
    calls: int = 0
    cached_calls: int = 0  # informational: how many of `calls` were served from the disk cache
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def add(self, res: "ChatResult") -> None:
        with self._lock:
            self.calls += 1
            self.llm_tokens_in += res.prompt_tokens or 0
            self.llm_tokens_out += res.completion_tokens or 0
            self.cached_calls += 1 if res.cached else 0
            # Disk-cache hits are billed as if computed (F, 00:53): a warm dev run must cost the same as the
            # cold test run Stoa will see.
            if is_local(res.backend):
                self.gpu_seconds += gpu_seconds_estimate(res.prompt_tokens or 0, res.completion_tokens or 0, res.backend)
            else:
                self.api_calls += 1

    def as_dict(self) -> dict:
        return {"llm_tokens_in": self.llm_tokens_in, "llm_tokens_out": self.llm_tokens_out,
                "gpu_seconds": round(self.gpu_seconds, 3), "api_calls": self.api_calls}

    def __str__(self) -> str:
        return (f"cost: calls={self.calls} tok_in={self.llm_tokens_in} tok_out={self.llm_tokens_out} "
                f"gpu_s={self.gpu_seconds:.2f} api_calls={self.api_calls}")


_METER: contextvars.ContextVar[Cost | None] = contextvars.ContextVar("stoa_llm_cost", default=None)


@contextlib.contextmanager
def cost_meter():
    """`with cost_meter() as c: ...chat(...)...` -> c.as_dict(). Nested meters all get charged."""
    parent = _METER.get()
    c = Cost()
    tok = _METER.set(c)
    try:
        yield c
    finally:
        _METER.reset(tok)
        if parent is not None:  # roll up into the enclosing meter
            with parent._lock:
                parent.calls += c.calls
                parent.llm_tokens_in += c.llm_tokens_in
                parent.llm_tokens_out += c.llm_tokens_out
                parent.gpu_seconds += c.gpu_seconds
                parent.api_calls += c.api_calls
                parent.cached_calls += c.cached_calls


# Amortised GPU time per token on the shared server (Qwen3-VL-8B bf16, RTX PRO 6000, batched by vLLM).
# Measured at saturation: dev run of 2,160 questions in ~62 s at ~1.2k prompt tokens each => ~40k prompt tok/s;
# we use a conservative 25k. Decode: ~1k tok/s aggregate at typical batch sizes. HTTP wall time is NOT used,
# because it includes queueing behind other agents' requests (F, 00:19: 0.5 s idle vs 7.8 s busy).
PREFILL_TPS = float(os.environ.get("LLM_PREFILL_TPS", 25_000))
DECODE_TPS = float(os.environ.get("LLM_DECODE_TPS", 1_000))
# :8002 = Qwen3.6-35B-A3B-FP8 (D21, free-text answers). Measured 09:40 on the same GPU, 16 concurrent requests
# (experiments/r2/tput.py): prefill 25.3k tok/s (8B under other agents' load at the same time: 14.5k), decode 722 tok/s
# (8B: 856). ~3B active parameters, so per token it costs about what the 8B does; decode is billed at the measured
# 700 tok/s (1.4x the 8B constant) so the demo's cost line stays honest (D21 item 4).
PER_BACKEND_TPS = {"local2": (float(os.environ.get("LLM2_PREFILL_TPS", 25_000)),
                              float(os.environ.get("LLM2_DECODE_TPS", 700)))}


def gpu_seconds_estimate(tokens_in: int, tokens_out: int, backend: str = "local") -> float:
    pre, dec = PER_BACKEND_TPS.get(backend, (PREFILL_TPS, DECODE_TPS))
    return round(tokens_in / pre + tokens_out / dec, 4)


def _charge(res: "ChatResult") -> "ChatResult":
    m = _METER.get()
    if m is not None:
        m.add(res)
    # Report to the contract's CostMeter (the eval attributes it per question). Cache hits included, billed
    # as computed, so warm and cold runs cost the same.
    try:
        from stoa.contract import record_cost
    except ImportError:  # older contract without cost metering
        return res
    tin, tout = res.prompt_tokens or 0, res.completion_tokens or 0
    if is_local(res.backend):
        record_cost(llm_calls=1, llm_tokens_in=tin, llm_tokens_out=tout, gpu_seconds=gpu_seconds_estimate(tin, tout, res.backend))
    else:
        record_cost(llm_calls=1, llm_tokens_in=tin, llm_tokens_out=tout, api_calls=1, api_tokens_in=tin,
                    api_tokens_out=tout)
    return res


# --------------------------------------------------------------------------------------------- client
@dataclass
class ChatResult:
    text: str
    images: list[ImageInfo] = field(default_factory=list)  # one per input image, in order
    model: str = ""
    backend: str = ""
    latency_s: float = 0.0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning: str | None = None  # thinking text if the server returned it separately
    texts: list[str] = field(default_factory=list)  # all n samples when n > 1 (texts[0] == text)
    finish_reason: str | None = None
    logprobs: list[dict] | None = None  # [{"t": token, "lp": logprob, "top": [[alt, lp], ...]}] (chat(logprobs=K))
    cached: bool = False


_clients: dict[str, Any] = {}
_clients_lock = threading.Lock()


def _client(backend: str):
    from openai import OpenAI

    with _clients_lock:
        if backend not in _clients:
            cfg = BACKENDS[backend]
            key = os.environ.get(cfg["api_key_env"], "") if cfg["api_key_env"] else "EMPTY"
            if cfg["api_key_env"] and not key:
                raise RuntimeError(f"backend {backend!r} needs ${cfg['api_key_env']} in the environment")
            _clients[backend] = OpenAI(base_url=cfg["base_url"], api_key=key, timeout=cfg["timeout"],
                                       max_retries=0)
        return _clients[backend]


_TB_SEEN: dict[str, tuple[bool, float]] = {}


def text_backend(default: str = "local") -> str:
    """Backend for long FREE-TEXT answers (e.g. ifc fact-card answers): $STOA_TEXT_BACKEND (e.g. "local2" = Qwen3.6-35B-A3B
    on :8002) when that server answers /v1/models (re-checked every 60 s), else `default`. Unset -> `default`, so callers
    can use it unconditionally. R2 09:07: ifc_bench dev free text, 35B vs 8B on the same fact cards: 8B judge 62.0 vs 54.5
    (21 wins / 6 losses); hosted Nemotron re-judging the 27 discordant pairs: 6 vs 0."""
    want = os.environ.get("STOA_TEXT_BACKEND", "").strip()
    if not want or want == default or want not in BACKENDS:
        return default
    now = time.time()
    ok, seen = _TB_SEEN.get(want, (False, 0.0))
    if now - seen > 60:
        try:
            _client(want).with_options(timeout=3.0).models.list()
            ok = True
        except Exception:  # noqa: BLE001  (second server down: fall back silently)
            ok = False
        _TB_SEEN[want] = (ok, now)
    return want if ok else default


def served_model(backend: str = "local") -> str:
    """The concrete model id behind the "default" alias (first id listed by /v1/models)."""
    try:
        data = _client(backend).models.list().data
        ids = [m.id for m in data]
        # LoRA adapters are listed too (vLLM sets `parent` on them): the base model is the first without a parent
        base = [m.id for m in data if m.id != "default" and not (getattr(m, "model_extra", None) or {}).get("parent")
                and not getattr(m, "parent", None)]
        return base[0] if base else next((i for i in ids if i != "default"), ids[0] if ids else "")
    except Exception as e:  # noqa: BLE001
        return f"unavailable ({type(e).__name__})"


_SERVED: dict[str, tuple[float, frozenset]] = {}


def served_models(backend: str = "local", ttl: float = 60.0) -> frozenset:
    """Every model id the server lists (base names, aliases and LoRA adapters), cached for `ttl` seconds.
    Empty set if the server is unreachable."""
    now = time.time()
    hit = _SERVED.get(backend)
    if hit and now - hit[0] < ttl:
        return hit[1]
    try:
        ids = frozenset(m.id for m in _client(backend).models.list().data)
    except Exception:  # noqa: BLE001
        ids = frozenset()
    _SERVED[backend] = (now, ids)
    return ids


def _nvidia_throttle(backend: str = "nvidia") -> None:
    """Space out hosted API calls (nvidia, gemini) across every process on this machine (file lock + timestamp)."""
    rpm = float(os.environ.get(f"{backend.upper()}_RPM", {"nvidia": 30, "gemini": 10}.get(backend, 10)))
    interval = 60.0 / max(rpm, 0.1)
    lock = SHARED / "locks" / f"{backend}-api.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            last = float((f.read().strip() or "0"))
            wait = last + interval - time.time()
            if wait > 0:
                time.sleep(wait)
            f.seek(0)
            f.truncate()
            f.write(f"{time.time():.3f}")
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


GEMINI_LOG = SHARED / "logs" / "gemini_calls.jsonl"


def _agent_id() -> str:
    return os.environ.get("STOA_AGENT") or os.environ.get("AGENT_ID") or "unknown"


def gemini_calls_today(agent: str | None = None) -> int:
    """Gemini requests this agent sent today (from the shared call log)."""
    agent, day, n = agent or _agent_id(), time.strftime("%Y-%m-%d"), 0
    try:
        with open(GEMINI_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                n += d.get("agent") == agent and d.get("day") == day
    except FileNotFoundError:
        pass
    return n


def _gemini_guard() -> None:
    cap = int(os.environ.get("GEMINI_MAX_CALLS_PER_DAY", 200))
    n = gemini_calls_today()
    if n >= cap:
        raise RuntimeError(f"Gemini daily call cap reached for agent {_agent_id()!r} ({n} >= {cap}; Google's no-abuse "
                           "rule, COMMON.md). Use the local server or hosted Nemotron.")


def _gemini_log(model: str, purpose: str | None, ok: bool, status: str, t0: float, resp: Any = None) -> None:
    u = getattr(resp, "usage", None)
    rec = {"time": time.strftime("%H:%M:%S"), "day": time.strftime("%Y-%m-%d"), "agent": _agent_id(), "model": model,
           "purpose": purpose or os.environ.get("STOA_GEMINI_PURPOSE") or "unspecified", "ok": ok, "status": status,
           "tokens_in": getattr(u, "prompt_tokens", None), "tokens_out": getattr(u, "completion_tokens", None),
           "latency_s": round(time.time() - t0, 2)}
    try:
        GEMINI_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(GEMINI_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass


def _cache_path(key_obj: Any) -> Path:
    h = hashlib.sha256(json.dumps(key_obj, sort_keys=True, default=str).encode()).hexdigest()
    root = Path(os.environ.get("STOA_LLM_CACHE_DIR", str(SHARED / "artifacts" / "llm-cache")))
    return root / h[:2] / f"{h}.json"


def chat(
    messages: str | list[dict],
    images: Sequence[Any] | None = None,
    *,
    backend: str = "local",
    model: str | None = None,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    top_p: float | None = None,
    seed: int | None = None,
    n: int = 1,
    thinking: bool | None = False,
    json_schema: dict | None = None,
    max_pixels: int = DEFAULT_MAX_PIXELS,
    max_side: int = DEFAULT_MAX_SIDE,
    image_format: str = "PNG",
    retries: int = 6,
    cache: bool | None = None,
    extra_body: dict | None = None,
    logprobs: int = 0,
    purpose: str | None = None,
) -> ChatResult:
    """One chat completion.

    messages : a prompt string, or OpenAI-style messages. `images` are inserted (before the text) into the
               LAST user message, which is how Qwen-VL models like it. Images can be PIL / path / bytes /
               numpy / `Tile`.
    thinking : False -> ask hybrid-thinking models (Qwen3.5/3.6, Nemotron) to answer directly; True -> let
               them think (slower, sometimes better at arithmetic); None -> model default.
    json_schema: a JSON schema dict -> guided decoding (vLLM `structured_outputs`/`guided_json`).
    cache    : on-disk response cache (temperature 0 only). Default from env STOA_LLM_CACHE=1.
    logprobs : K > 0 -> return per-token logprobs of the first choice with the top-K alternatives in
               `ChatResult.logprobs` (see `answer_prob`). Free on vLLM; use it for a real confidence.
    purpose  : backend "gemini" only: why this call is made (logged; COMMON.md asks for every call's purpose).
    """
    cfg = BACKENDS[backend]
    model = model or cfg["model"]
    msgs: list[dict] = [{"role": "user", "content": messages}] if isinstance(messages, str) else \
        [dict(m) for m in messages]
    if system:
        msgs.insert(0, {"role": "system", "content": system})

    infos: list[ImageInfo] = []
    if images:
        parts = []
        for im in images:
            part, info = prepare_image(im, max_pixels, max_side, fmt=image_format)
            parts.append(part)
            infos.append(info)
        idx = max(i for i, m in enumerate(msgs) if m["role"] == "user")
        content = msgs[idx]["content"]
        text_parts = [{"type": "text", "text": content}] if isinstance(content, str) else list(content)
        msgs[idx]["content"] = parts + text_parts

    body: dict[str, Any] = dict(extra_body or {})
    if thinking is not None:
        body.setdefault("chat_template_kwargs", {})["enable_thinking"] = bool(thinking)
    if json_schema is not None:
        if is_local(backend):
            body["structured_outputs"] = {"json": json_schema}
        else:
            body["guided_json"] = json_schema
    kwargs: dict[str, Any] = dict(model=model, messages=msgs, max_tokens=max_tokens, temperature=temperature)
    if top_p is not None:
        kwargs["top_p"] = top_p
    if seed is not None:
        kwargs["seed"] = seed
    if n > 1:  # one prefill (image encoded once), n decodes: cheap self-consistency on vLLM
        kwargs["n"] = n
    if logprobs:
        kwargs["logprobs"] = True
        kwargs["top_logprobs"] = int(logprobs)
    if backend == "gemini":  # Google's OpenAI-compatible endpoint: no vLLM-only fields
        body.pop("chat_template_kwargs", None)
        body.pop("guided_json", None)
        if thinking is not None:
            kwargs["reasoning_effort"] = "high" if thinking else "low"
        if json_schema is not None:
            kwargs["response_format"] = {"type": "json_schema", "json_schema": {"name": "answer", "schema": json_schema}}
        retries = min(retries, 3)
    if body:
        kwargs["extra_body"] = body

    use_cache = (os.environ.get("STOA_LLM_CACHE") == "1") if cache is None else cache
    use_cache = use_cache and temperature == 0.0
    cpath = None
    if use_cache:
        concrete = served_model(backend) if (is_local(backend) and model == "default") else model
        cpath = _cache_path({"b": backend, "m": concrete, "k": {**kwargs, "model": concrete}})
        if cpath.exists():
            d = json.loads(cpath.read_text())
            return _charge(ChatResult(images=infos, cached=True, **d))

    from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

    client = _client(backend)
    delay = 2.0
    last_err: Exception | None = None
    restart_budget = float(os.environ.get("LLM_RESTART_WAIT", 300))  # local server restarts take ~2 min
    waited = 0.0
    attempt = 0
    while attempt <= retries:
        attempt += 1
        if backend in ("nvidia", "gemini"):
            if backend == "gemini":
                _gemini_guard()
            _nvidia_throttle(backend)
        t0 = time.time()
        try:
            resp = client.chat.completions.create(**kwargs)
            if backend == "gemini":
                _gemini_log(model, purpose, True, "200", t0, resp)
            ch = resp.choices[0]
            msg = ch.message
            reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None)
            text = msg.content or ""
            if not text and reasoning and thinking is False:
                text = reasoning  # some servers put everything into reasoning when thinking is off
            res = ChatResult(
                text=text, images=infos, model=resp.model or model, backend=backend,
                latency_s=time.time() - t0,
                prompt_tokens=getattr(resp.usage, "prompt_tokens", None) if resp.usage else None,
                completion_tokens=getattr(resp.usage, "completion_tokens", None) if resp.usage else None,
                reasoning=reasoning, finish_reason=ch.finish_reason,
                texts=[c.message.content or "" for c in resp.choices],
                logprobs=_logprobs_of(ch) if logprobs else None,
            )
            if cpath is not None:
                cpath.parent.mkdir(parents=True, exist_ok=True)
                d = {k: v for k, v in res.__dict__.items() if k not in ("images", "cached")}
                cpath.write_text(json.dumps(d))
            return _charge(res)
        except RateLimitError as e:  # 429: back off, honour Retry-After when given
            last_err = e
            if backend == "gemini":
                _gemini_log(model, purpose, False, "429", t0)
            ra = None
            try:
                ra = float(e.response.headers.get("retry-after"))  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001
                pass
            time.sleep(ra if ra else delay)
            delay = min(delay * 2, 60)
        except (APIConnectionError, APITimeoutError) as e:  # server restarting / overloaded
            last_err = e
            if backend == "local2" and os.environ.get("STOA_LOCAL2_FALLBACK", "1") != "0":
                # the optional second server (D21: 35B for free text) is gone: answer on :8001 NOW instead of waiting
                # up to LLM_RESTART_WAIT for it (a demo must not hang), and tell text_backend() for the next 60 s
                _TB_SEEN["local2"] = (False, time.time())
                backend, client, cpath = "local", _client("local"), None
                if kwargs.get("model") not in (None, "default"):
                    kwargs["model"] = "default"
                continue
            if is_local(backend) and isinstance(e, APIConnectionError) and waited < restart_budget:
                attempt -= 1  # a restarting local server doesn't use up retries, only the time budget
            time.sleep(delay)
            waited += delay
            delay = min(delay * 2, 30)
        except APIStatusError as e:
            last_err = e
            if backend == "gemini":
                _gemini_log(model, purpose, False, str(e.status_code), t0)
            if e.status_code in (500, 502, 503, 504):
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            raise  # 400 etc.: the request itself is wrong (e.g. prompt too long) — don't retry
    raise RuntimeError(f"chat failed after {attempt} attempts ({waited:.0f}s waiting) on {backend}: {last_err!r}")


def _logprobs_of(choice: Any) -> list[dict] | None:
    lp = getattr(choice, "logprobs", None)
    content = getattr(lp, "content", None) if lp is not None else None
    if not content:
        return None
    return [{"t": c.token, "lp": round(float(c.logprob), 6),
             "top": [[a.token, round(float(a.logprob), 4)] for a in (c.top_logprobs or [])]} for c in content]


def answer_prob(res: "ChatResult", value: str | None = None, max_digits: int = 0) -> float | None:
    """Probability the model gave to the number it answered: product over the tokens of the FIRST number in
    the reply (Qwen tokenises digits one by one) of p(token). With `value`, the first occurrence of that
    string is used instead. max_digits > 0 -> only the first N digit tokens count (for areas/lengths scored
    within 2%, the 3rd+ significant digits don't matter). None when logprobs were not requested or no
    number was found.

    Interpretable as a confidence: p("7") = 0.93 means the model put 93% on the leading digit path. Raw
    token probabilities are over-confident; calibrate per question kind (e.g. isotonic on TRAIN)."""
    toks = res.logprobs
    if not toks:
        return None
    text = "".join(t["t"] for t in toks)
    if value is not None:
        start = text.find(value)
        if start < 0:
            return None
        end = start + len(value)
    else:
        m = re.search(r"-?\d+(?:[.,]\d+)?", text)
        if not m:
            return None
        start, end = m.span()
    lp, pos, nd = 0.0, 0, 0
    for t in toks:  # tokens overlapping [start, end)
        a, b = pos, pos + len(t["t"])
        pos = b
        if b <= start or a >= end:
            continue
        if any(ch.isdigit() for ch in t["t"]):
            if max_digits and nd >= max_digits:
                break
            lp += t["lp"]
            nd += 1
    return round(math.exp(lp), 6)


def chat_many(requests: Iterable[dict], workers: int = 16) -> list[ChatResult | Exception]:
    """Run many `chat(**req)` calls concurrently (vLLM batches them). Errors are returned, not raised."""
    reqs = list(requests)

    def one(r: dict):
        try:
            return chat(**r)
        except Exception as e:  # noqa: BLE001
            return e

    ctx = contextvars.copy_context()  # so cost_meter() around chat_many still sees every call

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(lambda r: ctx.copy().run(one, r), reqs))


# --------------------------------------------------------------------------------------------- parsing
@dataclass
class Box:
    x0: float
    y0: float
    x1: float
    y1: float
    label: str = ""

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    def as_list(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]


@dataclass
class Point:
    x: float
    y: float
    label: str = ""


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> Any:
    """Best-effort JSON from model output: fenced block, else the first {...} or [...] that parses."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    cands = _FENCE.findall(text) + [text]
    for c in cands:
        c = c.strip()
        try:
            return json.loads(c)
        except Exception:  # noqa: BLE001
            pass
        for open_c, close_c in (("[", "]"), ("{", "}")):
            i = c.find(open_c)
            while i != -1:
                depth = 0
                for j in range(i, len(c)):
                    if c[j] == open_c:
                        depth += 1
                    elif c[j] == close_c:
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(c[i:j + 1])
                            except Exception:  # noqa: BLE001
                                break
                i = c.find(open_c, i + 1)
    return None


def _to_px(x: float, y: float, info: ImageInfo | tuple[int, int] | None, coords: str) -> tuple[float, float]:
    """Model coords -> original-image pixels. coords: rel1000 | yx1000 (Gemini: [y, x] order, 0..1000) | rel1 | pct |
    abs (abs = pixels of the sent image)."""
    if coords == "yx1000":
        x, y, coords = y, x, "rel1000"
    if info is None:
        return x, y
    if isinstance(info, tuple):
        info = ImageInfo(info[0], info[1], info[0], info[1])
    if coords == "rel1000":
        sx, sy = x / 1000.0 * info.sent_w, y / 1000.0 * info.sent_h
    elif coords == "rel1":
        sx, sy = x * info.sent_w, y * info.sent_h
    elif coords == "pct":
        sx, sy = x / 100.0 * info.sent_w, y / 100.0 * info.sent_h
    else:
        sx, sy = x, y
    return info.to_original(sx, sy)


_NUM = r"-?\d+(?:\.\d+)?"
_BOX_TAG = re.compile(rf"\(\s*({_NUM})\s*,\s*({_NUM})\s*\)\s*,\s*\(\s*({_NUM})\s*,\s*({_NUM})\s*\)")
_POINT_TAG = re.compile(r"<point\s+x=\"([\d.]+)\"\s+y=\"([\d.]+)\"[^>]*?(?:alt=\"([^\"]*)\")?[^>]*>", re.I)
_LIST4 = re.compile(rf"\[\s*({_NUM})\s*,\s*({_NUM})\s*,\s*({_NUM})\s*,\s*({_NUM})\s*\]")
_LIST2 = re.compile(rf"\[\s*({_NUM})\s*,\s*({_NUM})\s*\]")


def _walk(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def parse_boxes(text: str, info: ImageInfo | tuple[int, int] | None = None, coords: str = "rel1000"
                ) -> list[Box]:
    """Boxes from model output, in original-image pixels.

    Understands Qwen JSON ({"bbox_2d":[x1,y1,x2,y2],"label":..}, also "bbox"/"box"), Qwen tags
    (<|box_start|>(x1,y1),(x2,y2)<|box_end|>), and bare [x1,y1,x2,y2] lists as a last resort.
    """
    out: list[Box] = []
    data = extract_json(text)
    if data is not None:
        for d in _walk(data):
            for k in ("bbox_2d", "bbox", "box", "box_2d"):
                b = d.get(k)
                if isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) for v in b):
                    x0, y0 = _to_px(b[0], b[1], info, coords)
                    x1, y1 = _to_px(b[2], b[3], info, coords)
                    out.append(Box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1),
                                   str(d.get("label", d.get("name", "")))))
                    break
        if out:
            return out
    for m in _BOX_TAG.finditer(text):
        a, b, c, d = (float(v) for v in m.groups())
        x0, y0 = _to_px(a, b, info, coords)
        x1, y1 = _to_px(c, d, info, coords)
        out.append(Box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
    if out:
        return out
    for m in _LIST4.finditer(text):
        a, b, c, d = (float(v) for v in m.groups())
        x0, y0 = _to_px(a, b, info, coords)
        x1, y1 = _to_px(c, d, info, coords)
        out.append(Box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
    return out


def parse_points(text: str, info: ImageInfo | tuple[int, int] | None = None, coords: str = "rel1000"
                 ) -> list[Point]:
    """Points from model output, in original-image pixels.

    Understands Qwen JSON ({"point_2d":[x,y],"label":..}, also "point"), Molmo tags
    (<point x="12.3" y="45.6" alt="door"> in percent -> pass coords="pct"), and box centres as fallback.
    """
    out: list[Point] = []
    data = extract_json(text)
    if data is not None:
        for d in _walk(data):
            for k in ("point_2d", "point", "pt"):
                p = d.get(k)
                if isinstance(p, list) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p):
                    x, y = _to_px(p[0], p[1], info, coords)
                    out.append(Point(x, y, str(d.get("label", ""))))
                    break
        if out:
            return out
    for m in _POINT_TAG.finditer(text):
        x, y = _to_px(float(m.group(1)), float(m.group(2)), info, "pct" if coords == "rel1000" else coords)
        out.append(Point(x, y, m.group(3) or ""))
    if out:
        return out
    boxes = parse_boxes(text, info, coords)
    if boxes:
        return [Point(*b.center, b.label) for b in boxes]
    for m in _LIST2.finditer(text):
        x, y = _to_px(float(m.group(1)), float(m.group(2)), info, coords)
        out.append(Point(x, y))
    return out


def nms_points(points: list[Point], min_dist: float) -> list[Point]:
    """Greedy de-duplication of points closer than `min_dist` px (e.g. after tiling)."""
    kept: list[Point] = []
    for p in points:
        if all((p.x - q.x) ** 2 + (p.y - q.y) ** 2 >= min_dist ** 2 for q in kept):
            kept.append(p)
    return kept


def nms_boxes(boxes: list[Box], iou_thr: float = 0.5) -> list[Box]:
    """Greedy de-duplication of boxes (larger boxes first)."""
    def area(b: Box) -> float:
        return max(0.0, b.x1 - b.x0) * max(0.0, b.y1 - b.y0)

    def iou(a: Box, b: Box) -> float:
        ix = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
        iy = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
        inter = ix * iy
        u = area(a) + area(b) - inter
        return inter / u if u > 0 else 0.0

    kept: list[Box] = []
    for b in sorted(boxes, key=area, reverse=True):
        if all(iou(b, k) < iou_thr for k in kept):
            kept.append(b)
    return kept


# ---------------------------------------------------------------------------------------------------------------
# Question translation: a language-agnostic front end (F 04:01: sealed hard2r collapses on languages no rule
# covers: Polish cubicasa 21%, Estonian ifc 20%). Rules and templates understand en/fi/de/fr/it; anything else is
# translated to English by the local model, with quoted names, IDs and numbers swapped for placeholders first so
# they come back byte-identical (a storey called '1.korrus' must not become '1st floor').
# ---------------------------------------------------------------------------------------------------------------

# function words / question words per language (lower case, accents kept); scored, not first-match
_LANG_WORDS: dict[str, set[str]] = {
    "en": set("how many what which is are the of in on this does do there total area floor plan room rooms "
              "and with by for than larger smaller".split()),
    "fi": set("kuinka monta montako mikä mitkä onko on ja kerroksessa pohjapiirustuksessa pohjapiirustukseen "
              "yhteensä paljonko pinta-ala huonetta tässä".split()),
    "de": set("wie viele welche welcher ist sind der die das im auf dem den gibt es und wohnung fläche geschoss "
              "grundriss gross groß als".split()),
    "fr": set("combien quelle quel quels est sont de la le les du des sur dans et une un ce cette plan surface "
              "pièces appartement étage".split()),
    "it": set("quanti quante quale qual è di il lo la del della nel sul questo questa e una superficie stanze "
              "appartamento piano pianta".split()),
    "es": set("cuántos cuántas cuál cuáles qué el los las es son del en y una superficie habitaciones planta "
              "piso hay".split()),
    "pt": set("quantos quantas qual quais o os as é são do da em e uma área quartos planta andar há".split()),
    "nl": set("hoeveel welke wat het van is zijn op en een oppervlakte verdieping kamers".split()),
    "sv": set("hur många vilka vilken är och på det den finns rum ytan våning".split()),
    "da": set("hvor mange hvilke hvad er og på det den findes rum etage".split()),
    "no": set("hvor mange hvilke hva er og på det den finnes rom etasje".split()),
    "pl": set("ile jaka jaki jakie który która jest są na w i czy pomieszczeń pokoi powierzchnia tym tego "
              "kondygnacji piętrze".split()),
    "cs": set("kolik kolika jaká jaký jaké který která je jsou na v a se místností plocha tomto podlaží patře více "
              "než má oken dveří stěn počet celková celkový celkem".split()),
    "sk": set("koľko aká aký ktorý je sú na v a miestností plocha tomto podlaží".split()),
    "hu": set("hány hány mennyi van vannak a az és milyen melyik alaprajzon terület szint szinten helyiség "
              "teljes".split()),
    "tr": set("kaç ne nedir bu ve bir mi mı alanı katta oda odası toplam kattaki planda".split()),
    "ro": set("câte câți cât care este sunt și pe în din suprafața camere etaj planul acest".split()),
    "et": set("mitu kui palju on ja kas korrusel ruumi pindala mis milline millised milliseid protsent protsenti "
              "protsentides korruse korrus ruum ruumid ruumide ruumil netopinnast pinnast kogupinnast osakaal kokku "
              "suure moodustab plaanil joonisel hoones mudelis aknaid uksi akende uste".split()),
    "lv": set("cik kāda ir un uz stāvā telpu platība".split()),
    "lt": set("kiek koks yra ir ant aukšte patalpų plotas".split()),
}
# R2 09:40 (experiments/r2/probes/lang_id.py): terse wordings without a question word were read as English on a tie
# ("Nettofläche Whg. B in m², ohne Balkon und Loggia?" en 'in' 1 vs de 'und' 1; "Quante porte ci sono in tutto
# l'edificio?"), so they never reached the translator; Dutch "Tel de ramen op deze plattegrond." was French. More
# general function/domain words per language, and every word now scores 1 / (number of languages that list it), so a
# shared word ('in', 'de', 'plan', 'area') can no longer outvote a word only one language uses. No vocabulary added
# for hr / nb / el / lt (F's held-out hardL languages). Not added: storey names that appear UNQUOTED in English
# questions ('00 Begane grond'), and 'all' (tied an English injection tail with the Finnish question before it).
_LANG_MORE: dict[str, str] = {
    "en": "count number net door doors window windows wall walls kitchen living bedroom bathroom apartment ground "
          "storey level vs per between from",
    "fi": "laske laskekaa kpl määrä lukumäärä ovien ikkunoiden ikkunat ikkunaa ovet ovea asunto asunnon asunnossa "
          "huoneisto huoneiston neliöinä neliömetriä pohjakuva pohjakuvassa pohjapiirros piirustus piirustuksessa "
          "makuuhuonetta makuuhuoneita keittiö olohuone kylpyhuone kerros kerroksen ilman tai mitä missä paljon",
    "de": "in mit ohne für von zu ein eine einer eines einem alle aller gesamt gesamte gesamten insgesamt zusammen "
          "hat haben nicht oder anzahl zahl zählen zähle wieviel wieviele wo was wohnfläche nettowohnfläche "
          "nettofläche flächen zimmer räume raum türen tür fenster wände wand erdgeschoss obergeschoss "
          "untergeschoss dachgeschoss stockwerk küche wohnzimmer schlafzimmer badezimmer diesem dieser diesen "
          "dieses plan",
    "fr": "en au aux avec sans pour par nombre compte compter surface nette logement porte portes fenêtre fenêtres "
          "mur murs pièce rez chaussée cuisine salon chambre chambres salle bain bâtiment totale plus moins que plan",
    "it": "in con senza per che ci sono tutto tutti tutte numero conta contare quanto quanta area netta netto lorda "
          "alloggio porte porta finestre finestra muri muro pareti edificio stanza locale locali cucina soggiorno "
          "camera camere bagno bagni dell nella nelle negli sulla al ai alla più meno terra",
    "es": "con sin para por de la número cuenta contar puertas puerta ventanas ventana paredes muros neta neto "
          "apartamento vivienda baja plano cocina salón dormitorio baño total",
    "pt": "no na nos nas com sem para por número conte contar portas porta janelas janela paredes apartamento desta "
          "deste cozinha sala quarto banho total rés chão",
    "nl": "de een in met zonder voor aantal tel telt tellen deze dit die er staan ramen raam deuren deur muren kamer "
          "keuken woonkamer slaapkamer badkamer plattegrond totaal netto appartement woning hoe groot",
    "sv": "i av med utan för antal räkna lägenhet lägenheten lägenheter dörrar dörr fönster fönstren väggar sovrum "
          "badrum kök vardagsrum bottenvåningen våningen ritningen planritningen totalt sammanlagt tillsammans "
          "nettoarea yta area",
    "da": "antal døre vinduer vægge stueetagen lejlighed køkken badeværelse soveværelse alt med uden i",
    "pl": "w z bez dla do od liczba policz drzwi okna okien ścian ściany mieszkania mieszkanie parterze rzucie rzut "
          "kuchnia łazienka sypialnia netto wszystkich razem łącznie",
    "cs": "v z bez pro do od spočítej spočítejte okna bytu byt přízemí výkresu půdorysu kuchyně koupelna ložnice",
    "ro": "la de cu fără pentru numărul număr numără uși ușă ferestre fereastră ferestrele pereți apartamentul "
          "parter plan bucătărie dormitor baie total",
    "hu": "meg számold száma darab ajtók ajtó ablak ablakok ablakokat falak földszint földszinten rajzon lakás "
          "konyha fürdőszoba hálószoba összesen nettó",
    "tr": "sayısı say sayın kapı kapılar pencere pencereleri pencereler duvar zemin kat plandaki daire mutfak banyo "
          "yatak net metrekare",
    "et": "arv loe loenda uksed akende seinte esimesel teisel korter korteri köök vannituba magamistuba netopind",
}
_LANG_WORDS2: dict[str, set[str]] = {c: v | set(_LANG_MORE.get(c, "").split()) for c, v in _LANG_WORDS.items()}
_LANG_DF: dict[str, int] = {}
for _vocab in _LANG_WORDS2.values():
    for _w in _vocab:
        _LANG_DF[_w] = _LANG_DF.get(_w, 0) + 1
_LANG_CHARS: dict[str, str] = {  # letters that (almost) only one language family uses
    "pl": "ąęłńśźż", "cs": "ěřůť", "sk": "ľĺŕô", "hu": "őű", "tr": "ğşı", "ro": "ășțâî", "et": "õ",
    "es": "ñ¿¡", "pt": "ãõ", "fi": "", "lv": "āēīķļņģ", "lt": "ėįų", "da": "æø", "no": "æø", "sv": "å",
}
_LANG_CHARS2 = {**_LANG_CHARS, "da": "æøå", "no": "æøå"}  # v2: å is Danish/Norwegian too (Danish read as Swedish)
COVERED_LANGS = ("en", "fi", "de", "fr", "it")  # languages the dataset (and therefore our rules) use
_QUOTED = re.compile(r"(?<![^\W\d_])'[^']{1,80}'(?![^\W\d_])|\"[^\"]{1,80}\"|‘[^’]{1,80}’|“[^”]{1,80}”|„[^“”]{1,80}[“”]|«[^»]{1,80}»")
# IDs and numbers: anything with a digit (1.korrus, A-101, 2,40, 1 200, 25 CHF stays: only the number part)
_IDNUM = re.compile(r"(?<![\w])(?:\w*\d[\w.,/\-]*\w|\d)(?![\w])")


def _strip_quoted(q: str) -> str:
    return _QUOTED.sub(" ", q)


def _lang_score(question: str, vocab_by_lang: dict[str, set[str]], df: dict[str, int] | None) -> str:
    t = _strip_quoted(question).lower()
    words = re.findall(r"[^\W\d_]+(?:-[^\W\d_]+)?", t)
    if not words:
        return "?"
    if df is not None:
        letters = [ch for w in words for ch in w]
        if sum(1 for ch in letters if ch > "\u024f") * 2 > len(letters):
            return "?"  # mostly non-Latin script (Greek, Cyrillic, ...): no vocabulary here, never a rule language
    best, best_s = "?", 0.0
    for code, vocab in vocab_by_lang.items():
        s = sum((1.0 / df[w] if df else 1.0) for w in words if w in vocab)
        chars = (_LANG_CHARS2 if df else _LANG_CHARS).get(code, "")
        if chars:
            s += 1.5 * sum(1 for ch in t if ch in chars)
        if s > best_s:
            best, best_s = code, s
    return best if best_s >= (1e-9 if df else 1.0) else "?"


def lang_guess(question: str) -> str:
    """Best-guess ISO 639-1 code of a question (no model call; quoted names ignored). '?' when nothing matches.
    Meant for routing ("is this a language our rules cover?"), not for linguistics: close pairs (da/no, cs/sk)
    can be confused, which does not matter because both get translated.

    Two scorers: v1 (original vocabulary, 1 point per word) and v2 (_LANG_MORE + 1/df weights + non-Latin -> '?').
    v2 is right more often (open labelled probes 892 -> 928/946; 0 changes on the 6,671 open dataset questions), but
    the pipeline reads a COVERED language (en/fi/de/fr/it) as "the rules read it" and then skips translation, so
    v2's corrections TOWARD covered languages measured 0 wins / 1 loss (terse Finnish 'Laske ikkunat.' lost its
    translation fallback) and +46% LLM calls on the 63 affected open-probe rows (R2 09:30, artifacts/R2/
    lang_changed.jsonl). So v2 is used only when it moves a question to an UNCOVERED language (Dutch read as
    French, terse Dutch/Swedish/Spanish read as English): those are exactly the questions the front end should
    translate (held-out hardL: +30 points from translating uncovered languages)."""
    v1 = _lang_score(question, _LANG_WORDS, None)
    v2 = _lang_score(question, _LANG_WORDS2, _LANG_DF)
    # only a covered -> uncovered correction changes routing; uncovered -> other uncovered drift is left alone so
    # questions the front end already translates (incl. F's held-out hardL languages) keep their exact old path
    return v2 if v1 in COVERED_LANGS and v2 not in COVERED_LANGS and v2 != "?" else v1


@dataclass
class Translation:
    text: str                 # the English question (== the original when nothing was translated)
    lang: str                 # source language (model's answer when it translated, else lang_guess)
    translated: bool          # a model call rewrote the question
    ok: bool = True           # every protected span came back verbatim (False -> text is the original)
    original: str = ""
    note: str = ""            # for Answer.assumptions: "translated from Polish: '...'"


_TR_SYSTEM_BASE = (
    "You translate questions about construction drawings and building models into English. Rules: keep every "
    "placeholder such as [[1]] exactly as written, once each (a placeholder in quotes is a name or label: keep it "
    "in quotes); keep apartment, room and grid letters or codes; do not answer the question; do not add, drop or "
    "change any condition, comparison, unit or name; use standard English building terms (storey/floor, apartment, room, "
    "toilet, sink, door, window, net floor area, wall, slab). Reply as JSON {\"lang\": \"<ISO 639-1 code of the "
    "source>\", \"english\": \"<the English question>\"}."
)
# + a fixed domain glossary and "never add / drop qualifiers" (F 04:36/04:38: the remaining losses were concept-noun
# slips, e.g. Polish 'belek' (beams) -> balconies, and one ADDED 'external'). experiments/r2/probes/concept_match.py:
# translation parses to the same (task, target) as its English base on hardL_open 139/158 vs 129/158 without it,
# lang4 47 vs 46/48, 'belek' fixed, 0 vs 2 lost placeholders. (Two noun hints, washbasin vs kitchen sink and bathtub
# vs bathroom, were added after seeing hardL_open misses: F's held-out hardL is the honest check.)
_TR_SYSTEM = _TR_SYSTEM_BASE + (
    " Never add a qualifier or condition the source does not state (e.g. external, internal, load-bearing, net, "
    "gross) and never drop one it states; translate every noun. Translate building nouns with these English terms: "
    "toilet bowl / WC seat (a fixture), separate WC room (a room), washbasin (a bathroom wash basin, lavabo), kitchen "
    "sink, shower, bathtub (the tub itself, not the room), sauna, bedroom, bathroom / washroom (a room), kitchen, "
    "living room, balcony, terrace, storey / floor (a level of the building), apartment, room / space, door, window, "
    "wall, slab, beam, column, stair, roof, railing.")
# Source-language hints for building nouns the 8B does not know (S0 04:51: pl 'belek' -> balconies). General domain
# vocabulary (pl, et, cs, hu, ro, es, sv, fi, de, nl, da/no), not taken from any probe or sealed split. Used by
# to_english since 05:00: concept match hardL_open 141/158 (v2 without it 139, none 129), lang4 47/48, F's 11
# pl/ro ifc trigger questions 11/11 in the pipeline (v2: 10/11, 'belek' -> balconies).
_TR_GLOSSARY = (
    " Source-language hints: beam = belka/belki/belek (pl), tala (et), trám (cs), gerenda (hu), grindă/grinzi (ro), "
    "viga (es), balk/balkar (sv), palkki (fi), Balken (de), balk (nl), bjælke/bjelke (da/no); column = słup (pl), "
    "post/sammas (et), sloup (cs), oszlop (hu), stâlp/stâlpi (ro), columna/pilar (es), pelare (sv), pilari (fi), "
    "Stütze/Säule (de), kolom (nl), søjle/søyle (da/no); slab = płyta/strop (pl), plaat/vahelagi (et), deska/strop "
    "(cs), födém/lemez (hu), placă/plăci/planșeu (ro), losa/forjado (es), bjälklag/platta (sv), laatta (fi), "
    "Decke/Platte (de), vloerplaat (nl), dæk (da); stair = schody (pl), trepp (et), schodiště (cs), lépcső (hu), "
    "scară/scări (ro), escalera (es), trappa (sv), porras (fi); wall = ściana (pl), sein (et), stěna (cs), fal (hu), "
    "perete (ro), muro/pared (es), vägg (sv), seinä (fi); balcony = balkon (pl, cs), rõdu (et), erkély (hu), balcon "
    "(ro), balcón (es), balkong (sv), parveke (fi); washbasin = umywalka (pl), kraanikauss (et), umyvadlo (cs), mosdó "
    "(hu), lavoar (ro), lavabo (es), handfat (sv); kitchen sink = zlew (pl), valamu (et), dřez (cs), mosogató (hu), "
    "chiuvetă (ro), fregadero (es), diskbänk (sv); toilet bowl = sedes/miska WC (pl), WC-pott (et), mísa (cs), "
    "WC-csésze (hu), vas WC (ro), inodoro (es), toalettstol (sv); bathtub = wanna (pl), vann (et), vana (cs), kád "
    "(hu), cadă/căzi (ro), bañera (es), badkar (sv), kylpyamme (fi); shower = prysznic (pl), dušš (et), sprcha (cs), "
    "zuhany (hu), duș (ro), ducha (es), dusch (sv); sauna = bastu (sv), szauna (hu); bathroom = łazienka (pl), "
    "vannituba (et), koupelna (cs), fürdőszoba (hu), baie (ro), baño (es), badrum (sv); bedroom = sypialnia (pl), "
    "magamistuba (et), ložnice (cs), hálószoba (hu), dormitor (ro), dormitorio (es), sovrum (sv); storey = kondygnacja/"
    "piętro (pl), korrus (et), podlaží/patro (cs), szint/emelet (hu), nivel/etaj (ro), planta (es), våning (sv).")
# F 08:20 (open hardL cs/hu/tr/ro slips): room codes read as fixtures ('washrooms (KH, KPH, PH)' -> 'toilets'),
# hu 'Hány … közül' -> 'Which of', ro 'băi' / tr 'banyo' next to showers -> 'bathrooms', cs 'Kolik van' noun dropped.
# NOT used (08:50, experiments/r2/probes/hints2_ab.py): appended to v3 it was WORSE, hardL_open concept match 206 vs
# 212/232 (hu 45 vs 54: 'A lakás' read as 'A apartment' -> room area), lang4 47 vs 48/48, and the targeted slips stayed.
_TR_HINTS2 = (
    " Room codes in parentheses (KH, KPH, PH, PESUH, SH, WC, MH, S) mark ROOMS: name them as rooms (bathroom, "
    "washroom, WC room), never as fixtures (toilet, toilet bowl). 'How many of …' = 'Hány … közül' (hu), 'kaç "
    "tanesi' (tr), 'câte dintre' (ro), 'kolik z' (cs): keep it a count, never 'which'. bathtub = küvet (tr); "
    "'van' in 'kolik van' (cs) is bathtubs; next to showers, 'băi' (ro) and 'banyo' (tr) are bathtubs.")
# Quantity and unit words (W1 04:56: et 'kogumaht' total volume -> 'total area', hu 'lábban' in feet -> 'at ground
# level'). NOT used (05:10): with the one-letter fix v3 already matches W1's c5 cs/hu/sv rows 54/54, and adding these
# was slightly worse elsewhere (hardL_open concept match 208 vs 210/232, lang4 46 vs 47/48; noise-level).
_TR_GLOSSARY_Q = (
    " Quantity and unit hints: volume = objętość (pl), maht/ruumala (et), objem (cs), térfogat (hu), volum (ro), "
    "volumen (es), volym (sv), tilavuus (fi); area = powierzchnia (pl), pindala (et), plocha (cs), terület/alapterület "
    "(hu), suprafață/arie (ro), superficie/área (es), yta/area (sv), pinta-ala (fi); length = długość (pl), pikkus (et), "
    "délka (cs), hossz (hu), lungime (ro), longitud (es), längd (sv), pituus (fi); feet = stopa/stopy/stóp/stopach (pl), "
    "jalg/jalgades (et), stopa/stopách (cs), láb/lábban (hu), picior/picioare (ro), pie/pies (es), fot/fötter (sv), "
    "jalka/jalkaa (fi); metres = metr/metrach (pl), meeter/meetrites (et), metr/metrech (cs), méter/méterben (hu), "
    "metru/metri (ro), metro/metros (es), meter (sv); total = łączny/całkowity (pl), kogu-/kokku (et), celkový (cs), "
    "teljes/összes (hu), total (ro, es), total/sammanlagd (sv).")
_TR_SCHEMA = {"type": "object", "properties": {"lang": {"type": "string"}, "english": {"type": "string"}},
              "required": ["lang", "english"]}
_LANG_NAMES = {"pl": "Polish", "et": "Estonian", "es": "Spanish", "cs": "Czech", "hu": "Hungarian", "tr": "Turkish",
               "ro": "Romanian", "pt": "Portuguese", "nl": "Dutch", "sv": "Swedish", "da": "Danish", "no": "Norwegian",
               "sk": "Slovak", "lv": "Latvian", "lt": "Lithuanian", "fi": "Finnish", "de": "German", "fr": "French",
               "it": "Italian", "en": "English"}
_tr_memo: dict[tuple, Translation] = {}
_tr_lock = threading.Lock()


_NUM_SUFFIX = re.compile(r"(\d+(?:[.,]\d+)*)(-[^\W\d_]+)")  # Hungarian/Turkish case endings: 1.11-es, 12-ben
_LETTER = re.compile(r"(?:(?<=\s)|^)[A-Z](?=[\s,.;:?!)]|$)")  # apartment/unit letters (A, B)
_ONE_LETTER_WORDS = {"cs": "ovszkuai", "sk": "ovszkuai", "pl": "wzioau", "hu": "a", "sv": "i", "es": "yao",
                     "it": "eaio", "ro": "a", "pt": "aoe", "fr": "a", "lt": "ir", "lv": "ar"}
_QCHARS = "'\"‘’“”„«»"
# grouped thousands (Swiss 1'200 / 1’200, 1 200 with a (thin/no-break) space): ONE number, masked before quotes so
# the apostrophe can never pair with a quote mark (Q 05:08: "1'200 CHF" came out as 1 and 200)
_THOUSANDS = re.compile(r"(?<![\w'’.,])\d{1,3}(?:['’\u00a0\u202f ]\d{3})+(?:[.,]\d+)?(?![\w'’])")


def _protect(q: str) -> tuple[str, list[str]]:
    """Mask quoted names (quote marks stay visible, so the model knows a label is there), numbers/IDs and
    unit letters as [[n]]; return the masked text and the spans (quoted ones WITH their quote marks)."""
    spans: list[str] = []
    # a sentence-initial one-letter WORD of the language (cs 'O kolik', pl 'W modelu', hu article 'A') is not a unit
    # letter; Turkish 'A dairesinin' (apartment A) has no such word, so it stays protected
    one_letter = _ONE_LETTER_WORDS.get(lang_guess(q), "")

    def keep(text: str) -> str:
        spans.append(text)
        return f"[[{len(spans)}]]"

    def quoted(m: re.Match) -> str:
        t = m.group(0)
        return t[0] + keep(t) + t[-1]

    def idnum(m: re.Match) -> str:
        t = m.group(0)
        ns = _NUM_SUFFIX.fullmatch(t)
        return keep(ns.group(1)) + ns.group(2) if ns else keep(t)

    def letter(m: re.Match) -> str:
        return m.group(0) if (m.start() == 0 and m.group(0).lower() in one_letter) else keep(m.group(0))

    masked = _THOUSANDS.sub(lambda m: keep(m.group(0)), q)
    masked = _QUOTED.sub(quoted, masked)
    parts = re.split(r"(\[\[\d+\]\])", masked)  # outside the masked names only
    masked = "".join(p if re.fullmatch(r"\[\[\d+\]\]", p) else _LETTER.sub(letter, _IDNUM.sub(idnum, p))
                     for p in parts)
    return masked, spans


def _restore(text: str, spans: list[str]) -> tuple[str, bool]:
    """Put the spans back; a quoted name always comes back with its own quote marks, whether or not the model
    kept the quotes around the placeholder. ok = every placeholder appeared exactly once."""
    # the model sometimes writes [1] / [[1] for [[1]] (F 08:30: Estonian hard2r rows fell back to the original)
    text = re.sub(r"\[{1,2}\s*(\d{1,2})\s*\]{1,2}",
                  lambda m: f"[[{m.group(1)}]]" if 1 <= int(m.group(1)) <= len(spans) else m.group(0), text)
    ok = all(len(re.findall(rf"\[\[{i}\]\]", text)) == 1 for i in range(1, len(spans) + 1))
    for i in range(len(spans), 0, -1):  # [[12]] before [[1]]
        sp = spans[i - 1]
        ph = f"[[{i}]]"
        if len(sp) >= 2 and sp[0] in _QCHARS and sp[-1] in _QCHARS:
            text = re.sub(rf"[{_QCHARS}]?{re.escape(ph)}[{_QCHARS}]?", lambda _m: sp, text)
        else:
            text = text.replace(ph, sp)
    return text, ok and not re.search(r"\[\[\d+\]\]", text)


def should_translate(question: str, intent: Any = None) -> bool:
    """The measured trigger for to_english(question, force=True): a non-English question the rule-based intent
    parser could not read (unknown language, no target, or fell back to a free-text task). R2 04:20: on the CS/HU/TR/RO
    probe this fires on 46/48 and lifts the pipeline 38 -> 48/48; on hard's 175 non-English questions (fi/de/fr/it
    templates + new sv/nl/pl/de wordings the rules already read) it fires on 0 and changes nothing, whereas
    translating every non-English question there LOSES 7 answers to translation slips ("vasche da bagno" -> bathrooms,
    "bastur" -> bathrooms, "vloeren" -> floors). After translating, re-parse; keep the translation only if the
    re-parse finds a target. `intent` = stoa.router.intent.parse(question) (parsed here when None)."""
    if lang_guess(question) == "en":
        return False
    if intent is None:
        from stoa.router.intent import parse

        intent = parse(question)
    return (getattr(intent, "lang", "?") == "?" or getattr(intent, "target", None) in (None, "unknown")
            or getattr(intent, "task", None) == "text" or (TRANSLATE_CONJ and _joins_nouns(question, intent)))


# 'and' per language OUTSIDE the rule languages (en/fi/de/fr/it, whose 'und/et/e/ja' the composer reads itself)
_CONJ = {"sv": "och|samt", "nb": "og", "no": "og", "da": "og", "nl": "en", "pl": "i|oraz", "cs": "a|i", "sk": "a|i",
         "et": "ja", "lt": "ir", "lv": "un", "hu": "és", "tr": "ve", "ro": "și|și|si", "es": "y|e", "pt": "e",
         "hr": "i", "sl": "in", "el": "και"}
# R2 08:40 (Q's compose-cc:sv 3/6): "Hur många toalettstolar och balkonger finns det totalt?" parses as balconies only,
# and "sovrum och bastur … totalt" names two classes but the composer reads only English 'and' / 'in total', so a
# Swedish/Dutch/Polish/... composition reaches the LoRA or the agent as ONE question. Translating it lets the composer
# split it. Kill switch: STOA_TR_CONJ=0.
TRANSLATE_CONJ = os.environ.get("STOA_TR_CONJ", "1") != "0"


def _joins_nouns(question: str, intent: Any) -> bool:
    """A count/area question in a language the rules do not cover that joins words with its 'and'."""
    if getattr(intent, "task", None) not in ("count", "area"):
        return False
    rx = _CONJ.get(lang_guess(question))
    if not (rx and re.search(rf"(?<![^\W\d_])(?:{rx})(?![^\W\d_])", _strip_quoted(question), re.I)):
        return False
    from stoa.router.compose import _TOGETHER
    from stoa.router.intent import targets_mentioned

    # the composer already reads it (two classes + its 'in total' word, e.g. NL 'deuren en ramen … in totaal' 0.98
    # as is): translating would only cap a right answer at the translated-reading confidence
    return not (len(set(targets_mentioned(question)) - {"apartment", "room"}) >= 2 and _TOGETHER.search(question))


def to_english(question: str, *, keep: Sequence[str] = COVERED_LANGS, force: bool = False,
               backend: str = "local", model: str | None = None) -> Translation:
    """Translate a question into English unless its language is in `keep` (default: the languages our rules cover).

    One local-LLM call (~150 tokens in / ~40 out, cost recorded like any chat) for an uncovered language; none
    otherwise. Quoted names, IDs and numbers are masked as [[n]] before the call and restored after, so they are
    byte-identical; if the model loses one, the original question is returned with ok=False (caller: keep the
    original route and lower the confidence). Memoised in-process; disk-cached with STOA_LLM_CACHE=1.
    `force=True` translates any non-English question. Recommended use (measured, see should_translate):
        if should_translate(q, intent): tr = to_english(q, force=True); re-parse tr.text; use it if that finds a target
    Translating questions the rules already read loses answers (hard: 7 losses / 1 win on 175)."""
    guess = lang_guess(question)
    if guess == "en" or (not force and guess in keep):
        return Translation(question, guess, False, True, question)
    key = (question, backend, model)
    with _tr_lock:
        if key in _tr_memo:
            return _tr_memo[key]
    masked, spans = _protect(question)
    try:
        r = chat(masked, system=_TR_SYSTEM + _TR_GLOSSARY, backend=backend, model=model, max_tokens=300, temperature=0.0,
                 json_schema=_TR_SCHEMA)
        d = extract_json(r.text) or {}
        eng = str(d.get("english", "")).strip()
        lang = str(d.get("lang", guess) or guess).strip().lower()[:5] or guess
    except Exception as e:  # noqa: BLE001  (server down: answer on the original rather than fail)
        return Translation(question, guess, False, False, question, f"translation failed ({type(e).__name__})")
    text, ok = _restore(eng, spans) if eng else (question, False)
    if not ok and spans and lang != "en":
        # one corrective turn, only on a lost placeholder (R2 08:45: Estonian '... korruse [[1]] netopinnast' came back
        # as "the floor's net area" without [[1]]); the retry costs a call only on these failures
        try:
            need = ", ".join(f"[[{i}]]" for i in range(1, len(spans) + 1))
            msgs = [{"role": "user", "content": masked}, {"role": "assistant", "content": r.text},
                    {"role": "user", "content": f"Your translation lost or changed a placeholder. Each of {need} must "
                                                "appear exactly once, in the role it has in the source. Reply with the "
                                                "corrected JSON only."}]
            r2 = chat(msgs, system=_TR_SYSTEM + _TR_GLOSSARY, backend=backend, model=model, max_tokens=300,
                      temperature=0.0, json_schema=_TR_SCHEMA)
            eng2 = str((extract_json(r2.text) or {}).get("english", "")).strip()
            if eng2:
                t2, ok2 = _restore(eng2, spans)
                if ok2:
                    text, ok = t2, True
        except Exception:  # noqa: BLE001
            pass
    if lang == "en":
        res = Translation(question, "en", False, True, question)
    elif not ok:
        res = Translation(question, lang, False, False, question,
                          f"translation from {_LANG_NAMES.get(lang, lang)} lost a name or number; used the original")
    else:
        res = Translation(text, lang, True, True, question,
                          f"question translated from {_LANG_NAMES.get(lang, lang)} by the local model: \"{text}\"")
    with _tr_lock:
        _tr_memo[key] = res
    return res


if __name__ == "__main__":  # smoke test: python -m stoa.llm [backend]
    import sys

    be = sys.argv[1] if len(sys.argv) > 1 else "local"
    print("model:", served_model(be) if is_local(be) else BACKENDS[be]["model"])
    img = Image.new("RGB", (800, 400), "white")
    from PIL import ImageDraw

    dr = ImageDraw.Draw(img)
    dr.rectangle((100, 100, 300, 300), outline="black", width=6)
    dr.ellipse((500, 150, 600, 250), outline="red", width=6)
    r = chat('Locate the red circle. Output JSON [{"bbox_2d":[x1,y1,x2,y2],"label":"circle"}].',
             images=[img], backend=be, max_tokens=200)
    print(r.text.strip()[:300])
    print("boxes (px, expect ~[500,150,600,250]):", [[round(v) for v in b.as_list()] for b in parse_boxes(r.text, r.images[0])])
    print(f"latency {r.latency_s:.1f}s, tokens {r.prompt_tokens}->{r.completion_tokens}")
