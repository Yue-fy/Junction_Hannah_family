"""Do dense small plans need a 2x pass? Count windows (and doors) on maps inferred at 2x and KEPT at 2x
(infer.py --scale 2 --keep-res, tag u2_), vs the frozen 1x counts. Leak-safe: tune on original CC5K val, report on
original test (our sealed test excluded). Rules: always 2x; 2x when the long side <= T; 2x when the 1x count per
megapixel >= D (dense plans).  Run: $JUNCTION_VENV/bin/python -I dense2x.py"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from count import SEG, counts, gold_table, stems_of  # noqa: E402

FROZEN = {"windows": (2e-4, 5), "doors": (2e-4, 0)}


def load(st, tag):
    p = os.path.join(SEG, tag + st + ".npz")
    try:
        return {"icons": np.load(p)["icons"]} if os.path.exists(p) else None
    except Exception:  # noqa: BLE001 - being written by infer.py
        return None


def rows(split, gold, t, grid):
    out = []
    for st in stems_of(split):
        if t not in gold.get(st, {}):
            continue
        z1, z2 = load(st, ""), load(st, "u2_")
        if z1 is None:
            continue
        H, W = z1["icons"].shape
        c1 = counts(z1, t, *FROZEN[t])
        c2 = {g: counts(z2, t, *g) for g in grid} if z2 is not None else None  # test: only gated plans have 2x maps
        out.append(dict(st=st, g=gold[st][t], c1=c1, c2=c2, L=max(H, W), dens=c1 / (H * W / 1e6)))
    return out


def acc(rs, pick):
    rs = [r for r in rs if r["c2"] is not None or _gate_off(pick, r)]
    return sum(pick(r) == r["g"] for r in rs) / max(1, len(rs))


def _gate_off(pick, r):
    try:
        pick(r)
        return True
    except TypeError:  # pick needed 2x maps this plan doesn't have
        return False


if __name__ == "__main__":
    gold = gold_table()
    grid = [(mf, k) for mf in (5e-5, 1e-4, 2e-4, 3e-4) for k in (0, 3, 5, 7, 9)]
    for t in ("windows", "doors"):
        val, test = rows("val", gold, t, grid), rows("test", gold, t, grid)
        print(f"\n== {t}: val n={len(val)} test n={len(test)}  1x frozen: val {100*acc(val, lambda r: r['c1']):.1f} "
              f"test {100*acc(test, lambda r: r['c1']):.1f}")
        best = max(grid, key=lambda g: acc(val, lambda r: r["c2"][g]))
        print(f"  always 2x, best on val {best}: val {100*acc(val, lambda r: r['c2'][best]):.1f} "
              f"test {100*acc(test, lambda r: r['c2'][best]):.1f}")
        for g in sorted(grid, key=lambda g: -acc(val, lambda r: r["c2"][g]))[:4]:
            print(f"    {g}: val {100*acc(val, lambda r: r['c2'][g]):.1f} test {100*acc(test, lambda r: r['c2'][g]):.1f}")
        # gated: 2x only on dense or small plans
        cands = []
        for g in grid:
            for D in (0, 5, 10, 15, 20, 30, 40, 60):
                for T in (700, 900, 1100, 1300, 1500):
                    pick = lambda r, g=g, D=D, T=T: r["c2"][g] if (r["dens"] >= D and r["L"] <= T) else r["c1"]
                    cands.append((acc(val, pick), g, D, T, pick))
        cands.sort(key=lambda c: -c[0])
        a, g, D, T, pick = cands[0]
        n2 = sum(r["dens"] >= D and r["L"] <= T for r in test)
        print(f"  gated best on val: 2x{g} when dens>={D}/MP and long side<={T}: val {100*a:.1f} test "
              f"{100*acc(test, pick):.1f} (2x used on {n2}/{len(test)} test plans)")
        # paired drawing-level bootstrap on test, gated vs 1x
        rng = np.random.default_rng(0)
        d = np.array([(pick(r) == r["g"]) - (r["c1"] == r["g"]) for r in test if _gate_off(pick, r)], float)
        bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(4000)]
        print(f"  test gated - 1x: {100*d.mean():+.1f} [{100*np.percentile(bs, 2.5):+.1f}, {100*np.percentile(bs, 97.5):+.1f}]")
