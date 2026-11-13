"""Convenience base class for solvers (optional; any object with name/can_handle/solve works)."""

from __future__ import annotations

from pathlib import Path

from stoa.contract import Answer
from stoa.data import abspath, siblings, source_of


class BaseSolver:
    name: str = "base"
    #: file extensions this solver can read (lowercase, with dot); empty = any
    extensions: tuple[str, ...] = ()
    #: dataset sources this solver targets; empty = any
    sources: tuple[str, ...] = ()

    def __init__(self, **kwargs):
        self.options = kwargs

    def can_handle(self, path: str, question: str) -> bool:
        if self.sources and source_of(path) not in self.sources:
            return False
        if self.extensions and Path(path).suffix.lower() not in self.extensions:
            return False
        return True

    def solve(self, path: str, question: str) -> Answer:  # pragma: no cover - abstract
        raise NotImplementedError

    # helpers -------------------------------------------------------------
    def abstain(self, reason: str, trace: list[str] | None = None) -> Answer:
        return Answer.abstain(self.name, reason, trace)

    @staticmethod
    def abspath(path: str) -> Path:
        return abspath(path)

    @staticmethod
    def siblings(path: str) -> dict[str, str]:
        return siblings(path)
