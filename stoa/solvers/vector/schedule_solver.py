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
{tables}
Other text on the sheet (legends, notes; not tables):
{text}"""


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
        # legends and notes are short rows; long rows are table rows (already in the tables)
        other = [" | ".join(c.text for c in r.cells)[:160] for r in rows if len(r.cells) <= 3]
        text = "\n".join(t for t in other if len(t) > 2)[:9000]
        doc = DOC.format(tables="\n".join(desc), text=text)
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
        elif unit == "count":
            value = int(round(float(value)))
        elif isinstance(value, float):
            value = round(value, 2)
        if unit not in ("count", "ft2", "m2", "ft", "m", None):
            unit = None
        evidence = [Evidence(file=path, page=0, bbox=[round(v, 1) for v in boxes[i]], bbox_space="pdf_pt",
                             note=f"row {i}") for i in res.get("used", []) if i in boxes]
        conf = 0.55 if evidence else 0.4
        return Answer(value=value, unit=unit, confidence=conf, evidence=evidence, trace=trace, solver=self.name,
                      assumptions=["tables rebuilt from the PDF text layer (row/column alignment); the model wrote "
                                   "the query, the numbers come from the extracted rows"],
                      missing=[] if evidence else ["the query did not report which rows it used"])
