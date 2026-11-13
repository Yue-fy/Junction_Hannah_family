"""Tiled pointing for windows/doors on TRAIN drawings: upscale, cut overlapping tiles, point per tile, merge by
distance, compare with the whole-image result from calibrate.py.

    PYTHONPATH=$PWD $JUNCTION_VENV/bin/python experiments/w3/tiles.py --n 30 --classes window,door
"""
import argparse, collections, concurrent.futures as cf, json, math, random, time
from pathlib import Path

from PIL import Image

from stoa import llm
from stoa.data import abspath
from stoa.eval.splits import load_split
from stoa.solvers.raster.classes import SYMBOL_DEF, question_class
from stoa.solvers.raster.vlm import POINT_PROMPT, upscaled

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=30)
ap.add_argument("--classes", default="window,door")
ap.add_argument("--target-px", type=int, default=4_000_000)
ap.add_argument("--tile", type=int, default=1024)
ap.add_argument("--overlap", type=int, default=192)
ap.add_argument("--seed", type=int, default=7)
a = ap.parse_args()

gold = collections.defaultdict(dict)
for q in load_split("train"):
    if q.source == "cubicasa5k" and q.question.lower().startswith("how"):
        c = question_class(q.question)
        if c:
            gold[q.path][c] = q.answer
paths = sorted(p for p, d in gold.items() if len(d) >= 8)
random.Random(a.seed).shuffle(paths)  # same order as calibrate.py -> same first drawings
paths = paths[: a.n]
classes = a.classes.split(",")


def run(p, c):
    img = llm.load_image(abspath(p))
    big, f = upscaled(img, a.target_px)
    tiles = llm.tile_image(big, a.tile, a.overlap)
    name, definition = SYMBOL_DEF[c]
    reqs = [dict(messages=POINT_PROMPT.format(name=name, definition=definition), images=[t], max_tokens=600,
                 max_pixels=a.tile * a.tile + 10, cache=True) for t in tiles]
    res = llm.chat_many(reqs, workers=8)
    pts, trunc, tok = [], 0, 0
    for t, r in zip(tiles, res):
        if isinstance(r, Exception):
            continue
        tok += r.completion_tokens or 0
        info = r.images[0]
        info.offset = (t.x0, t.y0)
        if r.finish_reason == "length":
            trunc += 1
            continue  # a looping tile is dropped
        # ignore points in the outer half-overlap band of a tile when a neighbour covers it (dedupe by NMS anyway)
        pts += llm.parse_points(r.text, info)
    merged = llm.nms_points(pts, 0.012 * math.hypot(*big.size))
    return dict(path=p, cls=c, value=len(merged), raw=len(pts), tiles=len(tiles), trunc=trunc, tok=tok,
                gold=gold[p][c])


t0 = time.time()
rows = []
with cf.ThreadPoolExecutor(6) as ex:
    futs = [ex.submit(run, p, c) for p in paths for c in classes if c in gold[p]]
    for f in cf.as_completed(futs):
        rows.append(f.result())
out = Path("/home/fangy4/work/projects/junction-shared/artifacts/W3/calib") / f"tiles-{time.strftime('%H%M%S')}.jsonl"
out.write_text("".join(json.dumps(r) + "\n" for r in rows))
print(f"{out} {time.time() - t0:.0f}s")
for c in classes:
    rs = [r for r in rows if r["cls"] == c]
    if rs:
        print(c, len(rs), "exact", sum(r["value"] == r["gold"] for r in rs), "within1",
              sum(abs(r["value"] - r["gold"]) <= 1 for r in rs), "under", sum(r["value"] < r["gold"] for r in rs),
              "over", sum(r["value"] > r["gold"] for r in rs), "trunc tiles", sum(r["trunc"] for r in rs),
              "tiles", sum(r["tiles"] for r in rs), "pairs", [(r["value"], r["gold"]) for r in rs][:15])
