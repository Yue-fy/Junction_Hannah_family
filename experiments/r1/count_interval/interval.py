"""Calibrated integer prediction intervals for cubicasa counts from two counters (LoRA cc-v2 + CC5K detector).

Split-conformal style: margins fitted on a calibration run (train_gate: the LoRA never trained on it), checked on
another run (dev). Rules compared:
  point  [a - lo, a + hi]                         a = answer after crosscheck arbitration
  hull   [min(L, C) - lo, max(L, C) + hi]         the two counters' range, widened
  rel    [floor(a*(1-lo)), ceil(a*(1+hi))]        relative margins (big plans get wide intervals)
Margins per (group, case): group = openings (window, door) | fixtures (wc, sink) | rooms (bedroom, balcony,
bathroom, kitchen); case = agree | disagree. Margins = smallest lo+hi whose calibration coverage is
>= ceil((n+1)(1-alpha))/n (the finite-sample conformal level).
  python interval.py CALIB.jsonl EVAL.jsonl [--alpha 0.1]"""
import json
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cc5k_evidence"))
from agree import load_cache, rows  # noqa: E402
from calib_combo import enrich, p_digits  # noqa: E402
from fit_calib import case  # noqa: E402

GROUP = {"window": "openings", "door": "openings", "wc": "fixtures", "sink": "fixtures",
         "bedroom": "rooms", "balcony": "rooms", "bathroom": "rooms", "kitchen": "rooms"}


def load(f, cache):
    out = []
    for r in enrich(rows([f], cache), p_digits([f]), cache):
        if r["lora"] is None:
            continue
        c, a = case(r)
        r["ans"] = a
        r["case"] = "agree" if c == "agree" else "dis"
        out.append(r)
    return out


def bounds(rule, r, lo, hi):
    a, L, C = r["ans"], r["lora"], r["det"]
    if rule == "point":
        return a - lo, a + hi
    if rule == "hull":
        return min(L, C) - lo, max(L, C) + hi
    if rule == "rel":
        return math.floor(a * (1 - lo)), math.ceil(a * (1 + hi))
    raise ValueError(rule)


GRID = {"point": [(lo, hi) for lo in range(0, 15) for hi in range(0, 30)],
        "hull": [(lo, hi) for lo in range(0, 15) for hi in range(0, 30)],
        "rel": [(lo / 20, hi / 20) for lo in range(0, 20) for hi in range(0, 60)]}


def fit(rs, rule, alpha, key):
    cells = defaultdict(list)
    for r in rs:
        cells[key(r)].append(r)
    tab = {}
    for k, g in cells.items():
        n = len(g)
        need = min(1.0, math.ceil((n + 1) * (1 - alpha)) / n)
        best = None
        for lo, hi in GRID[rule]:
            cov = sum(b[0] <= r["gold"] <= b[1] for r in g for b in [bounds(rule, r, lo, hi)]) / n
            if cov >= need:
                w = sum(b[1] - b[0] + 1 for r in g for b in [bounds(rule, r, lo, hi)]) / n
                if best is None or w < best[0]:
                    best = (w, lo, hi)
        tab[k] = (best[1], best[2]) if best else GRID[rule][-1]
    return tab


def evaluate(rs, rule, tab, key):
    by = defaultdict(lambda: [0, 0, 0])
    for r in rs:
        lo, hi = tab.get(key(r), GRID[rule][-1])
        b = bounds(rule, r, lo, hi)
        for k in (r["tgt"], "ALL"):
            by[k][0] += b[0] <= r["gold"] <= b[1]
            by[k][1] += b[1] - b[0] + 1
            by[k][2] += 1
    return by


if __name__ == "__main__":
    alpha = float(sys.argv[sys.argv.index("--alpha") + 1]) if "--alpha" in sys.argv else 0.1
    cache = load_cache()
    cal, ev = load(sys.argv[1], cache), load(sys.argv[2], cache)
    keys = {"group×case": lambda r: (GROUP[r["tgt"]], r["case"]), "target×case": lambda r: (r["tgt"], r["case"])}
    print(f"alpha={alpha} (nominal coverage {100*(1-alpha):.0f}%); calib n={len(cal)}, eval n={len(ev)}")
    for kn, key in keys.items():
        for rule in ("point", "hull", "rel"):
            tab = fit(cal, rule, alpha, key)
            res = evaluate(ev, rule, tab, key)
            line = " ".join(f"{t}:{100*c/n:.0f}%/{w/n:.1f}" for t, (c, w, n) in sorted(res.items()))
            print(f"{kn:11} {rule:5} {line}")
            if "--dump" in sys.argv:
                print("   ", json.dumps({"|".join(k): v for k, v in sorted(tab.items())}))


def write(cal, path):
    """Merge the chosen rule (hull, group x case) at 90% and 80% into crosscheck_calib.json["intervals"]."""
    key = lambda r: (GROUP[r["tgt"]], r["case"])  # noqa: E731
    d = json.load(open(path))
    d["intervals"] = {"rule": "[min(answer, detector) - lo, max(answer, detector) + hi], lo/hi per group x "
                              "(agree|disagree); split-conformal margins fitted on " + os.path.basename(sys.argv[1]),
                      "groups": GROUP}
    for alpha in (0.1, 0.2):
        tab = fit(cal, "hull", alpha, key)
        lvl = str(int(round(100 * (1 - alpha))))
        d["intervals"][lvl] = {}
        for (g, c), (lo, hi) in sorted(tab.items()):
            d["intervals"][lvl].setdefault(g, {})["agree" if c == "agree" else "disagree"] = [lo, hi]
    json.dump(d, open(path, "w"), indent=1)
    print(json.dumps(d["intervals"], indent=1))


if __name__ == "__main__" and "--write" in sys.argv:
    write(load(sys.argv[1], load_cache()), sys.argv[sys.argv.index("--write") + 1])
