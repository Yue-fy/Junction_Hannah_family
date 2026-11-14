"""Compound questions → atomic sub-questions + arithmetic (general reasoning, shown step by step in the trace).

Handled shapes (any language the intent parser knows, English phrasing rules here):
  sum      "How many doors and windows ... in total?" / "toilets, washbasins and bathtubs altogether"
           "combined net floor area of room 1.45 and room 1.20" / "apartments C and B"
  diff     "How many more doors than windows ...?" / "By how many m² is room 1.06 larger than room 1.04?"
  argmax   "Which of the rooms 'A', 'B' and 'C' on 'L' has the largest net floor area?" (text answer)
  max/min  "net floor area of the largest of the rooms 'A', 'B' and 'C' on 'L'"
  exists   "Does this apartment have a sauna?" -> count > 0 -> yes/no
  atleast  "Does this floor plan show at least two WC seats?" -> count >= 2 -> yes/no

`decompose(source, question)` -> Plan(op, subs=[sub-question strings], labels) or None. The pipeline answers each
sub-question with the normal cascade and combines the values; evidence is the union of the parts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from stoa.router.canonical import canonical
from stoa.router.intent import _NEGATION, _QUOTED, _TARGETS, Intent, modifiers, parse

_TOGETHER = re.compile(r"\b(in total|together|altogether|combined|in all|total number|sum of|zusammen|insgesamt|"
                       r"yhteens[aä]|au total|in totale|i alt|totaal)\b", re.I)
# Q 08:21: "How many doors and how many windows are on '1.korrus'?" was summed (101 @ 0.86; gold 46 and 55): two counting
# cues, or "respectively / each / separately", without a total cue -> one count per class
_COUNT_CUE = re.compile(r"\bhow many\b|\bnumber of\b|\bwie viele\b|\bcombien\b|\bquant[ie]\b|\bkuinka monta\b|\bmontako\b|"
                        r"\bhur många\b|\bhoeveel\b|\bmitu\b|\bhvor mange\b", re.I)
_EACH = re.compile(r"\b(respectively|separately|each separately|one by one|for each (?:kind|type|class)|jeweils|"
                   r"respectivement|rispettivamente|vastaavasti|var för sig|respectivamente|elk afzonderlijk)\b", re.I)
_MORE_THAN = re.compile(r"how many more (?P<a>.+?) than (?P<b>.+?)(?: are| is| does| do| on| in|\?|$)", re.I)
_LARGER = re.compile(r"by how (?:many|much) (?:m²|m2|square metres|square meters|ft²)? ?is (?P<a>.+?) (?:larger|bigger|greater) than (?P<b>.+?)(?:\s*\(|\?|$)", re.I)
_SMALLER = re.compile(r"by how (?:many|much) (?:m²|m2|square metres|square meters|ft²)? ?is (?P<a>.+?) smaller than (?P<b>.+?)(?:\s*\(|\?|$)", re.I)
_WHICH_LARGEST = re.compile(r"\bwhich\b.*\b(largest|biggest|smallest|greatest)\b", re.I)
_OF_LARGEST = re.compile(r"\bof the (largest|biggest|smallest) of\b", re.I)
_CMP2 = re.compile(r"\b(?P<w>more|fewer|less|as many)\s+(?P<a>[^?,;]+?)\s+(?:than|as)\s+(?P<b>[^?,;.]+)", re.I)
_EXISTS = re.compile(r"^\s*(does|do|is there|are there|has|have|onko|gibt es|y a-t-il|c'è|har)\b", re.I)
_ROOM_NOS = re.compile(r"\brooms?\s+([A-Z]{0,2}\d+(?:\.\d+)+)(?:\s*\((['‘«„\"][^)]*)\))?", re.I)
_AT_LEAST = re.compile(r"\b(at least|more than|over|mindestens|au moins|v[äa]hint[äa][äa]n)\s+(\d+|one|two|three|four|five|"
                       r"six|zwei|drei|deux|trois|kaksi|kolme)\b", re.I)
_NUMWORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "zwei": 2, "drei": 3, "deux": 2, "trois": 3,
            "kaksi": 2, "kolme": 3}
_APTS = re.compile(r"\bapartments?\s+([A-Z])\s*(?:,|and|&|\+)\s*([A-Z])\b", re.I)


# combined concepts some sources only ask about separately
COMPONENTS = {"shower_bathtub": ["shower", "bathtub"]}


@dataclass
class Plan:
    op: str  # sum | diff | argmax | argmin | max | min | exists | atleast (note = n) | gt | lt | ge (yes/no)
    subs: list[str]
    labels: list[str] = field(default_factory=list)
    unit: str | None = None
    note: str = ""


def _targets_in(text: str) -> list[tuple[int, str]]:
    """All target classes mentioned in text, by position, longest-specific first (no overlaps)."""
    taken: list[tuple[int, int]] = []
    out = []
    for t, rx in _TARGETS:
        for m in rx.finditer(text):
            if any(not (m.end() <= a or m.start() >= b) for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            out.append((m.start(), t))
    return sorted(out)


def _sub_for(source: str, target: str, base: Intent) -> str | None:
    it = Intent(task=base.task, target=target, scope=base.scope, unit=base.unit,
                filters={k: v for k, v in base.filters.items() if k in ("storey", "model", "apartment")}, lang="en")
    return canonical(source, it)


def decompose(source: str, question: str) -> Plan | None:
    q = question.strip()
    from stoa.router.prior import known_template

    if known_template(q):  # a question shape seen in train is atomic: solve it directly
        return None
    base = parse(q)
    if base.filters.get("apartment") and base.task == "count":
        return None  # "doors and windows of apartment C": dxf scopes apartments itself; else the agent asks per part
    qn = _QUOTED.sub(" <q> ", q)
    quoted = [next(g for g in m.groups() if g).strip() for m in _QUOTED.finditer(q)]

    # comparison of two counts asked yes/no (R1 03:46): "Does this apartment have more bedrooms (MH) than bathrooms?"
    # was read as "is there a bedroom?" by the exists branch below
    if base.task in ("yesno", "text"):
        mc = _CMP2.search(_NEGATION.sub(" ", re.sub(r"\([^)]*\)", " ", qn)))
        if mc:
            ta = [t for _, t in _targets_in(mc.group("a")) if t not in ("apartment", "room")]
            tb = [t for _, t in _targets_in(mc.group("b")) if t not in ("apartment", "room")]
            if ta and tb and ta[0] != tb[0]:
                sa = _sub_for(source, ta[0], Intent("count", ta[0], "drawing", "count"))
                sb = _sub_for(source, tb[0], Intent("count", tb[0], "drawing", "count"))
                if sa and sb:
                    op = {"more": "gt", "fewer": "lt", "less": "lt", "as many": "ge"}[mc.group("w").lower()]
                    return Plan(op, [sa, sb], [ta[0], tb[0]], None)

    # exists: "Does this apartment have a sauna?"
    if base.task in ("yesno", "text") and _EXISTS.search(q):
        ts = [t for _, t in _targets_in(_NEGATION.sub(" ", qn)) if t not in ("apartment", "room")]
        if ts:
            sub = _sub_for(source, ts[0], Intent("count", ts[0], "drawing", "count"))
            mt = _AT_LEAST.search(qn)
            if sub and mt:  # "at least two WC seats?" / "more than one bathroom?" -> count >= n
                n = _NUMWORD.get(mt.group(2).lower(), None) if not mt.group(2).isdigit() else int(mt.group(2))
                if n is not None:
                    n = n + 1 if mt.group(1).lower().startswith(("more", "over")) else n
                    return Plan("atleast", [sub], [ts[0]], None, str(n))
            elif sub:
                return Plan("exists", [sub], [ts[0]], None, f"is there at least one {ts[0]}?")

    # diff of counts: "how many more doors than windows"
    m = _MORE_THAN.search(qn)
    if m and base.task == "count":
        ta, tb = _targets_in(m.group("a")), _targets_in(m.group("b"))
        if ta and tb:
            sa, sb = _sub_for(source, ta[0][1], base), _sub_for(source, tb[0][1], base)
            if sa and sb:
                return Plan("diff", [sa, sb], [ta[0][1], tb[0][1]], "count")

    # diff of areas: "By how many m² is room 1.06 larger than room 1.04"
    m = _LARGER.search(q) or _SMALLER.search(q)
    if m:
        ra, rb = _ROOM_NOS.search(m.group("a")), _ROOM_NOS.search(m.group("b"))
        if ra and rb and source == "swiss_dwellings":
            subs = [canonical(source, parse(f"What is the net floor area of room {r.group(1)} in m²?")) for r in (ra, rb)]
            if all(subs):
                op = "diff" if m.re is _LARGER else "rdiff"
                return Plan(op, subs, [f"room {ra.group(1)}", f"room {rb.group(1)}"], "m2")

    # argmax / max over named rooms on a storey (ifc_models style)
    if (_WHICH_LARGEST.search(q) or _OF_LARGEST.search(q)) and len(quoted) >= 3:
        storey = quoted[-1]
        rooms = quoted[:-1]
        word = (_WHICH_LARGEST.search(q) or _OF_LARGEST.search(q)).group(1).lower()
        big = word != "smallest"
        subs = [f"What is the net floor area of the room '{r}' on '{storey}', in m²?" for r in rooms]
        if _WHICH_LARGEST.search(q) and not _OF_LARGEST.search(q):
            return Plan("argmax" if big else "argmin", subs, rooms, None)
        return Plan("max" if big else "min", subs, rooms, "m2")

    # sum of areas: "combined net floor area of room 1.45 ('Zimmer') and room 1.20 ('Küche')"
    if base.task == "area" and _TOGETHER.search(q):
        rs = _ROOM_NOS.findall(q)
        if len(rs) >= 2 and source == "swiss_dwellings":
            subs = []
            for no, lab in rs:
                lab = lab.strip("'‘’«»„“”\" ")
                subs.append(f"What is the net floor area of room {no} ('{lab}') in m²?" if lab
                            else f"What is the net floor area of room {no} in m²?")
            return Plan("sum", subs, [f"room {no}" for no, _ in rs], "m2")
        if len(quoted) >= 3:  # "combined net floor area of the rooms 'A' and 'B' on 'Level 1'"
            storey, rooms = quoted[-1], quoted[:-1]
            return Plan("sum", [f"What is the net floor area of the room '{r}' on '{storey}', in m²?" for r in rooms],
                        rooms, "m2")
        ma = _APTS.search(q)
        if ma:
            subs = [canonical(source, parse(f"What is the net floor area of apartment {a} in m², summing all its rooms "
                                            "except balconies, loggias, terraces and other outdoor spaces?"))
                    for a in ma.groups()]
            if all(subs):
                return Plan("sum", subs, [f"apartment {a}" for a in ma.groups()], "m2")

    # separate counts in any language: two counting cues ("Montako ovea ja montako ikkunaa …", "Wie viele Türen und
    # wie viele Fenster …") or "respectively", and no total cue (Q 08:35: FI -> the agent answered doors only @ 0.95)
    if base.task == "count" and not _TOGETHER.search(q) and not (set(modifiers(q)) & {"avg", "ratio", "share", "diff",
                                                                                         "compare", "threshold"}):
        first = re.sub(r"\([^)]*\)", " ", re.split(r"\?", qn)[0])  # parentheses hold definitions
        if len(_COUNT_CUE.findall(first)) >= 2 or _EACH.search(qn):
            clause = _NEGATION.sub(" ", first)
            ts = []
            for _, t in _targets_in(clause):
                if t not in ts and t not in ("room", "storey", "sanitary"):
                    ts.append(t)
            subs = [_sub_for(source, t, base) for t in ts]
            if len(ts) >= 2 and all(subs):
                return Plan("list", subs, list(ts), "count")
    # sum of counts: "doors and windows in total", "toilets, washbasins and bathtubs altogether"
    if base.task == "count" and (_TOGETHER.search(q) or re.search(r"\b(and|plus)\b", qn, re.I)):
        clause = qn
        mc = re.search(r"\bcounting (.+)", qn, re.I)  # "sanitary fixtures ..., counting toilet seats, sinks ..."
        if mc:
            clause = mc.group(1)
        else:
            clause = re.split(r"\?", qn)[0]  # first sentence: definitions after it are not targets
        clause = _NEGATION.sub(" ", re.sub(r"\([^)]*\)", " ", clause))  # parentheses hold definitions
        ts = []
        for _, t in _targets_in(clause):
            if t not in ts and t not in ("room", "storey") and not (mc and t == "sanitary"):
                ts.append(t)
        first = re.split(r"\?", qn)[0]
        if len(ts) >= 2 and not _TOGETHER.search(q) and (len(_COUNT_CUE.findall(first)) >= 2 or _EACH.search(qn)):
            subs = [_sub_for(source, t, base) for t in ts]
            if all(subs):
                return Plan("list", subs, list(ts), "count")
        if len(ts) >= 2:
            subs, labels = [], []
            for t in ts:
                parts = [t] if _sub_for(source, t, base) else COMPONENTS.get(t, [t])
                for pt in parts:
                    subs.append(_sub_for(source, pt, base))
                    labels.append(pt)
            if all(subs):
                return Plan("sum", subs, labels, "count")
    return None


def _fmt(v: float, unit: str | None) -> str:
    return str(int(round(v))) if unit == "count" else f"{round(v, 2)}"


def combine(plan: Plan, values: list) -> tuple[object, str]:
    """-> (value, readable arithmetic)."""
    lab = plan.labels or [f"part {i + 1}" for i in range(len(values))]
    nums = []
    for v in values:
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            nums.append(None)
    if plan.op == "exists":
        n = nums[0]
        return ("yes" if (n or 0) > 0 else "no"), f"{lab[0]} count = {values[0]} → {'yes' if (n or 0) > 0 else 'no'}"
    if plan.op == "atleast":
        n, k = nums[0], int(plan.note)
        yes = n is not None and n >= k
        return ("yes" if yes else "no"), f"{lab[0]} count = {values[0]} {'≥' if yes else '<'} {k} → {'yes' if yes else 'no'}"
    if plan.op == "list":  # separate answers, one per class (no arithmetic)
        shown = [_fmt(n, plan.unit) if n is not None else str(v) for n, v in zip(nums, values)]
        return "; ".join(f"{lab[i]}: {shown[i]}" for i in range(len(values))), "separate counts, not a sum: " + ", ".join(
            f"{lab[i]} {shown[i]}" for i in range(len(values)))
    if any(n is None for n in nums):
        return None, "a part has no numeric value"
    if plan.op in ("gt", "lt", "ge"):
        a, b = nums[0], nums[1]
        yes = a > b if plan.op == "gt" else a < b if plan.op == "lt" else a >= b
        sym = {"gt": ">", "lt": "<", "ge": "≥"}[plan.op]
        return ("yes" if yes else "no"), (f"{lab[0]} {values[0]} {sym if yes else 'not ' + sym} {lab[1]} {values[1]} → "
                                         f"{'yes' if yes else 'no'}")
    if plan.op == "sum":
        v = sum(nums)
        expr = " + ".join(f"{lab[i]} {values[i]}" for i in range(len(values))) + f" = {_fmt(v, plan.unit)}"
    elif plan.op in ("diff", "rdiff"):
        v = nums[0] - nums[1] if plan.op == "diff" else nums[1] - nums[0]
        expr = (f"{lab[0]} {values[0]} − {lab[1]} {values[1]} = {_fmt(nums[0] - nums[1], plan.unit)}"
                + (f" (asked the other way round: {_fmt(v, plan.unit)})" if plan.op == "rdiff" else ""))
    elif plan.op in ("max", "min"):
        i = max(range(len(nums)), key=lambda k: nums[k]) if plan.op == "max" else min(range(len(nums)), key=lambda k: nums[k])
        v = nums[i]
        expr = f"{plan.op} of " + ", ".join(f"{lab[k]} {values[k]}" for k in range(len(values))) + f" = {lab[i]} {values[i]}"
    elif plan.op in ("argmax", "argmin"):
        i = max(range(len(nums)), key=lambda k: nums[k]) if plan.op == "argmax" else min(range(len(nums)), key=lambda k: nums[k])
        return lab[i], (f"{'largest' if plan.op == 'argmax' else 'smallest'} of "
                        + ", ".join(f"{lab[k]} {values[k]}" for k in range(len(values))) + f" → {lab[i]}")
    else:
        return None, f"unknown op {plan.op}"
    if plan.unit == "count":
        v = int(round(v))
    else:
        v = round(v, 2)
    return v, expr
