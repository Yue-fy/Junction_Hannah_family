"""One LLM budget per question across the whole cascade (D20-2; Stoa scores cost, lower is better).

`Pipeline.solve` opens a question meter; every LLM/VLM call made inside it (any solver, the agent, cross-checks)
is recorded by stoa.llm through stoa.contract.record_cost and lands here. Optional steps (the agent's next step,
a second solver's cross-check, the both-readings pass, area cross-checks) ask `over()` before they spend more; when
the question has already used QUESTION_TOKENS they answer with the best reading so far and say so
(`note()` -> assumptions). Steps that produce the FIRST reading never check: the budget stops escalation, it never
leaves a question without an answer.

Solvers owned by others can call `over()` / `remaining()` too (e.g. a table-QA retry loop).
"""
from __future__ import annotations

import contextlib
import contextvars
import os

from stoa.contract import CostMeter

# tokens in + out for one question. dev (2,215 Qs, night 4fb47c9): p99 14.4k, max 43k (schedule table QA on a 6-table
# sheet, right at 0.3); hard/hard2 max 9.6k. Q's red team v18: p99 37k, 29 Qs > 15k holding 53% of all tokens.
QUESTION_TOKENS = int(os.environ.get("STOA_QUESTION_TOKENS", 20000))
# LLM calls for one question (the agent alone stops at 6 calls without a sure reading)
QUESTION_CALLS = int(os.environ.get("STOA_QUESTION_CALLS", 12))

_METER: contextvars.ContextVar[CostMeter | None] = contextvars.ContextVar("w4_question_meter", default=None)
_HIT: contextvars.ContextVar[list | None] = contextvars.ContextVar("w4_budget_hits", default=None)


@contextlib.contextmanager
def question():
    """Meter one question. Nested use (a question asked inside another) shares the outer meter."""
    if _METER.get() is not None:
        yield _METER.get()
        return
    with CostMeter() as m:
        tok = _METER.set(m)
        tok2 = _HIT.set([])
        try:
            yield m
        finally:
            _METER.reset(tok)
            _HIT.reset(tok2)


def spent() -> tuple[int, int]:
    """(tokens in + out, LLM calls) so far for the current question; (0, 0) outside a question."""
    m = _METER.get()
    if m is None:
        return 0, 0
    c = m.cost
    return int((c.llm_tokens_in or 0) + (c.llm_tokens_out or 0)), int(c.llm_calls or 0)


def over() -> bool:
    tok, calls = spent()
    return tok >= QUESTION_TOKENS or calls >= QUESTION_CALLS


def remaining() -> int:
    return max(0, QUESTION_TOKENS - spent()[0])


def skip(step: str) -> str | None:
    """None if `step` may run; else a trace line saying why it was skipped (and the hit is recorded)."""
    if not over():
        return None
    tok, calls = spent()
    hits = _HIT.get()
    if hits is not None:
        hits.append(step)
    return f"LLM budget for this question reached ({tok} tokens / {calls} calls): {step} skipped"


def note() -> str | None:
    """Assumption line for the final answer when any step was skipped."""
    hits = _HIT.get()
    if not hits:
        return None
    return (f"LLM budget reached ({QUESTION_TOKENS} tokens or {QUESTION_CALLS} calls per question): answered with the "
            f"best reading so far ({', '.join(dict.fromkeys(hits))} skipped)")
