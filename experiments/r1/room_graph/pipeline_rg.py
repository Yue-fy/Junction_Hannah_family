"""Measure the per-room route INSIDE the real pipeline without editing W4's files: registers `pipeline_rg` =
Pipeline + "per_room() fires (cubicasa raster, room-scoped, not an area question) -> room_graph.solve()".

    python experiments/r1/room_graph/pipeline_rg.py --split experiments/r1/room_graph/probe/probe_v4.jsonl [stoa.eval args]

This is the change suggested to W4 for stoa/pipeline.py `Pipeline.solve`, right after `self._front_end(question)`
and BEFORE `decompose(...)` -- the composer turns "How many windows do the two bedrooms have in total?" into
"windows on this plan" + "bedrooms" = 6, so a hook inside `_solve_atomic` never sees the room scope (measured: 2
probe questions lost that way).  Here it wraps solve() on the question as asked (the probes are English):
    if self.cc5k and source_of(path) == "cubicasa5k":
        hit = per_room(question, path)
        if hit["fire"]:
            ans = room_graph.answer.solve(path, question)
            if ans.value is not None: cap conf, prepend trace, return ans
D8: pretrained CubiCasa5K segmentation -> cc5k=1 path only (cc5k=0 never calls it).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stoa.data import source_of  # noqa: E402
from stoa.pipeline import Pipeline  # noqa: E402
from stoa.solvers import register  # noqa: E402

CONF_CAP = 0.75  # room_graph's confidence is a provisional rule (n = 78 by-eye probe Qs); keep it out of the top bin


@register("pipeline_rg")
class PipelineRG(Pipeline):
    def solve(self, path: str, question: str):
        if self.cc5k and source_of(path) == "cubicasa5k":
            t0 = time.perf_counter()
            try:
                from experiments.r1.room_graph.route import per_room

                hit = per_room(question, path)
            except Exception:  # noqa: BLE001
                hit = {"fire": False}
            if hit["fire"]:
                try:
                    from experiments.r1.room_graph.answer import solve as rg_solve

                    ans = rg_solve(path, question)
                except Exception as e:  # noqa: BLE001
                    ans = None
                    why = f"room_graph failed: {type(e).__name__}"
                else:
                    why = "room_graph gave no answer"
                if ans is not None and ans.value is not None:
                    ans.confidence = min(float(ans.confidence or 0.0), CONF_CAP)
                    ans.trace = [f"route: {hit['why']} -> room graph (R1; pretrained CubiCasa5K segmentation, "
                                 "CC BY-NC 4.0)", *ans.trace]
                    ans.solver = "pipeline/room_graph"
                    try:
                        ans.cost.wall_seconds = round(time.perf_counter() - t0, 4)
                    except Exception:  # noqa: BLE001
                        pass
                    return ans
                out = super().solve(path, question)
                out.trace = [f"route: {hit['why']}; {why}; fell back", *out.trace]
                return out
        return super().solve(path, question)


if __name__ == "__main__":
    from stoa.eval.runner import main

    args = sys.argv[1:]
    if "--solver" not in args:
        args = ["--solver", "pipeline_rg", *args]
    raise SystemExit(main(args))
