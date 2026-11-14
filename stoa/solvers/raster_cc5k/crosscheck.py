"""CC5K detections as EVIDENCE and CROSS-CHECK for another solver's cubicasa count (D11; R1).

The counting LoRA (vlm_lora) answers cubicasa counts best overall but returns no boxes. The pretrained CubiCasa5K
model's detections are precomputed for every dataset drawing (artifacts/R1/cc5k_counts.jsonl), so attaching them
costs a dict lookup: no torch, no GPU, no LLM call.

    from stoa.solvers.raster_cc5k.crosscheck import check
    ans = check(path, intent.key, ans)          # returns a NEW Answer; the input is not modified

What it does for a drawing-scope count key (count:<target>:drawing) on a drawing with cached detections:
  1. evidence: one image_px box per detected symbol / segmented room, added when the answer has no located evidence
     (notes "window 2 of 5 (CC5K detector)").
  2. cross-check line in the trace and on the first evidence note, in the pipeline's format:
     "cross-check: vlm_lora 4 = CC5K detector 4 ✓" / "cross-check: vlm_lora 4 ≠ CC5K detector 3 ✗".
     On disagreement a `missing` line says which count the boxes show.
  3. arbitration (only targets in ARBITRATE = window, wc): when the two disagree and the detector's calibrated
     confidence is higher than the other solver's own probability (p(answer digits) from its trace, else its
     confidence), the detector's count becomes the answer, with the detector's confidence.
     Measured (experiments/r1/cc5k_evidence/policy.py; chosen on train_gate, which the LoRA never saw):
       windows  train_gate 15.0 → 32.5 (+17.5 [+5.0, +32.5]); dev 18.5 → 38.0 (+19.4 [+8.3, +30.6])
       WC seats train_gate 85.0 → 90.0 (+5.0 n.s.);           dev 75.7 → 81.3 (+5.6 [−1.9, +13.1])
       doors were +5.0 / +3.5 / −11.1 (train_gate / dev / leak-free 50 Qs) → not arbitrated; sinks and rooms lose
       → never arbitrated (the LoRA keeps its answer; the detector only adds boxes and the ✓/✗ line).
     Leak note (D3/D8): dev/train_gate drawings are mostly in CC5K's original train list. Measured memorisation is
     small (KNOWLEDGE 01:33); on the leak-free-for-both 50 Qs windows were +13.3 and WC +5.9 (n≈15 each, noise ±25).
  4. confidence, for answers of the solvers listed in crosscheck_calib.json (vlm_lora): the pipeline gives them a
     constant per-key train hit rate, and agreement with the detector is informative relative to that (likelihood
     ratio up to 6.7 for WC seats), so the confidence becomes P(right | target, agree / kept-despite-disagreement)
     fitted on train_gate (fit_calib.py; (k+1)/(n+2), capped 0.95); a switched answer takes the detector's own
     calibrated confidence. Other solvers keep their confidence (not measured). Relative to the LoRA's OWN
     p(answer digits) agreement adds little (dev AUROC 0.864 → 0.868), and a noisy-OR on agreement is wrong here
     (the two are not independent; dev ECE 0.040 → 0.052).
  5. range, for the same solvers: a calibrated integer interval for the true count (Stoa: "a best estimate with a
     calibrated confidence"), [min(answer, detector) - lo, max(answer, detector) + hi] with split-conformal margins
     per group (openings: window, door | fixtures: wc, sink | rooms) x agree/disagree, fitted on train_gate
     (experiments/r1/count_interval/interval.py). 90% nominal → covers the true count on 93% of dev answers (mean
     width 3.9 values) and 97% of the leak-free-for-both drawings (3.2). Fixtures and rooms: the two counts' range
     (margins 0); windows/doors: widened by −1/+5 (both counters miss symbols). Machine line in the trace
     "interval90: [lo, hi]"; a human line goes to `missing` when lo < hi. interval() is public for the composer
     (e.g. a comparison is sure only when the two ranges don't overlap).
No-op (returns a copy with at most one trace line) when: the key is not a drawing-scope count of a supported target,
the value is not an integer, the answer already comes from raster_cc5k, or the drawing has no cached detections and
live inference is off (default; pass live=True or set CC5K_LIVE=1 to run predict.py via CC5K_PYTHON, ~1–3 s CPU).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from pathlib import Path

from stoa.contract import Answer, Evidence

SHARED = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")
DATA = os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")
CACHE = Path(os.environ.get("CC5K_COUNTS", os.path.join(SHARED, "artifacts", "R1", "cc5k_counts.jsonl")))
PREDICT = Path(__file__).resolve().parents[3] / "experiments" / "r1" / "cc5k_model" / "predict.py"

# intent target -> (record group, class key, noun for notes, what produced it)
TARGETS = {
    "window": ("counts", "windows", "window", "CC5K detector"),
    "door": ("counts", "doors", "door", "CC5K detector"),
    "wc": ("counts", "wc_seats", "toilet", "CC5K detector"),
    "sink": ("counts", "sinks", "sink", "CC5K detector"),
    "bedroom": ("rooms", "bedrooms", "bedroom", "CC5K room segmentation"),
    "balcony": ("rooms", "balconies", "balcony", "CC5K room segmentation"),
    "bathroom": ("rooms", "bathrooms", "bathroom", "CC5K room segmentation"),
    "kitchen": ("rooms", "kitchens", "kitchen", "CC5K room segmentation"),
}
ARBITRATE = frozenset({"window", "wc"})
GAIN = {"window": "windows: train_gate +17.5, dev +19.4 pts over the LoRA alone",
        "wc": "WC seats: train_gate +5.0, dev +5.6 pts over the LoRA alone"}
_P_RX = re.compile(r"p\(answer digits\) = ([0-9.]+)")
_CALIB_PATH = Path(__file__).with_name("crosscheck_calib.json")
_calib: dict | None = None


def _table() -> dict:
    global _calib
    if _calib is None:
        try:
            _calib = json.loads(_CALIB_PATH.read_text())
        except Exception:  # noqa: BLE001 - no table: confidences stay as they are
            _calib = {"applies_to_solvers": [], "targets": {}}
    return _calib

_cache: dict | None = None
_lock = threading.Lock()


def _load() -> dict:
    global _cache
    if _cache is None:
        with _lock:
            if _cache is None:
                c = {}
                if CACHE.exists():
                    with open(CACHE) as f:
                        for line in f:
                            d = json.loads(line)
                            c[d["path"]] = d
                _cache = c
    return _cache


def _rel(path: str) -> str:
    if path.startswith("data/"):
        return path
    try:
        return os.path.relpath(path, DATA)
    except ValueError:
        return path


def detections(path: str, live: bool | None = None) -> dict | None:
    """The cached detector record for a drawing ({"path", "size", "counts": {...}, "rooms": {...}, "cc5k_list"}),
    or None. live=None -> env CC5K_LIVE=1 decides; live inference needs CC5K_PYTHON (torch) and CC5K_WEIGHTS."""
    rel = _rel(path)
    d = _load().get(rel)
    if d is not None:
        return d
    if live is None:
        live = os.environ.get("CC5K_LIVE", "0") == "1"
    if not live or not PREDICT.exists():
        return None
    py = os.environ.get("CC5K_PYTHON", "/data/User/fangy4/envs/junction-train/bin/python")
    full = path if os.path.isabs(path) else os.path.join(DATA, path)
    try:
        out = subprocess.run([py, "-I", str(PREDICT), full], capture_output=True, text=True, timeout=300)
        d = json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001 - no torch env / weights / bad image: no cross-check
        return None
    d.update(path=rel, cc5k_list="unknown", live=True)
    with _lock:
        _load()[rel] = d
    return d


def _target(key_or_target: str | None) -> str | None:
    if not key_or_target:
        return None
    parts = key_or_target.split(":")
    if len(parts) == 3:  # intent key count:<target>:<scope>; only whole-drawing counts match the detections
        if parts[0] != "count" or parts[2] != "drawing":
            return None
        return parts[1] if parts[1] in TARGETS else None
    return key_or_target if key_or_target in TARGETS else None


def _int(v) -> int | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(round(f)) if abs(f - round(f)) < 1e-6 else None


def _own_p(ans: Answer) -> float:
    for t in reversed(ans.trace or []):
        m = _P_RX.search(t)
        if m:
            return float(m.group(1))
    return float(ans.confidence or 0.0)


def interval(target: str, value: int, detector: int, level: int = 90) -> tuple[int, int] | None:
    """Calibrated range for the true count given another solver's `value` and the CC5K `detector` count (both ints),
    or None when no table exists for the target/level. level 90 or 80 (nominal coverage, %)."""
    t = _table().get("intervals") or {}
    g = (t.get("groups") or {}).get(target)
    m = (t.get(str(level)) or {}).get(g or "", {}).get("agree" if value == detector else "disagree")
    if m is None:
        return None
    lo, hi = int(m[0]), int(m[1])
    return max(0, min(value, detector) - lo), max(value, detector) + hi


def check(path: str, key: str | None, ans: Answer, source: str | None = None, live: bool | None = None,
          arbitrate: bool = True) -> Answer:
    """See the module docstring. `key`: intent key ("count:window:drawing") or a bare target ("window").
    `source`: the name to print for the other solver (default: ans.solver)."""
    out = ans.model_copy(deep=True)
    tgt = _target(key)
    v = _int(ans.value)
    if tgt is None or v is None or "raster_cc5k" in (ans.solver or ""):
        return out
    d = detections(path, live)
    if d is None:
        out.trace = [*out.trace, "cc5k cross-check: no cached CubiCasa5K detections for this drawing"]
        return out
    grp, cls, noun, what = TARGETS[tgt]
    rec = (d.get(grp) or {}).get(cls)
    if rec is None:
        return out
    det, boxes = int(rec["count"]), rec.get("boxes") or []
    det_conf = rec.get("confidence")  # symbols only (calibrated on original CC5K val); rooms have none
    src = source or (ans.solver or "solver").replace("pipeline/", "")
    agree = v == det
    note = f"cross-check: {src} {v} {'=' if agree else '≠'} {what} {det} {'✓' if agree else '✗'}"
    trace = [note]
    switched = False
    if not agree and arbitrate and tgt in ARBITRATE and det_conf is not None:
        p = _own_p(ans)
        if det_conf > p:
            switched = True
            out.value, out.unit, out.confidence = det, "count", round(float(det_conf), 3)
            out.solver = f"{ans.solver}+raster_cc5k" if ans.solver else "raster_cc5k"
            trace.append(f"arbitration: {what} (conf {det_conf:.2f}) is surer than {src} (p {p:.2f}) → answer {det} "
                         f"(rule measured on train_gate/dev: {GAIN[tgt]})")
            out.missing = [*out.missing, f"{src} counted {v}, the {what} {det}: the boxes show the detector's {det}; "
                                         f"the two disagree, so check the drawing"]
        else:
            trace.append(f"arbitration: kept {src} {v} (p {p:.2f} ≥ {what} conf {det_conf:.2f})")
    if not agree and not switched:
        out.missing = [*out.missing, f"{src} says {v}, the {what} found {det} (boxes show the {det} found)"]
    tab = _table()
    if not switched and any(n in (ans.solver or "") for n in tab.get("applies_to_solvers", [])):
        c = tab.get("targets", {}).get(tgt, {}).get("agree" if agree else "kept")
        if c is not None:
            trace.append(f"confidence {out.confidence:.2f} → {c:.2f}: P(right | {src} and {what} "
                         f"{'agree' if agree else 'disagree'}) on train_gate, which {src} never saw")
            out.confidence = float(c)
    if any(n in (ans.solver or "") for n in tab.get("applies_to_solvers", [])):
        rng = interval(tgt, v, det)
        if rng is not None:
            trace.append(f"interval90: [{rng[0]}, {rng[1]}]")
            if rng[0] < rng[1]:
                out.missing = [*out.missing, f"exact count not certain: 90% range {rng[0]}–{rng[1]} ({src} {v}, {what} "
                                             f"{det}; this range held the true count for 93% of dev answers)"]
    has_located = any(e.bbox is not None or e.ifc_guid for e in out.evidence)
    rel = d["path"]
    if not has_located and boxes:
        n = len(boxes)
        ev = [Evidence(file=rel, bbox=[float(x) for x in b], bbox_space="image_px",
                       note=f"{noun} {i + 1} of {n} ({what})") for i, b in enumerate(boxes)]
        ev[0] = ev[0].model_copy(update={"note": f"{ev[0].note}; {note}"})
        out.evidence = ev + list(out.evidence)
        out.missing = [m for m in out.missing if m != "no located evidence from this solver"]
        out.assumptions = [*out.assumptions, f"the {noun} boxes come from the pretrained CubiCasa5K model (Kalervo et "
                                             f"al. 2019, weights CC BY-NC 4.0), an independent second count"]
        if d.get("cc5k_list") == "train":
            out.assumptions.append("this drawing is in the CubiCasa5K model's original training list (measured: its "
                                   "accuracy there is within a few points of held-out drawings)")
    elif out.evidence:
        e0 = out.evidence[0]
        out.evidence[0] = e0.model_copy(update={"note": (e0.note + "; " + note).strip("; ")})
    elif not boxes:
        trace.append(f"{what} found no {noun}; nothing to locate")
    out.trace = [*out.trace, *trace]
    return out
