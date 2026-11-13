"""Build LoRA training data for raster counting from the TRAIN split only (never dev/test).

One sample per drawing: the image once, then several question/answer turns in random order (each object
kind once, random language / paraphrase). Encoding the image once per drawing makes training ~9x cheaper
than one sample per question. The first turn matches inference exactly (system + image + question).

Output JSONL: {"image": abs path, "turns": [{"q": ..., "a": "7"}, ...], "source", "path"}
Usage: $JUNCTION_VENV/bin/python experiments/r2/lora/build_data.py --out $JUNCTION_SHARED/artifacts/R2/lora/train.jsonl
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import re
from pathlib import Path

from stoa.data import abspath, template_of
from stoa.eval.splits import load_split

# Paraphrases per object kind (English). {} = nothing. Keeps the model from keying on exact template text.
PARA = {
    "window": ["How many windows are there in this plan?", "Count the windows in this floor plan.",
               "Number of windows shown on the drawing?"],
    "floor": ["How many storeys are shown in this drawing?", "How many separate floor levels does this plan show?"],
    "toilet": ["How many WC seats (toilet bowls) are drawn?", "Count the toilets drawn on this plan."],
    "sink": ["How many sinks and washbasins are drawn in total (kitchen and bathrooms)?"],
    "shower": ["How many showers and bathtubs are drawn in total?", "Count showers plus bathtubs on this plan."],
    "door": ["How many doors does this floor plan show? Only doorways with a door leaf count.",
             "Count the doors (door leaves) drawn on this plan."],
    "sauna": ["How many saunas does this plan have?"],
    "kitchen": ["How many kitchens or kitchenettes are on this plan?"],
    "bedroom": ["How many bedrooms (MH) are there?", "Count the bedrooms on this floor plan."],
    "bathroom": ["How many bathrooms or washrooms are there (not counting separate WCs)?"],
    "wc_room": ["How many separate WC rooms are on this plan?"],
    "balcony": ["How many balconies are on this plan (glazed balconies included)?"],
}
KIND_RE = [
    ("window", r"window|ikkun"), ("floor", r"floors \(storeys\)|kerrosta"), ("toilet", r"toilet bowl|wc-istuin"),
    ("sink", r"sinks|tiskiallas|pesu- ja tiski"), ("shower", r"shower|suihku"), ("door", r"\bdoors?\b|\bovea\b"),
    ("sauna", r"sauna"), ("kitchen", r"kitchen|keittiö"), ("bedroom", r"bedroom|makuuhuone"),
    ("bathroom", r"bathroom|kylpy- tai pesuhuone"), ("wc_room", r"separate wc|erillistä wc"),
    ("balcony", r"balcon|parveke"),
]


def kind_of(q: str) -> str | None:
    ql = q.lower()
    for k, rx in KIND_RE:
        if re.search(rx, ql):
            return k
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--sources", default="cubicasa5k")
    ap.add_argument("--max-drawings", type=int, default=0)
    ap.add_argument("--para-prob", type=float, default=0.25)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--png-twins", action="store_true",
                    help="questions asked on a vector file (swiss PDF/DXF) train on its PNG twin (same drawing, raster)")
    ap.add_argument("--exclude-split", default="train_gate",
                    help="drop every drawing that appears in this split (train_gate is used to gate the model; "
                         "training on it would make the gate meaningless). '' = keep all")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    srcs = set(a.sources.split(","))

    excluded = {q.path for q in load_split(a.exclude_split)} if a.exclude_split else set()
    by_drawing: dict[str, dict[str, list]] = collections.defaultdict(lambda: collections.defaultdict(list))
    n_q = 0
    for q in load_split("train"):
        if q.source not in srcs or q.type != "count" or q.path in excluded:
            continue
        k = kind_of(q.question) if q.source == "cubicasa5k" else template_of(q.question)
        if k is None:
            continue
        path = q.path
        if Path(path).suffix.lower() not in (".png", ".jpg", ".jpeg"):
            twin = str(Path(path).with_suffix(".png"))
            if not (a.png_twins and abspath(twin).exists()):
                continue  # the LoRA only sees raster images
            path = twin
        by_drawing[path][k].append(q)
        n_q += 1

    paths = sorted(by_drawing)
    rng.shuffle(paths)
    if a.max_drawings:
        paths = paths[: a.max_drawings]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_turns = 0
    with open(out, "w") as f:
        for p in paths:
            turns = []
            for k, qs in by_drawing[p].items():
                q = rng.choice(qs)
                text = q.question
                if k in PARA and rng.random() < a.para_prob:
                    text = rng.choice(PARA[k])
                ans = q.answer
                ans = int(round(float(ans))) if isinstance(ans, (int, float)) or str(ans).replace(".", "").isdigit() else ans
                turns.append({"q": text, "a": str(ans)})
            rng.shuffle(turns)
            f.write(json.dumps({"image": str(abspath(p)), "path": p, "source": p.split("/")[1], "turns": turns}) + "\n")
            n_turns += len(turns)
    print(f"{len(paths)} drawings, {n_turns} turns (from {n_q} train questions; {len(excluded)} paths of "
          f"split {a.exclude_split!r} excluded) -> {out}")


if __name__ == "__main__":
    main()
