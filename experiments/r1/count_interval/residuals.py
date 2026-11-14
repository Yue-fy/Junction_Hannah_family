"""Residual distributions (gold - answer) for cubicasa counts after crosscheck arbitration, by target and case.
  python residuals.py PRED.jsonl"""
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cc5k_evidence"))
from agree import load_cache, rows  # noqa: E402
from calib_combo import enrich, p_digits  # noqa: E402
from fit_calib import case  # noqa: E402

if __name__ == "__main__":
    cache = load_cache()
    f = sys.argv[1]
    rs = [r for r in enrich(rows([f], cache), p_digits([f]), cache) if r["lora"] is not None]
    by = defaultdict(list)
    for r in rs:
        c, v = case(r)
        by[(r["tgt"], "agree" if c == "agree" else "dis")].append((r["gold"] - v, v, r))
    for k in sorted(by):
        g = by[k]
        res = Counter(d for d, _, _ in g)
        rel = sorted(d / max(1, v) for d, v, _ in g)
        print(f"{k[0]:9} {k[1]:5} n={len(g):3d} mean_ans={sum(v for _, v, _ in g)/len(g):5.1f} "
              f"res: {dict(sorted(res.items()))}")
