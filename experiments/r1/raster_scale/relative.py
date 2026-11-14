"""Scale-free questions on raster plans ('which room is largest?', 'is the kitchen bigger than bedroom 2?',
'how many times larger is A than B?'): they need only the CC5K region areas, no px/m. Checked against the printed
room areas (truth.jsonl from raster_scale.py: plans with >= 3 printed rooms matched to distinct regions).

    python experiments/r1/raster_scale/relative.py
"""
import itertools
import json
import math
import os
from pathlib import Path

ART = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")) / "artifacts" / "R1" / "raster_scale"


def q(xs, p):
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


rows = [r for r in map(json.loads, open(ART / "truth.jsonl")) if len(r["per_room"]) >= 3]
top, pairs, pairs_far, ratio_err, n_rooms = 0, [], [], [], 0
for r in rows:
    pr = [p for p in r["per_room"] if p["m2"] > 0]
    n_rooms += len(pr)
    top += max(pr, key=lambda p: p["px"]) is max(pr, key=lambda p: p["m2"])
    for a, b in itertools.combinations(pr, 2):
        if a["m2"] == b["m2"]:
            continue
        ok = (a["px"] > b["px"]) == (a["m2"] > b["m2"])
        pairs.append(ok)
        if max(a["m2"], b["m2"]) / min(a["m2"], b["m2"]) >= 1.25:  # sizes differ by >= 25%
            pairs_far.append(ok)
        ratio_err.append(abs((a["px"] / b["px"]) / (a["m2"] / b["m2"]) - 1))
print(f"{len(rows)} plans with >= 3 printed rooms ({n_rooms} rooms)")
print(f"largest printed room = largest region: {top}/{len(rows)} ({100 * top / len(rows):.0f}%)")
print(f"pairwise 'A bigger than B' right: {100 * sum(pairs) / len(pairs):.1f}% of {len(pairs)} pairs; "
      f"when sizes differ by >= 25%: {100 * sum(pairs_far) / len(pairs_far):.1f}% of {len(pairs_far)}")
print(f"area ratio A/B from pixels: error p50 {100 * q(ratio_err, .5):.1f}%, within 10% "
      f"{100 * sum(e <= .1 for e in ratio_err) / len(ratio_err):.0f}%, within 20% {100 * sum(e <= .2 for e in ratio_err) / len(ratio_err):.0f}%")
