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
                          apartment=r.unit, outdoor=r.outdoor, shaft=r.shaft, printed_area_m2=r.printed_area,
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
                         n_rooms_indoor=sum(1 for r in rs if r.number and not r.outdoor and not r.shaft),
                         net_area_m2=round(sum(r.area for r in rs if r.number and not r.outdoor), 2),
                         outdoor_area_m2=round(sum(r.area for r in rs if r.outdoor), 2)))
    net = [r for r in fm.rooms if r.number and not r.outdoor and not r.shaft]
    floor = [dict(net_area_m2=round(sum(r.area for r in net), 2), n_rooms_numbered_indoor=len(net),
                  n_apartments=len(fm.units), outdoor_area_m2=round(sum(r.area for r in fm.rooms if r.number and r.outdoor), 2))]
    rdf = pd.DataFrame(rooms)
    if not rdf.empty:
        rdf = rdf.set_index("room_id", drop=False)  # rooms.index == room_id, so `.index` is safe to report
        rdf.index.name = None
    return {"rooms": rdf, "objects": pd.DataFrame(objects), "apartments": pd.DataFrame(apts), "floor": pd.DataFrame(floor)}


DOC = """Tables extracted from one floor plan (Swiss, DXF; areas in m²; labels in German/French/Italian):
rooms: one row per room polygon. room_id (int, key), number (str like "2.05" or None), name (room label, e.g.
  Zimmer/Schlafzimmer=bedroom, Bad/Bain/Bagno=bathroom, Küche/Cuisine/Cucina=kitchen, Korridor/Couloir=corridor,
  Wohnen/Essen/Séjour=living, Balkon/Balcon=balcony, Reduit=storage, Treppenhaus=stairs, or None), area_m2 (float,
  net floor area), apartment (letter like "A" or None), outdoor (bool), shaft (bool: shaft/void), printed_area_m2 (area printed on the plan
  or None), n_doors, n_windows (doors/windows touching the room), n_toilets, n_washbasins, n_bathtubs, n_showers.
objects: object_id, kind (door|window|toilet|washbasin|bathtub|shower), rooms (comma-separated room numbers it
  touches), apartment.
apartments: apartment (letter), n_rooms_numbered (incl. balconies), n_rooms_indoor (what "how many rooms" means),
  net_area_m2 (numbered indoor rooms), outdoor_area_m2.
floor: one row: net_area_m2 (the floor's total net floor area), n_rooms_numbered_indoor, n_apartments, outdoor_area_m2.
Conventions: "net floor area" of an apartment = its numbered rooms, excluding outdoor ones (= apartments.net_area_m2);
of the floor = numbered rooms that are neither outdoor nor shafts (= floor.net_area_m2). A "room" is a row with a
number; rows without a number are wall gaps, ducts or voids (ignore them unless asked). Rooms "not in apartment X" =
floor total minus apartments.net_area_m2 of X. Answer "which apartment" with its letter. A door between two
rooms appears in both rooms' n_doors; count doors/windows in `objects`, not by summing n_doors."""

PROMPT = """{doc}

{data}

Question: {question}

Write Python (pandas available as pd; DataFrames {names}) that computes the answer.
Set `answer` (a number; a short string for which/what questions; True/False for yes/no questions), `unit`
({units} or None) and `used` = list of {id_col} values of the rows the answer is based on (empty if none).
For "which ..." questions `answer` is the identifier (apartment letter, room number or room name), not its area.
Compute everything from the DataFrames: never type a number or room_id from the data above into the code.
No imports, no printing. Reply with one ```python code block only."""


WHICH = re.compile(r"^\s*(which|welche[rs]?|quel(?:le)?s?\s+(?:appartement|pièce|logement)|lequel|laquelle|quale|"
                   r"in\s+which|welk[e]?|vilk(?:en|et)|cu[áa]l|kumpi|kt[óo]r[ey])\b", re.I)


def _render(tables: dict[str, pd.DataFrame], max_rows: int = 160, sep: str = ",") -> str:
    """sep="|": values are shown as printed, without CSV quote doubling (a 14"x6" cell is not shown doubled)."""
    import csv

    out = []
    for name, df in tables.items():
        if df.empty:
            out.append(f"{name}: (empty)")
            continue
        body = (df.head(max_rows).to_csv(index=False) if sep == "," else
                df.head(max_rows).to_csv(index=False, sep=sep, quoting=csv.QUOTE_NONE, escapechar="\\"))
        out.append(f"{name} ({len(df)} rows{', columns separated by ' + repr(sep) if sep != ',' else ''}):\n" + body)
    return "\n".join(out)


def _extract_code(text: str) -> str:
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.S)
    if m is None:  # an unclosed fence (reply cut at max_tokens): drop the opening fence line
        m = re.search(r"```(?:python)?[^\n]*\n(.*)", text, re.S)
    return (m.group(1) if m else text).strip()


HARDCODED = re.compile(r"^\s*answer\s*=\s*[-+*/().\d\s]+(?:#.*)?$", re.M)
TYPED_TEXT = re.compile(r"""^\s*answer\s*=\s*(?P<q>["'])(?P<v>(?:(?!(?P=q)).|\\.)*)(?P=q)\s*(?:#.*)?$""", re.M)


def _typed_cell(code: str, tables: dict[str, pd.DataFrame]) -> str | None:
    """`answer = "AL-1/GL-1"` where that string is a cell of a table: the model copied it from the rendered CSV
    (an 8B model often reads the neighbouring row). Returns the literal, or None."""
    m = TYPED_TEXT.search(code)
    if m is None:
        return None
    lit = m.group("v").replace('\\"', '"').replace("\\'", "'").strip()
    norm = re.sub(r"\s+", "", lit).upper()
    if not norm:
        return None
    for df in tables.values():
        for c in df.columns:
            if (df[c].dtype == object or pd.api.types.is_string_dtype(df[c])) and (df[c].astype(str).str.replace(r"\s+", "", regex=True).str.upper() == norm).any():
                return lit
    return None


def _run(code: str, tables: dict[str, pd.DataFrame]) -> dict:
    code = re.sub(r"(?<=[A-Za-z])'(?=S\b)", r"\\'", code)  # WOMEN'S inside '...' -> WOMEN\'S
    code = "\n".join(ln for ln in code.splitlines() if not re.match(r"\s*(import\s+(pandas|re|math|numpy)\b|from\s+\w+\s+import)", ln))
    if re.search(r"\b(import|open|exec|eval|__\w+__|os\.|sys\.|subprocess)\b", code):
        raise ValueError("code uses a forbidden construct")
    if HARDCODED.search(code):
        raise ValueError("`answer` is a typed-in number; compute it from the DataFrames (filter rows, then "
                         "len()/sum()) so the result is traceable to rows")
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


LITERAL_RE = re.compile(r"""(?:contains|startswith|endswith|==|match)\(?\s*r?(["'])(.{2,40}?)\1""")


def _where(code: str, tables: dict[str, pd.DataFrame]) -> str:
    """For an empty selection: where do the strings the code searched for actually occur? ("'Casement' is in
    t2.Family (4 rows)"), so the retry can pick the right column."""
    hints = []
    for _, lit in LITERAL_RE.findall(code)[:4]:
        words = [w for w in re.split(r"[^A-Za-z0-9]+", lit) if len(w) >= 3] or [lit]
        pat = "|".join(re.escape(w) for w in words[:3])
        found = []
        for name, df in tables.items():
            for c in df.columns:
                if df[c].dtype == object or pd.api.types.is_string_dtype(df[c]):
                    n = int(df[c].astype(str).str.contains(pat, case=False, regex=True, na=False).sum())
                    if n:
                        found.append(f"{name}[{c!r}] ({n} rows)")
        hints.append(f"{lit!r}: " + (", ".join(found[:4]) if found else "not found in any table"))
    return ("; where those words occur (case-insensitive): " + "; ".join(hints)) if hints else ""


def ask(question: str, tables: dict[str, pd.DataFrame], backend: str = "local", tries: int = 3, doc: str = DOC,
        id_col: str = "room_id", units: str = '"count", "m2"', lookup_text: bool = False, sep: str = ",") -> dict:
    """lookup_text: a typed-in string that is a table cell is sent back once ("look it up"); if the lookup fails,
    the typed answer is kept (res["typed"] = True)."""
    from stoa.llm import chat

    names = ", ".join(f"`{k}`" for k in tables)
    msgs = [{"role": "user", "content": PROMPT.format(doc=doc, data=_render(tables, sep=sep), question=question, names=names,
                                                      id_col=id_col, units=units)}]
    last = {"value": None, "unit": None, "used": [], "code": "", "error": "no attempt"}
    typed = None  # the first typed-in cell answer, kept as the fallback
    for attempt in range(tries):
        r = chat(msgs, backend=backend, max_tokens=700, temperature=0.0)
        code = _extract_code(r.text)
        try:
            res = _run(code, tables)
            lit = _typed_cell(code, tables) if lookup_text and typed is None and attempt < tries - 1 else None
            if lit is not None and res["value"] == lit:
                typed = dict(res, code=code, error=None, typed=True)
                raise ValueError(f"`answer` is the typed-in string {lit!r}; look the cell up in the DataFrame instead "
                                 "(e.g. df.loc[df[\"<id column>\"] == \"<id>\", \"<column>\"].iloc[0]) so it comes "
                                 "from the right row, and set `used` to that row's id")
            v = res["value"]
            if isinstance(v, float) and v != v:
                raise ValueError("the query returned NaN (an empty selection or a non-numeric column); check the "
                                 "filter against the cell values shown above")
            if v is None or (isinstance(v, str) and not v.strip()) or (v == 0 and not res["used"] and attempt < tries - 1):
                raise ValueError(f"the query returned {v!r} (no matching rows). Look at the actual cell values and "
                                 "column contents shown above (headers may be misaligned) and fix the filter"
                                 + _where(code, tables))
            if WHICH.search(question) and not isinstance(res["value"], str):
                raise ValueError(f"the question asks WHICH one, but answer = {res['value']!r}; set answer to the "
                                 "identifier string (apartment letter / room number / name)")
            res.update(code=code, error=None)
            return res
        except Exception as e:  # noqa: BLE001 - feed the error back once
            last = {"value": None, "unit": None, "used": [], "code": code, "error": f"{type(e).__name__}: {e}"}
            msgs += [{"role": "assistant", "content": r.text},
                     {"role": "user", "content": f"That code failed: {last['error']}. Fix it; reply with short code only "
                                                     "(no comments, no helper functions)."}]
    return typed if typed is not None else last
