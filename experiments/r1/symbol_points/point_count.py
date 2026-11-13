"""Cubicasa symbol counts by POINTING (one class per prompt, 2x upscaled image), vs the per-template prior.

F's error analysis: asking the VLM "how many" gives '2' for most fixture questions and undercounts
windows/doors. Hypothesis: asking for one point per object, one class at a time (showers and bathtubs
separately, then summed), fixes much of it; the points are the evidence.
Explore on TRAIN drawings; confirm on dev later with a frozen policy.
Run: $JUNCTION_VENV/bin/python -I point_count.py --split train --max-drawings 40 [--scale 2]
"""
import argparse
import collections
import concurrent.futures as cf
import hashlib
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "room_labels"))
from openai import OpenAI  # noqa: E402

import run as rl  # noqa: E402  (img_b64, DATA, SHARED)

CACHE = os.path.join(rl.SHARED, "artifacts", "R1", "symbol_points")
TEMPLATES = {
    "windows": r"How many windows are shown|Kuinka monta ikkunaa",
    "doors": r"How many doors are shown|Kuinka monta ovea",
    "wc_seats": r"How many toilet bowls|WC-istuinta",
    "sinks": r"How many sinks and wash basins|pesu- ja tiskiallasta",
    "shower_bath": r"How many showers and bathtubs|suihkua ja kylpyammetta",
}
CLASSES = {  # class -> description used in the pointing prompt
    "window": "window (a window symbol drawn in an exterior wall: thin parallel lines across the wall)",
    "door": "door (a door leaf with its swing arc; not open doorways without a door)",
    "toilet": "toilet bowl (WC seat)",
    "sink": "sink or wash basin (kitchen sink or bathroom basin; a double-bowl sink is one)",
    "shower": "shower (shower tray or shower area symbol)",
    "bathtub": "bathtub",
}
SHORT = {"window": "window", "door": "door", "toilet": "toilet", "sink": "sink", "shower": "shower", "bathtub": "bathtub"}
TPL_CLASSES = {"windows": ["window"], "doors": ["door"], "wc_seats": ["toilet"], "sinks": ["sink"],
               "shower_bath": ["shower", "bathtub"]}
PROMPT = ("This is an architectural floor plan. Point to every {desc} in the plan. "
          'Output a JSON list with one entry per object: [{{"point_2d": [x, y], "label": "{cls}"}}]. '
          "If there is none, output [].")


def points(text):
    pts = []
    for m in re.finditer(r'"point_2d"\s*:\s*\[\s*([\d.]+)\s*,\s*([\d.]+)\s*\]', text):
        p = (float(m.group(1)), float(m.group(2)))
        if all(math.dist(p, q) > 12 for q in pts):  # same object listed twice / repetition loops
            pts.append(p)
    return pts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    ap.add_argument("--max-drawings", type=int, default=40)
    ap.add_argument("--scale", type=float, default=2.0)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--prompt", default="long", choices=["long", "short"])
    ap.add_argument("--only", default="", help="comma list of templates")
    a = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)

    def tpl(q):
        for k, rx in TEMPLATES.items():
            if re.search(rx, q):
                return k
    Q = {}
    for line in open(os.path.join(rl.DATA, "questions.jsonl")):
        d = json.loads(line)
        if d["path"].startswith("data/cubicasa5k/") and tpl(d["question"]):
            Q[hashlib.sha1(f"{d['path']}\n{d['question']}".encode()).hexdigest()[:12]] = d
    srows = lambda s: [json.loads(l)["qid"] for l in open(os.path.join(rl.SHARED, "results", "splits", f"{s}.jsonl"))]
    prior_c = collections.defaultdict(collections.Counter)
    for qid in srows("train"):
        if qid in Q:
            prior_c[tpl(Q[qid]["question"])][Q[qid]["answer"]] += 1
    prior = {k: v.most_common(1)[0][0] for k, v in prior_c.items()}
    rows = [Q[q] for q in srows(a.split) if q in Q]
    # one gold per (drawing, template): EN and FI twins have the same answer
    gold = {}
    for d in rows:
        gold[(d["path"], tpl(d["question"]))] = d["answer"]
    paths = sorted({p for p, _ in gold})[: a.max_drawings]
    gold = {k: v for k, v in gold.items() if k[0] in set(paths) and (not a.only or k[1] in a.only.split(","))}
    print(f"{len(gold)} (drawing, template) pairs on {len(paths)} drawings ({a.split}); prior {prior}")

    client = OpenAI(base_url=rl.BASE, api_key="EMPTY")

    def call(job):
        path, cls = job
        tag = "" if a.prompt == "long" else ".short"
        f = os.path.join(CACHE, f"{os.path.basename(path)}.{cls}.s{a.scale:g}{tag}.json")
        if os.path.exists(f):
            return job, json.load(open(f))
        import time
        t0 = time.time()
        r = client.chat.completions.create(model="default", temperature=0, max_tokens=1200, messages=[{
            "role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + rl.img_b64(os.path.join(rl.DATA, path), a.scale)}},
                {"type": "text", "text": PROMPT.format(desc=(CLASSES if a.prompt == "long" else SHORT)[cls], cls=cls)}]}])
        out = {"text": r.choices[0].message.content, "in": r.usage.prompt_tokens, "out": r.usage.completion_tokens,
               "s": time.time() - t0}
        json.dump(out, open(f, "w"))
        return job, out

    need = sorted({(p, c) for (p, t) in gold for c in TPL_CLASSES[t]})
    with cf.ThreadPoolExecutor(a.workers) as ex:
        res = dict(ex.map(call, need))

    S = collections.defaultdict(collections.Counter)
    errs = collections.defaultdict(collections.Counter)
    for (p, t), g in gold.items():
        n = sum(len(points(res[(p, c)]["text"])) for c in TPL_CLASSES[t])
        S[t]["n"] += 1
        S[t]["points"] += n == g
        S[t]["prior"] += prior[t] == g
        S[t]["within1"] += abs(n - g) <= 1
        errs[t][max(-3, min(3, n - g))] += 1
    print(f"{'template':12s} {'n':>4s} {'points':>7s} {'±1':>6s} {'prior':>7s}  pred-gold histogram (clipped ±3)")
    for t in TEMPLATES:
        s = S[t]
        if s["n"]:
            print(f"{t:12s} {s['n']:4d} {s['points']/s['n']:7.1%} {s['within1']/s['n']:6.1%} {s['prior']/s['n']:7.1%}  {sorted(errs[t].items())}")
    print(f"calls {len(res)}, tokens in {sum(v['in'] for v in res.values())}, out {sum(v['out'] for v in res.values())}, "
          f"mean {sum(v['s'] for v in res.values())/len(res):.1f}s")


if __name__ == "__main__":
    main()
