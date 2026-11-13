"""Which model elements does a rendered ifc_models plan draw? Compare per storey and class:
model count (all elements contained in the storey) vs elements whose z-range crosses the cut plane at
elevation + h, vs elements drawn on the plan SVG (by GUID, split into same-storey / other-storey).
Usage: python experiments/w1/cut_check.py  -> prints agreement per h and the worst plans."""
import collections, sys
from pathlib import Path
from stoa.data import data_root
from stoa.solvers.ifc.index import load_index
from stoa.solvers.ifc.plan2d import plan_items, plans_of_model

CLASSES = {"doors": ("IfcDoor",), "windows": ("IfcWindow",), "walls": ("IfcWall", "IfcWallStandardCase"),
           "columns": ("IfcColumn",), "rooms": ("IfcSpace",)}
HS = (0.6, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5)
models = sorted({str(p.relative_to(data_root())) for p in (data_root() / "data/ifc_models").glob("*.ifc")
                 if not p.name.startswith("resbim")})
agree = collections.Counter(); n = 0; rows = []
for m in models:
    try:
        idx = load_index(m)
    except Exception as ex:
        continue
    for sg, plan in plans_of_model(m).items():
        items = plan_items(plan)
        if not items:
            continue
        st = next(s for s in idx.storeys if s.guid == sg)
        tagged = {it.cls for it in items.values()}
        for what, cls in CLASSES.items():
            if not (set(cls) & tagged):
                continue  # class not tagged in this SVG: no data
            on = [e for e in idx.in_storey(sg) if e.cls in cls]
            drawn_same = sum(1 for g, it in items.items() if it.cls in cls and idx.elements.get(g) and idx.elements[g].storey == sg)
            drawn_all = sum(1 for it in items.values() if it.cls in cls)
            r = {"plan": plan, "storey": st.name, "what": what, "model": len(on), "drawn_same": drawn_same, "drawn_all": drawn_all}
            for h in HS:
                z = (st.elevation or 0.0) + h
                r[h] = sum(1 for e in on if e.geo and e.geo.bbox and e.geo.bbox[2] - 1e-6 <= z <= e.geo.bbox[5] + 1e-6)
            rows.append(r)
print(len(rows), "plan x class rows")
print("model == drawn_same:", sum(r["model"] == r["drawn_same"] for r in rows), " model == drawn_all:", sum(r["model"] == r["drawn_all"] for r in rows))
for h in HS:
    print(f"h={h}: crossing == drawn_same {sum(r[h] == r['drawn_same'] for r in rows)}")
bad = [r for r in rows if r["model"] != r["drawn_all"]]
for r in bad[:60]:
    print(Path(r["plan"]).name[:60], r["storey"], r["what"], "model", r["model"], "drawn", r["drawn_same"], "/", r["drawn_all"], "cross@1.2", r[1.2], "@1.0", r[1.0])
print("--- rows where crossing@1.2 != drawn_same")
for r in rows:
    if r[1.2] != r["drawn_same"]:
        print(Path(r["plan"]).name[:60], r["storey"], r["what"], "model", r["model"], "drawn", r["drawn_same"], "/", r["drawn_all"], "cross@1.2", r[1.2], "@1.3", r[1.3], "@1.1", r[1.1])
