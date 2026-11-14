"""Find room areas printed on cubicasa plans ("12,5 m²") with boxes, using the shared local VLM as the OCR engine.

These printed areas are the ground truth for the raster scale experiment (raster_scale.py): a printed area inside a
CC5K room region gives that drawing's true pixels-per-metre. Only drawing CONTENT is used (no dataset labels), and
only TRAIN-split drawings, so nothing here touches dev/test answers.

    python experiments/r1/raster_scale/find_areas.py --n-hqa 500 --n-colorful 150 --workers 4
Output: $JUNCTION_SHARED/artifacts/R1/raster_scale/areas.jsonl  (one line per drawing; resumable)
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from stoa import llm  # noqa: E402

SHARED = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
DATA = Path(os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset"))
OUT = SHARED / "artifacts" / "R1" / "raster_scale" / "areas.jsonl"

PROMPT = ("Find every floor AREA printed as text on this floor plan: numbers with a unit of m², m2 or sq m "
          "(for example '12,5 m²' or '8.0 m2'), usually written inside a room under its name. "
          "Output a JSON list with one entry per printed area: "
          '[{"bbox_2d": [x1, y1, x2, y2], "text": "<the area text exactly as printed>"}]. '
          "Coordinates are 0-1000 relative to this image. Output [] if no area is printed.")
ITEM = re.compile(r'\{[^{}]*?"bbox_2d"\s*:\s*\[([^\]]*)\][^{}]*?"text"\s*:\s*"((?:[^"\\]|\\.)*)"[^{}]*\}')
NUM = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:m²|m2|m\^2|sq\.? ?m|㎡)", re.I)


def upscale(img: Image.Image, scale: float = 2.0, max_side: int = 2400) -> Image.Image:
    s = min(scale, max_side / max(img.size))
    return img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS) if s != 1 else img


UNITLESS = re.compile(r"(?<![\d.,])(\d{1,3}[.,]\d)(?![\d.,])")


def parse(text: str, w: int, h: int, unitless: bool = False) -> list[dict]:
    """unitless=True also accepts a bare one-decimal number (Finnish plans often print 'MH 11.7' without m²),
    1-200 m², as a fallback the caller uses only when no item carried a unit."""
    out = []
    for m in ITEM.finditer(text):
        try:
            b = [float(v) for v in m.group(1).split(",")[:4]]
        except ValueError:
            continue
        if len(b) != 4:
            continue
        t = m.group(2)
        n = NUM.search(t)
        if not n and unitless:
            n = UNITLESS.search(t)
            if n and not 1.0 <= float(n.group(1).replace(",", ".")) <= 200:
                n = None
        if not n:
            continue
        box = [b[0] / 1000 * w, b[1] / 1000 * h, b[2] / 1000 * w, b[3] / 1000 * h]
        out.append({"text": t, "m2": float(n.group(1).replace(",", ".")), "box": [round(v, 1) for v in box]})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-hqa", type=int, default=500)
    ap.add_argument("--n-colorful", type=int, default=150)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(SHARED / "results" / "splits" / "train.jsonl")]
    paths = sorted({r["path"] for r in rows if r["path"].startswith("data/cubicasa5k/")})
    rng = random.Random(a.seed)
    hqa = [p for p in paths if "/high_quality_architectural-" in p]
    col = [p for p in paths if "/colorful-" in p]
    pick = rng.sample(hqa, min(a.n_hqa, len(hqa))) + rng.sample(col, min(a.n_colorful, len(col)))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if OUT.exists():
        done = {json.loads(l)["path"] for l in open(OUT)}
    todo = [p for p in pick if p not in done]
    print(f"{len(pick)} picked, {len(todo)} to do", flush=True)

    reqs, sizes = [], []
    for p in todo:
        img = Image.open(DATA / p).convert("RGB")
        sizes.append(img.size)
        reqs.append(dict(messages=PROMPT, images=[upscale(img)], max_tokens=600, max_pixels=6_000_000,
                         cache=True, extra_body={"repetition_penalty": 1.05}))
    # chunked so partial progress lands on disk
    with open(OUT, "a") as f:
        for i in range(0, len(reqs), 40):
            res = llm.chat_many(reqs[i:i + 40], workers=a.workers)
            for p, (w, h), r in zip(todo[i:i + 40], sizes[i:i + 40], res):
                if isinstance(r, Exception):
                    f.write(json.dumps({"path": p, "error": str(r)[:200]}) + "\n")
                    continue
                f.write(json.dumps({"path": p, "size": [w, h], "areas": parse(r.text, w, h),
                                    "raw": r.text[:2000]}) + "\n")
            f.flush()
            print(f"{min(i + 40, len(reqs))}/{len(reqs)}", flush=True)


if __name__ == "__main__":
    main()
