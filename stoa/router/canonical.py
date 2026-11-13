"""Canonical English question for an intent, so solvers that match known templates also answer translations
and paraphrases ("normalise, then solve").

    canonical("swiss_dwellings", parse("Wie viele Fenster sind auf diesem Grundriss zu sehen?"))
    -> "How many windows are drawn on this floor plan?"

Keys without filters use the most common English TRAIN question of that (source, key). Keys with filters
(room number, label, apartment, storey, model, room name) use the generators below, which follow the
dataset's own English wording. Returns None when there is no canonical form (unknown target, no train data).
"""

from __future__ import annotations

import collections
import functools
import re

from stoa.data import template_of
from stoa.router.intent import Intent, parse

PLURAL = {"window": "windows", "door": "doors", "room": "rooms (spaces)", "stair": "stairs", "wall": "walls",
          "column": "columns", "beam": "beams", "slab": "slabs", "sanitary": "sanitary fixtures",
          "light": "light fixtures", "furniture": "furniture items"}
_EN = re.compile(r"^\s*(how|what|which|is|are|does|do|count)\b", re.I)


@functools.lru_cache(maxsize=1)
def _plain_templates() -> dict[tuple[str, str], str]:
    """(source, key) -> most common English train question, for keys without filters."""
    from stoa.eval.splits import load_split

    cnt: dict[tuple[str, str], collections.Counter] = collections.defaultdict(collections.Counter)
    seen: dict[str, Intent] = {}
    for q in load_split("train"):
        if q.source == "ifc_bench" or not _EN.match(q.question):
            continue
        t = template_of(q.question)
        it = seen.get(t) or seen.setdefault(t, parse(q.question))
        if not it.filters and it.target != "unknown":
            cnt[(q.source, it.key)][q.question] += 1
    return {k: c.most_common(1)[0][0] for k, c in cnt.items()}


def canonical(source: str, it: Intent) -> str | None:
    f = it.filters
    if it.target == "unknown":
        return None
    if source == "swiss_dwellings":
        if it.key == "area:room:room" and f.get("room_no"):
            lab = f.get("label") or f.get("room")
            return (f"What is the net floor area of room {f['room_no']} ('{lab}') in m²?" if lab
                    else f"What is the net floor area of room {f['room_no']} in m²?")
        if it.key == "area:apartment:apartment" and f.get("apartment"):
            return (f"What is the net floor area of apartment {f['apartment']} in m², summing all its rooms except "
                    "balconies, loggias, terraces and other outdoor spaces?")
        if it.key == "area:room:label_total" and f.get("label"):
            return f"What is the total net area in m² of all rooms labelled '{f['label']}' on this floor?"
        if it.key == "count:room:label" and f.get("label"):
            return f"How many rooms labelled '{f['label']}' are there on this floor?"
    if source == "ifc_models":
        st, plural = f.get("storey"), PLURAL.get(it.target, it.target + "s")
        if it.key == "area:room:room" and f.get("room") and st:
            return f"What is the net floor area of the room '{f['room']}' on '{st}', in m²?"
        if it.scope == "storey" and it.task == "count" and st:
            return f"How many {plural} are shown on the floor plan of '{st}'?"
        if it.scope == "model" and it.task == "count" and f.get("model"):
            return f"How many {plural} are there in the model '{f['model']}'?"
        if it.scope == "storey_total" and st:
            if it.key == "area:room:storey_total":
                return f"What is the total net floor area of all rooms (spaces) on '{st}', in m²?"
            if it.key == "area:wall:storey_total":
                return f"What is the total net side area of all walls on '{st}', in m²?"
            if it.key == "volume:wall:storey_total":
                return f"What is the total net volume of all walls on '{st}', in m³?"
            if it.key == "volume:slab:storey_total":
                return f"What is the total net volume of all slabs on '{st}', in m³?"
            if it.key == "length:wall:storey_total":
                return f"What is the total length of all walls on '{st}', in metres?"
    if not f:
        return _plain_templates().get((source, it.key))
    return None
