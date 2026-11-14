"""Text groups of a vector PDF sheet: room/unit tags, note paragraphs, title-block fields, each with the drawing view
it sits in. A plan's text is not a table: a life-safety room tag is 5-8 stacked short lines ("COMMUNITY / ROOM /
115 - 410 SF / A-2 Occupancy / 27.3 O.L."), a general note is a paragraph. Rebuilding rows across the whole sheet
(pdftables) glues unrelated tags and note columns together; grouping stacked lines keeps each tag whole.

1. lines from PyMuPDF (`dict`), boxes moved to visual space (page.rotation_matrix); only lines that read
   horizontally on the displayed sheet are grouped (vertical text stays alone: mostly dimension strings).
2. two lines join when they have about the same font size, the vertical gap is < 0.6 x line height, and they
   overlap horizontally (stacked, as in a tag or a paragraph). Groups are capped at 40 lines.
3. view titles: groups that contain a printed scale ('3/32" = 1'-0"', '1:100', 'SCALE: ...'); the title is the
   longest line of the group that is not the scale or a bare number. A group belongs to the view whose title is
   below it and to its left (US sheets put the title under the view's lower-left corner), nearest first.
Output boxes are in UNROTATED page space (PyMuPDF word space = `pdf_pt` evidence), like pdftables.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass

SCALE_RE = re.compile(r"\d+\s*/\s*\d+\s*\"?\s*=\s*1'\s*-?\s*0\"|\b1\s*\"\s*=\s*\d+\s*'|\b1\s*:\s*\d{1,4}\b|"
                      r"\bscale\s*:|\bN\.?T\.?S\.?\b|not to scale", re.I)


DIM_RE = re.compile(r"-?\d+\s*'\s*-?\s*\d*(?:\s+\d+/\d+)?\s*\"?|\d+(?:[.,]\d+)?\s*(?:mm|cm|m|ft|in|%|sf|m²)\.?", re.I)
PAREN_RE = re.compile(r"\([A-Za-z][^()]{2,60}\)")


@dataclass
class TextGroup:
    text: str  # lines in reading order, joined with " / "
    box: tuple  # unrotated page space
    vbox: tuple  # visual space
    n_lines: int
    size: float
    view: str | None = None
    is_title: bool = False
    kind: str = "group"  # "group" (tag / paragraph / single line) or "list" (one line of a zipped two-column list)


def _lines(page):
    import pymupdf

    M = page.rotation_matrix
    rot = page.rotation % 360
    out = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            t = " ".join("".join(s["text"] for s in ln["spans"]).split())
            if not t:
                continue
            dx, dy = ln["dir"]
            # visual direction = dir rotated like the page
            vx, vy = {0: (dx, dy), 90: (-dy, dx), 180: (-dx, -dy), 270: (dy, -dx)}.get(rot, (dx, dy))
            v = pymupdf.Rect(ln["bbox"]) * M
            size = max((s["size"] for s in ln["spans"]), default=0.0)
            out.append({"t": t, "box": tuple(round(x, 2) for x in ln["bbox"]), "v": (v.x0, v.y0, v.x1, v.y1),
                        "horiz": abs(vx) > 0.9 and abs(vy) < 0.2 and vx > 0, "size": size})
    return _join_baseline(out)


def _join_baseline(lines):
    """Pieces of one printed line become one line: same baseline band, same size, horizontal gap < 0.6 line heights
    (< 40 when the right piece is a value: "PUBLIC AREAS:" ...... "= 100 PSF")."""
    hz = sorted((x for x in lines if x["horiz"]), key=lambda x: ((x["v"][1] + x["v"][3]) / 2, x["v"][0]))
    out = [x for x in lines if not x["horiz"]]
    used = [False] * len(hz)
    for i, a in enumerate(hz):
        if used[i]:
            continue
        cur = dict(a)
        used[i] = True
        h = a["v"][3] - a["v"][1]
        for j in range(i + 1, len(hz)):
            b = hz[j]
            if (b["v"][1] + b["v"][3]) / 2 - (a["v"][1] + a["v"][3]) / 2 > 0.4 * h:
                break
            if used[j] or abs(b["size"] - a["size"]) > 0.25 * max(a["size"], 1e-6):
                continue
            gap = b["v"][0] - cur["v"][2]
            # a tab-aligned value column: "PUBLIC AREAS:" ........ "= 100 PSF"
            # (two room tags side by side are NOT joined: their lines are separate pieces ~2+ heights apart)
            if b["t"].startswith("=") or (cur["t"].rstrip().endswith(":") and b["t"][:1].isdigit()):
                lim = 40
            elif b["t"][:1].isdigit() and not re.search(r"\d", cur["t"]):  # "A) SLABS-ON-GRADE" .. "4000 PSI"
                lim = 6
            else:
                lim = 0.6
            if -0.5 * h <= gap <= lim * h:
                cur["t"] = cur["t"] + " " + b["t"]
                cur["v"] = (min(cur["v"][0], b["v"][0]), min(cur["v"][1], b["v"][1]), max(cur["v"][2], b["v"][2]),
                            max(cur["v"][3], b["v"][3]))
                cur["box"] = (min(cur["box"][0], b["box"][0]), min(cur["box"][1], b["box"][1]),
                              max(cur["box"][2], b["box"][2]), max(cur["box"][3], b["box"][3]))
                used[j] = True
        out.append(cur)
    return out


VALUE_RE = re.compile(r"^=?\s*\$?\d[\d,./'\"\- ]*(?:\s*[A-Za-z%#]{1,5}\.?\*?)?$")
ITEM_RE = re.compile(r"^\(?(?:\d{1,2}|[A-Z])[.)]\s")  # "1. ", "A) ", "(B) ": a new numbered note starts


def _chunks(idx: list[int], lines, max_lines: int = 8) -> list[list[int]]:
    """A long stacked group (a column of general notes) -> one chunk per numbered note, at most max_lines each."""
    if len(idx) <= 10:
        return [idx]
    out, cur = [], []
    for i in idx:
        if cur and (len(cur) >= max_lines or (ITEM_RE.match(lines[i]["t"]) and len(cur) >= 2)):
            out.append(cur)
            cur = []
        cur.append(i)
    if cur:
        out.append(cur)
    return out


def _groups(lines) -> list[list[int]]:
    n = len(lines)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    hz = sorted((i for i in range(n) if lines[i]["horiz"]), key=lambda i: lines[i]["v"][1])

    def dim_label(i, j):
        """A dimension value and its '(LABEL)' stacked across the dimension line ("35' - 0\"" over "(FRONT YARD
        SETBACK)"): ~1 line height apart, so the 0.6 rule never joins them (W2 09:55: the setback lost its value)."""
        ti, tj = lines[i]["t"], lines[j]["t"]
        return (DIM_RE.fullmatch(ti) and PAREN_RE.fullmatch(tj)) or (DIM_RE.fullmatch(tj) and PAREN_RE.fullmatch(ti))
    count = {i: 1 for i in range(n)}
    for k, i in enumerate(hz):
        a = lines[i]["v"]
        ha = a[3] - a[1]
        for j in hz[k + 1:]:
            b = lines[j]["v"]
            if b[1] - a[3] > 1.6 * ha:
                break
            hb = b[3] - b[1]
            if b[1] < a[1] + 0.5 * ha:  # same line height band: side-by-side, not stacked
                continue
            if abs(lines[i]["size"] - lines[j]["size"]) > 0.25 * max(lines[i]["size"], lines[j]["size"], 1e-6):
                continue
            if b[1] - a[3] > 0.6 * min(ha, hb):
                if not (b[1] - a[3] <= 1.6 * min(ha, hb) and dim_label(i, j) and
                        abs(a[0] + a[2] - b[0] - b[2]) <= 2 * max(ha, hb)):
                    continue
            if min(a[2], b[2]) - max(a[0], b[0]) <= 0:  # no horizontal overlap
                continue
            # lines of one tag / paragraph share a left edge, right edge or centre; two tags placed diagonally
            # close to each other interleave their lines but don't align
            tol = max(ha, hb)
            if not (abs(a[0] - b[0]) <= tol or abs(a[2] - b[2]) <= tol or abs(a[0] + a[2] - b[0] - b[2]) <= 2 * tol):
                continue
            ri, rj = find(i), find(j)
            if ri != rj and count[ri] + count[rj] <= 40:
                parent[rj] = ri
                count[ri] += count[rj]
    out: dict[int, list[int]] = {}
    for i in range(n):
        out.setdefault(find(i), []).append(i)
    return list(out.values())


@functools.lru_cache(maxsize=16)
def text_groups(pdf_abspath: str, page_no: int = 0) -> tuple[TextGroup, ...]:
    import pymupdf

    with pymupdf.open(pdf_abspath) as doc:
        lines = _lines(doc[page_no])
    groups = []
    for g0 in _zip(_groups(lines), lines):
        if g0 and g0[0] == -1:  # a two-column list: each line is a record ("PATH A 191' - 0\"")
            for i in g0[1:]:
                _add(groups, [i], lines)
                groups[-1].kind = "list"
            continue
        for g in _chunks(g0, lines):
            _add(groups, g, lines)
    _list_titles(groups)
    titles = [g for g in groups if g.is_title]
    if titles:
        for g in groups:
            if g.is_title:
                continue
            cx, cy = (g.vbox[0] + g.vbox[2]) / 2, (g.vbox[1] + g.vbox[3]) / 2
            cand = [t for t in titles if t.vbox[1] >= cy - 2 and t.vbox[0] <= cx + 20]
            if cand:
                best = min(cand, key=lambda t: (round((t.vbox[1] - cy) / 60), -t.vbox[0]))
                g.view = best.view
    # reading order: top-to-bottom, left-to-right
    groups.sort(key=lambda g: (g.vbox[1] // 40, g.vbox[0]))
    return tuple(groups)


def _zip(groups: list[list[int]], lines) -> list[list[int]]:
    """Two stacked groups side by side whose lines share baselines are one two-column list ("PATH A" | "191' - 0\"",
    "08/15/2019" | "75% CD Set", "A) SLABS-ON-GRADE" | "4000 PSI"): lines are paired by baseline (the joined lines
    are appended to `lines`); unpaired lines stay as they are. Only label/value columns are zipped, not two room tags
    side by side: one column must be mostly values (numbers, dates, "= ...") or the left lines end with ":"."""
    for g in groups:
        g.sort(key=lambda i: (lines[i]["v"][1], lines[i]["v"][0]))

    def yc(i):
        return (lines[i]["v"][1] + lines[i]["v"][3]) / 2

    def valuey(t):  # a short printed value: "4000 PSI", "191' - 0\"", "08/15/2019", "0.45", "= 100 PSF" (not "1. CODE: ...")
        t = t.strip()
        return len(t) <= 24 and bool(VALUE_RE.match(t)) and not re.fullmatch(r"\d{1,2}[.)]", t)  # not an item marker

    ok = [2 <= len(g) <= 40 and all(lines[i]["horiz"] for i in g) for g in groups]
    span = [(min(lines[i]["v"][1] for i in g), max(lines[i]["v"][3] for i in g),
             min(lines[i]["v"][0] for i in g), max(lines[i]["v"][2] for i in g)) if ok[k] else None
            for k, g in enumerate(groups)]
    order = sorted((k for k in range(len(groups)) if ok[k]), key=lambda k: span[k][2])
    done: set[int] = set()
    out = []
    for k, g in enumerate(groups):
        if k in done:
            continue
        if ok[k]:
            h = min(lines[i]["v"][3] - lines[i]["v"][1] for i in g)
            y0, y1, _, right = span[k]
            best = None
            for j in order:
                if j == k or j in done:
                    continue
                o = groups[j]
                oy0, oy1, left, _ = span[j]
                if left - right > 40 * h:
                    break
                if oy1 < y0 or oy0 > y1 or left <= min(lines[i]["v"][2] for i in g):
                    continue
                pairs = []
                for a in g:
                    b = min(o, key=lambda b: abs(yc(a) - yc(b)))
                    # per line: the value starts right of ITS label (a label list inside a note paragraph whose long
                    # lines run past the value column: S-100 'A) SLABS-ON-GRADE ... 4000 PSI', W2 09:45)
                    if abs(yc(a) - yc(b)) < 0.4 * h and 0 < lines[b]["v"][0] - lines[a]["v"][2] <= 40 * h:
                        pairs.append((a, b))
                if len(pairs) < 2 or len(pairs) < 0.7 * min(len(g), len(o)) or len({b for _, b in pairs}) < len(pairs):
                    continue
                vals = max(sum(valuey(lines[b]["t"]) for _, b in pairs), sum(valuey(lines[a]["t"]) for a, _ in pairs))
                keys = sum(lines[a]["t"].rstrip().endswith(":") for a, _ in pairs)
                if max(vals, keys) < 0.7 * len(pairs):
                    continue
                # labels are short ("PATH A", "PUBLIC AREAS:", "Permit Revision #5"); long lines are note text
                if max(sum(len(lines[a]["t"]) for a, _ in pairs), sum(len(lines[b]["t"]) for _, b in pairs)) > 40 * len(pairs):
                    continue
                best = (j, pairs)
                break  # the nearest column to the right
            if best is not None:
                j, pairs = best
                o = groups[j]
                done.add(j)
                if left_edge_cut := [a for a in g if lines[a]["v"][2] >= span[j][2]]:
                    # the label lines sit inside a paragraph: only the run of paired lines becomes the list; the
                    # paragraph lines above/below it stay one group each
                    pa = sorted(g, key=yc)
                    first = min(pa.index(a) for a, _ in pairs)
                    last = max(pa.index(a) for a, _ in pairs)
                    if first > 0:
                        out.append(pa[:first])
                    if last < len(pa) - 1:
                        out.append(pa[last + 1:])
                    g = pa[first:last + 1]
                paired_a = {a: b for a, b in pairs}
                paired_b = set(paired_a.values())
                merged = []
                for a in g:
                    if a in paired_a:
                        la, lb = lines[a], lines[paired_a[a]]
                        lines.append({"t": la["t"] + " " + lb["t"], "horiz": True, "size": max(la["size"], lb["size"]),
                                      "box": tuple(min(la["box"][q], lb["box"][q]) if q < 2 else
                                                   max(la["box"][q], lb["box"][q]) for q in range(4)),
                                      "v": tuple(min(la["v"][q], lb["v"][q]) if q < 2 else max(la["v"][q], lb["v"][q])
                                                 for q in range(4))})
                        merged.append(len(lines) - 1)
                    else:
                        merged.append(a)
                merged += [b for b in o if b not in paired_b]
                merged.sort(key=lambda i: yc(i))
                out.append([-1] + merged)  # -1 marks a zipped list: one row per line
                continue
        out.append(g)
    return out


def _list_titles(groups: list[TextGroup]) -> None:
    """A two-column list's lines get the heading printed just above the list ("EGRESS DATA", "EXIT ROUTE DISTANCE"):
    'EGRESS DATA: PATH A 191' - 0"' (the heading is often the only thing a question names)."""
    lists = [g for g in groups if g.kind == "list"]
    if not lists:
        return
    heads = [g for g in groups if g.kind != "list" and not g.is_title]
    # one list = list lines that touch each other vertically and overlap horizontally
    lists.sort(key=lambda g: g.vbox[1])
    runs: list[list[TextGroup]] = []
    for g in lists:
        h = g.vbox[3] - g.vbox[1]
        for r in runs:
            last = r[-1]
            if 0 <= g.vbox[1] - last.vbox[3] <= 1.2 * h and min(g.vbox[2], last.vbox[2]) > max(g.vbox[0], last.vbox[0]):
                r.append(g)
                break
        else:
            runs.append([g])
    for r in runs:
        top = r[0].vbox
        h = top[3] - top[1]
        above = [x for x in heads if 0 <= top[1] - x.vbox[3] <= 4 * h and
                 min(x.vbox[2], max(g.vbox[2] for g in r)) > max(x.vbox[0], min(g.vbox[0] for g in r))]
        if not above:
            continue
        # the nearest heading, plus one more heading line above it ("EGRESS DATA" over "EXIT ROUTE DISTANCE")
        above.sort(key=lambda x: top[1] - x.vbox[3])
        title = above[0].text
        for x in above[1:2]:
            if 0 <= above[0].vbox[1] - x.vbox[3] <= 4 * h:
                title = x.text + " / " + title
        for g in r:
            g.text = f"{title[:80]}: {g.text}"


def _add(groups: list, g: list[int], lines) -> None:
    ls = [lines[i] for i in g]
    box = (min(x["box"][0] for x in ls), min(x["box"][1] for x in ls), max(x["box"][2] for x in ls),
           max(x["box"][3] for x in ls))
    vbox = (min(x["v"][0] for x in ls), min(x["v"][1] for x in ls), max(x["v"][2] for x in ls),
            max(x["v"][3] for x in ls))
    tg = TextGroup(" / ".join(x["t"] for x in ls), box, vbox, len(ls), max(x["size"] for x in ls))
    if SCALE_RE.search(tg.text) and len(ls) <= 4:
        names = [x for x in ls if not SCALE_RE.search(x["t"]) and not re.fullmatch(r"[\w.]{1,4}", x["t"])
                 and re.search(r"[A-Za-z]{3}", x["t"])]
        if names:
            tg.is_title = True
            tg.view = max(names, key=lambda x: (x["size"], len(x["t"])))["t"]
    groups.append(tg)
