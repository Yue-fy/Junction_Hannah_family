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
    words: tuple = ()  # (x0, x1, text, box) per word, visual space

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
    cell_boxes: list[list] = field(default_factory=list)  # per data row, per column: box or None
    totals: list[tuple[str, tuple]] = field(default_factory=list)  # printed total rows ("BASEMENT: 8 | 1091 SF"), box


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
        rows.append(Row(y, [Cell(" ".join(w[4] for w in s), s[0][0], s[-1][2], y, _union([w[5] for w in s]),
                                 tuple((w[0], w[2], w[4], w[5]) for w in s))
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
    tables = [p for t in tables for p in _split_stacked(t)]
    for t in tables:
        _pull_totals(t)
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
    if sum(has_digit) >= 0.8 * len(run):  # header repeats / blank rows inside the table
        run = [i for i, d in zip(run, has_digit) if d]
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

    def col_of(c: Cell, header: bool = False) -> int | None:
        # a centred header word may start left of the left-aligned ids below it
        if c.x0 < x_left - 2 - (min(c.x1 - c.x0, 3 * h) / 2 if header else 0) or c.xc > x_right:
            return None
        return min(range(len(xs)), key=lambda k: abs(xs[k] - c.xc))

    data, boxes, cboxes = [], [], []
    for i in run:
        vals = [""] * len(xs)
        bs = []
        cb: list = [None] * len(xs)
        for c in rows[i].cells:
            k = col_of(c)
            if k is not None:
                vals[k] = (vals[k] + " " + c.text).strip()
                bs.append(c.box)
                cb[k] = c.box if cb[k] is None else _union([cb[k], c.box])
        _split_glued(rows[i].cells, xs, vals, cb, col_of)
        if not bs or (len(xs) >= 4 and sum(bool(v) for v in vals) <= 1):
            continue  # stray word / blank row inside the table, not a record
        data.append(vals)
        boxes.append(_union(bs))
        cboxes.append(cb)
    # header: rows just above the first data row, within the table's x-range
    first = run[0]
    head = [""] * len(xs)
    title = ""
    j = first - 1
    n_head = 0
    extra = []
    head_cells: list[tuple[int, Cell]] = []  # (header line, 1 = the line right above the data), cell
    while j >= 0 and rows[first].y - rows[j].y < 9 * h and n_head < 5:
        hc = [c for c in rows[j].cells if col_of(c, header=True) is not None]
        if (len({col_of(c, header=True) for c in hc}) >= max(3, 0.5 * len(xs)) and any(ch.isdigit() for c in hc for ch in c.text)
                and _depth < 3):
            extra.append(j)  # a data row whose key cell is blank/elsewhere: belongs to the table, not the header
            first = j
            j -= 1
            continue
        if hc:
            n_head += 1
            if len(hc) == 1 and len(xs) > 3 and n_head > 1 and re.search(r"schedule|legend|key|types?\b|list", hc[0].text, re.I):
                title = hc[0].text
                break
            for c in hc:
                k = col_of(c, header=True)
                head[k] = (c.text + " " + head[k]).strip()
                head_cells.append((n_head, c))
        j -= 1
    if extra:
        return _build(rows, sorted(set(run) | set(extra)), h, _depth + 1)
    if not re.search(r"schedule", title, re.I):
        # the caption ("Door Schedule", "FINISH ROOM SCHEDULE") sits a few rows above the header
        for j in range(first - 1, -1, -1):
            if rows[first].y - rows[j].y > 25 * h:
                break
            cap = [c for c in rows[j].cells if c.x1 >= x_left - 2 * h and c.x0 <= x_right
                   and re.search(r"schedule", c.text, re.I)]
            if cap:
                title = cap[0].text
                break
    head = _group_headers(head, xs, head_cells)
    xs, head, data = _merge_split_columns(xs, head, data, cboxes)
    names, seen = [], {}
    for k, hname in enumerate(head):
        nm = re.sub(r"\s+", " ", hname).strip() or f"col{k}"
        seen[nm] = seen.get(nm, 0) + 1
        names.append(nm if seen[nm] == 1 else f"{nm}_{seen[nm]}")
    df = pd.DataFrame(data, columns=names)
    bbox = _union(boxes)
    return Table(title=title, columns=names, df=df, row_boxes=boxes, bbox=bbox, run=list(run), xs=list(xs),
                 cell_boxes=cboxes,
                 y0=rows[run[0]].y, y1=rows[run[-1]].y)


def _group_headers(head: list[str], xs: list[float], head_cells: list[tuple[int, Cell]]) -> list[str]:
    """Grouped headers: "Door | Frame" over "Type Matl | Matl Type" gives two columns whose bottom header line is the
    same ("Matl"). Prefix each such column with the nearest label from the lines above ("Door Matl", "Frame Matl").
    Words repeated by stacked lines are dropped ("Door Door Type" -> "Door Type")."""
    def clean(h: str) -> str:
        return re.sub(r"\b([A-Za-z]{2,})(?:\s+\1\b)+", r"\1", re.sub(r"\s+", " ", h).strip(), flags=re.I)

    head = [clean(h) for h in head]
    upper = [c for line, c in head_cells if line >= 2]
    base: dict[int, str] = {}
    for line, c in head_cells:
        if line == 1:
            k = min(range(len(xs)), key=lambda j: abs(xs[j] - c.xc))
            base[k] = (base.get(k, "") + " " + c.text).strip()
    groups: dict[str, list[int]] = {}
    for k, b in base.items():
        groups.setdefault(b.lower(), []).append(k)
    for ks in groups.values():
        if len(ks) < 2 or not upper:
            continue
        pref = [min(upper, key=lambda c: abs(c.xc - xs[k])).text.strip() for k in ks]
        if len({p.lower() for p in pref}) == len(ks):  # every duplicate gets its own group label
            for k, p in zip(ks, pref):
                if p.lower() not in head[k].lower():
                    head[k] = clean(f"{p} {head[k]}")
    return head


def _merge_split_columns(xs: list[float], head: list[str], data: list[list[str]], cboxes: list[list] | None = None):
    """One printed column can be split in two when its cells are aligned differently (left vs centred): an unnamed
    column whose filled cells never share a row with a named neighbour's filled cells is that neighbour."""
    k = 0
    while k < len(xs) and data:
        if head[k].strip() or not any(r[k] for r in data):
            k += 1
            continue
        cands = []
        for nb in (k - 1, k + 1):
            if 0 <= nb < len(xs) and head[nb].strip() and not any(r[k] and r[nb] for r in data) \
                    and any(r[nb] for r in data):
                cands.append((abs(xs[nb] - xs[k]), nb))
        if not cands:
            k += 1
            continue
        nb = min(cands)[1]
        for r in data:
            r[nb] = r[nb] or r[k]
        for r in data:
            del r[k]
        for cb in cboxes or []:
            cb[nb] = cb[nb] or cb[k]
            del cb[k]
        del xs[k]
        del head[k]
    return xs, head, data


TITLE_IN_HEAD = re.compile(r"^(?P<t>.*?\b(?:SCHEDULE|TAKEOFF|LEGEND)\b(?:\s*-\s*[A-Z]+)?)\s+(?P<n>\S.*)$", re.I)
TOTAL_RE = re.compile(r"^(?:grand\s+)?totals?\b|^[^:]{1,40}:\s*\d+\s*$", re.I)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _sub_table(t: Table, rows_idx: list[int], cols: list[int], title: str, names: list[str] | None = None) -> Table | None:
    """Columns `cols` of rows `rows_idx` of t as a table of its own (rows/columns that are empty there are dropped)."""
    df = t.df
    name_of = dict(zip(cols, names or [df.columns[c] for c in cols]))
    keep = [i for i in rows_idx if any(str(df.iat[i, c]).strip() for c in cols)]
    cols = [c for c in cols if any(str(df.iat[i, c]).strip() for i in keep)]
    if len(keep) < 2 or len(cols) < 2:
        return None
    names = [name_of[c] for c in cols]
    seen, uniq = {}, []
    for nm in names:
        seen[nm] = seen.get(nm, 0) + 1
        uniq.append(nm if seen[nm] == 1 else f"{nm}_{seen[nm]}")
    sub = pd.DataFrame([[df.iat[i, c] for c in cols] for i in keep], columns=uniq)
    cb = [[t.cell_boxes[i][c] for c in cols] if t.cell_boxes else [] for i in keep]
    boxes = [_union([b for b in r if b is not None]) if any(b is not None for b in r) else t.row_boxes[i]
             for r, i in zip(cb, keep)]
    return Table(title=title, columns=uniq, df=sub, row_boxes=boxes, bbox=_union(boxes), run=[t.run[0]] if t.run else [],
                 xs=[t.xs[c] for c in cols] if t.xs else [], y0=t.y0, y1=t.y1, cell_boxes=cb)


def _split_stacked(t: Table) -> list[Table]:
    """Revit sheets put schedules side by side and stack them: rows of the left schedule share their y with rows of
    the right one, and a second schedule below the right one repeats header words ("Mark | Family | Type | Count")
    inside the data. Split at such a repeated header: left columns = one table; right columns above the header =
    a second table; below it = a third. Schedule titles merged into column names ("WINDOW SCHEDULE - SIMPLIFIED
    Count") become the tables' titles."""
    df = t.df
    if df.shape[0] < 4 or df.shape[1] < 4:
        return [t]
    titles: dict[int, str] = {}
    names = list(df.columns)
    for c, nm in enumerate(names):
        m = TITLE_IN_HEAD.match(str(nm))
        if m:
            titles[c] = m.group("t").strip()
            names[c] = m.group("n").strip()
    hdr_words = {_norm(w) for nm in names for w in [nm, *str(nm).split()] if len(_norm(w)) >= 3}
    split_row, j0 = None, None
    for i in range(1, df.shape[0]):
        hits = [c for c in range(df.shape[1]) if str(df.iat[i, c]).strip() and _norm(str(df.iat[i, c])) in hdr_words]
        if len(hits) >= 3 and not any(ch.isdigit() for c in hits for ch in str(df.iat[i, c])):
            split_row, j0 = i, min(hits)
            break
    if split_row is None:
        if len(titles) >= 2:  # side by side, nothing stacked: split between the two titled column groups
            cs = sorted(titles)
            gap = max(range(cs[0] + 1, cs[1] + 1), key=lambda c: (t.xs[c] - t.xs[c - 1]) if t.xs else 0)
            t.df.columns = names
            left = _sub_table(t, list(range(df.shape[0])), list(range(gap)), titles[cs[0]])
            right = _sub_table(t, list(range(df.shape[0])), list(range(gap, df.shape[1])), titles[cs[1]])
            return [x for x in (left, right) if x is not None] or [t]
        if titles and not re.search(r"schedule|takeoff|legend", t.title or "", re.I):
            t.title = next(iter(titles.values()))
        t.df.columns = names
        t.columns = names
        return [t]
    # header block of the lower table: the split row plus rows just above it with only text in the right columns
    top = split_row
    while top - 1 >= 0 and all(not str(df.iat[top - 1, c]).strip() or not any(ch.isdigit() for ch in str(df.iat[top - 1, c]))
                               for c in range(j0, df.shape[1])) and any(str(df.iat[top - 1, c]).strip()
                                                                        for c in range(j0, df.shape[1])):
        top -= 1
    lower_names = [" ".join(str(df.iat[i, c]).strip() for i in range(top, split_row + 1) if str(df.iat[i, c]).strip())
                   or names[c] for c in range(j0, df.shape[1])]
    left_title = next((titles[c] for c in sorted(titles) if c < j0), t.title if j0 > 0 else "")
    right_title = next((titles[c] for c in sorted(titles) if c >= j0), "" if j0 > 0 else t.title)
    t.df.columns = names
    out = []
    if j0 > 0:
        out.append(_sub_table(t, list(range(df.shape[0])), list(range(j0)), left_title, names[:j0]))
    out.append(_sub_table(t, list(range(top)), list(range(j0, df.shape[1])), right_title, names[j0:]))
    out.append(_sub_table(t, list(range(split_row + 1, df.shape[0])), list(range(j0, df.shape[1])), "", lower_names))
    out = [x for x in out if x is not None]
    return out or [t]


def _pull_totals(t: Table) -> None:
    """Printed subtotal/total rows ("BASEMENT: 8 | 1091 SF", "Grand total: 39") are not records: move them out of
    the table (t.totals keeps their text and box, for the notes and as a cross-check)."""
    df = t.df
    if df.empty:
        return
    drop = []
    for i in range(len(df)):
        vals = [str(v).strip() for v in df.iloc[i] if str(v).strip()]
        if vals and TOTAL_RE.match(vals[0]) and len(vals) <= max(2, 0.5 * df.shape[1]):
            drop.append(i)
            t.totals.append((" | ".join(vals), t.row_boxes[i]))
    if drop and len(drop) < len(df):
        keep = [i for i in range(len(df)) if i not in drop]
        t.df = df.iloc[keep].reset_index(drop=True)
        t.row_boxes = [t.row_boxes[i] for i in keep]
        if t.cell_boxes:
            t.cell_boxes = [t.cell_boxes[i] for i in keep]
    elif drop:
        t.totals.clear()


DIM_END = re.compile(r"(?:\d+/\d+|\d)[\"']?$")
WORD_ONLY = re.compile(r"[A-Za-z][A-Za-z./()&-]*$")


def _split_glued(cells: list[Cell], xs: list[float], vals: list[str], cb: list, col_of) -> None:
    """Tight columns glue neighbouring cells into one ("6' - 5 3/8\" SLIDER" = height + type). Split a cell where a
    dimension/number is followed by plain words whose centre is nearest to a column on the right that is empty in
    this row."""
    for c in cells:
        k = col_of(c)
        if k is None or len(c.words) < 2 or vals[k] != c.text:
            continue
        for sp in range(1, len(c.words)):
            left, right = c.words[:sp], c.words[sp:]
            if not DIM_END.search(left[-1][2]) or not all(WORD_ONLY.match(w[2]) for w in right):
                continue
            xc = (right[0][0] + right[-1][1]) / 2
            k2 = min(range(len(xs)), key=lambda j: abs(xs[j] - xc))
            if k2 <= k or vals[k2] or abs(xs[k2] - xc) >= abs(xs[k] - xc):
                continue
            vals[k] = " ".join(w[2] for w in left)
            vals[k2] = " ".join(w[2] for w in right)
            cb[k] = _union([w[3] for w in left])
            cb[k2] = _union([w[3] for w in right])
            break


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
