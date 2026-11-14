"""How well does the raster text layer read historical scans? Proxy gold = catalogue titles (no questions exist).

HABS/HAER: the Library of Congress title ("... (sheet 2 of 5) - <structure>, <place>, <county>, <ST>") is what the
sheet's title block prints. Finna (Helsinki City Archives): the title is usually the street address, written on the
drawing. Per drawing we measure, for the tiled reading (tile=1100 px, ~2x) and a one-call whole-image baseline
(tile=99999 -> one tile, sent at max side 2000 px):
  name_recall : share of the structure name's words (len >= 4) found in the text layer (fuzzy >= 0.85)
  state       : the state's full name (HABS) is found
  address     : the street name of the address (Finna) is found
  scale       : a scale note is parsed (no gold; rate only)
  n_texts, tokens, seconds

    python experiments/w3/textlayer_eval.py --habs 20 --finna 10 [--workers 3]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from stoa.solvers.raster import textlayer as T  # noqa: E402

ROOT = Path(os.environ["STOA_DATA"])
OUT = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")) / "artifacts" / "W3" / \
    "textlayer_eval.jsonl"
STATES = {"AK": "Alaska", "AL": "Alabama", "AR": "Arkansas", "AZ": "Arizona", "CA": "California", "CO": "Colorado",
          "CT": "Connecticut", "DC": "Columbia", "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
          "IA": "Iowa", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "KS": "Kansas", "KY": "Kentucky",
          "LA": "Louisiana", "MA": "Massachusetts", "MD": "Maryland", "ME": "Maine", "MI": "Michigan",
          "MN": "Minnesota", "MO": "Missouri", "MS": "Mississippi", "MT": "Montana", "NC": "North Carolina",
          "ND": "North Dakota", "NE": "Nebraska", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
          "NV": "Nevada", "NY": "New York", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
          "PR": "Puerto Rico", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
          "TX": "Texas", "UT": "Utah", "VA": "Virginia", "VT": "Vermont", "WA": "Washington", "WI": "Wisconsin",
          "WV": "West Virginia", "WY": "Wyoming", "VI": "Virgin Islands", "GU": "Guam"}
ROW = re.compile(r"^\| (\S+\.jpg) \| (.+?) \| ")


def catalogue(src: str) -> dict[str, str]:
    out = {}
    for line in (ROOT / "data" / src / "LICENSE.md").read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if m and (ROOT / "data" / src / m.group(1)).exists():
            out[m.group(1)] = m.group(2)
    return out


def found(word: str, tl: T.TextLayer, thr: float = 0.85) -> bool:
    return any(T.match_score(word, i.text) >= thr for i in tl.items) or T.match_score(word, tl.text()) >= thr


def measure(path: str, title: str, src: str, tile: int) -> dict:
    tl = T.text_layer(path, tile=tile)
    r = {"path": path, "src": src, "tile": tile, "n_texts": len(tl.items), "tiles": tl.tiles,
         "tok_in": tl.tokens_in, "tok_out": tl.tokens_out, "seconds": tl.seconds,
         "scale": [s["line"] for s in T.scales(tl)[:2]], "n_dims": len(T.dimensions(tl))}
    if src == "habs":
        body = title.split(") - ", 1)[1] if ") - " in title else title.split(" - ", 1)[-1]
        parts = [p.strip() for p in body.split(",")]
        st = parts[-1]
        name = ", ".join(parts[:max(1, len(parts) - 3)])
        words = [w for w in re.findall(r"[A-Za-z']{4,}", name)]
        r["name_words"] = len(words)
        r["name_recall"] = round(sum(found(w, tl) for w in words) / len(words), 3) if words else None
        r["state"] = found(STATES.get(st, st), tl) if st in STATES else None
        m = re.search(r"\(sheet (\d+) of (\d+)\)", title)
        if m:
            txt = T.norm(tl.text())
            r["sheet_of"] = bool(re.search(r"\bsheets?\b", txt)) and m.group(2) in re.findall(r"\d+", txt)
    else:
        street = re.findall(r"[A-Za-zÅÄÖåäöÜüÉé-]{4,}", title)
        r["name_words"] = len(street)
        r["address"] = found(street[0], tl, 0.8) if street else None
        r["name_recall"] = round(sum(found(w, tl, 0.8) for w in street) / len(street), 3) if street else None
    return r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--habs", type=int, default=20)
    ap.add_argument("--finna", type=int, default=10)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--tiles", default="1100,99999")
    a = ap.parse_args()
    rng = random.Random(14)
    jobs = []
    for src, n in (("habs", a.habs), ("finna", a.finna)):
        cat = catalogue(src)
        keys = sorted(k for k, t in cat.items() if src != "habs" or "(sheet" in t)
        for k in rng.sample(keys, min(n, len(keys))):
            for tile in [int(t) for t in a.tiles.split(",")]:
                jobs.append((f"data/{src}/{k}", cat[k], src, tile))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with cf.ThreadPoolExecutor(a.workers) as ex, OUT.open("a") as f:
        for r in ex.map(lambda j: measure(*j), jobs):
            rows.append(r)
            f.write(json.dumps(r) + "\n")
            f.flush()
            print(json.dumps({k: r[k] for k in r if k not in ("scale",)}), flush=True)
    for src in ("habs", "finna"):
        for tile in sorted({r["tile"] for r in rows}):
            rs = [r for r in rows if r["src"] == src and r["tile"] == tile]
            if not rs:
                continue

            def avg(k):
                v = [float(r[k]) for r in rs if r.get(k) is not None]
                return round(sum(v) / len(v), 3) if v else None
            print(f"{src} tile={tile} n={len(rs)} name_recall={avg('name_recall')} state={avg('state')} "
                  f"address={avg('address')} sheet_of={avg('sheet_of')} scale_rate={sum(bool(r['scale']) for r in rs)}/{len(rs)} "
                  f"texts={avg('n_texts')} tok_in={avg('tok_in')} tok_out={avg('tok_out')} sec={avg('seconds')}")


if __name__ == "__main__":
    main()
