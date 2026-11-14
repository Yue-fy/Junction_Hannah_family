"""Run stoa.eval with the proposed stoa/data.py hook (R2 10:30, for F): a raster OUTSIDE the dataset folders with no IFC
model next to it gets source 'cubicasa5k' when stoa.style.guess_style says CubiCasa at p >= 0.8, so every CubiCasa
reader (LoRA cc-v2 + its per-concept gate, raster_cc5k, the cubicasa route) applies to an uploaded apartment plan.
Measurement only (monkeypatch); the real change belongs in stoa/data.py (F).

    PYTHONPATH=. $JUNCTION_VENV/bin/python experiments/r2/style/eval_hooked.py --solver pipeline --split <path> ...
"""
import functools
import sys
from pathlib import Path

import stoa.data as D


@functools.lru_cache(maxsize=4096)
def _outside_source_cached(path: str, folder_mtime: int) -> str:
    if D.ifc_model_for(path):
        return "ifc_models"
    if Path(path).suffix.lower() in (".png", ".jpg", ".jpeg"):
        try:
            from stoa.style import guess_style

            s, p = guess_style(path)
            if s == "cubicasa5k" and p >= 0.8:
                return "cubicasa5k"
        except Exception:  # noqa: BLE001
            pass
    return "unknown"


D._outside_source_cached = _outside_source_cached

if __name__ == "__main__":
    from stoa.eval.runner import main

    sys.exit(main())
