"""Hypothesis: ROOM_OUTLINE polygons with no text that lie inside a labelled room are holes (columns,
shafts) and must be subtracted from that room. Test on the 'total' and per-room templates.
Run: python3 -I test_holes.py [n_floors]
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from minidxf import pip, read_entities, shoelace  # noqa: E402
from test_total import NUM, OUTDOOR  # noqa: E402

D = os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")


def rooms_with_holes(dxf):
    E = read_entities(dxf)
    polys = [e for e in E if e["layer"] == "ROOM_OUTLINE" and len(e["x"]) >= 3]
    texts = [e for e in E if e["layer"] == "ROOM_TEXT" and e["x"]]
    R = []
    for p in polys:
        inside = [t["text"].strip() for t in texts if pip(t["x"][0], t["y"][0], p["x"], p["y"])]
        nums = [t for t in inside if NUM.match(t)]
        names = [t for t in inside if not NUM.match(t) and not re.match(r"^(Whg|App)\.", t)]
        R.append({"p": p, "area": shoelace(p["x"], p["y"]), "num": nums[0] if nums else None,
                  "name": names[0] if names else None, "n": len(inside), "holes": 0.0, "is_hole": False})
    # a polygon with no text whose vertices all lie inside a texted polygon is a hole of it
    for h in R:
        if h["n"]:
            continue
        for r in R:
            if r is h or not r["n"] or r["area"] <= h["area"]:
                continue
            xs, ys = h["p"]["x"], h["p"]["y"]
            cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
            if pip(cx, cy, r["p"]["x"], r["p"]["y"]):
                r["holes"] += h["area"]
                h["is_hole"] = True
                break
    return R


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    Q = collections.defaultdict(list)
    for line in open(os.path.join(D, "questions.jsonl")):
        d = json.loads(line)
        if d["path"].startswith("data/swiss_dwellings/") and d["type"] == "area":
            Q[d["path"]].append(d)
    pat_room = re.compile(r"net floor area of room (\S+) \('(.+)'\) in m²")
    S = collections.Counter()
    T = collections.Counter()
    for p in sorted(Q)[:n]:
        R = rooms_with_holes(os.path.join(D, p[:-4] + ".dxf"))
        for d in Q[p]:
            q, a = d["question"], d["answer"]
            if q.startswith("What is the total net floor area"):
                inc = [r for r in R if r["num"] and r["name"] not in OUTDOOR]
                for k, v in {"no_holes": sum(r["area"] for r in inc),
                             "minus_holes": sum(r["area"] - r["holes"] for r in inc)}.items():
                    T["total/" + k] += 1
                    S["total/" + k] += abs(v - a) <= 0.02 * a
            m = pat_room.search(q)
            if m:
                c = [r for r in R if r["num"] == m.group(1)]
                if c:
                    for k, v in {"no_holes": sum(r["area"] for r in c),
                                 "minus_holes": sum(r["area"] - r["holes"] for r in c)}.items():
                        T["room/" + k] += 1
                        S["room/" + k] += abs(v - a) <= 0.02 * a
    for k in sorted(T):
        print(f"{k:22s} {S[k]}/{T[k]} = {S[k]/T[k]:.1%}")
