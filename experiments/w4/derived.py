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


def build2(seed: int = SEED) -> list[dict]:
    """`derived2`: NEW wordings and recipes written before any run on them (generality check for derived.jsonl's
    fixes): 'apiece', thousands separators, 'each X needs', 'pro m²' in German, Finnish 'jos', 'per 10 m²', no 'if'."""
    rng = random.Random(seed + 13)
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
            b, sk = g("cubi", "bedrooms"), g("cubi", "sinks")
            if b:
                cands["fi-beds"].append(_row(path, "Jos jokaiseen makuuhuoneeseen tarvitaan kaksi sänkyä, montako "
                                                   "sänkyä tarvitaan yhteensä?", 2 * b, "count", "count", "fi-beds",
                                             "cubicasa5k"))
            if sk:
                cands["taps"].append(_row(path, "Each sink or wash basin on this plan needs one new tap costing 85 euros. "
                                                "What do the taps cost altogether?", 85 * sk, "EUR", "area", "taps",
                                          "cubicasa5k"))
        elif "swiss_dwellings" in path:
            apts = [(f[1], v) for f, v in F.items() if f[0] == "swiss_apt_area"]
            if apts:
                a, v = rng.choice(sorted(apts))
                cands["de-rent"].append(_row(path, f"Wie hoch ist die Monatsmiete der Wohnung {a} (Nettofläche ohne "
                                                   f"Balkone und Aussenflächen) bei 25 CHF pro m²?", round(25 * v, 2),
                                             "CHF", "area", "de-rent", "swiss_dwellings"))
            d = g("swiss", "doors")
            if d:
                cands["door-paint"].append(_row(path, "Painting one door takes 1.5 hours. How many hours does it take to "
                                                      "paint all the doors drawn on this plan?", round(1.5 * d, 2), "h",
                                                "area", "door-paint", "swiss_dwellings"))
        else:
            area = {f[1]: v for f, v in F.items() if f[0] == "ifc_storey_area"}
            doors = {f[2]: v for f, v in F.items() if f[0] == "ifc_plan_count" and f[1] == "doors"}
            wins = {f[2]: v for f, v in F.items() if f[0] == "ifc_plan_count" and f[1] == "windows"}
            for st, n in wins.items():
                if n:
                    cands["window-apiece"].append(_row(path, f"What would it cost to replace every window on '{st}' at "
                                                             f"1,200 € apiece?", 1200 * n, "EUR", "area",
                                                       "window-apiece", "ifc_models"))
            for st, n in doors.items():
                if n and area.get(st):
                    cands["doors-per-10"].append(_row(path, f"Doors on '{st}': how many are there per 10 m² of room "
                                                            f"area?", round(10 * n / area[st], 4), "", "area",
                                                      "doors-per-10", "ifc_models"))
            for st, v in area.items():
                if v:
                    cands["fr-cleaning"].append(_row(path, f"Le nettoyage coûte 2,40 € par m². Combien coûte le "
                                                           f"nettoyage de toutes les pièces de '{st}' ?",
                                                     round(2.4 * v, 2), "EUR", "area", "fr-cleaning", "ifc_models"))
    out = []
    for recipe in sorted(cands):
        rows = cands[recipe]
        rng.shuffle(rows)
        seen = collections.Counter()
        for r in rows:
            if seen[r["path"]] >= 2:
                continue
            seen[r["path"]] += 1
            r["meta"]["kind"] = "derived2"
            out.append(r)
            if sum(seen.values()) >= 8:
                break
    return out


def build3(seed: int = SEED) -> list[dict]:
    """`derived3` (cycle 72, written before any run, NOT tuned on): unit conversions, time constants with a unit change,
    a relative difference between apartments, per-unit rates on ifc, a price per apartment."""
    rng = random.Random(seed + 17)
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
            wc, ba = g("cubi", "wc_seats"), g("cubi", "bathrooms")
            if wc and ba:
                cands["wc-per-bath"].append(_row(path, "On this plan, how many toilet seats are there per bathroom "
                                                       "(washrooms, not separate WC rooms)?", round(wc / ba, 3), "",
                                                 "area", "wc-per-bath", "cubicasa5k"))
        elif "swiss_dwellings" in path:
            apts = sorted((f[1], v) for f, v in F.items() if f[0] == "swiss_apt_area")
            if len(apts) >= 2:
                (a1, v1), (a2, v2) = rng.sample(apts, 2)
                if v1 > v2:
                    cands["apt-pct"].append(_row(path, f"By what percentage is apartment {a1} larger than apartment "
                                                       f"{a2} (net floor area)?", round(100 * (v1 - v2) / v2, 3), "%",
                                                 "area", "apt-pct", "swiss_dwellings"))
            n = g("swiss", "apartments")
            if n:
                cands["mailboxes"].append(_row(path, "Every apartment on this floor gets a new letterbox for 60 CHF. "
                                                     "What do the letterboxes cost in total?", 60 * n, "CHF", "area",
                                               "mailboxes", "swiss_dwellings"))
            for f, v in F.items():
                if f[0] == "swiss_label_count" and v and rng.random() < 0.5:
                    cands["clean-minutes"].append(_row(
                        path, f"Cleaning one room labelled '{f[1]}' takes 20 minutes. How many hours does cleaning all "
                              f"of them on this floor take?", round(v * 20 / 60, 3), "h", "area", "clean-minutes",
                        "swiss_dwellings"))
                    break
        else:
            area = {f[1]: v for f, v in F.items() if f[0] == "ifc_storey_area"}
            doors = {f[2]: v for f, v in F.items() if f[0] == "ifc_plan_count" and f[1] == "doors"}
            length = {f[1]: v for f, v in F.items() if f[0] == "ifc_wall_length"}
            for st, v in area.items():
                if v:
                    cands["sqft"].append(_row(path, f"How many square feet do all the rooms on '{st}' cover together?",
                                              round(v * 10.7639, 2), "ft2", "area", "sqft", "ifc_models"))
            for st, v in length.items():
                if v and doors.get(st):
                    cands["wall-per-door"].append(_row(path, f"What length of wall is there per door on '{st}', in "
                                                             f"metres?", round(v / doors[st], 3), "m", "area",
                                                       "wall-per-door", "ifc_models"))
    out = []
    for recipe in sorted(cands):
        rows = cands[recipe]
        rng.shuffle(rows)
        seen = collections.Counter()
        for r in rows:
            if seen[r["path"]] >= 2:
                continue
            seen[r["path"]] += 1
            r["meta"]["kind"] = "derived3"
            out.append(r)
            if sum(seen.values()) >= 8:
                break
    return out


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["3"]:
        rows = build3()
        out3 = OUT.with_name("derived3.jsonl")
        out3.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        print(len(rows), "rows ->", out3, collections.Counter(r["meta"]["recipe"] for r in rows))
        sys.exit(0)

    if sys.argv[1:] == ["2"]:
        rows = build2()
        out2 = OUT.with_name("derived2.jsonl")
        out2.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        print(len(rows), "rows ->", out2, collections.Counter(r["meta"]["recipe"] for r in rows))
        sys.exit(0)
    rows = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(len(rows), "rows ->", OUT, collections.Counter(r["meta"]["recipe"] for r in rows))
