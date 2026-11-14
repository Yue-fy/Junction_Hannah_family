"""Offline: can a combination of the pipeline's (LoRA) count and R1's CC5K detector count fix cubicasa windows/doors?

python experiments/F/window_combo.py PIPE_RUN.jsonl [--concept windows]
Reads stored predictions only (no model calls). cc5k counts: $JUNCTION_SHARED/artifacts/R1/cc5k_counts.jsonl
(cc5k_list says whether the drawing was in CubiCasa5K's own train list = leaky for the detector).
"""
import argparse, json, os, re, statistics as st
from collections import Counter, defaultdict
from pathlib import Path

SH = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
KEYS = {"windows": re.compile(r"window|ikkun", re.I), "doors": re.compile(r"\bdoors?\b|\bove", re.I),
        "wc_seats": re.compile(r"toilet|wc-istuin", re.I), "sinks": re.compile(r"sink|allas|altaa", re.I)}

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--concept", default="windows")
a = ap.parse_args()
cc = {}
for l in open(SH / "artifacts/R1/cc5k_counts.jsonl"):
    d = json.loads(l)
    cc[d["path"]] = d
rows = [json.loads(l) for l in open(a.run)]
rx = KEYS[a.concept]
rows = [r for r in rows if r["source"] == "cubicasa5k" and r["type"] == "count" and rx.search(r["question"])
        and not re.search(r"bath|shower|suihku|kylpy", r["question"], re.I)]
print(f"{a.concept}: {len(rows)} questions on {len({r['path'] for r in rows})} drawings")
strata = defaultdict(list)
for r in rows:
    d = cc.get(r["path"])
    if not d or a.concept not in d["counts"]:
        continue
    strata[d["cc5k_list"]].append((r, d["counts"][a.concept]["count"], d["counts"][a.concept].get("confidence")))
for lst, items in sorted(strata.items()):
    g = [r["gold"] for r, _, _ in items]
    p = [r["value"] if isinstance(r["value"], (int, float)) else -1 for r, _, _ in items]
    c = [x for _, x, _ in items]
    n = len(items)
    def acc(pred): return 100 * sum(int(round(x)) == y for x, y in zip(pred, g)) / n
    print(f"\n[{lst}] n={n}  gold mean {st.mean(g):.2f}  pipe mean {st.mean(p):.2f}  cc5k mean {st.mean(c):.2f}")
    print(f"  pipeline {acc(p):.1f}  cc5k {acc(c):.1f}  max {acc([max(x, y) for x, y in zip(p, c)]):.1f}  "
          f"min {acc([min(x, y) for x, y in zip(p, c)]):.1f}  mean-round {acc([(x + y) / 2 + 1e-9 for x, y in zip(p, c)]):.1f}  "
          f"oracle {100 * sum(x == t or y == t for x, y, t in zip(p, c, g)) / n:.1f}")
    for k in (-2, -1, 1, 2):
        print(f"  pipeline{k:+d} {acc([x + k for x in p]):.1f}  cc5k{k:+d} {acc([x + k for x in c]):.1f}", end="")
    print()
    agree = [(x, t) for x, y, t in zip(p, c, g) if x == y]
    print(f"  agree {len(agree)}/{n} right {sum(x == t for x, t in agree)}")
    print("  error pipe-gold:", sorted(Counter(x - t for x, t in zip(p, g)).items()))
    print("  error cc5k-gold:", sorted(Counter(x - t for x, t in zip(c, g)).items()))
    print("  solvers:", Counter(r["solver"] for r, _, _ in items).most_common(4))
