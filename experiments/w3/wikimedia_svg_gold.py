"""Off-domain text reading + room-label counts on Wikimedia floor plans, gold = the <text> of the SVG sibling.

Wikimedia plans often ship as SVG + a raster rendering. The SVG's text elements are what is printed on the raster, so
they are gold for (1) text recall of the raster text layer and (2) room-class label counts (classes.label_class on
the SVG texts vs on the text layer), i.e. raster's off-domain `_text_count` class path (conf 0.45, unmeasured so far).

    python experiments/w3/wikimedia_svg_gold.py [--n 20] [--workers 4]
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import os
import random
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from stoa.solvers.raster import textlayer as T  # noqa: E402
from stoa.solvers.raster.classes import ROOM_CLASSES, label_class  # noqa: E402

ROOT = Path(os.environ["STOA_DATA"]) / "data" / "wikimedia"
OUT = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")) / "artifacts" / "W3" / \
    "wikimedia_svg_gold.jsonl"


def svg_texts(f: Path) -> list[str]:
    try:
        root = ET.parse(f).getroot()
    except ET.ParseError:
        return []
    out = []
    for el in root.iter():
        if el.tag.split("}")[-1] == "text":
            t = re.sub(r"\s+", " ", "".join(el.itertext())).strip()
            if t:
                out.append(t)
    return out


def measure(img: str, texts: list[str]) -> dict:
    tl = T.text_layer(img)
    gold = [t for t in texts if len(T.norm(t)) >= 2]
    found = [t for t in gold if any(T.match_score(t, i.text) >= 0.85 for i in tl.items)]
    g = collections.Counter(c for c in map(label_class, gold) if c)
    p = collections.Counter(c for c in (label_class(i.text) for i in tl.items) if c)
    cls = {c: [g.get(c, 0), p.get(c, 0)] for c in ROOM_CLASSES if g.get(c) or p.get(c)}
    return {"path": img, "n_gold": len(gold), "recall": round(len(found) / len(gold), 3) if gold else None,
            "n_read": len(tl.items), "classes": cls, "tok_in": tl.tokens_in, "tiles": tl.tiles}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    cands = []
    for f in sorted(ROOT.glob("*.svg")):
        sib = next((f.with_suffix(e) for e in (".jpg", ".png") if f.with_suffix(e).exists()), None)
        texts = svg_texts(f)
        if sib and len(texts) >= 5:
            cands.append((f"data/wikimedia/{sib.name}", texts))
    rng = random.Random(7)
    sample = rng.sample(cands, min(a.n, len(cands)))
    rows = []
    with cf.ThreadPoolExecutor(a.workers) as ex, OUT.open("w") as fo:
        for r in ex.map(lambda c: measure(*c), sample):
            rows.append(r)
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(json.dumps(r, ensure_ascii=False)[:300], flush=True)
    rec = [r["recall"] for r in rows if r["recall"] is not None]
    pairs = [v for r in rows for v in r["classes"].values()]
    print(f"{len(cands)} candidates; n={len(rows)} text recall mean {sum(rec) / len(rec):.3f}; room-class counts "
          f"(class present in gold or read) exact {sum(g == p for g, p in pairs)}/{len(pairs)}, "
          f"over {sum(p > g for g, p in pairs)}, under {sum(p < g for g, p in pairs)}")


if __name__ == "__main__":
    main()
