"""Fit the confidence table crosscheck.check() uses for vlm_lora answers: P(answer right | target, case), case in
{agree, kept (disagree, LoRA kept), switched (disagree, detector chosen)}, on a run the LoRA never trained on
(train_gate). (k+1)/(n+2), capped at 0.95 (≤ 40 questions per cell).
  python fit_calib.py LORA_TRAIN_GATE.jsonl OUT.json"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agree import load_cache, rows  # noqa: E402
from calib_combo import enrich, p_digits  # noqa: E402

ARBITRATE = {"window", "wc"}
CAP = 0.95


def case(r):
    if r["agree"]:
        return "agree", r["lora"]
    if r["tgt"] in ARBITRATE and r["pdet"] > r["p"]:
        return "switched", r["det"]
    return "kept", r["lora"]


if __name__ == "__main__":
    cache = load_cache()
    rs = enrich(rows([sys.argv[1]], cache), p_digits([sys.argv[1]]), cache)
    cells = defaultdict(lambda: [0, 0])
    for r in rs:
        c, v = case(r)
        cells[(r["tgt"], c)][0] += v == r["gold"]
        cells[(r["tgt"], c)][1] += 1
    tab = defaultdict(dict)
    for (t, c), (k, n) in sorted(cells.items()):
        tab[t][c] = round(min(CAP, (k + 1) / (n + 2)), 3)
        tab[t]["n_" + c] = n
    out = {"fitted_on": os.path.basename(sys.argv[1]), "rule": "(k+1)/(n+2) capped at 0.95",
           "applies_to_solvers": ["vlm_lora"], "arbitrate": sorted(ARBITRATE), "targets": tab}
    json.dump(out, open(sys.argv[2], "w"), indent=1)
    print(json.dumps(out, indent=1))
