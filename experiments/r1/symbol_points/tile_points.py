"""Tiled pointing for cubicasa windows/doors (F's hypothesis: windows are 1-2 px wide at the resolution we
send, so tile and upscale before pointing).

Each image is cut into a GxG grid with `overlap` (fraction of the tile), each tile is upscaled so its long
side is `tile_px`, the VLM points to every <class> per tile, points are mapped back to image pixels and
merged across tiles when closer than `merge_px` (in original pixels). Explore on train_gate, gate per class.
Run: $JUNCTION_VENV/bin/python -I tile_points.py --split train_gate --max-drawings 40 --classes window,door
"""
import argparse
import base64
import collections
import concurrent.futures as cf
import hashlib
import io
import json
import math
import os
import re
import sys
import time

from openai import OpenAI
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import point_count as pc  # noqa: E402

CACHE = os.path.join(pc.rl.SHARED, "artifacts", "R1", "tile_points")
CLS_TPL = {"window": "windows", "door": "doors", "toilet": "wc_seats", "sink": "sinks"}
PROMPT = ("This is a crop of an architectural floor plan. Point to every {cls} symbol in this crop. "
          'Output a JSON list: [{{"point_2d": [x, y], "label": "{cls}"}}]. If there is none, output [].')


def tiles(im, g, overlap):
    W, H = im.size
    tw, th = W / (g - (g - 1) * overlap), H / (g - (g - 1) * overlap)
    for i in range(g):
        for j in range(g):
            x0, y0 = i * tw * (1 - overlap), j * th * (1 - overlap)
            yield (int(x0), int(y0), int(min(W, x0 + tw)), int(min(H, y0 + th)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train_gate")
    ap.add_argument("--max-drawings", type=int, default=40)
    ap.add_argument("--classes", default="window,door")
    ap.add_argument("--grid", type=int, default=2)
    ap.add_argument("--overlap", type=float, default=0.15)
    ap.add_argument("--tile-px", type=int, default=1280)
    ap.add_argument("--merge-px", type=float, default=8)
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)
    classes = a.classes.split(",")

    Q = {}
    for line in open(os.path.join(pc.rl.DATA, "questions.jsonl")):
        d = json.loads(line)
        if d["path"].startswith("data/cubicasa5k/"):
            for c in classes:
                if re.search(pc.TEMPLATES[CLS_TPL[c]], d["question"]):
                    Q[hashlib.sha1(f"{d['path']}\n{d['question']}".encode()).hexdigest()[:12]] = (d, c)
    sp = lambda s: [json.loads(l)["qid"] for l in open(os.path.join(pc.rl.SHARED, "results", "splits", f"{s}.jsonl"))]
    prior_c = collections.defaultdict(collections.Counter)
    for q in sp("train"):
        if q in Q:
            prior_c[Q[q][1]][Q[q][0]["answer"]] += 1
    prior = {c: v.most_common(1)[0][0] for c, v in prior_c.items()}
    gold = {}
    for q in sp(a.split):
        if q in Q:
            d, c = Q[q]
            gold[(d["path"], c)] = d["answer"]
    paths = sorted({p for p, _ in gold})[: a.max_drawings]
    gold = {k: v for k, v in gold.items() if k[0] in set(paths)}
    print(f"{len(gold)} (drawing, class) pairs on {len(paths)} drawings ({a.split}); prior {prior}")
    client = OpenAI(base_url=pc.rl.BASE, api_key="EMPTY")
    tag = f"g{a.grid}o{a.overlap:g}t{a.tile_px}"

    def call(job):
        path, cls, k, box = job
        f = os.path.join(CACHE, f"{os.path.basename(path)}.{cls}.{tag}.{k}.json")
        if os.path.exists(f):
            return job, json.load(open(f))
        im = Image.open(os.path.join(pc.rl.DATA, path)).convert("RGB").crop(box)
        s = a.tile_px / max(im.size)
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        t0 = time.time()
        r = client.chat.completions.create(model="default", temperature=0, max_tokens=800,
                                           extra_body={"repetition_penalty": 1.05}, messages=[{
            "role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}},
                {"type": "text", "text": PROMPT.format(cls=cls)}]}])
        out = {"text": r.choices[0].message.content, "in": r.usage.prompt_tokens, "out": r.usage.completion_tokens,
               "s": time.time() - t0, "box": box}
        json.dump(out, open(f, "w"))
        return job, out

    jobs = []
    for (p, c) in gold:
        im = Image.open(os.path.join(pc.rl.DATA, p))
        for k, box in enumerate(tiles(im, a.grid, a.overlap)):
            jobs.append((p, c, k, box))
    with cf.ThreadPoolExecutor(a.workers) as ex:
        res = dict(ex.map(call, jobs))

    S = collections.defaultdict(collections.Counter)
    hist = collections.defaultdict(collections.Counter)
    for (p, c), g in gold.items():
        pts = []
        for (pp, cc, k, box), out in res.items():
            if pp != p or cc != c:
                continue
            x0, y0, x1, y1 = box
            for (u, v) in pc.points(out["text"]):
                x, y = x0 + u / 1000 * (x1 - x0), y0 + v / 1000 * (y1 - y0)
                if all(math.dist((x, y), q) > a.merge_px for q in pts):
                    pts.append((x, y))
        n = len(pts)
        S[c]["n"] += 1
        S[c]["tiles"] += n == g
        S[c]["prior"] += prior[c] == g
        S[c]["w1"] += abs(n - g) <= 1
        hist[c][max(-3, min(3, n - g))] += 1
        S[c]["ratio"] += n / g if g else 0
    print(f"{'class':8s} {'n':>4s} {'tiled':>7s} {'±1':>6s} {'prior':>7s} {'mean pred/gold':>15s}  pred-gold (clipped ±3)")
    for c in classes:
        s = S[c]
        print(f"{c:8s} {s['n']:4d} {s['tiles']/s['n']:7.1%} {s['w1']/s['n']:6.1%} {s['prior']/s['n']:7.1%} {s['ratio']/s['n']:15.2f}  {sorted(hist[c].items())}")
    print(f"calls {len(res)}, tokens in {sum(v['in'] for v in res.values())}, out {sum(v['out'] for v in res.values())}, "
          f"mean {sum(v['s'] for v in res.values())/len(res):.1f}s")


if __name__ == "__main__":
    main()
