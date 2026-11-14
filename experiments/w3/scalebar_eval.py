"""Scale-bar reading on cached raster text layers (artifacts/W3/textlayer), with gold-free self-checks.

1. ft/m pairs: sheets with a FEET and a METERS bar for the same view must give px/m / px/ft = 3.2808.
2. HABS written scale: the sheet size follows from the aspect ratio (R1 04:24: 1.5 -> 24x36 in, ~1.27 -> 19x24 in),
   the scan is 3000 px on the long side, so a written 1/4" = 1'-0" (1:48) on a 36 in sheet predicts
   3000 / 36 * 12 / 48 = 20.8 px/ft; a bar of the same view should agree (other views on the sheet may differ).

    python experiments/w3/scalebar_eval.py [--reread] [--limit N] [--out artifacts/W3/scalebar.jsonl]
"""
import argparse, glob, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from stoa.solvers.raster import scalebar as S, textlayer as T  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--reread", action="store_true")
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--out", default="")
a = ap.parse_args()
files = sorted(glob.glob(str(T.CACHE_DIR / "*.json")))
seen, rows = set(), []
pairs_ok = pairs = habs_ok = habs_n = nbars = 0
for f in files:
    d = json.load(open(f))
    if d["path"] in seen:
        continue
    seen.add(d["path"])
    d["items"] = [T.TextItem(**i) for i in d["items"]]
    d["size"] = tuple(d["size"])
    tl = T.TextLayer(**d)
    bs = S.bars(tl.path, reread=a.reread, layer=tl)
    if not bs:
        continue
    nbars += len(bs)
    cons = S.consistency(bs)
    pairs += sum(1 for c in cons)
    pairs_ok += sum(1 for c in cons if "✓" in c)
    habs = []
    asp = max(tl.size) / min(tl.size)
    long_in = 36 if abs(asp - 1.5) < 0.03 else 24 if 1.24 < asp < 1.30 else None
    if "/habs/" in tl.path and max(tl.size) == 3000 and long_in:
        for sc in T.scales(tl):
            if sc["kind"] != "imperial":
                continue
            pred = 3000 / long_in * 12 / sc["ratio"]
            for b in bs:
                if b.unit == "ft":
                    habs.append((sc["ratio"], round(b.px_per_unit, 2), round(pred, 2), abs(b.px_per_unit / pred - 1) <= 0.03))
    if habs:
        habs_n += 1
        habs_ok += any(h[3] for h in habs)
    print(Path(tl.path).name[:40], tl.size, "|", " || ".join(f"{b.unit}:{b.px_per_unit:.2f}px n{len(b.labels)} r{b.residual:.1f} {b.source}"
                                             + (f" [{'; '.join(b.notes)}]" if b.notes else "") for b in bs),
          "|", "; ".join(cons), "|", habs[:2] if habs else "")
    rows.append({"path": tl.path, "bars": [{"notes": b.notes, "unit": b.unit, "px_per_unit": b.px_per_unit, "n": len(b.labels),
                 "residual": b.residual, "source": b.source, "box": b.box, "labels": [l[:2] for l in b.labels]} for b in bs],
                 "consistency": cons, "habs_written": habs})
    if a.limit and len(rows) >= a.limit:
        break
snapped = sum(1 for r in rows for b in r["bars"] if "+drawn" in b["source"])
swiss = [b["px_per_unit"] for r in rows if "/swiss_dwellings/" in r["path"] for b in r["bars"][:1] if b["unit"] == "m"]
sw_err = sorted(min(abs(x / 59.055 - 1), abs(x / 29.528 - 1)) for x in swiss)
print(f"drawn bar found (snapped) for {snapped}/{nbars} bars; Swiss PNG (exact 59.055 or 29.528 px/m at 1:100/1:200, "
      f"A3 2480 px): n={len(sw_err)}, median err {100 * sw_err[len(sw_err) // 2]:.2f}%, max {100 * sw_err[-1]:.2f}%, "
      f"within 1%: {sum(e <= .01 for e in sw_err)}" if sw_err else "")
print(f"\n{len(seen)} drawings, {len(rows)} with >=1 bar, {nbars} bars; ft/m pairs consistent {pairs_ok}/{pairs}; "
      f"HABS sheets whose ft bar matches the written scale at 36in/3000px: {habs_ok}/{habs_n}")
if a.out:
    Path(a.out).write_text("".join(json.dumps(r) + "\n" for r in rows))
