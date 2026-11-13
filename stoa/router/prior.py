"""Answer prior per (source, intent key), built from the TRAIN split only (S0 D3/D4).

The prior is the last resort of the cascade (never a bare refusal): the most common train answer for counts,
the median for areas/lengths/volumes, with its own hit rate on train as the calibrated confidence. Keys are
language independent (`stoa.router.intent.Intent.key`), so a Finnish or paraphrased question gets the same
prior as its English twin. Fallbacks: (source, key) -> (any source, key) -> (source, task) -> (task).
"""

from __future__ import annotations

import collections
import statistics
import threading
from dataclasses import dataclass

from stoa.data import template_of
from stoa.router.intent import Intent, parse

_LOCK = threading.Lock()
_TABLE: dict | None = None


@dataclass
class PriorAnswer:
    value: float | int | str
    unit: str | None
    hit_rate: float  # share of train questions with this key that the prior answers correctly
    n: int  # train questions behind it
    level: str  # which fallback level answered ("source+key", "key", "source+task", "task")


def _within(a, b, rel=0.02) -> bool:
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return abs(a - b) <= rel * max(abs(b), 1e-9)


def _best(rows: list[tuple]) -> PriorAnswer | None:
    """rows: (answer, unit, task). Mode for counts/text, median for measures; hit rate on the same rows."""
    if not rows:
        return None
    unit = collections.Counter(u for _, u, _ in rows).most_common(1)[0][0]
    task = collections.Counter(t for _, _, t in rows).most_common(1)[0][0]
    vals = [v for v, u, _ in rows if u == unit]
    if task in ("area", "length", "volume"):
        nums = [float(v) for v in vals if isinstance(v, (int, float))]
        if nums:
            med = statistics.median(nums)
            hit = sum(1 for v in nums if _within(med, v)) / len(rows)
            return PriorAnswer(round(med, 2), unit, hit, len(rows), "")
    v, c = collections.Counter(vals).most_common(1)[0]
    return PriorAnswer(v, unit, c / len(rows), len(rows), "")


def _build() -> dict:
    from stoa.eval.splits import load_split

    by_tpl_intent: dict[str, Intent] = {}
    groups: dict[tuple, list] = collections.defaultdict(list)
    for q in load_split("train"):
        t = template_of(q.question)
        it = by_tpl_intent.get(t)
        if it is None:
            it = by_tpl_intent[t] = parse(q.question)
        row = (q.answer, q.unit, q.type)
        groups[("source+key", q.source, it.key)].append(row)
        groups[("key", "", it.key)].append(row)
        groups[("source+task", q.source, q.type)].append(row)
        groups[("task", "", q.type)].append(row)
    table = {}
    for k, rows in groups.items():
        b = _best(rows)
        if b is not None:
            b.level = k[0]
            table[k] = b
    return table


def table() -> dict:
    global _TABLE
    with _LOCK:
        if _TABLE is None:
            _TABLE = _build()
    return _TABLE


_TEMPLATES: set | None = None


def known_template(question: str) -> bool:
    """True if this question's template (stoa.data.template_of) occurs in the train split."""
    global _TEMPLATES
    with _LOCK:
        if _TEMPLATES is None:
            from stoa.eval.splits import load_split

            _TEMPLATES = {template_of(q.question) for q in load_split("train")}
    return template_of(question) in _TEMPLATES


def lookup(source: str, intent: Intent, min_n: int = 20) -> PriorAnswer | None:
    t = table()
    for k in (("source+key", source, intent.key), ("key", "", intent.key),
              ("source+task", source, intent.task), ("task", "", intent.task)):
        b = t.get(k)
        if b is None:
            continue
        if k[0] in ("source+key", "key") and (intent.target == "unknown" or b.n < min_n):
            continue
        return b
    return None
