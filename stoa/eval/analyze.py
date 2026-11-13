"""Error analysis of an eval run: where are the points lost, and why?

    python -m stoa.eval.analyze RUN [--baseline RUN_B] [--top 15] [--examples 4] [--out file.md]

RUN is a predictions file from `python -m stoa.eval` or its run id (artifacts/eval/<run_id>.jsonl).
Without --baseline, the newest dummy run on the same split is used (if any).

Prints markdown:
1. headline: micro accuracy with a cluster-bootstrap 95% CI (resampling drawings), weighted_acc, refusals, cost
2. loss table: source x type x template ranked by weighted points lost (bucket share in the FULL dataset x
   wrong / bucket size), with the baseline's accuracy on the same questions and the error pattern
3. error types per bucket (refusal, exception, over/under-count, off-by-one, unit, area ratio quantiles)
4. failing examples for the top templates (question, gold, prediction, evidence, last trace lines)
5. dev oracle of "best of RUN and baseline per template" (an upper bound for gating: choose gates on TRAIN)
6. calibration: accuracy per confidence bin
For significance of a difference between two runs use experiments/r1/stats/compare.py (paired, clustered).
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import random
import statistics
from pathlib import Path

from stoa.eval.runner import SCORED_TYPES, full_shares
from stoa.eval.scoring import convert, parse_number
from stoa.eval.splits import shared_root


def resolve(run: str) -> Path:
    p = Path(run)
    if p.exists():
        return p
    return shared_root() / "artifacts" / "eval" / (run.removesuffix(".jsonl") + ".jsonl")


def load(run: str) -> list[dict]:
    with open(resolve(run), encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def find_baseline(rows: list[dict], solver: str = "dummy") -> Path | None:
    """Newest run of `solver` whose predictions cover the same qids."""
    qids = {r["qid"] for r in rows}
    d = shared_root() / "artifacts" / "eval"
    for p in sorted(d.glob(f"*-{solver}-*.jsonl"), key=os.path.getmtime, reverse=True):
        try:
            other = {json.loads(line)["qid"] for line in open(p, encoding="utf-8")}
        except Exception:  # noqa: BLE001
            continue
        if qids <= other:
            return p
    return None


def cluster_ci(rows: list[dict], n_boot: int = 1000, seed: int = 0) -> tuple[float, float]:
    by = collections.defaultdict(list)
    for r in rows:
        by[r["path"]].append(1.0 if r["correct"] else 0.0)
    keys = list(by)
    rng = random.Random(seed)
    accs = []
    for _ in range(n_boot):
        s = n = 0.0
        for k in (keys[rng.randrange(len(keys))] for _ in keys):
            s += sum(by[k])
            n += len(by[k])
        accs.append(s / n if n else 0.0)
    accs.sort()
    return accs[int(0.025 * n_boot)], accs[int(0.975 * n_boot) - 1]


def error_kind(r: dict) -> str:
    if r.get("error"):
        return "exception"
    if r["abstained"]:
        return "refusal"
    if r["correct"]:
        return "correct"
    x = parse_number(r["value"])
    g = parse_number(r["gold"])
    if x is None:
        return "unparseable"
    if r["type"] == "count":
        d = round(x) - round(g)
        if abs(d) == 1:
            return "off-by-one " + ("over" if d > 0 else "under")
        return "overcount" if d > 0 else "undercount"
    y = convert(x, r.get("unit"), r.get("gold_unit"))
    if y is None:
        return "wrong-dimension unit"
    if g:
        ratio = y / g
        if 0.85 <= ratio <= 1.15:
            return "near miss (2-15%)"
        return "too high" if ratio > 1 else "too low"
    return "wrong"


def short(s, n=110) -> str:
    s = str(s).replace("\n", " ").replace("|", "/")
    return s if len(s) <= n else s[: n - 1] + "…"


def analyze(rows: list[dict], base: list[dict] | None, top: int = 15, n_ex: int = 4, title: str = "") -> str:
    shares = full_shares()
    scored = [r for r in rows if r["type"] in SCORED_TYPES]
    bmap = {r["qid"]: r for r in (base or [])}
    out = []
    w = out.append
    n = len(scored)
    acc = sum(r["correct"] for r in scored) / n if n else 0
    lo, hi = cluster_ci(scored) if scored else (0, 0)
    bucket_rows = collections.defaultdict(list)
    for r in scored:
        bucket_rows[f"{r['source']}/{r['type']}"].append(r)
    wacc_num = sum(shares.get(b, 0) * sum(x["correct"] for x in v) / len(v) for b, v in bucket_rows.items())
    wacc_den = sum(shares.get(b, 0) for b in bucket_rows)
    refusals = sum(r["abstained"] for r in rows)
    usd = statistics.fmean(r.get("cost", {}).get("usd", 0) for r in rows) if rows else 0
    w(f"## {title}\n")
    w(f"- scored questions: {n} on {len({r['path'] for r in scored})} drawings; micro accuracy **{100*acc:.1f}%** "
      f"(95% cluster CI {100*lo:.1f}–{100*hi:.1f}); weighted_acc **{100*wacc_num/wacc_den:.1f}%**" if wacc_den else "")
    w(f"- refusals: {refusals}/{len(rows)}; exceptions: {sum(1 for r in rows if r.get('error'))}; "
      f"mean cost ${usd:.5f}/question; evidence on {sum(1 for r in rows if r.get('evidence'))}/{len(rows)} answers")
    if base:
        bs = [bmap[r["qid"]] for r in scored if r["qid"] in bmap]
        if bs:
            w(f"- baseline ({bs[0].get('solver', '?')}) on the same questions: "
              f"{100*sum(b['correct'] for b in bs)/len(bs):.1f}%")
    w("")

    # loss table by template
    tpl = collections.defaultdict(list)
    for r in scored:
        tpl[(f"{r['source']}/{r['type']}", r["template"])].append(r)
    table = []
    for (b, t), v in tpl.items():
        wrong = [r for r in v if not r["correct"]]
        pts = 100 * shares.get(b, 0) / max(1e-9, wacc_den) * len(wrong) / len(bucket_rows[b])
        kinds = collections.Counter(error_kind(r) for r in wrong)
        b_acc = None
        bv = [bmap[r["qid"]] for r in v if r["qid"] in bmap]
        if bv:
            b_acc = sum(x["correct"] for x in bv) / len(bv)
        table.append((pts, b, t, v, wrong, kinds, b_acc))
    table.sort(key=lambda x: -x[0])
    total_wrong = sum(len(x[4]) for x in table) or 1
    w("### Where points are lost (ranked by weighted_acc points lost)\n")
    w("| # | bucket | template | n | acc | baseline acc | lost | % of lost Qs | w-pts lost | main error types |")
    w("|---|---|---|---:|---:|---:|---:|---:|---:|---|")
    for i, (pts, b, t, v, wrong, kinds, b_acc) in enumerate(table[:top], 1):
        a = 100 * (len(v) - len(wrong)) / len(v)
        ba = "-" if b_acc is None else f"{100*b_acc:.0f}%"
        ks = ", ".join(f"{k} {c}" for k, c in kinds.most_common(3))
        w(f"| {i} | {b} | {short(t, 70)} | {len(v)} | {a:.0f}% | {ba} | {len(wrong)} | "
          f"{100*len(wrong)/total_wrong:.1f}% | {pts:.2f} | {ks} |")
    w("")

    # error types per bucket
    w("### Error types per bucket\n")
    w("| bucket | n | acc | error types (count) | pred/gold ratio p10/p50/p90 (wrong numeric) |")
    w("|---|---:|---:|---|---|")
    for b, v in sorted(bucket_rows.items()):
        wrong = [r for r in v if not r["correct"]]
        kinds = collections.Counter(error_kind(r) for r in wrong)
        ratios = []
        for r in wrong:
            x, g = parse_number(r["value"]), parse_number(r["gold"])
            if x is not None and g:
                y = convert(x, r.get("unit"), r.get("gold_unit"))
                if y is not None:
                    ratios.append(y / g)
        ratios.sort()
        rq = (f"{ratios[len(ratios)//10]:.2f} / {ratios[len(ratios)//2]:.2f} / {ratios[min(len(ratios)-1, 9*len(ratios)//10)]:.2f}"
              if ratios else "-")
        w(f"| {b} | {len(v)} | {100*(len(v)-len(wrong))/len(v):.0f}% | "
          f"{', '.join(f'{k} {c}' for k, c in kinds.most_common())} | {rq} |")
    w("")

    # examples
    w("### Failing examples (top templates)\n")
    rng = random.Random(0)
    for i, (pts, b, t, v, wrong, kinds, b_acc) in enumerate(table[: min(top, 8)], 1):
        if not wrong:
            continue
        w(f"**{i}. {b} — {short(t, 90)}** ({len(wrong)}/{len(v)} wrong)\n")
        for r in rng.sample(wrong, min(n_ex, len(wrong))):
            tr = " ⟶ ".join(short(x, 60) for x in (r.get("trace") or [])[-3:])
            w(f"- `{r['path'].split('/')[-1]}`: {short(r['question'], 90)} — gold **{short(r['gold'], 40)}**, "
              f"pred **{short(r['value'], 40)}** {r.get('unit') or ''} ({error_kind(r)}; evidence {len(r.get('evidence') or [])}; "
              f"conf {r.get('confidence')}) — trace: {tr}")
        w("")

    # oracle vs baseline per template
    if base:
        gain = 0
        lines = []
        for (b, t), v in tpl.items():
            bv = [bmap[r["qid"]] for r in v if r["qid"] in bmap]
            if len(bv) != len(v):
                continue
            a = sum(r["correct"] for r in v)
            ba = sum(x["correct"] for x in bv)
            if ba > a:
                gain += ba - a
                lines.append((ba - a, b, t, len(v), a, ba))
        lines.sort(reverse=True)
        w("### Templates where the baseline beats this run (dev oracle; choose any gating on TRAIN, not here)\n")
        w(f"Best-of-two per template would add {gain} correct answers ({100*gain/max(1,n):.1f} pts micro).\n")
        w("| bucket | template | n | this run | baseline |")
        w("|---|---|---:|---:|---:|")
        for d, b, t, nn, a, ba in lines[:12]:
            w(f"| {b} | {short(t, 80)} | {nn} | {a} | {ba} |")
        w("")

    # calibration
    confs = [r for r in scored if isinstance(r.get("confidence"), (int, float))]
    if confs and len({r["confidence"] for r in confs}) > 1:
        w("### Calibration (accuracy per confidence bin)\n")
        w("| confidence | n | accuracy |")
        w("|---|---:|---:|")
        bins = collections.defaultdict(list)
        for r in confs:
            bins[min(9, int(r["confidence"] * 10))].append(r["correct"])
        for k in sorted(bins):
            w(f"| {k/10:.1f}–{(k+1)/10:.1f} | {len(bins[k])} | {100*sum(bins[k])/len(bins[k]):.0f}% |")
        w("")
    else:
        w("_Calibration: confidence is constant in this run, so there is nothing to calibrate. "
          "Solvers should vary it (D4)._\n")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m stoa.eval.analyze", description=__doc__)
    ap.add_argument("run")
    ap.add_argument("--baseline", default=None, help="run id/path; default: newest dummy run covering the same qids")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--examples", type=int, default=4)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    rows = load(a.run)
    bpath = resolve(a.baseline) if a.baseline else find_baseline(rows)
    base = load(str(bpath)) if bpath else None
    md = analyze(rows, base, a.top, a.examples, title=f"{resolve(a.run).stem} (baseline: {bpath.stem if bpath else 'none'})")
    if a.out:
        Path(a.out).write_text(md + "\n", encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
