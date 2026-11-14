"""Make an audit batch for the expert workbench (tab 1) from ANY eval predictions file, without re-running a solver.

    $JUNCTION_VENV/bin/python -m workbench.batch RUN [--name stoa] [--label "Stoa's example questions"]
        [--ref-label Stoa] [--n 40] [--seed 7] [--credit "..."]

RUN = a predictions file (`python -m stoa.eval ... ` prints its path) or a run id (artifacts/eval/<run_id>.jsonl).
Typical use after the noon reveal: put Stoa's examples in a jsonl split ({"path", "question", "answer"?}), run
`python -m stoa.eval --solver pipeline --split /path/to/stoa_examples.jsonl --no-leaderboard`, then
`python -m workbench.batch <that run> --name stoa --label "Stoa's example questions" --ref-label Stoa`.
The page shows a "Check N new items" button for every batch in human/batches/ that is not loaded yet.

Rows without a reference answer (gold null) are fine: the page says so and asks the expert for the right answer.
Drawings outside the dataset are copied into human/drawings/ (the only other folder the workbench may open);
evidence that points at them is rewritten to the copy. If RUN has more than --n rows, a sample is drawn per
(source, type), a third of each from answers that are wrong or below 0.6 confidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

from workbench import catalog
from workbench.store import human_dir


def _pred_file(run: str) -> Path:
    p = Path(run)
    if p.is_file():
        return p
    shared = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
    q = shared / "artifacts" / "eval" / f"{run.removesuffix('.jsonl')}.jsonl"
    if q.is_file():
        return q
    raise SystemExit(f"no predictions file or run id: {run}")


def _added_copy(path: str, credit: str, cache: dict) -> str:
    """Workbench key for `path`; a renderable drawing outside the dataset is copied into human/drawings/ first.
    Anything else outside the dataset (an IFC, a missing file) keeps its path: the page never opens it."""
    if path in cache:
        return cache[path]
    try:
        key = catalog.canon(path)
    except catalog.BadPath:
        src = Path(path)
        key = path
        if src.is_file() and src.suffix.lower() in catalog.RENDER_EXT:
            h = hashlib.sha1(src.read_bytes()).hexdigest()[:8]
            stem = re.sub(r"[^A-Za-z0-9._-]+", "_", src.stem).strip("._-")[:60] or "drawing"
            ext = ".jpg" if src.suffix.lower() == ".jpeg" else src.suffix.lower()
            d = catalog.human_drawings_dir()
            d.mkdir(parents=True, exist_ok=True)
            dst = d / f"{stem}-{h}{ext}"
            if not dst.exists():
                shutil.copyfile(src, dst)
                side = {"title": src.stem.replace("_", " "), "original_name": src.name, "source_path": str(src),
                        "credit": credit, "license": "", "added": time.strftime("%Y-%m-%dT%H:%M:%S")}
                (d / f"{dst.name}.json").write_text(json.dumps(side, ensure_ascii=False, indent=1), encoding="utf-8")
            key = catalog.HUMAN_PREFIX + dst.name
    cache[path] = key
    return key


def sample(rows: list[dict], n: int, seed: int) -> list[dict]:
    if len(rows) <= n:
        return rows
    rng = random.Random(seed)
    strata: dict[tuple, list] = defaultdict(list)
    for r in rows:
        strata[(r.get("source"), r.get("type"))].append(r)
    scale = n / len(rows)
    out = []
    for _key, pool in sorted(strata.items(), key=lambda kv: str(kv[0])):
        quota = max(1, round(len(pool) * scale))
        pool = pool[:]
        rng.shuffle(pool)
        hard = [r for r in pool if r.get("correct") is False or float(r.get("confidence") or 0) < 0.6]
        easy = [r for r in pool if r not in hard]
        n_hard = min(len(hard), max(1, math.ceil(quota / 3)))
        chosen = hard[:n_hard] + easy[: quota - n_hard]
        chosen += hard[n_hard:][: quota - len(chosen)]
        out.extend(chosen)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run")
    ap.add_argument("--name", default="", help="batch name ([A-Za-z0-9_-], ≤ 40); default: from the run id")
    ap.add_argument("--label", default="", help="what the button says, e.g. \"Stoa's example questions\"")
    ap.add_argument("--ref-label", default="", help="who made the reference answers (shown as 'Reference answer (X)')")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--credit", default="provided to the team; not part of the Stoa dataset",
                    help="credit line for drawings copied from outside the dataset")
    a = ap.parse_args(argv)

    pf = _pred_file(a.run)
    name = a.name or re.sub(r"[^A-Za-z0-9_-]+", "-", pf.stem)[-40:].strip("-")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name):
        raise SystemExit("--name: letters, digits, '_' and '-' only, at most 40")
    rows = [json.loads(line) for line in pf.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if r.get("path") and r.get("question")]
    keep, cache, sealed = [], {}, 0
    for r in rows:
        key = _added_copy(r["path"], a.credit, cache)
        if key.startswith("data/") and catalog.is_sealed(key):
            sealed += 1  # D15: never show a test drawing
            continue
        r["path"] = key
        for e in r.get("evidence") or []:
            if e.get("file"):
                e["file"] = _added_copy(e["file"], a.credit, cache)
        keep.append(r)
    picked = sample(keep, a.n, a.seed)
    by_src = defaultdict(list)  # interleave sources so the expert sees variety from the first item
    for r in picked:
        by_src[r.get("source")].append(r)
    order = []
    while any(by_src.values()):
        for s in list(by_src):
            if by_src[s]:
                order.append(by_src[s].pop(0))
    out = human_dir() / "batches" / f"{name}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for i, r in enumerate(order, 1):
            r["item_id"] = f"{name}-{i:02d}-{r.get('qid') or hashlib.sha1(r['question'].encode()).hexdigest()[:12]}"
            r["batch"] = name
            r["batch_label"] = a.label or name
            r["ref_label"] = a.ref_label
            r["from_run"] = pf.stem
            r["made_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    tmp.replace(out)
    n_gold = sum(1 for r in order if r.get("gold") is not None)
    n_added = sum(1 for k in set(cache.values()) if k.startswith(catalog.HUMAN_PREFIX))
    print(f"wrote {len(order)} items ({n_gold} with a reference answer) to {out}; "
          f"{n_added} drawing(s) in human/drawings; {sealed} test-split rows skipped", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
