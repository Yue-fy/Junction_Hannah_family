"""Per-concept accuracy of several eval runs on the questions they share (owner: R2).

    $JUNCTION_VENV/bin/python experiments/r2/compare_runs.py RUN_A RUN_B [RUN_C ...] [--source cubicasa5k]

RUN = a run_id (prefix ok) or a predictions .jsonl path. Concepts pool a template with its translations
(stoa.data.concept_map) when available. Prints n, accuracy per run, and mean tokens/GPU-s/API calls per run.
A row with no gold and no judge verdict (e.g. Stoa's noon examples without answers) is NOT scored: the cell shows
"-" (or the accuracy over the scored rows with their count). --show prints every question with each run's answer.
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from stoa.eval.analyze import load, resolve  # noqa: E402


def concept_of(template: str) -> str:
    try:
        from stoa.data import concept_map

        return concept_map().get(template, template)
    except Exception:  # noqa: BLE001
        return template


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--source", default=None)
    ap.add_argument("--show", action="store_true", help="print each question with gold and every run's value @ confidence")
    ap.add_argument("--by", default="concept", choices=["concept", "kind", "type", "source"],
                    help="group rows by dataset concept (default), meta.kind (probe/Stoa example kinds), type or source")
    a = ap.parse_args()
    runs = []
    for r in a.runs:
        p = Path(r) if Path(r).exists() else resolve(r)
        if not p.exists():  # run_id prefix (run ids end in a random suffix)
            hits = sorted(p.parent.glob(Path(r).name.removesuffix(".jsonl") + "*.jsonl"))
            hits = [h for h in hits if not h.name.endswith(".judged.jsonl")]
            if not hits:
                sys.exit(f"no predictions file for {r}")
            p = hits[-1]
        rows = {x["qid"]: x for x in load(str(p)) if not a.source or x["source"] == a.source}
        runs.append((Path(p).stem[-40:], rows))
    common = set.intersection(*(set(r) for _, r in runs))
    print(f"{len(common)} shared questions (score = exact/2% when gold is a number, else the LLM judge's verdict)")
    by = collections.defaultdict(list)
    for q in common:
        r0 = runs[0][1][q]
        key = {"concept": lambda: concept_of(r0.get("template") or ""), "kind": lambda: str((r0.get("meta") or {}).get(
            "kind") or r0.get("type")), "type": lambda: str(r0.get("type")), "source": lambda: str(r0.get("source"))}[a.by]()
        by[key].append(q)
    hdr = "  ".join(f"{name[-22:]:>22}" for name, _ in runs)
    print(f"{'n':>4}  {hdr}  {a.by}")

    def score(row):  # True / False, or None = not scorable (no gold, no judge verdict)
        if row.get("correct") is not None:
            return bool(row["correct"])
        return None if row.get("text_judge") is None else bool(row["text_judge"])

    def cell(vals):
        sc = [v for v in vals if v is not None]
        if not sc:
            return f"{'-':>22}"
        if len(sc) == len(vals):
            return f"{100 * sum(sc) / len(sc):22.1f}"
        return f"{f'{100 * sum(sc) / len(sc):.1f} of {len(sc)}':>22}"

    allv = [[] for _ in runs]
    for c, qs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        accs = []
        for i, (_, rows) in enumerate(runs):
            vals = [score(rows[q]) for q in qs]
            allv[i] += vals
            accs.append(cell(vals))
        print(f"{len(qs):4d}  {'  '.join(accs)}  {c[:70]}")
    print(f"{len(common):4d}  " + "  ".join(cell(v) for v in allv) + "  ALL")
    if a.show:
        for q in sorted(common, key=lambda q: (str((runs[0][1][q].get("meta") or {}).get("kind")), q)):
            r0 = runs[0][1][q]
            print(f"\n[{(r0.get('meta') or {}).get('kind')}] {r0['question'][:160]}\n    file {r0['path']}  gold {r0.get('gold')}")
            for name, rows in runs:
                r = rows[q]
                v = str(r.get("value"))[:100].replace("\n", " ")
                print(f"    {name[-22:]:>22}: {v} {r.get('unit') or ''} @ {r.get('confidence')}  ({r.get('solver')})"
                      + ("" if score(r) is None else (" ✓" if score(r) else " ✗")))
    for name, rows in runs:
        cs = [rows[q].get("cost") or {} for q in common]
        if cs and cs[0]:
            m = {k: statistics.fmean(c.get(k, 0) or 0 for c in cs) for k in
                 ("llm_tokens_in", "llm_tokens_out", "gpu_seconds", "api_calls")}
            print(f"cost {name[-30:]}: " + ", ".join(f"{k}={v:.3g}" for k, v in m.items()))


if __name__ == "__main__":
    main()
