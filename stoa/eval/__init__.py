"""Evaluation: `python -m stoa.eval --solver <name> --split smoke|dev|test [--limit N] [--source S]`."""

from stoa.eval.scoring import score
from stoa.eval.splits import load_split

__all__ = ["score", "load_split"]
