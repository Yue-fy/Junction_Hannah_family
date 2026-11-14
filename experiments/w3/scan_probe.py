"""Probe split for text questions on historical scans; gold ONLY from catalogue titles in data/<src>/LICENSE.md.

  HABS/HAER: "What is the name of the structure documented on this sheet?" -> the first part of the title's structure
             name (judged free-form; the title block prints it; full name kept in meta).
  Finna (Helsinki City Archives): "What is the street address of the building on this drawing?" -> the title when it
             is a plain address ("Laajasuontie 15"); the leading "<street> <number>" of titles that start with one.
Drawings are drawn disjoint from W4's scans split (artifacts/W4/scans.jsonl) and from textlayer_eval's sample.

    python experiments/w3/scan_probe.py [--n 20]  -> $JUNCTION_SHARED/artifacts/W3/scan_probe.jsonl
    python -m stoa.eval --solver raster --split $JUNCTION_SHARED/artifacts/W3/scan_probe.jsonl --judge local
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from textlayer_eval import catalogue  # noqa: E402

SHARED = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
ADDR = re.compile(r"^([A-ZÅÄÖ][\wåäö-]*(?:katu|tie|kuja|polku|tori|ranta|väylä|puistikko|gatan|vägen|kaari|rinne|"
                  r"portti|aukio|esplanadi|bulevardi)\s\d+[a-z]?)(?=$|[,( ])")


def qid(*a) -> str:
    return "w3" + hashlib.sha1("|".join(a).encode()).hexdigest()[:10]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    a = ap.parse_args()
    used = set()
    for f in (SHARED / "artifacts/W4/scans.jsonl", SHARED / "artifacts/W3/textlayer_eval.jsonl"):
        if f.exists():
            used |= {json.loads(l)["path"] for l in f.read_text().splitlines() if l.strip()}
    rng = random.Random(1411)
    rows = []
    cat = catalogue("habs")
    keys = sorted(k for k, t in cat.items() if ") - " in t and f"data/habs/{k}" not in used)
    groups = {}
    for k in keys:
        groups.setdefault(k.split("_")[0], k)  # one sheet per HABS item
    for k in rng.sample(sorted(groups.values()), a.n):
        body = cat[k].split(") - ", 1)[1]
        parts = [p.strip() for p in body.split(",")]
        name = ", ".join(parts[:max(1, len(parts) - 3)])
        p = f"data/habs/{k}"
        q = "What is the name of the structure documented on this drawing sheet?"
        rows.append({"qid": qid(p, q), "path": p, "question": q, "answer": parts[0], "unit": None, "type": "text",
                     "source": "habs", "group": f"habs/{k.split('_')[0]}",
                     "meta": {"kind": "scan", "recipe": "name", "full_title": name}})
    cat = catalogue("finna")
    keys = sorted(k for k, t in cat.items() if ADDR.match(t.strip()) and f"data/finna/{k}" not in used)
    print(f"finna: {len(keys)} drawings with a street address title")
    for k in rng.sample(keys, a.n):
        p = f"data/finna/{k}"
        q = "What is the street address of the building on this drawing?"
        rows.append({"qid": qid(p, q), "path": p, "question": q, "answer": ADDR.match(cat[k].strip()).group(1), "unit": None,
                     "type": "text", "source": "finna", "group": f"finna/{k.split('_')[0]}", "meta": {"kind": "scan", "recipe": "address"}})
    out = SHARED / "artifacts/W3/scan_probe.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(f"{len(rows)} questions -> {out}")
    for r in rows[:3] + rows[-3:]:
        print(r["path"], "|", r["answer"])


if __name__ == "__main__":
    main()
