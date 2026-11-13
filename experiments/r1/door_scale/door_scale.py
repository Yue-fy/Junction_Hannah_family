"""How good is "assume a standard door width" as a scale fallback when a drawing has no scale?

Ground truth from swiss DXF (metres): every DOOR arc radius = leaf width. Per floor, take the median
leaf width (robust to double/garage doors). If a solver measures door leaves in pixels and assumes the
median is W0 metres, its length scale is off by median_w / W0, and areas by (median_w / W0)^2.
Reports the distribution of that error and the share of floors within the 2% area tolerance.
Run: python3 -I door_scale.py [n_floors]
"""
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "swiss_area_def"))
from minidxf import read_entities  # noqa: E402

D = os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    sw = os.path.join(D, "data", "swiss_dwellings")
    files = sorted(f for f in os.listdir(sw) if f.endswith(".dxf"))[:n]
    med, allw = [], []
    for f in files:
        r = [e["r"] for e in read_entities(os.path.join(sw, f)) if e["layer"] == "DOOR" and e["type"] == "ARC" and e["r"]]
        if len(r) >= 3:
            med.append(statistics.median(r))
            allw.extend(r)
    W0 = statistics.median(med)
    q = statistics.quantiles(allw, n=10)
    print(f"floors={len(med)} doors={len(allw)}; single-door leaf width deciles (m): {[round(x, 2) for x in q]}")
    print(f"per-floor median leaf width: median W0={W0:.3f} m; deciles {[round(x, 3) for x in statistics.quantiles(med, n=10)]}")
    errs = sorted(abs((m / W0) ** 2 - 1) for m in med)
    for t in (0.02, 0.05, 0.10, 0.20):
        print(f"  area error <= {t:.0%}: {sum(e <= t for e in errs) / len(errs):.1%} of floors")
    print(f"  median |area error| = {statistics.median(errs):.1%}; 80th pct = {errs[int(0.8 * len(errs))]:.1%}")
