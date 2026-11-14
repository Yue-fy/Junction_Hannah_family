"""Door arcs (raster, twins=0) vs the counting LoRA (vlm_lora -> cc-v3 on non-CubiCasa PNGs) on the same door
questions (upload_set.py). Prints accuracy bands per method, agreement-conditioned accuracy and simple
combination rules, so the pipeline owner can pick a rule for twin-less / uploaded Swiss-style PNGs.
Usage: python experiments/w3/doorwin/upload_cmp.py <raster_run.jsonl> <lora_run.jsonl>
"""
from __future__ import annotations

import json
import sys


def load(f):
    out = {}
    for line in open(f):
        r = json.loads(line)
        out[r["qid"]] = r
    return out


def band(pred, gold):
    if pred is None:
        return None
    e = abs(pred - gold)
    return {"exact": e == 0, "pm1": e <= 1, "pm2": e <= 2, "10pct": e <= 0.1 * gold}


def summary(name, rows):
    n = len(rows)
    ans = [b for b in rows if b is not None]
    s = {k: sum(b[k] for b in ans) for k in ("exact", "pm1", "pm2", "10pct")}
    print(f"{name:34s} n={n:3d} answered={len(ans):3d}  " + "  ".join(f"{k} {v:3d} ({100 * v / n:4.1f}%)"
                                                                       for k, v in s.items()))


def main():
    ra, lo = load(sys.argv[1]), load(sys.argv[2])
    qids = sorted(set(ra) & set(lo))
    rows = []
    for q in qids:
        g = int(ra[q]["gold"])
        a = ra[q]["value"]
        b = lo[q]["value"]
        rows.append((q, g, int(a) if a is not None else None, int(b) if b is not None else None,
                     float(lo[q].get("confidence") or 0)))
    summary("door arcs", [band(a, g) for _, g, a, _, _ in rows])
    summary("LoRA (cc-v3)", [band(b, g) for _, g, _, b, _ in rows])
    both = [(g, a, b, c) for _, g, a, b, c in rows if a is not None and b is not None]
    summary("arcs where both answer", [band(a, g) for g, a, _, _ in both])
    summary("LoRA where both answer", [band(b, g) for g, _, b, _ in both])
    summary("mean(arcs, LoRA) rounded", [band(round((a + b) / 2), g) for g, a, b, _ in both])
    summary("max(arcs, LoRA)", [band(max(a, b), g) for g, a, b, _ in both])
    summary("arcs else LoRA", [band(a if a is not None else b, g) for _, g, a, b, _ in rows])
    for tol in (0, 1, 2):
        ag = [(g, a, b) for g, a, b, _ in both if abs(a - b) <= tol]
        dis = [(g, a, b) for g, a, b, _ in both if abs(a - b) > tol]
        print(f"agree within {tol}: {len(ag):3d}/{len(both)}  arcs exact {sum(a == g for g, a, _ in ag):3d}  "
              f"LoRA exact {sum(b == g for g, _, b in ag):3d}  arcs pm1 {sum(abs(a - g) <= 1 for g, a, _ in ag):3d}"
              f" | disagree {len(dis):3d}: arcs exact {sum(a == g for g, a, _ in dis):3d}, LoRA exact "
              f"{sum(b == g for g, _, b in dis):3d}, arcs closer {sum(abs(a - g) < abs(b - g) for g, a, b in dis)}"
              f", LoRA closer {sum(abs(b - g) < abs(a - g) for g, a, b in dis)}")
    # LoRA confidence bins
    for lo_c, hi_c in ((0, 0.2), (0.2, 0.45), (0.45, 0.8), (0.8, 1.01)):
        sel = [(g, a, b) for g, a, b, c in both if lo_c <= c < hi_c]
        if sel:
            print(f"LoRA conf [{lo_c:.2f},{hi_c:.2f}): n={len(sel):3d} LoRA exact {sum(b == g for g, _, b in sel):3d}"
                  f"  arcs exact {sum(a == g for g, a, _ in sel):3d}")
    # signed error by size
    import statistics as st
    ea = [a - g for _, g, a, _, _ in rows if a is not None]
    eb = [b - g for _, g, _, b, _ in rows if b is not None]
    print(f"median signed error: arcs {st.median(ea):+.1f}, LoRA {st.median(eb):+.1f}; median |rel err| arcs "
          f"{st.median(abs(a - g) / g for _, g, a, _, _ in rows if a is not None and g):.3f} LoRA "
          f"{st.median(abs(b - g) / g for _, g, _, b, _ in rows if b is not None and g):.3f}")
    small = [(g, a, b) for g, a, b, _ in both if g <= 15]
    big = [(g, a, b) for g, a, b, _ in both if g > 15]
    for nm, sel in (("gold<=15", small), ("gold>15", big)):
        print(f"{nm}: n={len(sel)} arcs exact {sum(a == g for g, a, _ in sel)} pm1 {sum(abs(a - g) <= 1 for g, a, _ in sel)}"
              f" | LoRA exact {sum(b == g for g, _, b in sel)} pm1 {sum(abs(b - g) <= 1 for g, _, b in sel)}")


if __name__ == "__main__":
    main()
