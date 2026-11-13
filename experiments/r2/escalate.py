"""Cascade check: on questions where the local 8B is unsure, is hosted Nemotron better? (owner: R2)

1) select: from a vlm_direct predictions file run with conf=logprob, write the qids whose confidence is below a
   threshold (optionally one source, a fixed random sample) as an eval split file:
     $JUNCTION_VENV/bin/python experiments/r2/escalate.py select RUN --below 0.4 --source cubicasa5k --n 80 \
         --out $JUNCTION_SHARED/artifacts/R2/escalate_low.jsonl
2) run Nemotron on that file with the eval tool (`--split <file> --solver vlm_direct --solver-arg backend=nvidia`)
3) report: accuracy of local vs Nemotron on the selected questions, and the cascade's overall accuracy and API
   share for every threshold, assuming Nemotron's accuracy on the sample holds below the threshold:
     $JUNCTION_VENV/bin/python experiments/r2/escalate.py report LOCAL_RUN NEMOTRON_RUN
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from stoa.eval.analyze import load, resolve  # noqa: E402


def _rows(run: str) -> list[dict]:
    p = Path(run) if Path(run).exists() else resolve(run)
    if not p.exists():
        hits = sorted(x for x in p.parent.glob(Path(run).name + "*.jsonl") if not x.name.endswith(".judged.jsonl"))
        p = hits[-1]
    return load(str(p))


def select(a) -> None:
    rows = [r for r in _rows(a.run) if r.get("value") is not None and r.get("correct") is not None
            and (not a.source or r["source"] == a.source) and r["confidence"] < a.below]
    random.Random(0).shuffle(rows)
    rows = rows[: a.n]
    with open(a.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({"qid": r["qid"], "path": r["path"], "type": r["type"], "source": r["source"]}) + "\n")
    acc = sum(r["correct"] for r in rows) / max(1, len(rows))
    print(f"wrote {len(rows)} qids (conf < {a.below}), local accuracy on them {acc:.3f} -> {a.out}")


def report(a) -> None:
    loc = {r["qid"]: r for r in _rows(a.local)}
    nem = {r["qid"]: r for r in _rows(a.nemotron)}
    common = [q for q in nem if q in loc and loc[q].get("correct") is not None]
    lc = sum(bool(loc[q]["correct"]) for q in common)
    nc = sum(bool(nem[q]["correct"]) for q in common)
    both = sum(bool(loc[q]["correct"]) and bool(nem[q]["correct"]) for q in common)
    print(f"{len(common)} escalated questions: local {lc / len(common):.3f}, Nemotron {nc / len(common):.3f} "
          f"(both right {both}, only local {lc - both}, only Nemotron {nc - both})")
    usd = [nem[q].get("cost", {}).get("usd") or 0 for q in common]
    print(f"Nemotron mean cost {sum(usd) / len(usd) * 1000:.2f} $/1k, mean latency "
          f"{sum(nem[q].get('latency_s') or 0 for q in common) / len(common):.1f} s")
    gain = (nc - lc) / len(common)  # accuracy change per escalated question (on the sample)
    allr = [r for r in loc.values() if r.get("correct") is not None and r.get("value") is not None
            and (not a.source or r["source"] == a.source)]
    base = sum(bool(r["correct"]) for r in allr) / len(allr)
    print(f"local alone on {len(allr)} questions: {base:.3f}")
    for t in (0.2, 0.3, 0.4, 0.5):
        share = sum(r["confidence"] < t for r in allr) / len(allr)
        print(f"  escalate conf < {t}: {share:.1%} of questions to Nemotron, est. accuracy {base + share * gain:.3f} "
              f"(assumes the sample's gain {gain:+.3f}/q holds)")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    s.add_argument("run")
    s.add_argument("--below", type=float, default=0.4)
    s.add_argument("--source")
    s.add_argument("--n", type=int, default=80)
    s.add_argument("--out", required=True)
    r = sub.add_parser("report")
    r.add_argument("local")
    r.add_argument("nemotron")
    r.add_argument("--source")
    a = ap.parse_args()
    (select if a.cmd == "select" else report)(a)


if __name__ == "__main__":
    main()
