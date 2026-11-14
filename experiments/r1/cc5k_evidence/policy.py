"""Policy P2 (chosen on train_gate, confirmed on dev): for window/door/wc counts, when the LoRA and the CC5K
detector disagree, keep the one with the higher calibrated probability (LoRA p(answer digits) vs CC5K confidence
fitted on original-CC5K val); sinks and room counts keep the LoRA. Reports accuracy, paired cluster CI vs the
LoRA alone, and calibration of three confidence options.
  python policy.py PRED.jsonl [...]"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agree import load_cache, rows  # noqa: E402
from calib_combo import enrich, metrics, p_digits  # noqa: E402
from ensemble import paired_ci  # noqa: E402

ARBITRATE = {"window", "door", "wc"}


def decide(r, shrink=1.0):
    """-> (value, confidence, who)"""
    if r["agree"] or r["tgt"] not in ARBITRATE or r["p"] >= r["pdet"]:
        c = r["p"] if r["agree"] or r["tgt"] not in ARBITRATE else r["p"] * shrink
        return r["lora"], c, "lora"
    return r["det"], r["pdet"] * shrink, "cc5k"


if __name__ == "__main__":
    cache = load_cache()
    for f in sys.argv[1:]:
        V = enrich(rows([f], cache), p_digits([f]), cache)
        print(f"\n== {os.path.basename(f)}  n={len(V)}")
        by = defaultdict(list)
        for r in V:
            by[r["tgt"]].append(r)
        for t in ("window", "door", "wc", "sink"):
            g = by[t]
            d, lo, hi = paired_ci(g, lambda r: decide(r)[0], lambda r: r["lora"])
            n_sw = sum(decide(r)[2] == "cc5k" for r in g)
            print(f"  {t:7} n={len(g):3d} P2 {100*sum(decide(r)[0]==r['gold'] for r in g)/len(g):5.1f} "
                  f"lora {100*sum(r['lora']==r['gold'] for r in g)/len(g):5.1f}  Δ {100*d:+.1f} [{100*lo:+.1f}, {100*hi:+.1f}]"
                  f"  switched {n_sw}")
        sym = [r for r in V if r["tgt"] in ARBITRATE]
        d, lo, hi = paired_ci(sym, lambda r: decide(r)[0], lambda r: r["lora"])
        print(f"  window+door+wc: Δ {100*d:+.1f} [{100*lo:+.1f}, {100*hi:+.1f}]")
        for s in (1.0, 0.8, 0.7):
            rs = []
            ps = []
            for r in V:
                v, c, _ = decide(r, s)
                rs.append(dict(r, right=(v == r["gold"])))
                ps.append(c)
            print(f"  conf shrink on disagreement x{s}: " + " ".join(f"{k}={v:.3f}" for k, v in metrics(rs, ps).items()))
