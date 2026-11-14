"""Fit vlm_lora's per-concept confidence table (owner: R2): hit rate of the LoRA per (intent target, answer-digit
probability bin) on train_gate (drawings the LoRA never saw). Writes stoa/solvers/lora_concept_conf.json.
    $JUNCTION_VENV/bin/python experiments/r2/fit_concept_conf.py [--model cc-v2] [--run RUN]
Validation (experiments/r2/conf_cost.py on dev pipeline bb98): AUROC 0.892 vs 0.881 for the pipeline's
train-hit-rate x raster-agreement confidence, ECE 0.037 vs 0.035, without the raster second reader.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from experiments.r2.conf_cost import BINS, pbin, signals  # noqa: E402
from stoa.eval.analyze import load, resolve  # noqa: E402
from stoa.router.intent import parse  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="cc-v2")
ap.add_argument("--run", default="20261114-012403-vlm_direct-train_gate-ee1b")
x = ap.parse_args()
tab: dict = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
for r in load(resolve(x.run)):
    p, _ = signals(r)
    if p is None or r.get("correct") is None:
        continue
    for key in (parse(r["question"]).target, "_all"):
        cell = tab[key][str(pbin(p))]
        cell[0] += bool(r["correct"]); cell[1] += 1
out = Path(__file__).resolve().parents[2] / "stoa/solvers/lora_concept_conf.json"
data = json.loads(out.read_text()) if out.exists() else {}
data[x.model] = {"bins": BINS, "fit_run": x.run, "shrink": 4,
                 "table": {k: {b: v for b, v in sorted(t.items())} for k, t in sorted(tab.items())}}
out.write_text(json.dumps(data, indent=1) + "\n")
print(out, {k: sum(v[1] for v in t.values()) for k, t in tab.items()})
