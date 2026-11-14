"""Does tiled label reading fix drawings whose one-shot label list looped / hit max_tokens? TRAIN only.

    PYTHONPATH=$PWD STOA_LLM_CACHE=1 $JUNCTION_VENV/bin/python experiments/w3/tiled_labels.py [--all]
Compares per-class label-count accuracy (bedroom, wc_room, balcony, sauna-with-code) of the current items
(labels-train500.jsonl) vs vlm.read_labels_tiled on the truncated drawings (--all: every drawing, slower).
"""
import argparse, collections, concurrent.futures as cf, contextvars, json, os, time
from pathlib import Path
from stoa import llm
from stoa.data import abspath
from stoa.solvers.raster import vlm
from stoa.solvers.raster.classes import label_class, type_code

SHARED = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
ap = argparse.ArgumentParser(); ap.add_argument("--all", action="store_true"); ap.add_argument("--n", type=int, default=999)
a = ap.parse_args()
rows = [json.loads(l) for l in open(SHARED / "artifacts/W3/calib/labels-train500.jsonl")]
sel = [r for r in rows if a.all or any("truncated" in n or "LOOP" in n for n in r.get("notes", []))][: a.n]
print(len(sel), "drawings")


def counts(texts):
    n = collections.Counter(label_class(t) for t in texts)
    codes = [type_code(t) for t in texts if type_code(t)]
    n["sauna_code"] = n["sauna"] or int(bool(codes and "sauna" in codes[0]["classes"]))
    return n


def run(r):
    img = llm.load_image(abspath(r["path"]))
    items, log = vlm.read_labels_tiled(img)
    return r, [i.text for i in items], log


t0 = time.time()
with cf.ThreadPoolExecutor(16) as ex:
    out = list(ex.map(lambda r: contextvars.copy_context().run(run, r), sel))
stat = collections.defaultdict(lambda: [0, 0, 0])
tok = 0
dump = SHARED / "artifacts/W3/calib/labels-tiled.jsonl"
with open(dump, "w") as fh:
    for r, texts, log in out:
        tok += log.tokens_in + log.tokens_out
        old, new = counts([t for t, *_ in r["items"]]), counts(texts)
        for c, gc in (("bedroom", "bedroom"), ("wc_room", "wc_room"), ("balcony", "balcony"), ("sauna_code", "sauna")):
            if gc in r["gold"]:
                s = stat[c]; g = float(r["gold"][gc])
                s[0] += 1; s[1] += old[c] == g; s[2] += new[c] == g
        fh.write(json.dumps({"path": r["path"], "gold": r["gold"], "tiled_texts": texts, "notes": log.notes,
                             "tok": [log.tokens_in, log.tokens_out]}) + "\n")
for c, (n, o, t) in stat.items():
    print(f"{c:12s} n={n:3d} one-shot {o / n:6.1%}  tiled {t / n:6.1%}  ({t - o:+d})")
print(f"{time.time() - t0:.0f}s, {tok / max(1, len(out)):.0f} tokens per drawing -> {dump}")
