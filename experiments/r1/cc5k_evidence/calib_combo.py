"""Confidence for LoRA answers with a CC5K cross-check. Fit on FIT (train_gate: LoRA never saw it), test on EVAL (dev).
Models compared (all per concept):
  A  p          : the LoRA's own p(answer digits) (what vlm_lora reports)
  B  table      : P(right | concept, agree?) from FIT, Beta-smoothed
  C  NB         : odds(p) x LR(agree?|concept), LR = P(agree|right)/P(agree|wrong) from FIT (smoothed)
For the windows rule (answer = detector) the value changes, so B/C are computed for the detector's answer with
the CC5K confidence (cached, fitted on original CC5K val) as p.
  python calib_combo.py FIT.jsonl EVAL.jsonl [--json OUT]"""
import json
import math
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agree import load_cache, rows, KEY2CC  # noqa: E402

USE_DET = {"window"}  # concepts where the detector's count is the answer (decided on FIT: +15 [+2.5, +30])


def p_digits(pred_files):
    out = {}
    for f in pred_files:
        for r in map(json.loads, open(f)):
            for t in r.get("trace") or []:
                m = re.search(r"p\(answer digits\) = ([0-9.]+)", t)
                if m:
                    out[r["qid"]] = float(m.group(1))
    return out


def enrich(rs, pd, cache):
    for r in rs:
        grp, k = KEY2CC[r["tgt"]]
        r["p"] = min(0.995, max(0.005, pd.get(r["qid"], r["conf"] or 0.3)))
        r["pdet"] = min(0.995, max(0.005, cache[r["path"]][grp][k].get("confidence", 0.5)))
        r["agree"] = r["lora"] == r["det"]
        r["value"] = r["det"] if r["tgt"] in USE_DET else r["lora"]
        r["right"] = r["value"] == r["gold"]
        r["p_own"] = r["pdet"] if r["tgt"] in USE_DET else r["p"]
    return rs


def fit(rs, a=2.0):
    by = defaultdict(list)
    for r in rs:
        by[r["tgt"]].append(r)
    tab = {}
    for t, g in by.items():
        base = sum(r["right"] for r in g) / len(g)
        e = {"n": len(g), "acc": round(base, 3)}
        for ag in (True, False):
            gg = [r for r in g if r["agree"] == ag]
            k = sum(r["right"] for r in gg)
            e["p_agree" if ag else "p_disagree"] = round((k + a * base) / (len(gg) + a), 3)
            e["n_agree" if ag else "n_disagree"] = len(gg)
        R = [r for r in g if r["right"]]
        W = [r for r in g if not r["right"]]
        pa_r = (sum(r["agree"] for r in R) + 1) / (len(R) + 2)
        pa_w = (sum(r["agree"] for r in W) + 1) / (len(W) + 2)
        e["lr_agree"] = round(pa_r / pa_w, 3)
        e["lr_disagree"] = round((1 - pa_r) / (1 - pa_w), 3)
        tab[t] = e
    return tab


def pred(r, tab, model):
    e = tab[r["tgt"]]
    if model == "A":
        return r["p_own"]
    if model == "B":
        return e["p_agree"] if r["agree"] else e["p_disagree"]
    o = r["p_own"] / (1 - r["p_own"]) * (e["lr_agree"] if r["agree"] else e["lr_disagree"])
    return o / (1 + o)


def metrics(rs, ps):
    n = len(rs)
    brier = sum((p - r["right"]) ** 2 for r, p in zip(rs, ps)) / n
    bins = defaultdict(list)
    for r, p in zip(rs, ps):
        bins[min(9, int(p * 10))].append((p, r["right"]))
    ece = sum(abs(sum(p for p, _ in b) / len(b) - sum(y for _, y in b) / len(b)) * len(b) for b in bins.values()) / n
    pos = [p for r, p in zip(rs, ps) if r["right"]]
    neg = [p for r, p in zip(rs, ps) if not r["right"]]
    auc = sum((x > y) + 0.5 * (x == y) for x in pos for y in neg) / (len(pos) * len(neg)) if pos and neg else float("nan")
    hi = [(r, p) for r, p in zip(rs, ps) if p >= 0.8]
    hi_acc = sum(r["right"] for r, _ in hi) / len(hi) if hi else float("nan")
    return dict(acc=sum(r["right"] for r in rs) / n, brier=brier, ece=ece, auroc=auc, cov80=len(hi) / n, acc80=hi_acc)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    args = [a for a in args if a != out]
    cache = load_cache()
    F = enrich(rows([args[0]], cache), p_digits([args[0]]), cache)
    V = enrich(rows([args[1]], cache), p_digits([args[1]]), cache)
    tab = fit(F)
    print(json.dumps(tab, indent=0)[:3000])
    for name, rs in (("FIT", F), ("EVAL", V)):
        for m in "ABC":
            ms = metrics(rs, [pred(r, tab, m) for r in rs])
            print(f"{name:4} {m}: " + " ".join(f"{k}={v:.3f}" for k, v in ms.items()))
        for t in ("window", "door", "wc", "sink"):
            g = [r for r in rs if r["tgt"] == t]
            print(f"   {t:7} " + "  ".join(f"{m}: ece={metrics(g, [pred(r, tab, m) for r in g])['ece']:.3f} "
                                          f"auc={metrics(g, [pred(r, tab, m) for r in g])['auroc']:.2f}" for m in "ABC"))
    if out:
        json.dump({"fit": os.path.basename(args[0]), "use_detector": sorted(USE_DET), "a": 2.0, "concepts": tab},
                  open(out, "w"), indent=1)
