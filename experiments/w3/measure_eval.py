"""Measuring on raster plans with the graphic scale bar, checked against DXF gold.

Swiss PNG twins (synthetic renders of the DXF geometry, A3 at 1:100, a printed 0-1-2-5 m bar) of dev drawings whose
text layer is cached: single-room net-area questions ("... locale 1.19 ...", any language) from questions.jsonl.
Path: raster textqa on the PNG (text layer + image; for size questions the VLM gives the element's box and the
program converts px with the bar). Reports the bar's px/m vs the exact 59.055 px/m (2480 px = 420 mm, 1:100),
and the answer's relative error vs the DXF net area (within 2 / 10 / 20 %).

    python experiments/w3/measure_eval.py [--limit 40] [--workers 3]
"""
import argparse, collections, glob, json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from stoa.solvers.raster import scalebar as SB, textlayer as T, textqa  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--limit", type=int, default=40)
ap.add_argument("--workers", type=int, default=3)
ap.add_argument("--out", default=os.environ["JUNCTION_SHARED"] + "/artifacts/W3/measure_eval.jsonl")
a = ap.parse_args()

cached = {}
for f in glob.glob(str(T.CACHE_DIR / "site*.json")):
    d = json.load(open(f))
    cached.setdefault(d["path"], f)
qs = [json.loads(l) for l in open(os.environ["STOA_DATA"] + "/questions.jsonl")]
room = re.compile(r"(?<![\d.])(\d+\.\d{2})(?![\d])")
rows = []
for q in qs:
    if q.get("type") != "area" or "swiss" not in q["path"]:
        continue
    png = q["path"][:-4] + ".png"
    if png not in cached:
        continue
    m = room.findall(q["question"])
    if len(m) != 1 or re.search(r"apartment|wohnung|appartement|appartamento|summe|sum|total|gesamt|tutte|toutes", q["question"], re.I):
        continue
    rows.append({**q, "png": png, "room": m[0]})
# one question per room, spread over drawings
seen, sel = set(), []
by = collections.defaultdict(list)
for r in rows:
    by[r["png"]].append(r)
while len(sel) < a.limit and any(by.values()):
    for k in list(by):
        if by[k]:
            r = by[k].pop(0)
            if (r["png"], r["room"]) not in seen:
                seen.add((r["png"], r["room"]))
                sel.append(r)
sel = sel[:a.limit]
print(f"{len(rows)} single-room area questions on {len(cached)} cached Swiss PNGs; using {len(sel)}")


def run(r):
    ans = textqa.answer(r["png"], r["question"])
    b = SB.best_bar(r["png"], prefer="m")
    v = ans.value
    try:
        v = float(v)
    except (TypeError, ValueError):
        v = None
    err = abs(v / r["answer"] - 1) if v and r["answer"] else None
    return {"path": r["png"], "question": r["question"], "gold": r["answer"], "value": ans.value, "unit": ans.unit,
            "conf": ans.confidence, "measured": any("measured" in t for t in ans.trace),
            "path_kind": "fill" if any("flood fill" in t for t in ans.trace) else "box" if any("measured" in t for t in
                                                                                             ans.trace) else "read", "rel_err": err,
            "bar_px_per_m": b.px_per_m if b else None, "bar_source": b.source if b else None, "trace": ans.trace[-2:]}


with ThreadPoolExecutor(a.workers) as ex:
    res = list(ex.map(run, sel))
Path(a.out).write_text("".join(json.dumps(r) + "\n" for r in res))
bars = [r["bar_px_per_m"] for r in res if r["bar_px_per_m"]]
berr = sorted(abs(b / 59.055 - 1) for b in {r["path"]: r["bar_px_per_m"] for r in res if r["bar_px_per_m"]}.values())
print(f"bar found on {len(set(r['path'] for r in res if r['bar_px_per_m']))}/{len(set(r['path'] for r in res))} drawings; "
      f"|px/m / 59.055 - 1|: median {100 * berr[len(berr) // 2]:.2f}%, max {100 * berr[-1]:.2f}%" if berr else "no bars")
for kind in ("fill", "box", "read"):
    sub = [r for r in res if r["path_kind"] == kind]
    e = [r["rel_err"] for r in sub if r["rel_err"] is not None]
    if not sub:
        continue
    e.sort()
    print(f"{kind:6s} n={len(sub)} answered={len(e)} "
          f"within 2%: {sum(x <= .02 for x in e)}  10%: {sum(x <= .10 for x in e)}  20%: {sum(x <= .20 for x in e)}  "
          f"median err {100 * e[len(e) // 2]:.1f}%" if e else f"{kind}: n={len(sub)} no numeric answers")
