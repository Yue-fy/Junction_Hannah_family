"""raster_cc5k: cubicasa symbol counts (windows, doors, WC seats, sinks) from the pretrained CubiCasa5K
multi-task model (Kalervo et al., SCIA 2019; weights CC BY-NC 4.0). DECISIONS D8.

How it answers: connected components of the model's icon map (settings frozen on original-CC5K val
drawings). Evidence = one image_px box per counted symbol. Confidence = P(exact | template, count bucket)
fitted on CC5K val. Lookup order:
  1. precomputed counts for every dataset drawing: $JUNCTION_SHARED/artifacts/R1/cc5k_counts.jsonl
  2. live CPU inference: $CC5K_PYTHON -I experiments/r1/cc5k_model/predict.py IMG (needs torch; ~1-3 s)
  3. otherwise abstain (value None) so the cascade falls through.
No GPU, no LLM tokens. Env vars (docs/CONTRACT.md): CC5K_WEIGHTS, CC5K_PYTHON, CC5K_THREADS.

Leak rule (D3/D8): the model trained on the original CubiCasa5K train list (84% of our cubicasa drawings).
Quote its accuracy from `cc5k_heldout` only; dev/test numbers with it are labelled inflated (measured: train-list
accuracy is within a few points of held-out, research/methods.md §3a).
"""
from __future__ import annotations

import importlib.util
import os
import threading
from pathlib import Path

from stoa.contract import Answer
from stoa.solvers import register
from stoa.solvers.base import BaseSolver

_ADAPTER = Path(__file__).resolve().parents[3] / "experiments" / "r1" / "cc5k_model" / "adapter.py"
_mod = None
_lock = threading.Lock()


def _adapter():
    global _mod
    if _mod is None:
        with _lock:  # eval runs solve() in threads: publish the module only once it is fully executed
            if _mod is None:
                spec = importlib.util.spec_from_file_location("r1_cc5k_adapter", _ADAPTER)
                m = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(m)
                _mod = m
    return _mod


@register("raster_cc5k")
class RasterCC5KSolver(BaseSolver):
    extensions = (".png", ".jpg", ".jpeg")

    def can_handle(self, path: str, question: str) -> bool:
        if not super().can_handle(path, question) or not _ADAPTER.exists():
            return False
        return _adapter().template_of(question) is not None

    def solve(self, path: str, question: str) -> Answer:
        try:
            a = _adapter()
        except Exception as e:  # noqa: BLE001
            return self.abstain(f"cc5k adapter unavailable: {e}")
        t = a.template_of(question)
        if t is None:
            return self.abstain("not a windows/doors/WC seats/sinks count question")
        from stoa.data import source_of
        foreign = source_of(path) != "cubicasa5k"
        if foreign and t != "windows":
            # measured on unseen styles: swiss PNG twins doors 0%, WC seats 7%, sinks 34%; ResBIM Revit doors 0-12%
            return self.abstain(f"the CubiCasa5K detector does not transfer to this drawing style for {t} (unseen styles: "
                                "doors 0%, WC seats 7%, sinks 34% exact); only windows transfer")
        try:
            ans = a.RasterCC5K().answer_template(path, t)
        except Exception as e:  # noqa: BLE001 - no cache entry and no working torch env / weights
            return self.abstain(f"no cached CC5K counts and live inference failed: {type(e).__name__}: {str(e)[:120]}",
                                trace=[f"CC5K_PYTHON={os.environ.get('CC5K_PYTHON', a.PY)}"])
        ans.solver = self.name
        ans.trace.append("pretrained CubiCasa5K multi-task model (Kalervo et al. 2019), weights CC BY-NC 4.0")
        if foreign:  # windows on a non-CubiCasa style: exact on 26% of swiss PNG plans, 77% of ResBIM Revit plans
            ans.confidence = 0.26
            ans.assumptions = [*ans.assumptions, "drawing style unlike CubiCasa5K: windows transfer (exact on 26% of swiss "
                                                 "PNG plans and 77% of ResBIM plans); the CubiCasa-calibrated "
                                                 "confidence and range do not apply"]
            return ans
        try:  # calibrated range (leak-safe: fitted on CC5K val, coverage checked on CC5K test; crosscheck.py)
            from stoa.solvers.raster_cc5k.crosscheck import detector_interval
            rng = detector_interval(t, int(ans.value)) if ans.value is not None else None
        except Exception:  # noqa: BLE001 - no table: no range
            rng = None
        if rng is not None:
            ans.trace.append(f"interval90: [{rng[0]}, {rng[1]}]")
            if rng[0] < rng[1]:
                ans.missing = [*ans.missing, f"exact count not certain: 90% range {rng[0]}–{rng[1]} (held the true "
                                             f"count ~90% of the time on held-out CubiCasa5K drawings)"]
        return ans
