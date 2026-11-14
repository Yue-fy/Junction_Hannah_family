"""Analyse a pipeline run over redteam/questions.jsonl.

    python3 redteam/analyze.py $JUNCTION_SHARED/artifacts/eval/<run>.jsonl [--md out.md]

Reports, per kind: accuracy (eval scorer, which converts units), strict accuracy (the number is in the unit the
question asked for), confidence, confidently-wrong answers; paraphrase/perturbation flips against the control row of
the same base question; how false-premise / unanswerable questions were handled; risk-coverage over every row
(false-premise and unanswerable rows count as wrong when answered: a number there is a guess).
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict

UNIT_ALIASES = {"m2": {"m2", "m²", "sqm"}, "cm2": {"cm2", "cm²"}, "ft2": {"ft2", "ft²", "sf", "sq ft", "sqft"},
                "mm": {"mm"}, "m": {"m"}, "count": {"count", None, ""}}
FLAG_WORDS = re.compile(r"not found|no (such|room|storey|level|space|scale|data)|does not exist|doesn't exist|"
                        r"unknown|not (in|on|shown|available|given|present|listed)|cannot|can't|missing|assum|"
                        r"no .* (named|called|labelled)|not stated", re.I)


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def same_value(a, b, typ):
    x, y = num(a), num(b)
    if x is None or y is None:
        return str(a).strip().lower() == str(b).strip().lower()
    if typ == "count":
        return round(x) == round(y)
    return abs(x - y) <= 0.02 * max(abs(y), 1e-9)


def strict_ok(r):
    if not r["correct"]:
        return False
    gu = r.get("gold_unit")
    if gu in (None, "count"):
        return True
    return (r.get("unit") or "").strip().lower() in UNIT_ALIASES.get(gu, {gu})


def handled_flag(r):
    """A false-premise / unanswerable row is handled well when the answer is unsure AND says why."""
    c = r["confidence"] or 0
    text = " ".join(map(str, (r.get("missing") or []) + (r.get("assumptions") or [])))
    return c < 0.5 and bool(r.get("missing") or FLAG_WORDS.search(text))


def risk_coverage(rows):
    """rows: (confidence, ok). Returns AURC and accuracy at fixed coverages."""
    rows = sorted(rows, key=lambda t: -t[0])
    n = len(rows)
    cum, aurc, pts = 0, 0.0, {}
    for i, (_, ok) in enumerate(rows, 1):
        cum += ok
        aurc += 1 - cum / i
        for cov in (0.2, 0.4, 0.6, 0.8, 1.0):
            if i == max(1, round(cov * n)):
                pts[cov] = cum / i
    return aurc / max(n, 1), pts


def ece(rows, bins=10):
    b = defaultdict(list)
    for c, ok in rows:
        b[min(int(c * bins), bins - 1)].append((c, ok))
    n = len(rows)
    return sum(len(v) / n * abs(sum(c for c, _ in v) / len(v) - sum(o for _, o in v) / len(v)) for v in b.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--md", default=None)
    ap.add_argument("--rerun", default=None, help="another run over the same questions: report answer changes")
    a = ap.parse_args()
    rows = [json.loads(line) for line in open(a.run)]
    out = []
    p = out.append

    by = defaultdict(list)
    for r in rows:
        by[(r.get("meta") or {}).get("kind", "?")].append(r)

    p("| kind | n | acc (scorer) | strict acc | mean conf | conf≥0.8 | wrong at conf≥0.8 | errors |")
    p("|---|---:|---:|---:|---:|---:|---:|---:|")
    order = sorted(by, key=lambda k: (k.split(":")[0], k))
    for k in order:
        v = by[k]
        sc = [r for r in v if r["correct"] is not None]
        acc = sum(r["correct"] for r in sc) / len(sc) if sc else None
        sacc = sum(strict_ok(r) for r in sc) / len(sc) if sc else None
        hi = [r for r in v if (r["confidence"] or 0) >= 0.8]
        if (v[0].get("meta") or {}).get("expect") == "flag":
            wrong_hi = len(hi)
        else:
            wrong_hi = sum(1 for r in hi if r["correct"] is False)
        mc = sum((r["confidence"] or 0) for r in v) / len(v)
        f = lambda x: "—" if x is None else f"{100 * x:.0f}%"
        p(f"| {k} | {len(v)} | {f(acc)} | {f(sacc)} | {mc:.2f} | {len(hi)} | {wrong_hi} | "
          f"{sum(1 for r in v if r.get('error'))} |")

    # perturbation flips vs the control row of the same base question
    ctrl = {(r["meta"] or {}).get("base_qid"): r for r in rows if (r.get("meta") or {}).get("kind") == "control"}
    flips = defaultdict(lambda: [0, 0, 0])  # kind -> [n, flipped, flipped-and-confident]
    flip_rows = []
    for r in rows:
        m = r.get("meta") or {}
        if not m.get("kind", "").startswith(("perturb", "image")):
            continue
        c = ctrl.get(m.get("base_qid"))
        if c is None:
            continue
        k = m["kind"]
        flips[k][0] += 1
        if not same_value(r["value"], c["value"], r["type"]):
            flips[k][1] += 1
            if (r["confidence"] or 0) >= 0.8:
                flips[k][2] += 1
            flip_rows.append((k, c, r))
    p("")
    p("Answer changed vs the unperturbed control (same drawing, same meaning):")
    p("")
    p("| perturbation | n | answer changed | changed at conf≥0.8 |")
    p("|---|---:|---:|---:|")
    for k in sorted(flips):
        n, f_, fc = flips[k]
        p(f"| {k} | {n} | {f_} | {fc} |")

    # false premise / unanswerable
    p("")
    p("False-premise and unanswerable questions (handled = conf < 0.5 and says what is missing):")
    p("")
    p("| kind | question | value | conf | handled | solver | missing / assumptions (first) |")
    p("|---|---|---|---:|---|---|---|")
    for r in rows:
        m = r.get("meta") or {}
        if m.get("expect") != "flag":
            continue
        why = ((r.get("missing") or []) + (r.get("assumptions") or []) + [""])[0]
        p(f"| {m['kind']} | {r['question'][:90]} | {str(r['value'])[:40]} | {r['confidence'] or 0:.2f} | "
          f"{'yes' if handled_flag(r) else '**NO**'} | {r['solver']} | {str(why)[:110]} |")

    # risk-coverage
    rc = []
    for r in rows:
        m = r.get("meta") or {}
        if m.get("expect") == "flag":
            rc.append(((r["confidence"] or 0), 0))
        elif r["correct"] is not None:
            rc.append(((r["confidence"] or 0), int(bool(r["correct"]))))
    aurc, pts = risk_coverage(rc)
    oracle = sorted([o for _, o in rc], reverse=True)
    oaurc, _ = risk_coverage([(1 - i / len(oracle), o) for i, o in enumerate(oracle)])
    p("")
    p(f"Risk-coverage over {len(rc)} rows (flag rows count as wrong): AURC {aurc:.3f} (oracle {oaurc:.3f}), "
      f"ECE {ece(rc):.3f}, accuracy at coverage " + ", ".join(f"{int(100 * k)}%: {100 * v:.0f}%" for k, v in pts.items()))

    # confidently wrong list
    p("")
    p("Confidently wrong (conf ≥ 0.8; flag rows: any answer at conf ≥ 0.8):")
    p("")
    for r in rows:
        m = r.get("meta") or {}
        bad = (m.get("expect") == "flag" and (r["confidence"] or 0) >= 0.8) or (
            r["correct"] is False and (r["confidence"] or 0) >= 0.8)
        if bad:
            p(f"- [{m.get('kind')}] {r['path'].split('/')[-1][:50]} — \"{r['question'][:110]}\" → {r['value']} "
              f"{r['unit'] or ''} (gold {r['gold']}) conf {r['confidence']:.2f} via {r['solver']}")
    p("")
    p("Answer changes under perturbation (control → variant):")
    p("")
    for k, c, r in flip_rows:
        p(f"- [{k}] {r['path'].split('/')[-1][:45]}: {c['value']} ({c['confidence'] or 0:.2f}, {c['solver']}) → "
          f"{r['value']} ({r['confidence'] or 0:.2f}, {r['solver']}); gold {r['gold']}")
    if a.rerun:  # the same questions in another run of the same code: is the pipeline deterministic?
        other = {r["qid"]: r for r in map(json.loads, open(a.rerun))}
        both = [(r, other[r["qid"]]) for r in rows if r["qid"] in other]
        changed = [(x, y) for x, y in both if not same_value(x["value"], y["value"], x["type"])]
        dconf = [abs((x["confidence"] or 0) - (y["confidence"] or 0)) for x, y in both]
        p("")
        p(f"Run-to-run (same question, same code, other run {a.rerun.split('/')[-1]}): {len(both)} shared questions, "
          f"answer changed on {len(changed)}, confidence moved > 0.05 on {sum(d > 0.05 for d in dconf)}, "
          f"solver changed on {sum(x['solver'] != y['solver'] for x, y in both)}.")
        for x, y in changed:
            p(f"- [{(x.get('meta') or {}).get('kind')}] {x['question'][:80]}: {y['value']} ({y['confidence'] or 0:.2f}, "
              f"{y['solver']}) → {x['value']} ({x['confidence'] or 0:.2f}, {x['solver']}); gold {x['gold']}")
    txt = "\n".join(out)
    print(txt)
    if a.md:
        open(a.md, "w").write(txt + "\n")


if __name__ == "__main__":
    main()
