"""Does triage predict where the pipeline fails? Triage every row of a run, then accuracy per triage class.

    $JUNCTION_VENV/bin/python experiments/r1/noon/triage_vs_run.py RUN.jsonl [--q-redteam DIR]

RUN.jsonl = a stoa.eval predictions file. Rows the eval leaves unscored (yes/no, multi-part text) are rescored with
Q's redteam/analyze.py rescore() (redteam/analyze.py in this repo, read-only import), else they are skipped.
"""
import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from experiments.r1.noon.triage import NN, triage_one  # noqa: E402
from stoa.eval.splits import load_split  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--q-redteam", default=str(ROOT / "redteam"), help="dir with Q's analyze.py ('' = skip)")
    a = ap.parse_args()
    rows = [json.loads(x) for x in open(a.run, encoding="utf-8") if x.strip()]
    if a.q_redteam:
        sys.path.insert(0, a.q_redteam)
        from analyze import rescore  # noqa: E402  (Q's scorer, unchanged)
        rows = rescore(rows)
    idx = [{"question": q.question, "path": q.path, "type": q.type} for s in ("train", "dev") for q in load_split(s)]
    nn = NN(idx)
    cls = collections.defaultdict(lambda: [0, 0, 0, 0])  # scored, right, conf>=0.8, conf>=0.8 wrong
    for r in rows:
        c = r.get("correct")
        if isinstance(c, str):
            c = {"True": True, "False": False}.get(c)
        if c is None:
            continue
        t = triage_one(r["question"], r["path"], nn)
        conf = float(r.get("confidence") or 0)
        keys = ["all"]
        keys.append("NEW (nn<0.5, no tmpl)" if t["novel"] else "seen (nn>=0.5 or tmpl)")
        keys.append(f"{t['source']}: " + ("NEW" if t["novel"] else "seen"))
        if any(x.startswith("parser gap") for x in t["todo"]):
            keys.append("parser gap")
        for k in ("link", "room", "est", "compose"):
            if t[k]:
                keys.append(k)
        if t["novel"] and any(x.startswith("parser gap") for x in t["todo"]):
            keys.append("NEW + parser gap")
        for k in keys:
            s = cls[k]
            s[0] += 1
            s[1] += bool(c)
            s[2] += conf >= 0.8
            s[3] += (conf >= 0.8 and not c)
    print(f"{'triage class':26s} {'n':>5s} {'acc':>6s} {'conf>=0.8':>9s} {'cw':>4s} {'cw rate':>7s}")
    for k, (n, ok, hi, cw) in sorted(cls.items(), key=lambda kv: -kv[1][0]):
        print(f"{k:26s} {n:5d} {100 * ok / n:5.1f}% {hi:9d} {cw:4d} {100 * cw / max(1, hi):6.1f}%")


if __name__ == "__main__":
    main()
