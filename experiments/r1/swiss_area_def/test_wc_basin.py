"""Toilet vs washbasin on swiss DXF FIXTURE layer. Both are 48-vertex ellipses.
Hypothesis v1 (FAILED, 5%): ellipse inside a rectangle -> washbasin (both symbols sit in a rectangle).
Hypothesis v2 (from rendering site3387, see methods.md): a washbasin's ellipse has a drain CIRCLE at its
centre; a toilet's ellipse has none (a cistern line sits next to it). Rule: ellipse containing the centre
of a FIXTURE CIRCLE -> washbasin, else toilet.
Run: python3 -I test_wc_basin.py [n] [margin]
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from minidxf import pip, read_entities  # noqa: E402

D = os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")


def split_wc_basin(dxf, margin=0.0, min_vertices=4):
    E = [e for e in read_entities(dxf) if e["layer"] == "FIXTURE" and e["type"] == "LWPOLYLINE"]
    ell = [e for e in E if len(e["x"]) == 48]
    circles = [(e["x"][0], e["y"][0]) for e in read_entities(dxf) if e["layer"] == "FIXTURE" and e["type"] == "CIRCLE"]
    wc = basin = 0
    for e in ell:
        has_drain = any(pip(x, y, e["x"], e["y"]) for x, y in circles)
        basin += has_drain
        wc += not has_drain
    return wc, basin


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    margin = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    Q = collections.defaultdict(dict)
    for line in open(os.path.join(D, "questions.jsonl")):
        d = json.loads(line)
        if d["path"].startswith("data/swiss_dwellings/"):
            if d["question"].startswith("How many toilets"):
                Q[d["path"]]["toilets"] = d["answer"]
            elif d["question"].startswith("How many washbasins"):
                Q[d["path"]]["washbasins"] = d["answer"]
    hit, tot, err = collections.Counter(), collections.Counter(), collections.defaultdict(collections.Counter)
    for p in sorted(Q)[:n]:
        wc, basin = split_wc_basin(os.path.join(D, p[:-4] + ".dxf"), margin)
        for k, v in (("toilets", wc), ("washbasins", basin)):
            if k in Q[p]:
                tot[k] += 1
                hit[k] += v == Q[p][k]
                err[k][v - Q[p][k]] += 1
    for k in ("toilets", "washbasins"):
        print(f"margin={margin} {k:10s} exact {hit[k]}/{tot[k]} = {hit[k]/tot[k]:.1%}  pred-gold {sorted(err[k].items())[:9]}")
