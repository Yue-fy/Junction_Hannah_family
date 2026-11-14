"""Calibrated range for counts the CC5K detector answers ALONE (raster_cc5k first, e.g. windows on cc5k=1).
Leak-safe (D3/D8): split-conformal margins fitted on drawings in the original CC5K val list, coverage reported on
the original test list (our sealed test excluded). Interval = [C - lo, C + hi], margins per class x size bucket of C
(errors grow with plan size: R2/F 03:2x).  python det_interval.py [--alpha 0.1] [--write crosscheck_calib.json]"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cc5k_model"))
from count import gold_table, stems_of  # noqa: E402

SH = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")
CLASSES = ("windows", "doors", "wc_seats", "sinks")
BUCKETS = {"windows": (4, 8), "doors": (4, 8), "wc_seats": (1,), "sinks": (2,)}


def bucket(cls, c):
    edges = BUCKETS[cls]
    for i, e in enumerate(edges):
        if c <= e:
            return f"<={e}"
    return f">{edges[-1]}"


def rows(split, gold, cache):
    sealed = {json.loads(l)["path"] for l in open(f"{SH}/results/splits/test.jsonl")}
    out = []
    for st in stems_of(split):
        p = f"data/cubicasa5k/{st}.png"
        if p in sealed or p not in cache:
            continue
        for cls in CLASSES:
            if cls in gold.get(st, {}):
                c = cache[p]["counts"][cls]["count"]
                out.append(dict(cls=cls, b=bucket(cls, c), c=c, g=gold[st][cls]))
    return out


def fit(rs, alpha):
    cells = {}
    for r in rs:
        cells.setdefault((r["cls"], r["b"]), []).append(r)
    tab = {}
    for k, g in cells.items():
        n = len(g)
        need = min(1.0, math.ceil((n + 1) * (1 - alpha)) / n)
        best = None
        for lo in range(0, 15):
            for hi in range(0, 30):
                cov = sum(r["c"] - lo <= r["g"] <= r["c"] + hi for r in g) / n
                if cov >= need and (best is None or lo + hi < best[0]):
                    best = (lo + hi, lo, hi)
        tab[k] = [best[1], best[2]] if best else [14, 29]
    return tab


if __name__ == "__main__":
    alpha = float(sys.argv[sys.argv.index("--alpha") + 1]) if "--alpha" in sys.argv else 0.1
    gold = gold_table()
    cache = {json.loads(l)["path"]: json.loads(l) for l in open(f"{SH}/artifacts/R1/cc5k_counts.jsonl")}
    val, test = rows("val", gold, cache), rows("test", gold, cache)
    tab = fit(val, alpha)
    print(f"alpha {alpha}: val n={len(val)}, test n={len(test)}")
    for cls in CLASSES:
        t = [r for r in test if r["cls"] == cls]
        cov = [max(0, r["c"] - tab[(cls, r["b"])][0]) <= r["g"] <= r["c"] + tab[(cls, r["b"])][1] for r in t]
        w = [tab[(cls, r["b"])][0] + tab[(cls, r["b"])][1] + 1 for r in t]
        exact = sum(r["c"] == r["g"] for r in t) / len(t)
        print(f"  {cls:8} test n={len(t):3d} exact {100*exact:4.1f}%  range coverage {100*sum(cov)/len(t):4.1f}%  "
              f"mean width {sum(w)/len(w):4.1f}  margins " +
              " ".join(f"{b}:-{v[0]}/+{v[1]}" for (c, b), v in sorted(tab.items()) if c == cls))
    if "--write" in sys.argv:
        p = sys.argv[sys.argv.index("--write") + 1]
        d = json.load(open(p))
        lvl = str(int(round(100 * (1 - alpha))))
        d.setdefault("detector_intervals", {"rule": "[C - lo, C + hi] for the CC5K detector's own count, margins per "
                                                    "class x count bucket, split-conformal on original CC5K val, "
                                                    "coverage checked on original CC5K test (leak-safe, D8)",
                                            "buckets": BUCKETS})
        d["detector_intervals"][lvl] = {f"{c}|{b}": v for (c, b), v in sorted(tab.items())}
        json.dump(d, open(p, "w"), indent=1)
