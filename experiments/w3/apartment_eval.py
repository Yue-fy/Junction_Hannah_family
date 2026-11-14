"""Apartment net floor area on Swiss PNG plans (raster only: unit boundary + printed room areas), CPU only.

Drawings = Swiss PNGs whose text layer is already cached (artifacts/W3/textlayer); questions = the dataset's
"net floor area of apartment X" (English; the gold is the DXF room sum). Reports per split of the drawing so the
tuning drawings (dev/smoke) and the untouched ones (train) are separate.
    $JUNCTION_VENV/bin/python experiments/w3/apartment_eval.py [--mode sum|interior|hybrid]
"""
import argparse
import glob
import json
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from stoa.solvers.raster import apartment as A, scalebar as SB, textlayer as T  # noqa: E402

SH = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
DATA = Path(os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset"))
ap = argparse.ArgumentParser()
ap.add_argument("--mode", default="hybrid")
ap.add_argument("--kinds", type=int, default=1, help="1 = apartments only, 3 = + floor totals + labelled sums")
ap.add_argument("--out", default=str(SH / "artifacts/W3/apartment_eval.jsonl"))
ap.add_argument("--verbose", action="store_true")
a = ap.parse_args()

split = {}
for s in ("train", "dev", "smoke", "test"):
    f = SH / "results/splits" / f"{s}.jsonl"
    if f.exists() and s != "test":
        for line in open(f):
            r = json.loads(line)
            if "group" in r:
                split.setdefault(r["group"], s)
stems = {}
for f in glob.glob(str(SH / "artifacts/W3/textlayer/*.json")):
    p = json.load(open(f))["path"]
    if "swiss_dwellings" in p and p.endswith(".png"):
        stems[Path(p).stem] = p
qs = {}
for line in open(DATA / "questions.jsonl"):
    q = json.loads(line)
    st = Path(q.get("path", "")).stem
    kinds = ("What is the net floor area of apartment", "What is the total net floor area in m² of all numbered",
             "What is the total net area in m² of all rooms labelled")
    if st in stems and q["question"].startswith(kinds[:a.kinds]):
        qs.setdefault((st, q["question"]), q)
rows = []
for (st, text), q in sorted(qs.items()):
    p = stems[st]
    sp = split.get("swiss_dwellings/" + st.split("_")[0], "?")
    tl = T.text_layer(p)
    try:
        bar = SB.best_bar(p, prefer="m", layer=tl, reread=False)
    except Exception:
        bar = None
    r = A.room_set(p, tl, text, bar.px_per_m if bar else None, mode=a.mode)
    kind = "unit" if "apartment" in text else "labelled" if "labelled" in text else "floor"
    rec = {"stem": st, "split": sp, "kind": kind, "q": text[:90], "gold": q["answer"], "bar": bool(bar)}
    if r:
        rec.update(pred=r["value"], err=round(r["value"] / float(q["answer"]) - 1, 4), n=len(r["rooms"]),
                   measured=len(r["measured"]), unmeasured=len(r["unmeasured"]), region_m2=r.get("region_m2"),
                   interior_m2=r.get("interior_m2"))
    rows.append(rec)
with open(a.out, "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
for sp in sorted({(r["kind"], r["split"]) for r in rows}):
    rs = [r for r in rows if (r["kind"], r["split"]) == sp]
    got = [r for r in rs if "err" in r]
    e = [abs(r["err"]) for r in got]
    print(f"{sp}: {len(rs)} Qs on {len({r['stem'] for r in rs})} plans; answered {len(got)}; within 2% "
          f"{sum(x <= .02 for x in e)}, 5% {sum(x <= .05 for x in e)}, 10% {sum(x <= .10 for x in e)}; "
          f"median err {100 * statistics.median(e) if e else float('nan'):.1f}%")
for r in rows if a.verbose else []:
    print(r["split"], r["stem"][-22:], r["q"][38:50], r["gold"], r.get("pred"), r.get("err"),
          f"n={r.get('n')} meas={r.get('measured')} unm={r.get('unmeasured')} reg={r.get('region_m2')} int={r.get('interior_m2')}")
