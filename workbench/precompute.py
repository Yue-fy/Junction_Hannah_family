"""Precompute the audit sample for the expert workbench (tab 1, "Check our answers").

    $JUNCTION_VENV/bin/python -m workbench.precompute [--n 40] [--seed 7]

Picks ~40 dev questions spread over sources and question types (one per drawing per stratum), runs the
`pipeline` solver on each (same code path as the eval: stoa.eval.runner.run_one) and writes
$JUNCTION_SHARED/human/audit_items.jsonl. About a third of each stratum is drawn from answers that are wrong
or below 0.6 confidence, because that is where a human check is most informative; the rest are confident
answers (is the evidence good enough to verify them in seconds?).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

from workbench.store import human_dir

# (source, type) -> how many items in the sample of 40
QUOTA = {
    ("cubicasa5k", "count"): 10,
    ("swiss_dwellings", "area"): 5,
    ("swiss_dwellings", "count"): 5,
    ("ifc_models", "area"): 4,
    ("ifc_models", "count"): 3,
    ("ifc_models", "volume"): 2,
    ("ifc_models", "length"): 1,
    ("ifc_bench", "text"): 4,
    ("opening_design", "count"): 2,
    ("opening_design", "text"): 2,
    ("opening_design", "area"): 2,
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40, help="scale the quotas to about this many items")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--oversample", type=float, default=2.0, help="candidates per slot (to find wrong ones)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--split", default="dev", help="dev uses QUOTA; other splits get a proportional quota per stratum")
    ap.add_argument("--prefix", default="a", help="item_id prefix (a = first batch, b = harder batch, ...)")
    ap.add_argument("--refresh", default=None, metavar="ITEMS.jsonl",
                    help="re-run the SAME items of this file on the current pipeline (items the expert already "
                         "checked keep their old answer, so her verdict stays about what she saw)")
    a = ap.parse_args(argv)

    from stoa.eval.runner import run_one
    from stoa.eval.splits import load_split
    from stoa.solvers import get_solver

    if a.refresh:
        return refresh(Path(a.refresh), run_one, load_split, get_solver("pipeline"))

    rng = random.Random(a.seed)
    strata: dict[tuple, list] = defaultdict(list)
    for q in load_split(a.split):
        strata[(q.source, q.type)].append(q)
    quotas = QUOTA if a.split == "dev" else {k: len(v) for k, v in strata.items()}
    scale = a.n / sum(quotas.values())

    solver = get_solver("pipeline")
    picked: list[dict] = []
    for key, quota in quotas.items():
        quota = max(1, round(quota * scale))
        pool = strata.get(key, [])
        rng.shuffle(pool)
        seen_paths, cands = set(), []
        for q in pool:  # one question per drawing
            if q.path in seen_paths:
                continue
            seen_paths.add(q.path)
            cands.append(q)
            if len(cands) >= math.ceil(quota * a.oversample):
                break
        rows = []
        for q in cands:
            t0 = time.time()
            r = run_one(solver, q, handled_only=False)
            print(f"{key} {q.qid} conf={r['confidence']:.2f} correct={r['correct']} "
                  f"{time.time() - t0:.1f}s  {q.question[:70]}", file=sys.stderr, flush=True)
            rows.append(r)
        hard = [r for r in rows if r["correct"] is False or (r["confidence"] or 0) < 0.6]
        easy = [r for r in rows if r not in hard]
        n_hard = min(len(hard), max(1, quota // 3))
        chosen = hard[:n_hard] + easy[: quota - n_hard]
        chosen += [r for r in hard[n_hard:] if len(chosen) < quota][: quota - len(chosen)]
        picked.extend(chosen)

    # interleave sources so the expert sees variety from the first item
    by_src = defaultdict(list)
    for r in picked:
        by_src[r["source"]].append(r)
    order = []
    while any(by_src.values()):
        for s in list(by_src):
            if by_src[s]:
                order.append(by_src[s].pop(0))
    out = Path(a.out) if a.out else human_dir() / "audit_items.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for i, r in enumerate(order, 1):
            r["item_id"] = f"{a.prefix}{i:02d}-{r['qid']}"
            r["split"] = a.split
            r["made_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    tmp.replace(out)
    print(f"wrote {len(order)} items to {out}", file=sys.stderr)
    return 0


def refresh(path: Path, run_one, load_split, solver) -> int:
    from workbench import store

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    checked = {r.get("item_id") for r in store.read("audit")}
    by_split: dict[str, dict] = {}
    changed = 0
    out = []
    for r in rows:
        if r["item_id"] in checked:
            out.append(r)
            continue
        sp = r.get("split") or "dev"
        if sp not in by_split:
            by_split[sp] = {q.qid: q for q in load_split(sp)}
        q = by_split[sp].get(r["qid"])
        if q is None:
            print(f"{r['item_id']}: not in split {sp}, kept", file=sys.stderr)
            out.append(r)
            continue
        new = run_one(solver, q, handled_only=False)
        if (new.get("value"), new.get("correct")) != (r.get("value"), r.get("correct")):
            changed += 1
            print(f"{r['item_id']}: {r.get('value')!r} ({r.get('correct')}) -> {new.get('value')!r} ({new.get('correct')}) "
                  f"conf {r.get('confidence')} -> {new.get('confidence')}", file=sys.stderr, flush=True)
        keep = {k: r[k] for k in ("item_id", "split", "batch", "batch_label", "ref_label") if k in r}
        out.append({**new, **keep, "made_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "refreshed_from": r.get("made_at")})
    checked = {r.get("item_id") for r in store.read("audit")}  # she may have clicked meanwhile
    out = [o if o["item_id"] not in checked else next(r for r in rows if r["item_id"] == o["item_id"]) for o in out]
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False, default=str) + "\n")
    tmp.replace(path)
    print(f"refreshed {path}: {len(out)} items, {changed} answers changed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
