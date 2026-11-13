"""Leak-safe eval set for models pretrained on CubiCasa5K (DECISION D3).

Our cubicasa5k PNG `<folder>-<id>.png` is CubiCasa5K `/<folder>/<id>/` (all 4,787 map). A model trained on
the official CubiCasa5K train (and tuned on val) has only NOT seen the official `test` drawings. This
writes `cc5k_heldout.jsonl` (same format as results/splits/*.jsonl): questions on our drawings that are in
the official CubiCasa5K test list, excluding our sealed `test` split, at most CAP per drawing, English only
(the Finnish twin has the same answer), templates rotated so every template is covered.
Run: python3 -I make_heldout.py   (needs artifacts/R1/cc5k_split/test.txt from fetch_lists.py)
"""
import collections
import hashlib
import json
import os
import random

SHARED = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")
DATA = os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")
A = os.path.join(SHARED, "artifacts", "R1", "cc5k_split")
CAP = 4
FI = ("Kuinka", "Montako")


def qid(path, question):  # must match stoa.data.make_qid
    return hashlib.sha1((path + "\n" + question).encode("utf-8")).hexdigest()[:12]


if __name__ == "__main__":
    official_test = set()
    for line in open(os.path.join(A, "test.txt")):
        line = line.strip().strip("/")
        if line:
            folder, i = line.split("/")[-2:]
            official_test.add(f"{folder}-{i}")
    sealed = {json.loads(l)["path"] for l in open(os.path.join(SHARED, "results", "splits", "test.jsonl"))}
    by_draw = collections.defaultdict(list)
    for line in open(os.path.join(DATA, "questions.jsonl")):
        d = json.loads(line)
        if not d["path"].startswith("data/cubicasa5k/") or d["path"] in sealed:
            continue
        stem = os.path.basename(d["path"])[:-4]
        if stem in official_test and not d["question"].startswith(FI):
            by_draw[d["path"]].append(d)
    rng = random.Random(20261113)
    out, tpl_count = [], collections.Counter()
    for path in sorted(by_draw):
        qs = by_draw[path]
        rng.shuffle(qs)
        qs.sort(key=lambda d: tpl_count[d["question"][:40]])  # least-covered templates first
        for d in qs[:CAP]:
            tpl_count[d["question"][:40]] += 1
            out.append({"qid": qid(d["path"], d["question"]), "path": d["path"], "type": d["type"],
                        "source": "cubicasa5k", "group": "cubicasa5k/" + os.path.basename(d["path"])[:-4]})
    with open(os.path.join(A, "cc5k_heldout.jsonl"), "w") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
    print(f"{len(out)} questions on {len(by_draw)} drawings; templates: {len(tpl_count)}; min/max per template "
          f"{min(tpl_count.values())}/{max(tpl_count.values())}")
