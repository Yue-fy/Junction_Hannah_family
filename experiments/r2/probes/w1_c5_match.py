"""Concept + unit match of to_english on W1's c5 multilingual ifc probe (night-W1 experiments/w1/probes/c5_ml.py),
cs/hu/sv rows only (pl/et/es are hard2r's sealed languages: not used to choose prompts). Owner: R2.
    $JUNCTION_VENV/bin/python experiments/r2/probes/w1_c5_match.py <path to c5_ml.py>"""
from __future__ import annotations

import importlib.util
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import stoa.llm as L  # noqa: E402
from stoa.router.intent import parse  # noqa: E402

spec = importlib.util.spec_from_file_location("c5", sys.argv[1])
c5 = importlib.util.module_from_spec(spec); spec.loader.exec_module(c5)  # noqa: E702
en = c5.Q["en"].strip().split("\n")
items = [(q, en[i], lg) for lg in ("cs", "hu", "sv") if lg in c5.Q for i, q in enumerate(c5.Q[lg].strip().split("\n"))]


def unit(q: str) -> str:
    return "ft" if re.search(r"\bfeet\b|\bft\b", q, re.I) else ("m" if re.search(r"\bmet(re|er)s?\b", q, re.I) else "")


def key(q: str):
    it = parse(q)
    return it.task, it.target, unit(q)


for name, glossary in (("v3", L._TR_GLOSSARY), ("v4 (+quantity/unit hints, not used)", L._TR_GLOSSARY + L._TR_GLOSSARY_Q)):
    L._tr_memo.clear()
    old = L._TR_GLOSSARY
    L._TR_GLOSSARY = glossary
    with ThreadPoolExecutor(4) as ex:
        tr = list(ex.map(lambda it: L.to_english(it[0], force=True), items))
    L._TR_GLOSSARY = old
    m = [key(t.text) == key(e) for t, (_, e, _) in zip(tr, items)]
    print(f"{name}: concept+unit match {sum(m)}/{len(m)}, not ok {sum(not t.ok for t in tr)}")
    for t, (q, e, lg), ok in zip(tr, items, m):
        if not ok:
            print(f"   {lg}: {t.text[:80]} | EN {e[:60]} | {key(t.text)} vs {key(e)}")
