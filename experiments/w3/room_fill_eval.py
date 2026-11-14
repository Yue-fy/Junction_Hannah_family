"""Room area by flood fill from the label (stoa/solvers/raster/measure.py) vs DXF gold, on the Swiss PNG twins whose
text layer is cached (same 148 single-room questions as measure_eval.py, no VLM call: CPU only).

    python experiments/w3/room_fill_eval.py [--door 1.05]
"""
import argparse, collections, glob, json, os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from stoa.solvers.raster import measure as M, scalebar as SB, textlayer as T  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--door", type=float, default=1.05)
ap.add_argument("--wall", type=float, default=0.0)
ap.add_argument("--hull", action="store_true")
ap.add_argument("--clip", type=float, default=0.0)
ap.add_argument("--split", action="store_true")
ap.add_argument("--fixture", action="store_true")
ap.add_argument("--grow", type=int, default=0)
ap.add_argument("--paths", default="", help="file with PNG paths to use (e.g. held-out drawings); default: all cached")
ap.add_argument("--exclude", default="", help="file with PNG paths to leave out")
ap.add_argument("--out", default=os.environ["JUNCTION_SHARED"] + "/artifacts/W3/room_fill_eval.jsonl")
a = ap.parse_args()
layers = {}
for f in glob.glob(str(T.CACHE_DIR / "site*.json")):
    d = json.load(open(f))
    d["items"] = [T.TextItem(**i) for i in d["items"]]
    d["size"] = tuple(d["size"])
    layers.setdefault(d["path"], T.TextLayer(**d))
qs = [json.loads(l) for l in open(os.environ["STOA_DATA"] + "/questions.jsonl")]
only = set(open(a.paths).read().split()) if a.paths else set()
excl = set(open(a.exclude).read().split()) if a.exclude else set()
rows, inks, seen = [], {}, set()
for q in qs:
    if q.get("type") != "area" or "swiss" not in q["path"]:
        continue
    png = q["path"][:-4] + ".png"
    if png not in layers or len(M._ROOM_ID.findall(q["question"])) != 1:
        continue
    if (only and png not in only) or png in excl:
        continue
    if re.search(r"apartment|wohnung|appartement|appartamento|summe|sum|total|gesamt|tutte|toutes", q["question"], re.I):
        continue
    key = (png, M._ROOM_ID.findall(q["question"])[0])
    if key in seen:
        continue
    seen.add(key)
    tl = layers[png]
    bar = SB.best_bar(png, prefer="m", reread=False, layer=tl)
    lab = M.find_label(tl, q["question"])
    r = {"path": png, "question": q["question"], "gold": q["answer"], "bar": bar.px_per_m if bar else None,
         "label": lab.text if lab else None}
    if bar and lab:
        if png not in inks:
            inks[png] = M._ink(png)
        got = M.room_area(png, lab.box, bar.px_per_m, door_m=a.door, ink=inks[png], wall_m=a.wall, hull=a.hull, clip=a.clip > 0, clip_m2=a.clip or 3.0,
                           others=[i.box for i in tl.items if M._ROOM_ID.fullmatch(i.text.strip()) and i is not lab]
                           if a.split else None, fixture_retry=a.fixture, grow=a.grow)
        if got:
            r.update(value=got["m2"], rel_err=abs(got["m2"] / q["answer"] - 1), box=got["box"], wall_frac=got["wall_frac"])
    rows.append(r)
Path(a.out).write_text("".join(json.dumps(r) + "\n" for r in rows))
n = len(rows)
lab = sum(1 for r in rows if r["label"])
ans = [r for r in rows if "value" in r]
e = sorted(r["rel_err"] for r in ans)
print(f"{n} rooms; label found {lab}; area answered {len(ans)}")
if e:
    print(f"within 2%: {sum(x <= .02 for x in e)}  5%: {sum(x <= .05 for x in e)}  10%: {sum(x <= .10 for x in e)}  "
          f"20%: {sum(x <= .20 for x in e)}  median {100 * e[len(e) // 2]:.1f}%  (of answered)")
    ratio = sorted(r["value"] / r["gold"] for r in ans)
    print("ratio pred/gold p10/p50/p90:", [round(ratio[int(p * (len(ratio) - 1))], 3) for p in (.1, .5, .9)])
