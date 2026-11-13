"""Registers `agent` (W4): the general tool-using agent alone, with the pipeline's atomic cascade as its `ask` tool."""
from stoa.solvers import register
from stoa.solvers.base import BaseSolver


@register("agent")
class AgentSolver(BaseSolver):
    def __init__(self, backend: str = "local", max_steps: int | str = 7, **kwargs):
        super().__init__(**kwargs)
        from stoa.pipeline import Pipeline
        from stoa.router.agent import Agent

        self._pipe = Pipeline(agent=0)
        self._agent = Agent(ask_fn=lambda p, q: self._pipe._solve_atomic(p, q, allow_agent=False),
                            backend=backend, max_steps=int(max_steps))

    def solve(self, path, question):
        return self._agent.solve(path, question)
