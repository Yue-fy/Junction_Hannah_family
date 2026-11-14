"""Fresh probe of LINK questions (plan sheets <-> IFC model <-> storeys <-> rooms), gold computed independently of
stoa.kg: sheet counts from the file names, model counts from the IFC index, drawn counts from the plan's SVG twin
(unique data-guid per Ifc class), a room's storey from the IFC index.  Non-test models only (dev/train: smiley-west,
gdynia, warmond; esplanades = Q's v17).  Written and committed BEFORE any system run.

    python experiments/r1/kg_qa/make_probe.py   -> experiments/r1/kg_qa/probe_kg.jsonl
"""
import glob
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from stoa.data import data_root  # noqa: E402
from stoa.solvers.ifc.index import load_index  # noqa: E402

D = "data/ifc_models/"


def sheets(stem, kind):
    return sorted(os.path.basename(p) for p in glob.glob(str(data_root() / (D + stem)) + f"_{kind}-*.pdf"))


def drawn(svg, cls):
    txt = (data_root() / (D + svg)).read_text(errors="ignore")
    guids = set()
    for m in re.finditer(r"<[^>]*class=\"(Ifc[A-Za-z]+)[^\"]*\"[^>]*>", txt):
        if m.group(1).startswith(cls):
            g = re.search(r'data-guid="([^"]+)"', m.group(0))
            if g:
                guids.add(g.group(1))
    return len(guids)


def model_count(model, storey, cls):
    idx = load_index(D + model)
    s = next(s for s in idx.storeys if s.name == storey)
    return sum(1 for e in idx.in_storey(s.guid) if e.eff_cls.startswith(cls))


def storey_of_room(model, room):
    idx = load_index(D + model)
    hits = {s.name for s in idx.storeys for e in idx.in_storey(s.guid)
            if e.cls == "IfcSpace" and room.lower() in f"{e.long_name or ''} {e.name or ''}".lower()}
    return sorted(hits)


def yn(b):
    return "yes" if b else "no"


rows = []


def add(path, q, ans, typ, kind, note, accept_re=None):
    r = {"qid": f"kg{len(rows) + 1:02d}", "path": D + path, "question": q, "answer": ans,
         "unit": "count" if typ == "count" else None, "type": typ,
         "meta": {"kind": kind, "note": note, "gold_how": "make_probe.py (file names / IFC index / SVG twin)"}}
    if accept_re:
        r["meta"]["accept_re"] = accept_re
    rows.append(r)


# --- smiley-west (dev) ---------------------------------------------------------------------------------------
SW = "kit-smiley-west_ac-20-smiley-west-10-bldg"
p = SW + "_plan-03-1-og.pdf"
n = len(sheets(SW, "plan"))
add(p, "How many floor plan sheets does this building have?", n, "count", "sheets", f"plan sheets {n}")
add(p, "Welche Geschosse des Modells haben keinen eigenen Grundriss?", "Dach", "text", "storeys-without-plan",
    "IFC storeys KG, EG, 1.OG, 2.OG, Dach; plans kg/eg/1-og/2-og", r"(?i)\bdach\b|roof")
m, d = model_count(SW + ".ifc", "1.OG", "IfcWindow"), drawn(SW + "_plan-03-1-og.svg", "IfcWindow")
add(p, "Do the floor plan and the IFC model agree on the number of windows on '1.OG'?", yn(m == d), "text", "agree",
    f"model {m}, drawn {d}")
st = storey_of_room(SW + ".ifc", "ZIMMER-5-4")
add(p, "Which plan sheet shows the room 'ZIMMER-5-4'?", st[0] if len(st) == 1 else st, "text", "which-sheet",
    f"storey {st}", r"(?i)2\.?\s*OG|plan-04|2-og")
st = storey_of_room(SW + ".ifc", "Kellerraum-05-2")
add(p, "Missä kerroksessa on huone 'Kellerraum-05-2'?", st[0] if len(st) == 1 else st, "text", "which-storey",
    f"storey {st}", r"(?i)\bKG\b|keller|basement|kellari|plan-01")
m, d = model_count(SW + ".ifc", "EG", "IfcWindow"), drawn(SW + "_plan-02-eg.svg", "IfcWindow")
add(p, "How many windows on 'EG' are in the IFC model but not drawn on the EG floor plan?", m - d, "count",
    "model-minus-drawn", f"model {m} - drawn {d}")
bench = sorted(glob.glob(str(data_root() / "data/ifc_bench/smiley_west*")))
add(p, "Is this building also available as a model in another dataset?", yn(bool(bench)), "text", "same-building",
    f"ifc_bench {[os.path.basename(b) for b in bench]}")

# --- gdynia (dev) --------------------------------------------------------------------------------------------
GD = "bimspeed-gdynia_ruchu-oporu-18"
p = GD + "_plan-03-0.pdf"
n = len(sheets(GD, "elevation"))
add(p, "How many elevation drawings are there in this drawing set?", n, "count", "sheets", f"elevations {n}")
n = sum(len(sheets(GD, k)) for k in ("plan", "section", "elevation"))
add(p, "How many sheets in total belong to this building (plans, sections and elevations)?", n, "count", "sheets",
    f"all sheets {n}")
st = storey_of_room(GD + ".ifc", "Boiler room")
add(p, "On which floor plan is the boiler room?", st[0] if len(st) == 1 else st, "text", "which-sheet",
    f"storey {st}; sheet plan-02-1", r"(^|[\s'\"(])-\s?1\b|plan-02|minus one|basement|cellar")
# (gdynia/warmond plan SVGs tag only IfcSpace -> no independent drawn count; agree rows use models that tag openings)
KI = "kit-institute_ac20-institute-var-2"
m, d = model_count(KI + ".ifc", "Erdgeschoss", "IfcDoor"), drawn(KI + "_plan-02-erdgeschoss.svg", "IfcDoor")
add(KI + "_plan-02-erdgeschoss.pdf", "Le plan et la maquette IFC indiquent-ils le même nombre de portes au niveau "
    "'Erdgeschoss' ?", yn(m == d), "text", "agree", f"model {m}, drawn {d}")
TU = "tuwien-escape-route_real-world-escape-route-test-model-zdb"
m, d = model_count(TU + ".ifc", "DG1", "IfcWindow"), drawn(TU + "_plan-05-dg1.svg", "IfcWindow")
add(TU + "_plan-05-dg1.pdf", "Does the model contain more windows on storey 'DG1' than the 'DG1' floor plan shows?",
    yn(m > d), "text", "model-vs-drawn", f"model {m}, drawn {d}")
n = len(sheets(GD, "section"))
add(p, "Is there a section drawing of this building in the set?", yn(n > 0), "text", "sheets", f"sections {n}")

# --- warmond (dev) -------------------------------------------------------------------------------------------
WA = "bimspeed-warmond_ar"
p = WA + "_plan-05-2-level.pdf"
n = len(sheets(WA, "plan"))
add(p, "Wie viele Grundrisse gibt es für dieses Gebäude?", n, "count", "sheets", f"plan sheets {n}")
FZ = "kit-fzk-haus_ac20-fzk-haus"
m, d = model_count(FZ + ".ifc", "Erdgeschoss", "IfcWindow"), drawn(FZ + "_plan-01-erdgeschoss.svg", "IfcWindow")
add(FZ + "_plan-01-erdgeschoss.pdf", "Do the floor plan and the IFC model agree on the number of windows on "
    "'Erdgeschoss'?", yn(m == d), "text", "agree", f"model {m}, drawn {d}")
m, d = model_count(TU + ".ifc", "DG1", "IfcWindow"), drawn(TU + "_plan-05-dg1.svg", "IfcWindow")
add(TU + "_plan-05-dg1.pdf", "How many windows on 'DG1' does the model have that are not drawn on this plan?", m - d,
    "count", "model-minus-drawn", f"model {m} - drawn {d}")
st = storey_of_room(WA + ".ifc", "Attic")
add(p, "Which sheet shows the attic rooms?", st[0] if len(st) == 1 else st, "text", "which-sheet", f"storey {st}",
    r"(?i)attic|plan-08")
n = len(sheets(WA, "section"))
add(p, "Kuinka monta leikkauspiirustusta tästä rakennuksesta on?", n, "count", "sheets", f"sections {n}")
add(p, "Which storeys of the model have no rooms at all?",
    "Basement, Entrance, Intermediate level 1, Intermediate level 2", "text", "storeys-without-rooms",
    "IfcSpace count 0 on Basement, Entrance, Intermediate level 1/2",
    r"(?i)(?=.*basement)(?=.*entrance)(?=.*intermediate)")
m, d = model_count(KI + ".ifc", "1. Obergeschoss", "IfcDoor"), drawn(KI + "_plan-03-1-obergeschoss.svg", "IfcDoor")
add(KI + "_plan-03-1-obergeschoss.pdf", "Stimmen der Grundriss von '1. Obergeschoss' und das IFC-Modell bei der "
    "Anzahl der Türen überein?", yn(m == d), "text", "agree", f"model {m}, drawn {d}")
m, d = model_count(TU + ".ifc", "UG2", "IfcDoor"), drawn(TU + "_plan-01-ug2.svg", "IfcDoor")
add(TU + "_plan-01-ug2.pdf", "Does the 'UG2' floor plan show doors that the model does not assign to 'UG2'?",
    yn(d > m), "text", "drawn-vs-model", f"model {m}, drawn {d} (doors of another storey crossing the cut)")

if __name__ == "__main__":
    # sanity: Q's v17 gold says esplanades 1.korrus windows drawn 52, model 55
    ES = "bsc-esplanades_1807-ep-ar-v18"
    print("sanity esplanades 1.korrus windows: model", model_count(ES + ".ifc", "1.korrus", "IfcWindow"),
          "drawn", drawn(ES + "_plan-01-1-korrus.svg", "IfcWindow"))
    out = Path(__file__).parent / "probe_kg.jsonl"
    with open(out, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for r in rows:
        print(r["qid"], r["answer"], "|", r["meta"]["note"], "|", r["question"])
