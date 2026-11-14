"""Generate `hard3`: a SEALED held-out set of DERIVED-quantity questions (prices, rates, constants, percentages, shares
stated in the question and applied to quantities the drawing holds). No wordings live in git.

Why: Stoa says the hidden answers are "not so simple". W4 built rules for derived questions on its own dev probe
(artifacts/W4/derived*.jsonl, experiments/w4/derived.py) and measures on it, so we have no honest number for this family.
hard3 uses DIFFERENT recipes (occupancy limits, yearly running costs, area growth, ft² prices, proportional cost
splits, detector counts, heater power, cleaning time, flooring with waste, hardware costs, wall surface, ...) with
constants drawn per instance, in several languages, read from $JUNCTION_SHARED/sealed/F/hard3_templates.json.

Answers: arithmetic on the dataset's own gold answers of DEV drawings only (never test/train). Integer answers that
need a floor() (occupancy) are only asked when the exact value is >= 10% away from an integer boundary.
Types: count (exact), area / length (2%, units), ratio (dimensionless numbers, money, hours, kW: 2%, unit trusted).
Rules (like hard2r, D12): only F and S0 run it, at milestones, aggregates only; never quote its questions or failures.

Run:  python -m stoa.eval.hard3 --write   -> $JUNCTION_SHARED/results/splits/hard3.jsonl  (refuses to overwrite)
"""
from __future__ import annotations

import collections
import json
import math
import os
import random
from pathlib import Path

from stoa.data import concept_map, drawing_group, ifc_model_for, load_questions
from stoa.eval.hard import FT2_PER_M2, _row, parse
from stoa.eval.splits import SEED, split_of_group, splits_dir

QUOTAS = {"cubicasa5k": 60, "swiss_dwellings": 70, "ifc_models": 50}
OFFSET = 23


def templates_path() -> Path:
    root = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")
    return Path(root) / "sealed" / "F" / "hard3_templates.json"


def _num(x: float) -> float:
    return round(x, 2)


def _ok_floor(x: float) -> bool:
    f = x - math.floor(x)
    return 0.1 <= f <= 0.9


def swiss(facts, rng) -> list[tuple]:
    """(recipe, params, answer, unit, type, from_qids)"""
    out = []
    apts = [(f[1], q) for f, q in facts if f[0] == "swiss_apt_area" and isinstance(q.answer, (int, float)) and q.answer > 0]
    total = next((q for f, q in facts if f[0] == "swiss_total_area" and isinstance(q.answer, (int, float))), None)
    fixed = {f[1]: q for f, q in facts if f[0] == "swiss" and isinstance(q.answer, (int, float))}
    if apts:
        a, qa = rng.choice(apts)
        k = rng.choice([8, 10, 12, 15])
        if _ok_floor(qa.answer / k):
            out.append(("s-occupancy", {"a": a, "k": k}, math.floor(qa.answer / k), "count", "count", [qa.qid]))
        a, qa = rng.choice(apts)
        p = rng.choice([0.9, 1.1, 1.35, 1.6])
        out.append(("s-heating-year", {"a": a, "p": p}, _num(12 * p * qa.answer), "EUR", "ratio", [qa.qid]))
        a, qa = rng.choice(apts)
        g = rng.choice([5, 8, 12, 15])
        out.append(("s-growth", {"a": a, "g": g}, _num(qa.answer * (1 + g / 100)), "m2", "area", [qa.qid]))
    if len(apts) >= 2:
        (a, qa), (b, qb) = rng.sample(apts, 2)
        bill = rng.choice([480, 600, 900, 1200])
        out.append(("s-split-bill", {"a": a, "b": b, "bill": bill}, _num(bill * qa.answer / (qa.answer + qb.answer)),
                    "EUR", "ratio", [qa.qid, qb.qid]))
    if total is not None and total.answer > 0:
        price = rng.choice([2.5, 3.2, 4.1])
        out.append(("s-carpet-ft2", {"price": price}, _num(total.answer * FT2_PER_M2 * price), "USD", "ratio",
                    [total.qid]))
    if "toilets" in fixed and "washbasins" in fixed and fixed["toilets"].answer + fixed["washbasins"].answer > 0:
        t, w = rng.choice([310, 420, 560]), rng.choice([140, 190, 260])
        out.append(("s-fixtures", {"t": t, "w": w}, t * fixed["toilets"].answer + w * fixed["washbasins"].answer,
                    "CHF", "ratio", [fixed["toilets"].qid, fixed["washbasins"].qid]))
    return out


def cubicasa(facts, rng) -> list[tuple]:
    out = []
    by = {f[1]: q for f, q in facts if f[0] == "cubi" and isinstance(q.answer, (int, float))}
    v = lambda k: by[k].answer  # noqa: E731
    if "bedrooms" in by and "floors" in by:
        out.append(("c-detectors", {}, v("bedrooms") + v("floors"), "count", "count", [by["bedrooms"].qid, by["floors"].qid]))
    if "saunas" in by and v("saunas") >= 1:
        kw = rng.choice([6, 8, 9])
        out.append(("c-heater", {"kw": kw}, kw * v("saunas"), "kW", "ratio", [by["saunas"].qid]))
    if "bathrooms" in by and v("bathrooms") >= 1:
        m = rng.choice([20, 25, 30])
        out.append(("c-cleaning", {"m": m}, m * v("bathrooms"), "min", "ratio", [by["bathrooms"].qid]))
    if "bedrooms" in by and "wc_seats" in by and v("wc_seats") >= 1 and v("bedrooms") >= 1:
        out.append(("c-bed-per-wc", {}, _num(v("bedrooms") / v("wc_seats")), None, "ratio",
                    [by["bedrooms"].qid, by["wc_seats"].qid]))
    if "balconies" in by and v("balconies") >= 1:
        n, e = rng.choice([2, 3]), rng.choice([25, 35, 40])
        out.append(("c-planters", {"n": n, "e": e}, n * e * v("balconies"), "EUR", "ratio", [by["balconies"].qid]))
    return out


def ifc(facts, rng) -> list[tuple]:
    """Single-storey recipes, asked on the plan file the storey's facts came from."""
    out = []
    st_area = {f[1]: q for f, q in facts if f[0] == "ifc_storey_area" and isinstance(q.answer, (int, float)) and q.answer > 0}
    plan = collections.defaultdict(dict)
    for f, q in facts:
        if f[0] == "ifc_plan_count" and isinstance(q.answer, (int, float)):
            plan[f[2]][f[1]] = q
    walls = {f[1]: q for f, q in facts if f[0] == "ifc_wall_length" and isinstance(q.answer, (int, float)) and q.answer > 0}
    for st, qa in sorted(st_area.items()):
        w = rng.choice([8, 10, 12])
        out.append(("i-flooring-waste", {"st": st, "w": w}, _num(qa.answer * (1 + w / 100)), "m2", "area", [qa.qid], qa.path))
        rate = rng.choice([80, 100, 150])
        out.append(("i-cleaning-hours", {"st": st, "rate": rate}, _num(qa.answer / rate), "h", "ratio", [qa.qid], qa.path))
    for st, d in sorted(plan.items()):
        if "doors" in d and "windows" in d and d["doors"].answer + d["windows"].answer > 0:
            pd, pw = rng.choice([95, 120, 150]), rng.choice([35, 45, 60])
            out.append(("i-hardware", {"st": st, "pd": pd, "pw": pw}, pd * d["doors"].answer + pw * d["windows"].answer,
                        "EUR", "ratio", [d["doors"].qid, d["windows"].qid], d["doors"].path))
    for st, qw in sorted(walls.items()):
        h = rng.choice([2.6, 2.7, 3.0])
        out.append(("i-wall-surface", {"st": st, "h": h}, _num(qw.answer * h), "m2", "area", [qw.qid], qw.path))
    return out


GEN = {"swiss_dwellings": swiss, "ifc_models": ifc, "cubicasa5k": cubicasa}


def build(seed: int = SEED) -> list[dict]:
    spec = json.load(open(templates_path(), encoding="utf-8"))
    rng = random.Random(seed + OFFSET)
    sog = split_of_group()
    dev_groups = {g for g, s in sog.items() if s == "dev"}
    cm = concept_map()
    all_qs = load_questions()
    by_qid = {q.qid: q for q in all_qs}
    facts_by_key = collections.defaultdict(list)
    for q in all_qs:
        if q.source not in GEN or drawing_group(q.path) not in dev_groups:
            continue
        if by_qid.get(cm[q.qid], q).qid != q.qid:
            continue  # each concept once, via its English row
        f = parse(q)
        if f:
            key = (ifc_model_for(q.path) or q.path) if q.source == "ifc_models" else q.path
            facts_by_key[key].append((f, q))
    cands = collections.defaultdict(list)
    for key in sorted(facts_by_key):
        facts = facts_by_key[key]
        src = facts[0][1].source
        for item in GEN[src](facts, rng):
            recipe, params, ans, unit, qtype, ids = item[:6]
            path = item[6] if len(item) > 6 else key
            wordings = spec[recipe]
            w = wordings[rng.randrange(len(wordings))]
            r = _row(path, w["text"].format(**params), ans, unit, qtype, "derived", recipe, ids)
            r["qid"] = "d" + r["qid"][1:]
            r["meta"]["lang"] = w["lang"]
            cands[src].append(r)
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
    """Write the split; print COUNTS only (never questions)."""
    f = splits_dir() / "hard3.jsonl"
    if f.exists() and not force:
        raise SystemExit(f"{f} exists; refusing to overwrite (sealed split). Use --force only with S0's OK.")
    rows = build(seed)
    with open(f, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    c = collections.Counter((r["source"], r["meta"]["recipe"], r["type"]) for r in rows)
    langs = collections.Counter(r["meta"]["lang"] for r in rows)
    return {"n": len(rows), "path": str(f), "by_source_recipe_type": {"/".join(map(str, k)): v for k, v in sorted(c.items())},
            "langs": dict(langs)}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.write:
        print(json.dumps(write(force=a.force), indent=1))
