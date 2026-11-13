"""Per-drawing table of gold cubicasa counts (one row per drawing, one column per English concept).

Used to test whether room-type counts (which a label-reading VLM call gets right ~80% of the time) predict
fixture counts (WC seats, sinks, showers+baths) better than the constant prior. Only train-split drawings
are used to choose rules; dev drawings only to report.

    python experiments/F/label2fixture/table.py --split train > /dev/null   # prints a summary to stderr
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict

from stoa.data import load_questions, template_of

CONCEPTS = {
    "window": "how many windows are shown on this floor plan?",
    "storey": "how many floors (storeys) does this floor plan show?",
    "wc_seat": "how many toilet bowls (wc seats) are drawn on this floor plan?",
    "sink": "how many sinks and wash basins (kitchen and bathroom combined; a double-bowl sink counts as one) are drawn on this floor plan?",
    "shower_bath": "how many showers and bathtubs are drawn on this floor plan in total?",
    "door": "how many doors are shown on this floor plan? count doorways fitted with a door; open doorways without a door leaf do not count.",
    "sauna": "how many saunas are on this floor plan?",
    "kitchen": "how many kitchens (including kitchenettes, open kitchens and utility kitchens) are on this floor plan?",
    "bedroom": "how many bedrooms (makuuhuone, usually marked mh) are on this floor plan?",
    "bathroom": "how many bathrooms or washrooms (e.g. kh, kph, ph, pesuh, sh) are on this floor plan, not counting separate wc rooms?",
    "wc_room": "how many separate wc rooms (toilet rooms marked wc) are on this floor plan?",
    "balcony": "how many balconies (parveke, including glazed balconies) are on this floor plan?",
}
BY_TEMPLATE = {v: k for k, v in CONCEPTS.items()}


def drawing_table(paths: set[str] | None = None) -> dict[str, dict[str, int]]:
    """path -> {concept: gold count} over ALL cubicasa questions (each drawing's questions share a split)."""
    out: dict[str, dict[str, int]] = defaultdict(dict)
    for q in load_questions():
        if q.source != "cubicasa5k" or (paths is not None and q.path not in paths):
            continue
        c = BY_TEMPLATE.get(template_of(q.question))
        if c is not None:
            out[q.path][c] = int(round(float(q.answer)))
    return dict(out)


def split_paths(name: str) -> set[str]:
    from stoa.eval.splits import splits_dir
    with open(splits_dir() / f"{name}.jsonl", encoding="utf-8") as fh:
        return {json.loads(line)["path"] for line in fh if line.strip()}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    a = ap.parse_args()
    t = drawing_table(split_paths(a.split))
    print(f"{len(t)} drawings", file=sys.stderr)
    for p, row in t.items():
        print(json.dumps({"path": p, **row}))
