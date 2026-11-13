"""Command line: ask one question about one drawing and print the answer with its evidence.

    $JUNCTION_VENV/bin/python -m stoa.cli ask data/cubicasa5k/colorful-10052.png "How many windows?"
    $JUNCTION_VENV/bin/python -m stoa.cli ask <path> "<question>" --solver vlm_direct --json
    $JUNCTION_VENV/bin/python -m stoa.cli intent "Wie viele Fenster sind auf diesem Grundriss eingezeichnet?"
"""

from __future__ import annotations

import argparse
import json
import sys

from stoa.contract import CostMeter


def _kv(items):
    out = {}
    for it in items or []:
        k, _, v = it.partition("=")
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m stoa.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("ask", help="answer a question about a drawing")
    a1.add_argument("path", help="dataset-relative path, e.g. data/swiss_dwellings/<file>.pdf")
    a1.add_argument("question")
    a1.add_argument("--solver", default="pipeline")
    a1.add_argument("--solver-arg", action="append", default=[])
    a1.add_argument("--json", action="store_true", help="print the full Answer JSON")
    a2 = sub.add_parser("intent", help="show the parsed intent of a question")
    a2.add_argument("question")
    a = ap.parse_args(argv)

    if a.cmd == "intent":
        from stoa.router.intent import parse

        print(json.dumps(parse(a.question).to_dict(), ensure_ascii=False, indent=1))
        return 0

    from stoa.data import abspath
    from stoa.solvers import get_solver

    if not abspath(a.path).is_file():
        print(f"no such file: {a.path}", file=sys.stderr)
        return 2
    solver = get_solver(a.solver, **_kv(a.solver_arg))
    with CostMeter() as m:
        ans = solver.solve(a.path, a.question)
    rep, met = ans.cost.model_dump(), m.cost.model_dump()
    ans.cost = ans.cost.model_validate({k: max(rep.get(k, 0) or 0, met.get(k, 0) or 0) for k in set(rep) | set(met)})
    if a.json:
        print(ans.model_dump_json(indent=1))
        return 0
    print(f"answer: {ans.value} {ans.unit or ''}   (confidence {ans.confidence:.2f}, solver {ans.solver})")
    for x in ans.assumptions:
        print(f"  assumes: {x}")
    for x in ans.missing:
        print(f"  missing: {x}")
    for e in ans.evidence[:20]:
        where = f"guid {e.ifc_guid}" if e.ifc_guid else f"page {e.page} bbox {[round(v, 1) for v in (e.bbox or [])]} {e.bbox_space or ''}"
        print(f"  evidence: {e.file} {where}  {e.note}")
    if len(ans.evidence) > 20:
        print(f"  ... {len(ans.evidence) - 20} more evidence items")
    print("trace:")
    for t in ans.trace:
        print(f"  - {t}")
    c = ans.cost
    print(f"cost: {c.llm_calls} LLM calls ({c.api_calls} hosted), tokens {c.llm_tokens_in}/{c.llm_tokens_out}, "
          f"GPU {c.gpu_seconds:.2f}s, wall {c.wall_seconds:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
