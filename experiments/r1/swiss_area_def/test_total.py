"""Does 'total net floor area of all numbered indoor rooms' == sum of ROOM_OUTLINE polygon areas?

For every swiss_dwellings floor with that question: label each ROOM_OUTLINE polygon by the ROOM_TEXT
points inside it (name + number), then try several inclusion rules and report the share within 2%.
Run: python3 -I test_total.py  (stdlib only)
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from minidxf import pip, read_entities, shoelace  # noqa: E402

D = os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")
NUM = re.compile(r"^[A-Z]{0,2}\d+(\.\d+)*$")


def rooms_of(dxf):
    E = read_entities(dxf)
    polys = [e for e in E if e["layer"] == "ROOM_OUTLINE" and len(e["x"]) >= 3]
    texts = [e for e in E if e["layer"] == "ROOM_TEXT" and e["x"]]
    out = []
    for p in polys:
        inside = [t["text"] for t in texts if pip(t["x"][0], t["y"][0], p["x"], p["y"])]
        nums = [t for t in inside if NUM.match(t.strip())]
        names = [t for t in inside if not NUM.match(t.strip()) and not re.match(r"^(Whg|App)\.", t)]
        out.append({"area": shoelace(p["x"], p["y"]), "num": nums[0] if nums else None,
                    "name": names[0] if names else None, "n_texts": len(inside)})
    return out


OUTDOOR = {"Balkon", "Balcon", "Balcone", "Loggia", "Terrasse", "Terrazza", "Sitzplatz", "Dachterrasse",
           "Laubengang", "Garten", "Jardin", "Giardino", "Veranda", "Wintergarten"}
SHAFT = {"Lift", "Ascenseur", "Ascensore", "Schacht", "Gaine", "Luftraum", "Vide", "Lichthof"}


if __name__ == "__main__":
    qs = {}
    for line in open(os.path.join(D, "questions.jsonl")):
        d = json.loads(line)
        if d["path"].startswith("data/swiss_dwellings/") and d["question"].startswith("What is the total net floor area"):
            qs[d["path"]] = d["answer"]
    paths = sorted(qs)[: int(sys.argv[1]) if len(sys.argv) > 1 else 200]
    names = collections.Counter()
    rules = collections.Counter()
    misses = []
    for p in paths:
        R = rooms_of(os.path.join(D, p[:-4] + ".dxf"))
        for r in R:
            names[r["name"]] += 1
        ans = qs[p]
        OUT = OUTDOOR
        cand = {
            "all_polys": sum(r["area"] for r in R),
            "numbered": sum(r["area"] for r in R if r["num"]),
            "numbered_not_outdoor": sum(r["area"] for r in R if r["num"] and r["name"] not in OUT),
            "not_outdoor": sum(r["area"] for r in R if r["name"] not in OUT),
            "numbered_not_outdoor_not_shaft": sum(r["area"] for r in R if r["num"] and r["name"] not in OUT | SHAFT),
        }
        for k, v in cand.items():
            if abs(v - ans) <= 0.02 * abs(ans):
                rules[k] += 1
        if abs(cand["numbered_not_outdoor"] - ans) > 0.02 * ans:
            names_m = [(round(r["area"], 2), r["name"]) for r in R if r["num"] and r["name"] not in OUT]
            misses.append((p, ans, round(cand["numbered_not_outdoor"], 2), round(cand["all_polys"], 2)))
    print(f"n floors = {len(paths)}")
    for k in cand:
        print(f"  {k:22s} within 2%: {rules[k]}/{len(paths)} = {rules[k]/len(paths):.1%}")
    print("room names (top 40):", names.most_common(40))
    print("misses (first 10):", misses[:10])
