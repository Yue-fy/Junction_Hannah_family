"""Generality check: the CC5K detector on an UNSEEN raster style, the swiss PNG twins (R2's count splits; gold comes
from the DXF). Per symbol class: exact, within ±1, median count ratio; paired with other solvers' runs on the same
questions.  python swiss_png_check.py PRED1.jsonl [PRED2 ...] -- RUN1.jsonl [RUN2 ...]
PRED = predict.py output lines; RUN = eval prediction files on swiss_png_counts_* (vlm_lora, raster, ...)."""
import json
import os
import re
import statistics
import sys
from collections import defaultdict

SH = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")
RX = {"windows": r"\bwindows?\b|fenster|fen[êe]tre|finestr", "doors": r"\bdoors?\b|t[üu]ren|portes?\b|porte\b",
      "wc_seats": r"toilet|\bwc\b|klosett", "sinks": r"wash ?basin|sink|lavabo|waschtisch|lavandino"}


def cls_of(q):
    q = q.lower()
    if re.search(r"rooms?\b|räume|zimmer|pièces?|stanze|locali", q) and not re.search(RX["windows"] + "|" + RX["doors"], q):
        return None  # "WC rooms" etc. are room counts, not symbols
    for k, x in RX.items():
        if re.search(x, q):
            return k


if __name__ == "__main__":
    i = sys.argv.index("--") if "--" in sys.argv else len(sys.argv)
    preds, runs = sys.argv[1:i], sys.argv[i + 1:]
    det = {}
    for f in preds:
        for l in open(f):
            d = json.loads(l)
            p = d.get("path") or d.get("image")
            det[p[p.rindex("/data/") + 1:]] = d["counts"]
    qs = []
    for f in ("swiss_png_counts_dev.jsonl", "swiss_png_counts_train_gate.jsonl"):
        for l in open(f"{SH}/artifacts/R2/{f}"):
            r = json.loads(l)
            c = cls_of(r["question"])
            if c and r["path"] in det:
                qs.append(dict(qid=r["qid"], path=r["path"], cls=c, gold=int(r["answer"]), split=f[18:-6],
                               det=det[r["path"]][c]["count"]))
    other = {}
    for f in runs:
        name = os.path.basename(f).split("-")[2]
        other[name] = {json.loads(l)["qid"]: json.loads(l) for l in open(f)}
    by = defaultdict(list)
    for q in qs:
        by[q["cls"]].append(q)
    for c, g in sorted(by.items()):
        n = len(g)
        ex = sum(q["det"] == q["gold"] for q in g) / n
        w1 = sum(abs(q["det"] - q["gold"]) <= 1 for q in g) / n
        ratio = statistics.median(q["det"] / q["gold"] for q in g if q["gold"])
        line = f"{c:9} n={n:3d} CC5K exact {100*ex:4.0f}%  ±1 {100*w1:4.0f}%  median det/gold {ratio:.2f}  median gold {statistics.median(q['gold'] for q in g)}"
        for name, rr in other.items():
            m = [q for q in g if q["qid"] in rr]
            if m:
                acc = sum(bool(rr[q["qid"]].get("correct")) for q in m) / len(m)
                agree = [q for q in m if rr[q["qid"]].get("value") is not None and round(float(rr[q["qid"]]["value"])) == q["det"]]
                ag = sum(bool(rr[q["qid"]].get("correct")) for q in agree)
                line += f" | {name} {100*acc:.0f}% (n{len(m)}; agree w/ CC5K {len(agree)}, right {ag})"
        print(line)
