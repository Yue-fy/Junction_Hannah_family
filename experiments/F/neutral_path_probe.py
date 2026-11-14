"""Neutral-path probe (F c226): the SAME dev question, the SAME file bytes, asked at four kinds of path.

Stoa's hidden files and a visitor's upload will not sit in our dataset folders. Several routes key on the path:
source_of() reads data/<source>/ from it, siblings() finds same-stem twins (dxf/png/ifc) in the same folder, and
caches/gates are keyed by dataset-relative paths. This probe measures how much of our accuracy is the path.

Variants (meta.wording):
  dataset      the dataset path (control)
  twins_name   a neutral folder with every same-stem twin under its ORIGINAL file name (folder effects only)
  twins_hash   a hashed stem in a neutral folder, WITH every same-stem twin (swiss pdf+dxf+png; ifc_models view + its
               .ifc model; cubicasa png + svg) under the same hashed stem: "a drawing package, new names"
  srcdir_lone  the asked file alone, hashed name, inside .../data/<source>/ (source_of still says the source, no twins)
  lone_hash    the asked file alone, hashed name, no source folder: "a visitor uploads one file"
Copies are hard links (same file system) under $NEUTRAL_ROOT (default /data/User/fangy4/stoa-neutral), outside git
and outside $STOA_DATA. Dev drawings only: OPEN probe, fine to quote and fix against.

    python experiments/F/neutral_path_probe.py [SCALE] [--bench]  # -> artifacts/F/neutral_path{,_bench}.jsonl
    python -m stoa.eval --solver pipeline --split $JUNCTION_SHARED/artifacts/F/neutral_path.jsonl --workers 5
    python3 experiments/F/control_compare.py $JUNCTION_SHARED/artifacts/F/neutral_path.jsonl RUN
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import random
import shutil
import sys
from pathlib import Path

from stoa.data import abspath, ifc_model_for, siblings
from stoa.eval.splits import load_split, shared_root

# (source, type) -> (drawings, questions per drawing) at SCALE 1
PLAN = {
    ("cubicasa5k", "count"): (14, 4),
    ("swiss_dwellings", "area"): (10, 3),
    ("swiss_dwellings", "count"): (10, 3),
    ("ifc_models", "area"): (8, 3),
    ("ifc_models", "count"): (8, 2),
    ("ifc_models", "volume"): (6, 2),
    ("ifc_models", "length"): (4, 2),
    ("opening_design", "count"): (6, 3),
    ("opening_design", "area"): (3, 3),
}
VARIANTS = ("dataset", "twins_name", "twins_hash", "srcdir_lone", "lone_hash")


def _link(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _twins(rel: str) -> dict[str, str]:
    sib = dict(siblings(rel))
    if rel.endswith((".pdf", ".svg", ".png")) and "/ifc_models/" in rel:
        m = ifc_model_for(rel)
        if m:
            sib[".ifc"] = m
        # the plan's SVG twin (GlobalId tags) is a same-stem sibling already when it exists
    return sib


PLAN_BENCH = {("ifc_bench", "text"): (10, 2)}  # --bench: free-text model questions (judge them: --judge local)


def main(scale: float = 1.0, bench: bool = False) -> None:
    root = Path(os.environ.get("NEUTRAL_ROOT", "/data/User/fangy4/stoa-neutral"))
    rng = random.Random(226)
    dev = load_split("dev")
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for q in dev:
        if q.answer is None:
            continue
        by[(q.source, q.type)][q.path].append(q)
    rows = []
    for key, (n_draw, per) in (PLAN_BENCH if bench else PLAN).items():
        paths = sorted(by.get(key, {}))
        rng.shuffle(paths)
        for p in paths[: max(1, round(n_draw * scale))]:
            qs = by[key][p][:]
            rng.shuffle(qs)
            h = hashlib.sha1(p.encode()).hexdigest()[:10]
            ext = Path(p).suffix.lower()
            src_abs = abspath(p)
            paths_v = {"dataset": p}
            ndir = root / "named" / h
            for e, rel in _twins(p).items():
                _link(abspath(rel), ndir / Path(rel).name)
            paths_v["twins_name"] = str(ndir / Path(p).name)
            # twins_hash: every twin under the same hashed stem
            tdir = root / "twins" / h
            for e, rel in _twins(p).items():
                _link(abspath(rel), tdir / f"d{h}{e}")
            paths_v["twins_hash"] = str(tdir / f"d{h}{ext}")
            sdir = root / "srcdir" / h / "data" / key[0]
            _link(src_abs, sdir / f"d{h}{ext}")
            paths_v["srcdir_lone"] = str(sdir / f"d{h}{ext}")
            ldir = root / "lone" / h
            _link(src_abs, ldir / f"d{h}{ext}")
            paths_v["lone_hash"] = str(ldir / f"d{h}{ext}")
            for q in qs[:per]:
                for v in VARIANTS:
                    qid = "np" + hashlib.sha1(f"{q.qid}|{v}".encode()).hexdigest()[:10]
                    rows.append({"qid": qid, "path": paths_v[v], "question": q.question, "answer": q.answer,
                                 "unit": q.unit, "type": q.type,
                                 "meta": {"kind": f"{key[0]}/{key[1]}:{v}", "wording": v, "probe_kind": "neutral",
                                          "source": key[0], "base_qid": q.qid, "base_path": p,
                                          "twins": sorted(_twins(p))}})
    out = shared_root() / "artifacts" / "F" / ("neutral_path_bench.jsonl" if bench else "neutral_path.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    c = collections.Counter(r["meta"]["kind"].split(":")[0] for r in rows if r["meta"]["wording"] == "dataset")
    print(f"{len(rows)} rows ({len(rows) // len(VARIANTS)} bases) -> {out}")
    for k, v in sorted(c.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(float(args[0]) if args else 1.0, bench="--bench" in sys.argv)
