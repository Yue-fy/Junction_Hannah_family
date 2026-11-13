"""The floor: answer with the most common train-split answer for the question's template.

Counts: mode per template. Areas/lengths/volumes: median per template. Text: mode per template.
Falls back to (source, type), then type. Evidence is empty: this solver proves nothing.
"""

from __future__ import annotations

import collections
import statistics
import threading

from stoa.contract import Answer
from stoa.data import source_of, template_of
from stoa.solvers import register
from stoa.solvers.base import BaseSolver


@register("dummy")
class DummySolver(BaseSolver):
    def __init__(self, split: str = "train", **kwargs):
        super().__init__(**kwargs)
        self.split = split
        self._lock = threading.Lock()
        self._tables = None

    def _build(self):
        from stoa.eval.splits import load_split

        by_tpl, by_src_type, by_type = (collections.defaultdict(list) for _ in range(3))
        types = {}
        for q in load_split(self.split):
            t = template_of(q.question)
            by_tpl[t].append((q.answer, q.unit))
            by_src_type[(q.source, q.type)].append((q.answer, q.unit))
            by_type[q.type].append((q.answer, q.unit))
            types[t] = q.type

        def best(rows, qtype):
            unit = collections.Counter(u for _, u in rows).most_common(1)[0][0]
            vals = [v for v, u in rows if u == unit]
            if qtype in ("area", "length", "volume"):
                nums = [v for v in vals if isinstance(v, (int, float))]
                if nums:
                    return statistics.median(nums), unit, len(rows)
            return collections.Counter(vals).most_common(1)[0][0], unit, len(rows)

        self._tables = (
            {t: best(r, types[t]) for t, r in by_tpl.items()},
            {k: best(r, k[1]) for k, r in by_src_type.items()},
            {k: best(r, k) for k, r in by_type.items()},
            types,
        )

    def solve(self, path: str, question: str) -> Answer:
        with self._lock:
            if self._tables is None:
                self._build()
        tpl_t, src_t, type_t, types = self._tables
        t = template_of(question)
        if t in tpl_t:
            v, u, n = tpl_t[t]
            return Answer(value=v, unit=u, confidence=0.05, solver=self.name,
                          trace=[f"template seen {n}x in {self.split}", "answer = mode/median for template"])
        qtype = types.get(t) or ("count" if any(w in question.lower() for w in ("how many", "kuinka monta", "wie viele")) else "area")
        key = (source_of(path), qtype)
        if key in src_t:
            v, u, n = src_t[key]
            return Answer(value=v, unit=u, confidence=0.01, solver=self.name,
                          trace=[f"unseen template; fallback to {key} mode over {n}"])
        if qtype in type_t:
            v, u, n = type_t[qtype]
            return Answer(value=v, unit=u, confidence=0.01, solver=self.name, trace=[f"fallback to type {qtype}"])
        return self.abstain("no statistics")
