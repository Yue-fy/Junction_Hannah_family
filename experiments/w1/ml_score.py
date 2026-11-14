"""Summarise ml_run.py output: per language x mode, right / confident-wrong (conf >= 0.8 and wrong)."""
import json, sys
from collections import defaultdict
rows = [json.loads(x) for x in open(sys.argv[1])]
agg = defaultdict(lambda: [0, 0, 0])
for r in rows:
    a = agg[(r["mode"], r["lang"])]
    a[0] += 1; a[1] += r["ok"]; a[2] += r["cw"]
for mode in ("raw", "tr"):
    tot = [0, 0, 0]
    line = []
    for (m, lang), a in sorted(agg.items()):
        if m != mode:
            continue
        line.append(f"{lang} {a[1]}/{a[0]} cw{a[2]}")
        tot = [x + y for x, y in zip(tot, a)]
    if tot[0]:
        print(f"{mode}: {tot[1]}/{tot[0]} right, {tot[2]} confident-wrong | " + ", ".join(line))
if len(sys.argv) > 2:
    for r in rows:
        if not r["ok"] and r["mode"] in sys.argv[2].split(","):
            print(f"{r['mode']} {r['lang']} {r['idx']:2d} {'CW' if r['cw'] else '  '} [{r['conf']:.2f}] {str(r['value'])[:28]!s:>28} (gold {r['gold']}) | {r['q_used'][:110]}")
