"""Run stoa.eval with one LLM component moved to another backend (R2 bake-off harness; no repo code changed).

  python experiments/r2/eval_backend.py --agent local2 [--translate local2] -- <stoa.eval args>

--agent B      the general agent's planner (stoa.router.agent.Agent default backend) -> B
--translate B  stoa.llm.to_english default backend -> B
Everything else (atomic solvers, LoRA counts, rules) stays on the shared :8001.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ap = argparse.ArgumentParser()
ap.add_argument("--agent")
ap.add_argument("--translate")
a, rest = ap.parse_known_args()
rest = [x for x in rest if x != "--"]

if a.agent:
    import stoa.router.agent as A

    d = list(A.Agent.__init__.__defaults__)
    d[1] = a.agent  # (ask_fn, backend, max_steps)
    A.Agent.__init__.__defaults__ = tuple(d)
if a.translate:
    import stoa.llm as L

    kw = dict(L.to_english.__kwdefaults__ or {})
    if "backend" in kw:
        kw["backend"] = a.translate
        L.to_english.__kwdefaults__ = kw
    else:
        d = list(L.to_english.__defaults__ or ())
        names = L.to_english.__code__.co_varnames[:L.to_english.__code__.co_argcount]
        i = names.index("backend") - (len(names) - len(d))
        d[i] = a.translate
        L.to_english.__defaults__ = tuple(d)

from stoa.eval.runner import main  # noqa: E402

sys.exit(main(rest))
