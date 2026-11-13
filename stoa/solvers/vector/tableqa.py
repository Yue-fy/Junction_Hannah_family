"""Table QA: an LLM writes a few lines of pandas over tables we extracted deterministically; we run the code.

Why: the hidden test asks harder, free-form questions. The geometry (areas, counts, which room holds which
fixture) is exact and cheap to extract; what varies is the *question*. So the model only translates the
question into a query over a small, documented table (no numbers come from the model), the code runs on
real data, and the rows it used become the evidence. Cost: one local text-only call (~2-4k tokens in);
a second call only if the first code raised (the error is fed back, as in IFC-Bench's iterative agent).

    tables = floor_tables(fm)             # rooms / objects / apartments DataFrames (+ dxf bboxes)
    res = ask(question, tables)           # {"value", "unit", "used": {"rooms": [ids]}, "code", "error"}
"""

from __future__ import annotations

import math
import re
import statistics

import pandas as pd
from shapely.geometry import Point
from shapely.geometry import box as sbox

from stoa.solvers.vector.floor import FloorModel

SAFE_BUILTINS = {k: __builtins__[k] if isinstance(__builtins__, dict) else getattr(__builtins__, k) for k in (
    "abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "len", "list", "max", "min", "range", "round",
    "set", "sorted", "str", "sum", "tuple", "zip", "isinstance", "print")}


def floor_tables(fm: FloorModel) -> dict[str, pd.DataFrame]:
    rooms = []
    for r in fm.rooms:
        rooms.append(dict(room_id=r.idx, number=r.number, name=r.name, area_m2=round(r.area, 2),
                          apartment=r.unit, outdoor=r.outdoor, printed_area_m2=r.printed_area,
                          n_doors=0, n_windows=0, n_toilets=0, n_washbasins=0, n_bathtubs=0, n_showers=0))
    by_id = {d["room_id"]: d for d in rooms}
    objects = []
    for kind, items in fm.items.items():
        for k, it in enumerate(items):
            b = sbox(*it.bbox)
            c = b.centroid
            if kind in ("door", "window"):  # in a wall: touches up to two rooms
                hit = [r for r in fm.rooms if r.poly.buffer(0.25).intersects(b)]
            else:
                hit = [r for r in fm.rooms if r.poly.contains(Point(c.x, c.y))] or \
                      [r for r in fm.rooms if r.poly.intersects(b)]
            for r in hit:
                by_id[r.idx][f"n_{kind}s"] += 1
            objects.append(dict(object_id=f"{kind}{k + 1}", kind=kind,
                                rooms=",".join(r.number or f"#{r.idx}" for r in hit),
                                apartment=next((r.unit for r in hit if r.unit), None)))
    apts = []
    for u in fm.units:
        rs = [r for r in fm.rooms if r.unit == u.label]
        apts.append(dict(apartment=u.label, n_rooms_numbered=sum(1 for r in rs if r.number),
                         net_area_m2=round(sum(r.area for r in rs if r.number and not r.outdoor), 2),
                         outdoor_area_m2=round(sum(r.area for r in rs if r.outdoor), 2)))
    return {"rooms": pd.DataFrame(rooms), "objects": pd.DataFrame(objects), "apartments": pd.DataFrame(apts)}


DOC = """Tables extracted from one floor plan (Swiss, DXF; areas in m²; labels in German/French/Italian):
rooms: one row per room polygon. room_id (int, key), number (str like "2.05" or None), name (room label, e.g.
  Zimmer/Schlafzimmer=bedroom, Bad/Bain/Bagno=bathroom, Küche/Cuisine/Cucina=kitchen, Korridor/Couloir=corridor,
  Wohnen/Essen/Séjour=living, Balkon/Balcon=balcony, Reduit=storage, Treppenhaus=stairs, or None), area_m2 (float,
  net floor area), apartment (letter like "A" or None), outdoor (bool), printed_area_m2 (area printed on the plan
  or None), n_doors, n_windows (doors/windows touching the room), n_toilets, n_washbasins, n_bathtubs, n_showers.
objects: object_id, kind (door|window|toilet|washbasin|bathtub|shower), rooms (comma-separated room numbers it
  touches), apartment.
apartments: apartment (letter), n_rooms_numbered, net_area_m2 (numbered indoor rooms), outdoor_area_m2.
Conventions: "net floor area" of an apartment/floor = numbered rooms, excluding outdoor ones. A door between two
rooms appears in both rooms' n_doors; count doors/windows in `objects`, not by summing n_doors."""

PROMPT = """{doc}

{data}

Question: {question}

Write Python (pandas available as pd; DataFrames `rooms`, `objects`, `apartments`) that computes the answer.
Set `answer` (a number, or a short string for which/what questions), `unit` ("count", "m2" or null) and `used` =
list of room_id values of the rooms the answer is based on (empty if none). No imports, no printing.
Reply with one ```python code block only."""


def _render(tables: dict[str, pd.DataFrame], max_rows: int = 160) -> str:
    out = []
    for name, df in tables.items():
        if df.empty:
            out.append(f"{name}: (empty)")
            continue
        out.append(f"{name} ({len(df)} rows):\n" + df.head(max_rows).to_csv(index=False))
    return "\n".join(out)


def _extract_code(text: str) -> str:
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


def _run(code: str, tables: dict[str, pd.DataFrame]) -> dict:
    if re.search(r"\b(import|open|exec|eval|__\w+__|os\.|sys\.|subprocess)\b", code):
        raise ValueError("code uses a forbidden construct")
    env = {"pd": pd, "math": math, "re": re, "statistics": statistics, "__builtins__": SAFE_BUILTINS}
    env.update({k: v.copy() for k, v in tables.items()})
    exec(compile(code, "<tableqa>", "exec"), env)  # noqa: S102 - restricted namespace, local data only
    if "answer" not in env:
        raise ValueError("code did not set `answer`")
    ans = env["answer"]
    if hasattr(ans, "item"):
        ans = ans.item()
    if isinstance(ans, (pd.Series, pd.DataFrame, list, tuple)) and not isinstance(ans, str):
        ans = ans.tolist() if hasattr(ans, "tolist") else list(ans)
        ans = ans[0] if len(ans) == 1 else ", ".join(map(str, ans))
    used = env.get("used", [])
    if hasattr(used, "tolist"):
        used = used.tolist()
    return {"value": ans, "unit": env.get("unit"), "used": [int(u) for u in list(used)[:200] if str(u).lstrip("-").isdigit()]}


def ask(question: str, tables: dict[str, pd.DataFrame], backend: str = "local", tries: int = 2) -> dict:
    from stoa.llm import chat

    msgs = [{"role": "user", "content": PROMPT.format(doc=DOC, data=_render(tables), question=question)}]
    last = {"value": None, "unit": None, "used": [], "code": "", "error": "no attempt"}
    for _ in range(tries):
        r = chat(msgs, backend=backend, max_tokens=500, temperature=0.0)
        code = _extract_code(r.text)
        try:
            res = _run(code, tables)
            res.update(code=code, error=None)
            return res
        except Exception as e:  # noqa: BLE001 - feed the error back once
            last = {"value": None, "unit": None, "used": [], "code": code, "error": f"{type(e).__name__}: {e}"}
            msgs += [{"role": "assistant", "content": r.text},
                     {"role": "user", "content": f"That code failed: {last['error']}. Fix it; reply with code only."}]
    return last
