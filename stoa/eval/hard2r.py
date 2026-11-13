"""Generate `hard2r`: a SEALED held-out set for milestone runs (test 2 and later). No wordings live in git.

Why: `hard2q` was the clean held-out set at 01:14, but by 01:50 several agents had measured it per solver version
and tuned thresholds from its aggregates, and its wordings are readable in stoa/eval/hard2p.py. hard2r is fresher
in two ways:
  1. a NEW DRAW of the hard2 recipes (different rooms, thresholds, apartments and storeys on the same dev drawings,
     via another seed), so most answers differ from hard2/hard2p/hard2q (meta.draw = "fresh"; recipes that are
     deterministic per storey/drawing can redraw a hard2 instance: meta.draw = "same-as-hard2");
  2. a FOURTH wording in new languages (swiss Spanish, ifc Estonian, cubicasa Polish, plus new English), read from
     $JUNCTION_SHARED/sealed/F/hard2r_templates.json, outside git.
Rules (like D10): only F and S0 run it, at milestones, aggregates only; never quote its questions or failures.

Run:  python -m stoa.eval.hard2r --write  -> $JUNCTION_SHARED/results/splits/hard2r.jsonl (refuses to overwrite)
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import random
import re
from pathlib import Path

from stoa.eval import hard2
from stoa.eval.hard2p import REWORD
from stoa.eval.splits import SEED, splits_dir

DRAW_OFFSET = 17   # hard2 uses SEED + 2; this gives a different sample of rooms/thresholds/apartments/storeys
WORD_OFFSET = 11


def templates_path() -> Path:
    root = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")
    return Path(root) / "sealed" / "F" / "hard2r_templates.json"


def build(seed: int = SEED) -> list[dict]:
    spec = json.load(open(templates_path(), encoding="utf-8"))
    tpls, and_word, lang = spec["templates"], spec["and"], spec["lang"]
    hard2_ids = {json.loads(line)["qid"] for line in open(splits_dir() / "hard2.jsonl", encoding="utf-8") if line.strip()}
    rng = random.Random(seed + WORD_OFFSET)
    out = []
    for r in hard2.build(seed + DRAW_OFFSET):
        # deterministic recipes (per storey / per drawing) can redraw the same instance as hard2: keep it, tagged
        draw = "same-as-hard2" if r["qid"] in hard2_ids else "fresh"
        recipe = r["meta"]["recipe"]
        key = f"{recipe}@ifc" if (recipe == "rooms-above-threshold" and r["source"] == "ifc_models") else recipe
        m = re.match(REWORD[key][0], r["question"])
        if not m:
            raise ValueError(f"{key}: no match")
        i = rng.randrange(2)
        q = tpls[key][i]
        lg = "en" if i == 0 else lang[r["source"]]
        for k, g in enumerate(m.groups(), 1):
            if lg != "en":
                g = g.replace(" and ", and_word[lg])
            q = q.replace("{" + str(k) + "}", g)
        qid = "r" + hashlib.sha1(f"{r['path']}\n{q}".encode()).hexdigest()[:11]
        out.append({**r, "qid": qid, "question": q,
                    "meta": {**r["meta"], "kind": "reasoning-reworded-r", "variant": lg, "draw": draw}})
    return out


def write(seed: int = SEED, force: bool = False) -> dict:
    f = splits_dir() / "hard2r.jsonl"
    if f.exists() and not force:
        raise SystemExit(f"{f} exists; splits are frozen (use --force only if nobody has run on it)")
    rows = build(seed)
    with open(f, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    c = collections.Counter((r["source"], r["type"], r["meta"]["variant"], r["meta"]["draw"]) for r in rows)
    return {"n": len(rows), "path": str(f), "by": {"/".join(k): v for k, v in sorted(c.items())}}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.write:
        print(json.dumps(write(force=a.force), indent=1, ensure_ascii=False))
    else:  # counts only: never print the questions
        rows = build()
        c = collections.Counter((r["source"], r["meta"]["recipe"], r["meta"]["variant"]) for r in rows)
        for k, v in sorted(c.items()):
            print(v, k)
