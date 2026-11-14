"""Translate a split file's questions with stoa.llm.to_english (owner: R2): simulates a pipeline front end that
translates every question in an uncovered language. Writes <in>_translated.jsonl next to the input (qid + '-x').
    $JUNCTION_VENV/bin/python experiments/r2/probes/translate_split.py $JUNCTION_SHARED/artifacts/R2/lang4.jsonl [--show]
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from stoa.llm import to_english  # noqa: E402

src = Path(sys.argv[1])
rows = [json.loads(line) for line in src.open()]
t0 = time.time()
with ThreadPoolExecutor(4) as ex:
    res = list(ex.map(lambda r: to_english(r["question"]), rows))
out = []
for r, t in zip(rows, res):
    if "--show" in sys.argv:
        print(f"{t.lang:3s} ok={int(t.ok)} tr={int(t.translated)} | {t.text}")
    out.append({**r, "question": t.text, "qid": r["qid"] + "-x",
                "meta": {**(r.get("meta") or {}), "translated": t.translated, "ok": t.ok, "original": r["question"]}})
dst = src.with_name(src.stem + "_translated.jsonl")
dst.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in out))
print(f"{dst}: {len(out)} rows, {sum(t.translated for t in res)} translated, {sum(not t.ok for t in res)} not ok, "
      f"{time.time() - t0:.1f} s")
