"""Translate a split file's questions with stoa.llm.to_english (owner: R2): simulates a pipeline front end that
translates questions before routing. Writes <in>_translated[_<backend>].jsonl next to the input (qid + '-x').
    $JUNCTION_VENV/bin/python experiments/r2/probes/translate_split.py <split.jsonl> [--show] [--force] [--backend nvidia]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from stoa.llm import to_english  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("split")
ap.add_argument("--show", action="store_true")
ap.add_argument("--force", action="store_true")
ap.add_argument("--backend", default="local")
a = ap.parse_args()
src = Path(a.split)
rows = [json.loads(line) for line in src.open()]
t0 = time.time()
with ThreadPoolExecutor(4 if a.backend != "nvidia" else 1) as ex:
    res = list(ex.map(lambda r: to_english(r["question"], force=a.force, backend=a.backend), rows))
out = []
for r, t in zip(rows, res):
    if a.show:
        print(f"{t.lang:3s} ok={int(t.ok)} tr={int(t.translated)} | {t.text}")
    out.append({**r, "question": t.text, "qid": r["qid"] + "-x",
                "meta": {**(r.get("meta") or {}), "translated": t.translated, "ok": t.ok, "original": r["question"]}})
dst = src.with_name(src.stem + "_translated" + ("" if a.backend == "local" else "_" + a.backend) + ".jsonl")
dst.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in out))
print(f"{dst}: {len(out)} rows, {sum(t.translated for t in res)} translated, {sum(not t.ok for t in res)} not ok, "
      f"{time.time() - t0:.1f} s")
