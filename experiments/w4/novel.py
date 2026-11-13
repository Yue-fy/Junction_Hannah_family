"""A small `novel` split: question KINDS that are neither dataset templates nor `hard` recipes (W4, cycle 2).

Stoa: the hidden test is "harder and different". This set checks whether the pipeline + general agent can
answer question kinds nothing was built for, on DEV drawings only, with gold computed from existing answers:

cubicasa  sleeping-rooms (= bedrooms, unseen synonym), wet-rooms (bathrooms + WC rooms + saunas),
          bed-minus-bath (bedrooms - bathrooms), cook (= kitchens, unseen wording)
swiss     avg-label-area (total area of label / number of rooms with that label), share-label (% of total
          indoor area), apt-diff (|apartment A - apartment B| in m²)
ifc       room-share (% of the storey's room area taken by one room), room-vs-storey-rest (storey area minus room)

    python experiments/w4/novel.py   -> $JUNCTION_SHARED/artifacts/W4/novel.jsonl
    python -m stoa.eval --solver pipeline --split $JUNCTION_SHARED/artifacts/W4/novel.jsonl --no-leaderboard
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import random
from pathlib import Path

from stoa.data import concept_map, drawing_group, load_questions
from stoa.eval.hard import parse
from stoa.eval.splits import SEED, split_of_group

OUT = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")) / "artifacts/W4/novel.jsonl"
PER_RECIPE = 12


def _row(path, question, answer, unit, typ, recipe, src):
    qid = "nv" + hashlib.sha1(f"{path}|{question}".encode()).hexdigest()[:10]
    return {"qid": qid, "path": path, "question": question, "answer": answer, "unit": unit, "type": typ,
            "source": src, "meta": {"kind": "novel", "recipe": recipe}}


def build(seed: int = SEED) -> list[dict]:
    rng = random.Random(seed + 7)
    sog = split_of_group()
    dev_groups = {g for g, s in sog.items() if s == "dev"}
    cm = concept_map()
    all_qs = load_questions()
    by_qid = {q.qid: q for q in all_qs}
    facts_by_path = collections.defaultdict(dict)
    for q in all_qs:
        if q.source not in ("cubicasa5k", "swiss_dwellings", "ifc_models") or drawing_group(q.path) not in dev_groups:
            continue
        if by_qid.get(cm.get(q.qid, q.qid), q).qid != q.qid:
            continue
        f = parse(q)
        if f and isinstance(q.answer, (int, float)):
            facts_by_path[q.path][f] = q.answer
    cands = collections.defaultdict(list)
    for path in sorted(facts_by_path):
        F = facts_by_path[path]
        g = lambda *k: F.get(tuple(k))  # noqa: E731
        if "cubicasa5k" in path:
            b, ba, wc, s, k = (g("cubi", x) for x in ("bedrooms", "bathrooms", "wc_rooms", "saunas", "kitchens"))
            if b is not None:
                cands["sleeping-rooms"].append(_row(path, "How many rooms in this home are meant for sleeping?", b,
                                                    "count", "count", "sleeping-rooms", "cubicasa5k"))
            if None not in (ba, wc, s):
                cands["wet-rooms"].append(_row(
                    path, "How many wet rooms does this apartment have (bathrooms/washrooms, separate WC rooms and "
                          "saunas all count)?", ba + wc + s, "count", "count", "wet-rooms", "cubicasa5k"))
            if None not in (b, ba) and b >= ba:
                cands["bed-minus-bath"].append(_row(
                    path, "Compared with the number of bathrooms (not separate WCs), how many more bedrooms are there?",
                    b - ba, "count", "count", "bed-minus-bath", "cubicasa5k"))
            if k is not None:
                cands["cook"].append(_row(path, "In how many separate places on this plan can one cook (kitchens, "
                                                "kitchenettes)?", k, "count", "count", "cook", "cubicasa5k"))
        elif "swiss_dwellings" in path:
            tot = next((v for f, v in F.items() if f[0] == "swiss_total_area"), None)
            for f, v in F.items():
                if f[0] == "swiss_label_area":
                    n = F.get(("swiss_label_count", f[1]))
                    if n:
                        cands["avg-label-area"].append(_row(
                            path, f"On average, how large (net m²) is a room labelled '{f[1]}' on this floor?",
                            round(v / n, 2), "m2", "area", "avg-label-area", "swiss_dwellings"))
                    if tot:
                        cands["share-label"].append(_row(
                            path, f"What percentage of the total net indoor floor area of this floor is taken up by "
                                  f"rooms labelled '{f[1]}'?", round(100 * v / tot, 4), "%", "area", "share-label",
                            "swiss_dwellings"))
            apts = [(f[1], v) for f, v in F.items() if f[0] == "swiss_apt_area"]
            if len(apts) >= 2:
                (a1, v1), (a2, v2) = rng.sample(apts, 2)
                if abs(v1 - v2) > 1:
                    cands["apt-diff"].append(_row(
                        path, f"What is the difference in net floor area between apartment {a1} and apartment {a2}, "
                              f"in m² (positive number)?", round(abs(v1 - v2), 2), "m2", "area", "apt-diff",
                        "swiss_dwellings"))
        else:
            storeys = {f[1]: v for f, v in F.items() if f[0] == "ifc_storey_area"}
            for f, v in F.items():
                if f[0] == "ifc_room_area" and f[2] in storeys and storeys[f[2]] > v > 0:
                    cands["room-share"].append(_row(
                        path, f"What share of the total room area on '{f[2]}' does the room '{f[1]}' take, in percent?",
                        round(100 * v / storeys[f[2]], 4), "%", "area", "room-share", "ifc_models"))
                    cands["storey-rest"].append(_row(
                        path, f"How much net floor area (m²) do all the other rooms on '{f[2]}' have together, "
                              f"leaving out '{f[1]}'?", round(storeys[f[2]] - v, 2), "m2", "area", "storey-rest",
                        "ifc_models"))
    out = []
    for recipe in sorted(cands):
        rows = cands[recipe]
        rng.shuffle(rows)
        seen_paths = set()
        for r in rows:  # one per drawing per recipe
            if r["path"] in seen_paths:
                continue
            seen_paths.add(r["path"])
            out.append(r)
            if len(seen_paths) >= PER_RECIPE:
                break
    return out


if __name__ == "__main__":
    rows = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(len(rows), "rows ->", OUT, collections.Counter(r["meta"]["recipe"] for r in rows))
