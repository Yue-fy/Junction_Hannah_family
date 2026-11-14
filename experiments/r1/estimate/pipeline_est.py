"""Measure the estimate route INSIDE the real pipeline without editing W4's files: registers `pipeline_est` =
Pipeline + R1's out-of-drawing estimator (experiments/r1/estimate/estimate.py).

Policy (the hook W4 would add to stoa/pipeline.py `_solve_question`, after the link route):
  hit = kind_of(question) (also on the to_english translation when the question is not English, like the link route)
  - CubiCasa / Swiss Dwellings: these drawings carry only room labels, areas and symbols, never rent, prices, years
    or wall build-ups -> answer with the estimate FIRST (0 LLM calls; saves the agent call that answered "unknown").
  - other sources (IFC, sheet sets, scans): run the normal pipeline first (a sheet or a model CAN state an energy
    figure, a U-value, a date); use the estimate only when that answer is None / not a number / a number below
    conf 0.3 with no evidence. Text-judged answers (IFC-Bench, or the pipeline's own answer was a sentence) get the
    estimate as a sentence ("Not recorded in the model; estimate ~ ... ").

    python experiments/r1/estimate/pipeline_est.py --split <jsonl> [stoa.eval args]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stoa.data import source_of  # noqa: E402
from stoa.pipeline import Pipeline, _cost_of  # noqa: E402
from stoa.solvers import register  # noqa: E402

FIRST = ("cubicasa5k", "swiss_dwellings")


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def estimate_kind(question: str):
    """(hit, english_or_None, cost_or_None): the trigger on the question as asked, then on its translation."""
    from experiments.r1.estimate.estimate import kind_of

    hit = kind_of(question)
    if hit["fire"]:
        return hit, None, None
    try:
        from stoa.contract import CostMeter
        from stoa.llm import lang_guess, to_english

        if lang_guess(question) == "en":
            return hit, None, None
        with CostMeter() as m:
            tr = to_english(question, force=True)
        text = getattr(tr, "text", None) or str(tr)
        h2 = kind_of(text)
        return h2, text, m
    except Exception:  # noqa: BLE001
        return hit, None, None


@register("pipeline_est")
class PipelineEst(Pipeline):
    def solve(self, path: str, question: str):
        from experiments.r1.estimate.estimate import solve as est_solve

        t0 = time.perf_counter()
        hit, english, _m = estimate_kind(question)
        src = source_of(path)
        route = f"route: out-of-drawing question ({hit.get('why')}" + (f"; via translation '{english[:60]}'" if english
                                                                         else "") + ") -> R1 estimate"
        if hit.get("fire") and src in FIRST:
            est = est_solve(path, question, hit)
            if est is not None:
                est.trace = [route + " first (this kind of drawing never states it)", *est.trace]
                est.solver = "pipeline/estimate"
                est.cost.wall_seconds = round(time.perf_counter() - t0, 4)
                return est
        ans = super().solve(path, question)
        if not hit.get("fire"):
            return ans
        weak = ans.value is None or not _num(ans.value) or (float(ans.confidence or 0) < 0.3 and not ans.evidence)
        if not weak:
            ans.trace = [*ans.trace, f"estimate route fired ({hit['kind']}) but the pipeline read a value: kept"]
            return ans
        est = est_solve(path, question, hit, as_text=(src == "ifc_bench" or isinstance(ans.value, str)))
        if est is None:
            return ans
        est.trace = [*ans.trace[-6:], f"{route} as fallback: the pipeline answered {str(ans.value)[:60]!r} at "
                     f"{float(ans.confidence or 0):.2f}", *est.trace]
        est.solver = "pipeline/estimate"
        est.cost = _cost_of(ans)
        est.cost.wall_seconds = round(time.perf_counter() - t0, 4)
        return est


if __name__ == "__main__":
    from stoa.eval.runner import main

    args = sys.argv[1:]
    if "--solver" not in args:
        args = ["--solver", "pipeline_est", *args]
    raise SystemExit(main(args))
