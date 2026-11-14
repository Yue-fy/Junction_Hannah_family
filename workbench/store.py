"""Append-only JSONL files under $JUNCTION_SHARED/human/ (audit.jsonl, questions.jsonl, rules.jsonl)."""

from __future__ import annotations

import fcntl
import json
import os
import time
from pathlib import Path

DEFAULT_SHARED = "/home/fangy4/work/projects/junction-shared"


def human_dir() -> Path:
    """$JUNCTION_SHARED/human, or $WORKBENCH_HUMAN_DIR (tests: keep test clicks out of the expert's files)."""
    if os.environ.get("WORKBENCH_HUMAN_DIR"):
        return Path(os.environ["WORKBENCH_HUMAN_DIR"])
    return Path(os.environ.get("JUNCTION_SHARED", DEFAULT_SHARED)) / "human"


def append(name: str, row: dict) -> dict:
    """Append one row (with a server timestamp) to human/<name>.jsonl; returns the row as written."""
    row = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), **row}
    p = human_dir() / f"{name}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False, default=str) + "\n"
    with open(p, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(line)
        f.flush()
        fcntl.flock(f, fcntl.LOCK_UN)
    return row


def read(name: str) -> list[dict]:
    p = human_dir() / f"{name}.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out
