"""Can a VLM tell which views a historical scan shows (plan / elevation / section / site plan)? (owner: R2)

Weak gold = keywords in the Finna title (Finnish: pohjapiirustus/pohjapiirros = plan, julkisivu = elevation,
leikkaus = section, asemapiirros/asema- = site plan), only for titles that name at least one kind.
    $JUNCTION_VENV/bin/python experiments/r2/scan_views.py --n 100 [--backend nvidia] [--out FILE]
Prints exact-set accuracy, per-view precision/recall and cost. Licence: Finna drawings are CC BY 4.0
(credit per data/finna/LICENSE.md).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from stoa import llm  # noqa: E402

DATA = Path(os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset"))
VIEWS = ("plan", "elevation", "section", "site")
KW = {
    "plan": r"pohjapiir|pohja-|pohjakuva|pohjat\b",
    "elevation": r"julkisivu",
    "section": r"leikkaus",
    "site": r"asemapiir|asema-|asemakaava",
}
PROMPT = (
    "This is a scanned architectural drawing sheet. Which kinds of views does it contain? Choose from: "
    "plan (floor plan seen from above), elevation (facade view), section (vertical cut through the building), "
    "site (site plan showing the plot, neighbouring streets or buildings). A sheet can contain several. "
    'Answer with JSON only: {"views": ["plan", ...]}'
)


def gold_rows() -> list[dict]:
    rows = []
    for line in (DATA / "data/finna/LICENSE.md").read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 4 or not cells[1].endswith(".jpg"):
            continue
        title = cells[2].lower()
        # "julkisivu- ja pohjapiirustus" = elevation AND plan: the hyphenated prefix shares the suffix
        views = {v for v, rx in KW.items() if re.search(rx, title)}
        if re.search(r"leikkaus-|julkisivu-|asema-", title) and re.search(r"piirustus|piirros", title):
            views |= {"plan"} if re.search(r"pohja", title) else set()
        if views:
            rows.append({"file": cells[1], "title": cells[2], "gold": sorted(views)})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--backend", default="local")
    ap.add_argument("--out")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    rows = gold_rows()
    random.Random(0).shuffle(rows)
    rows = rows[: a.n]
    reqs = [dict(messages=PROMPT, images=[str(DATA / "data/finna" / r["file"])], backend=a.backend,
                 max_tokens=(1024 if a.backend == "nvidia" else 64), thinking=False) for r in rows]
    t0 = time.time()
    with llm.cost_meter() as c:
        res = llm.chat_many(reqs, workers=a.workers if a.backend == "local" else 4)
    exact, tp, fp, fn = 0, dict.fromkeys(VIEWS, 0), dict.fromkeys(VIEWS, 0), dict.fromkeys(VIEWS, 0)
    out = []
    for r, x in zip(rows, res):
        if isinstance(x, Exception):
            pred = []
        else:
            d = llm.extract_json(x.text) or {}
            pred = sorted({str(v).lower().split()[0] for v in (d.get("views") or []) if str(v).strip()} & set(VIEWS)) \
                if isinstance(d, dict) else []
        g = set(r["gold"])
        exact += set(pred) == g
        for v in VIEWS:
            tp[v] += v in pred and v in g
            fp[v] += v in pred and v not in g
            fn[v] += v not in pred and v in g
        out.append({**r, "pred": pred})
    n = len(rows)
    print(f"{a.backend}: {n} finna scans, exact view set {exact / n:.1%}, {time.time() - t0:.0f} s, {c}")
    for v in VIEWS:
        p = tp[v] / max(1, tp[v] + fp[v])
        rc = tp[v] / max(1, tp[v] + fn[v])
        print(f"  {v:10s} gold {tp[v] + fn[v]:3d}  precision {p:.2f}  recall {rc:.2f}")
    if a.out:
        Path(a.out).write_text("\n".join(json.dumps(o, ensure_ascii=False) for o in out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
