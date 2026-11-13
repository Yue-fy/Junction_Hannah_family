"""Apartment and per-room net area templates on swiss_dwellings, from DXF polygons.

- "net floor area of apartment X ... except balconies, loggias, terraces and other outdoor spaces":
  rooms whose label point lies inside the UNIT_OUTLINE that contains the 'Whg. X' / 'App. X' text.
- "net floor area of room N ('Name')": the ROOM_OUTLINE polygon containing room-number text N.
- "total net area of all rooms labelled 'Name'": sum of polygons with that name.
Run: python3 -I test_apartment.py [n_floors]
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
APT = re.compile(r"^(Whg|App|Appartement|Wohnung|Apt)\.?\s*([A-Z0-9]+)$")


def parse(dxf):
    E = read_entities(dxf)
    polys = [e for e in E if e["layer"] == "ROOM_OUTLINE" and len(e["x"]) >= 3]
    units = [e for e in E if e["layer"] == "UNIT_OUTLINE" and len(e["x"]) >= 3]
    texts = [e for e in E if e["layer"] == "ROOM_TEXT" and e["x"]]
    rooms = []
    for p in polys:
        inside = [t for t in texts if pip(t["x"][0], t["y"][0], p["x"], p["y"])]
        nums = [t["text"].strip() for t in inside if NUM.match(t["text"].strip())]
        names = [t["text"] for t in inside if not NUM.match(t["text"].strip()) and not APT.match(t["text"].strip())]
        # anchor point = first text inside, else first vertex
        ax, ay = (inside[0]["x"][0], inside[0]["y"][0]) if inside else (sum(p["x"]) / len(p["x"]), sum(p["y"]) / len(p["y"]))
        rooms.append({"area": shoelace(p["x"], p["y"]), "num": nums[0] if nums else None,
                      "name": names[0] if names else None, "ax": ax, "ay": ay})
    apts = {}
    for u in units:
        lab = [APT.match(t["text"].strip()).group(2) for t in texts
               if APT.match(t["text"].strip()) and pip(t["x"][0], t["y"][0], u["x"], u["y"])]
        if lab:
            apts[lab[0]] = u
    return rooms, apts


def within(a, b):
    return abs(a - b) <= 0.02 * abs(b)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    Q = collections.defaultdict(list)
    pat_apt = re.compile(r"net floor area of apartment (\w+) in m²")
    pat_room = re.compile(r"net floor area of room (\S+) \('(.+)'\) in m²")
    pat_lab = re.compile(r"total net area in m² of all rooms labelled '(.+)'")
    for line in open(os.path.join(D, "questions.jsonl")):
        d = json.loads(line)
        if d["path"].startswith("data/swiss_dwellings/") and d["type"] == "area":
            Q[d["path"]].append(d)
    paths = sorted(Q)[:n]
    score = collections.Counter()
    tot = collections.Counter()
    ex = collections.defaultdict(list)
    for p in paths:
        rooms, apts = parse(os.path.join(D, p[:-4] + ".dxf"))
        for d in Q[p]:
            q, ans = d["question"], d["answer"]
            m = pat_apt.search(q)
            if m:
                u = apts.get(m.group(1))
                pred = None
                if u is not None:
                    pred = sum(r["area"] for r in rooms if r["num"] and r["name"] not in OUTDOOR
                               and pip(r["ax"], r["ay"], u["x"], u["y"]))
                tot["apartment"] += 1
                score["apartment"] += pred is not None and within(pred, ans)
                if pred is None or not within(pred, ans):
                    ex["apartment"].append((p[21:], m.group(1), ans, pred and round(pred, 2), sorted(apts)))
                continue
            m = pat_room.search(q)
            if m:
                cand = [r["area"] for r in rooms if r["num"] == m.group(1)]
                pred = sum(cand) if cand else None
                tot["room"] += 1
                score["room"] += pred is not None and within(pred, ans)
                if pred is None or not within(pred, ans):
                    ex["room"].append((p[21:], m.group(1), m.group(2), ans, pred, len(cand)))
                continue
            m = pat_lab.search(q)
            if m:
                pred = sum(r["area"] for r in rooms if r["name"] == m.group(1))
                tot["label"] += 1
                score["label"] += within(pred, ans)
                if not within(pred, ans):
                    ex["label"].append((p[21:], m.group(1), ans, round(pred, 2)))
                continue
            tot["other:" + q[:60]] += 1
    for k in tot:
        print(f"{k:70s} {score[k]}/{tot[k]} = {score[k]/tot[k]:.1%}")
    for k, v in ex.items():
        print(k, "misses e.g.", v[:6])
