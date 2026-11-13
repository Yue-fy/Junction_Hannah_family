"""Paired difference A − B on shared questions with a drawing-cluster bootstrap 95% CI (owner: R2).
    $JUNCTION_VENV/bin/python experiments/r2/paired.py RUN_A RUN_B [--source cubicasa5k] [--grep REGEX]"""
from __future__ import annotations

import argparse
import collections
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from experiments.r2.escalate import _rows  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("a")
ap.add_argument("b")
ap.add_argument("--source")
ap.add_argument("--grep")
x = ap.parse_args()
A = {r["qid"]: r for r in _rows(x.a) if r.get("correct") is not None}
B = {r["qid"]: r for r in _rows(x.b) if r.get("correct") is not None}
by = collections.defaultdict(list)
for q in A.keys() & B.keys():
    r = A[q]
    if x.source and r["source"] != x.source:
        continue
    if x.grep and not re.search(x.grep, r["question"], re.I):
        continue
    by[r["path"]].append(int(bool(r["correct"])) - int(bool(B[q]["correct"])))
groups = list(by.values())
n = sum(len(g) for g in groups)
d = sum(sum(g) for g in groups) / n
rng = random.Random(0)
boots = []
for _ in range(2000):
    s = [groups[rng.randrange(len(groups))] for _ in groups]
    boots.append(sum(sum(g) for g in s) / sum(len(g) for g in s))
boots.sort()
print(f"{n} Qs on {len(groups)} drawings: A − B = {d * 100:+.1f} pts [{boots[50] * 100:+.1f}, {boots[1949] * 100:+.1f}]")
