"""The contract every solver implements. Changing this file needs a DECISION from S0.

    solver.solve(path, question) -> Answer

`path` is always dataset-relative, exactly as in questions.jsonl, e.g.
"data/cubicasa5k/colorful-10052.png". Use `stoa.data.abspath(path)` to open the file.

An Answer with `value=None` is a refusal: allowed but discouraged (Stoa: "refusing is not useful").
Prefer a best estimate with a low `confidence`, plus `assumptions` and `missing`.

Cost: LLM clients call `record_cost(...)`; the eval wraps every solve() in a `CostMeter`, so token counts
and API calls are attributed to the question automatically. Solvers may also fill `Answer.cost` directly.
"""

from __future__ import annotations

import contextvars
import threading
import time
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

BBoxSpace = Literal["pdf_pt", "image_px"]
Value = float | int | str | None


class Evidence(BaseModel):
    """One piece of evidence a human can check in seconds.

    - 2D: `file` + `page` + `bbox` ([x0, y0, x1, y1]) in `bbox_space`:
        "pdf_pt"   = PDF points in the page's own coordinate space (PyMuPDF `page.rect`, origin top-left,
                     y down, unrotated page units as PyMuPDF reports them).
        "image_px" = pixels of the image file as stored on disk (origin top-left, y down).
      A point is a degenerate box (x0 == x1, y0 == y1).
    - 3D: `file` (the .ifc) + `ifc_guid` (GlobalId); `page`/`bbox` stay None.
    - `note`: short human-readable label ("window 3", "Kitchen 12.4 m2", "row U01").
    """

    model_config = ConfigDict(extra="forbid")

    file: str  # dataset-relative, like the question's path ("data/<source>/...")
    page: int | None = None  # 0-based page index for PDFs; None for images / IFC
    bbox: list[float] | None = None  # [x0, y0, x1, y1]
    bbox_space: BBoxSpace | None = None  # required when bbox is set
    ifc_guid: str | None = None
    note: str = ""


class Cost(BaseModel):
    """What answering one question cost. All fields default to 0; add more fields if useful (extra allowed)."""

    model_config = ConfigDict(extra="allow")

    llm_tokens_in: int = 0
    llm_tokens_out: int = 0
    gpu_seconds: float = 0.0  # GPU time attributable to this question (local model server or own model)
    api_calls: int = 0  # calls to hosted APIs (NVIDIA etc.); local-server calls are NOT api_calls
    api_tokens_in: int = 0  # the part of llm_tokens_in that went to hosted APIs (priced in the cost score)
    api_tokens_out: int = 0
    llm_calls: int = 0  # all LLM/VLM calls, local or hosted
    wall_seconds: float = 0.0  # filled by the eval if left 0

    # Mapping view (backward compatibility with code written when cost was a dict, e.g.
    # `{**meter_dict, **(ans.cost or {})}`): only NON-ZERO fields are exposed, and an all-zero Cost is falsy,
    # so a default Cost never overwrites real numbers in such a merge.
    def keys(self):
        return [k for k, v in self.model_dump().items() if v]

    def __getitem__(self, key):
        return self.model_dump()[key]

    def __bool__(self) -> bool:
        return any(bool(v) for v in self.model_dump().values())

    def add(self, other: "Cost") -> "Cost":
        d = self.model_dump()
        for k, v in other.model_dump().items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                d[k] = d.get(k, 0) + v
        return Cost.model_validate(d)


class Answer(BaseModel):
    """What every solver returns. JSON-serialisable via `answer.model_dump()` / `model_dump_json()`."""

    # validate_assignment: `ans.cost = {...}` or `ans.evidence = [...]` after construction is coerced/checked
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    value: Value = None  # None = abstain
    unit: str | None = None  # "count", "m2", "m3", "m", "ft2", ... or None for text
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)  # short strings: what the solver did, step by step
    solver: str = ""
    assumptions: list[str] = Field(default_factory=list)  # "no scale bar; assumed door width 0.9 m"
    missing: list[str] = Field(default_factory=list)  # what would make the answer certain ("no IFC sibling")
    cost: Cost = Field(default_factory=Cost)

    @property
    def abstained(self) -> bool:
        return self.value is None

    @classmethod
    def abstain(cls, solver: str, reason: str, trace: list[str] | None = None,
                missing: list[str] | None = None) -> "Answer":
        """A refusal. Discouraged: prefer a low-confidence estimate with assumptions/missing."""
        return cls(value=None, confidence=0.0, solver=solver, trace=[*(trace or []), f"abstain: {reason}"],
                   missing=list(missing or [reason]))


@runtime_checkable
class Solver(Protocol):
    """Implement this and register it with `@register` from `stoa.solvers`."""

    name: str

    def can_handle(self, path: str, question: str) -> bool: ...

    def solve(self, path: str, question: str) -> Answer: ...


# --- cost metering ----------------------------------------------------------------------------------
_CURRENT_METER: contextvars.ContextVar["CostMeter | None"] = contextvars.ContextVar("stoa_cost_meter", default=None)


class CostMeter:
    """Accumulates cost recorded with `record_cost` inside a `with` block (per thread / context).

        with CostMeter() as m:
            ans = solver.solve(path, question)
        m.cost  # Cost(llm_tokens_in=..., ...)
    Nested meters all receive the record (an outer meter sees inner costs too).
    """

    def __init__(self):
        self.cost = Cost()
        self._lock = threading.Lock()
        self._parent: CostMeter | None = None
        self._token = None
        self._t0 = 0.0

    def __enter__(self) -> "CostMeter":
        self._parent = _CURRENT_METER.get()
        self._token = _CURRENT_METER.set(self)
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc) -> None:
        _CURRENT_METER.reset(self._token)
        self.wall_seconds = time.perf_counter() - self._t0

    def _add(self, c: Cost) -> None:
        with self._lock:
            self.cost = self.cost.add(c)
        if self._parent is not None:
            self._parent._add(c)


def record_cost(**fields) -> None:
    """Call from LLM/VLM clients after each call, e.g.
    record_cost(llm_tokens_in=usage.prompt_tokens, llm_tokens_out=usage.completion_tokens, llm_calls=1,
                gpu_seconds=elapsed)                       # local server
    record_cost(llm_tokens_in=..., llm_tokens_out=..., api_tokens_in=..., api_tokens_out=..., api_calls=1,
                llm_calls=1)                               # hosted API
    No-op outside a CostMeter. Thread-safe. Note: work in a thread pool started *inside* solve() runs in a
    fresh context; wrap it with `contextvars.copy_context().run(...)` to keep the meter."""
    m = _CURRENT_METER.get()
    if m is not None:
        m._add(Cost(**fields))
