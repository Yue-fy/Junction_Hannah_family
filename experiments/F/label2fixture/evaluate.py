"""Fixture counts from room-label counts: does reading room codes (one VLM call per drawing, R1's cache) predict
WC seats, sinks and showers+bathtubs better than the constant prior?

Rules were chosen on TRAIN gold (table.py, 4,366 drawings), before looking at dev:
  sink        = kitchens' + bathrooms' + wc_rooms     (train gold: 81% vs mode 60%)
  wc_seat     = wc_rooms + bathrooms'                 (train gold: 72% vs mode 69%)
  shower_bath = bathrooms'                            (train gold: 85% vs mode 81%)
with kitchens' = 1 (the label reading over-counts kitchens: 12/51 too high on train, so use the prior,
as R1's policy does) and bathrooms' = max(1, k) (rooms that nearly always exist but are often unlabelled).
If the label output looped or holds no room code at all, the prior is used.

Here the room counts are R1's VLM label readings (artifacts/R1/room_labels/*.labels.v2[r].json), so errors
compound. Scored on every labelled drawing whose fixture question exists (all of the drawing's questions,
train and dev drawings reported separately; test drawings never touched).

    PYTHONPATH=. $JUNCTION_VENV/bin/python experiments/F/label2fixture/evaluate.py
"""
from __future__ import annotations

import collections
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
R1_DIR = Path(os.environ.get("R1_WT", "/data/User/fangy4/projects/junction-wt/R1")) / "experiments/r1/room_labels"
sys.path.insert(0, str(R1_DIR))

import run as r1  # noqa: E402  (R1's parser: parse_items, count_labels)
from table import drawing_table, split_paths  # noqa: E402

PRIOR = {"sink": 2, "wc_seat": 1, "shower_bath": 1}  # train mode (table.py)
LOOP = 6


def looped(text: str) -> bool:
    c = collections.Counter(t for _, t in r1.parse_items(text))
    return bool(c) and c.most_common(1)[0][1] > LOOP


def label_text(path: str) -> str | None:
    base = Path(r1.CACHE) / (Path(path).name + ".labels.v2.json")
    if not base.exists():
        return None
    text = json.loads(base.read_text())["text"]
    retry = base.with_name(base.name.replace(".labels.v2.json", ".labels.v2r.json"))
    if looped(text) and retry.exists():
        text = json.loads(retry.read_text())["text"]
    return text


KITCHEN = os.environ.get("KITCHEN", "prior")  # "prior" = always 1 (train: label reading over-counts kitchens 12/51)


def rules(k: collections.Counter) -> dict[str, int]:
    kit = 1 if KITCHEN == "prior" else max(1, k["kitchen"])
    bath, wc = max(1, k["bathroom"]), k["wc_room"]
    return {"sink": kit + bath + wc, "wc_seat": wc + bath, "shower_bath": bath}


def predict(path: str) -> tuple[dict[str, int], str]:
    text = label_text(path)
    if text is None:
        return {}, "no-labels"
    if looped(text):
        return dict(PRIOR), "loop->prior"
    k = r1.count_labels(text)
    if not any(k[c] for c in ("kitchen", "bathroom", "wc_room", "bedroom", "sauna", "balcony")):
        return dict(PRIOR), "no-room-codes->prior"
    return rules(k), "rules"


def main() -> None:
    for split in ("train", "dev"):
        table = drawing_table(split_paths(split))
        acc = collections.defaultdict(collections.Counter)
        modes = collections.Counter()
        for path, gold in table.items():
            pred, mode = predict(path)
            if mode == "no-labels":
                continue
            modes[mode] += 1
            for c, p in pred.items():
                if c not in gold:
                    continue
                acc[c]["n"] += 1
                acc[c]["rule"] += p == gold[c]
                acc[c]["prior"] += PRIOR[c] == gold[c]
                acc[c]["ruled"] += mode == "rules"
                if mode == "rules":
                    acc[c]["n_r"] += 1
                    acc[c]["rule_r"] += p == gold[c]
                    acc[c]["prior_r"] += PRIOR[c] == gold[c]
        print(f"== {split}: {sum(modes.values())} labelled drawings, modes {dict(modes)}")
        print(f"{'concept':12s} {'n':>4s} {'rules':>7s} {'prior':>7s} {'delta':>7s} | when rules fire: n, rules, prior")
        for c, s in acc.items():
            print(f"{c:12s} {s['n']:4d} {s['rule']/s['n']:7.1%} {s['prior']/s['n']:7.1%} "
                  f"{(s['rule']-s['prior'])/s['n']:+7.1%} | {s['n_r']:4d} {s['rule_r']/max(1,s['n_r']):6.1%} "
                  f"{s['prior_r']/max(1,s['n_r']):6.1%}")


if __name__ == "__main__":
    main()
