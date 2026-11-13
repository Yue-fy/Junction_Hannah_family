"""Generate the `hard2` split: reasoning kinds that questions.jsonl never asks, answers from ground truth only.

Stoa: the hidden test is "harder and different" and "answers are not so simple". `hard` (stoa/eval/hard.py)
covers translations, paraphrases and simple compositions (sum, difference, max, yes/no). `hard2` adds
aggregations a template router has not seen, all computed from known answers of the SAME dev drawing:

- swiss:  threshold counts over rooms, average room area, apartment share of the floor (%), ratio of two
          apartments, room sums in ft², smallest apartment (text), doors per apartment (ratio), floor area
          outside one apartment
- ifc:    average room area per storey, two storeys combined, which storey has more doors (text), wall length
          in feet, threshold counts over rooms, room share of its storey (%)
- cubicasa: wet rooms (bathrooms + WC rooms + saunas), toilets + showers/baths, "more bedrooms than
          bathrooms?" and "at least two WC seats?" (yes/no)

New scored type `ratio` (dimensionless numbers: percentages, ratios) is scored like areas (within 2%).
Only DEV drawings are used (never test/train). Thresholds are placed so that no value is within 5% of them.

Run:  python -m stoa.eval.hard2 --write   -> $JUNCTION_SHARED/results/splits/hard2.jsonl  (refuses to overwrite
without --force). Each row: {qid, path, question, answer, unit, type, source, group, meta: {kind: "reasoning",
recipe, from_qids}}.
"""
from __future__ import annotations

import collections
import json
import random

from stoa.data import concept_map, drawing_group, ifc_model_for, load_questions
from stoa.eval.hard import FT2_PER_M2, FT_PER_M, _row, parse
from stoa.eval.splits import SEED, split_of_group, splits_dir

QUOTAS = {"cubicasa5k": 100, "swiss_dwellings": 120, "ifc_models": 80}


def _ids(rooms: list[tuple]) -> str:
    """[(room_no, label, q)] -> "2.01 ('Zimmer'), 2.02 ('Bad') and 2.03 ('Küche')" """
    parts = [f"{r} ('{lab}')" for r, lab, _ in rooms]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _threshold_any(values: list[float], rng: random.Random) -> float | None:
    """A round threshold below all, between two, or above all values (so the answer varies), >= 5% from each."""
    vs = sorted(values)
    spots = [vs[0] * 0.8, vs[-1] * 1.2] + [(a + b) / 2 for a, b in zip(vs, vs[1:]) if b > a * 1.12]
    rng.shuffle(spots)
    for c in spots:
        for t in (round(c), round(c, 1)):
            if t > 0 and all(abs(v - t) > 0.05 * max(v, t) for v in vs):
                return t
    return None


def _threshold(values: list[float], rng: random.Random) -> float | None:
    """A round threshold strictly between two sorted values, at least 5% away from every value."""
    vs = sorted(values)
    gaps = [(a, b) for a, b in zip(vs, vs[1:]) if b > a * 1.12]
    if not gaps:
        return None
    a, b = rng.choice(gaps)
    for t in (round((a + b) / 2), round((a + b) / 2, 1)):
        if all(abs(v - t) > 0.05 * max(v, t) for v in vs):
            return t
    return None


def swiss(facts, rng) -> list[tuple]:
    out = []
    rooms = [(f[1], f[2], q) for f, q in facts if f[0] == "swiss_room_area" and isinstance(q.answer, (int, float))]
    apts = [(f[1], q) for f, q in facts if f[0] == "swiss_apt_area" and isinstance(q.answer, (int, float))]
    total = next((q for f, q in facts if f[0] == "swiss_total_area"), None)
    fixed = {f[1]: q for f, q in facts if f[0] == "swiss"}
    if len(rooms) >= 2:
        two = rng.sample(rooms, 2)
        vs = sorted(q.answer for *_, q in two)
        t = _threshold_any(vs, rng)
        if t is not None:
            n = sum(1 for *_, q in two if q.answer > t)
            out.append((f"How many of the rooms {_ids(two)} have a net floor area of more than {t:g} m²?", n, "count",
                        "count", "rooms-above-threshold", [q.qid for *_, q in two]))
        avg = sum(q.answer for *_, q in two) / 2
        out.append((f"What is the average net floor area of rooms {_ids(two)}, in m²?", round(avg, 2), "m2", "area",
                    "average-room-area", [q.qid for *_, q in two]))
    if len(rooms) >= 2:
        two = rng.sample(rooms, 2)
        s = sum(q.answer for *_, q in two)
        out.append((f"What is the combined net floor area of rooms {_ids(two)}, in square feet?",
                    round(s * FT2_PER_M2, 1), "ft2", "area", "room-sum-ft2", [q.qid for *_, q in two]))
    if total is not None and isinstance(total.answer, (int, float)) and total.answer > 0 and apts:
        a, qa = rng.choice(apts)
        if qa.answer < total.answer:
            out.append((f"What share of the total net floor area of all numbered indoor rooms on this floor does "
                        f"apartment {a} take up, in percent?", round(100 * qa.answer / total.answer, 1), "%", "ratio",
                        "apartment-share-pct", [qa.qid, total.qid]))
            out.append((f"What is the total net floor area, in m², of the numbered indoor rooms on this floor that do "
                        f"not belong to apartment {a}?", round(total.answer - qa.answer, 2), "m2", "area",
                        "floor-minus-apartment", [qa.qid, total.qid]))
    if len(apts) >= 2:
        (a1, q1), (a2, q2) = rng.sample(apts, 2)
        big, small = ((a1, q1), (a2, q2)) if q1.answer >= q2.answer else ((a2, q2), (a1, q1))
        if small[1].answer > 0 and big[1].answer > small[1].answer * 1.05:
            out.append((f"How many times larger is apartment {big[0]} than apartment {small[0]} by net floor area? "
                        f"Give the ratio.", round(big[1].answer / small[1].answer, 2), None, "ratio",
                        "apartment-ratio", [big[1].qid, small[1].qid]))
    if len(apts) >= 2:
        two = rng.sample(apts, 2)
        vs = sorted(q.answer for _, q in two)
        if vs[1] > vs[0] * 1.05:
            low = min(two, key=lambda t: t[1].answer)
            out.append((f"Which is smaller by net floor area, apartment {two[0][0]} or apartment {two[1][0]}?",
                        f"apartment {low[0]}", None, "text", "smaller-apartment", [q.qid for _, q in two]))
    d, ap = fixed.get("doors"), fixed.get("apartments")
    if d is not None and ap is not None and isinstance(ap.answer, (int, float)) and ap.answer > 1:
        out.append(("On average, how many doors are drawn per apartment on this floor plan (all doors on the floor "
                    "divided by the number of apartments)?", round(d.answer / ap.answer, 2), None, "ratio",
                    "doors-per-apartment", [d.qid, ap.qid]))
    return out


def ifc(facts, rng) -> list[tuple]:
    """facts of ONE model (all its plan files and the model itself). Single-storey questions are asked on the
    plan file the facts came from; two-storey questions on the model (.ifc)."""
    from stoa.data import ifc_model_for

    out = []
    model = ifc_model_for(facts[0][1].path) or facts[0][1].path
    st_area = {f[1]: q for f, q in facts if f[0] == "ifc_storey_area" and isinstance(q.answer, (int, float))}
    plan = collections.defaultdict(dict)
    for f, q in facts:
        if f[0] == "ifc_plan_count":
            plan[f[2]][f[1]] = q
    rooms = collections.defaultdict(list)
    for f, q in facts:
        if f[0] == "ifc_room_area" and isinstance(q.answer, (int, float)):
            rooms[f[2]].append((f[1], q))
    walls = {f[1]: q for f, q in facts if f[0] == "ifc_wall_length" and isinstance(q.answer, (int, float))}
    for st, qa in st_area.items():
        qn = plan.get(st, {}).get("rooms (spaces)")
        if qn is not None and qn.answer and qa.answer > 0:
            out.append((f"What is the average net floor area per room (space) on '{st}', in m²?",
                        round(qa.answer / qn.answer, 3), "m2", "area", "average-room-area-storey", [qa.qid, qn.qid],
                        qa.path))
    if len(st_area) >= 2:
        (s1, q1), (s2, q2) = rng.sample(sorted(st_area.items()), 2)
        out.append((f"What is the combined net floor area of all rooms (spaces) on '{s1}' and on '{s2}', in m²?",
                    round(q1.answer + q2.answer, 3), "m2", "area", "two-storeys-area", [q1.qid, q2.qid], model))
    doors = {st: o["doors"] for st, o in plan.items() if "doors" in o}
    if len(doors) >= 2:
        (s1, q1), (s2, q2) = rng.sample(sorted(doors.items()), 2)
        if q1.answer != q2.answer:
            top = s1 if q1.answer > q2.answer else s2
            out.append((f"Which storey has more doors on its floor plan, '{s1}' or '{s2}'?", top, None, "text",
                        "storey-more-doors", [q1.qid, q2.qid], model))
    for st, qw in walls.items():
        out.append((f"What is the total length of all walls on '{st}', in feet?", round(qw.answer * FT_PER_M, 2), "ft",
                    "length", "wall-length-ft", [qw.qid], qw.path))
    for st, rs in rooms.items():
        if len(rs) >= 4:
            four = rng.sample(rs, 4)
            t = _threshold([q.answer for _, q in four], rng)
            if t is not None:
                names = ", ".join(f"'{n}'" for n, _ in four[:-1]) + f" and '{four[-1][0]}'"
                out.append((f"How many of the rooms {names} on '{st}' have a net floor area of more than {t:g} m²?",
                            sum(1 for _, q in four if q.answer > t), "count", "count", "rooms-above-threshold",
                            [q.qid for _, q in four], four[0][1].path))
        if st in st_area and rs and st_area[st].answer > 0:
            n, q = rng.choice(rs)
            out.append((f"What percentage of the total net floor area of '{st}' does the room '{n}' take up?",
                        round(100 * q.answer / st_area[st].answer, 2), "%", "ratio", "room-share-pct",
                        [q.qid, st_area[st].qid], q.path))
    return out


def cubicasa(facts, rng) -> list[tuple]:
    out = []
    by = {f[1]: q for f, q in facts if f[0] == "cubi" and isinstance(q.answer, (int, float))}

    def has(*ks):
        return all(k in by for k in ks)

    if has("bathrooms", "wc_rooms", "saunas"):
        out.append(("How many wet rooms does this floor plan have, counting bathrooms or washrooms (KH, KPH, PH, PESUH, "
                    "SH), separate WC rooms and saunas together?",
                    by["bathrooms"].answer + by["wc_rooms"].answer + by["saunas"].answer, "count", "count", "wet-rooms",
                    [by[k].qid for k in ("bathrooms", "wc_rooms", "saunas")]))
    if has("wc_seats", "showers_baths"):
        out.append(("How many toilet seats, showers and bathtubs are drawn on this floor plan together?",
                    by["wc_seats"].answer + by["showers_baths"].answer, "count", "count", "wc+showers",
                    [by["wc_seats"].qid, by["showers_baths"].qid]))
        out.append(("Does this floor plan show at least two toilet seats (WC bowls)? Answer yes or no.",
                    "yes" if by["wc_seats"].answer >= 2 else "no", None, "text", "two-wc-yes-no", [by["wc_seats"].qid]))
    if has("bedrooms", "bathrooms") and by["bedrooms"].answer != by["bathrooms"].answer:
        out.append(("Does this apartment have more bedrooms (MH) than bathrooms or washrooms (not counting separate WC "
                    "rooms)? Answer yes or no.", "yes" if by["bedrooms"].answer > by["bathrooms"].answer else "no", None,
                    "text", "more-bedrooms-than-bathrooms", [by["bedrooms"].qid, by["bathrooms"].qid]))
    return out


GEN = {"swiss_dwellings": swiss, "ifc_models": ifc, "cubicasa5k": cubicasa}


def build(seed: int = SEED) -> list[dict]:
    rng = random.Random(seed + 2)
    sog = split_of_group()
    dev_groups = {g for g, s in sog.items() if s == "dev"}
    cm = concept_map()
    all_qs = load_questions()
    by_qid = {q.qid: q for q in all_qs}
    facts_by_path = collections.defaultdict(list)
    for q in all_qs:
        if q.source not in GEN or drawing_group(q.path) not in dev_groups:
            continue
        if by_qid.get(cm[q.qid], q).qid != q.qid:
            continue  # each concept once, via its English row
        f = parse(q)
        if f:
            key = (ifc_model_for(q.path) or q.path) if q.source == "ifc_models" else q.path
            facts_by_path[key].append((f, q))
    cands = collections.defaultdict(list)
    for key in sorted(facts_by_path):
        facts = facts_by_path[key]
        src = facts[0][1].source
        for item in GEN[src](facts, rng):
            text, ans, unit, qtype, recipe, ids = item[:6]
            path = item[6] if len(item) > 6 else key
            cands[src].append(_row(path, text, ans, unit, qtype, "reasoning", recipe, ids))
    out, seen = [], set()
    for src, n in QUOTAS.items():
        rows = sorted(cands[src], key=lambda r: r["qid"])
        rng.shuffle(rows)
        by_r = collections.defaultdict(list)
        for r in rows:
            by_r[r["meta"]["recipe"]].append(r)
        picked = []
        while len(picked) < n and any(by_r.values()):
            for k in sorted(by_r):
                if by_r[k] and len(picked) < n:
                    r = by_r[k].pop()
                    if r["qid"] not in seen:
                        seen.add(r["qid"])
                        picked.append(r)
        out.extend(picked)
    return out


def write(seed: int = SEED, force: bool = False) -> dict:
    f = splits_dir() / "hard2.jsonl"
    if f.exists() and not force:
        raise SystemExit(f"{f} exists; splits are frozen (use --force only if nobody has run on it)")
    rows = build(seed)
    with open(f, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    c = collections.Counter((r["source"], r["meta"]["recipe"], r["type"]) for r in rows)
    return {"n": len(rows), "path": str(f), "by": {"/".join(k): v for k, v in sorted(c.items())}}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.write:
        print(json.dumps(write(force=a.force), indent=1))
    else:
        rows = build()
        c = collections.Counter((r["source"], r["meta"]["recipe"]) for r in rows)
        for k, v in sorted(c.items()):
            print(v, k)
        for r in random.Random(1).sample(rows, min(14, len(rows))):
            print(r["source"][:5], "|", r["question"], "->", r["answer"], r["unit"])
