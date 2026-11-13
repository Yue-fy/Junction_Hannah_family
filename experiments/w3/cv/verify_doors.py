"""CV proposes door-swing candidates, the local VLM verifies each crop (yes/no). TRAIN only.

    PYTHONPATH=$PWD $JUNCTION_VENV/bin/python experiments/w3/cv/verify_doors.py <doors-raw.jsonl> [--n 120]
        [--score 1.0 --inner 0.35 --rfrac 0.022]

Reads the raw candidates written by doors.py eval (coordinates in the <=1000 px downscaled image), crops each
candidate's swing box (+60% margin) from the original image, asks Qwen3-VL "is this a door?", and reports exact
accuracy of (#yes after NMS) vs the prior. Writes artifacts/W3/cv/verify-<time>.jsonl.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import os
import statistics
import sys
import time
from pathlib import Path

import cv2
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from sweep_doors import box, nms  # noqa: E402

from stoa import llm  # noqa: E402
from stoa.data import abspath  # noqa: E402

SHARED = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
PROMPT = ("This is a small crop of an architectural floor plan. Is there a DOOR symbol in the middle of it: a "
          "straight door leaf line from a hinge point plus a quarter-circle swing arc? Chairs, beds, toilets, "
          "tables, stairs, text and dimension lines are not doors. Answer only yes or no.")


def crop(img: Image.Image, d, f: float, margin: float = 0.6, side: int = 320) -> Image.Image:
    x0, y0, x1, y1 = box(d)
    r = d[2]
    x0, y0, x1, y1 = [v / f for v in (x0 - margin * r, y0 - margin * r, x1 + margin * r, y1 + margin * r)]
    c = img.crop((int(max(0, x0)), int(max(0, y0)), int(min(img.width, x1)), int(min(img.height, y1))))
    s = side / max(c.size)
    return c.resize((max(1, int(c.width * s)), max(1, int(c.height * s))), Image.LANCZOS)


def ask(im: Image.Image) -> tuple[bool, int, int]:
    res = llm.chat(PROMPT, [im], max_tokens=3, cache=True)
    return res.text.strip().lower().startswith("y"), res.prompt_tokens or 0, res.completion_tokens or 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--score", type=float, default=1.0)
    ap.add_argument("--inner", type=float, default=0.35)
    ap.add_argument("--rfrac", type=float, default=0.022)
    ap.add_argument("--workers", type=int, default=24)
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.raw)][: a.n]
    jobs = []
    for i, r in enumerate(rows):
        m = max(r["shape"])
        r["cands"] = nms([d for d in r["raw"] if d[4] <= a.score and d[5] <= a.inner and d[2] >= a.rfrac * m])
        img = Image.open(abspath(r["path"])).convert("RGB")
        f = r["shape"][0] / img.height  # downscale factor used by doors.py
        for j, d in enumerate(r["cands"]):
            jobs.append((i, j, crop(img, d, f)))
    print(f"{len(rows)} drawings, {len(jobs)} candidate crops")
    t0 = time.time()
    with cf.ThreadPoolExecutor(a.workers) as ex:
        out = list(ex.map(lambda j: ask(j[2]), jobs))
    tok_in = sum(o[1] for o in out)
    yes = collections.defaultdict(list)
    for (i, j, _), (y, *_t) in zip(jobs, out):
        if y:
            yes[i].append(j)
    prior = collections.Counter(r["gold"] for r in rows).most_common(1)[0][0]
    res = []
    for i, r in enumerate(rows):
        res.append(dict(path=r["path"], gold=r["gold"], n_cand=len(r["cands"]), n_yes=len(yes[i]),
                        yes=[r["cands"][j][:4] for j in yes[i]]))
    outp = SHARED / f"artifacts/W3/cv/verify-{time.strftime('%H%M%S')}.jsonl"
    with open(outp, "w") as fh:
        for x in res:
            fh.write(json.dumps(x) + "\n")
    n = len(res)
    for k in ("n_cand", "n_yes"):
        ex_ = sum(x[k] == x["gold"] for x in res) / n
        w1 = sum(abs(x[k] - x["gold"]) <= 1 for x in res) / n
        ratio = statistics.median(x[k] / max(1, x["gold"]) for x in res)
        print(f"{k}: exact {ex_:.1%} within1 {w1:.1%} median ratio {ratio:.2f}")
    print(f"prior ({prior}): {sum(prior == x['gold'] for x in res) / n:.1%};  {time.time() - t0:.0f}s, "
          f"{tok_in / max(1, n):.0f} tokens in per drawing -> {outp}")


if __name__ == "__main__":
    main()
