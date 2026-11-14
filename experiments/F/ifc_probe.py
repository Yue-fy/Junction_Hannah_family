"""Held-out IFC probe for W1 (S0 04:00): question/answer pairs on IFC models that have NO dataset questions for these
kinds, with gold computed INDEPENDENTLY of stoa/solvers/ifc (plain ifcopenshell: by_type counts, spatial containment,
space base quantities). Step 1 (this file, `validate`): check that the independent definitions reproduce the dataset's
own gold on TRAIN models; only definitions that agree >= 95% are used to generate probe questions (step 2, `--write`).

python experiments/F/ifc_probe.py validate          # agreement per question kind on train ifc_models
python experiments/F/ifc_probe.py write             # -> $JUNCTION_SHARED/artifacts/F/ifc_probe.jsonl (not sealed)
"""
from __future__ import annotations

import collections
import json
import os
import sys
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element as ue

from stoa.data import abspath, ifc_model_for, load_questions
from stoa.eval.hard import parse
from stoa.eval.splits import load_split

KIND = {"doors": ["IfcDoor"], "windows": ["IfcWindow"], "walls": ["IfcWall"], "columns": ["IfcColumn"],
        "beams": ["IfcBeam"], "stairs": ["IfcStair"], "rooms (spaces)": ["IfcSpace"],
        "sanitary fixtures": ["IfcSanitaryTerminal"], "light fixtures": ["IfcLightFixture"]}
_CACHE: dict[str, object] = {}


def model(path: str):
    if path not in _CACHE:
        _CACHE[path] = ifcopenshell.open(str(abspath(path)))
    return _CACHE[path]


def _types(m, classes):
    out = []
    for c in classes:
        try:
            out += m.by_type(c)
        except RuntimeError:  # class not in this schema
            pass
    return out


def model_count(m, kind: str) -> int:
    return len({e.id() for e in _types(m, KIND[kind])})


def storey_of(e):
    s = ue.get_container(e)
    while s is not None and not s.is_a("IfcBuildingStorey"):
        s = ue.get_aggregate(s) if s.is_a("IfcSpace") or s.is_a("IfcSpatialStructureElement") else None
    return s


def spaces_on(m, storey_name: str):
    out = []
    for sp in _types(m, ["IfcSpace"]):
        st = ue.get_aggregate(sp)
        while st is not None and not st.is_a("IfcBuildingStorey"):
            st = ue.get_aggregate(st)
        if st is not None and (st.Name or "") == storey_name:
            out.append(sp)
    return out


def storey_count(m, kind: str, storey_name: str) -> int:
    if kind == "rooms (spaces)":
        return len(spaces_on(m, storey_name))
    n = 0
    for e in _types(m, KIND[kind]):
        s = storey_of(e)
        if s is not None and (s.Name or "") == storey_name:
            n += 1
    return n


def space_area(sp) -> float | None:
    for pset, props in ue.get_psets(sp, qtos_only=True).items():
        for k in ("NetFloorArea", "GrossFloorArea"):
            if isinstance(props.get(k), (int, float)) and props[k] > 0:
                return float(props[k])
    return None


def storey_area(m, storey_name: str) -> float | None:
    a = [space_area(sp) for sp in spaces_on(m, storey_name)]
    return round(sum(x for x in a if x), 2) if a and any(a) else None


def independent(q) -> float | None:
    f = parse(q)
    if not f:
        return None
    mp = ifc_model_for(q.path) or q.path
    if not mp.endswith(".ifc"):
        return None
    m = model(mp)
    if f[0] == "ifc_model_count" and f[1] in KIND:
        return model_count(m, f[1])
    if f[0] == "ifc_plan_count" and f[1] in KIND:
        return storey_count(m, f[1], f[2])
    if f[0] == "ifc_storey_area":
        return storey_area(m, f[1])
    return None


def validate(split: str = "train") -> None:
    agree = collections.defaultdict(lambda: [0, 0, 0])
    for q in load_split(split):
        if q.source != "ifc_models":
            continue
        f = parse(q)
        if not f or f[0] not in ("ifc_model_count", "ifc_plan_count", "ifc_storey_area"):
            continue
        k = f"{f[0]}:{f[1] if f[0] != 'ifc_storey_area' else ''}"
        try:
            v = independent(q)
        except Exception as ex:  # noqa: BLE001
            v = None
            print("  error", k, type(ex).__name__, ex, file=sys.stderr)
        a = agree[k]
        a[0] += 1
        if v is None:
            a[2] += 1
        elif (abs(v - q.answer) <= 0.02 * abs(q.answer) + 1e-9) if f[0] == "ifc_storey_area" else int(v) == int(q.answer):
            a[1] += 1
    for k, (n, ok, none) in sorted(agree.items()):
        print(f"{k:42s} n={n:3d} agree={ok:3d} ({100 * ok / n:5.1f}%) none={none}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "validate"
    if cmd == "validate":
        validate(sys.argv[2] if len(sys.argv) > 2 else "train")


VALID = ["doors", "windows", "walls", "columns", "beams", "stairs", "rooms (spaces)"]  # 100% vs train gold


def candidates(n_resbim: int = 12) -> list[str]:
    """IFC models with no count questions, never in test: ifc_bench train/dev models, the RWTH models, a ResBIM sample."""
    import random
    from stoa.data import data_root, drawing_group
    from stoa.eval.splits import split_of_group
    root, sog = data_root(), split_of_group()
    asked = {(ifc_model_for(q.path) or q.path) for q in load_questions()
             if q.source == "ifc_models" and parse(q) and parse(q)[0] in ("ifc_model_count", "ifc_plan_count")}
    out = []
    for p in sorted((root / "data/ifc_bench").glob("*.ifc")) + sorted((root / "data/ifc_models").glob("*.ifc")):
        rel = str(p.relative_to(root))
        if rel in asked or sog.get(drawing_group(rel)) == "test":
            continue
        if p.name.startswith("resbim-"):
            continue
        out.append(rel)
    res = sorted(str(p.relative_to(root)) for p in (root / "data/ifc_models").glob("resbim-*_model.ifc"))
    res = [r for r in res if sog.get(drawing_group(r)) != "test"]
    out += random.Random(7).sample(res, min(n_resbim, len(res)))
    return out


def write(out_path: str | None = None, max_storeys: int = 3) -> None:
    import hashlib
    out_path = out_path or os.path.join(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"),
                                        "artifacts", "F", "ifc_probe.jsonl")
    rows = []
    for mp in candidates():
        try:
            m = model(mp)
        except Exception as ex:  # noqa: BLE001
            print("skip", mp, type(ex).__name__, file=sys.stderr)
            continue
        p = m.by_type("IfcProject")[0]
        name = (p.LongName or p.Name or Path(mp).stem).strip()
        for k in VALID:
            n = model_count(m, k)
            if n > 0:
                rows.append((mp, f"How many {k} are there in the model '{name}'?", n, "model"))
        storeys = [s.Name for s in m.by_type("IfcBuildingStorey") if s.Name]
        for st in [s for s in dict.fromkeys(storeys) if storeys.count(s) == 1][:max_storeys]:
            for k in ("doors", "windows", "walls", "rooms (spaces)"):
                n = storey_count(m, k, st)
                if n > 0:
                    rows.append((mp, f"How many {k} are shown on the floor plan of '{st}'?", n, "storey"))
        _CACHE.pop(mp, None)
    with open(out_path, "w", encoding="utf-8") as fh:
        for mp, qq, n, lvl in rows:
            fh.write(json.dumps({"qid": "ip" + hashlib.sha1(f"{mp}\n{qq}".encode()).hexdigest()[:10], "path": mp,
                                 "question": qq, "answer": n, "unit": "count", "type": "count",
                                 "meta": {"kind": "ifc-probe", "level": lvl}}, ensure_ascii=False) + "\n")
    c = collections.Counter((r[0].split("/")[1], r[3]) for r in rows)
    print(len(rows), "questions on", len({r[0] for r in rows}), "models;", dict(c), "->", out_path)


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "write":
    write()
