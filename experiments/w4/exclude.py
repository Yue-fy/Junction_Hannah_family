"""`exclude` probe split (W4, cycle 73): FRESH wordings of "this floor's indoor net area WITHOUT apartment X" on swiss
dev floors, written before any run (F 04:28: on held-out wordings dxf returned the EXCLUDED apartment's own area at
0.90-0.96 and the KG cross-check 'confirmed' it). Gold = total net floor area of all numbered indoor rooms (dataset
gold) - apartment X's net floor area (dataset gold). EN/DE/FR/IT, 15 wordings, one floor per row.

    python experiments/w4/exclude.py     -> $JUNCTION_SHARED/artifacts/W4/exclude.jsonl  (15 wordings, 30 rows)
    python experiments/w4/exclude.py 2   -> .../exclude2.jsonl (5 looser wordings, 30 rows)
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import random
from pathlib import Path

from stoa.data import concept_map, drawing_group, load_questions
from stoa.eval.hard import parse
from stoa.eval.splits import SEED, split_of_group

OUT = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")) / "artifacts/W4/exclude.jsonl"

WORDINGS = [
    "How much net floor area on this floor is outside apartment {a}, counting only numbered indoor rooms (m²)?",
    "What is the net floor area of all numbered indoor rooms on this floor except those of apartment {a}?",
    "Leaving apartment {a} aside, how many square metres of numbered indoor rooms does this floor have?",
    "Total indoor net area of this floor without apartment {a}, in m²?",
    "If apartment {a} is taken out, what net floor area of numbered indoor rooms remains on this floor?",
    "What is this floor's net indoor floor area minus apartment {a}?",
    "How many m² of numbered indoor rooms on this floor are not part of apartment {a}?",
    "Excluding apartment {a}, what is the total net floor area of the indoor rooms on this floor?",
    "Sum the net floor areas of all numbered indoor rooms on this plan apart from the ones in apartment {a}.",
    "How much indoor net floor area does this floor have besides apartment {a}?",
    "Net floor area of the rest of this floor (all numbered indoor rooms except apartment {a}), in m²?",
    "Wie gross ist die Nettofläche aller nummerierten Innenräume dieses Geschosses ohne die Wohnung {a}?",
    "Quelle est la surface nette des pièces intérieures numérotées de cet étage, sans l'appartement {a} ?",
    "Qual è la superficie netta dei locali interni numerati di questo piano, escluso l'appartamento {a}?",
    "Apart from apartment {a}, how large is the net floor area of the numbered indoor rooms on this floor?",
]


# set 2 (written after the first run showed dxf handles set 1): looser, conversational wordings
WORDINGS2 = [
    "How big is apartment {a}? Leave it out and give me the rest of the floor.",
    "Apartment {a} aside, what's left of the floor's numbered indoor rooms in m²?",
    "Floor area without counting apartment {a} - numbered indoor rooms only, net, m²?",
    "I want the net indoor area of this floor but not apartment {a}.",
    "Everything on this floor except apartment {a}: how many m² of numbered indoor rooms is that?",
]


def build(seed: int = SEED, wordings: list[str] = WORDINGS, tag: str = "exclude") -> list[dict]:
    rng = random.Random(seed + 73 + (0 if tag == 'exclude' else 1))
    sog = split_of_group()
    dev = {g for g, s in sog.items() if s == "dev"}
    cm = concept_map()
    all_qs = load_questions()
    by_qid = {q.qid: q for q in all_qs}
    facts = collections.defaultdict(dict)
    for q in all_qs:
        if q.source != "swiss_dwellings" or drawing_group(q.path) not in dev:
            continue
        if by_qid.get(cm.get(q.qid, q.qid), q).qid != q.qid:
            continue
        f = parse(q)
        if f and isinstance(q.answer, (int, float)):
            facts[q.path][f] = q.answer
    rows = []
    paths = [p for p in sorted(facts) if any(k[0] == "swiss_total_area" for k in facts[p])
             and sum(k[0] == "swiss_apt_area" for k in facts[p]) >= 2]
    rng.shuffle(paths)
    for i, path in enumerate(paths[:30]):
        F = facts[path]
        total = next(v for k, v in F.items() if k[0] == "swiss_total_area")
        apts = sorted((k[1], v) for k, v in F.items() if k[0] == "swiss_apt_area")
        a, va = rng.choice(apts)
        if not 0 < va < total:
            continue
        qtext = wordings[i % len(wordings)].format(a=a)
        qid = "ex" + hashlib.sha1(f"{path}|{qtext}".encode()).hexdigest()[:10]
        rows.append({"qid": qid, "path": path, "question": qtext, "answer": round(total - va, 2), "unit": "m2",
                     "type": "area", "source": "swiss_dwellings",
                     "meta": {"kind": tag, "wording": i % len(wordings), "apartment": a, "apt_area": va,
                              "total": total}})
    return rows


if __name__ == "__main__":
    import sys

    two = len(sys.argv) > 1 and sys.argv[1] == "2"
    rows = build(wordings=WORDINGS2, tag="exclude2") if two else build()
    OUT = OUT.with_name("exclude2.jsonl") if two else OUT
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(OUT, len(rows))
