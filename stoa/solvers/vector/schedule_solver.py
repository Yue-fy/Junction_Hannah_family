"""`schedule` solver: questions about schedule tables on vector PDF sheets (opening_design door/window/finish
schedules), answered by table QA over tables rebuilt from the PDF text layer.

  PDF words --pdftables--> tables (DataFrames, one box per row) + the sheet's other text lines
  question + tables --tableqa.ask (local LLM writes pandas, we run it)--> value + row_ids used
  evidence = the boxes of the rows used (pdf_pt, PyMuPDF word space = unrotated page space).
The model never supplies numbers: counts and sums come from running its code on the extracted rows.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from stoa.contract import Answer, Evidence
from stoa.data import abspath, siblings, source_of
from stoa.solvers import register
from stoa.solvers.base import BaseSolver
from stoa.solvers.vector import tableqa
from stoa.solvers.vector.pdftables import pdf_tables
from stoa.solvers.vector import sheettext
from stoa.solvers.vector.pdftext import SCALE_RE, text_groups

TEXT_ID = 800000  # row ids of the `text` table (text groups: tags, note paragraphs, title-block fields)
TEXT_DOC = ("- `text`: text groups of the sheet outside the tables, {n} rows, columns ['row_id', 'view', 'text']: "
            "a room/unit TAG is one row with its stacked lines joined by ' / ' (e.g. 'COMMUNITY / ROOM / 115 - 410 SF / "
            "A-2 Occupancy / 27.3 O.L.'), a note paragraph or title-block field is one row; `view` = the title of the "
            "drawing (plan/section) the group sits under, e.g. 'LIFE SAFETY PLAN - BASEMENT' (None = title block or "
            "unknown). Use it for questions about plans, tags, notes and the title block (use `.str.contains(..., "
            "regex=False)` or `.str.extract` on `text`; one tag row = one room/unit).")

DOC = """Tables rebuilt from the text layer of one construction drawing sheet (US units; values are strings exactly
as printed, e.g. "108 SF", "3' - 0\\"", "A1"; empty string = blank cell; multi-line headers are joined; a header
may be wrong or "colN", so look at the values). Each table has a `row_id` column (unique across tables).
Count/quantity/area columns are numbers; for values like "108 SF" or "110 CFM" a parsed twin column `<col>_num`
exists (NaN where blank); all
other columns (ids, room numbers, types) are strings: compare them with strings ("118", not 118).
Use double quotes for strings that contain an apostrophe ("WOMEN'S LOCKER").
Counting rows: one row = one item unless a Count/Qty column says otherwise (then sum that column over the rows).
Printed subtotal/total rows ("BASEMENT: 8 | 1091 SF", "Grand total: 39") are not table rows; they are in `notes`.
A cell may hold several codes ("A, B"): match a code as a whole token, not inside "A-620" or "AL-1", e.g.
df["Notes"].str.contains(r"(?<![\\w-])A(?![\\w-])").
Dimensions are strings as printed (3' - 0"): never convert them to numbers; for "width and height" answer
f"{{w}} wide x {{h}} high" with the printed strings.
Text answers: give the value as printed; if the question also asks what a code means, find the code in `notes`
(e.g. notes[notes.text.str.contains("F4")]) and answer "F4 - <meaning>"; if it asks for two things (how many
and what total), answer one string with both ("3 rooms, 4541 SF"); include those notes rows in `used`.
{tables}"""


NUM_RE = re.compile(r"^-?\d[\d,]*(?:\.\d+)?$")
QTY_RE = re.compile(r"^(-?\d[\d,]*(?:\.\d+)?)\s*(SF|S\.F\.|sq\.?\s*ft|ft²|ft2|m²|m2|LF|EA)\.?$", re.I)
ANY_QTY_RE = re.compile(r"^(-?\d[\d,]*(?:\.\d+)?)\s+([A-Za-z][A-Za-z/]{0,5})\.?$")
UNIT_MAP = {"sf": "ft2", "sqft": "ft2", "sq ft": "ft2", "ft²": "ft2", "ft2": "ft2", "m²": "m2", "m2": "m2",
            "count": "count", "ft": "ft", "m": "m"}


def _typed(df: pd.DataFrame) -> pd.DataFrame:
    """Numeric-looking columns -> numbers; "108 SF"-style columns get a parsed `<col>_num` twin."""
    df = df.copy()
    for c in list(df.columns):
        vals = [v.strip() for v in df[c].astype(str) if v.strip()]
        if not vals:
            continue
        quantity = re.search(r"count|qty|quant|area|total|sum|amount|sf\b", str(c), re.I)
        if quantity and sum(bool(NUM_RE.match(v)) for v in vals) >= 0.8 * len(vals):
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
        elif sum(bool(QTY_RE.match(v)) for v in vals) >= 0.6 * len(vals):
            df[f"{c}_num"] = pd.to_numeric(df[c].astype(str).str.extract(QTY_RE.pattern.strip("^$"), flags=re.I)[0]
                                           .str.replace(",", ""), errors="coerce")
        else:  # "110 CFM", "1.5 KW", "40 GPM": one consistent unit word -> parsed twin
            m = [ANY_QTY_RE.match(v) for v in vals]
            units = {x.group(2).upper() for x in m if x}
            if sum(bool(x) for x in m) >= 0.6 * len(vals) and len(units) == 1:
                df[f"{c}_num"] = pd.to_numeric(df[c].astype(str).str.extract(ANY_QTY_RE.pattern.strip("^$"))[0]
                                               .str.replace(",", ""), errors="coerce")
    return df


NOT_FOUND_RE = re.compile(r"^\s*(unknown|not found|not (?:listed|specified|available|shown|given)|n/?a|none|no data|"
                          r"no (?:such|matching) \w+|cannot (?:be )?determined?)\s*\.?\s*$", re.I)
# a short answer that is a refusal in other words ("Size not found in note", "No path distances found")
REFUSAL_IN_RE = re.compile(r"\b(not (?:found|listed|specified|available|shown|given|mentioned)|no \w+(?: \w+)? found|"
                           r"cannot be determined|unknown)\b", re.I)
CODE = r"(?:[A-Z]{1,3}-?\d{1,2}[A-Z]?|[A-Z]{2,3})"
CODE_RE = re.compile(rf"^{CODE}$")
CODES_ANSWER = re.compile(rf"^\s*{CODE}(?:\s*(?:&|,|/|\band\b)\s*{CODE})*\s*$")
TOPICS = ("floor", "ceiling", "wall", "base", "door", "frame", "glaz", "glass", "window", "hardware", "partition",
          "roof", "finish", "material")


def _legend(rows) -> dict[str, list[tuple[str, tuple, int]]]:
    """Legend lines of the sheet: a row that STARTS with a code cell ("F4") followed by its meaning
    ("RESILIENT FLOORING (T.B.D.)"). Only the cell right after the code is the meaning (rows may merge columns)."""
    out: dict[str, list] = {}
    for k, r in enumerate(rows):
        cells = r.cells
        if len(cells) < 2:
            continue
        lead = 0 if CODE_RE.match(cells[0].text.strip()) else (
            1 if len(cells) > 2 and not re.search(r"[A-Za-z]{2}", cells[0].text) and CODE_RE.match(cells[1].text.strip()) else None)
        if lead is None:
            continue
        code, meaning = cells[lead].text.strip(), cells[lead + 1].text.strip()
        if CODE_RE.match(meaning) or len(re.findall(r"[A-Za-z]{3,}", meaning)) < 1 or re.match(r"(?i)see\b", meaning):
            continue
        box = tuple(min(c.box[i] for c in cells[lead:lead + 2]) if i < 2 else max(c.box[i] for c in cells[lead:lead + 2])
                    for i in range(4))
        out.setdefault(code, []).append((meaning, box, k))
    return out


def _explain_codes(value: str, question: str, rows, legend) -> tuple[str, list[tuple[str, str, tuple]]] | None:
    """'F2 & F3' -> 'F2 (ARTIFICIAL TURF) & F3 (RESILIENT ...)' from the sheet's own legend; None if nothing found."""
    if not CODES_ANSWER.match(value):
        return None
    topics = [t for t in TOPICS if t in question.lower()]
    found = []
    for code in re.findall(CODE, value):
        cands = legend.get(code)
        if not cands:
            continue

        def score(c):
            window = " ".join(cell.text for r in rows[max(0, c[2] - 15):c[2] + 1] for cell in r.cells).lower()
            return sum(t in window for t in topics)
        best = max(cands, key=score)
        if topics and score(best) == 0:
            continue  # e.g. a door type "B2" must not be explained by the base legend's "B2 = CERAMIC TILE"
        meaning, box, _ = best
        found.append((code, meaning, box))
    if not found:
        return None
    if len(found) == 1 and len(re.findall(CODE, value)) == 1:
        return f"{found[0][0]} - {found[0][1]}", found
    out = value
    for code, meaning, _ in found:
        out = re.sub(rf"(?<![\w-]){re.escape(code)}(?![\w-])", f"{code} ({meaning})", out, count=1)
    return out, found


# count nouns that name no thing ("how many items in total"): never evidence that the table is missing
GENERIC_RE = re.compile(r"(items?|things?|objects?|elements?|units?|pieces?|total|numbers?|instances?|occurrences?|"
                        r"times|each|every|overall|altogether)", re.I)
KINDS_RE = re.compile(r"\b(types?|kinds?|marks?|different|distinct|unique|rows?|entries|lines?|records?|styles?|"
                      r"models?|categories|variants?)\b", re.I)


def _qty_sum(value: int, used: list, tables: dict[str, pd.DataFrame], question: str) -> int | None:
    """The model counted rows (len) of a table that has a Count/Qty column: answer the summed quantity instead,
    unless the question counts kinds ("how many door TYPES ..."). None = keep the value."""
    used = [int(u) for u in used if isinstance(u, (int, float)) and int(u) < 900000]
    if not used or value != len(set(used)):
        return None
    question = re.sub(r"\([^)]*\)", " ", question)  # "(types SS, TT and UU)" filters, it is not the counted noun
    m = re.search(r"how many\s+(.*?)(?:\b(?:are|is|does|do|have|has|carry|carries|appear|in|on|at|of|with|that|which|"
                  r"whose|for|from|within|scheduled|listed|shown|use|uses|need|needs|require|get|belong)\b|[?,]|$)", question, re.I)
    if m is None or KINDS_RE.search(m.group(1)):
        return None
    total = 0.0
    for u in set(used):
        hit = None
        for name, df in tables.items():
            if name == "notes" or df.empty:
                continue
            r = df[df["row_id"] == u]
            if len(r):
                hit = (df, r.iloc[0])
                break
        if hit is None:
            return None
        df, row = hit
        qty = next((c for c in df.columns if re.search(r"^(count|qty|quantity|quan\.?|no\.?|number of units)$",
                                                          str(c).strip(), re.I)
                    and pd.api.types.is_numeric_dtype(df[c])), None)
        if qty is None or pd.isna(row[qty]):
            return None
        total += float(row[qty])
    total = int(round(total))
    return total if total != value else None


MULT_Q = re.compile(r"\b(?:N|\d+)[- ]?(wide|panel|leaf|gang|bay|lite|light|unit)s?\b[^?]*?\b(?:consists?|contains?|"
                    r"comprises?|is made|are made|has|have|equals?|=|holds?|means?|counts? as)\b[^?]*?\b(?:N|\d+)\b", re.I)


def _assembly_total(question: str, tables: dict[str, pd.DataFrame], path: str = "") -> tuple[int, list[int], str] | None:
    """'if every N-wide window assembly consists of N ESDH3066 window units, how many units ...': each row's own
    '<k>-WIDE' times its Count/Qty, summed over the rows naming the question's item ids. Deterministic, because the
    LLM-written code dropped the multiplier in 1 of 3 runs under load (S0 09:36, D22: 235 @0.85 vs gold 379).
    Returns (total, row ids, formula) or None when the question has no per-row multiplier or no such column."""
    m = MULT_Q.search(question)
    if not m:
        return None
    word = m.group(1).lower()
    cell_re = re.compile(rf"\b(\d+)\s*-?\s*{word}s?\b", re.I)
    ids = tableqa.id_tokens(question, path)
    for name, df in tables.items():
        if name in ("notes", "text") or df.empty:
            continue
        qty = next((c for c in df.columns if re.search(r"^(count|qty|quantity|quan\.?|no\.?|number of units)$",
                                                          str(c).strip(), re.I) and pd.api.types.is_numeric_dtype(df[c])),
                   None)
        if qty is None:
            continue
        cols = [c for c in df.columns if c not in ("row_id", qty)]
        rows = []
        for _, r in df.iterrows():
            cells = " | ".join(str(r[c]) for c in cols)
            km = cell_re.search(cells)
            if km is None or pd.isna(r[qty]):
                continue
            up = cells.upper()
            if ids and not all(i in up for i in ids):
                continue
            rows.append((int(r["row_id"]), int(km.group(1)), float(r[qty])))
        if len(rows) >= 2:
            total = int(round(sum(k * q for _, k, q in rows)))
            formula = " + ".join(f"{k}x{q:g}" for _, k, q in rows)
            return total, [i for i, _, _ in rows], f"{formula} = {total}"
    return None


SECOND_LOOK = ("\n(The tables are already loaded as pandas DataFrames under these names, with typed numeric columns; "
               "use them directly.)")
COMPLEX_Q = re.compile(r"\bif\b|\beach\b|\bevery\b|\bper\b|consist|assum|\btimes\b|multipl|\bratio\b|percent|"
                       r"average|\bmean\b|\btotal\b|\bsum\b|\ball\b|\bwhose\b|\bstarts?\s+with|\bboth\b", re.I)


def _complex(question: str, res: dict) -> bool:
    """A multi-step question or query (where a second sample of the LLM-written code can disagree)."""
    stm = [ln for ln in (res.get("code") or "").splitlines() if ln.strip() and not ln.strip().startswith("#")]
    return len(stm) >= 4 or bool(COMPLEX_Q.search(question))


def _clean(name: str) -> str:
    return re.sub(r"\W+", "_", name).strip("_").lower()[:30] or "table"


@register("schedule")
class ScheduleSolver(BaseSolver):
    """Options: backend=local|nvidia, text=1 (0: no `text` table of tags/notes/title block)."""

    extensions = (".pdf",)

    def __init__(self, backend: str = "local", text: int | str = 1, **kwargs):
        super().__init__(**kwargs)
        self.backend = backend
        self.use_text = str(text) not in ("0", "false", "no")

    def can_handle(self, path: str, question: str) -> bool:
        if Path(path).suffix.lower() != ".pdf" or source_of(path) in ("swiss_dwellings", "ifc_models"):
            return False
        return True

    def solve(self, path: str, question: str) -> Answer:
        a = self._solve_tables(path, question)
        if not self.use_text or (a.value is not None and a.confidence >= 0.5) or \
                (a.trace and str(a.trace[0]).startswith("sheet text:")):
            return a
        # a schedule sheet whose tables gave no confident answer: the question may be about the plan / notes / title
        # block printed next to the schedule (held-out A000: drawing index + site plan). One more read, of the text
        # groups and the table rows together; kept only if it cites printed rows and is surer.
        pdf = str(abspath(path))
        tabs, _ = pdf_tables(pdf)
        groups = [g for g in text_groups(pdf) if g.n_lines >= 2 or g.kind == "list" or
                  (len(g.text) >= 12 and re.search(r"[A-Za-z]{3}", g.text))]
        if not groups:
            return a
        b = self._sheet_text(path, question, [t for t in tabs if len(t.df.columns) >= 3], groups)
        if b.value is not None and b.evidence and b.confidence > a.confidence:
            b.trace = list(a.trace) + [f"the schedule tables gave no confident answer ({a.value!r}, conf "
                                       f"{a.confidence:.2f}); read the sheet's printed text groups instead"] + list(b.trace)
            return b
        return a

    def _solve_tables(self, path: str, question: str) -> Answer:
        pdf = str(abspath(path))
        tabs, rows = pdf_tables(pdf)
        # a sheet without a real schedule (a plan, life-safety or notes sheet): its page-wide "rows" glue unrelated tags
        # and note columns together, so the model gets the text groups instead (tags, paragraphs, two-column lists;
        # plus any table of >= 3 columns). Schedule sheets keep exactly the old prompt: adding the text table there
        # changed the code the model wrote (dev A-801 'rooms listed' 29 -> 27).
        def _named(t):  # a real schedule has a title or mostly named columns (not a plan's dimension chains)
            names = [c for c in t.df.columns if not re.fullmatch(r"col\d+", str(c)) and re.search(r"[A-Za-z]{2}", str(c))]
            return bool(t.title) or len(names) >= 0.5 * len(t.df.columns)
        schedule_sheet = any(len(t.df) >= 4 and len(t.df.columns) >= 3 and _named(t) for t in tabs)
        groups = [g for g in text_groups(pdf) if g.n_lines >= 2 or g.kind == "list" or
                  (len(g.text) >= 12 and re.search(r"[A-Za-z]{3}", g.text))] \
            if self.use_text and not schedule_sheet else []
        if groups:
            return self._sheet_text(path, question, [t for t in tabs if len(t.df.columns) >= 3], groups)
        if not tabs and not groups:
            return self.abstain("no tables or text found in the PDF text layer")
        tables: dict[str, pd.DataFrame] = {}
        boxes: dict[int, tuple] = {}
        desc = []
        rid = 0
        for k, t in enumerate(tabs):
            name = f"t{k + 1}_{_clean(t.title)}" if t.title else f"t{k + 1}"
            df = _typed(t.df)
            ids = list(range(rid, rid + len(df)))
            df.insert(0, "row_id", ids)
            df.index = pd.Index(ids)  # `.index` == row_id, so code that reports `.index.tolist()` cites the right rows
            for i, b in zip(ids, t.row_boxes):
                boxes[i] = b
            rid += len(df) + 1000 - (len(df) % 1000)  # table k's row ids start at a multiple of 1000
            tables[name] = df
            desc.append(f"- `{name}`: {t.title or 'untitled'}, {len(df)} rows, columns {list(df.columns)}")
        # sheet text outside the tables (legends/notes), capped
        # legends and notes are short rows (long rows are table rows): a `notes` table, so the code can look up
        # what a code means ("F4") and the lines it used become evidence too
        notes, nid = [], 900000
        for k, t in enumerate(tabs):  # printed subtotal/total rows taken out of the tables: a cross-check
            for txt, box in t.totals:
                name = f"t{k + 1}_{_clean(t.title)}" if t.title else f"t{k + 1}"
                notes.append({"row_id": nid, "text": f"{name} printed total row: {txt}"})
                boxes[nid] = box
                nid += 1
        for r in rows:
            if len(r.cells) <= 3:
                txt = " | ".join(c.text for c in r.cells)[:160]
                if len(txt) > 2:
                    notes.append({"row_id": nid, "text": txt})
                    boxes[nid] = tuple(min(c.box[k] for c in r.cells) if k < 2 else max(c.box[k] for c in r.cells)
                                       for k in range(4))
                    nid += 1
        if notes or not groups:
            tables["notes"] = pd.DataFrame(notes[:300], columns=["row_id", "text"])
            tables["notes"].index = pd.Index([n["row_id"] for n in notes[:300]])
            desc.append(f"- `notes`: other text lines of the sheet (legends, keys, general notes), {len(notes[:300])} "
                        "rows, columns ['row_id', 'text']")
        if groups:
            # plans / notes sheets: text that is not a table (tags, paragraphs, title block), one row per group;
            # multi-line groups (tags, paragraphs) first, as only the first 160 rows are shown to the model
            groups.sort(key=lambda g: g.n_lines < 2)
            trows = []
            for k, g in enumerate(groups[:400]):
                trows.append({"row_id": TEXT_ID + k, "view": g.view, "text": g.text[:300]})
                boxes[TEXT_ID + k] = g.box
            tables["text"] = pd.DataFrame(trows)
            tables["text"].index = pd.Index([r["row_id"] for r in trows])
            desc.append(TEXT_DOC.format(n=len(trows)))
        doc = DOC.format(tables="\n".join(desc))
        if "notes" not in tables:  # plan / notes sheet: legends and notes are text groups
            doc = doc.replace("`notes`", "`text`").replace("notes[notes.text", "text[text.text")
        trace = [f"{len(tabs)} tables from the PDF text layer: " + "; ".join(
            f"{n} ({len(df)}x{len(df.columns) - 1})" for n, df in tables.items())]
        try:
            res = tableqa.ask(question, tables, backend=self.backend, doc=doc, id_col="row_id",
                              units='"count", "ft2", "m2", "ft", "m"', lookup_text=True, sep="|")
        except Exception as e:  # noqa: BLE001
            return Answer.abstain(self.name, f"table QA failed: {type(e).__name__}: {e}", trace)
        trace.append("table QA code: " + " ; ".join(ln.strip() for ln in (res.get("code") or "").splitlines()
                                                   if ln.strip())[:700])
        if res.get("typed"):
            trace.append("the model typed the answer from the table text; asked to look it up, the lookup failed, "
                         "so the typed value is kept")
        if res.get("value") is None or (isinstance(res["value"], float) and res["value"] != res["value"]):
            return Answer.abstain(self.name, f"table QA gave no answer ({res.get('error') or 'NaN'})", trace)
        if isinstance(res["value"], str) and (NOT_FOUND_RE.match(res["value"]) or
                                              (len(res["value"]) < 60 and REFUSAL_IN_RE.search(res["value"]))):
            # "Unknown" / "Not found" is a refusal dressed as a value: say so, so the cascade can try another reader
            return Answer.abstain(self.name, f"the rows the question needs were not found in the tables rebuilt from "
                                             f"the PDF text (table QA said {res['value']!r})", trace)
        value, unit = res["value"], res.get("unit")
        unit = UNIT_MAP.get(str(unit).lower().replace(".", "").strip(), unit) if unit else unit
        if isinstance(value, bool):
            value, unit = ("yes" if value else "no"), None
        if isinstance(value, str):
            unit = None
            value = re.sub(r"(\d+')\s*-\s*(\d)", r"\1-\2", value).strip()  # 5' - 10 3/8" -> 5'-10 3/8"
        elif unit == "count" and abs(float(value) - round(float(value))) >= 0.05:
            unit = None  # "27.3 O.L." is a number, not a count: keep it as printed
            value = round(float(value), 2)
        elif unit == "count":
            value = int(round(float(value)))
        elif isinstance(value, float):
            value = round(value, 2)
        if isinstance(value, float) and unit in ("ft", None) and value == int(value):
            # "11' - 3 1/8\"" read as 11.0: a length printed in feet-inches is answered as printed (A200 held-out)
            used_txt = " ".join(str(v) for df in tables.values() if "row_id" in df.columns
                                for v in df[df["row_id"].isin(res.get("used", []))].drop(columns="row_id").to_numpy().ravel())
            dims = re.findall(r"-?\d+' ?- ?\d+(?: \d+/\d+)?\"", used_txt)
            hit = [d for d in dict.fromkeys(dims)
                   if re.match(rf"-?{int(value)}'", d) and not re.search(r"- ?0\"$", d)]
            via_inch = [d for d in dict.fromkeys(dims) if re.search(rf"- ?{int(value)}(?: \d+/\d+)?\"$", d)]
            if len(hit) == 1 or (not hit and len(via_inch) == 1):
                d = (hit or via_inch)[0]
                trace.append(f"the query returned {value:g}, a part of the printed {d}; answered as printed")
                value, unit = d.replace("' - ", "'-"), None
        if unit not in ("count", "ft2", "m2", "ft", "m", None):
            unit = None
        if isinstance(value, (int, float)) and not isinstance(value, bool) and unit in ("ft", None) and \
                not COMPLEX_Q.search(question) and not re.search(r"how many|number of|count", question, re.I):
            # a plain lookup whose number is not printed in its cited rows but sits within a foot of a printed
            # feet-inch dimension there: the code converted/shifted it (Q/W4 v21: "22' - 5\"" -> 21.92 = 22.42 - 0.5
            # in some runs); answer the printed dimension
            texts = []
            for u in res.get("used", []):
                for df in tables.values():
                    hit = df[df["row_id"] == u] if "row_id" in df.columns else df.iloc[0:0]
                    if len(hit):
                        texts.append(" | ".join(str(v) for k, v in hit.iloc[0].items() if k != "row_id"))
                        break
            dims = {re.sub(r"(\d+')\s*-\s*(\d)", r"\1-\2", m.group(0).strip()): sheettext._ftin(m.group(0))
                    for t in texts for m in sheettext.DIM_IN_ROW.finditer(t)}
            dims = {d: v for d, v in dims.items() if v is not None}
            if dims and all(abs(v - float(value)) > 0.005 for v in dims.values()):
                near = sorted((abs(v - float(value)), d) for d, v in dims.items() if abs(v - float(value)) < 1.0)
                if len(near) == 1 or (len(near) > 1 and near[0][0] < near[1][0] - 0.1):
                    trace.append(f"lookup check: {value} is not printed in the cited rows; the printed dimension "
                                 f"{near[0][1]!r} is -> answered it")
                    value, unit = near[0][1], None
        row_label = {}
        if "text" in tables:
            for _, row in tables["text"].iterrows():
                row_label[int(row["row_id"])] = f"text: {row['text'][:80]}" + (f" (view {row['view']})" if row["view"] else "")
        for name, df in tables.items():
            if name in ("notes", "text") or df.empty:
                continue
            qty = next((c for c in df.columns if re.search(r"^(count|qty|quantity|no\.?)$", str(c).strip(), re.I)), None)
            key = df.columns[1] if len(df.columns) > 1 else None
            for _, row in df.iterrows():
                lab = f"{name} row: {row[key]}" if key is not None else f"{name} row"
                if qty is not None and pd.notna(row[qty]):
                    lab += f" (qty {row[qty]:g})" if isinstance(row[qty], (int, float)) else f" (qty {row[qty]})"
                row_label[int(row["row_id"])] = lab
        evidence = [Evidence(file=path, page=0, bbox=[round(v, 1) for v in boxes[i]], bbox_space="pdf_pt",
                             note=(f"note line {i - 900000}" if i >= 900000 else row_label.get(i, f"table row {i}")))
                    for i in res.get("used", []) if i in boxes]
        n_rows_used = len(evidence)
        if unit == "count" and isinstance(value, int):
            fixed = _qty_sum(value, res.get("used", []), tables, question)
            if fixed is not None:
                trace.append(f"count check: the code counted {value} rows, but their quantity column sums to {fixed}; "
                             "answered the quantity")
                value = fixed
        if isinstance(value, str):
            # a bare code answer ("F4") gets its meaning from the sheet's own legend: "F4 - RESILIENT FLOORING"
            ex = _explain_codes(value, question, rows, _legend(rows))
            if ex is not None:
                value, found = ex
                trace.append("legend: " + "; ".join(f"{c} = {m}" for c, m, _ in found))
                evidence += [Evidence(file=path, page=0, bbox=[round(v, 1) for v in b], bbox_space="pdf_pt",
                                      note=f"legend: {c} = {m}") for c, m, b in found]
        # dev opening_design (v10, tuned on it): 100% of answers that cite rows right; self-written probes on 3 unlabelled
        # sheets: ~85-90% (the first look at a new sheet 8/11). Typed-in answers whose lookup failed are less sure.
        conf = (0.7 if res.get("typed") else 0.85) if n_rows_used else 0.5
        missing = [] if n_rows_used else ["the query did not report which rows it used"]
        about_table = re.search(r"schedul|listed|table|legend|\bkey\b|specified|finish", question, re.I)
        about_drawing = re.search(r"\b(drawn|shown|depicted|visible)\b|\bin\s+(?:the\s+)?(?:enlarged\s+)?plan\b",
                                  question, re.I)
        used_text = [i for i in res.get("used", []) if TEXT_ID <= i < 900000 and i in boxes]
        assumptions = ["tables rebuilt from the PDF text layer (row/column alignment); the model wrote "
                       "the query, the numbers come from the extracted rows"]
        if used_text and len(used_text) == n_rows_used:
            # the answer comes from text groups (tags, notes, title block), not schedule rows: grouping stacked lines
            # into tags is a heuristic (a tag can merge with a neighbour or be split), so less sure than a schedule
            # row; aggregates over many tags more so. Fresh probe (experiments/w2/sheet_probe), not calibrated yet.
            conf = min(conf, 0.75 if len(used_text) == 1 else 0.6)
            assumptions = [f"read from {len(used_text)} printed text group(s) of the sheet (room/unit tags, notes, "
                           "title block); stacked lines within ~0.6 line heights were grouped into one tag"]
        if about_drawing and not about_table:
            if used_text and len(used_text) == n_rows_used and unit == "count":
                conf = min(conf, 0.5)
                missing.append("counted the printed tags; rooms/elements drawn without a tag are not counted")
            elif not used_text:
                conf = min(conf, 0.15)
                missing.append("the question is about symbols drawn on a plan; schedules and text can't count those "
                               "(needs symbol detection on the drawing)")
        if value == 0 and not evidence:
            conf = min(conf, 0.2)
        elif value == 0 and unit == "count":
            conf = min(conf, 0.35)  # "none" from a rebuilt table is weak evidence (a misread column also gives 0)
            missing.append("the count is 0: no row matched, which can also mean the column was misread")
        if n_rows_used and tableqa._rows_mention_ids(question, res.get("used", []), tables, "row_id", path) is False:
            conf = min(conf, 0.3)  # the question names an id (P13, 115.A) that none of the cited rows contains
            missing.append("none of the rows the answer used contains the identifier named in the question")
        named = [w for w in re.findall(r"(\w+)\s+schedules?\b", question.lower()) if w not in ("the", "a", "this")]
        known = " ".join([t.title for t in tabs] + [str(c) for df in tables.values() for c in df.columns] +
                         [str(v) for n, df in tables.items() if n != "notes" for v in (df if n == "text" else df.head(60)).to_numpy().ravel()]).lower()
        hm = re.search(r"how many\s+(.*?)(?:\b(?:are|is|does|do|have|has|use|uses|in|on|of|with|that|which)\b|[?,(]|$)",
                       question, re.I)
        counted = [w for w in re.findall(r"[a-z]{4,}", hm.group(1).lower())
                   if not KINDS_RE.fullmatch(w) and not GENERIC_RE.fullmatch(w)] if hm else []
        if named and not any(w.rstrip("s") in known for w in named):
            conf = min(conf, 0.3)  # e.g. "pier schedule" but no pier table was rebuilt from this sheet
            missing.append(f"no '{named[0]} schedule' table could be rebuilt from the PDF text (it may be drawn among "
                           "detail drawings); the answer comes from other text")
        elif counted and not any(w.rstrip("s")[:5] in known for w in counted):
            conf = min(conf, 0.3)  # "how many pier types": no rebuilt table mentions piers
            missing.append(f"no rebuilt table mentions '{' '.join(counted)}'; the answer comes from other text")
        det = _assembly_total(question, tables, path) if unit == "count" or isinstance(value, (int, float)) else None
        if det is None and isinstance(value, (int, float)) and not isinstance(value, bool) and conf > 0.5 and \
                _complex(question, res):
            # S0 04:57: the same dev question gave 379 and 235 at conf 0.85 in two runs (LLM-written code is not
            # deterministic on the server). For multi-step questions/code, draw a second independent query; on
            # disagreement the answer is not sure. Simple lookups (75% of dev) were stable: no second call there.
            try:
                res2 = tableqa.ask(question, tables, backend=self.backend, doc=doc + SECOND_LOOK, id_col="row_id",
                                   units='"count", "ft2", "m2", "ft", "m"', lookup_text=True, sep="|")
                v2 = res2.get("value")
            except Exception as e:  # noqa: BLE001
                v2 = None
                trace.append(f"second independent query failed: {type(e).__name__}: {e}")
            if not (isinstance(v2, (int, float)) and not isinstance(v2, bool)) or v2 != v2:
                conf = min(conf, 0.6)  # the second look found nothing: the first answer is not confirmed
                trace.append(f"second independent query gave no number ({v2!r}); the answer is not confirmed")
                missing.append("a second, independent table query could not reproduce the answer")
            else:
                v2n = int(round(float(v2))) if unit == "count" else round(float(v2), 2)
                if unit == "count" and isinstance(value, int):
                    v2f = _qty_sum(v2n, res2.get("used", []), tables, question)
                    v2n = v2f if v2f is not None else v2n
                same = abs(float(v2n) - float(value)) <= 0.005 * max(abs(float(value)), 1.0)
                trace.append(f"second independent query: {v2n} -> {'agrees' if same else 'DISAGREES'} with {value}")
                if not same:
                    conf = min(conf, 0.5)
                    missing.append(f"two independent table queries disagree ({value} vs {v2n}); the reading of the "
                                   "schedule is unstable, check the cited rows")
        if det is not None:
            total, det_rows, formula = det
            trace.append(f"per-row multiplier (deterministic): {formula}" +
                         (" -> agrees with the query" if value == total else f" -> replaces the query's {value!r}"))
            value, unit = total, "count"
            conf = 0.85
            missing = [x for x in missing if not x.startswith("two independent table queries")]
            evidence = [Evidence(file=path, page=0, bbox=[round(v, 1) for v in boxes[i]], bbox_space="pdf_pt",
                                 note=row_label.get(i, f"table row {i}")) for i in det_rows if i in boxes]
        if isinstance(value, str) and value.strip().upper() in tableqa.id_tokens(question, path):
            conf = min(conf, 0.2)  # the answer only repeats an identifier from the question
            missing.append(f"the answer {value!r} repeats the question's identifier; the table row was not found")
        used_notes = [i for i in res.get("used", []) if isinstance(i, int) and i >= 900000]
        if used_notes and len(used_notes) == len(res.get("used", [])):
            # Q 09:23: on a schedule sheet a question about the plan's notes was read from the `notes` lines by
            # table-QA code at 0.85 ("FIBER CEMENT CLAPBOARD -" for its colour): free-text lines are the sheet-text
            # reader's level (0.65), not a schedule row's
            conf = min(conf, 0.65)
            trace.append("answer read from free-text note lines only (not schedule rows) -> confidence <= 0.65")
        if isinstance(value, str):
            aw = set(re.findall(r"[a-z0-9]+", value.lower()))
            if aw and aw <= set(re.findall(r"[a-z0-9]+", question.lower())):
                conf = min(conf, 0.2)  # a label, not its value
                missing.append(f"the answer {value!r} only repeats words of the question (a label, not its value)")
        return Answer(value=value, unit=unit, confidence=conf, evidence=evidence, trace=trace, solver=self.name,
                      assumptions=assumptions, missing=missing)

    def _sheet_text(self, path: str, question: str, tabs, groups) -> Answer:
        """A sheet without a schedule: answer from its text groups (tags, notes, title block, two-column lists) and
        the rows of any small table, by row pointing + Python arithmetic (sheettext.py)."""
        rows, boxes = [], {}
        for k, g in enumerate(groups[:600]):
            rows.append({"id": TEXT_ID + k, "view": g.view, "text": g.text})
            boxes[TEXT_ID + k] = g.box
        rid = 700000
        for t in tabs:
            named = [c for c in t.df.columns if not re.fullmatch(r"col\d+", str(c)) and re.search(r"[A-Za-z]{2}", str(c))]
            if not t.title and len(named) < 0.5 * len(t.df.columns):
                continue  # rows of dimension strings on a plan ("col5: -; col10: 5' - 0\"") only mislead the model
            for (_, r), b in zip(t.df.iterrows(), t.row_boxes):
                txt = "; ".join(f"{c}: {v}" for c, v in r.items() if str(v).strip())
                rows.append({"id": rid, "view": t.title or None, "text": f"table row: {txt}"})
                boxes[rid] = b
                rid += 1
        trace = [f"sheet text: {len(groups)} text groups (tags, notes, title block) + {rid - 700000} rows of small "
                 "named tables"]
        try:
            res = sheettext.ask(question, rows, backend=self.backend)
        except Exception as e:  # noqa: BLE001
            return Answer.abstain(self.name, f"sheet text QA failed: {type(e).__name__}: {e}", trace)
        trace += res["trace"]
        if res["value"] is None or (isinstance(res["value"], str) and (NOT_FOUND_RE.match(res["value"]) or (
                len(res["value"]) < 60 and REFUSAL_IN_RE.search(res["value"])))):
            return Answer.abstain(self.name, "the printed text of the sheet does not contain the answer "
                                             f"(op={res['op']})", trace)
        by_id = {r["id"]: r for r in rows}
        evidence = [Evidence(file=path, page=0, bbox=[round(v, 1) for v in boxes[i]], bbox_space="pdf_pt",
                             note=f"text: {by_id[i]['text'][:80]}" + (f" (view {by_id[i]['view']})" if by_id[i]["view"] else ""))
                    for i in res["used"] if i in boxes]
        # fresh probe (experiments/w2/sheet_probe, 20 Qs, no dataset questions on these sheets): not calibrated yet,
        # so below the schedule rows' 0.85; aggregates (count/sum over tags) can miss an untagged or split tag
        # held-out probes (3 sheets written before running): lookups 0.75 were right ~6/10, so 0.65 / 0.55
        conf = 0.65 if res["op"] == "lookup" else 0.55
        missing = []
        if not res["ok"]:
            conf = min(conf, 0.4)
            missing.append("a value the model cited is not printed in the row it cited")
        if not evidence:
            conf = min(conf, 0.3)
            missing.append("no printed row supports the answer")
        about_drawing = re.search(r"\b(drawn|shown|depicted|visible)\b", question, re.I)
        if res["op"] == "count" and about_drawing:
            conf = min(conf, 0.5)
            missing.append("counted the printed tags; elements drawn without a tag are not counted")
        ids = tableqa.id_tokens(question, path)
        if isinstance(res["value"], str) and res["value"].strip().upper() in ids:
            conf = min(conf, 0.2)
            missing.append(f"the answer {res['value']!r} repeats the question's identifier")
        if isinstance(res["value"], str):
            qw = set(re.findall(r"[a-z0-9]+", question.lower()))
            aw = set(re.findall(r"[a-z0-9]+", res["value"].lower()))
            if aw and aw <= qw:
                conf = min(conf, 0.2)  # "(FRONT YARD SETBACK)" for "what is the front yard setback?": the label, not the value
                missing.append(f"the answer {res['value']!r} only repeats words of the question (a label, not its value)")
        cited = " ".join(by_id[i]["text"] for i in res["used"] if i in by_id).upper()
        if ids and evidence and not any(re.search(rf"(?<![\w.-]){re.escape(x)}(?![\w-])", cited) for x in ids):
            conf = min(conf, 0.3)  # "pier P13" but no cited row contains P13 (S-101: a scale string at 0.75)
            missing.append("none of the cited text rows contains the identifier named in the question")
        if isinstance(res["value"], str) and SCALE_RE.search(res["value"]) and not re.search(r"\bscale", question, re.I):
            conf = min(conf, 0.2)  # "vertical reinforcing of pier P13" -> '1/2" = 1'-0"' (the detail's scale)
            missing.append("the answer is a drawing scale, but the question does not ask for a scale")
        if re.search(r"\bschedul", question, re.I):
            # the question is about a schedule, but no schedule table could be rebuilt (or it did not answer):
            # a schedule drawn among details (S-101 pier schedule) is mangled into text groups
            conf = min(conf, 0.3)
            missing.append("the question is about a schedule, but no schedule table could be rebuilt from this sheet's "
                           "text; the answer comes from loose text groups")
        elif res["op"] == "count" and re.search(r"\b(types?|marks?|kinds?)\b", question, re.I):
            conf = min(conf, 0.4)  # counting types/marks = reading a type list (a schedule) that was not rebuilt
            missing.append("counting types/marks needs a schedule table, which could not be rebuilt from the text")
        assumptions = [f"read from {len(evidence)} printed text group(s) of the sheet (room/unit tags, notes, title "
                       "block); stacked lines within ~0.6 line heights were grouped into one tag"]
        if res["op"] in ("count", "sum", "max", "min", "mean"):
            assumptions.append(f"{res['op']} computed in Python over the cited rows' printed values")
        return Answer(value=res["value"], unit=res["unit"], confidence=conf, evidence=evidence, trace=trace,
                      solver=self.name, assumptions=assumptions, missing=missing)



@register("pdf_text")
class PdfTextSolver(ScheduleSolver):
    """Any vector PDF with a text layer from OUTSIDE the dataset's known sources (a drawing set handed in at the demo,
    Stoa's hidden/noon examples): the pipeline routes such PDFs to `pdf_vector`, `pdf_text`, `vlm_direct`, and
    `schedule` (routed only for opening_design) never saw them. Same reader as `schedule`: rebuilt schedule tables, and
    the sheet's text groups (tags, notes, title block) by row pointing. Not for swiss_dwellings / ifc_models (their DXF /
    IFC twins answer) nor opening_design / cubicasa5k (routed elsewhere), so the dataset's answers don't change."""

    def can_handle(self, path: str, question: str) -> bool:
        return Path(path).suffix.lower() == ".pdf" and \
            source_of(path) not in ("swiss_dwellings", "ifc_models", "opening_design", "cubicasa5k")
