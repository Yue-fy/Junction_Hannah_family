"""Offline simulation of the "both readings" rule for machine-translated questions (R2/F 04:5x, W4 to wire).

The pipeline's language front end translates a question the rules can't read, answers the English version and caps the
confidence (0.9, or 0.75 with extra structure). Meanwhile dxf/ifc translate or cross-check INSIDE themselves, so the
pipeline run with translate=0 ("original reading") is already a strong second reading. Rule simulated here:
  agree (same value)   -> keep the translated answer, confidence = max(both)       [the cap is lifted only on agreement]
  disagree             -> the more confident reading, confidence capped at DIS_CAP
Inputs are two stored runs on the same split (front end on / translate=0); no model calls. Aggregates only, so it is
safe on held-out splits (hardL).

    python experiments/F/both_readings_sim.py ON_RUN.jsonl OFF_RUN.jsonl [--dis-cap 0.5] [--skip-lang en]
"""
from __future__ import annotations

import argparse
import json


def load(path):
    return {r["qid"]: r for r in (json.loads(x) for x in open(path, encoding="utf-8") if x.strip())}


def same(a, b) -> bool:
    if a is None or b is None:
        return False
    try:
        fa, fb = float(a), float(b)
        return abs(fa - fb) <= 1e-3 * max(1.0, abs(fa), abs(fb))
    except (TypeError, ValueError):
        return str(a).strip().lower() == str(b).strip().lower()


def metrics(rows):
    """rows: list of (correct: bool, conf: float)."""
    n = len(rows)
    acc = sum(c for c, _ in rows) / n
    bins = [[] for _ in range(10)]
    for c, p in rows:
        bins[min(int(p * 10), 9)].append((c, p))
    ece = sum(abs(sum(c for c, _ in b) / len(b) - sum(p for _, p in b) / len(b)) * len(b) for b in bins if b) / n
    hi = [c for c, p in rows if p >= 0.8]
    pos = [p for c, p in rows if c]
    neg = [p for c, p in rows if not c]
    auroc = (sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg))) if pos and neg else float("nan")
    return (f"acc {100 * acc:5.1f}  ECE {ece:.3f}  AUROC {auroc:.3f}  conf>=0.8 {len(hi):3d} ({100 * len(hi) / n:4.1f}%) "
            f"@ {100 * sum(hi) / max(1, len(hi)):5.1f}%  confident-wrong {len(hi) - sum(hi)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("on")
    ap.add_argument("off")
    ap.add_argument("--dis-cap", type=float, default=0.5)
    ap.add_argument("--skip-lang", default="en")
    ap.add_argument("--dis-pick", choices=("confident", "translated"), default="confident",
                    help="on disagreement: the more confident reading, or always the translated one (both capped)")
    ap.add_argument("--det-only", action="store_true",
                    help="lift the cap on agreement only when the translated answer came from a rules solver (not a VLM)")
    a = ap.parse_args()
    on, off = load(a.on), load(a.off)
    qids = [q for q in on if q in off and (on[q].get("meta") or {}).get("lang") != a.skip_lang and on[q].get("gold") is not None]
    pol = {"translated (current)": [], "original (translate=0)": [], "both readings": []}
    n_agree = n_agree_right = 0
    by_src: dict[str, dict[str, list]] = {}
    for q in qids:
        r1, r0 = on[q], off[q]
        c1, c0 = bool(r1.get("correct")), bool(r0.get("correct"))
        p1, p0 = float(r1.get("confidence") or 0), float(r0.get("confidence") or 0)
        pol["translated (current)"].append((c1, p1))
        pol["original (translate=0)"].append((c0, p0))
        if same(r1.get("value"), r0.get("value")):
            n_agree += 1
            n_agree_right += c1
            vlm = any(k in str(r1.get("solver") or "") for k in ("vlm", "raster", "lora"))
            both = (c1, p1) if (a.det_only and vlm) else (c1, max(p1, p0))
        else:
            both = (c1, min(p1, a.dis_cap)) if (p1 >= p0 or a.dis_pick == "translated") else (c0, min(p0, a.dis_cap))
        pol["both readings"].append(both)
        s = by_src.setdefault(r1.get("source", "?"), {k: [] for k in pol})
        s["translated (current)"].append((c1, p1))
        s["original (translate=0)"].append((c0, p0))
        s["both readings"].append(both)
    print(f"{len(qids)} non-{a.skip_lang} questions; readings agree on {n_agree} ({100 * n_agree / len(qids):.0f}%), "
          f"{n_agree_right} of them right ({100 * n_agree_right / max(1, n_agree):.1f}%); disagree cap {a.dis_cap}")
    for k, v in pol.items():
        print(f"  {k:24s} {metrics(v)}")
    for src, d in sorted(by_src.items()):
        print(f"  [{src}] n={len(d['both readings'])}")
        for k, v in d.items():
            print(f"    {k:22s} {metrics(v)}")


if __name__ == "__main__":
    main()
