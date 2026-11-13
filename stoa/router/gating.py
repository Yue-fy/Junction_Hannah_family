"""Per-(source, intent) gating: which solver answers which kind of question, measured on TRAIN (S0 D4).

The table lives in `stoa/router/gating.json` (committed; built by `python -m stoa.router.calibrate`). It holds
no question text, only intent keys ("count:window:drawing") with each solver's hit rate on a train sample:

    {"meta": {...}, "entries": {"cubicasa5k|count:window:drawing":
        {"n": 40, "acc": {"prior": 0.12, "vlm_direct": 0.15}, "cost_usd": {"vlm_direct": 0.0006}}}}

`plan(source, key, available)` -> solvers to try in order. A solver is kept only if it beats the prior on the
train sample by `margin` (default 3 points); the prior is always last. Unknown keys (templates the hidden test
may bring) get no gate: the router falls back to routing by file type, and the general path.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

GATING_PATH = Path(__file__).with_name("gating.json")
_LOCK = threading.Lock()
_CACHE: dict | None = None


def load(path: Path | None = None) -> dict:
    global _CACHE
    with _LOCK:
        if path is not None:
            return json.loads(Path(path).read_text()) if Path(path).exists() else {"entries": {}}
        if _CACHE is None:
            _CACHE = json.loads(GATING_PATH.read_text()) if GATING_PATH.exists() else {"entries": {}}
        return _CACHE


def entry(source: str, key: str) -> dict | None:
    return load().get("entries", {}).get(f"{source}|{key}")


def plan(source: str, key: str, candidates: list[str], margin: float = 0.03, min_n: int = 15) -> tuple[list[str], dict | None]:
    """Order `candidates` (routing order, cheapest first) by the train gate.

    Returns (solvers to try, gate entry or None). With a gate: solvers measured on this key are kept only if
    acc > prior + margin, sorted by accuracy (cheaper first on ties within 1 point); solvers the gate has not
    measured (e.g. landed after calibration) keep their routing order and go first if deterministic.
    """
    e = entry(source, key)
    if not e or e.get("n", 0) < min_n:
        return list(candidates), None
    acc = e.get("acc", {})
    p = acc.get("prior", 0.0)
    measured = [c for c in candidates if c in acc]
    unmeasured = [c for c in candidates if c not in acc]
    good = [c for c in measured if acc[c] > p + margin]
    good.sort(key=lambda c: (-round(acc[c] * 100), candidates.index(c)))
    return unmeasured + good, e
