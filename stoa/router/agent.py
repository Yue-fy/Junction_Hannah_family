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
SCOPE_PENALTY = 0.6  # an ask that names none of the question's quoted names (storey, room, label) is about another scope
SYSTEM = """You answer one question about a construction drawing or building model by calling tools, step by step.
Tools (one per step):
- ask: input = ONE simple question in English that the team's solvers answer reliably (see KNOWN QUESTIONS).
  Split a complex question into such simple questions, one per step.
- table: input = "". Shows the extracted data table of this drawing (rooms, areas, labels, apartments, storeys).
- rows: input = a condition on the room table (swiss drawings), e.g. "area_m2 > 10 and numbered and not outdoor" or
  "apartment == 'B' and name == 'Bad'". Columns: number, name, area_m2, apartment, outdoor, numbered, n_doors,
  n_windows, n_toilets, n_washbasins, n_bathtubs, n_showers. Returns how many rooms match and their area sum.
- find_text: input = a word or phrase to search in the drawing's text.
- look: input = a short question for a vision model looking at the drawing image (use only if nothing else works).
- calc: input = an arithmetic expression using numbers from earlier tool results, e.g. "(12.5+8.25)/2".
  Comparisons give 1 or 0, so "(38.65 > 31) + (12.07 > 31)" counts how many values are above 31.
- answer: input = the final value only (a number, or a short text such as "apartment B", the storey name, "yes"
  or "no" when the question asks which one / yes or no); set "unit" (count, m2, m3, m, ft2, ft, %, or the unit the
  question asks for, e.g. EUR, h, l, m2/door; "" if none).
Rules: never invent numbers; every number in calc must come from a tool result or be stated in the question (a price,
a rate, an "if ..." assumption). Answer the computed value as calc returned it (do not round it). Prefer ask over look.
For "which ... more/larger" questions ask the value for each candidate, then answer with the candidate's name.
Use table to look up single values (one room's area, its apartment) and to see which rooms exist: never ask about a
room number you have not seen in the table. To count or sum rooms by a condition ("larger than 10 m²", "not in
apartment A"), use rows. For TOTALS (all rooms of a floor, an apartment, all rooms labelled X,
a storey) ask the KNOWN question instead of adding table rows yourself.
Reply with JSON only: {"thought": "<max 20 words>", "tool": "<tool>", "input": "<string>", "unit": "<unit or empty>"}"""
_ROWS_TOOL = SYSTEM[SYSTEM.index("- rows:"):SYSTEM.index("- find_text:")]
_ROWS_RULE = """To count or sum rooms by a condition ("larger than 10 m²", "not in
apartment A"), use rows. """


def system_for(src: str) -> str:
    """The rows tool reads the swiss room table only; elsewhere the model kept calling it (IFC: 3 errors, no answer)."""
    if src == "swiss_dwellings":
        return SYSTEM
    return SYSTEM.replace(_ROWS_TOOL, "").replace(_ROWS_RULE, "")

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
        "How many <doors/windows/...> are there in the model '<model name>'? (WHOLE building, all storeys; use the "
        "storey question above when the question names a storey)",
        "What is the total net volume of all walls on '<storey>', in m³?",
        "What is the total length of all walls on '<storey>', in metres?",
    ],
}

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv}
_CMP = {ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Lt: operator.lt, ast.LtE: operator.le, ast.Eq: operator.eq,
        ast.NotEq: operator.ne}
_FUN = {"min": min, "max": max, "round": round, "abs": abs, "sum": lambda *a: sum(a[0] if len(a) == 1 else a),
        "sqrt": math.sqrt}


# numbers a calculation may use without a tool result: small factors, percent, unit conversions (ft, ft²)
_CONST = {0.0, 1.0, 2.0, 3.0, 4.0, 10.0, 100.0, 1000.0, 0.3048, 3.28084, 3.2808, 10.7639, 10.764, 0.092903, 0.0929}


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
        if isinstance(n, ast.Compare) and all(type(o) in _CMP for o in n.ops):
            left, ok = ev(n.left), True
            for o, c in zip(n.ops, n.comparators):
                right = ev(c)
                ok = ok and _CMP[type(o)](left, right)
                left = right
            return 1.0 if ok else 0.0
        if isinstance(n, ast.BoolOp):
            vals = [bool(ev(v)) for v in n.values]
            return 1.0 if (all(vals) if isinstance(n.op, ast.And) else any(vals)) else 0.0
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

    def _swiss_rooms(self, path: str):
        dxf = siblings(path).get(".dxf") or (path if path.endswith(".dxf") else None)
        if source_of(path) != "swiss_dwellings" or not dxf:
            return None
        from stoa.solvers.vector import tableqa
        from stoa.solvers.vector.floor import load_floor

        df = tableqa.floor_tables(load_floor(str(abspath(dxf))))["rooms"].copy()
        df["numbered"] = df["number"].fillna("").astype(str).str.len() > 0
        return df

    _COND_OK = re.compile(r"[\w\s.'\"<>=!()&|+\-*/,äöüéèàÄÖÜ²]+")

    def _rows(self, path: str, cond: str, results) -> str:
        """Deterministic filter over the swiss room table (no attribute access, no calls)."""
        df = self._swiss_rooms(path)
        if df is None:
            return "error: rows works on swiss drawings with a DXF; use table + calc"
        c = cond.strip().strip("`")
        if not self._COND_OK.fullmatch(c) or "__" in c or re.search(r"[A-Za-z_)\]]\s*\.", c) or re.search(r"\w\s*\(", c):
            return "error: use a plain condition like \"area_m2 > 10 and numbered and not outdoor\""
        c = re.sub(r"\bAND\b", "and", re.sub(r"\bOR\b", "or", c))
        sub = df.query(c, engine="python")
        n, tot = len(sub), round(float(sub["area_m2"].sum()), 2)
        ev: list[Evidence] = []
        if self.ask_fn is not None:  # the matched rooms' outlines on the drawing (deterministic asks, no LLM)
            for r in sub.head(6).itertuples():
                if not r.number:
                    continue
                try:
                    a = self.ask_fn(path, f"What is the net floor area of room {r.number} ('{r.name}') in m²?")
                except Exception:  # noqa: BLE001
                    continue
                ev += [e.model_copy(update={"note": f"room {r.number} '{r.name}' {r.area_m2} m² matches"})
                       for e in (a.evidence or [])[:1]]
        results.append((n, 0.9, ev, f"rows: {c[:70]} (count)"))
        results.append((tot, 0.9, ev, f"rows: {c[:70]} (area sum)"))
        listed = ", ".join(f"{r.number or '-'} {r.name} {r.area_m2}" for r in sub.head(12).itertuples())
        return f"{n} room(s) match, area_m2 sum {tot}: {listed}" + (" …" if n > 12 else "")

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
        msgs = [{"role": "system", "content": system_for(src)}, {"role": "user", "content": ctx}]
        tools = ["ask", "table", "rows", "find_text", "look", "calc", "answer"]
        if src != "swiss_dwellings":
            tools.remove("rows")
        schema = {"type": "object", "properties": {
            "thought": {"type": "string", "maxLength": 200},
            "tool": {"type": "string", "enum": tools},
            "input": {"type": "string", "maxLength": 1200}, "unit": {"type": "string", "maxLength": 24}},
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
        done: dict[tuple[str, str], str] = {}  # (tool, input) -> observation
        from stoa.router.intent import parse

        # scope names: the storey / model the question is about (room labels are not: a swiss room is asked by number)
        _f = parse(question).filters
        names = {str(_f[k]).strip().lower() for k in ("storey", "model") if _f.get(k)}
        names = {n for n in names if len(n) >= 2}
        for step in range(self.max_steps):
            force = step == self.max_steps - 1
            if force:
                msgs.append({"role": "user", "content": "Last step: call answer now with your best value."})
            try:
                r = llm.chat(msgs, backend=self.backend, max_tokens=500, temperature=0.0, json_schema=schema)
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
            if tool == "answer" and not results and not force and step < 2 and not str(d.get("input", "")).strip()[:1].isalpha():
                # an answer before any tool result (seen: "28 * (net area of apartment A in m²) CHF" in step 1)
                msgs.append({"role": "assistant", "content": r.text})
                msgs.append({"role": "user", "content": "error: no tool has returned a number yet. Call ask / table "
                                                        "first, then calc, then answer."})
                trace.append(f"think: {thought} → answer before any tool result: refused")
                continue
            if tool == "answer" or (force and tool != "answer"):
                final = inp if tool == "answer" else None
                unit = (d.get("unit") or "").strip() or None
                trace.append(f"think: {thought} → answer {inp} {unit or ''}".strip())
                break
            if (tool, inp) in done and tool != "answer":
                obs = (f"error: you already called {tool}({inp[:60]}) and got: {done[(tool, inp)][:300]}. "
                       "Use that result, or call ask / calc / answer")
                cost_box = [Cost()]
            else:
                n_res = len(results)
                obs = self._run(tool, inp, path, evidence, results, cost_box := [Cost()])
                if tool == "ask" and names and len(results) > n_res and not any(n in inp.lower() for n in names):
                    # scope drift: the question names '1.korrus', the sub-question none of its names (the 8B model
                    # asked the whole-model door count for "doors per 100 m² on '1.korrus'": 211 instead of 46)
                    v, c, e, w = results[-1]
                    results[-1] = (v, round(c * SCOPE_PENALTY, 3), e, w)
                    obs += (" -- WARNING: this sub-question names none of " + ", ".join(f"'{n}'" for n in sorted(names))
                            + " from the question, so it is about a different scope; ask again naming it if needed")
                done[(tool, inp)] = obs
            cost = cost.add(cost_box[0])
            trace.append(f"think: {thought} → {tool}({inp[:90]}): {obs[:160]}")
            if obs.startswith("error"):
                n_bad += 1
                if n_bad >= 3:
                    break
            msgs.append({"role": "user", "content": f"RESULT of {tool}: {obs[:3600]}"})
        ans = self._finish(final, unit, results, evidence, trace, assumptions, missing, cost, t0, question)
        if src == "swiss_dwellings" and self.ask_fn is not None and ans.value is not None and ans.confidence > 0.25:
            try:
                self._table_evidence(path, results, ans)
            except Exception:  # noqa: BLE001 - evidence is a bonus, never a failure
                pass
        return ans

    def _table_evidence(self, path: str, results, ans: Answer) -> None:
        """Rooms whose table area the calculation used -> their drawn outline (asked to the deterministic solver)."""
        tables = [str(v) for v, c, _, _ in results if c == -2.0]
        exprs = " ".join(w[6:] for v, c, _, w in results if c == -1.0)
        if not tables or not exprs:
            return
        nums = {float(t) for t in re.findall(r"\d+\.\d+", exprs)}
        rows = []
        for line in tables[-1].splitlines():  # "number,name,area_m2,apartment,outdoor"
            parts = line.split(",")
            if len(parts) >= 3 and re.fullmatch(r"\d+(?:\.\d+)*", parts[0] or "x") and _num(parts[2]) is not None:
                rows.append((parts[0], parts[1], _num(parts[2])))
        hit = [(no, name) for no, name, a in rows if a in nums][:6]
        for no, name in hit:
            a = self.ask_fn(path, f"What is the net floor area of room {no} ('{name}') in m²?" if name
                            else f"What is the net floor area of room {no} in m²?")
            for e in (a.evidence or [])[:1]:
                ans.evidence.append(e.model_copy(update={"note": f"room {no} '{name}' used in the calculation"}))
        if hit:
            ans.trace.append("evidence: outlines of the rooms used — " + ", ".join(f"{no}" for no, _ in hit))

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
                t = self._table(path)
                results.append((t, -2.0, [], "table"))  # conf -2: data the calc numbers may come from, see _grounding
                return t
            if tool == "rows":
                return self._rows(path, inp, results)
            if tool == "find_text":
                return self._find_text(path, inp, evidence)
            if tool == "look":
                a = self._look(path, inp)
                c = a.cost
                cost_box[0] = Cost.model_validate(c) if isinstance(c, dict) else (c or Cost())
                if a.value is None:
                    return "no answer"
                # vlm_direct's confidence is calibrated on TRAIN (R2: answer-digit logprobs; conf >= 0.8 -> 89% right)
                results.append((a.value, min(a.confidence, 0.9), list(a.evidence), f"look: {inp[:80]}"))
                return f"{_fmt(a.value)} {a.unit or ''} (vision model, confidence {a.confidence:.2f})"
            if tool == "calc":
                v = calc(inp)
                results.append((v, -1.0, [], f"calc: {inp}"))  # conf -1: derived, see _finish
                return _fmt(round(v, 4))
            return f"error: unknown tool {tool}"
        except Exception as e:  # noqa: BLE001
            return f"error: {type(e).__name__}: {str(e)[:100]}"

    @staticmethod
    def _grounding(expr: str, results, question: str):
        """Trace each number of a calc expression to an ask result, the data table, an earlier calc, the question
        itself (thresholds, room numbers) or a unit constant. -> (asks used, table used?, ungrounded numbers)."""
        num = re.compile(r"\d+(?:\.\d+)?")
        in_q = {float(t) for t in num.findall(question)}
        table = {float(t) for v, c, _, _ in results if c == -2.0 for t in num.findall(str(v))}
        asks = [r for r in results if r[1] >= 0 and _num(r[0]) is not None]
        calcs = [r for r in results if r[1] == -1.0]
        used: dict[int, tuple] = {}
        state = {"table": False}
        bad: list[str] = []

        def close(a, b, rel):
            return abs(a - b) <= rel * max(abs(b), 1e-9) + 1e-9

        def visit(e: str, depth: int):
            for t in num.findall(e):
                y = float(t)
                hit = next((i for i, a in enumerate(asks) if close(y, _num(a[0]), 0.005)), None)
                if hit is not None:
                    used[hit] = asks[hit]
                elif y in table:
                    state["table"] = True
                    state["n_table"] = state.get("n_table", 0) + 1
                elif y in in_q or y in _CONST:
                    pass
                else:
                    prev = next((c for c in calcs if close(y, c[0], 0.0005) and c[3][6:] != e), None)
                    if prev is not None and depth < 4:
                        visit(prev[3][6:], depth + 1)
                    else:
                        bad.append(t)

        visit(expr, 0)
        # adding many table rows by hand is where the model slips (wrong rows, a missed room): less sure
        return list(used.values()), (state.get("n_table", 0) if state["table"] else 0), bad

    def _finish_text(self, final, results, evidence, trace, assumptions, missing, cost, t0) -> Answer:
        asked = [(v, c, e, w) for v, c, e, w in results if c >= 0]
        conf = 0.25
        if len(asked) >= 2:
            conf = 0.85
            for _, c, _, _ in asked:
                conf *= max(0.05, c)
            assumptions.append("answer chosen by comparing the tool results above")
            for _, _, ev, w in asked:
                evidence += [e.model_copy(update={"note": (f"{w[5:60]} — {e.note}" if e.note else w[5:60])}) for e in ev[:6]]
        else:
            missing.append("the agent's answer is not backed by a tool result")
        cost.wall_seconds = round(time.perf_counter() - t0, 3)
        trace.insert(0, f"agent: general tool-using path ({len(trace)} steps, {cost.llm_calls} LLM calls)")
        return Answer(value=final, unit=None, confidence=round(min(conf, 0.95), 3), evidence=evidence[:20], trace=trace,
                      solver="agent", assumptions=assumptions, missing=missing, cost=cost)

    def _finish(self, final, unit, results, evidence, trace, assumptions, missing, cost, t0, question) -> Answer:
        value = final
        from stoa.router.intent import _QUOTED

        names = {next(g for g in m.groups() if g).strip().lower() for m in _QUOTED.finditer(question)}
        if final is not None and str(final).strip().strip("'\"‘’“”«»").lower() in names:
            # "which storey has more doors, '1.korrus' or '2.korrus'?" -> '1.korrus' is a name, not the number 1 (W5)
            final, unit = str(final).strip().strip("'\"‘’“”«»"), None
            return self._finish_text(final, results, evidence, trace, assumptions, missing, cost, t0)
        x = _num(final)
        numeric_unit = (unit or "").lower() in ("count", "m2", "m²", "m3", "m³", "m", "ft2", "ft²", "ft", "ft3", "%")
        mu = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*(m²|m2|m³|m3|m|ft²|ft2|ft|%|doors?|windows?|rooms?)\s*", str(final or ""))
        if x is None and mu and not unit:  # "14.11 m²" with no unit field
            x, unit = float(mu.group(1)), {"m²": "m2", "m³": "m3", "ft²": "ft2"}.get(mu.group(2), mu.group(2))
            unit = "count" if unit.rstrip("s") in ("door", "window", "room") else unit
        if x is None and final is not None and numeric_unit:  # "12.5 m2" -> 12.5; "1.OG" (a storey name) stays text
            m = re.search(r"-?\d+(?:\.\d+)?", str(final))
            if m and len(str(final)) < 24:
                x = float(m.group(0))
        if x is not None:
            value = int(round(x)) if (unit == "count" or (not unit and x == int(x))) else round(x, 4)
        # confidence: which tool results back this value?
        direct = [(v, c, e, w) for v, c, e, w in results if c >= 0 and _num(v) is not None and x is not None
                  and abs(_num(v) - x) <= 0.005 * max(abs(x), 1)]
        calcs = [(v, c, e, w) for v, c, e, w in results if c == -1.0 and x is not None
                 and abs(v - x) <= 0.005 * max(abs(x), 1)]
        if not calcs and x is not None and x == int(x):
            # the model rounded the calc result to whole units (5.908 days -> 6): still grounded; keep the exact value
            near = [(v, c, e, w) for v, c, e, w in results if c == -1.0 and abs(v - x) < 1 and v != int(v)]
            if near:
                v = near[-1][0]
                assumptions.append(f"the agent rounded {round(v, 4)} to {int(x)}; the computed value is reported")
                x, value, calcs = v, round(v, 4), near[-1:]
        asked = [(v, c, e, w) for v, c, e, w in results if c >= 0]
        if calcs:  # the final value was computed: trace every number of the calc back to a tool result
            used, from_table, bad = self._grounding(calcs[-1][3][6:], results, question)
            if not bad:
                conf = 0.9 * (1.0 if not from_table else 0.95 if from_table <= 2 else 0.6)
                for _, c, _, _ in used:
                    conf *= max(0.05, c)
                assumptions.append("value computed in code from the tool results above (" + calcs[-1][3][:100] + ")")
            else:
                conf, used = 0.25, []
                missing.append("the calculation uses numbers no tool returned: " + ", ".join(bad[:5]))
        elif direct:
            conf = max(c for _, c, _, _ in direct)
            used = direct[:1]
        elif x is None and value is not None and str(value).strip() and len(asked) >= 2 and len(str(value)) <= 60:
            # a text answer chosen by comparing values ("which storey has more doors?" -> '0'): backed by the asks
            conf = 0.85
            for _, c, _, _ in asked:
                conf *= max(0.05, c)
            used = asked
            assumptions.append("answer chosen by comparing the tool results above")
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
