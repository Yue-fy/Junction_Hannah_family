"""The prior: answer with the most common TRAIN answer for this kind of question (S0 D4 last resort).

Registered as `prior` and (for old leaderboard comparability) `dummy`.

Backoff, most specific first (a level is used when it has >= MIN_N train answers):
  1. "keyed" question: numbers -> <N> but quoted names kept (e.g. "rooms labelled 'Küche'")
  2. template (quoted names -> <Q>, numbers -> <N>)
  3. (source, type), then type
Counts/text: mode. Areas/lengths/volumes: median.
confidence = how often that answer was right on train (mode share, or share of answers within 2% of the
median), so the router can compare it with other solvers. Never refuses for numeric questions.
"""

from __future__ import annotations

import collections
import re
import statistics
import threading

from stoa.contract import Answer
from stoa.data import _NUM, source_of, template_of
from stoa.solvers import register
from stoa.solvers.base import BaseSolver

MIN_N = 20
ASSUMPTION = "no direct evidence: answered with the most common answer for this kind of question in the training data"

_COUNT_RE = re.compile(r"\b(how many|number of|count|kuinka monta|montako|wie viele|combien|quanti|quante|hvor mange|"
                       r"hur många|hoeveel|mitu|cuántos|cuántas)\b", re.I)
_VOL_RE = re.compile(r"(m³|m3\b|volume|volumen|tilavuus|maht)", re.I)
_LEN_RE = re.compile(r"(\blength\b|\blänge\b|\blængde\b|\blengte\b|\bin met(re|er)s?\b|\bin metern\b)", re.I)
_AREA_RE = re.compile(r"(m²|m2\b|ft²|ft2\b|sq ?ft|area|fläche|ala\b|surface|superficie|oppervlakte|areal|pind)", re.I)


def keyed_of(question: str) -> str:
    return re.sub(r"\s+", " ", _NUM.sub("<N>", question.lower())).strip()


def guess_type(question: str) -> str:
    if _VOL_RE.search(question):
        return "volume"
    if _COUNT_RE.search(question):
        return "count"
    if _LEN_RE.search(question):
        return "length"
    if _AREA_RE.search(question):
        return "area"
    return "text"


@register("prior")
class PriorSolver(BaseSolver):
    def __init__(self, split: str = "train", min_n: int = MIN_N, **kwargs):
        super().__init__(**kwargs)
        self.split = split
        self.min_n = int(min_n)
        self._lock = threading.Lock()
        self._tables = None

    def _build(self):
        from stoa.eval.splits import load_split

        levels = {k: collections.defaultdict(list) for k in ("keyed", "tpl", "src_type", "type")}
        types = {}
        for q in load_split(self.split):
            row = (q.answer, q.unit)
            t = template_of(q.question)
            levels["keyed"][keyed_of(q.question)].append(row)
            levels["tpl"][t].append(row)
            levels["src_type"][(q.source, q.type)].append(row)
            levels["type"][q.type].append(row)
            types[t] = q.type

        def best(rows, qtype):
            unit = collections.Counter(u for _, u in rows).most_common(1)[0][0]
            vals = [v for v, u in rows if u == unit]
            if qtype in ("area", "length", "volume"):
                nums = [float(v) for v in vals if isinstance(v, (int, float))]
                if nums:
                    med = statistics.median(nums)
                    hit = sum(1 for v in nums if abs(v - med) <= 0.02 * abs(med)) / len(nums)
                    return med, unit, len(rows), hit
            v, k = collections.Counter(vals).most_common(1)[0]
            return v, unit, len(rows), k / len(vals)

        def qtype_of(key, rows, level):
            if level == "src_type":
                return key[1]
            if level == "type":
                return key
            return types.get(template_of(key) if level == "keyed" else key) or "count"

        self._tables = {lvl: {k: best(r, qtype_of(k, r, lvl)) for k, r in d.items()} for lvl, d in levels.items()}
        self._types = types

    def solve(self, path: str, question: str) -> Answer:
        with self._lock:
            if self._tables is None:
                self._build()
        tb = self._tables
        t = template_of(question)
        qtype = self._types.get(t) or guess_type(question)
        for level, key in (("keyed", keyed_of(question)), ("tpl", t), ("src_type", (source_of(path), qtype)),
                           ("type", qtype)):
            hit = tb[level].get(key)
            if hit and (hit[2] >= self.min_n or level == "type"):
                v, u, n, rate = hit
                if qtype == "text" and level in ("src_type", "type"):
                    break  # a random paragraph from another drawing is worse than nothing
                return Answer(
                    value=v, unit=u, confidence=round(min(0.95, rate), 3), solver=self.name,
                    trace=[f"prior level={level} n={n} train hit rate={rate:.2f}"],
                    assumptions=[ASSUMPTION], missing=["the drawing itself was not analysed"],
                )
        return Answer(value="unknown", unit=None, confidence=0.0, solver=self.name,
                      trace=["no prior for this free-text question"], assumptions=[ASSUMPTION],
                      missing=["the drawing itself was not analysed"])


@register("dummy")
class DummySolver(PriorSolver):
    """Alias kept for leaderboard continuity."""
