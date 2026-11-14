"""Door-count rules on cached detections (doorwin_dets_*.jsonl): exact / within-1 / within-10% vs DXF leaf gold."""
import json, sys, collections
rows = [json.loads(l) for l in open(sys.argv[1])]
rules = {
    "visible": lambda r: len(r["dets"]),
    **{f"+red_hinge>={t}": (lambda t: lambda r: len(r["dets"]) + sum(d["red_hinge"] >= t for d in r["dets"]))(t)
       for t in (1, 5, 10, 20)},
    **{f"+red_box>={t}": (lambda t: lambda r: len(r["dets"]) + sum(d["red_box"] >= t for d in r["dets"]))(t)
       for t in (5, 20, 40)},
}
for name, f in rules.items():
    ex = w1 = w10 = 0
    err = []
    for r in rows:
        v, g = f(r), r["gold"]
        ex += v == g; w1 += abs(v - g) <= 1; w10 += abs(v - g) <= 0.1 * g
        err.append(v - g)
    err.sort()
    print(f"{name:18s} exact {ex:2d}/{len(rows)} within1 {w1:2d} within10% {w10:2d} median err {err[len(err)//2]:+d} "
          f"q10/q90 {err[len(err)//10]:+d}/{err[9*len(err)//10]:+d}")
