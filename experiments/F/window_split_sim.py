"""Offline: does splitting long CC5K window boxes into several windows fix the detector's undercount?

python experiments/F/window_split_sim.py [--split cc5k_heldout]
Uses R1's cached detections ($JUNCTION_SHARED/artifacts/R1/cc5k_counts.jsonl) and gold from the split. Only drawings
NOT in CubiCasa5K's own train list are leak-free for the detector. Fit the rule on even-hash drawings, check on odd.
"""
import argparse, json, os, re, hashlib, statistics as st
from pathlib import Path
from stoa.eval.splits import load_split

SH = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
ap = argparse.ArgumentParser(); ap.add_argument("--split", default="cc5k_heldout"); ap.add_argument("--concept", default="windows")
a = ap.parse_args()
RX = {"windows": r"window|ikkun", "doors": r"\bdoors?\b|\bov[ei]"}[a.concept]
cc = {json.loads(l)["path"]: json.loads(l) for l in open(SH / "artifacts/R1/cc5k_counts.jsonl")}
rows = []
for q in load_split(a.split):
    if q.source != "cubicasa5k" or not re.search(RX, q.question, re.I):
        continue
    d = cc.get(q.path)
    if not d or d["cc5k_list"] == "train":
        continue
    boxes = d["counts"][a.concept]["boxes"]
    lens = [max(x1 - x0, y1 - y0) for x0, y0, x1, y1 in boxes]
    thick = [min(x1 - x0, y1 - y0) for x0, y0, x1, y1 in boxes]
    rows.append(dict(path=q.path, gold=int(q.answer), n=len(boxes), lens=lens, thick=thick, size=d["size"]))
print(f"{a.concept}: {len(rows)} leak-free questions")
fit = [r for r in rows if int(hashlib.md5(r["path"].encode()).hexdigest(), 16) % 2 == 0]
chk = [r for r in rows if r not in fit]

def est(r, mode, k):
    if not r["lens"]:
        return 0
    if mode == "raw":
        return r["n"]
    if mode == "med":     # split boxes longer than k x the drawing's median box length
        m = st.median(r["lens"])
        return sum(max(1, round(L / (k * m))) if L > 1.5 * k * m else 1 for L in r["lens"])
    if mode == "thick":   # split boxes longer than k x wall thickness (box short side)
        t = st.median(r["thick"])
        return sum(max(1, int(L // (k * t))) for L in r["lens"])
    if mode == "add":
        return r["n"] + k

def acc(rs, mode, k):
    return 100 * sum(est(r, mode, k) == r["gold"] for r in rs) / max(1, len(rs))

print("raw detector: fit %.1f  check %.1f" % (acc(fit, "raw", 0), acc(chk, "raw", 0)))
print("gold - detector:", sorted(__import__("collections").Counter(r["gold"] - r["n"] for r in rows).items()))
best = {}
for mode, ks in (("med", [0.8, 1.0, 1.2, 1.5, 2.0]), ("thick", [3, 4, 5, 6, 8, 10, 12]), ("add", [1, 2])):
    for k in ks:
        f, c = acc(fit, mode, k), acc(chk, mode, k)
        print(f"  {mode:5s} k={k:<4} fit {f:5.1f}  check {c:5.1f}")

# --- does the miss depend on image size (detector resolution)? ---
print("\nmiss (gold - detector) by image size (max side px):")
bins = [(0, 1500), (1500, 2500), (2500, 3500), (3500, 5000), (5000, 99999)]
for lo, hi in bins:
    rs = [r for r in rows if lo <= max(r["size"]) < hi]
    if not rs:
        continue
    miss = [r["gold"] - r["n"] for r in rs]
    print(f"  {lo:5d}-{hi:<5d} n={len(rs):3d} exact {100 * sum(m == 0 for m in miss) / len(rs):5.1f}%  "
          f"mean miss {st.mean(miss):5.2f}  gold mean {st.mean(r['gold'] for r in rs):5.1f}  "
          f"rel miss {st.mean((r['gold'] - r['n']) / max(1, r['gold']) for r in rs):5.2f}")
print("\nby gold count:")
for lo, hi in [(0, 4), (4, 8), (8, 12), (12, 20), (20, 999)]:
    rs = [r for r in rows if lo <= r["gold"] < hi]
    if rs:
        print(f"  gold {lo}-{hi}: n={len(rs)} exact {100 * sum(r['gold'] == r['n'] for r in rs) / len(rs):.1f}%  "
              f"mean size {st.mean(max(r['size']) for r in rs):.0f}px  rel miss {st.mean((r['gold'] - r['n']) / max(1, r['gold']) for r in rs):.2f}")

# --- resolution: px per window. Proxy = image long side / sqrt(gold); and detected box length ---
print("\nby px-per-window proxy (long side / sqrt(gold)):")
for lo, hi in [(0, 200), (200, 300), (300, 400), (400, 9999)]:
    rs = [r for r in rows if r["gold"] > 0 and lo <= max(r["size"]) / r["gold"] ** 0.5 < hi]
    if rs:
        bl = [st.median(r["lens"]) for r in rs if r["lens"]]
        print(f"  {lo:4d}-{hi:<4d} n={len(rs):3d} exact {100 * sum(r['gold'] == r['n'] for r in rs) / len(rs):5.1f}%  "
              f"rel miss {st.mean((r['gold'] - r['n']) / r['gold'] for r in rs):5.2f}  median box len {st.median(bl) if bl else 0:.0f}px")
