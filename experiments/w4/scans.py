"""Build a small measured split for historical scans (no questions in questions.jsonl): HABS sheets.

Gold comes ONLY from the Library of Congress catalogue titles in data/habs/LICENSE.md ("... (sheet 2 of 5) - <name>,
<place>, <county>, <ST>"), i.e. what the sheet's title block prints. Two questions per sheet:
  - "Which sheet of the set is this, and how many sheets does the set have?"  -> "2 of 5"
  - "In which U.S. state is the documented structure? Two-letter code."       -> "AK"

    python experiments/w4/scans.py [--n 20]  -> $JUNCTION_SHARED/artifacts/W4/scans.jsonl
    python -m stoa.eval --solver pipeline --split $JUNCTION_SHARED/artifacts/W4/scans.jsonl --judge local
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
from pathlib import Path

ROW = re.compile(r"^\| (\S+\.jpg) \| (.+?) \| (\S+) \|")
SHEET = re.compile(r"\(sheet (\d+) of (\d+)\)")
STATE = re.compile(r",\s*([A-Z]{2})\s*$")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    a = ap.parse_args()
    root = Path(os.environ["STOA_DATA"])
    rows = []
    for line in (root / "data" / "habs" / "LICENSE.md").read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if not m:
            continue
        f, title = m.group(1), m.group(2)
        s, st = SHEET.search(title), STATE.search(title)
        if s and st and (root / "data" / "habs" / f).exists():
            rows.append((f, s.group(1), s.group(2), st.group(1)))
    rng = random.Random(7)
    rng.shuffle(rows)
    seen, pick = set(), []
    for r in rows:  # one sheet per survey (ak0015 ...), spread over states
        k = r[0].split("_")[0]
        if k not in seen:
            seen.add(k)
            pick.append(r)
        if len(pick) >= a.n:
            break
    out = Path(os.environ.get("JUNCTION_SHARED", ".")) / "artifacts" / "W4" / "scans.jsonl"
    with open(out, "w", encoding="utf-8") as fh:
        for f, n, m, st in pick:
            path = f"data/habs/{f}"
            for kind, q, ans in (
                ("sheet-of", "Which sheet of the drawing set is this, and how many sheets does the set have? "
                             "Answer like '2 of 5'.", f"{n} of {m}"),
                ("state", "In which U.S. state is the documented structure located? Give the two-letter state code.", st),
            ):
                qid = "s" + hashlib.sha1(f"{path}|{kind}".encode()).hexdigest()[:11]
                fh.write(json.dumps({"qid": qid, "path": path, "question": q, "answer": ans, "unit": None, "type": "text",
                                     "source": "habs", "group": f"habs/{f.split('_')[0]}",
                                     "meta": {"kind": "scan", "recipe": kind}}) + "\n")
    print(f"{len(pick)} sheets, {2 * len(pick)} questions -> {out}")


if __name__ == "__main__":
    main()
