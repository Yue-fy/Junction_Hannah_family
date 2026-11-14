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

DOC = """Tables rebuilt from the text layer of one construction drawing sheet (US units; values are strings exactly
as printed, e.g. "108 SF", "3' - 0\\"", "A1"; empty string = blank cell; multi-line headers are joined; a header
may be wrong or "colN", so look at the values). Each table has a `row_id` column (unique across tables).
Count/quantity/area columns are numbers; for values like "108 SF" a parsed twin column `<col>_num` exists; all
other columns (ids, room numbers, types) are strings: compare them with strings ("118", not 118).
Use double quotes for strings that contain an apostrophe ("WOMEN'S LOCKER").
Counting rows: one row = one item unless a Count/Qty column says otherwise.
Text answers: give the value as printed; if the question also asks what a code means, find the code in `notes`
(e.g. notes[notes.text.str.contains("F4")]) and answer "F4 - <meaning>"; if it asks for two things (how many
and what total), answer one string with both ("3 rooms, 4541 SF"); include those notes rows in `used`.
{tables}"""


NUM_RE = re.compile(r"^-?\d[\d,]*(?:\.\d+)?$")
QTY_RE = re.compile(r"^(-?\d[\d,]*(?:\.\d+)?)\s*(SF|S\.F\.|sq\.?\s*ft|ft²|ft2|m²|m2|LF|EA)\.?$", re.I)
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
    return df


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


def _clean(name: str) -> str:
    return re.sub(r"\W+", "_", name).strip("_").lower()[:30] or "table"


@register("schedule")
class ScheduleSolver(BaseSolver):
    """Options: backend=local|nvidia, min_rows=3."""

    extensions = (".pdf",)

    def __init__(self, backend: str = "local", **kwargs):
        super().__init__(**kwargs)
        self.backend = backend

    def can_handle(self, path: str, question: str) -> bool:
        if Path(path).suffix.lower() != ".pdf" or source_of(path) in ("swiss_dwellings", "ifc_models"):
            return False
        return True

    def solve(self, path: str, question: str) -> Answer:
        pdf = str(abspath(path))
        tabs, rows = pdf_tables(pdf)
        if not tabs:
            return self.abstain("no tables found in the PDF text layer")
        tables: dict[str, pd.DataFrame] = {}
        boxes: dict[int, tuple] = {}
        desc = []
        rid = 0
        for k, t in enumerate(tabs):
            name = f"t{k + 1}_{_clean(t.title)}" if t.title else f"t{k + 1}"
            df = _typed(t.df)
            ids = list(range(rid, rid + len(df)))
            df.insert(0, "row_id", ids)
            for i, b in zip(ids, t.row_boxes):
                boxes[i] = b
            rid += len(df) + 1000 - (len(df) % 1000)  # table k's row ids start at a multiple of 1000
            tables[name] = df
            desc.append(f"- `{name}`: {t.title or 'untitled'}, {len(df)} rows, columns {list(df.columns)}")
        # sheet text outside the tables (legends/notes), capped
        # legends and notes are short rows (long rows are table rows): a `notes` table, so the code can look up
        # what a code means ("F4") and the lines it used become evidence too
        notes, nid = [], 900000
        for r in rows:
            if len(r.cells) <= 3:
                txt = " | ".join(c.text for c in r.cells)[:160]
                if len(txt) > 2:
                    notes.append({"row_id": nid, "text": txt})
                    boxes[nid] = tuple(min(c.box[k] for c in r.cells) if k < 2 else max(c.box[k] for c in r.cells)
                                       for k in range(4))
                    nid += 1
        tables["notes"] = pd.DataFrame(notes[:300])
        desc.append(f"- `notes`: other text lines of the sheet (legends, keys, general notes), {len(notes[:300])} rows,"
                    " columns ['row_id', 'text']")
        doc = DOC.format(tables="\n".join(desc))
        trace = [f"{len(tabs)} tables from the PDF text layer: " + "; ".join(
            f"{n} ({len(df)}x{len(df.columns) - 1})" for n, df in tables.items())]
        try:
            res = tableqa.ask(question, tables, backend=self.backend, doc=doc, id_col="row_id",
                              units='"count", "ft2", "m2", "ft", "m"')
        except Exception as e:  # noqa: BLE001
            return Answer.abstain(self.name, f"table QA failed: {type(e).__name__}: {e}", trace)
        trace.append("table QA code: " + " ; ".join(ln.strip() for ln in (res.get("code") or "").splitlines()
                                                   if ln.strip())[:700])
        if res.get("value") is None:
            return Answer.abstain(self.name, f"table QA gave no answer ({res.get('error')})", trace)
        value, unit = res["value"], res.get("unit")
        unit = UNIT_MAP.get(str(unit).lower().replace(".", "").strip(), unit) if unit else unit
        if isinstance(value, bool):
            value, unit = ("yes" if value else "no"), None
        if isinstance(value, str):
            unit = None
            value = re.sub(r"(\d+')\s*-\s*(\d)", r"\1-\2", value).strip()  # 5' - 10 3/8" -> 5'-10 3/8"
        elif unit == "count":
            value = int(round(float(value)))
        elif isinstance(value, float):
            value = round(value, 2)
        if unit not in ("count", "ft2", "m2", "ft", "m", None):
            unit = None
        row_label = {}
        for name, df in tables.items():
            if name == "notes" or df.empty:
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
        if isinstance(value, str):
            # a bare code answer ("F4") gets its meaning from the sheet's own legend: "F4 - RESILIENT FLOORING"
            ex = _explain_codes(value, question, rows, _legend(rows))
            if ex is not None:
                value, found = ex
                trace.append("legend: " + "; ".join(f"{c} = {m}" for c, m, _ in found))
                evidence += [Evidence(file=path, page=0, bbox=[round(v, 1) for v in b], bbox_space="pdf_pt",
                                      note=f"legend: {c} = {m}") for c, m, b in found]
        # calibrated on dev (opening_design, local model): 78% right overall; answers that cite rows are right more often
        conf = 0.8 if n_rows_used else 0.5
        missing = [] if n_rows_used else ["the query did not report which rows it used"]
        about_table = re.search(r"schedul|listed|table|legend|\bkey\b|specified|finish", question, re.I)
        about_drawing = re.search(r"\b(drawn|shown|depicted|visible)\b|\bin\s+(?:the\s+)?(?:enlarged\s+)?plan\b",
                                  question, re.I)
        if about_drawing and not about_table:
            conf = min(conf, 0.15)
            missing.append("the question is about symbols drawn on a plan; schedules and text can't count those "
                           "(needs symbol detection on the drawing)")
        if value == 0 and not evidence:
            conf = min(conf, 0.2)
        return Answer(value=value, unit=unit, confidence=conf, evidence=evidence, trace=trace, solver=self.name,
                      assumptions=["tables rebuilt from the PDF text layer (row/column alignment); the model wrote "
                                   "the query, the numbers come from the extracted rows"],
                      missing=missing)
