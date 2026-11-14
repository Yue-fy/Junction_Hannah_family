"""Translation quality as CONCEPT match (owner: R2): does to_english(foreign) parse to the same intent (task, target)
as the English base question? F 04:38: the front end's remaining losses are concept-noun slips. Compares the current
system prompt (A) with a candidate (B: domain glossary + 'never add qualifiers'). Translations are forced (every
foreign row) and also counted on the should_translate subset.
    $JUNCTION_VENV/bin/python experiments/r2/probes/concept_match.py
"""
from __future__ import annotations

import collections
import json
import sys
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
extra = [("Ile belek jest w modelu 'BIM-Speed Gdynia'?", "How many beams are there in the model 'BIM-Speed Gdynia'?", "pl"),
         ("Ile belek znajduje się w modelu „BIM-Speed Gdynia - semi-detached house Ruchu Oporu 18”?",
          "How many beams are there in the model 'BIM-Speed Gdynia - semi-detached house Ruchu Oporu 18'?", "pl")]
tk = [json.loads(x) for x in (S / "artifacts/F/trigger_known.jsonl").open()]
sets.append(("belek", extra))

PROMPTS = {"A (no glossary)": L._TR_SYSTEM_BASE, "B2 (English terms)": L._TR_SYSTEM,
           "B3 (B2 + source-language hints; default since 05:00)": L._TR_SYSTEM + L._TR_GLOSSARY}
L._TR_GLOSSARY = ""  # the loop below sets the whole system prompt


def key(q: str):
    it = parse(q)
    return it.task, it.target


for name, items in sets:
    for pname, prompt in PROMPTS.items():
        if prompt is None:
            continue
        L._TR_SYSTEM = prompt
        L._tr_memo.clear()
        with ThreadPoolExecutor(4) as ex:
            tr = list(ex.map(lambda it: L.to_english(it[0], force=True), items))
        trig = [L.should_translate(q) for q, _, _ in items]
        match = [key(t.text) == key(e) for t, (_, e, _) in zip(tr, items)]
        tmatch = [m for m, g in zip(match, trig) if g]
        bylang = collections.defaultdict(lambda: [0, 0])
        for m, (_, _, lg) in zip(match, items):
            bylang[lg][0] += m; bylang[lg][1] += 1
        print(f"{name:10s} prompt {pname}: concept match {sum(match)}/{len(match)} (on should_translate rows "
              f"{sum(tmatch)}/{len(tmatch)}), not ok {sum(not t.ok for t in tr)}  by lang "
              + " ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(bylang.items())))
        if "--show" in sys.argv or name == "belek":
            for t, (q, e, lg), m in zip(tr, items, match):
                if not m:
                    print(f"    MISS {lg}: {t.text[:90]}  | en: {e[:70]}  | {key(t.text)} vs {key(e)}")
L._TR_SYSTEM = PROMPTS["B2 (English terms)"]
