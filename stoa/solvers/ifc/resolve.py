"""Resolve names from a question against a model: storeys, rooms (IfcSpace), the model/project itself.

exact -> normalised (accent/case/punctuation folded) -> fuzzy (rapidfuzz). Every match returns a score and
the method, so the solver can put "matched storey '2.korrus' -> '2. korrus' (normalised)" in the trace and
lower its confidence for fuzzy matches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from stoa.solvers.ifc.index import Element, IfcIndex, Storey
from stoa.solvers.ifc.parse import fold


def norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", fold(s or ""))


@dataclass
class Match:
    obj: object  # Storey | Element | str (model name)
    label: str  # the string we matched against
    score: float  # 0..100
    method: str  # exact | normalised | fuzzy

    @property
    def guid(self) -> str | None:
        return getattr(self.obj, "guid", None)


def _best(query: str, candidates: list[tuple[object, str]], cutoff: float = 80.0) -> Match | None:
    if not query or not candidates:
        return None
    for obj, lab in candidates:
        if lab == query:
            return Match(obj, lab, 100.0, "exact")
    nq = norm(query)
    hits = [(obj, lab) for obj, lab in candidates if norm(lab) == nq and nq]
    if hits:
        return Match(hits[0][0], hits[0][1], 99.0, "normalised")
    from rapidfuzz import fuzz

    best = None
    for obj, lab in candidates:
        s = fuzz.ratio(nq, norm(lab))
        if best is None or s > best.score:
            best = Match(obj, lab, float(s), "fuzzy")
    return best if best and best.score >= cutoff else None


def storey_labels(s: Storey) -> list[str]:
    out = [s.name]
    if s.long_name and s.long_name != s.name:
        out.append(s.long_name)
    return [x for x in out if x]


def match_storey(idx: IfcIndex, name: str, cutoff: float = 80.0) -> Match | None:
    cands = [(s, lab) for s in idx.storeys for lab in storey_labels(s)]
    return _best(name, cands, cutoff)


def space_labels(e: Element) -> list[str]:
    n, ln = (e.name or "").strip(), (e.long_name or "").strip()
    out = []
    if ln and n:
        out += [f"{ln} ({n})", f"{n} ({ln})", f"{n} {ln}", f"{ln} {n}"]
    out += [x for x in (ln, n) if x]
    return out


def match_space(idx: IfcIndex, name: str, storey_guid: str | None = None, cutoff: float = 85.0) -> list[Match]:
    """All spaces matching `name` (several spaces can share a label), restricted to a storey if given.
    Returns the best-scoring group (same label score)."""
    spaces = [e for e in idx.elements.values() if e.cls == "IfcSpace"]
    if storey_guid:
        on = [e for e in spaces if e.storey == storey_guid]
        spaces = on or spaces
    cands = [(e, lab) for e in spaces for lab in space_labels(e)]
    best = _best(name, cands, cutoff)
    if best is None:
        return []
    # every space with an equally good label (duplicates like 'Bedroom (B1)' twice are rare but exist)
    group = []
    for e in spaces:
        m = _best(name, [(e, lab) for lab in space_labels(e)], cutoff)
        if m and m.score >= best.score - 1e-6:
            group.append(m)
    return group or [best]


def model_labels(idx: IfcIndex) -> list[str]:
    out = [x for x in (idx.project_name, idx.project_long_name, *idx.building_names) if x]
    return out


def match_model(idx: IfcIndex, name: str, cutoff: float = 70.0) -> Match | None:
    return _best(name, [(idx.path, lab) for lab in model_labels(idx)], cutoff)
