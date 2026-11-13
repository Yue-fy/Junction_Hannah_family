"""Swiss fixtures from the DXF FIXTURE layer (measured on 300 floors):
- bathtubs = 69-vertex LWPOLYLINEs; showers = 5-vertex LWPOLYLINEs (both 100%).
- toilets + washbasins = 48-vertex LWPOLYLINEs (ellipses). Toilet vs washbasin: test whether a 4-vertex
  rectangle (the cistern) touches the ellipse's bbox.
Run: python3 -I test_fixtures.py [n] [gap_m]
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from minidxf import read_entities  # noqa: E402

D = os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")


def bbox(e):
    return min(e["x"]), min(e["y"]), max(e["x"]), max(e["y"])


def gap(a, b):
    dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
    return max(dx, dy)


def fixtures(dxf, g=0.03):
    E = [e for e in read_entities(dxf) if e["layer"] == "FIXTURE" and e["type"] == "LWPOLYLINE"]
    ell = [bbox(e) for e in E if len(e["x"]) == 48]
    rect = [bbox(e) for e in E if len(e["x"]) == 4]
    toilets = sum(1 for b in ell if any(gap(b, r) <= g for r in rect))
    return {"toilets": toilets, "washbasins": len(ell) - toilets,
            "bathtubs": sum(1 for e in E if len(e["x"]) == 69), "showers": sum(1 for e in E if len(e["x"]) == 5)}


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    g = float(sys.argv[2]) if len(sys.argv) > 2 else 0.03
    pats = {"toilets": "How many toilets", "washbasins": "How many washbasins", "bathtubs": "How many bathtubs",
            "showers": "How many showers"}
    Q = collections.defaultdict(dict)
    for line in open(os.path.join(D, "questions.jsonl")):
        d = json.loads(line)
        if d["path"].startswith("data/swiss_dwellings/"):
            for k, v in pats.items():
                if d["question"].startswith(v):
                    Q[d["path"]][k] = d["answer"]
    hit, tot, err = collections.Counter(), collections.Counter(), collections.defaultdict(collections.Counter)
    for p in sorted(Q)[:n]:
        f = fixtures(os.path.join(D, p[:-4] + ".dxf"), g)
        for k, a in Q[p].items():
            tot[k] += 1
            hit[k] += f[k] == a
            err[k][f[k] - a] += 1
    for k in pats:
        print(f"gap={g} {k:10s} exact {hit[k]}/{tot[k]} = {hit[k]/max(1, tot[k]):.1%}  pred-gold {sorted(err[k].items())[:8]}")
