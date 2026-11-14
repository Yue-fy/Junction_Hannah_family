"""`derived` probe split (W4, cycle 4): DERIVED quantities, computed FROM a measured quantity with a price, a rate or
a constant stated in the question. Not a dataset template, not a hard/hard2 recipe; written after W5 found
"if each door costs 450 euros, how much do the doors on '1.korrus' cost?" answered '46 count' at conf 0.97.

DEV drawings only; gold = arithmetic on the dataset's own gold answers (no model involved). Several languages.

ifc       door-cost (EN), tile-cost (DE, price per m2), area-per-door (EN, rate), windows-per-100m2 (FI, rate),
          wall-days (EN, given constant)
swiss     window-cost (FR, CHF), rent (EN, CHF per m2 of an apartment)
cubicasa  beds (EN, 'if every bedroom gets two beds'), wc-cost (DE)

    python experiments/w4/derived.py   -> $JUNCTION_SHARED/artifacts/W4/derived.jsonl
    python -m stoa.eval --solver pipeline --split $JUNCTION_SHARED/artifacts/W4/derived.jsonl
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

OUT = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")) / "artifacts/W4/derived.jsonl"
PER_RECIPE = 10


def _row(path, question, answer, unit, typ, recipe, src):
    qid = "dv" + hashlib.sha1(f"{path}|{question}".encode()).hexdigest()[:10]
    return {"qid": qid, "path": path, "question": question, "answer": answer, "unit": unit, "type": typ,
            "source": src, "meta": {"kind": "derived", "recipe": recipe}}


def build(seed: int = SEED) -> list[dict]:
    rng = random.Random(seed + 11)
    sog = split_of_group()
    dev_groups = {g for g, s in sog.items() if s == "dev"}
    cm = concept_map()
    all_qs = load_questions()
    by_qid = {q.qid: q for q in all_qs}
    facts = collections.defaultdict(dict)
    for q in all_qs:
        if q.source not in ("cubicasa5k", "swiss_dwellings", "ifc_models") or drawing_group(q.path) not in dev_groups:
            continue
        if by_qid.get(cm.get(q.qid, q.qid), q).qid != q.qid:
            continue
        f = parse(q)
        if f and isinstance(q.answer, (int, float)):
            facts[q.path][f] = q.answer
    cands = collections.defaultdict(list)
    for path in sorted(facts):
        F = facts[path]
        g = lambda *k: F.get(tuple(k))  # noqa: E731
        if "cubicasa5k" in path:
            b, wc = g("cubi", "bedrooms"), g("cubi", "wc_seats")
            if b:
                cands["beds"].append(_row(path, "If every bedroom gets two beds, how many beds are needed for this "
                                                "home?", 2 * b, "count", "count", "beds", "cubicasa5k"))
            if wc:
                cands["wc-cost"].append(_row(path, "Wenn ein WC-Becken 420 Euro kostet, was kosten alle WC-Becken auf "
                                                   "diesem Grundriss zusammen, in Euro?", 420 * wc, "EUR", "area",
                                             "wc-cost", "cubicasa5k"))
        elif "swiss_dwellings" in path:
            w = g("swiss", "windows")
            if w:
                cands["window-cost"].append(_row(path, "Si une fenêtre coûte 650 CHF, combien coûtent toutes les "
                                                       "fenêtres de ce plan, en CHF ?", 650 * w, "CHF", "area",
                                                 "window-cost", "swiss_dwellings"))
            apts = [(f[1], v) for f, v in F.items() if f[0] == "swiss_apt_area"]
            if apts:
                a, v = rng.choice(sorted(apts))
                cands["rent"].append(_row(path, f"If the rent is 28 CHF per m² per month, what is the monthly rent of "
                                                f"apartment {a} (net floor area without balconies and other outdoor "
                                                f"spaces), in CHF?", round(28 * v, 2), "CHF", "area", "rent",
                                          "swiss_dwellings"))
        else:
            area = {f[1]: v for f, v in F.items() if f[0] == "ifc_storey_area"}
            doors = {f[2]: v for f, v in F.items() if f[0] == "ifc_plan_count" and f[1] == "doors"}
            wins = {f[2]: v for f, v in F.items() if f[0] == "ifc_plan_count" and f[1] == "windows"}
            length = {f[1]: v for f, v in F.items() if f[0] == "ifc_wall_length"}
            for st, n in doors.items():
                if n:
                    cands["door-cost"].append(_row(path, f"If each door costs 450 euros, how much do the doors on "
                                                         f"'{st}' cost in total, in euros?", 450 * n, "EUR", "area",
                                                   "door-cost", "ifc_models"))
                    if area.get(st):
                        cands["area-per-door"].append(_row(path, f"How many square metres of floor are there per door "
                                                                 f"on '{st}'?", round(area[st] / n, 3), "m2", "area",
                                                           "area-per-door", "ifc_models"))
            for st, v in area.items():
                if v:
                    cands["tile-cost"].append(_row(path, f"Was kostet es, den ganzen Boden von '{st}' zu fliesen, wenn "
                                                         f"ein Quadratmeter 35 Euro kostet?", round(35 * v, 2), "EUR",
                                                   "area", "tile-cost", "ifc_models"))
                    if wins.get(st):
                        cands["windows-per-100m2"].append(_row(
                            path, f"Montako ikkunaa kerroksessa '{st}' on 100 neliömetriä kohden?",
                            round(100 * wins[st] / v, 3), "", "area", "windows-per-100m2", "ifc_models"))
            for st, v in length.items():
                if v:
                    cands["wall-days"].append(_row(path, f"If a crew builds 15 metres of wall per day, how many days "
                                                         f"do all the walls on '{st}' take?", round(v / 15, 3), "",
                                                   "area", "wall-days", "ifc_models"))
    out = []
    for recipe in sorted(cands):
        rows = cands[recipe]
        rng.shuffle(rows)
        seen = collections.Counter()
        for r in rows:  # at most 2 per drawing per recipe (ifc has few dev models)
            if seen[r["path"]] >= 2:
                continue
            seen[r["path"]] += 1
            out.append(r)
            if sum(seen.values()) >= PER_RECIPE:
                break
    return out


if __name__ == "__main__":
    rows = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(len(rows), "rows ->", OUT, collections.Counter(r["meta"]["recipe"] for r in rows))
