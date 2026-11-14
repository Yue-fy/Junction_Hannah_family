"""Measure route.per_room: false fires on every non-sealed split + all dataset questions, recall on the probes.

    python experiments/r1/room_graph/route_eval.py   (needs STOA_DATA, JUNCTION_SHARED)
Sealed / held-out splits (test, hard2q, hard2p, hard2r, hard3, hardL) are NOT read here: S0 may count firings there
as an aggregate.
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from experiments.r1.room_graph.route import per_room, text_trigger  # noqa: E402
from stoa.data import load_questions  # noqa: E402

SPLITS = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")) / "results/splits"
HERE = Path(__file__).parent


def main():
    qs = load_questions()
    byid = {q.qid: q for q in qs}
    # 1) every dataset question (all sources), text trigger and raster-gated trigger
    fires, rfires = Counter(), Counter()
    ex = {}
    for q in qs:
        t = text_trigger(q.question)
        if t["fire"]:
            fires[q.source] += 1
            ex.setdefault(q.source, []).append((q.question[:110], t["kind"], t["match"]))
            if per_room(q.question, q.path)["fire"]:
                rfires[q.source] += 1
    tot = Counter(q.source for q in qs)
    print("dataset questions.jsonl: text-trigger fires / raster-gated fires / total, by source")
    for s in sorted(tot):
        print(f"  {s:20s} {fires[s]:6d} {rfires[s]:6d} / {tot[s]}")
    for s, rows in ex.items():
        for r in rows[:4]:
            print("   e.g.", s, r)
    # 2) non-sealed generated splits (rows carry question text)
    for name in ["smoke", "dev", "hard", "hard2", "hardL_open", "cc5k_heldout", "train_gate"]:
        f = SPLITS / f"{name}.jsonl"
        n = k = kr = 0
        eg = []
        for line in open(f):
            r = json.loads(line)
            qtext = r.get("question") or (byid[r["qid"]].question if r["qid"] in byid else None)
            if qtext is None:
                continue
            n += 1
            t = text_trigger(qtext)
            if t["fire"]:
                k += 1
                if per_room(qtext, r["path"])["fire"]:
                    kr += 1
                    eg.append((qtext[:120], t["kind"], t["match"]))
        print(f"split {name:12s}: text fires {k:4d}, raster-gated {kr:4d} / {n}")
        for e in eg[:6]:
            print("     ", e)
    # 3) recall on the room-graph probes (all per-room by construction except the whole-apartment area rows)
    for f in sorted((HERE / "probe").glob("probe_v*.jsonl")):
        rows = [json.loads(l) for l in open(f)]
        miss = [r["question"] for r in rows if not per_room(r["question"], r["path"])["fire"]]
        print(f"{f.name}: fires {len(rows) - len(miss)}/{len(rows)}; not fired: {miss}")
    # 4) fresh phrasing probe written before the trigger ran on it
    tp = fp = fn = tn = 0
    for line in open(HERE / "route_probe.txt"):
        if not line.strip() or line.startswith("#"):
            continue
        y, q = line.rstrip("\n").split("|", 1)
        hit = text_trigger(q)["fire"]
        if y == "1":
            tp += hit
            fn += not hit
            if not hit:
                print("   MISS", q)
        else:
            fp += hit
            tn += not hit
            if hit:
                print("   FALSE", q, text_trigger(q))
    print(f"route_probe.txt: recall {tp}/{tp + fn}, false fires {fp}/{fp + tn}")


if __name__ == "__main__":
    main()
