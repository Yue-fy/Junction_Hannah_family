"""Score experiments/F/cc5k_scale_probe.py output: accuracy per template x (upscale factor, kernel), fit/check halves.

python experiments/F/cc5k_scale_score.py $JUNCTION_SHARED/artifacts/F/cc5k_scale
Also: an adaptive rule (upscale only when the image is small) and a sanity check vs R1's cached counts (1.0, FROZEN k).
"""
import glob, hashlib, json, os, sys
from collections import defaultdict
D = sys.argv[1]
recs = [json.loads(l) for f in sorted(glob.glob(os.path.join(D, "probe-*.jsonl"))) for l in open(f)]
cached = {json.loads(l)["path"]: json.loads(l) for l in open(os.path.join(os.environ.get(
    "JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"), "artifacts/R1/cc5k_counts.jsonl"))}
FROZEN_K = {"windows": 5, "doors": 0, "wc_seats": 5, "sinks": 5}
half = lambda p: "fit" if int(hashlib.md5(p.encode()).hexdigest(), 16) % 2 == 0 else "check"
print(f"{len(recs)} drawings probed; mean sec per pass:",
      {f: round(sum(r.get(f'sec|{f}', 0) for r in recs) / max(1, len(recs)), 1) for f in ("1.0", "1.5", "2.0")})
same = sum(r["counts"][f"{t}|1.0|{FROZEN_K[t]}"] == cached[r["path"]]["counts"][t]["count"]
           for r in recs for t in r["gold"]) ; tot = sum(len(r["gold"]) for r in recs)
print(f"sanity: (x1.0, FROZEN k) reproduces R1's cached count on {same}/{tot}")

def rule(r, t, f, k, small=None):
    if small is not None and max(r["size"]) >= small:
        f, k = 1.0, FROZEN_K[t]
    return r["counts"][f"{t}|{f}|{k}"]

for t in ("windows", "doors", "wc_seats", "sinks"):
    rs = [r for r in recs if t in r["gold"]]
    if not rs:
        continue
    print(f"\n{t}: n={len(rs)} (fit {sum(half(r['path']) == 'fit' for r in rs)})   acc fit / check   [mean signed error]")
    rows = []
    for f in ("1.0", "1.5", "2.0"):
        for k in (0, 3, 5, 7):
            a = defaultdict(list)
            for r in rs:
                c = r["counts"][f"{t}|{f}|{k}"]
                a[half(r["path"])].append((c == r["gold"][t], c - r["gold"][t]))
            fa = 100 * sum(x for x, _ in a["fit"]) / max(1, len(a["fit"]))
            ca = 100 * sum(x for x, _ in a["check"]) / max(1, len(a["check"]))
            bias = sum(e for v in a.values() for _, e in v) / len(rs)
            mark = " <- FROZEN" if (f == "1.0" and k == FROZEN_K[t]) else ""
            rows.append((fa, f, k))
            print(f"   x{f} k={k}: {fa:5.1f} / {ca:5.1f}   [{bias:+.2f}]{mark}")
    fa, f, k = max(rows)
    for small in (1200, 1600, 99999):
        a = defaultdict(list)
        for r in rs:
            a[half(r["path"])].append(rule(r, t, f, k, small) == r["gold"][t])
        print(f"   best-on-fit x{f} k={k} only when long side < {small}: fit {100*sum(a['fit'])/len(a['fit']):.1f} / check {100*sum(a['check'])/len(a['check']):.1f}")
