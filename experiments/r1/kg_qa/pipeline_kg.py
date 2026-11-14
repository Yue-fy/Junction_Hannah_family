"""Measure the link-question route INSIDE the real pipeline without editing W4's files: registers `pipeline_kg` =
Pipeline + "is_link_question() fires and the drawing has a project graph (ifc_models / ifc_bench) -> kg_qa.solve();
no value -> the normal pipeline".

    python experiments/r1/kg_qa/pipeline_kg.py --split experiments/r1/kg_qa/probe_kg.jsonl [stoa.eval args]

Suggested change for W4 in stoa/pipeline.py `Pipeline.solve`, right after the question normalisers and BEFORE
decompose (the composer would split "do the plan and the model agree on the windows" into counts):
    if source_of(path) in ("ifc_models", "ifc_bench") and is_link_question(question)["fire"]:
        ans = kg_qa.solve(path, question)
        if ans.value is not None: prepend the route to the trace, return ans
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stoa.data import source_of  # noqa: E402
from stoa.pipeline import Pipeline  # noqa: E402
from stoa.solvers import register  # noqa: E402


@register("pipeline_kg")
class PipelineKG(Pipeline):
    def solve(self, path: str, question: str):
        if source_of(path) in ("ifc_models", "ifc_bench"):
            from experiments.r1.kg_qa.kgqa import is_link_question, solve as kg_solve

            hit = is_link_question(question)
            if hit["fire"]:
                try:
                    ans = kg_solve(path, question)
                except Exception as e:  # noqa: BLE001
                    ans = None
                    why = f"kg_qa failed: {type(e).__name__}"
                else:
                    why = "kg_qa: the linked facts do not answer it"
                if ans is not None and ans.value is not None:
                    ans.trace = [f"route: link question ({hit['why']}) -> project knowledge graph (R1 kg_qa over "
                                 "stoa.kg)", *ans.trace]
                    ans.solver = "pipeline/kg_qa"
                    return ans
                out = super().solve(path, question)
                out.trace = [*out.trace, why]
                return out
        return super().solve(path, question)


if __name__ == "__main__":
    from stoa.eval.runner import main

    args = sys.argv[1:]
    if "--solver" not in args:
        args = ["--solver", "pipeline_kg", *args]
    raise SystemExit(main(args))
