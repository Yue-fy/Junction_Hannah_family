"""LLM judge for free-text answers (text/other types), reported separately as `text_judge`.

Stoa scores text answers free-form, so exact matching is meaningless (ifc_bench references are paragraphs).
The judge asks a model whether the candidate states the same key facts as the reference. It is optional
(`python -m stoa.eval ... --judge local`) and its cost is NOT charged to the solver. Treat it as a noisy
signal: compare solvers with the same judge, and spot-check its verdicts.
"""

from __future__ import annotations

import re

PROMPT = """You grade answers to questions about construction drawings and building models.

Question: {question}

Reference answer: {gold}

Candidate answer: {pred}

The candidate is CORRECT if it states the same key facts as the reference: the same items, names, codes and
numbers (numbers may differ by rounding or by up to 2%; units may be converted; harmless extra detail is fine).
It is INCORRECT if a key fact is missing, wrong or contradicted, if it answers only part of a multi-part
reference, or if it is a refusal or "unknown".
Reply with exactly one word: CORRECT or INCORRECT."""


def judge_one(question: str, gold, pred, backend: str = "local") -> tuple[bool | None, str]:
    if pred is None or str(pred).strip() == "":
        return False, "empty"
    from stoa import llm

    try:
        r = llm.chat(PROMPT.format(question=question, gold=str(gold)[:6000], pred=str(pred)[:6000]),
                     backend=backend, max_tokens=8, temperature=0.0, thinking=False)
    except Exception as e:  # noqa: BLE001
        return None, f"judge error: {type(e).__name__}: {e}"
    t = (r.text or "").strip().upper()
    if re.search(r"\bINCORRECT\b", t):
        return False, t
    if re.search(r"\bCORRECT\b", t):
        return True, t
    return None, f"unparsed: {t[:40]}"


def judge_rows(rows: list[dict], backend: str = "local", workers: int = 8) -> None:
    """Add `text_judge` (True/False/None) to every text/other row in place."""
    import concurrent.futures as cf

    todo = [r for r in rows if r["type"] in ("text", "other")]
    with cf.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {ex.submit(judge_one, r["question"], r["gold"], r["value"], backend): r for r in todo}
        for f in cf.as_completed(futs):
            ok, why = f.result()
            futs[f]["text_judge"] = ok
            futs[f]["text_judge_raw"] = why
