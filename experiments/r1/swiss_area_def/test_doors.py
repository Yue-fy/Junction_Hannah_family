"""Doors on swiss DXF: one door = one leaf arc, except double doors whose two leaf arcs meet in the middle.
Rule: merge two DOOR arcs into one door when their radii agree within 15% and an endpoint of one arc lies
within `tol` metres of an endpoint of the other (the two leaves meet in the middle). Run: python3 -I test_doors.py [n] [tol]
"""
import collections
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from minidxf import read_entities  # noqa: E402

D = os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")


def ends(a):
    cx, cy, r = a["x"][0], a["y"][0], a["r"]
    return [(cx + r * math.cos(math.radians(t)), cy + r * math.sin(math.radians(t))) for t in a["a"]]


def count_doors(dxf, tol=0.05):
    arcs = [e for e in read_entities(dxf) if e["layer"] == "DOOR" and e["type"] == "ARC" and e["r"]]
    parent = list(range(len(arcs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(arcs)):
        for j in range(i + 1, len(arcs)):
            a, b = arcs[i], arcs[j]
            if abs(a["r"] - b["r"]) > 0.15 * max(a["r"], b["r"]):
                continue
            if min(math.dist(p, q) for p in ends(a) for q in ends(b)) <= tol:
                parent[find(i)] = find(j)
    return len({find(i) for i in range(len(arcs))}), len(arcs)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    tol = float(sys.argv[2]) if len(sys.argv) > 2 else 0.10
    Q = {}
    for line in open(os.path.join(D, "questions.jsonl")):
        d = json.loads(line)
        if d["path"].startswith("data/swiss_dwellings/") and d["question"].startswith("How many doors"):
            Q[d["path"]] = d["answer"]
    hit = raw = 0
    err = collections.Counter()
    for p in sorted(Q)[:n]:
        k, m = count_doors(os.path.join(D, p[:-4] + ".dxf"), tol)
        hit += k == Q[p]
        raw += m == Q[p]
        err[k - Q[p]] += 1
    N = min(n, len(Q))
    print(f"tol={tol}: paired-arc rule exact {hit}/{N} = {hit/N:.1%} (raw arcs {raw/N:.1%}); pred-gold: {sorted(err.items())}")
