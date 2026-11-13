"""Measure every raster method per object class on a TRAIN sample (never dev), write the gate.

    PYTHONPATH=$PWD $JUNCTION_VENV/bin/python experiments/w3/calibrate.py --n 60 [--methods labels,points,direct]
        [--write-gate]

Output: $JUNCTION_SHARED/artifacts/W3/calib/<run>.jsonl (one row per drawing x class x method) and a table of
accuracy per class x method next to the prior. --write-gate picks, per class, the method with the best TRAIN
accuracy (the prior wins ties) and writes stoa/solvers/raster/gate.json.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import contextvars
import json
import os
import random
import time
from pathlib import Path

from stoa.eval.splits import load_split
from stoa.solvers.raster import GATE_FILE, class_prior, vlm
from stoa.solvers.raster.classes import ALL_CLASSES, ROOM_CLASSES, SYMBOL_CLASSES, question_class
from stoa.data import abspath

SHARED = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--methods", default="labels,points,direct")
    ap.add_argument("--target-px", type=int, default=2_000_000)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--write-gate", action="store_true")
    ap.add_argument("--tag", default="")
    ap.add_argument("--classes", default="", help="comma list: only these classes for points/direct")
    a = ap.parse_args()
    methods = a.methods.split(",")
    only = set(a.classes.split(",")) if a.classes else None

    gold: dict[str, dict[str, tuple]] = collections.defaultdict(dict)  # path -> cls -> (answer, EN question)
    for q in load_split("train"):
        if q.source != "cubicasa5k" or not q.question.lower().startswith("how"):
            continue
        c = question_class(q.question)
        if c:
            gold[q.path][c] = (q.answer, q.question)
    paths = sorted(p for p, d in gold.items() if len(d) >= 8)
    random.Random(a.seed).shuffle(paths)
    paths = paths[: a.n]
    print(f"{len(paths)} train drawings, methods={methods}")

    tasks = []
    for p in paths:
        for m in methods:
            if m == "labels":
                tasks.append((p, "labels", None))
            elif m == "points":
                tasks += [(p, "points", c) for c in SYMBOL_CLASSES if c in gold[p] and (not only or c in only)]
            elif m == "direct":
                tasks += [(p, "direct", c) for c in gold[p] if not only or c in only]

    def run(t):
        p, m, c = t
        img = vlm.llm.load_image(abspath(p))
        t0 = time.time()
        try:
            if m == "labels":
                items, log, _ = vlm.read_labels(img, p, target_px=a.target_px)
                return dict(path=p, method=m, items=[(i.text, i.cls, round(i.x), round(i.y)) for i in items],
                            tok=(log.tokens_in, log.tokens_out), s=round(time.time() - t0, 1), notes=log.notes)
            if m == "points":
                items, log, _ = vlm.point_symbols(img, p, c, target_px=a.target_px)
                return dict(path=p, method=m, cls=c, value=len(items), tok=(log.tokens_in, log.tokens_out),
                            s=round(time.time() - t0, 1), notes=log.notes)
            v, log = vlm.direct_count(img, gold[p][c][1])
            return dict(path=p, method=m, cls=c, value=v, tok=(log.tokens_in, log.tokens_out),
                        s=round(time.time() - t0, 1))
        except Exception as e:  # noqa: BLE001
            return dict(path=p, method=m, cls=c, error=f"{type(e).__name__}: {e}"[:300])

    out_dir = SHARED / "artifacts" / "W3" / "calib"
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("%Y%m%d-%H%M%S") + (f"-{a.tag}" if a.tag else "")
    rows = []
    t0 = time.time()
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(contextvars.copy_context().run, run, t) for t in tasks]
        for i, f in enumerate(cf.as_completed(futs)):
            rows.append(f.result())
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(tasks)} {time.time() - t0:.0f}s", flush=True)
    with open(out_dir / f"{run_id}.jsonl", "w") as fh:
        for r in rows:
            r["gold"] = {c: g[0] for c, g in gold[r["path"]].items()}
            fh.write(json.dumps(r) + "\n")
    print(f"wrote {out_dir / f'{run_id}.jsonl'} in {time.time() - t0:.0f}s")
    report(rows, gold, a.write_gate)


def preds_from_rows(rows):
    """-> {(path, cls, method): value}; label rows expand into one prediction per room class."""
    pred = {}
    for r in rows:
        if r.get("error"):
            continue
        if r["method"] == "labels":
            cnt = collections.Counter(c for _, c, _, _ in r["items"] if c)
            for c in ROOM_CLASSES:
                pred[(r["path"], c, "labels")] = cnt.get(c, 0)
        else:
            pred[(r["path"], r["cls"], r["method"])] = r["value"]
    return pred


def report(rows, gold, write_gate=False):
    prior = class_prior()
    pred = preds_from_rows(rows)
    methods = sorted({m for (_, _, m) in pred})
    table = {}
    print(f"\n{'class':12s} {'n':>4s} {'prior':>6s} " + " ".join(f"{m:>7s}" for m in methods))
    for c in ALL_CLASSES:
        ps = [p for p in gold if c in gold[p] and any((p, c, m) in pred for m in methods)]
        if not ps:
            continue
        acc = {"prior": sum(gold[p][c][0] == prior[c][0] for p in ps) / len(ps)}
        for m in methods:
            have = [p for p in ps if (p, c, m) in pred]
            if have:
                acc[m] = sum(pred[(p, c, m)] == gold[p][c][0] for p in have) / len(have)
        table[c] = (len(ps), acc)
        print(f"{c:12s} {len(ps):4d} {acc['prior']:6.0%} " + " ".join(
            f"{acc[m]:7.0%}" if m in acc else f"{'-':>7s}" for m in methods))
    if write_gate:
        gate = {}
        for c, (n, acc) in table.items():
            best = max(acc, key=lambda m: (acc[m], m == "prior"))
            gate[c] = {"method": best, "acc": {m: round(v, 3) for m, v in acc.items()}, "n_train": n}
        GATE_FILE.write_text(json.dumps(gate, indent=1) + "\n")
        print(f"wrote {GATE_FILE}")


if __name__ == "__main__":
    main()
