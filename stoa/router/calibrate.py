"""Build `stoa/router/gating.json`: run candidate solvers on a TRAIN sample, per (source, intent key).

    python -m stoa.router.calibrate --solvers vlm_direct,dxf --per-key 40 --workers 16

- Sample: up to `--per-key` train questions per (source, intent key), at most one per drawing group first
  (spreads over drawings), fixed seed. ifc_bench (free text, unscored) is skipped.
- Results are cached per (solver, qid) in $JUNCTION_SHARED/artifacts/W4/calib/<solver>.jsonl, so adding a
  new solver later only runs that solver. The prior (stoa.router.prior) is always scored.
- Never uses dev/test (S0 D4): the eval numbers on dev stay honest.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import random
import sys
import time
from datetime import datetime

from stoa.contract import CostMeter
from stoa.data import drawing_group, template_of
from stoa.eval.runner import cost_usd
from stoa.eval.scoring import score
from stoa.eval.splits import load_split, shared_root
from stoa.router import gating, prior
from stoa.router.intent import parse

SCORED = ("count", "area", "length", "volume")


def sample(per_key: int, seed: int = 7, sources: set[str] | None = None):
    by_key = collections.defaultdict(list)
    intents = {}
    for q in load_split("train"):
        if q.type not in SCORED or q.source == "ifc_bench" or (sources and q.source not in sources):
            continue
        t = template_of(q.question)
        it = intents.get(t) or intents.setdefault(t, parse(q.question))
        by_key[(q.source, it.key)].append(q)
    out = []
    for k, qs in sorted(by_key.items()):
        rng = random.Random(f"{seed}|{k[0]}|{k[1]}")  # per-key seed: a parser change elsewhere keeps this sample
        qs.sort(key=lambda q: q.qid)
        rng.shuffle(qs)
        seen, first, rest = set(), [], []
        for q in qs:
            g = drawing_group(q.path)
            (rest if g in seen else first).append(q)
            seen.add(g)
        out += [(k, q) for q in (first + rest)[:per_key]]
    return out


def _cache_path(solver: str):
    d = shared_root() / "artifacts" / "W4" / "calib"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{solver}.jsonl"


def _load_cache(solver: str) -> dict:
    p = _cache_path(solver)
    out = {}
    if p.exists():
        for line in p.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["qid"]] = r
    return out


def run_solver(name: str, items, workers: int, kwargs: dict) -> dict:
    from stoa.solvers import get_solver

    cache = _load_cache(name)
    todo = [(k, q) for k, q in items if q.qid not in cache]
    if todo:
        solver = get_solver(name, **kwargs)
        print(f"[calibrate] {name}: {len(todo)} to run ({len(items) - len(todo)} cached)", file=sys.stderr)

        def one(kq):
            k, q = kq
            t0 = time.perf_counter()
            with CostMeter() as m:
                try:
                    ok_h = solver.can_handle(q.path, q.question)
                    ans = solver.solve(q.path, q.question) if ok_h else None
                except Exception as e:  # noqa: BLE001
                    ans, ok_h = None, f"error {type(e).__name__}"
            val = None if ans is None else ans.value
            unit = None if ans is None else ans.unit
            c = m.cost.model_dump()
            if ans is not None:
                rep = ans.cost if isinstance(ans.cost, dict) else ans.cost.model_dump()
                c = {kk: max(c.get(kk, 0) or 0, rep.get(kk, 0) or 0) for kk in set(c) | set(rep)
                     if isinstance(rep.get(kk, c.get(kk)), (int, float))}
            c["wall_seconds"] = c.get("wall_seconds") or round(time.perf_counter() - t0, 4)
            return {"qid": q.qid, "key": f"{k[0]}|{k[1]}", "value": val, "unit": unit,
                    "conf": None if ans is None else ans.confidence, "handled": ok_h,
                    "correct": bool(score(q.type, q.answer, q.unit, val, unit)) if val is not None else False,
                    "usd": cost_usd(c)}

        with open(_cache_path(name), "a") as f, cf.ThreadPoolExecutor(max(1, workers)) as ex:
            for i, r in enumerate(ex.map(one, todo)):
                cache[r["qid"]] = r
                f.write(json.dumps(r, default=str) + "\n")
                if i % 200 == 0:
                    print(f"[calibrate] {name}: {i}/{len(todo)}", file=sys.stderr)
    return cache


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m stoa.router.calibrate", description=__doc__)
    ap.add_argument("--solvers", default="vlm_direct", help="comma-separated registered solver names")
    ap.add_argument("--per-key", type=int, default=40)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--source", action="append", default=None)
    ap.add_argument("--solver-arg", action="append", default=[], help="name.key=value, e.g. vlm_direct.style=cot")
    ap.add_argument("--out", default=str(gating.GATING_PATH))
    a = ap.parse_args(argv)

    sources = {s for x in (a.source or []) for s in x.split(",") if s} or None
    items = sample(a.per_key, sources=sources)
    print(f"[calibrate] {len(items)} train questions over {len({k for k, _ in items})} keys", file=sys.stderr)
    names = [s for s in a.solvers.split(",") if s]
    kw = collections.defaultdict(dict)
    for it in a.solver_arg:
        k, _, v = it.partition("=")
        sname, _, field = k.partition(".")
        kw[sname][field] = v

    results = {"prior": {}}
    for k, q in items:  # the prior: train mode/median per key (in-sample; thousands of rows per key)
        pa = prior.lookup(k[0], parse(q.question))
        results["prior"][q.qid] = {"correct": bool(pa and score(q.type, q.answer, q.unit, pa.value, pa.unit)), "usd": 0.0}
    for n in names:
        results[n] = run_solver(n, items, a.workers, kw.get(n, {}))

    old = gating.load(gating.GATING_PATH) if gating.GATING_PATH.exists() else {"entries": {}}
    entries = dict(old.get("entries", {}))
    by_key = collections.defaultdict(list)
    for k, q in items:
        by_key[f"{k[0]}|{k[1]}"].append(q.qid)
    for key, qids in sorted(by_key.items()):
        e = entries.get(key, {"acc": {}, "cost_usd": {}})
        e["n"] = len(qids)
        for n, res in results.items():
            rows = [res[qid] for qid in qids if qid in res]
            if rows:
                e["acc"][n] = round(sum(r["correct"] for r in rows) / len(rows), 4)
                e["cost_usd"][n] = round(sum(r.get("usd", 0) for r in rows) / len(rows), 7)
        entries[key] = e
    meta = {"built": datetime.now().isoformat(timespec="seconds"), "split": "train", "per_key": a.per_key,
            "solvers": sorted(set(old.get("meta", {}).get("solvers", [])) | set(names) | {"prior"}),
            "solver_args": {**old.get("meta", {}).get("solver_args", {}), **{k: v for k, v in kw.items()}}}
    with open(a.out, "w") as f:
        json.dump({"meta": meta, "entries": entries}, f, indent=1, sort_keys=True)
    print(f"{'key':48s} {'n':>4s} " + " ".join(f"{n[:12]:>12s}" for n in results))
    for key, e in sorted(entries.items()):
        print(f"{key:48s} {e['n']:4d} " + " ".join(f"{100 * e['acc'].get(n, float('nan')):12.1f}" for n in results))
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
