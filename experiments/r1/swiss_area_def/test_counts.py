"""Swiss count templates from DXF layers: which simple rule reproduces the reference count?
Run: python3 -I test_counts.py [n_floors]
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from minidxf import read_entities  # noqa: E402

D = os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")
KEYS = {
    "apartments": re.compile(r"How many apartments"),
    "doors": re.compile(r"How many doors"),
    "windows": re.compile(r"How many windows"),
    "toilets": re.compile(r"How many toilets"),
    "washbasins": re.compile(r"How many washbasins"),
    "bathtubs": re.compile(r"How many bathtubs"),
    "showers": re.compile(r"How many showers"),
    "label": re.compile(r"How many rooms labelled '(.+)'"),
}


def feats(dxf):
    E = read_entities(dxf)
    c = collections.Counter((e["type"], e["layer"]) for e in E)
    # fixture polylines by vertex count, circles count
    fx = collections.Counter(len(e["x"]) for e in E if e["layer"] == "FIXTURE" and e["type"] == "LWPOLYLINE")
    texts = collections.Counter(e["text"].strip() for e in E if e["layer"] == "ROOM_TEXT" and e["text"])
    return c, fx, texts


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    Q = collections.defaultdict(list)
    for line in open(os.path.join(D, "questions.jsonl")):
        d = json.loads(line)
        if d["path"].startswith("data/swiss_dwellings/") and d["type"] == "count":
            Q[d["path"]].append(d)
    rules = {
        "apartments": {"UNIT_OUTLINE polys": lambda c, fx, t, a: c[("LWPOLYLINE", "UNIT_OUTLINE")],
                       "Whg/App texts": lambda c, fx, t, a: sum(v for k, v in t.items() if re.match(r"^(Whg|App)\.", k))},
        "doors": {"DOOR arcs": lambda c, fx, t, a: c[("ARC", "DOOR")],
                  "DOOR polys": lambda c, fx, t, a: c[("LWPOLYLINE", "DOOR")],
                  "DOOR polys/2": lambda c, fx, t, a: c[("LWPOLYLINE", "DOOR")] / 2},
        "windows": {"WINDOW polys": lambda c, fx, t, a: c[("LWPOLYLINE", "WINDOW")],
                    "WINDOW polys/3": lambda c, fx, t, a: c[("LWPOLYLINE", "WINDOW")] / 3},
        "label": {"ROOM_TEXT == label": lambda c, fx, t, a: t[a]},
    }
    hit = collections.Counter()
    tot = collections.Counter()
    ratio = collections.defaultdict(list)
    for p in sorted(Q)[:n]:
        c, fx, t = feats(os.path.join(D, p[:-4] + ".dxf"))
        for d in Q[p]:
            for k, rx in KEYS.items():
                m = rx.search(d["question"])
                if not m:
                    continue
                arg = m.group(1) if m.groups() else None
                for name, f in rules.get(k, {}).items():
                    v = f(c, fx, t, arg)
                    tot[(k, name)] += 1
                    hit[(k, name)] += v == d["answer"]
                if k in ("doors", "windows", "toilets", "washbasins", "bathtubs", "showers") and d["answer"]:
                    ratio[k].append((d["answer"], c[("ARC", "DOOR")], c[("LWPOLYLINE", "DOOR")], c[("LWPOLYLINE", "WINDOW")],
                                     c[("CIRCLE", "FIXTURE")], c[("LWPOLYLINE", "FIXTURE")]))
    for k in sorted(tot):
        print(f"{k[0]:10s} {k[1]:22s} exact {hit[k]}/{tot[k]} = {hit[k]/tot[k]:.1%}")
    for k in ("doors", "windows", "toilets", "washbasins"):
        print(k, "(answer, door arcs, door polys, window polys, fixture circles, fixture polys):", ratio[k][:8])
