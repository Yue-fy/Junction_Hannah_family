"""Run a registered solver over a split, score it, write predictions and one leaderboard line."""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import os
import random
import re
import statistics
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from stoa.contract import Answer, Cost, CostMeter
from stoa.data import Question, template_of
from stoa.eval.scoring import score, text_fuzzy
from stoa.eval.splits import load_split, shared_root

SCORED_TYPES = ("count", "area", "length", "volume", "ratio")  # ratio: dimensionless (%, x:y), generated splits only

# Cost score = estimated USD per question. Rates are assumptions, written down so runs are comparable:
RATES = {
    "gpu_usd_per_s": 0.0006,  # ~$2.2/h for a 96 GB workstation GPU (cloud rental equivalent)
    "cpu_usd_per_s": 0.000014,  # ~$0.05/h per busy core; applied to wall seconds
    "api_usd_per_mtok_in": 0.40,  # hosted VLM (Nemotron Super class), assumed list price
    "api_usd_per_mtok_out": 1.60,
    "local_usd_per_mtok_in": 0.05,  # local tokens, only used when the solver reports no gpu_seconds
    "local_usd_per_mtok_out": 0.20,
}


# Local-LLM GPU time from tokens at the shared server's measured throughput (same constants as stoa.llm).
PREFILL_TPS = float(os.environ.get("LLM_PREFILL_TPS", 25_000))
DECODE_TPS = float(os.environ.get("LLM_DECODE_TPS", 1_000))


def gpu_seconds_billed(c: dict) -> float:
    """GPU seconds we charge. Solvers that time local LLM calls by HTTP latency include queueing on the
    shared server (00:30: 30.9 s reported for a 1.6k-in/205-out call that needs ~0.27 s). So when a row has
    local LLM tokens, charge min(reported, token estimate); GPU work without tokens is charged as reported."""
    gpu = c.get("gpu_seconds", 0) or 0
    local_in = max(0, (c.get("llm_tokens_in", 0) or 0) - (c.get("api_tokens_in", 0) or 0))
    local_out = max(0, (c.get("llm_tokens_out", 0) or 0) - (c.get("api_tokens_out", 0) or 0))
    if local_in or local_out:
        gpu = min(gpu, local_in / PREFILL_TPS + local_out / DECODE_TPS) if gpu else gpu
    return gpu


def cost_usd(c: dict) -> float:
    local_in = max(0, c.get("llm_tokens_in", 0) - c.get("api_tokens_in", 0))
    local_out = max(0, c.get("llm_tokens_out", 0) - c.get("api_tokens_out", 0))
    usd = gpu_seconds_billed(c) * RATES["gpu_usd_per_s"] + c.get("wall_seconds", 0) * RATES["cpu_usd_per_s"]
    usd += (c.get("api_tokens_in", 0) * RATES["api_usd_per_mtok_in"]
            + c.get("api_tokens_out", 0) * RATES["api_usd_per_mtok_out"]) / 1e6
    if not c.get("gpu_seconds"):
        usd += (local_in * RATES["local_usd_per_mtok_in"] + local_out * RATES["local_usd_per_mtok_out"]) / 1e6
    return usd


def cost_tier(c: dict) -> str:
    """deterministic (no model calls) < local (own GPU / local server) < api (hosted model)."""
    if c.get("api_calls", 0) > 0 or c.get("api_tokens_in", 0) > 0:
        return "api"
    if c.get("llm_calls", 0) > 0 or c.get("llm_tokens_in", 0) > 0 or c.get("gpu_seconds", 0) > 0:
        return "local"
    return "deterministic"


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


def select(questions: list[Question], sources=None, types=None, limit=None, seed: int = 0,
           grep: str | None = None) -> list[Question]:
    rx = re.compile(grep, re.I) if grep else None
    qs = [q for q in questions if (not sources or q.source in sources) and (not types or q.type in types)
          and (rx is None or rx.search(q.question))]
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
    with CostMeter() as meter:
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
    # cost = field-wise max of what the solver reported and what LLM clients recorded (avoids double count)
    rep = ans.cost.model_dump() if hasattr(ans.cost, "model_dump") else dict(ans.cost or {})
    met = meter.cost.model_dump()
    cost = {k: max(rep.get(k, 0) or 0, met.get(k, 0) or 0) for k in set(rep) | set(met)
            if isinstance(rep.get(k, met.get(k)), (int, float))}
    if not cost.get("wall_seconds"):
        cost["wall_seconds"] = round(dt, 4)
    cost["usd"] = round(cost_usd(cost), 7)
    correct = score(q.type, q.answer, q.unit, ans.value, ans.unit)
    return {
        "qid": q.qid, "path": q.path, "question": q.question, "type": q.type, "source": q.source,
        "template": template_of(q.question), "gold": q.answer, "gold_unit": q.unit,
        "value": ans.value, "unit": ans.unit, "confidence": ans.confidence,
        "correct": correct, "text_fuzzy": text_fuzzy(ans.value, q.answer) if q.type in ("text", "other") else None,
        "abstained": ans.value is None, "handled": handled, "latency_s": round(dt, 4),
        "solver": ans.solver, "evidence": [e.model_dump(exclude_none=True) for e in ans.evidence],
        "assumptions": ans.assumptions, "missing": ans.missing, "cost": cost, "tier": cost_tier(cost),
        "trace": ans.trace[-20:], "error": err, "meta": getattr(q, "meta", None),
    }


_FULL_SHARES: dict[str, float] | None = None


def full_shares() -> dict[str, float]:
    """Share of each scored source/type bucket among scored questions of the FULL dataset (S0 D1)."""
    global _FULL_SHARES
    if _FULL_SHARES is None:
        from stoa.data import load_questions

        c = collections.Counter(f"{q.source}/{q.type}" for q in load_questions() if q.type in SCORED_TYPES)
        n = sum(c.values())
        _FULL_SHARES = {k: v / n for k, v in c.items()}
    return _FULL_SHARES


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _n_objects(evidence: list[dict]) -> int:
    """Located objects behind an answer: unique IFC GUIDs (a 3D element and its 2D box on a plan are one
    object, as the UI groups them) plus boxes without a GUID (one per counted symbol/room)."""
    guids = {e["ifc_guid"] for e in evidence if e.get("ifc_guid")}
    return len(guids) + sum(1 for e in evidence if e.get("bbox") and not e.get("ifc_guid"))


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
            # located on a drawing (bbox) — what the UI can highlight in 2D; ifc_guid-only evidence is 3D only
            "evidence_2d_rate": (round(sum(1 for r in answered if any(e.get("bbox") for e in r["evidence"] or []))
                                       / len(answered), 4) if answered else None),
        }
        # verifiability of counts: the number of located objects equals the answer
        cnt = [r for r in answered if r["type"] == "count" and r["evidence"] and _num(r["value"]) is not None]
        if cnt:
            d["evidence_count_match"] = round(sum(1 for r in cnt if _n_objects(r["evidence"]) == round(_num(r["value"])))
                                              / len(cnt), 4)
            d["evidence_count_n"] = len(cnt)
        d["refusal_rate"] = round(1 - d["coverage"], 4) if rows else None
        if text:
            d["text_n"] = len(text)
            d["text_fuzzy"] = round(sum(1 for r in text if r["text_fuzzy"]) / len(text), 4)
            judged = [r for r in text if r.get("text_judge") is not None]
            if judged:
                d["text_judge"] = round(sum(1 for r in judged if r["text_judge"]) / len(judged), 4)
                d["text_judged_n"] = len(judged)
        if rows and "cost" in rows[0]:
            d["usd_per_q"] = round(statistics.fmean(cost_usd(r["cost"]) for r in rows), 6)
        return d

    out = block(preds)
    buckets = collections.defaultdict(list)
    for r in preds:
        buckets[f"{r['source']}/{r['type']}"].append(r)
    out["by_bucket"] = {k: block(v) for k, v in sorted(buckets.items())}
    accs = [b["accuracy"] for b in out["by_bucket"].values() if b["accuracy"] is not None]
    out["macro_accuracy"] = round(sum(accs) / len(accs), 4) if accs else None
    # weighted_acc: bucket accuracies weighted by the bucket's share of the FULL dataset (renormalised over
    # the buckets present in this run). Estimates accuracy on a test drawn like the full data. Not
    # meaningful for generated splits (hard), where buckets mix kinds.
    shares = full_shares()
    wb = {k: b["accuracy"] for k, b in out["by_bucket"].items() if b["accuracy"] is not None and k in shares}
    tot = sum(shares[k] for k in wb)
    out["weighted_acc"] = round(sum(shares[k] * a for k, a in wb.items()) / tot, 4) if tot else None
    # generated splits (hard): accuracy per kind (translation / paraphrase / composition) and recipe
    if any(r.get("meta") for r in preds):
        kinds, recipes = collections.defaultdict(list), collections.defaultdict(list)
        for r in preds:
            meta = r.get("meta") or {}
            kinds[meta.get("kind", "?")].append(r)
            recipes[f"{meta.get('kind', '?')}/{r['source']}/{meta.get('recipe', '?')}"].append(r)
        out["by_kind"] = {k: block(v) for k, v in sorted(kinds.items())}
        out["by_recipe"] = {k: {x: block(v)[x] for x in ("n", "accuracy", "text_fuzzy") if x in block(v)}
                            for k, v in sorted(recipes.items())}
    # cost
    if preds and "cost" in preds[0]:
        for r in preds:  # re-cost stored rows with the current policy (old runs: queueing-inflated GPU time)
            r["cost"] = {**r["cost"], "usd": round(cost_usd(r["cost"]), 7)}
        keys = ("llm_tokens_in", "llm_tokens_out", "api_tokens_in", "api_tokens_out", "llm_calls", "api_calls",
                "gpu_seconds", "wall_seconds", "usd")
        out["cost_mean"] = {k: round(statistics.fmean(r["cost"].get(k, 0) for r in preds), 6) for k in keys}
        out["usd_per_1k_q"] = round(1000 * out["cost_mean"]["usd"], 4)
        tiers = collections.defaultdict(list)
        for r in preds:
            tiers[r["tier"]].append(r)
        out["by_tier"] = {t: {"share": round(len(v) / len(preds), 4), **{k: block(v)[k] for k in ("n", "accuracy", "coverage")}}
                          for t, v in sorted(tiers.items())}
    # calibration of Answer.confidence (Stoa: "know what you don't know"); bins stay in the predictions tools
    from stoa.eval.calibration import calibration

    cal = calibration(preds)
    if cal:
        out["calibration"] = {k: v for k, v in cal.items() if k != "bins"}
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
    if m.get("text_judge") is not None:
        print(f"text (LLM judge, not in accuracy): {pct(m['text_judge'])} of {m['text_judged_n']} judged; per bucket: "
              + ", ".join(f"{k} {pct(b['text_judge'])}" for k, b in m["by_bucket"].items() if b.get("text_judge") is not None),
              file=file)
    if m.get("evidence_rate") is not None:
        print(f"evidence: {pct(m['evidence_rate']).strip()}% of answers, located in 2D {pct(m.get('evidence_2d_rate')).strip()}%"
              + (f"; counts whose located items = the answer: {pct(m['evidence_count_match']).strip()}% of "
                 f"{m['evidence_count_n']}" if m.get("evidence_count_match") is not None else ""), file=file)
    print(f"weighted_acc (full-data bucket shares): {pct(m.get('weighted_acc'))}   macro: {pct(m['macro_accuracy'])}   "
          f"refusal: {pct(m.get('refusal_rate'))}   errors: {m['errors']}", file=file)
    cm = m.get("cost_mean") or {}
    print(f"cost/question: ${cm.get('usd', 0):.6f} (${m.get('usd_per_1k_q', 0):.3f} per 1k)  tokens in/out "
          f"{cm.get('llm_tokens_in', 0):.0f}/{cm.get('llm_tokens_out', 0):.0f}  llm calls {cm.get('llm_calls', 0):.2f}  "
          f"api calls {cm.get('api_calls', 0):.2f}  gpu s {cm.get('gpu_seconds', 0):.2f}  wall s mean/p50/p95 "
          f"{m.get('latency_mean_s')}/{m.get('latency_p50_s')}/{m.get('latency_p95_s')}", file=file)
    cal = m.get("calibration")
    if cal:
        print(f"calibration: ECE {cal['ece']:.3f}  Brier {cal['brier']:.3f}  AUROC "
              f"{'-' if cal['auroc'] is None else format(cal['auroc'], '.3f')}  AURC {cal['aurc']:.3f} (excess {cal['e_aurc']:.3f})  "
              f"conf>=0.8 on {100 * cal['hi_conf_share']:.0f}% of answers"
              + (f", {pct(cal['hi_conf_acc']).strip()}% of them right" if cal["hi_conf_acc"] is not None else ""), file=file)
    if m.get("by_kind"):
        print("hard kinds: " + "  ".join(f"{k}: n={v['n']} acc {pct(v['accuracy'])} text~ {pct(v.get('text_fuzzy'))}"
                                         for k, v in m["by_kind"].items()), file=file)
    if m.get("by_tier"):
        print("tiers: " + "  ".join(f"{t}: {100 * v['share']:.0f}% of Qs, acc {pct(v['accuracy'])}"
                                    for t, v in m["by_tier"].items()), file=file)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m stoa.eval", description=__doc__)
    ap.add_argument("--solver", required=True, help="registered solver name (see --list)")
    ap.add_argument("--split", default="smoke", help="smoke | dev | test | train | all")
    ap.add_argument("--limit", type=int, default=None, help="fixed random subset of N questions (same every run)")
    ap.add_argument("--source", action="append", default=None, help="filter by source; repeat or comma-separate")
    ap.add_argument("--type", action="append", default=None, help="filter by type (count, area, ...)")
    ap.add_argument("--grep", default=None, help="only questions matching this regex (case-insensitive), e.g. "
                    "'windows|ikkun|fenster|fönster' to iterate on one concept in any language")
    ap.add_argument("--workers", type=int, default=4, help="parallel threads calling solver.solve")
    ap.add_argument("--solver-arg", action="append", default=[], help="key=value passed to the solver constructor")
    ap.add_argument("--handled-only", action="store_true", help="abstain without calling solve() when can_handle is False")
    ap.add_argument("--note", default="", help="free text stored in the leaderboard line")
    ap.add_argument("--no-leaderboard", action="store_true", help="don't append to results/leaderboard.jsonl")
    ap.add_argument("--allow-test", action="store_true", help="required for --split test (S0 only)")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--judge", default="none", choices=("none", "local", "nvidia"),
                    help="grade text/other answers with an LLM judge (reported as text_judge; not in accuracy)")
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

    qs = select(load_split(a.split), sources, types, a.limit, grep=a.grep)
    if not qs:
        print("no questions selected", file=sys.stderr)
        return 2
    # unique even for runs started in the same second (R2 00:00): random suffix + exclusive create below
    split_tag = Path(a.split).stem if a.split.endswith(".jsonl") else a.split
    run_id = (f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{a.solver}-{split_tag}" + (f"-n{len(qs)}" if a.limit else "")
              + f"-{os.urandom(2).hex()}")
    out_dir = shared_root() / "artifacts" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    preds_path = out_dir / f"{run_id}.jsonl"

    try:
        from tqdm import tqdm
    except ImportError:  # pragma: no cover
        tqdm = None
    preds: list[dict] = []
    t0 = time.time()
    with open(preds_path, "x", encoding="utf-8") as fout, cf.ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
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
    if a.judge != "none" and any(r["type"] in ("text", "other") for r in preds):
        from stoa.eval.judge import judge_rows

        judge_rows(preds, a.judge, workers=a.workers)
        with open(preds_path, "w", encoding="utf-8") as fout:  # rewrite with verdicts
            for r in preds:
                fout.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    m = summarize(preds)
    m["wall_s"] = round(wall, 1)
    print_report(m)
    status = _git("status", "--porcelain", "--untracked-files=no")
    from stoa.eval.splits import split_hash
    line = {
        "time": datetime.now().isoformat(timespec="seconds"), "run_id": run_id, "solver": a.solver,
        "solver_args": kwargs, "split": a.split, "split_hash": split_hash(a.split), "limit": a.limit, "sources": sorted(sources) or None,
        "types": sorted(types) or None, "grep": a.grep, "handled_only": a.handled_only, "judge": a.judge, "n": len(qs),
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
