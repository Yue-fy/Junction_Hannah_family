"""Fit vlm_direct's confidence map (raw answer-digit probability -> accuracy) on a TRAIN predictions file.

Run vlm_direct with `--solver-arg conf=raw` on a train sample, then:
    $JUNCTION_VENV/bin/python experiments/r2/fit_conf.py artifacts/eval/<run>.jsonl [--bins 6]
Prints per kind (count / measure): quantile bins with accuracy (made monotone by pool-adjacent-violators),
AUROC of the raw probability, ECE before/after, and a CONF_MAP literal to paste into vlm_direct.py.
With --check <dev predictions run with conf=logprob>, reports AUROC/ECE of the mapped confidence there.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SHARED = Path("/home/fangy4/work/projects/junction-shared")


def load(run: str) -> list[dict]:
    p = Path(run)
    if not p.exists():
        p = SHARED / "artifacts/eval" / (run if run.endswith(".jsonl") else run + ".jsonl")
    rows = []
    for line in open(p, encoding="utf-8"):
        r = json.loads(line)
        if r.get("correct") is None or r.get("value") is None:
            continue
        tr = " ".join(r.get("trace") or [])
        m = re.search(r"p\(answer digits\) = ([0-9.]+)", tr)
        if not m:
            continue
        r["_p"] = float(m.group(1))
        r["_kind"] = "count" if "kind=count" in tr else "measure"
        rows.append(r)
    return rows


def auroc(ps: list[float], ys: list[bool]) -> float:
    pos = [p for p, y in zip(ps, ys) if y]
    neg = [p for p, y in zip(ps, ys) if not y]
    if not pos or not neg:
        return float("nan")
    win = sum((1.0 if a > b else 0.5 if a == b else 0.0) for a in pos for b in neg)
    return win / (len(pos) * len(neg))


def ece(conf: list[float], ys: list[bool], bins: int = 10) -> float:
    tot, n = 0.0, len(ys)
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, c in enumerate(conf) if (lo < c <= hi) or (b == 0 and c == 0)]
        if idx:
            tot += len(idx) / n * abs(sum(conf[i] for i in idx) / len(idx) - sum(ys[i] for i in idx) / len(idx))
    return tot


def fit(ps: list[float], ys: list[bool], bins: int) -> list[tuple[float, float]]:
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    k = max(1, len(order) // bins)
    blocks = []  # [upper edge, n, correct]
    for s in range(0, len(order), k):
        ids = order[s:s + k]
        blocks.append([ps[ids[-1]], len(ids), sum(ys[i] for i in ids)])
    merged = []  # bins sharing an upper edge (many answers have p == 1.0) are one bin
    for b in blocks:
        if merged and b[0] <= merged[-1][0]:
            merged[-1] = [b[0], merged[-1][1] + b[1], merged[-1][2] + b[2]]
        else:
            merged.append(b)
    blocks = merged
    if len(blocks) > 1 and blocks[-1][1] < k // 2:  # merge a small tail
        e, n, c = blocks.pop()
        blocks[-1] = [e, blocks[-1][1] + n, blocks[-1][2] + c]
    # pool adjacent violators: accuracy must not decrease with p
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][2] / blocks[i][1] > blocks[i + 1][2] / blocks[i + 1][1]:
            blocks[i] = [blocks[i + 1][0], blocks[i][1] + blocks[i + 1][1], blocks[i][2] + blocks[i + 1][2]]
            del blocks[i + 1]
            i = max(0, i - 1)
        else:
            i += 1
    out = [(round(e, 6), round((c + 1) / (n + 2), 3)) for e, n, c in blocks]  # Laplace-smoothed
    out[-1] = (1.0, out[-1][1])
    for i in range(1, len(out)):  # smoothing can break monotonicity of tiny bins
        out[i] = (out[i][0], max(out[i][1], out[i - 1][1]))
    return out


def apply(table: list[tuple[float, float]], p: float) -> float:
    for e, a in table:
        if p <= e:
            return a
    return table[-1][1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--bins", type=int, default=6)
    ap.add_argument("--check", help="dev predictions run with conf=logprob (mapped) to report AUROC/ECE")
    a = ap.parse_args()
    rows = load(a.run)
    cmap = {}
    for kind in ("count", "measure"):
        rs = [r for r in rows if r["_kind"] == kind]
        if len(rs) < 30:
            print(f"{kind}: only {len(rs)} rows, skipped")
            continue
        ps, ys = [r["_p"] for r in rs], [bool(r["correct"]) for r in rs]
        t = fit(ps, ys, a.bins)
        cmap[kind] = t
        mapped = [apply(t, p) for p in ps]
        print(f"{kind}: n={len(rs)} acc={sum(ys) / len(ys):.3f} AUROC(raw)={auroc(ps, ys):.3f} "
              f"ECE raw={ece(ps, ys):.3f} const0.3={ece([0.3] * len(ys), ys):.3f} mapped={ece(mapped, ys):.3f}")
        for e, acc in t:
            print(f"   p <= {e:.3f}: {acc:.3f}")
        by_src: dict[str, list] = {}
        for r in rs:
            by_src.setdefault(r["source"], []).append(r)
        for s, rr in sorted(by_src.items()):
            if len(rr) >= 20:
                print(f"   {s:16s} n={len(rr):4d} acc={sum(r['correct'] for r in rr) / len(rr):.3f} "
                      f"AUROC={auroc([r['_p'] for r in rr], [bool(r['correct']) for r in rr]):.3f}")
    print("CONF_MAP =", json.dumps({k: [list(x) for x in v] for k, v in cmap.items()}))
    if a.check:
        rows = load(a.check)
        cs = [r["confidence"] for r in rows]
        ys = [bool(r["correct"]) for r in rows]
        print(f"check {a.check}: n={len(rows)} AUROC={auroc(cs, ys):.3f} ECE={ece(cs, ys):.3f} "
              f"mean conf={sum(cs) / len(cs):.3f} acc={sum(ys) / len(ys):.3f}")


if __name__ == "__main__":
    main()
