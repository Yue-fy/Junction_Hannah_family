"""Schedules from a vector PDF's text layer (no ML, no grid lines needed).

1. words -> visual space (page.rotation_matrix), rows by y (tol 0.4 x median word height),
   cells by x-gap > 0.6 x height. Each cell keeps its box in UNROTATED page space (= PyMuPDF word space,
   used for `pdf_pt` evidence).
2. tables = maximal runs of rows whose FIRST cell starts at the same x (±4 pt) and that have >= 3 cells
   (data rows of a schedule start in the key column). Interleaved rows of other tables (side by side on the
   sheet) don't break a run: rows whose first cell is elsewhere are skipped while the gap stays small.
3. columns = clusters of cell x-centres that occur in >= 20% of the run's rows; cells right of the table's
   last column (neighbouring table) are dropped.
4. header = text of the up-to-4 rows just above the first data row, assigned to the nearest column.
Output: pandas DataFrames (one per table) + per-row boxes for evidence.
"""

from __future__ import annotations

import functools
import re
import statistics
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Cell:
    text: str
    x0: float  # visual space
    x1: float
    y: float
    box: tuple  # unrotated page space (PyMuPDF words), for evidence

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Row:
    y: float
    cells: list[Cell]


@dataclass
class Table:
    title: str
    columns: list[str]
    df: pd.DataFrame
    row_boxes: list[tuple]  # unrotated page-space box per data row
    bbox: tuple
    notes: list[str] = field(default_factory=list)
    run: list[int] = field(default_factory=list)  # row indices (visual rows) of the data rows
    xs: list[float] = field(default_factory=list)  # column x-centres (visual space)
    y0: float = 0.0
    y1: float = 0.0


def _union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def page_rows(page) -> tuple[list[Row], float]:
    import pymupdf

    M = page.rotation_matrix
    ws = []
    for w in page.get_text("words"):
        r = pymupdf.Rect(w[:4]) * M
        ws.append((r.x0, r.y0, r.x1, r.y1, w[4], tuple(round(v, 2) for v in w[:4])))
    if not ws:
        return [], 0.0
    h = statistics.median(w[3] - w[1] for w in ws)
    ws.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    groups, cur, ys = [], [], []
    for w in ws:
        yc = (w[1] + w[3]) / 2
        if cur and abs(yc - statistics.mean(ys)) > 0.4 * h:
            groups.append(cur)
            cur, ys = [], []
        cur.append(w)
        ys.append(yc)
    groups.append(cur)
    rows = []
    for g in groups:
        g.sort(key=lambda w: w[0])
        cells, seg = [], [g[0]]
        for a, b in zip(g, g[1:]):
            if b[0] - a[2] > 0.6 * h:
                cells.append(seg)
                seg = []
            seg.append(b)
        cells.append(seg)
        y = statistics.mean((w[1] + w[3]) / 2 for w in g)
        rows.append(Row(y, [Cell(" ".join(w[4] for w in s), s[0][0], s[-1][2], y, _union([w[5] for w in s]))
                            for s in cells]))
    return rows, h


def _cluster_1d(vals: list[float], tol: float) -> list[float]:
    vals = sorted(vals)
    out, cur = [], [vals[0]] if vals else []
    for v in vals[1:]:
        if v - cur[-1] <= tol:
            cur.append(v)
        else:
            out.append(cur)
            cur = [v]
    if cur:
        out.append(cur)
    return [(statistics.median(c), len(c)) for c in out]


def _first_cell(r: Row) -> Cell | None:
    """Key cell of a row: the first cell, skipping 1-2 character grid markers ("E", "D") in front of it."""
    cells = r.cells
    if len(cells) >= 2 and len(cells[0].text) == 1 and cells[0].text.isalpha() and cells[1].x0 - cells[0].x1 > 40:
        cells = cells[1:]
    return cells[0] if len(cells) >= 3 else None


def find_tables(rows: list[Row], h: float, min_rows: int = 3) -> list[Table]:
    # anchors: x0 of the key cell of rows with >= 3 cells, clustered with a tolerance (centred ids shift x0)
    firsts = [(i, c) for i, r in enumerate(rows) if (c := _first_cell(r)) is not None]
    by_anchor: dict[int, list[int]] = {}
    order = sorted(firsts, key=lambda ic: ic[1].x0)
    k, prev = -1, None
    for i, c in order:
        if prev is None or c.x0 - prev > 0.6 * h:
            k += 1
        by_anchor.setdefault(k, []).append(i)
        prev = c.x0
    tables, used = [], set()
    for key in sorted(by_anchor, key=lambda k: -len(by_anchor[k])):
        idx = sorted(i for i in by_anchor[key] if i not in used)
        if len(idx) < min_rows:
            continue
        # split into runs where consecutive data rows are not too far apart (<= 4 row heights + interleaving)
        runs, cur = [], [idx[0]]
        for a, b in zip(idx, idx[1:]):
            if rows[b].y - rows[a].y <= 6 * h:
                cur.append(b)
            else:
                runs.append(cur)
                cur = [b]
        runs.append(cur)
        for run in runs:
            if len(run) < min_rows:
                continue
            t = _build(rows, run, h)
            if t is not None:
                tables.append(t)
                used.update(run)
    tables = _merge(rows, tables, h)
    tables.sort(key=lambda t: (t.y0, t.bbox[0]))
    return tables


def _build(rows: list[Row], run: list[int], h: float, _depth: int = 0) -> Table | None:
    # leading rows without any digit are header rows when most data rows carry digits (ids, sizes, counts)
    def _key_cells(r: Row) -> list[Cell]:
        fc = _first_cell(r)
        return r.cells[r.cells.index(fc):][:3] if fc is not None else []

    has_digit = [any(ch.isdigit() for c in _key_cells(rows[i]) for ch in c.text) for i in run]
    if sum(has_digit) >= 0.7 * len(run):
        while run and not has_digit[0]:
            run, has_digit = run[1:], has_digit[1:]
    if len(run) < 2:
        return None
    x_left = min(_first_cell(rows[i]).x0 for i in run)
    cells = [c for i in run for c in rows[i].cells if c.x0 >= x_left - 2]
    cols = [(x, n) for x, n in _cluster_1d([c.xc for c in cells], 1.6 * h) if n >= 0.2 * len(run)]
    if len(cols) < 2:
        return None
    # the table ends where the column sequence has a big gap (neighbouring table)
    xs = [x for x, _ in cols]
    end = len(xs)
    for k in range(1, len(xs)):
        if xs[k] - xs[k - 1] > 25 * h:
            end = k
            break
    xs = xs[:end]
    x_right = xs[-1] + 12 * h

    def col_of(c: Cell) -> int | None:
        if c.x0 < x_left - 2 or c.xc > x_right:
            return None
        return min(range(len(xs)), key=lambda k: abs(xs[k] - c.xc))

    data, boxes = [], []
    for i in run:
        vals = [""] * len(xs)
        bs = []
        for c in rows[i].cells:
            k = col_of(c)
            if k is not None:
                vals[k] = (vals[k] + " " + c.text).strip()
                bs.append(c.box)
        data.append(vals)
        boxes.append(_union(bs))
    # header: rows just above the first data row, within the table's x-range
    first = run[0]
    head = [""] * len(xs)
    title = ""
    j = first - 1
    n_head = 0
    extra = []
    while j >= 0 and rows[first].y - rows[j].y < 9 * h and n_head < 5:
        hc = [c for c in rows[j].cells if col_of(c) is not None]
        if (len({col_of(c) for c in hc}) >= max(3, 0.5 * len(xs)) and any(ch.isdigit() for c in hc for ch in c.text)
                and _depth < 3):
            extra.append(j)  # a data row whose key cell is blank/elsewhere: belongs to the table, not the header
            first = j
            j -= 1
            continue
        if hc:
            n_head += 1
            if len(hc) == 1 and len(xs) > 3 and n_head > 1:
                title = hc[0].text
                break
            for c in hc:
                k = col_of(c)
                head[k] = (c.text + " " + head[k]).strip()
        j -= 1
    if extra:
        return _build(rows, sorted(set(run) | set(extra)), h, _depth + 1)
    names, seen = [], {}
    for k, hname in enumerate(head):
        nm = re.sub(r"\s+", " ", hname).strip() or f"col{k}"
        seen[nm] = seen.get(nm, 0) + 1
        names.append(nm if seen[nm] == 1 else f"{nm}_{seen[nm]}")
    df = pd.DataFrame(data, columns=names)
    bbox = _union(boxes)
    return Table(title=title, columns=names, df=df, row_boxes=boxes, bbox=bbox, run=list(run), xs=list(xs),
                 y0=rows[run[0]].y, y1=rows[run[-1]].y)


def _merge(rows: list[Row], tables: list[Table], h: float) -> list[Table]:
    """Rows of one schedule whose key column is blank start at another x and form separate runs; merge tables
    that overlap vertically (or touch) and whose columns are mostly the same."""
    changed = True
    while changed:
        changed = False
        tables.sort(key=lambda t: -len(t.run))
        for i, a in enumerate(tables):
            for b in tables[i + 1:]:
                if b.y0 > a.y1 + 6 * h or b.y1 < a.y0 - 6 * h:
                    continue
                shared = sum(1 for x in b.xs if any(abs(x - y) <= 1.6 * h for y in a.xs))
                if shared < 0.7 * len(b.xs) or shared < 3:
                    continue
                m = _build(rows, sorted(set(a.run) | set(b.run)), h)
                if m is None or len(m.xs) < len(a.xs):
                    continue
                tables = [t for t in tables if t is not a and t is not b] + [m]
                changed = True
                break
            if changed:
                break
    return tables


@functools.lru_cache(maxsize=32)
def pdf_tables(pdf_abspath: str, page_no: int = 0) -> tuple[list[Table], list[Row]]:
    import pymupdf

    with pymupdf.open(pdf_abspath) as doc:
        rows, h = page_rows(doc[page_no])
    return find_tables(rows, h), rows
