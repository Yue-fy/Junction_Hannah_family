"""Is the raster second reader worth its cost on cubicasa LoRA answers? (S0 03:56: cubicasa cost x20.)

The pipeline runs raster (VLM label reader + fixtures) as a second opinion on every LoRA count, then moves LoRA's
confidence by agreement ('cross-check: vlm_lora N = raster M ✓ → conf c'). The value never changes, so the only
gain is calibration/ranking. This replays one run: confidence before (LoRA's own) vs after the cross-check, and
gated variants where the second reader runs only when LoRA's own confidence is in a band [a, b].

    python experiments/r1/cost_gate/second_reader.py artifacts/eval/<run>.jsonl
"""
import json
import re
import sys
from collections import defaultdict

PRE = re.compile(r"^vlm_lora: \S+ count \(conf ([0-9.]+)")
# LoRA's own per-question confidence (answer-digit probability mapped on train_gate): free, no second reader
PRE = re.compile(r"^\[vlm_lora\] p\(answer digits\) = [0-9.e-]+ -> confidence ([0-9.]+)") if "--keyconf" not in sys.argv else PRE


def auroc(c, y):
    pos = [a for a, b in zip(c, y) if b]
    neg = [a for a, b in zip(c, y) if not b]
    if not pos or not neg:
        return float("nan")
    s = 0.0
    for p in pos:
        for n in neg:
            s += 1 if p > n else 0.5 if p == n else 0
    return s / len(pos) / len(neg)


def ece(c, y, bins=10):
    b = defaultdict(list)
    for a, t in zip(c, y):
        b[min(int(a * bins), bins - 1)].append((a, t))
    return sum(abs(sum(a for a, _ in v) / len(v) - sum(t for _, t in v) / len(v)) * len(v) for v in b.values()) / len(c)


def summary(name, c, y, used):
    hi = [t for a, t in zip(c, y) if a >= 0.8]
    print(f"{name:28s} ECE {ece(c, y):.3f}  AUROC {auroc(c, y):.3f}  Brier "
          f"{sum((a - t) ** 2 for a, t in zip(c, y)) / len(c):.4f}  conf>=0.8 on {100 * len(hi) / len(c):4.1f}% "
          f"@ {100 * sum(hi) / max(1, len(hi)):.1f}%  | second reader on {100 * used:.0f}% of Qs")


def main():
    rows = [json.loads(l) for l in open(sys.argv[1])]
    cc = [r for r in rows if r.get("source") == "cubicasa5k" and "vlm_lora" in r.get("solver", "")]
    pre, post, y, drawings = [], [], [], []
    for r in cc:
        p = next((float(m.group(1)) for t in r["trace"] for m in [PRE.match(t)] if m), None)
        if p is None:
            continue
        pre.append(p)
        post.append(r["confidence"])
        y.append(1 if r["correct"] else 0)
        drawings.append(r["path"])
    print(f"{len(y)} LoRA cubicasa answers, accuracy {100 * sum(y) / len(y):.1f}% (value identical in all variants)")
    summary("LoRA own conf (no reader)", pre, y, 0)
    summary("after cross-check (today)", post, y, 1)
    for a, b in [(0.3, 0.95), (0.4, 0.9), (0.5, 0.9), (0.2, 0.8), (0.0, 0.8), (0.5, 1.01), (0.0, 0.5)]:
        g = [q if a <= p < b else p for p, q in zip(pre, post)]
        used = sum(a <= p < b for p in pre) / len(pre)
        nd = len({d for d, p in zip(drawings, pre) if a <= p < b}) / len(set(drawings))
        summary(f"reader iff {a:.1f}<=own<{b:.2f}", g, y, used)
        print(f"{'':28s} (drawings needing a read: {100 * nd:.0f}%)")


if __name__ == "__main__" and "--boot" not in sys.argv and "--blends" not in sys.argv:
    main()


def bootstrap(path, reps=1000, seed=0):
    """Drawing-cluster bootstrap of (after - before) for AUROC and Brier, and per-key breakdown."""
    import random
    rows = [json.loads(l) for l in open(path)]
    by_d = defaultdict(list)
    keyed = defaultdict(list)
    for r in rows:
        if r.get("source") != "cubicasa5k" or "vlm_lora" not in r.get("solver", ""):
            continue
        p = next((float(m.group(1)) for t in r["trace"] for m in [PRE.match(t)] if m), None)
        if p is None:
            continue
        key = next((t.split(":")[1].split("[")[0].strip() for t in r["trace"] if t.startswith("intent:")), "?")
        rec = (p, r["confidence"], 1 if r["correct"] else 0)
        by_d[r["path"]].append(rec)
        keyed[key].append(rec)
    ds = list(by_d)
    rng = random.Random(seed)
    da, db = [], []
    for _ in range(reps):
        s = [x for d in (rng.choice(ds) for _ in ds) for x in by_d[d]]
        pre, post, y = zip(*s)
        da.append(auroc(post, y) - auroc(pre, y))
        db.append(sum((b - t) ** 2 - (a - t) ** 2 for a, b, t in s) / len(s))
    da.sort(); db.sort()
    print(f"bootstrap over {len(ds)} drawings: dAUROC {da[reps // 2]:+.3f} [{da[int(.025 * reps)]:+.3f}, "
          f"{da[int(.975 * reps)]:+.3f}]  dBrier {db[reps // 2]:+.4f} [{db[int(.025 * reps)]:+.4f}, {db[int(.975 * reps)]:+.4f}]")
    for k, v in sorted(keyed.items(), key=lambda kv: -len(kv[1])):
        pre, post, y = zip(*v)
        print(f"  {k:22s} n={len(v):3d} acc {100 * sum(y) / len(y):5.1f}  AUROC {auroc(pre, y):.3f} -> {auroc(post, y):.3f}  "
              f"Brier {sum((a - t) ** 2 for a, t in zip(pre, y)) / len(y):.3f} -> {sum((a - t) ** 2 for a, t in zip(post, y)) / len(y):.3f}")


if __name__ == "__main__" and "--boot" in sys.argv:
    bootstrap(sys.argv[1])


def blends(path):
    """Reader-free hedges: mean / min of the LoRA's own confidence and the key's train hit rate."""
    rows = [json.loads(l) for l in open(path)]
    KEY = re.compile(r"^vlm_lora: \S+ count \(conf ([0-9.]+)")
    OWN = re.compile(r"^\[vlm_lora\] p\(answer digits\) = [0-9.e-]+ -> confidence ([0-9.]+)")
    own, key, post, y = [], [], [], []
    for r in rows:
        if r.get("source") != "cubicasa5k" or "vlm_lora" not in r.get("solver", ""):
            continue
        o = next((float(m.group(1)) for t in r["trace"] for m in [OWN.match(t)] if m), None)
        k = next((float(m.group(1)) for t in r["trace"] for m in [KEY.match(t)] if m), None)
        if o is None or k is None:
            continue
        own.append(o); key.append(k); post.append(r["confidence"]); y.append(1 if r["correct"] else 0)
    print(f"{path.split('/')[-1]}: {len(y)} LoRA answers")
    summary("today (key x reader)", post, y, 1)
    summary("own", own, y, 0)
    summary("key hit rate only", key, y, 0)
    summary("mean(own, key)", [(a + b) / 2 for a, b in zip(own, key)], y, 0)
    summary("min(own, key)", [min(a, b) for a, b in zip(own, key)], y, 0)


if __name__ == "__main__" and "--blends" in sys.argv:
    blends(sys.argv[1])
