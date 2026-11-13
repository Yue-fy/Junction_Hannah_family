"""The contract every solver implements. Changing this file needs a DECISION from S0.

    solver.solve(path, question) -> Answer

`path` is always dataset-relative, exactly as in questions.jsonl, e.g.
"data/cubicasa5k/colorful-10052.png". Use `stoa.data.abspath(path)` to open the file.

An Answer with `value=None` is an abstention (counts as wrong for accuracy, reported as coverage).
"""

from __future__ import annotations

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


class Answer(BaseModel):
    """What every solver returns. JSON-serialisable via `answer.model_dump()` / `model_dump_json()`."""

    model_config = ConfigDict(extra="forbid")

    value: Value = None  # None = abstain
    unit: str | None = None  # "count", "m2", "m3", "m", "ft2", ... or None for text
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)  # short strings: what the solver did, step by step
    solver: str = ""

    @property
    def abstained(self) -> bool:
        return self.value is None

    @classmethod
    def abstain(cls, solver: str, reason: str, trace: list[str] | None = None) -> "Answer":
        return cls(value=None, confidence=0.0, solver=solver, trace=[*(trace or []), f"abstain: {reason}"])


@runtime_checkable
class Solver(Protocol):
    """Implement this and register it with `@register` from `stoa.solvers`."""

    name: str

    def can_handle(self, path: str, question: str) -> bool: ...

    def solve(self, path: str, question: str) -> Answer: ...
