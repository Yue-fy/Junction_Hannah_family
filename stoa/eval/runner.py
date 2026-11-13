"""Run a registered solver over a split, score it, write predictions and one leaderboard line."""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import os
import random
import statistics
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from stoa.contract import Answer
from stoa.data import Question, template_of
from stoa.eval.scoring import score, text_fuzzy
from stoa.eval.splits import load_split, shared_root

SCORED_TYPES = ("count", "area", "length", "volume")


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=10,
                              cwd=Path(__file__).resolve().parents[2]).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def _parse_kv(items: list[str]) -> dict:
    out = {}
    for it in items or []:
        k, _, v = it.partition("=")
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


def select(questions: list[Question], sources=None, types=None, limit=None, seed: int = 0) -> list[Question]:
    qs = [q for q in questions if (not sources or q.source in sources) and (not types or q.type in types)]
    if limit and limit < len(qs):
        idx = sorted(random.Random(seed).sample(range(len(qs)), limit))  # same subset every run
        qs = [qs[i] for i in idx]
    return qs


def run_one(solver, q: Question, handled_only: bool) -> dict:
    t0 = time.perf_counter()
    err = None
    handled = True
    try:
        handled = bool(solver.can_handle(q.path, q.question))
    except Exception:  # noqa: BLE001
        handled = True
    try:
        if handled_only and not handled:
            ans = Answer.abstain(getattr(solver, "name", "?"), "can_handle=False")
        else:
            ans = solver.solve(q.path, q.question)
            if not isinstance(ans, Answer):
                ans = Answer.model_validate(ans)
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
        ans = Answer.abstain(getattr(solver, "name", "?"), "exception", [traceback.format_exc(limit=4)[-800:]])
    dt = time.perf_counter() - t0
    correct = score(q.type, q.answer, q.unit, ans.value, ans.unit)
    return {
        "qid": q.qid, "path": q.path, "question": q.question, "type": q.type, "source": q.source,
        "template": template_of(q.question), "gold": q.answer, "gold_unit": q.unit,
        "value": ans.value, "unit": ans.unit, "confidence": ans.confidence,
        "correct": correct, "text_fuzzy": text_fuzzy(ans.value, q.answer) if q.type in ("text", "other") else None,
        "abstained": ans.value is None, "handled": handled, "latency_s": round(dt, 4),
        "solver": ans.solver, "evidence": [e.model_dump(exclude_none=True) for e in ans.evidence],
        "trace": ans.trace[-20:], "error": err,
    }


def summarize(preds: list[dict]) -> dict:
    def block(rows: list[dict]) -> dict:
        scored = [r for r in rows if r["type"] in SCORED_TYPES]
        text = [r for r in rows if r["type"] not in SCORED_TYPES]
        answered = [r for r in rows if not r["abstained"]]
        d = {
            "n": len(rows),
            "scored_n": len(scored),
            "correct": sum(1 for r in scored if r["correct"]),
            "accuracy": round(sum(1 for r in scored if r["correct"]) / len(scored), 4) if scored else None,
            "coverage": round(len(answered) / len(rows), 4) if rows else None,
            "acc_when_answered": (round(sum(1 for r in scored if r["correct"]) /
                                        max(1, sum(1 for r in scored if not r["abstained"])), 4) if scored else None),
            "evidence_rate": round(sum(1 for r in answered if r["evidence"]) / len(answered), 4) if answered else None,
        }
        if text:
            d["text_n"] = len(text)
            d["text_fuzzy"] = round(sum(1 for r in text if r["text_fuzzy"]) / len(text), 4)
        return d

    out = block(preds)
    buckets = collections.defaultdict(list)
    for r in preds:
        buckets[f"{r['source']}/{r['type']}"].append(r)
    out["by_bucket"] = {k: block(v) for k, v in sorted(buckets.items())}
    accs = [b["accuracy"] for b in out["by_bucket"].values() if b["accuracy"] is not None]
    out["macro_accuracy"] = round(sum(accs) / len(accs), 4) if accs else None
    lat = sorted(r["latency_s"] for r in preds)
    if lat:
        out["latency_mean_s"] = round(statistics.fmean(lat), 3)
        out["latency_p50_s"] = round(lat[len(lat) // 2], 3)
        out["latency_p95_s"] = round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 3)
    out["errors"] = sum(1 for r in preds if r["error"])
    return out


def print_report(m: dict, file=sys.stdout) -> None:
    def pct(x):
        return "  -  " if x is None else f"{100 * x:5.1f}"

    print(f"\n{'bucket':34s} {'n':>6s} {'acc%':>6s} {'cov%':>6s} {'ans-acc%':>8s} {'evid%':>6s} {'text~%':>6s}", file=file)
    for k, b in m["by_bucket"].items():
        print(f"{k:34s} {b['n']:6d} {pct(b['accuracy']):>6s} {pct(b['coverage']):>6s} {pct(b['acc_when_answered']):>8s} "
              f"{pct(b['evidence_rate']):>6s} {pct(b.get('text_fuzzy')):>6s}", file=file)
    print(f"{'OVERALL (micro, scored types)':34s} {m['n']:6d} {pct(m['accuracy']):>6s} {pct(m['coverage']):>6s} "
          f"{pct(m['acc_when_answered']):>8s} {pct(m['evidence_rate']):>6s} {pct(m.get('text_fuzzy')):>6s}", file=file)
    print(f"macro accuracy over buckets: {pct(m['macro_accuracy'])}   latency mean/p50/p95 s: "
          f"{m.get('latency_mean_s')}/{m.get('latency_p50_s')}/{m.get('latency_p95_s')}   errors: {m['errors']}", file=file)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m stoa.eval", description=__doc__)
    ap.add_argument("--solver", required=True, help="registered solver name (see --list)")
    ap.add_argument("--split", default="smoke", help="smoke | dev | test | train | all")
    ap.add_argument("--limit", type=int, default=None, help="fixed random subset of N questions (same every run)")
    ap.add_argument("--source", action="append", default=None, help="filter by source; repeat or comma-separate")
    ap.add_argument("--type", action="append", default=None, help="filter by type (count, area, ...)")
    ap.add_argument("--workers", type=int, default=4, help="parallel threads calling solver.solve")
    ap.add_argument("--solver-arg", action="append", default=[], help="key=value passed to the solver constructor")
    ap.add_argument("--handled-only", action="store_true", help="abstain without calling solve() when can_handle is False")
    ap.add_argument("--note", default="", help="free text stored in the leaderboard line")
    ap.add_argument("--no-leaderboard", action="store_true", help="don't append to results/leaderboard.jsonl")
    ap.add_argument("--allow-test", action="store_true", help="required for --split test (S0 only)")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    from stoa.solvers import available, get_solver, import_errors

    if a.split == "test" and not a.allow_test:
        print("the test split is sealed: only S0 runs it (with --allow-test)", file=sys.stderr)
        return 2
    sources = {s for x in (a.source or []) for s in x.split(",") if s}
    types = {t for x in (a.type or []) for t in x.split(",") if t}
    kwargs = _parse_kv(a.solver_arg)
    try:
        solver = get_solver(a.solver, **kwargs)
    except KeyError as e:
        print(e, file=sys.stderr)
        for mod, tb in import_errors().items():
            print(f"[import error] {mod}\n{tb}", file=sys.stderr)
        return 2

    qs = select(load_split(a.split), sources, types, a.limit)
    if not qs:
        print("no questions selected", file=sys.stderr)
        return 2
    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{a.solver}-{a.split}" + (f"-n{len(qs)}" if a.limit else "")
    out_dir = shared_root() / "artifacts" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    preds_path = out_dir / f"{run_id}.jsonl"

    try:
        from tqdm import tqdm
    except ImportError:  # pragma: no cover
        tqdm = None
    preds: list[dict] = []
    t0 = time.time()
    with open(preds_path, "w", encoding="utf-8") as fout, cf.ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        futs = [ex.submit(run_one, solver, q, a.handled_only) for q in qs]
        it = cf.as_completed(futs)
        if tqdm and not a.quiet:
            it = tqdm(it, total=len(futs), desc=run_id, file=sys.stderr, mininterval=2)
        for f in it:
            r = f.result()
            preds.append(r)
            fout.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    wall = time.time() - t0
    order = {q.qid: i for i, q in enumerate(qs)}
    preds.sort(key=lambda r: order[r["qid"]])

    m = summarize(preds)
    m["wall_s"] = round(wall, 1)
    print_report(m)
    status = _git("status", "--porcelain", "--untracked-files=no")
    line = {
        "time": datetime.now().isoformat(timespec="seconds"), "run_id": run_id, "solver": a.solver,
        "solver_args": kwargs, "split": a.split, "limit": a.limit, "sources": sorted(sources) or None,
        "types": sorted(types) or None, "handled_only": a.handled_only, "n": len(qs),
        "commit": _git("rev-parse", "--short", "HEAD"), "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(status), "agent": os.environ.get("AGENT_ID", ""), "note": a.note,
        "metrics": m, "preds": str(preds_path),
    }
    if not a.no_leaderboard:
        lb = shared_root() / "results" / "leaderboard.jsonl"
        with open(lb, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    print(f"\npredictions: {preds_path}" + ("" if a.no_leaderboard else "\nleaderboard: appended"))
    if m["errors"]:
        print(f"WARNING: {m['errors']} questions raised exceptions (see 'error' in predictions)", file=sys.stderr)
    _ = available  # keep import for --help discoverability
    return 0
