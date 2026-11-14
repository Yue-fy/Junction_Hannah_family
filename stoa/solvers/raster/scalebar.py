"""Graphic scale bars on raster drawings -> pixels per unit (ft, m, ...), read from the text layer's number labels.

Scans have no units: a written scale note (1/4" = 1'-0", 1:100) needs the scan's DPI to become px per foot, but a
GRAPHIC scale bar ("0 5 10 20 FEET" next to a striped bar) is printed on the sheet and survives any rescaling. Its
number labels sit at their ticks, so a straight-line fit of each label's x position against its value gives px per
unit, and the fit's residual says whether the labels really lie on one linear bar.

    bars(path)            -> [Bar(unit, px_per_unit, labels, box, residual, source)]  (cached text layer; no new call
                             when the labels were read as separate texts; one small crop re-read per bar whose labels
                             were read as ONE line, e.g. '0 10 20 40 FEET')
    best_bar(path, unit)  -> the most reliable bar (prefers the given unit family)
    to_units(px, bar)     -> a pixel length in the bar's unit;  meters(px, bar) -> in metres
    Bar.evidence(path)    -> Evidence boxes on the bar's labels (so a reader can check the reading in seconds)

Self-check (no gold needed): sheets with a FEET and a METERS bar must give px/m / px/ft = 3.2808.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from stoa import llm
from stoa.contract import Evidence
from stoa.solvers.raster import textlayer as T

# unit words (after upper-casing) -> canonical unit; metres per unit
UNIT_M = {"ft": 0.3048, "m": 1.0, "cm": 0.01, "km": 1000.0, "mi": 1609.344, "yd": 0.9144, "in": 0.0254,
          "fot": 0.2969, "aln": 0.5938}  # fot / aln: Swedish-Finnish foot and ell (pre-metric Nordic drawings)
_UNIT_WORDS = [
    ("ft", r"FEET|FOOT|FT|PIEDS?|PIES|FUSS|FUß"), ("m", r"METERS?|METRES?|MÈTRES?|METRI|METROS?|MTR|M\.?T\.?R|METRIA|M"),
    ("cm", r"CM"), ("km", r"KM|KILOMET(?:ER|RE)S?"), ("mi", r"MILES?"), ("yd", r"YARDS?|YDS?"),
    ("in", r"INCHES|INCH"), ("fot", r"FOT|FOTT|JALKAA|JALK"), ("aln", r"ALN|ALNAR|KYYNÄRÄÄ|KYYNARAA")]
_UNIT_RE = re.compile(r"(?<![A-ZÀ-Ý])(" + "|".join(f"(?P<{u}>{p})" for u, p in _UNIT_WORDS) + r")\.?(?![A-ZÀ-Ý])")
# one bar label: a number, optionally followed by a unit ('20', '20.', '80. M.', '50 Meter', "100'")
_LABEL = re.compile(r"^\s*(\d{1,5}(?:[.,]\d+)?)\s*\.?\s*([A-Za-zÀ-ÿ.'’ ]{0,12})\s*$")
# a whole bar read as ONE line: '0 10 20 40 60 80 FEET', '0 3 6 9 15 25 m.'
_ONE_LINE = re.compile(r"^\s*(?:\d{1,4}\s+)*0\s+(?:\d{1,5}(?:[.,]\d+)?[\s.]+){1,}\s*\d{0,5}\s*[A-Za-zÀ-ÿ.'’ ]{0,12}$")

REREAD_PROMPT = ("This crop shows the graphic scale bar of a technical drawing: a bar with number labels (like 0 5 10 "
                 "20) and a unit. Give the box of EVERY number label SEPARATELY, one entry per number, from left to "
                 'right: [{"bbox_2d": [x1, y1, x2, y2], "text": "<the number>"}]. Coordinates are 0-1000 relative to '
                 "this image.")


def unit_of(text: str) -> str | None:
    """Canonical unit of a word/line ('FEET' -> ft, 'Meter.' -> m, "100'" -> ft), None if none."""
    t = text.upper().replace("’", "'")
    m = _UNIT_RE.search(t)
    if m:
        return next(u for u, _ in _UNIT_WORDS if m.group(u))
    if re.search(r"\d\s*'\s*$", t):
        return "ft"
    return None


@dataclass
class Bar:
    unit: str | None
    px_per_unit: float
    labels: list[tuple[float, float, list[float]]]  # (value, x_centre_px, box)
    box: list[float]
    residual: float  # max |fit - x| in px
    source: str  # "layer" (labels read as separate texts) | "reread" (one-line bar re-read in a crop)
    unit_text: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def span_units(self) -> float:
        return self.labels[-1][0] - self.labels[0][0]

    @property
    def px_per_m(self) -> float | None:
        return self.px_per_unit / UNIT_M[self.unit] if self.unit in UNIT_M else None

    def describe(self) -> str:
        vals = " ".join(f"{v:g}" for v, _, _ in self.labels)
        u = self.unit or "unknown unit"
        return (f"graphic scale bar '{vals} {self.unit_text or u}' at x {self.box[0]:.0f}-{self.box[2]:.0f}, "
                f"y {self.box[1]:.0f}-{self.box[3]:.0f} px: {self.px_per_unit:.2f} px per {u}"
                f" (fit residual {self.residual:.1f} px over {self.labels[-1][1] - self.labels[0][1]:.0f} px)")

    def evidence(self, path: str) -> list[Evidence]:
        vals = " ".join(f"{v:g}" for v, _, _ in self.labels)
        return [Evidence(file=path, page=0, bbox=[round(c, 1) for c in self.box], bbox_space="image_px",
                         note=f"graphic scale bar {vals} {self.unit or ''}: {self.px_per_unit:.2f} px per "
                              f"{self.unit or 'unit'}")]


def _fit(vals: list[float], xs: list[float]) -> tuple[float, float, float]:
    """Least squares x = a + b * v -> (b, a, max residual)."""
    mv, mx = statistics.fmean(vals), statistics.fmean(xs)
    sv = sum((v - mv) ** 2 for v in vals)
    b = sum((v - mv) * (x - mx) for v, x in zip(vals, xs)) / sv if sv else 0.0
    a = mx - b * mv
    return b, a, max(abs(a + b * v - x) for v, x in zip(vals, xs))


def _runs(row: list[tuple[float, T.TextItem]]) -> list[list[tuple[float, T.TextItem]]]:
    """Split a row (sorted by x) into runs of strictly increasing values; labels LEFT of a 0 that decrease towards it
    (a subdivided first segment, '10 5 0 10 20') get negative values."""
    vals = [v for v, _ in row]
    if 0.0 in vals:
        z = k = vals.index(0.0)
        while k > 0 and vals[k - 1] > vals[k]:
            k -= 1
        row = [(-v, it) if k <= i < z else (v, it) for i, (v, it) in enumerate(row)]
    out, cur = [], [row[0]]
    for p in row[1:]:
        if p[0] > cur[-1][0]:
            cur.append(p)
        else:
            out.append(cur)
            cur = [p]
    out.append(cur)
    return out


def _bars_from_items(items: list[T.TextItem], all_items: list[T.TextItem], source: str,
                     unit_hint: tuple[str | None, str] = (None, "")) -> list[Bar]:
    nums = []
    for it in items:
        m = _LABEL.match(it.text)
        if not m:
            continue
        tail = m.group(2).strip()
        if tail and unit_of(tail) is None:
            continue
        nums.append((float(m.group(1).replace(",", ".")), it, unit_of(tail) if tail else None))
    used: set[int] = set()
    bars: list[Bar] = []
    nums.sort(key=lambda t: t[1].cy)
    for i, (v0, a, _) in enumerate(nums):
        if id(a) in used:
            continue
        ha = a.box[3] - a.box[1]
        row = [(v, it, u) for v, it, u in nums
               if abs(it.cy - a.cy) < 0.6 * max(ha, it.box[3] - it.box[1]) and id(it) not in used
               and 0.5 < (it.box[3] - it.box[1]) / max(ha, 1e-6) < 2.0]
        row.sort(key=lambda t: t[1].cx)
        if len(row) < 2:
            continue
        units = {id(it): u for _, it, u in row}
        for run0 in _runs([(v, it) for v, it, _ in row]):
            for run in (run0, [p for p in run0 if p[0] >= 0]):
                if len(run) < 2 or (run is not run0 and len(run) == len(run0)):
                    continue
                vals, xs = [v for v, _ in run], [it.cx for _, it in run]
                h = statistics.median(it.box[3] - it.box[1] for _, it in run)
                span = xs[-1] - xs[0]
                # labels on one bar: no huge gaps relative to the label size, and the values start at (or cross) 0
                gaps = [b - a_ for a_, b in zip(xs, xs[1:])]
                if min(vals) > 0 or span < 4 * h or max(gaps) > 40 * h:
                    continue
                b, a_, res = _fit(vals, xs)
                if b <= 0 or res > max(3.0, 0.03 * span):
                    continue
                # unit: on a label ('20 m'), else the nearest unit word around the row, else the caller's hint
                unit, utext = next(((units[id(it)], it.text) for _, it in run if units.get(id(it))), (None, ""))
                if unit is None:
                    x0, x1 = run[0][1].box[0], run[-1][1].box[2]
                    cands = []
                    for it in all_items:
                        u = unit_of(it.text)
                        if u is None or _LABEL.match(it.text) and not it.text.strip()[-1:].isalpha():
                            continue
                        if len(it.text) > 40 or any(it is r for _, r in run):
                            continue
                        dy = abs(it.cy - run[0][1].cy)
                        dx = max(0.0, x0 - it.box[2], it.box[0] - x1)
                        if dy < 5 * h and dx < 15 * h:
                            cands.append((dy + dx, u, it.text))
                    if cands:
                        _, unit, utext = min(cands)
                    else:
                        unit, utext = unit_hint
                if len(run) == 2 and unit is None:  # a 2-label bar needs a unit
                    continue
                box = [min(it.box[0] for _, it in run), min(it.box[1] for _, it in run),
                       max(it.box[2] for _, it in run), max(it.box[3] for _, it in run)]
                bars.append(Bar(unit=unit, px_per_unit=b, labels=[(v, it.cx, it.box) for v, it in run], box=box,
                                residual=res, source=source, unit_text=utext))
                used.update(id(it) for _, it in run)
                break
    return bars


def _reread(path: str, it: T.TextItem, size: tuple[int, int], backend: str) -> list[T.TextItem]:
    """A bar read as one text line: crop around it, upscale, ask for one box per number label."""
    W, H = size
    w, h = it.box[2] - it.box[0], it.box[3] - it.box[1]
    x0, x1 = max(0, it.box[0] - 0.15 * w), min(W, it.box[2] + 0.15 * w)
    y0, y1 = max(0, it.box[1] - 2.5 * h), min(H, it.box[3] + 2.5 * h)
    img = Image.open(T._abspath(path)).convert("RGB").crop((round(x0), round(y0), round(x1), round(y1)))
    s = min(4.0, 1400 / max(img.size))
    if s > 1.05:
        img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    r = llm.chat(REREAD_PROMPT, images=[img], backend=backend, max_tokens=600, cache=True,
                 max_pixels=1600 * 1600, max_side=1600)
    items = T.parse_items(r.text, round(x1) - round(x0), round(y1) - round(y0), max_repeat=12)
    for i in items:
        i.box = [i.box[0] + round(x0), i.box[1] + round(y0), i.box[2] + round(x0), i.box[3] + round(y0)]
    return items


def snap(path: str, bar: Bar, img: Image.Image | None = None) -> Bar:
    """Measure the DRAWN bar instead of trusting the VLM's label boxes (they are often evenly spaced guesses, 10% off
    on small digits): in a band just below (or above) the labels, the longest horizontal run of dark columns is the
    bar; its ends sit at the first and last label. px/unit = run length / value span, if both ends lie within about a
    label's width of the first/last label centre; otherwise the label fit stays (marked approximate)."""
    try:
        g = np.asarray((img or Image.open(T._abspath(path))).convert("L"), dtype=np.uint8)
    except OSError:
        return bar
    H, W = g.shape
    h = statistics.median(b[3] - b[1] for _, _, b in bar.labels)
    lw = statistics.median(b[2] - b[0] for _, _, b in bar.labels)
    (v0, x0, _), (v1, x1, _) = bar.labels[0], bar.labels[-1]
    xa, xb = int(max(0, x0 - 3 * h - lw)), int(min(W, x1 + 3 * h + lw))
    thr = min(160, int(np.percentile(g[int(bar.box[1]):int(bar.box[3]) + 1, xa:xb], 5)) + 60) if xb > xa else 160
    best = None
    for side in ("below", "above"):
        if side == "below":
            ya, yb = int(bar.box[3] + 1), int(min(H, bar.box[3] + 2.5 * h + 2))
        else:
            ya, yb = int(max(0, bar.box[1] - 2.5 * h - 2)), int(bar.box[1] - 1)
        if yb - ya < 2:
            continue
        band = g[ya:yb, xa:xb] < thr
        rows = band.sum(axis=1)
        # rows dark over a good part of the label span = the bar's lines/fill (a stepped HABS bar alternates between
        # two rows, so each covers ~half); rows that run on through both margins are a frame or separator line
        span = max(1.0, x1 - x0)
        ml, mr = int(max(1, x0 - lw - xa)), int(max(1, xb - (x1 + lw)))
        through = (band[:, :ml].mean(axis=1) > 0.5) & (band[:, -mr:].mean(axis=1) > 0.5)
        good = (rows >= 0.2 * span) & ~through
        # the bar is the first block of rows next to the labels: stop at the first blank row after it
        order = range(len(rows)) if side == "below" else range(len(rows) - 1, -1, -1)
        seen = False
        for r in order:
            if seen and rows[r] < 3:
                good[r:] = False if side == "below" else good[r:]
                if side == "above":
                    good[:r + 1] = False
                break
            seen = seen or bool(good[r])
        if not good.any():
            continue
        cols = band[good].any(axis=0)
        # longest run of dark columns, tolerating gaps of <= 2 px
        runs, start, gap = [], None, 0
        for i, c in enumerate(np.append(cols, False)):
            if c:
                if start is None:
                    start = i
                gap, last = 0, i
            elif start is not None:
                gap += 1
                if gap > 2 or i == len(cols):
                    runs.append((start, last))
                    start, gap = None, 0
        if not runs:
            continue
        ra, rb = max(runs, key=lambda r: r[1] - r[0])
        ra, rb = ra + xa, rb + xa
        tol = max(lw + h, 0.12 * span)  # VLM label boxes can be ~10% off; the drawn ends are the measurement
        if abs(ra - x0) <= tol and abs(rb - x1) <= tol and (best is None or rb - ra > best[1] - best[0]):
            best = (ra, rb + 1, side, ya, yb)
    if best is None:
        bar.notes.append("drawn bar not found next to the labels: px/unit from the label positions (approximate)")
        return bar
    ra, rb, side, ya, yb = best
    ppu = (rb - ra) / (v1 - v0)
    bar.notes.append(f"drawn bar {side} the labels: x {ra}-{rb} px for {v0:g}-{v1:g} -> {ppu:.2f} px/unit "
                     f"(label fit said {bar.px_per_unit:.2f})")
    bar.px_per_unit, bar.source = ppu, bar.source + "+drawn"
    bar.box = [float(min(ra, bar.box[0])), float(min(ya, bar.box[1])), float(max(rb, bar.box[2])),
               float(max(yb, bar.box[3]))]
    return bar


_CACHE: dict[str, list[Bar]] = {}


def bars(path: str, backend: str = "local", reread: bool = True, layer: T.TextLayer | None = None) -> list[Bar]:
    """All graphic scale bars of a raster drawing, best first (more labels, smaller relative residual)."""
    key = f"{path}|{backend}|{reread}"
    if key in _CACHE:
        return _CACHE[key]
    tl = layer or T.text_layer(path, backend=backend)
    out = _bars_from_items(tl.items, tl.items, "layer")
    try:
        img = Image.open(T._abspath(path))
        img.load()
    except OSError:
        img = None
    if reread:
        covered = [b.box for b in out]
        for it in tl.items:
            if not _ONE_LINE.match(it.text) or len(re.findall(r"\d+", it.text)) < 3:
                continue
            if any(T._iou(it.box, c) > 0.2 for c in covered):
                continue
            u = unit_of(re.sub(r"[\d.,\s]+", " ", it.text))
            sub = _reread(path, it, tl.size, backend)
            got = _bars_from_items(sub, sub, "reread", unit_hint=(u, it.text))
            # the crop may also hold a neighbouring bar (FEET over METERS): keep the row of THIS line
            got.sort(key=lambda b: abs((b.box[1] + b.box[3]) / 2 - it.cy))
            for b in got:
                b.notes.append(f"re-read of the one-line label '{it.text}'")
            out += got[:1]
    if img is not None:
        out = [snap(path, b, img) for b in out]
        if reread:  # labels misread (a missed '10', evenly spaced guesses): re-read the bar's crop, snap again
            for k, b in enumerate(out):
                if "+drawn" in b.source:
                    continue
                w = b.box[2] - b.box[0]  # labels the text layer missed are usually the larger values, on the right
                pseudo = T.TextItem(" ".join(f"{v:g}" for v, _, _ in b.labels),
                                    [max(0.0, b.box[0] - 0.3 * w), b.box[1], min(tl.size[0], b.box[2] + w), b.box[3]])
                sub = _reread(path, pseudo, tl.size, backend)
                got = [snap(path, x, img) for x in _bars_from_items(sub, sub, "reread", (b.unit, b.unit_text))]
                got = [x for x in got if "+drawn" in x.source]
                got.sort(key=lambda x: abs((x.labels[0][2][1] + x.labels[0][2][3]) / 2 - pseudo.cy))
                if got:
                    got[0].unit, got[0].unit_text = b.unit or got[0].unit, b.unit_text or got[0].unit_text
                    got[0].notes.insert(0, "labels re-read in a 4x crop (the text layer's label boxes did not fit "
                                           "the drawn bar)")
                    out[k] = got[0]
    _resolve_ft_m(out)
    _resolve_unknown(out, tl)
    out.sort(key=lambda b: (-len(b.labels), b.residual / max(1.0, b.labels[-1][1] - b.labels[0][1])))
    _CACHE[key] = out
    return out


def _resolve_ft_m(bs: list[Bar]) -> None:
    """HABS-style sheets print a FEET and a METERS bar for the same view, with both unit words close to both bars.
    If the px ratio of two nearby bars is 3.2808 (1 m = 3.2808 ft), the denser bar IS the metre bar."""
    for i, a in enumerate(bs):
        for b in bs[i + 1:]:
            if {a.unit, b.unit} - {"ft", "m", None}:
                continue
            near = abs(a.box[1] - b.box[1]) < 12 * (a.box[3] - a.box[1] + b.box[3] - b.box[1])
            r = max(a.px_per_unit, b.px_per_unit) / min(a.px_per_unit, b.px_per_unit)
            if near and abs(r / 3.2808 - 1) <= 0.03:
                hi, lo = (a, b) if a.px_per_unit > b.px_per_unit else (b, a)
                if (hi.unit, lo.unit) != ("m", "ft"):
                    for x, u in ((hi, "m"), (lo, "ft")):
                        if x.unit != u:
                            x.notes.append(f"unit {x.unit} -> {u}: the pair's px ratio {r:.3f} = 1 m / 1 ft")
                            x.unit = u


# paper widths in mm (long side, short side) for a scale note that names the sheet size: '1:200 (A3)'
_PAPER = {"A0": (1189, 841), "A1": (841, 594), "A2": (594, 420), "A3": (420, 297), "A4": (297, 210)}
_METRIC = re.compile(r"\bm²|\bm2\b|\bmetern?\b|\bmeters?\b|\bmetres?\b|\bmètres?\b|\bmetri\b|\bmetros?\b", re.I)
_IMPERIAL = re.compile(r"\bfeet\b|\bfoot\b|\bsq\.? ?ft\b|\d+'\s*-?\s*\d+\"|\binches\b", re.I)


def _resolve_unknown(bs: list[Bar], tl: T.TextLayer) -> None:
    """A bar whose unit word was not read ('0 2 4 10' with the 'm' missed): (1) the scale note x the paper size it
    names ('1:200 (A3)': 420 mm across 2480 px at 1:200 = 29.5 px/m) decides m vs ft when the bar fits one within 5%;
    (2) else a sheet whose texts are metric (m², 'Masse in Metern') and never imperial -> m."""
    unk = [b for b in bs if b.unit is None]
    if not unk:
        return
    W, H = tl.size
    text = tl.text()
    expect = []
    for it in tl.items:
        pm = re.search(r"\b(A[0-4])\b", it.text)
        if not pm:
            continue
        for sc in T.parse_scales(it.text):
            den = sc.get("ratio") or sc.get("denominator")
            if den:
                long_mm = _PAPER[pm.group(1)][0]
                expect.append((max(W, H) / long_mm * 1000 / float(den), f"'{it.text}' on a {max(W, H)} px sheet"))
    for b in unk:
        for ppm, why in expect:
            for u in ("m", "ft"):
                if abs(b.px_per_unit / (ppm * UNIT_M[u]) - 1) <= 0.05:
                    b.unit = u
                    b.notes.append(f"unit not printed with the bar; {why} gives {ppm * UNIT_M[u]:.2f} px per {u}, "
                                   f"the bar {b.px_per_unit:.2f} -> {u}")
                    break
            if b.unit:
                break
        if b.unit is None and _METRIC.search(text) and not _IMPERIAL.search(text):
            b.unit = "m"
            b.notes.append("unit not printed with the bar; the sheet's texts are metric (m², metres) and never "
                           "imperial -> assumed metres")


def best_bar(path: str, prefer: str | None = None, **kw) -> Bar | None:
    bs = [b for b in bars(path, **kw) if b.unit in UNIT_M]
    if prefer:
        bs.sort(key=lambda b: b.unit != prefer)
    return bs[0] if bs else None


def to_units(px: float, bar: Bar) -> float:
    return px / bar.px_per_unit


def meters(px: float, bar: Bar) -> float | None:
    return px / bar.px_per_m if bar.px_per_m else None


def consistency(bs: list[Bar]) -> list[str]:
    """Cross-checks between bars of one sheet: the same length in ft and m bars must agree."""
    out = []
    ms = [b for b in bs if b.px_per_m]
    for i, a in enumerate(ms):
        for b in ms[i + 1:]:
            h = max(a.box[3] - a.box[1], b.box[3] - b.box[1])
            overlap = min(a.box[2], b.box[2]) - max(a.box[0], b.box[0])
            if a.unit != b.unit and abs(a.box[1] - b.box[1]) < 8 * h and overlap > 0:  # stacked: the same view
                d = b.px_per_m / a.px_per_m - 1
                out.append(f"{a.unit} bar vs {b.unit} bar: {100 * d:+.1f}% "
                           + ("✓" if abs(d) <= 0.03 else "✗ (one of the bars is misread)"))
    return out
