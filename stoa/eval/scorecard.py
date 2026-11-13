"""One-page scorecard of a solver for the pitch/README: what Stoa scores, side by side with a baseline.

Stoa (13 Nov) scores accuracy, the reasoning (verifiable evidence, stated assumptions, calibrated
confidence), the interface, and cost. This prints all the measurable parts as markdown:

    python -m stoa.eval.scorecard DEV_RUN [--hard HARD_RUN] [--text TEXT_RUN] [--baseline RUN] [--out file.md]

DEV_RUN / HARD_RUN are predictions files or run ids (artifacts/eval/<run>.jsonl). TEXT_RUN is a run whose
text answers were judged (`--judge local` or `python -m stoa.eval.judge RUN` -> <run>.judged.jsonl); the
DEV_RUN itself is used when it carries verdicts. --baseline defaults to the newest prior/dummy run that
covers the same questions.
"""
from __future__ import annotations

import argparse
import collections
import sys

from stoa.eval.analyze import cluster_ci, find_baseline, load, resolve
from stoa.eval.runner import SCORED_TYPES, summarize


def _pct(x, d=1):
    return "–" if x is None else f"{100 * x:.{d}f}%"


def _metrics(rows: list[dict]) -> dict:
    m = summarize(rows)
    scored = [r for r in rows if r["type"] in SCORED_TYPES]
    m["ci"] = cluster_ci(scored) if scored else (None, None)
    m["assumption_rate"] = (sum(1 for r in rows if r.get("assumptions")) / len(rows)) if rows else None
    m["missing_rate"] = (sum(1 for r in rows if r.get("missing")) / len(rows)) if rows else None
    return m


def _text(rows: list[dict]) -> tuple[int, float | None]:
    j = [r for r in rows if r["type"] not in SCORED_TYPES and r.get("text_judge") is not None]
    return len(j), (sum(1 for r in j if r["text_judge"]) / len(j) if j else None)


def scorecard(dev: str, hard: str | None = None, text: str | None = None, baseline: str | None = None) -> str:
    rows = load(dev)
    base_path = baseline or find_baseline(rows, "prior") or find_baseline(rows, "dummy")
    base = load(str(base_path)) if base_path else None
    m = _metrics(rows)
    b = _metrics([r for r in base if r["qid"] in {x["qid"] for x in rows}]) if base else None
    solver = collections.Counter((r.get("solver") or "?").split("/")[0] for r in rows).most_common(1)[0][0]
    out = [f"## Scorecard: `{solver}` — {resolve(dev).stem}", ""]
    if base_path:
        out += [f"Baseline: `{resolve(str(base_path)).stem}`. CI = 95% cluster bootstrap over drawings.", ""]

    def row(name, f, why=""):
        out.append(f"| {name} | {f(m)} | {f(b) if b else '–'} | {why} |")

    out += ["| measure | this run | baseline | what it means |", "|---|---:|---:|---|"]
    row("weighted accuracy", lambda x: _pct(x.get("weighted_acc")), "bucket accuracies × full-dataset shares (headline)")
    row("micro accuracy [95% CI]", lambda x: f"{_pct(x['accuracy'])} [{_pct(x['ci'][0], 0)}–{_pct(x['ci'][1], 0)}]"
        if x["ci"][0] is not None else _pct(x["accuracy"]), "scored questions as sampled")
    row("refusals", lambda x: _pct(x.get("refusal_rate")), "value = null (Stoa: refusing is not useful)")
    row("answers with evidence", lambda x: _pct(x.get("evidence_rate")), "any file/box/IFC GUID")
    row("… located on a drawing", lambda x: _pct(x.get("evidence_2d_rate")), "a box the UI can highlight")
    row("counts: located objects = answer", lambda x: f"{_pct(x.get('evidence_count_match'))} of {x.get('evidence_count_n', 0)}"
        if x.get("evidence_count_match") is not None else "–", "verifiable in seconds")
    row("answers stating assumptions", lambda x: _pct(x.get("assumption_rate")), "Answer.assumptions non-empty")
    row("answers stating what is missing", lambda x: _pct(x.get("missing_rate")), "Answer.missing non-empty")
    cal = lambda x, k: (x.get("calibration") or {}).get(k)  # noqa: E731
    row("confidence ≥ 0.8: share / accuracy", lambda x: f"{_pct(cal(x, 'hi_conf_share'), 0)} / {_pct(cal(x, 'hi_conf_acc'))}"
        if x.get("calibration") else "–", "what the user sees as 'sure'")
    row("calibration error (ECE)", lambda x: f"{cal(x, 'ece'):.3f}" if x.get("calibration") else "–", "0 = confidence = accuracy")
    row("confidence ranks right above wrong (AUROC)", lambda x: f"{cal(x, 'auroc'):.2f}"
        if cal(x, "auroc") is not None else "–", "0.5 = confidence is noise")
    row("cost per 1,000 questions", lambda x: f"${x.get('usd_per_1k_q', 0):.2f}", "LLM tokens, GPU s, API calls priced (runner.RATES)")
    row("LLM calls per question", lambda x: f"{(x.get('cost_mean') or {}).get('llm_calls', 0):.2f}", "")
    row("deterministic tier (share / accuracy)", lambda x: (lambda t: f"{_pct(t.get('share'), 0)} / {_pct(t.get('accuracy'))}")(
        (x.get("by_tier") or {}).get("deterministic", {})), "no model call at all")
    row("latency p50 / p95", lambda x: f"{x.get('latency_p50_s')} s / {x.get('latency_p95_s')} s", "")
    if text:  # verdicts from a judged run of the same solver: shown per source too (matched by qid)
        verdict = {r["qid"]: r.get("text_judge") for r in load(text)}
        for r in rows:
            if r["type"] not in SCORED_TYPES and r.get("text_judge") is None and r["qid"] in verdict:
                r["text_judge"] = verdict[r["qid"]]
    tn, tacc = _text(rows)
    if tn:
        out.append(f"| text answers, LLM-judged | {_pct(tacc)} of {tn} | – | free text (ifc_bench, schedules); judge is lenient ±5 pts |")
    if hard:
        hm = summarize(load(hard))
        kinds = hm.get("by_kind") or {}
        out.append("| generality (hard): translation / paraphrase / composition | "
                   + " / ".join(_pct((kinds.get(k) or {}).get("accuracy"), 0) for k in ("translation", "paraphrase", "composition"))
                   + " | – | unseen wordings, languages, units, multi-step |")

    out += ["", "| source | n | accuracy | conf ≥ 0.8 share / acc | ECE | evidence in 2D | counts verifiable | $/1k |",
            "|---|---:|---:|---:|---:|---:|---:|---:|"]
    by_src = collections.defaultdict(list)
    for r in rows:
        by_src[r["source"]].append(r)
    for src, rs in sorted(by_src.items()):
        s = summarize(rs)
        c = s.get("calibration") or {}
        tj = _text(rs)
        acc = _pct(s["accuracy"]) if s["accuracy"] is not None else (f"text {_pct(tj[1])}" if tj[0] else "–")
        out.append(f"| {src} | {len(rs)} | {acc} | "
                   + (f"{_pct(c.get('hi_conf_share'), 0)} / {_pct(c.get('hi_conf_acc'))}" if c else "–") + " | "
                   + (f"{c['ece']:.3f}" if c else "–") + f" | {_pct(s.get('evidence_2d_rate'), 0)} | "
                   + (_pct(s.get("evidence_count_match"), 0) if s.get("evidence_count_match") is not None else "–")
                   + f" | {s.get('usd_per_1k_q', 0):.2f} |")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m stoa.eval.scorecard", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dev")
    ap.add_argument("--hard")
    ap.add_argument("--text")
    ap.add_argument("--baseline")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    md = scorecard(a.dev, a.hard, a.text, a.baseline)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)
    sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
