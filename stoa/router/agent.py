"""General tool-using agent for question kinds no template covers (Stoa: "the hidden test is harder and different").

A small LLM (the shared local server; text-only loop, cheap) plans with tools and never types a number it did not
get from a tool:

    ask(question)      answer a SIMPLE question with the team's solvers (the pipeline's atomic cascade: dxf, ifc,
                       schedule, raster, VLM, gated on train); returns value, unit, confidence, solver
    table()            the structured data behind this drawing: swiss DXF rooms/apartments, IFC fact card
    find_text(words)   search the PDF text layer; hits come back with page + box (become evidence)
    look(question)     ask the vision model about the drawing image directly
    calc(expression)   arithmetic in Python (+ - * / ** ( ) min max round abs sum)
    answer(value)      finish: value + unit; confidence comes from the tools used, not from the model

Every tool result is shown to the model as one short line and kept in the trace, so the reasoning is readable in
the UI. Evidence = the evidence of every `ask` whose value was used, plus text hits.
Confidence = product of the confidences of the asks used (x0.9 for the extra reasoning step); an answer not backed
by any tool result gets 0.25 and says so in `missing`.

    python -m stoa.eval --solver agent --split <novel.jsonl>     (standalone: builds its own pipeline for `ask`)
"""

from __future__ import annotations

import ast
import json
import math
import operator
import re
import time
from pathlib import Path

from stoa.contract import Answer, Cost, Evidence
from stoa.data import abspath, siblings, source_of

MAX_STEPS = 7
SYSTEM = """You answer one question about a construction drawing or building model by calling tools, step by step.
Tools (one per step):
- ask: input = ONE simple question in English that the team's solvers answer reliably (see KNOWN QUESTIONS).
  Split a complex question into such simple questions, one per step.
- table: input = "". Shows the extracted data table of this drawing (rooms, areas, labels, apartments, storeys).
- find_text: input = a word or phrase to search in the drawing's text.
- look: input = a short question for a vision model looking at the drawing image (use only if nothing else works).
- calc: input = an arithmetic expression using numbers from earlier tool results, e.g. "(12.5+8.25)/2".
- answer: input = the final value only (a number, or a short text); set "unit" (count, m2, m3, m, %, or "").
Rules: never invent numbers; every number in calc must come from a tool result. Prefer ask over look.
Reply with JSON only: {"thought": "<max 20 words>", "tool": "<tool>", "input": "<string>", "unit": "<unit or empty>"}"""

KNOWN = {
    "cubicasa5k": [
        "How many windows are shown on this floor plan?",
        "How many doors are shown on this floor plan?",
        "How many floors (storeys) does this floor plan show?",
        "How many toilet bowls (WC seats) are drawn on this floor plan?",
        "How many sinks and wash basins are drawn on this floor plan?",
        "How many showers and bathtubs are drawn on this floor plan in total?",
        "How many saunas are on this floor plan?",
        "How many kitchens (including kitchenettes) are on this floor plan?",
        "How many bedrooms (makuuhuone, usually marked MH) are on this floor plan?",
        "How many bathrooms or washrooms are on this floor plan, not counting separate WC rooms?",
        "How many separate WC rooms (toilet rooms marked WC) are on this floor plan?",
        "How many balconies are on this floor plan?",
    ],
    "swiss_dwellings": [
        "How many apartments (residential units) are shown on this floor plan?",
        "How many doors / windows / toilets / washbasins / bathtubs / showers are drawn on this floor plan?",
        "How many rooms labelled '<label>' are there on this floor?",
        "What is the total net area in m² of all rooms labelled '<label>' on this floor?",
        "What is the net floor area of room <number> in m²?",
        "What is the net floor area of apartment <letter> in m², summing all its rooms except balconies, loggias, "
        "terraces and other outdoor spaces?",
        "What is the total net floor area in m² of all numbered indoor rooms on this floor?",
    ],
    "ifc_models": [
        "What is the net floor area of the room '<room>' on '<storey>', in m²?",
        "What is the total net floor area of all rooms (spaces) on '<storey>', in m²?",
        "How many <doors/windows/walls/stairs/columns/rooms (spaces)> are shown on the floor plan of '<storey>'?",
        "How many <doors/windows/...> are there in the model '<model>'?",
        "What is the total net volume of all walls on '<storey>', in m³?",
        "What is the total length of all walls on '<storey>', in metres?",
    ],
}

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv}
_FUN = {"min": min, "max": max, "round": round, "abs": abs, "sum": lambda *a: sum(a[0] if len(a) == 1 else a),
        "sqrt": math.sqrt}


def calc(expr: str) -> float:
    """Safe arithmetic (no names except a few functions)."""
    expr = expr.replace("×", "*").replace("÷", "/").replace("^", "**").replace(",", ".") if expr.count(",") and \
        not re.search(r"\w\(", expr) else expr.replace("×", "*").replace("÷", "/").replace("^", "**")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            return _BIN[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            return -ev(n.operand) if isinstance(n.op, ast.USub) else ev(n.operand)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUN:
            return _FUN[n.func.id](*[ev(a) for a in n.args])
        if isinstance(n, (ast.List, ast.Tuple)):
            return [ev(e) for e in n.elts]
        raise ValueError(f"not allowed: {ast.dump(n)[:60]}")

    v = ev(ast.parse(expr.strip(), mode="eval"))
    if isinstance(v, list):
        raise ValueError("result is a list")
    return float(v)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt(v) -> str:
    x = _num(v)
    if x is None:
        return str(v)
    if x == int(x):
        return str(int(x))
    return f"{x:.4g}" if abs(x) < 1 else f"{x:.3f}".rstrip("0").rstrip(".")


class Agent:
    """`ask_fn(path, question) -> Answer` answers simple sub-questions (the pipeline's atomic cascade)."""

    def __init__(self, ask_fn=None, backend: str = "local", max_steps: int = MAX_STEPS):
        self.ask_fn = ask_fn
        self.backend = backend
        self.max_steps = max_steps

    # -- tools ------------------------------------------------------------------------------------
    def _table(self, path: str) -> str:
        src = source_of(path)
        if src == "swiss_dwellings":
            dxf = siblings(path).get(".dxf") or (path if path.endswith(".dxf") else None)
            if dxf:
                from stoa.solvers.vector import tableqa
                from stoa.solvers.vector.floor import load_floor

                t = tableqa.floor_tables(load_floor(str(abspath(dxf))))
                rooms = t["rooms"]
                cols = [c for c in ("number", "name", "area_m2", "apartment", "outdoor") if c in rooms]
                txt = "rooms:\n" + rooms[cols].to_csv(index=False)
                if not t["apartments"].empty:
                    txt += "apartments:\n" + t["apartments"].to_csv(index=False)
                return txt[:3500]
        if src in ("ifc_models", "ifc_bench") or path.endswith(".ifc"):
            from stoa.solvers.ifc.factcard import fact_card
            from stoa.solvers.ifc.index import load_index
            from stoa.solvers.ifc.solver import model_for

            m = model_for(path)
            if m:
                return fact_card(load_index(m), None, max_lines=90)[:4000]
        return "no structured table for this drawing (use ask or look)"

    def _pdf(self, path: str) -> str | None:
        if path.lower().endswith(".pdf"):
            return path
        return siblings(path).get(".pdf")

    def _find_text(self, path: str, words: str, ev: list[Evidence]) -> str:
        pdf = self._pdf(path)
        if not pdf:
            return "no text layer (not a PDF)"
        import fitz

        hits = []
        with fitz.open(str(abspath(pdf))) as doc:
            for pno, page in enumerate(doc):
                for r in page.search_for(words)[:8]:
                    # the line around the hit, for context
                    line = page.get_textbox(fitz.Rect(r.x0 - 120, r.y0 - 1, r.x1 + 200, r.y1 + 1)).replace("\n", " ")
                    hits.append((pno, [r.x0, r.y0, r.x1, r.y1], line.strip()[:80]))
                if len(hits) >= 8:
                    break
        for pno, bb, line in hits[:4]:
            ev.append(Evidence(file=pdf, page=pno, bbox=[round(x, 1) for x in bb], bbox_space="pdf_pt",
                               note=f"text '{words}'"))
        if not hits:
            return f"'{words}' not found in the text layer"
        return f"{len(hits)} hit(s): " + " | ".join(f"p{p}: {t}" for p, _, t in hits[:6])

    def _look(self, path: str, question: str) -> Answer:
        from stoa.solvers import get_solver

        img = path
        if path.endswith(".ifc") or path.endswith(".dxf") or path.endswith(".svg"):
            sib = siblings(path)
            img = sib.get(".png") or sib.get(".pdf") or path
        return get_solver("vlm_direct").solve(img, question)

    # -- loop -------------------------------------------------------------------------------------
    def solve(self, path: str, question: str, intent=None) -> Answer:
        from stoa import llm

        t0 = time.perf_counter()
        src = source_of(path)
        known = KNOWN.get(src, [])
        ctx = (f"FILE: {Path(path).name} (source {src}; siblings: {', '.join(sorted(siblings(path))) or 'none'})\n"
               + ("KNOWN QUESTIONS (ask these, filling in <...>):\n- " + "\n- ".join(known) + "\n" if known else "")
               + f"QUESTION: {question}")
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": ctx}]
        schema = {"type": "object", "properties": {
            "thought": {"type": "string", "maxLength": 200},
            "tool": {"type": "string", "enum": ["ask", "table", "find_text", "look", "calc", "answer"]},
            "input": {"type": "string", "maxLength": 400}, "unit": {"type": "string", "maxLength": 12}},
            "required": ["thought", "tool", "input"]}
        trace: list[str] = []
        evidence: list[Evidence] = []
        results: list[tuple[float | str, float, list[Evidence], str]] = []  # (value, conf, evidence, what)
        final = None
        unit = None
        assumptions: list[str] = []
        missing: list[str] = []
        cost = Cost()
        n_bad = 0
        for step in range(self.max_steps):
            force = step == self.max_steps - 1
            if force:
                msgs.append({"role": "user", "content": "Last step: call answer now with your best value."})
            try:
                r = llm.chat(msgs, backend=self.backend, max_tokens=220, temperature=0.0, json_schema=schema)
            except Exception as e:  # noqa: BLE001
                trace.append(f"agent: LLM error {type(e).__name__}")
                break
            cost = cost.add(Cost(llm_tokens_in=r.prompt_tokens or 0, llm_tokens_out=r.completion_tokens or 0,
                                 llm_calls=1, gpu_seconds=round(r.latency_s, 3)))
            try:
                d = json.loads(r.text)
            except Exception:  # noqa: BLE001
                d = llm.extract_json(r.text) or {}
            tool, inp = str(d.get("tool", "")), str(d.get("input", "")).strip()
            msgs.append({"role": "assistant", "content": r.text})
            thought = str(d.get("thought", ""))[:120]
            if tool == "answer" or (force and tool != "answer"):
                final = inp if tool == "answer" else None
                unit = (d.get("unit") or "").strip() or None
                trace.append(f"think: {thought} → answer {inp} {unit or ''}".strip())
                break
            obs = self._run(tool, inp, path, evidence, results, cost_box := [Cost()])
            cost = cost.add(cost_box[0])
            trace.append(f"think: {thought} → {tool}({inp[:90]}): {obs[:160]}")
            if obs.startswith("error"):
                n_bad += 1
                if n_bad >= 3:
                    break
            msgs.append({"role": "user", "content": f"RESULT of {tool}: {obs[:3600]}"})
        return self._finish(final, unit, results, evidence, trace, assumptions, missing, cost, t0, question)

    def _run(self, tool: str, inp: str, path: str, evidence, results, cost_box) -> str:
        try:
            if tool == "ask":
                if self.ask_fn is None:
                    return "error: ask unavailable"
                a = self.ask_fn(path, inp)
                c = a.cost
                cost_box[0] = Cost.model_validate(c) if isinstance(c, dict) else (c or Cost())
                if a.value is None:
                    return f"no answer ({(a.missing or ['?'])[0][:80]})"
                results.append((a.value, a.confidence, list(a.evidence), f"ask: {inp[:80]}"))
                return f"{_fmt(a.value)} {a.unit or ''} (confidence {a.confidence:.2f}, by {a.solver})"
            if tool == "table":
                return self._table(path)
            if tool == "find_text":
                return self._find_text(path, inp, evidence)
            if tool == "look":
                a = self._look(path, inp)
                c = a.cost
                cost_box[0] = Cost.model_validate(c) if isinstance(c, dict) else (c or Cost())
                if a.value is None:
                    return "no answer"
                results.append((a.value, min(a.confidence, 0.3), list(a.evidence), f"look: {inp[:80]}"))
                return f"{_fmt(a.value)} {a.unit or ''} (vision model, unverified)"
            if tool == "calc":
                v = calc(inp)
                results.append((v, -1.0, [], f"calc: {inp[:80]}"))  # conf -1: derived, see _finish
                return _fmt(round(v, 4))
            return f"error: unknown tool {tool}"
        except Exception as e:  # noqa: BLE001
            return f"error: {type(e).__name__}: {str(e)[:100]}"

    def _finish(self, final, unit, results, evidence, trace, assumptions, missing, cost, t0, question) -> Answer:
        value = final
        x = _num(final)
        if x is None and final is not None:
            m = re.search(r"-?\d+(?:\.\d+)?", str(final))
            if m and len(str(final)) < 24:
                x = float(m.group(0))
        if x is not None:
            value = int(round(x)) if unit == "count" else round(x, 4)
        # confidence: which tool results back this value?
        direct = [(v, c, e, w) for v, c, e, w in results if c >= 0 and _num(v) is not None and x is not None
                  and abs(_num(v) - x) <= 0.005 * max(abs(x), 1)]
        calcs = [(v, c, e, w) for v, c, e, w in results if c < 0 and x is not None and abs(v - x) <= 0.005 * max(abs(x), 1)]
        asked = [(v, c, e, w) for v, c, e, w in results if c >= 0]
        if calcs and asked:  # the final value was computed: every ask feeds it
            conf = 0.9
            for _, c, _, _ in asked:
                conf *= max(0.05, c)
            used = asked
            assumptions.append("value computed from the tool results above (" + calcs[-1][3] + ")")
        elif direct:
            conf = max(c for _, c, _, _ in direct)
            used = direct[:1]
        elif False:
            conf = 0.9
            for _, c, _, _ in asked:
                conf *= max(0.05, c)
            used = asked
            assumptions.append("value computed from the tool results above (" + calcs[-1][3] + ")")
        else:
            conf = 0.25
            used = []
            if value is not None:
                missing.append("the agent's answer is not backed by a tool result")
        for _, _, ev, w in used:
            for e in ev[:6]:
                evidence.append(e.model_copy(update={"note": (f"{w[5:60]} — {e.note}" if e.note else w[5:60])}))
        if value is None:
            missing.append("the agent did not reach an answer")
        cost.wall_seconds = round(time.perf_counter() - t0, 3)
        trace.insert(0, f"agent: general tool-using path ({len(trace)} steps, {cost.llm_calls} LLM calls)")
        return Answer(value=value, unit=unit if unit not in ("", "none") else None, confidence=round(min(conf, 0.95), 3),
                      evidence=evidence[:20], trace=trace, solver="agent", assumptions=assumptions, missing=missing,
                      cost=cost)


__all__ = ["Agent", "calc", "KNOWN"]
