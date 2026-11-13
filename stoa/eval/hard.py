"""Generate the `hard` split: generality checks whose answers come only from existing ground truth.

Stoa says the hidden test is harder and different from questions.jsonl. This split measures whether a
solver generalises beyond the templates, using DEV drawings only (never test/train):

- translation: the other-language twin of a dev question (real dataset rows, same answer; the eval split
  kept only one language per concept, see `stoa.eval.splits`).
- paraphrase: the same question reworded by hand-written rules (English, plus Swedish/German variants), some
  with a unit change (m² -> ft², m -> ft) to catch unit handling.
- composition: new questions computed from several known answers on the same drawing: sums ("doors and
  windows in total"), differences ("how many more windows than doors"), sums of two room areas, the
  largest of three rooms (numeric and text), sanitary fixture totals, yes/no presence.

Run:  python -m stoa.eval.hard --write   -> $JUNCTION_SHARED/results/splits/hard.jsonl
Each row: {qid, path, question, answer, unit, type, source, group, meta: {kind, recipe, from_qids}}.
The eval reports accuracy per kind (`by_kind`) for this split.
"""

from __future__ import annotations

import collections
import hashlib
import json
import random
import re

from stoa.data import Question, concept_map, drawing_group, load_questions
from stoa.eval.splits import SEED, split_of_group, splits_dir

FT2_PER_M2 = 10.7639104
FT_PER_M = 1 / 0.3048

QUOTAS = {  # per kind per source
    "translation": {"cubicasa5k": 100, "swiss_dwellings": 90, "ifc_models": 60},
    "paraphrase": {"cubicasa5k": 100, "swiss_dwellings": 90, "ifc_models": 60},
    "composition": {"cubicasa5k": 100, "swiss_dwellings": 90, "ifc_models": 60},
}

# --- parsing English dataset questions into facts ---------------------------------------------------------

CUBI = {
    "How many windows are shown on this floor plan?": "windows",
    "How many floors (storeys) does this floor plan show?": "floors",
    "How many toilet bowls (WC seats) are drawn on this floor plan?": "wc_seats",
    "How many sinks and wash basins (kitchen and bathroom combined; a double-bowl sink counts as one) are drawn on this floor plan?": "sinks",
    "How many showers and bathtubs are drawn on this floor plan in total?": "showers_baths",
    "How many doors are shown on this floor plan? Count doorways fitted with a door; open doorways without a door leaf do not count.": "doors",
    "How many saunas are on this floor plan?": "saunas",
    "How many kitchens (including kitchenettes, open kitchens and utility kitchens) are on this floor plan?": "kitchens",
    "How many bedrooms (makuuhuone, usually marked MH) are on this floor plan?": "bedrooms",
    "How many bathrooms or washrooms (e.g. KH, KPH, PH, PESUH, SH) are on this floor plan, not counting separate WC rooms?": "bathrooms",
    "How many separate WC rooms (toilet rooms marked WC) are on this floor plan?": "wc_rooms",
    "How many balconies (parveke, including glazed balconies) are on this floor plan?": "balconies",
}
SWISS_FIXED = {
    "How many apartments (residential units) are shown on this floor plan?": "apartments",
    "How many doors (interior doors and entrance doors together) are drawn on this floor plan?": "doors",
    "How many windows are drawn on this floor plan?": "windows",
    "How many toilets (WC) are drawn on this floor plan?": "toilets",
    "How many washbasins are drawn on this floor plan?": "washbasins",
    "How many bathtubs are drawn on this floor plan?": "bathtubs",
    "How many showers are drawn on this floor plan?": "showers",
}
RE = {
    "swiss_label_count": re.compile(r"^How many rooms labelled '(.+)' are there on this floor\?$"),
    "swiss_room_area": re.compile(r"^What is the net floor area of room (\S+) \('(.+)'\) in m²\?$"),
    "swiss_label_area": re.compile(r"^What is the total net area in m² of all rooms labelled '(.+)' on this floor\?$"),
    "swiss_apt_area": re.compile(r"^What is the net floor area of apartment (\w+) in m², summing all its rooms"),
    "swiss_total_area": re.compile(r"^What is the total net floor area in m² of all numbered indoor rooms on this floor"),
    "ifc_room_area": re.compile(r"^What is the net floor area of the room '(.+)' on '(.+)', in m²\?$"),
    "ifc_plan_count": re.compile(r"^How many (rooms \(spaces\)|doors|stairs|walls|columns|windows|beams) are shown on the floor plan of '(.+)'\?$"),
    "ifc_storey_area": re.compile(r"^What is the total net floor area of all rooms \(spaces\) on '(.+)', in m²\?$"),
    "ifc_wall_length": re.compile(r"^What is the total length of all walls on '(.+)', in metres\?$"),
    "ifc_model_count": re.compile(r"^How many ([\w ()]+) are there in the model '(.+)'\?$"),
}


def parse(q: Question) -> tuple | None:
    s = q.question.strip()
    if q.source == "cubicasa5k" and s in CUBI:
        return ("cubi", CUBI[s])
    if q.source == "swiss_dwellings":
        if s in SWISS_FIXED:
            return ("swiss", SWISS_FIXED[s])
        for k in ("swiss_label_count", "swiss_room_area", "swiss_label_area", "swiss_apt_area", "swiss_total_area"):
            m = RE[k].match(s)
            if m:
                return (k, *m.groups())
    if q.source == "ifc_models":
        for k in ("ifc_room_area", "ifc_plan_count", "ifc_storey_area", "ifc_wall_length", "ifc_model_count"):
            m = RE[k].match(s)
            if m:
                return (k, *m.groups())
    return None


# --- paraphrase rules ---------------------------------------------------------------------------------------

CUBI_NOUN = {
    "windows": "windows", "floors": "storeys (floors)", "wc_seats": "toilet seats (WC bowls)",
    "sinks": "sinks and washbasins (kitchen and bathrooms together; a double sink counts once)",
    "showers_baths": "showers plus bathtubs", "doors": "doors (only doorways that have a door leaf)",
    "saunas": "saunas", "kitchens": "kitchens (kitchenettes, open and utility kitchens included)",
    "bedrooms": "bedrooms (rooms marked MH)", "bathrooms": "bathrooms or washrooms (KH, KPH, PH, PESUH, SH; separate WC rooms excluded)",
    "wc_rooms": "separate toilet rooms (marked WC)", "balconies": "balconies, glazed ones included",
}
CUBI_SV = {  # Swedish (Finland's second official language)
    "windows": "Hur många fönster finns på planritningen?",
    "doors": "Hur många dörrar finns på planritningen? Räkna bara dörröppningar med dörrblad.",
    "saunas": "Hur många bastur finns på planritningen?",
    "balconies": "Hur många balkonger (även inglasade) finns på planritningen?",
    "bedrooms": "Hur många sovrum (MH) finns på planritningen?",
    "kitchens": "Hur många kök (även kokvrår) finns på planritningen?",
}
CUBI_DE = {
    "windows": "Wie viele Fenster sind auf diesem Grundriss zu sehen?",
    "saunas": "Wie viele Saunen gibt es auf diesem Grundriss?",
    "wc_seats": "Wie viele WC-Schüsseln sind auf diesem Grundriss eingezeichnet?",
}
EN_FORMS = [
    "Count the {noun} on this plan.",
    "What is the number of {noun} in this drawing?",
    "Looking at this floor plan, how many {noun} are there?",
    "I need a quick count for a quantity takeoff: {noun} on this sheet?",
]
SWISS_NOUN = {"apartments": "residential units (apartments)", "doors": "doors, interior and entrance doors together",
              "windows": "windows", "toilets": "WCs (toilets)", "washbasins": "washbasins (lavabos)",
              "bathtubs": "bathtubs", "showers": "showers"}


def paraphrases(q: Question, fact: tuple, rng: random.Random) -> list[tuple[str, object, str, str]]:
    """-> [(question, answer, unit, recipe)]"""
    a, u = q.answer, q.unit
    out = []
    k = fact[0]
    if k == "cubi":
        key = fact[1]
        out.append((rng.choice(EN_FORMS).format(noun=CUBI_NOUN[key]), a, u, f"en-form:{key}"))
        if key in CUBI_SV:
            out.append((CUBI_SV[key], a, u, f"sv:{key}"))
        if key in CUBI_DE:
            out.append((CUBI_DE[key], a, u, f"de:{key}"))
    elif k == "swiss":
        out.append((rng.choice(EN_FORMS).format(noun=SWISS_NOUN[fact[1]]), a, u, f"en-form:{fact[1]}"))
    elif k == "swiss_label_count":
        out.append((f"Count the rooms named '{fact[1]}' on this floor plan.", a, u, "label-count"))
    elif k == "swiss_room_area":
        rid, lab = fact[1], fact[2]
        out.append((f"How large is room {rid} ('{lab}')? Give its net floor area in square metres.", a, u, "room-area"))
        out.append((f"What is the net floor area of room {rid} ('{lab}') in square feet?",
                    round(a * FT2_PER_M2, 2), "ft2", "room-area-ft2"))
    elif k == "swiss_label_area":
        out.append((f"Add up the net areas of all rooms labelled '{fact[1]}' on this floor. Answer in m².", a, u, "label-area"))
    elif k == "swiss_apt_area":
        out.append((f"What is the net living area of unit {fact[1]} in m² (all its rooms, without balconies, loggias, "
                    f"terraces or other outdoor spaces)?", a, u, "apt-area"))
    elif k == "swiss_total_area":
        out.append(("Summing all numbered indoor rooms on this floor (no balconies, loggias, terraces, other outdoor "
                    "spaces, shafts or voids), what is the net floor area in square feet?",
                    round(a * FT2_PER_M2, 1), "ft2", "total-area-ft2"))
    elif k == "ifc_room_area":
        room, st = fact[1], fact[2]
        out.append((f"How big is the room '{room}' on storey '{st}'? Net floor area in m², please.", a, u, "room-area"))
        out.append((f"On storey '{st}', what is the net floor area of '{room}' in square feet?",
                    round(a * FT2_PER_M2, 2), "ft2", "room-area-ft2"))
    elif k == "ifc_plan_count":
        obj, st = fact[1], fact[2]
        out.append((f"Count the {obj} on storey '{st}'.", a, u, "plan-count"))
    elif k == "ifc_storey_area":
        out.append((f"What do the net floor areas of all spaces on '{fact[1]}' add up to, in m²?", a, u, "storey-area"))
    elif k == "ifc_wall_length":
        out.append((f"What is the combined length of all walls on '{fact[1]}', in feet?", round(a * FT_PER_M, 2), "ft",
                    "wall-length-ft"))
    elif k == "ifc_model_count":
        out.append((f"Count all {fact[1]} in the model '{fact[2]}'.", a, u, "model-count"))
    return out


# --- compositions per drawing -------------------------------------------------------------------------------


def compositions(path: str, facts: list[tuple[tuple, Question]], rng: random.Random) -> list[tuple]:
    """-> [(question, answer, unit, type, recipe, from_qids)]"""
    out = []
    by = {}
    for f, q in facts:
        by[f] = q
    src = facts[0][1].source

    def get(*key):
        q = by.get(key)
        return (q.answer, q.qid) if q is not None and isinstance(q.answer, (int, float)) else (None, None)

    if src in ("cubicasa5k", "swiss_dwellings"):
        tag = "cubi" if src == "cubicasa5k" else "swiss"
        d, dq = get(tag, "doors")
        w, wq = get(tag, "windows")
        door_def = " Count doorways fitted with a door; open doorways without a door leaf do not count." if tag == "cubi" else ""
        if d is not None and w is not None:
            out.append((f"How many doors and windows are shown on this floor plan in total?{door_def}", d + w, "count",
                        "count", "doors+windows", [dq, wq]))
            if w != d:
                more, less, n = ("windows", "doors", w - d) if w > d else ("doors", "windows", d - w)
                out.append((f"How many more {more} than {less} are shown on this floor plan?{door_def}", n, "count",
                            "count", f"{more}-{less}", [dq, wq]))
        if tag == "cubi":
            parts = [get("cubi", k) for k in ("wc_seats", "sinks", "showers_baths")]
            if all(v is not None for v, _ in parts):
                out.append(("How many sanitary fixtures are drawn on this floor plan in total, counting toilet seats, "
                            "sinks and washbasins (a double-bowl sink counts as one), showers and bathtubs together?",
                            sum(v for v, _ in parts), "count", "count", "wc+sinks+showers", [x for _, x in parts]))
            b, bq = get("cubi", "bedrooms")
            ba, baq = get("cubi", "bathrooms")
            if b is not None and ba is not None:
                out.append(("How many bedrooms (MH) and bathrooms or washrooms (KH, KPH, PH, PESUH, SH; not separate WC "
                            "rooms) does this floor plan have together?", b + ba, "count", "count", "bedrooms+bathrooms",
                            [bq, baq]))
            s, sq = get("cubi", "saunas")
            if s is not None:
                out.append(("Does this apartment have a sauna? Answer yes or no.", "yes" if s > 0 else "no", None, "text",
                            "sauna-yes-no", [sq]))
        else:
            parts = [(k, *get("swiss", k)) for k in ("toilets", "washbasins", "bathtubs", "showers")]
            parts = [p for p in parts if p[1] is not None]
            if len(parts) >= 3:
                names = ", ".join(p[0] for p in parts[:-1]) + " and " + parts[-1][0]
                out.append((f"How many {names} are drawn on this floor plan altogether?", sum(p[1] for p in parts),
                            "count", "count", "sanitary-total", [p[2] for p in parts]))
            rooms = [(f[1], f[2], q) for f, q in facts if f[0] == "swiss_room_area"]
            if len(rooms) >= 2:
                (r1, l1, q1), (r2, l2, q2) = rng.sample(rooms, 2)
                out.append((f"What is the combined net floor area of room {r1} ('{l1}') and room {r2} ('{l2}') in m²?",
                            round(q1.answer + q2.answer, 2), "m2", "area", "room-a+room-b", [q1.qid, q2.qid]))
                if abs(q1.answer - q2.answer) / max(q1.answer, q2.answer) > 0.05:
                    big, small = (q1, q2) if q1.answer > q2.answer else (q2, q1)
                    rb = r1 if big is q1 else r2
                    rs = r2 if big is q1 else r1
                    out.append((f"By how many m² is room {rb} larger than room {rs} (net floor area)?",
                                round(big.answer - small.answer, 2), "m2", "area", "room-a-minus-room-b",
                                [big.qid, small.qid]))
            if len(rooms) >= 3:
                tri = rng.sample(rooms, 3)
                areas = sorted(q.answer for _, _, q in tri)
                if areas[-1] > areas[-2] * 1.05:  # unambiguous
                    top = max(tri, key=lambda t: t[2].answer)
                    ids = ", ".join(f"{r} ('{lab}')" for r, lab, _ in tri[:-1]) + f" and {tri[-1][0]} ('{tri[-1][1]}')"
                    out.append((f"Of rooms {ids}, which one has the largest net floor area?", f"room {top[0]}", None,
                                "text", "argmax-room", [t[2].qid for t in tri]))
                    out.append((f"What is the net floor area, in m², of the largest of rooms {ids}?", top[2].answer,
                                "m2", "area", "max-room-area", [t[2].qid for t in tri]))
            apts = [(f[1], q) for f, q in facts if f[0] == "swiss_apt_area"]
            if len(apts) >= 2:
                (a1, q1), (a2, q2) = rng.sample(apts, 2)
                out.append((f"What is the combined net floor area of apartments {a1} and {a2} in m² (all rooms except "
                            f"balconies, loggias, terraces and other outdoor spaces)?", round(q1.answer + q2.answer, 2),
                            "m2", "area", "apt-a+apt-b", [q1.qid, q2.qid]))
    elif src == "ifc_models":
        rooms = collections.defaultdict(list)
        for f, q in facts:
            if f[0] == "ifc_room_area":
                rooms[f[2]].append((f[1], q))
        for st, rs in rooms.items():
            if len(rs) >= 2:
                (n1, q1), (n2, q2) = rng.sample(rs, 2)
                out.append((f"What is the combined net floor area of the rooms '{n1}' and '{n2}' on '{st}', in m²?",
                            round(q1.answer + q2.answer, 3), "m2", "area", "room-a+room-b", [q1.qid, q2.qid]))
            if len(rs) >= 3:
                tri = rng.sample(rs, 3)
                areas = sorted(q.answer for _, q in tri)
                if areas[-1] > areas[-2] * 1.05:
                    top = max(tri, key=lambda t: t[1].answer)
                    names = ", ".join(f"'{n}'" for n, _ in tri[:-1]) + f" and '{tri[-1][0]}'"
                    out.append((f"Which of the rooms {names} on '{st}' has the largest net floor area?", top[0], None,
                                "text", "argmax-room", [q.qid for _, q in tri]))
                    out.append((f"What is the net floor area, in m², of the largest of the rooms {names} on '{st}'?",
                                top[1].answer, "m2", "area", "max-room-area", [q.qid for _, q in tri]))
        plan = collections.defaultdict(dict)
        for f, q in facts:
            if f[0] == "ifc_plan_count":
                plan[f[2]][f[1]] = q
        for st, objs in plan.items():
            if "doors" in objs and "windows" in objs:
                d, w = objs["doors"], objs["windows"]
                out.append((f"How many doors and windows are shown on the floor plan of '{st}' in total?",
                            d.answer + w.answer, "count", "count", "doors+windows", [d.qid, w.qid]))
    return out


# --- build --------------------------------------------------------------------------------------------------


def _row(path, question, answer, unit, qtype, kind, recipe, from_qids):
    from stoa.data import source_of

    qid = "h" + hashlib.sha1(f"{path}\n{question}".encode()).hexdigest()[:11]
    return {"qid": qid, "path": path, "question": question, "answer": answer, "unit": unit, "type": qtype,
            "source": source_of(path), "group": drawing_group(path),
            "meta": {"kind": kind, "recipe": recipe, "from_qids": from_qids}}


def build(seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    sog = split_of_group()
    if not sog:
        raise RuntimeError("write the splits first (python -m stoa.eval.splits --write)")
    cm = concept_map()
    all_qs = load_questions()
    by_qid = {q.qid: q for q in all_qs}
    dev_ids = {json.loads(line)["qid"] for line in open(splits_dir() / "dev.jsonl", encoding="utf-8")}
    dev_groups = {g for g, s in sog.items() if s == "dev"}
    pool = [q for q in all_qs if drawing_group(q.path) in dev_groups and q.source in QUOTAS["translation"]]
    cands = {k: collections.defaultdict(list) for k in QUOTAS}

    # translation: the twin of a dev question
    twins = collections.defaultdict(list)
    for q in pool:
        twins[cm[q.qid]].append(q)
    for c, rows in twins.items():
        if len(rows) == 2:
            asked = [q for q in rows if q.qid in dev_ids]
            other = [q for q in rows if q.qid not in dev_ids]
            if asked and other:
                o = other[0]
                cands["translation"][o.source].append(_row(o.path, o.question, o.answer, o.unit, o.type, "translation",
                                                           "dataset-twin", [asked[0].qid]))

    # paraphrase + composition from English facts per file
    facts_by_path = collections.defaultdict(list)
    for q in pool:
        en = by_qid.get(cm[q.qid], q)
        if en.qid != q.qid:
            continue  # use each concept once, via its English row
        f = parse(q)
        if f:
            facts_by_path[q.path].append((f, q))
    for path in sorted(facts_by_path):
        facts = facts_by_path[path]
        for f, q in facts:
            for text, ans, unit, recipe in paraphrases(q, f, rng):
                cands["paraphrase"][q.source].append(_row(path, text, ans, unit, q.type, "paraphrase", recipe, [q.qid]))
        for text, ans, unit, qtype, recipe, src_ids in compositions(path, facts, rng):
            cands["composition"][facts[0][1].source].append(
                _row(path, text, ans, unit, qtype, "composition", recipe, src_ids))

    out, seen = [], set()
    for kind, quotas in QUOTAS.items():
        for src, n in quotas.items():
            rows = sorted(cands[kind][src], key=lambda r: r["qid"])
            rng.shuffle(rows)
            # spread over recipes: round-robin by recipe
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


def write(seed: int = SEED) -> dict:
    rows = build(seed)
    f = splits_dir() / "hard.jsonl"
    with open(f, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    c = collections.Counter((r["meta"]["kind"], r["source"], r["type"]) for r in rows)
    return {"n": len(rows), "path": str(f), "by": {"/".join(k): v for k, v in sorted(c.items())}}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    if a.write:
        print(json.dumps(write(), indent=1))
    else:
        rows = build()
        c = collections.Counter((r["meta"]["kind"], r["source"], r["meta"]["recipe"]) for r in rows)
        for k, v in sorted(c.items()):
            print(k, v)
        for r in random.Random(1).sample(rows, 12):
            print(r["meta"]["kind"], "|", r["question"], "->", r["answer"], r["unit"])
