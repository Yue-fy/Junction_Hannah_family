"""S0: aggregate count of where the translate-first front end (stoa.llm.should_translate) fires, per split and
source. Prints counts only (safe on sealed splits). Usage: PYTHONPATH=. $JUNCTION_VENV/bin/python experiments/s0/trigger_count.py test dev hard hard2r
"""
import collections, sys
from stoa.eval import load_split
from stoa.llm import should_translate, lang_guess
for split in sys.argv[1:]:
    qs = load_split(split)
    c = collections.Counter(); nonen = collections.Counter(); tot = collections.Counter()
    for q in qs:
        src = getattr(q, "source", None) or (q.get("source") if isinstance(q, dict) else "?")
        text = q.question if hasattr(q, "question") else q["question"]
        tot[src] += 1
        if lang_guess(text) != "en":
            nonen[src] += 1
            if should_translate(text):
                c[src] += 1
    print(f"{split}: n={sum(tot.values())} non-en={sum(nonen.values())} trigger={sum(c.values())}  by source trigger: {dict(c)}  non-en: {dict(nonen)}")
