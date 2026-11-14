"""Answer one question about a file the visitor uploaded in the demo (not part of the dataset).

Called by the Vite middleware (web/mock/stoaApi.ts, POST /api/ask on an `upload/...` path), one process per
question (the pipeline loads in ~0.3 s):

    echo '{"abs": "/tmp/stoa-uploads/ab12/plan.png", "virtual": "upload/ab12/plan.png", "question": "..."}' \
        | $JUNCTION_VENV/bin/python web/server/ask_upload.py

The API (stoa/api.py) only accepts dataset paths, so this does what its POST /ask does (solver, cost meter, intent,
compose plan) for an absolute path outside the dataset. The pipeline routes such a file by its extension (no
template, no vector/IFC twin: the hidden set's "different" drawings). Evidence that points at the uploaded file is
renamed to the virtual path the browser knows (also evidence on a file uploaded TOGETHER with it, in the same folder:
a sheet's IFC model). Prints the Answer as JSON on stdout (solvers' prints go to stderr).
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from pathlib import Path


def main() -> None:
    req = json.loads(sys.stdin.read() or "{}")
    abs_path, virtual, question = req["abs"], req["virtual"], str(req.get("question", "")).strip()
    solver_name, solver_args = req.get("solver") or "pipeline", req.get("solver_args") or {}
    # run from the repo root so stoa/ and experiments/ import like they do for the API
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    os.chdir(root)
    with contextlib.redirect_stdout(sys.stderr):
        from stoa.contract import Answer, CostMeter
        from stoa.solvers import get_solver

        solver = get_solver(solver_name, **solver_args)
        t0 = time.perf_counter()
        with CostMeter() as meter:
            ans = solver.solve(abs_path, question)
        if not isinstance(ans, Answer):
            ans = Answer.model_validate(ans)
        rep, met = ans.cost.model_dump(), meter.cost.model_dump()
        ans.cost = ans.cost.model_validate({k: max(rep.get(k, 0) or 0, met.get(k, 0) or 0) for k in set(rep) | set(met)})
        if not ans.cost.wall_seconds:
            ans.cost.wall_seconds = round(time.perf_counter() - t0, 4)
        out = ans.model_dump()
        name, folder = Path(abs_path).name, Path(abs_path).parent
        vdir = virtual.rsplit("/", 1)[0]
        for e in out.get("evidence") or []:
            f = str(e.get("file") or "")
            if not f or f == abs_path or Path(f).name == name:
                e["file"] = virtual
            elif Path(f).is_absolute() and Path(f).parent == folder:  # a file uploaded with it (the sheet's model)
                e["file"] = f"{vdir}/{Path(f).name}"
        # the browser knows the folder as upload/<id>: no temp paths in the reasoning shown to the visitor
        out["trace"] = [str(t).replace(str(folder), vdir) for t in out.get("trace") or []]
        try:
            from stoa.data import source_of
            from stoa.router.compose import decompose
            from stoa.router.intent import parse

            out["intent"] = parse(question).to_dict()
            plan = decompose(source_of(abs_path), question)
            if plan is not None:
                out["plan"] = {"op": plan.op, "parts": plan.labels, "sub_questions": plan.subs}
        except Exception:  # noqa: BLE001
            pass
    print(json.dumps(out, default=str))


if __name__ == "__main__":
    main()
