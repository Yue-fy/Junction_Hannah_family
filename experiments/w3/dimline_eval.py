"""Printed dimension strings vs their drawn dimension lines measured with the snapped graphic scale bar.

Every cached text layer with a drawn ('+drawn') ft bar: for each printed ft-in dimension, measure its line and compare.
Agreement within 3% means the reading, the line and the bar are all right (self-checking; no hand gold needed).
    $JUNCTION_VENV/bin/python experiments/w3/dimline_eval.py  -> artifacts/W3/dimline_eval.jsonl
"""
import glob
import json
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PIL import Image  # noqa: E402

from stoa.solvers.raster import dimline as D, scalebar as SB, textlayer as T  # noqa: E402

SH = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
rows = []
for f in sorted(glob.glob(str(SH / "artifacts/W3/textlayer/*.json"))):
    p = json.load(open(f))["path"]
    if not any(s in p for s in ("habs", "finna", "wikimedia", "europeana")):
        continue
    try:
        tl = T.text_layer(p)
    except Exception:
        continue
    dims = T.dimensions(tl)
    if not dims:
        continue
    bars = [b for b in SB.bars(p, layer=tl, reread=False) if b.unit == "ft" and "drawn" in b.source]
    if not bars:
        continue
    bar = bars[0]
    d = D._dark(Image.open(T._abspath(p)))
    for dm in dims:
        r = D.dim_line(d, dm["box"])
        rec = {"path": p, "text": dm["text"], "feet": dm["feet"], "box": dm["box"], "ppf": bar.px_per_unit}
        if r:
            rec.update(full_ft=round(r["px"] / bar.px_per_unit, 2), seg_ft=round(r["seg_px"] / bar.px_per_unit, 2),
                       ticks=len(r["ticks"]), vertical=r["vertical"])
            rec["full_err"] = round(rec["full_ft"] / dm["feet"] - 1, 4) if dm["feet"] else None
            rec["seg_err"] = round(rec["seg_ft"] / dm["feet"] - 1, 4) if dm["feet"] else None
        rows.append(rec)
with open(SH / "artifacts/W3/dimline_eval.jsonl", "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
found = [r for r in rows if "seg_err" in r and r["seg_err"] is not None]
print(f"{len(rows)} printed ft dims on {len({r['path'] for r in rows})} sheets with a drawn ft bar; line found {len(found)}")
for k in ("full_err", "seg_err"):
    e = [abs(r[k]) for r in found]
    if e:
        print(f"{k}: within 3% {sum(x <= .03 for x in e)}/{len(e)}, 10% {sum(x <= .10 for x in e)}, median {100 * statistics.median(e):.1f}%")
for r in found[:40]:
    print(f"{r['path'][-26:]:26s} {r['text']:>10s} {r['feet']:7.2f} ft  full {r['full_ft']:7.2f} seg {r['seg_ft']:7.2f} ticks {r['ticks']} {'V' if r['vertical'] else 'H'}")
