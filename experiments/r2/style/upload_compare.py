"""Paired summary of upload-probe runs (Q's experiments/q/upload_dev.py rows): accuracy, confident answers and misses,
located evidence, cost; wins/losses vs the first run. Rows pair by qid; a control run (dataset paths) pairs by meta.base +
question. Optional --guessed restricts to images stoa.style calls CubiCasa at p >= 0.8.

    PYTHONPATH=. python experiments/r2/style/upload_compare.py RUN_A.jsonl RUN_B.jsonl ... [--control Q_RUN.jsonl]
"""
import json
import sys

args = sys.argv[1:]
control = None
if "--control" in args:
    i = args.index("--control")
    control = args[i + 1]
    del args[i:i + 2]
guessed_only = "--guessed" in args
args = [a for a in args if a != "--guessed"]


def load(fn, kind=None):
    out = {}
    for line in open(fn, encoding="utf-8"):
        d = json.loads(line)
        if kind and d.get("meta", {}).get("kind") != kind:
            continue
        out[(d["meta"]["base"], d["question"])] = d
    return out


runs = [(fn.split("-")[-1][:4], load(fn, "updev:upload")) for fn in args]
if control:
    runs.append(("ctrl", load(control, "updev:control")))
keys = set.intersection(*[set(r) for _, r in runs])
if guessed_only:
    from stoa.style import guess_style

    g = {}
    keys = {k for k in keys if (g.setdefault(runs[0][1][k]["path"], guess_style(runs[0][1][k]["path"])))[0] == "cubicasa5k"
            and g[runs[0][1][k]["path"]][1] >= 0.8}
print(f"{len(keys)} paired questions" + (" (images guessed CubiCasa at p>=0.8)" if guessed_only else ""))
print(f"{'run':6} {'acc':>6} {'conf>=.8':>9} {'@acc':>6} {'conf-miss':>9} {'0.5-0.8':>8} {'evid':>6} {'$/1k':>7}  vs first: W/L")
base = runs[0][1]
for name, r in runs:
    rows = [r[k] for k in keys]
    n = len(rows)
    acc = sum(bool(x["correct"]) for x in rows)
    hi = [x for x in rows if (x["confidence"] or 0) >= 0.8]
    mid = sum(0.5 <= (x["confidence"] or 0) < 0.8 for x in rows)
    ev = sum(bool(x["evidence"]) for x in rows)
    usd = sum((x.get("cost") or {}).get("usd", 0) or 0 for x in rows) / n * 1000
    w = sum(bool(r[k]["correct"]) and not base[k]["correct"] for k in keys)
    lo = sum(not r[k]["correct"] and bool(base[k]["correct"]) for k in keys)
    hiacc = sum(bool(x["correct"]) for x in hi)
    print(f"{name:6} {acc / n * 100:6.1f} {len(hi):9d} {hiacc / max(1, len(hi)) * 100:6.1f} {len(hi) - hiacc:9d} {mid:8d} "
          f"{ev / n * 100:6.1f} {usd:7.3f}  {w}/{lo}")
