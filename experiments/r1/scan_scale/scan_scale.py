"""Scale of a historical scan (HABS sheets resized to <= 3000 px, so the DPI is lost), two independent ways, CPU only,
from W3's cached text layer (artifacts/W3/textlayer/*.json: every printed text with its image-px box):

  A  scale NOTE + standard sheet size: '1/4" = 1'-0"' gives paper inches per foot; HABS sheets are 24 x 36 in
     (aspect 1.5) or 19 x 24 in (aspect 1.263), so px per paper inch = long side px / long side in.
  B  graphic scale BAR: numeric tick labels on one row next to 'FEET'/'METERS' -> least-squares px per unit.

Where a sheet has exactly one scale note and a bar, the two should agree; agreement validates both and gives a
px/ft for lengths on the scan ('the north facade is 42 ft').

    python experiments/r1/scan_scale/scan_scale.py [--verbose]
"""

from __future__ import annotations

import glob
import json
import math
import os
import re
import statistics as st
import sys
from fractions import Fraction
from pathlib import Path

SHARED = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
TL = SHARED / "artifacts" / "W3" / "textlayer"
SHEETS = {"24x36": (1.5, 36.0), "19x24": (24 / 19, 24.0)}
UNIT = re.compile(r"\b(FEET|FT\.?|METERS?|METRES?)\b", re.I)
NUM = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*$")
FRAC = r"(\d+\s*/\s*\d+|\d+(?:\.\d+)?|\d+\s+\d+\s*/\s*\d+)"
NOTE_IMP = re.compile(FRAC + r'\s*(?:"|”|\'\'|IN\.?)\s*=\s*1\s*\'\s*-?\s*0?\s*"?', re.I)  # 1/4" = 1'-0"
NOTE_FT = re.compile(r'1\s*(?:"|”|IN\.?)\s*=\s*(\d+(?:\.\d+)?)\s*(?:\'|FT|FEET)', re.I)  # 1" = 20'
NOTE_MET = re.compile(r"\b1\s*:\s*(\d{2,5})\b")


def frac(s: str) -> float:
    s = s.strip()
    if " " in s and "/" in s:
        a, b = s.split(None, 1)
        return float(a) + float(Fraction(b.replace(" ", "")))
    return float(Fraction(s.replace(" ", ""))) if "/" in s else float(s)


def notes(items) -> list[float]:
    """Paper inches per real foot for every scale note on the sheet."""
    out = []
    for it in items:
        t = it["text"].replace("’", "'").replace("″", '"')
        for m in NOTE_IMP.finditer(t):
            try:
                v = frac(m.group(1))
                if 0 < v <= 3:
                    out.append(v)
            except (ValueError, ZeroDivisionError):
                pass
        for m in NOTE_FT.finditer(t):
            out.append(1 / float(m.group(1)))
        for m in NOTE_MET.finditer(t):
            n = int(m.group(1))
            if 10 <= n <= 5000:
                out.append(12 / n)
    return out


def bars(items) -> list[dict]:
    """px per foot from scale bars: number labels in one row near a unit word."""
    out = []
    nums = [(float(m.group(1)), it) for it in items for m in [NUM.match(it["text"])] if m]
    for u in items:
        if not UNIT.search(u["text"]):
            continue
        metric = bool(re.search(r"MET", u["text"], re.I))
        uy = (u["box"][1] + u["box"][3]) / 2
        uh = max(8.0, u["box"][3] - u["box"][1])
        row = [(v, (it["box"][0] + it["box"][2]) / 2) for v, it in nums
               if abs((it["box"][1] + it["box"][3]) / 2 - uy) <= 1.5 * uh and u["box"][0] - 1500 <= it["box"][0] <= u["box"][2] + 200]
        vals = {}
        for v, x in row:
            vals.setdefault(v, []).append(x)
        pts = sorted((v, st.median(xs)) for v, xs in vals.items())
        if len(pts) < 3:
            continue
        n = len(pts)
        mv = sum(v for v, _ in pts) / n
        mx = sum(x for _, x in pts) / n
        sxx = sum((v - mv) ** 2 for v, _ in pts)
        b = sum((v - mv) * (x - mx) for v, x in pts) / sxx
        ss_tot = sum((x - mx) ** 2 for _, x in pts)
        r2 = 1 - sum((x - (mx + b * (v - mv))) ** 2 for v, x in pts) / ss_tot if ss_tot else 0
        if b <= 0 or r2 < 0.98:
            continue
        out.append({"px_per_ft": b * 0.3048 if metric else b, "unit": "m" if metric else "ft", "n": n,
                    "r2": round(r2, 4), "labels": [v for v, _ in pts], "anchor": u["text"]})
    return out


MERGED = re.compile(r"^\s*(\d+(?:\.\d+)?)((?:\s+\d+(?:\.\d+)?)+)\s*(FEET|FT\.?|METERS?|METRES?)\.?\s*$", re.I)


def merged_bars(items) -> list[dict]:
    """Bars whose labels the OCR returned as ONE item ('0 10 20 30 60 90 ft.'): the box runs from the first label to the
    unit word along its long axis; label centres sit on the ticks, so px/unit = (centre of last label - centre of first)
    / (last - first), with character width ~ 0.6 x the text height (the short side of the box)."""
    out = []
    for it in items:
        m = MERGED.match(it["text"])
        if not m:
            continue
        vals = [float(m.group(1))] + [float(v) for v in m.group(2).split()]
        if vals != sorted(vals) or vals[-1] <= vals[0]:
            continue
        x0, y0, x1, y1 = it["box"]
        L, h = max(x1 - x0, y1 - y0), min(x1 - x0, y1 - y0)
        cw = 0.6 * h
        first, last, unit = m.group(1), m.group(2).split()[-1], m.group(3)
        span = L - cw * len(first) / 2 - cw * (len(last) / 2 + 1 + len(unit))
        if span <= 0:
            continue
        b = span / (vals[-1] - vals[0])
        metric = unit.upper().startswith("MET")
        out.append({"px_per_ft": b * 0.3048 if metric else b, "unit": "m" if metric else "ft", "n": len(vals),
                    "r2": None, "labels": vals, "anchor": it["text"], "merged": True})
    return out


def main() -> None:
    verbose = "--verbose" in sys.argv
    seen, rows = set(), []
    for f in sorted(glob.glob(str(TL / "*.json"))):
        d = json.load(open(f))
        p = d.get("path", "")
        if p in seen:
            continue
        seen.add(p)
        W, H = d["size"]
        asp = max(W, H) / min(W, H)
        sheet = next((k for k, (a, _) in SHEETS.items() if abs(asp - a) < 0.03), None)
        ns = notes(d["items"])
        bs = bars(d["items"]) + merged_bars(d["items"])
        row = {"path": p, "size": [W, H], "aspect": round(asp, 3), "sheet": sheet, "notes": ns, "bars": bs}
        if sheet:
            px_in = max(W, H) / SHEETS[sheet][1]
            row["note_px_per_ft"] = sorted({round(px_in * n, 2) for n in ns})
        rows.append(row)
    print(f"{len(rows)} scans; sheet size from aspect: {sum(1 for r in rows if r['sheet'])}; with a scale note: "
          f"{sum(1 for r in rows if r['notes'])}; with a scale bar fit (>=3 labels, R2>=0.98): {sum(1 for r in rows if r['bars'])}")
    both = []
    for r in rows:
        if not (r["bars"] and r.get("note_px_per_ft")):
            continue
        # each bar vs the CLOSEST note-derived scale (sheets can carry several scales)
        for b in r["bars"]:
            best = min(r["note_px_per_ft"], key=lambda s: abs(math.log(s / b["px_per_ft"])))
            both.append((r["path"], b["px_per_ft"], best, len(set(r["note_px_per_ft"])), b))
    if both:
        errs = [abs(b / n - 1) for _, b, n, _, _ in both]
        single = [abs(b / n - 1) for _, b, n, k, _ in both if k == 1]
        print(f"bar vs note-derived scale: {len(both)} bars on {len({p for p, *_ in both})} sheets; |bar/note - 1| p50 "
              f"{100 * st.median(errs):.1f}%, within 3% {100 * sum(e <= .03 for e in errs) / len(errs):.0f}%, within 10% "
              f"{100 * sum(e <= .1 for e in errs) / len(errs):.0f}%")
        if single:
            print(f"  sheets with ONE scale note: n={len(single)}, p50 {100 * st.median(single):.1f}%, within 3% "
                  f"{100 * sum(e <= .03 for e in single) / len(single):.0f}%")
        if verbose:
            for p, b, n, k, bb in both:
                print(f"  {p} bar {b:.2f} px/ft ({bb['unit']}, labels {bb['labels']}, R2 {bb['r2']}) vs note {n:.2f} "
                      f"({k} notes) -> {100 * (b / n - 1):+.1f}%")
    json.dump(rows, open(SHARED / "artifacts" / "R1" / "scan_scale.json", "w"), indent=0)


if __name__ == "__main__":
    main()
