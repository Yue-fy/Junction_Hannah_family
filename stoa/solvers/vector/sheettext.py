"""Questions about the printed text of a vector sheet that is NOT a schedule (plans with room/unit tags, life-safety
plans, general notes, title blocks). The 8B model is bad at writing regex/pandas code over free text (fresh probe:
7-10/20, run-to-run swings), but good at pointing at rows. So:

1. retrieve the text rows (pdftext groups + rows of any small rebuilt table) that share words/ids with the question;
2. one LLM call (JSON schema) returns the operation (lookup / count / sum / max / min / mean / none) and the rows it
   uses, each with its label and the value as printed;
3. Python does the arithmetic (count = number of distinct rows, sum/max/... over the printed numbers), checks that
   every value really occurs in its row, and the rows' boxes are the evidence.
"""

from __future__ import annotations

import math
import re
from collections import Counter

STOP = set("""a an the of in on at to for and or is are was were be by with from this that these those what which who
whom how many much does do did have has there their its it as all any each per into than other sheet drawing drawings
plan plans shown listed given printed total number""".split())

SCHEMA = {
    "type": "object",
    "properties": {
        "op": {"type": "string", "enum": ["lookup", "count", "sum", "max", "min", "mean", "none"]},
        "items": {"type": "array", "items": {
            "type": "object",
            "properties": {"row": {"type": "integer"}, "label": {"type": "string"}, "value": {"type": "string"}},
            "required": ["row", "label", "value"]}},
        "answer": {"type": "string"},
        "unit": {"type": "string", "enum": ["count", "ft2", "m2", "ft", "m", "none"]},
    },
    "required": ["op", "items", "answer", "unit"],
}

PROMPT = """Text printed on one construction drawing sheet, one row per text group: a room/unit TAG (its stacked lines
joined with " / "), a note paragraph, a title-block field, or one line of a two-column list. `view` = the drawing
(plan, section, legend) the row sits under; "-" = title block or unknown.

{rows}

Question: {question}

Answer ONLY from these rows. Return JSON with:
- op: "lookup" (one value read from one row), "count" (how many rows match), "sum" / "max" / "min" / "mean" (of a
  number printed in the matching rows), or "none" (these rows do not contain the answer).
- items: lookup -> the one row you read; count -> EVERY matching row; sum/max/min/mean -> EVERY matching row with its
  number. Each item: row (the id), label (the room/unit/item name or number in that row), value (the number or text
  exactly as printed in that row, digits only for numbers, e.g. "27.3", "1102", "S-2").
- answer: the final answer as printed (with its unit, e.g. "3000 PSF", "07/02/2020"); for "which" questions the label.
- unit: "count", "ft2", "m2", "ft", "m", or "none".
When the question names a view or floor (e.g. "basement plan"), only rows of that view match."""


def _toks(s: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+(?:[.\-/][a-z0-9]+)*", s.lower()):
        if w in STOP or len(w) < 2:
            continue
        out.append(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w)
    return out


def retrieve(question: str, rows: list[dict], k: int = 70) -> list[dict]:
    """Rows sharing words with the question (rarer words weigh more; ids/numbers x3), best k, in sheet order."""
    q = set(_toks(question))
    df = Counter(t for r in rows for t in set(_toks(r["text"] + " " + (r.get("view") or ""))))
    n = max(len(rows), 1)
    scored = []
    for i, r in enumerate(rows):
        toks = set(_toks(r["text"] + " " + (r.get("view") or "")))
        sc = 0.0
        for t in q & toks:
            w = math.log(1 + n / df[t])
            sc += w * (3 if re.search(r"\d", t) else 1)
        # prefix matches ("occupan" ~ "occupancy", "studio" ~ "studios")
        for t in q - toks:
            if len(t) >= 5 and any(x.startswith(t[:5]) for x in toks):
                sc += 0.5
        if sc > 0:
            scored.append((sc, i))
    keep = sorted(i for _, i in sorted(scored, reverse=True)[:k])
    return [rows[i] for i in keep]


def _num(s) -> float | None:
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(s))
    if not m:
        return None
    try:
        return float(m.group().replace(",", ""))
    except ValueError:
        return None


def _norm(s: str) -> str:
    return re.sub(r"[\s'\"]", "", str(s).lower())


def ask(question: str, rows: list[dict], backend: str = "local") -> dict:
    """rows: [{"id": int, "view": str|None, "text": str}]. Returns {value, unit, used, op, trace, ok}."""
    from stoa.llm import chat, extract_json

    sel = retrieve(question, rows)
    if not sel:
        return {"value": None, "unit": None, "used": [], "op": "none", "trace": ["no text row shares a word with the "
                                                                                    "question"], "ok": False}
    by_id = {r["id"]: r for r in sel}
    listing = "\n".join(f"[{r['id']}] view={r.get('view') or '-'} | {r['text'][:400]}" for r in sel)
    msgs = [{"role": "user", "content": PROMPT.format(rows=listing, question=question)}]
    res = chat(msgs, backend=backend, max_tokens=900, temperature=0.0, json_schema=SCHEMA)
    js = extract_json(res.text) or {}
    retried = False
    if (js.get("op") or "none") == "none" or not any(isinstance(it, dict) and it.get("row") in by_id
                                                     for it in js.get("items") or []):
        # the 8B model often says "none" for a total over many tags; one nudge (cost: one more call, only here)
        retried = True
        msgs += [{"role": "assistant", "content": res.text},
                 {"role": "user", "content": "Look again: the answer is usually in these rows. A 'total' or 'how many' "
                  "over several rooms/items is op sum or count with EVERY matching row listed as an item (row id, "
                  "label, the printed number). A single value is op lookup with the row it is printed in. Use op "
                  "none only if no row is related."}]
        res2 = chat(msgs, backend=backend, max_tokens=900, temperature=0.0, json_schema=SCHEMA)
        js = extract_json(res2.text) or js
    op = js.get("op") or "none"
    unit = js.get("unit")
    unit = None if unit in (None, "none", "") else unit
    items = [it for it in js.get("items") or [] if isinstance(it, dict) and it.get("row") in by_id]
    seen, uniq = set(), []
    for it in items:
        if it["row"] not in seen:
            seen.add(it["row"])
            uniq.append(it)
    items = uniq
    trace = [f"sheet text: {len(sel)} of {len(rows)} text rows retrieved; model op={op}{' (2nd try)' if retried else ''}, "
             f"{len(items)} rows: "
             + "; ".join(f"[{it['row']}] {it.get('label')}={it.get('value')}" for it in items[:30])]
    # every value must be printed in its row (a value the model made up or took from elsewhere is not evidence)
    bad = [it for it in items if _norm(it.get("value", "")) and _norm(it.get("value", "")) not in _norm(by_id[it["row"]]["text"])]
    if bad:
        trace.append("values not found in their rows: " + "; ".join(f"[{it['row']}] {it.get('value')}" for it in bad))
    out = {"value": None, "unit": unit, "used": [it["row"] for it in items], "op": op, "trace": trace,
           "ok": not bad, "items": items}
    which = re.search(r"\bwhich\b|\bwhat (?:room|unit|space|path)\b", question, re.I)
    if op == "none":
        return out
    if not items:
        # an answer without a cited row: kept as a low-confidence reading (Stoa: a bare refusal is not useful)
        ans = js.get("answer")
        if isinstance(ans, str) and ans.strip() and not re.match(r"(?i)\s*(none|unknown|n/?a|not )", ans):
            out.update(value=ans.strip(), unit=None, ok=False, uncited=True)
            trace.append("the model answered without citing a row")
        return out
    if op == "count":
        out.update(value=len(items), unit="count")
    elif op in ("sum", "max", "min", "mean"):
        nums = [(_num(it.get("value")), it) for it in items]
        if any(v is None for v, _ in nums):
            out["ok"] = False
            nums = [(v, it) for v, it in nums if v is not None]
        if not nums:
            return out
        if op == "sum":
            v = sum(x for x, _ in nums)
        elif op == "mean":
            v = sum(x for x, _ in nums) / len(nums)
        else:
            x, it = (max if op == "max" else min)(nums, key=lambda p: p[0])
            if which:
                out.update(value=f"{it.get('label') or js.get('answer')} ({it.get('value')})", unit=None, used=[it["row"]],
                           extreme=f"{it.get('label')} = {it.get('value')}")
                trace.append(f"{op} over {len(nums)} rows: {it.get('label')} ({it.get('value')})")
                return out
            v = x
        out.update(value=round(v, 2))
        trace.append(f"{op} of {len(nums)} printed numbers = {round(v, 2)} (computed in Python)")
    else:  # lookup
        ans = js.get("answer")
        if not isinstance(ans, str) or not ans.strip():
            ans = items[0].get("value")
        if unit in ("ft2", "m2", "ft", "m", "count") and _num(ans) is not None and unit != "ft":
            v = _num(ans)
            out.update(value=int(v) if unit == "count" and v == int(v) else v)
        else:
            out.update(value=str(ans).strip(), unit=None)
    return out
