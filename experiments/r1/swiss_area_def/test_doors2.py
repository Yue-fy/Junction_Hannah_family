"""Doors on swiss DXF, take 2: each door is drawn as one closed 5-vertex rectangle (+ a 2-vertex line +
leaf arcs), and some doors are drawn twice (exact duplicates). Measured: the UNIQUE count fails (6%);
the RAW count of 5-vertex DOOR polylines is the rule. Also compare unique arcs.
Run: python3 -I test_doors2.py [n]
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from minidxf import read_entities  # noqa: E402

D = os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")


def key(e):
    return tuple(sorted((round(x, 2), round(y, 2)) for x, y in zip(e["x"], e["y"])))


def door_feats(dxf):
    E = [e for e in read_entities(dxf) if e["layer"] == "DOOR"]
    rects = {key(e) for e in E if e["type"] == "LWPOLYLINE" and len(e["x"]) >= 4}
    arcs = {(round(e["x"][0], 2), round(e["y"][0], 2), round(e["r"], 2)) for e in E if e["type"] == "ARC"}
    nv = collections.Counter(len(e["x"]) for e in E if e["type"] == "LWPOLYLINE")
    n5 = sum(1 for e in E if e["type"] == "LWPOLYLINE" and len(e["x"]) == 5)
    return n5, len(arcs), nv


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    Q = {}
    for line in open(os.path.join(D, "questions.jsonl")):
        d = json.loads(line)
        if d["path"].startswith("data/swiss_dwellings/") and d["question"].startswith("How many doors"):
            Q[d["path"]] = d["answer"]
    hr = ha = 0
    err = collections.Counter()
    nvs = collections.Counter()
    bad = []
    for p in sorted(Q)[:n]:
        r, a, nv = door_feats(os.path.join(D, p[:-4] + ".dxf"))
        nvs.update(nv)
        hr += r == Q[p]
        ha += a == Q[p]
        err[r - Q[p]] += 1
        if r != Q[p] and len(bad) < 5:
            bad.append((p[21:], Q[p], r, a, dict(nv)))
    N = min(n, len(Q))
    print(f"raw 5-vertex DOOR polylines exact {hr}/{N} = {hr/N:.1%}; unique arcs {ha/N:.1%}; rect-gold {sorted(err.items())}")
    print("vertex counts of DOOR polylines:", nvs.most_common(6))
    print("misses:", bad)
