"""Same-gold UNIT probe (c227, OPEN: dev drawings only): the dataset question re-asked in another unit, gold converted.

Our scorer converts the predicted unit to the gold unit, so "17.58 m²" is right for "...in cm²?". A judge (or Stoa's
scorer) that reads the NUMBER in the unit asked would mark it wrong. This probe reports both:
  converted = our eval's score; strict = the returned value, read as-is, within 2% of the gold in the asked unit.

    python experiments/F/unit_probe.py write            -> $JUNCTION_SHARED/artifacts/F/unit_probe.jsonl
    python -m stoa.eval --solver pipeline --split $JUNCTION_SHARED/artifacts/F/unit_probe.jsonl --workers 4
    python3 experiments/F/unit_probe.py report RUN.jsonl
"""
import collections
import hashlib
import json
import os
import re
import sys

OUT = os.path.join(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"), "artifacts", "F",
                   "unit_probe.jsonl")
FT2, FT, CM2, CM, MM = 10.763910417, 3.280839895, 1e4, 100.0, 1000.0
AREA = {"ft2": ("in square feet", FT2), "sqft": ("in sq ft", FT2), "cm2": ("in cm²", CM2)}
LENGTH = {"mm": ("in millimetres", MM), "cm": ("in centimetres", CM), "ft": ("in feet", FT)}
UNIT_OF = {"ft2": "ft2", "sqft": "ft2", "cm2": "cm2", "mm": "mm", "cm": "cm", "ft": "ft"}


def write():
    from stoa.eval.splits import load_split
    rows, per = [], collections.Counter()
    for q in load_split("dev"):
        if q.type not in ("area", "length") or not isinstance(q.answer, (int, float)):
            continue
        pat = r"in m²|in square metres|en m²|in m2" if q.type == "area" else r"in metres|in meters|in meter|in m\b"
        if not re.search(pat, q.question) or not q.question.isascii() and q.source == "cubicasa5k":
            continue
        key = (q.source, q.type, re.sub(r"'[^']*'|\d+(\.\d+)?", "X", q.question)[:60])
        if per[key] >= 6:  # at most 6 bases per template
            continue
        per[key] += 1
        for name, (phrase, f) in (AREA if q.type == "area" else LENGTH).items():
            qq = re.sub(pat, phrase, q.question, count=1)
            qid = "un" + hashlib.sha1(f"{q.qid}|{name}".encode()).hexdigest()[:10]
            rows.append({"qid": qid, "path": q.path, "question": qq, "answer": round(float(q.answer) * f, 4),
                         "unit": UNIT_OF[name], "type": q.type,
                         "meta": {"kind": f"{q.source}/{q.type}:{name}", "wording": name, "base_qid": q.qid}})
        rows.append({"qid": "un" + hashlib.sha1(f"{q.qid}|m".encode()).hexdigest()[:10], "path": q.path,
                     "question": q.question, "answer": q.answer, "unit": q.unit, "type": q.type,
                     "meta": {"kind": f"{q.source}/{q.type}:dataset", "wording": "dataset", "base_qid": q.qid}})
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(len(rows), "rows ->", OUT)


def report(run):
    c = collections.defaultdict(lambda: [0, 0, 0, collections.Counter()])
    for line in open(run):
        r = json.loads(line)
        if r.get("correct") is None:
            continue
        k = r["meta"]["kind"]
        c[k][0] += 1
        c[k][1] += bool(r["correct"])
        try:
            strict = abs(float(r["value"]) - float(r["gold"])) <= 0.02 * abs(float(r["gold"]))
        except (TypeError, ValueError):
            strict = False
        c[k][2] += strict
        c[k][3][str(r.get("unit"))] += 1
    print(f"{'kind':38s} {'n':>4s} {'converted':>9s} {'strict':>7s}  returned units")
    for k in sorted(c):
        n, ok, st, units = c[k]
        print(f"{k:38s} {n:4d} {100 * ok / n:9.1f} {100 * st / n:7.1f}  {dict(units.most_common(3))}")


if __name__ == "__main__":
    write() if sys.argv[1] == "write" else report(sys.argv[2])
