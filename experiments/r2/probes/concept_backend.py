"""Translator bake-off (owner: R2): to_english (default prompt) on backend A vs B, scored as CONCEPT match (the
translation parses to the same (task, target) as the English base). Sets: F's hardL_open (cs/hu/tr/ro), R2's lang4,
W4's lang4b (pt/sk/lt/hr) when it has English bases, and the Polish 'belek' pair.
    $JUNCTION_VENV/bin/python experiments/r2/probes/concept_backend.py local local2 [--show]
"""
from __future__ import annotations

import collections
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import stoa.llm as L  # noqa: E402
from stoa.router.intent import parse  # noqa: E402

S = Path("/home/fangy4/work/projects/junction-shared")
sets = []
rows = [json.loads(x) for x in (S / "results/splits/hardL_open.jsonl").open()]
en = {r["meta"]["base_qid"]: r["question"] for r in rows if r["meta"]["lang"] == "en"}
sets.append(("hardL_open", [(r["question"], en[r["meta"]["base_qid"]], r["meta"]["lang"]) for r in rows
                            if r["meta"]["lang"] != "en" and r["meta"]["base_qid"] in en]))
l4 = [json.loads(x) for x in (S / "artifacts/R2/lang4.jsonl").open()]
l4en = {json.loads(x)["qid"].split("-")[0]: json.loads(x)["question"] for x in (S / "artifacts/R2/lang4_en.jsonl").open()}
sets.append(("lang4", [(r["question"], l4en[r["qid"].split("-")[0]], r["meta"]["lang"]) for r in l4]))
sets.append(("belek", [("Ile belek jest w modelu 'BIM-Speed Gdynia'?",
                        "How many beams are there in the model 'BIM-Speed Gdynia'?", "pl")]))


def key(q: str):
    it = parse(q)
    return it.task, it.target


backends = [a for a in sys.argv[1:] if not a.startswith("--")] or ["local", "local2"]
for name, items in sets:
    for be in backends:
        L._tr_memo.clear()
        t0 = time.time()
        with ThreadPoolExecutor(4) as ex:
            tr = list(ex.map(lambda it: L.to_english(it[0], force=True, backend=be), items))
        dt = time.time() - t0
        match = [key(t.text) == key(e) for t, (_, e, _) in zip(tr, items)]
        bylang = collections.defaultdict(lambda: [0, 0])
        for m, (_, _, lg) in zip(match, items):
            bylang[lg][0] += m; bylang[lg][1] += 1
        print(f"{name:10s} {be:7s}: concept match {sum(match)}/{len(match)}, not ok {sum(not t.ok for t in tr)}, "
              f"{dt:.1f}s  by lang " + " ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(bylang.items())), flush=True)
        if "--show" in sys.argv:
            for t, (q, e, lg), m in zip(tr, items, match):
                if not m:
                    print(f"    MISS {lg}: {t.text[:90]}  | en: {e[:70]}  | {key(t.text)} vs {key(e)}")
