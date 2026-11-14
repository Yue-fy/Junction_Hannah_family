"""Readable per-question review of one eval run, for questions WITHOUT gold (Stoa's example questions, ad-hoc files)
or with it. One markdown section per question: answer, confidence, solver, evidence (located or not), assumptions,
what is missing, cost and time, plus the last trace lines. Meant for a human deciding in minutes whether answers
look right (Stoa's noon examples: `--split stoa_examples.jsonl` rows with path + question, no answer).

    python -m stoa.eval.review artifacts/eval/<run>.jsonl [--out review.md] [--trace 4] [--only-low 0.8]
Never use it on sealed splits (test, hard2r, hard3, hardL): it prints questions.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

SEALED_HINTS = ("-test-", "-hard2r-", "-hard3-", "-hardL-", "-hardL_fe-", "-hard2q-", "-hard2p-")


def _fmt_val(r: dict) -> str:
    v = r.get("value")
    if v is None:
        return "— (no answer)"
    if isinstance(v, float):
        v = f"{v:.3f}".rstrip("0").rstrip(".")
    s = str(v)
    return (s[:300] + "…") if len(s) > 300 else s + (f" {r['unit']}" if r.get("unit") and r["unit"] != "count" else "")


def review(rows: list[dict], trace: int = 4, only_low: float | None = None) -> str:
    out = []
    n = len(rows)
    confs = [r.get("confidence") or 0 for r in rows]
    located = sum(any(e.get("bbox") or e.get("ifc_guid") for e in (r.get("evidence") or [])) for r in rows)
    scored = [r for r in rows if r.get("correct") is not None]
    cost = [((r.get("cost") or {}).get("usd") or 0) for r in rows]
    out.append(f"# Review: {n} questions\n")
    out.append(f"- answered: {sum(r.get('value') is not None for r in rows)}/{n}; confidence ≥ 0.8: "
               f"{sum(c >= 0.8 for c in confs)}; < 0.5: {sum(c < 0.5 for c in confs)}; evidence located (box or IFC "
               f"element): {located}/{n}")
    if scored:
        out.append(f"- scored against gold: {sum(bool(r['correct']) for r in scored)}/{len(scored)} right")
    out.append(f"- mean cost ${statistics.fmean(cost) * 1000:.3f} per 1k questions; mean wall "
               f"{statistics.fmean([r.get('latency_s') or 0 for r in rows]):.1f} s\n")
    for i, r in enumerate(rows, 1):
        c = r.get("confidence") or 0
        if only_low is not None and c >= only_low:
            continue
        ev = r.get("evidence") or []
        loc = [e for e in ev if e.get("bbox") or e.get("ifc_guid")]
        out.append(f"## {i}. {Path(r['path']).name}: {r['question']}\n")
        gold = "" if r.get("correct") is None else (f"  · gold {r.get('gold')} → {'RIGHT' if r['correct'] else 'WRONG'}")
        out.append(f"**{_fmt_val(r)}**  · conf {c:.2f} · {r.get('solver', '?')} · tier {r.get('tier', '?')}{gold}\n")
        out.append(f"- evidence: {len(ev)} item(s), {len(loc)} located"
                   + (f"; e.g. {loc[0].get('file', '')} p{loc[0].get('page')} {loc[0].get('note', '')[:120]}" if loc else ""))
        for a in (r.get("assumptions") or [])[:3]:
            out.append(f"- assumes: {a[:200]}")
        for m in (r.get("missing") or [])[:3]:
            out.append(f"- missing: {m[:200]}")
        k = r.get("cost") or {}
        out.append(f"- cost: {k.get('llm_calls', 0)} LLM calls, {k.get('llm_tokens_in', 0)}+{k.get('llm_tokens_out', 0)} tokens, "
                   f"{k.get('api_calls', 0)} hosted calls, {r.get('latency_s') or 0:.1f} s")
        if r.get("error"):
            out.append(f"- ERROR: {str(r['error'])[:200]}")
        if trace:
            out.append("- trace: " + " ⏵ ".join(t[:140] for t in (r.get("trace") or [])[-trace:]))
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m stoa.eval.review", description=__doc__)
    ap.add_argument("run", help="predictions .jsonl (artifacts/eval/<run>.jsonl)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--trace", type=int, default=4)
    ap.add_argument("--only-low", type=float, default=None, help="only questions with confidence below this")
    a = ap.parse_args(argv)
    if any(h in Path(a.run).name for h in SEALED_HINTS):
        raise SystemExit("refusing: this run is on a sealed/held-out split (it would print its questions)")
    rows = [json.loads(line) for line in open(a.run, encoding="utf-8") if line.strip()]
    md = review(rows, a.trace, a.only_low)
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
        print(f"wrote {a.out} ({len(rows)} questions)")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
