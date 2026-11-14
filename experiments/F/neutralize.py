"""Re-ask any OPEN probe/split file on neutral copies of its files (F c226): same qids, same questions, same gold,
the file (and its same-stem twins / IFC model) hard-linked to a neutral folder under a hashed or the original name.
Pair the two runs by qid with experiments/F/kind_compare.py.

    python experiments/F/neutralize.py IN.jsonl OUT.jsonl [--mode hash|name|lone]
    python -m stoa.eval --solver pipeline --split OUT.jsonl
    python3 experiments/F/kind_compare.py IN.jsonl RUN_IN RUN_OUT

hash: twins under one hashed stem (file names carry no meaning: 'A101.pdf', a scan id);
name: original names in a neutral folder (no data/<source>/ folder); lone: the asked file alone, hashed name.
Never on sealed splits (it prints nothing, but the copies would be readable by everyone).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

from stoa.data import abspath, ifc_model_for, siblings


def _link(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def neutral_path(p: str, mode: str, root: Path) -> str:
    h = hashlib.sha1(p.encode()).hexdigest()[:10]
    ext = Path(p).suffix.lower()
    if mode == "lone":
        dst = root / "lone" / h / f"d{h}{ext}"
        _link(abspath(p), dst)
        return str(dst)
    twins = dict(siblings(p))
    if ext in (".pdf", ".svg", ".png") and "/ifc_models/" in p:
        m = ifc_model_for(p)
        if m:
            twins[".ifc"] = m
    twins.setdefault(ext, p)
    folder = root / ("twins" if mode == "hash" else "named") / h
    for e, rel in twins.items():
        if mode == "hash":
            _link(abspath(rel), folder / f"d{h}{e}")
        else:
            _link(abspath(rel), folder / Path(rel).name)
    return str(folder / (f"d{h}{ext}" if mode == "hash" else Path(p).name))


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mode = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--mode=")), None)
    if "--mode" in sys.argv:
        mode = sys.argv[sys.argv.index("--mode") + 1]
        args = [a for a in args if a != mode]
    mode = mode or "hash"
    src, dst = args[0], args[1]
    if any(s in Path(src).name for s in ("test", "hard2r", "hard3", "hardL.", "hard2q", "hard2p")):
        sys.exit("refusing a sealed/held-out split")
    root = Path(os.environ.get("NEUTRAL_ROOT", "/data/User/fangy4/stoa-neutral"))
    n = 0
    with open(src, encoding="utf-8") as f, open(dst, "w", encoding="utf-8") as g:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            r["path"] = neutral_path(r["path"], mode, root)
            g.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    print(f"{n} rows -> {dst} (mode {mode})")


if __name__ == "__main__":
    main()
