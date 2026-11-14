"""stoa.solvers.raster_cc5k.crosscheck: CC5K detections as evidence + cross-check for another solver's count.
Uses the precomputed detections cache (artifacts/R1/cc5k_counts.jsonl); skipped where it is absent."""
import pytest

from stoa.contract import Answer
from stoa.solvers.raster_cc5k import crosscheck as cx

DRAWING = "data/cubicasa5k/colorful-10052.png"  # cached: windows 11, doors 4, wc_seats 0, sinks 1
needs_cache = pytest.mark.skipif(not cx.CACHE.exists() or cx.detections(DRAWING, live=False) is None,
                                 reason="no CC5K detections cache on this machine")


def lora(value, p, conf=0.5):
    return Answer(value=value, unit="count", confidence=conf, solver="vlm_lora",
                  trace=["raw: x", f"p(answer digits) = {p:.5f} -> confidence {p:.2f}"])


@needs_cache
def test_agree_adds_one_box_per_symbol_and_a_tick():
    out = cx.check(DRAWING, "count:door:drawing", lora(4, 0.6))
    assert out.value == 4
    assert len(out.evidence) == 4 and all(e.bbox_space == "image_px" and e.bbox for e in out.evidence)
    assert "cross-check: vlm_lora 4 = CC5K detector 4 ✓" in out.evidence[0].note
    assert any(t.startswith("cross-check:") for t in out.trace)
    assert out.confidence == cx._table()["targets"]["door"]["agree"]


@needs_cache
def test_window_disagreement_goes_to_the_surer_detector():
    det = cx.detections(DRAWING)["counts"]["windows"]
    out = cx.check(DRAWING, "count:window:drawing", lora(5, 0.05))
    assert out.value == det["count"] and out.confidence == pytest.approx(det["confidence"], abs=1e-3)
    assert "raster_cc5k" in out.solver and any("arbitration" in t for t in out.trace)
    assert "✗" in out.evidence[0].note and out.missing


@needs_cache
def test_window_disagreement_keeps_a_surer_lora():
    out = cx.check(DRAWING, "count:window:drawing", lora(5, 0.99))
    assert out.value == 5 and any("kept vlm_lora 5" in t for t in out.trace)


@needs_cache
def test_sinks_are_never_arbitrated():
    out = cx.check(DRAWING, "count:sink:drawing", lora(3, 0.01))
    assert out.value == 3 and "≠" in out.evidence[0].note and out.missing
    assert out.confidence == cx._table()["targets"]["sink"]["kept"]


@needs_cache
def test_input_is_not_modified_and_scoped_or_own_answers_are_untouched():
    a = lora(4, 0.6)
    cx.check(DRAWING, "count:door:drawing", a)
    assert a.evidence == [] and a.confidence == 0.5
    assert cx.check(DRAWING, "count:door:apartment", a) == a  # apartment scope: drawing-level boxes don't apply
    own = Answer(value=4, unit="count", confidence=0.5, solver="raster_cc5k")
    assert cx.check(DRAWING, "count:door:drawing", own) == own
    assert cx.check(DRAWING, "count:shower_bathtub:drawing", a) == a


@needs_cache
def test_other_solvers_keep_their_confidence_and_their_own_evidence():
    from stoa.contract import Evidence
    a = Answer(value=1, unit="count", confidence=0.7, solver="raster",
               evidence=[Evidence(file=DRAWING, bbox=[0, 0, 1, 1], bbox_space="image_px", note="label KT")])
    out = cx.check(DRAWING, "count:sink:drawing", a)
    assert out.confidence == 0.7 and len(out.evidence) == 1 and "CC5K detector 1 ✓" in out.evidence[0].note


def test_unknown_drawing_without_live_inference_is_a_noop():
    out = cx.check("data/cubicasa5k/does-not-exist.png", "count:window:drawing", lora(2, 0.4), live=False)
    assert out.value == 2 and out.evidence == [] and "no cached" in out.trace[-1]


def test_interval_is_the_two_counts_range_widened_for_openings():
    assert cx.interval("sink", 2, 2) == (2, 2)
    lo, hi = cx.interval("sink", 1, 3)
    assert lo <= 1 and hi >= 3
    lo, hi = cx.interval("window", 5, 8)
    assert lo <= 5 and hi >= 8 and hi - lo > 3
    assert cx.interval("door", 0, 0)[0] == 0  # never below zero
    assert cx.interval("shower_bathtub", 1, 1) is None


@needs_cache
def test_lora_answers_get_a_machine_readable_range():
    out = cx.check(DRAWING, "count:window:drawing", lora(5, 0.99))
    line = [t for t in out.trace if t.startswith("interval90:")]
    assert line and any("90% range" in m for m in out.missing)
    lo, hi = map(int, line[0].split("[")[1].rstrip("]").split(","))
    assert lo <= 5 and hi >= 11
    raster = Answer(value=1, unit="count", confidence=0.7, solver="raster")
    assert not any(t.startswith("interval90:") for t in cx.check(DRAWING, "count:sink:drawing", raster).trace)


@needs_cache
def test_a_third_count_switches_to_the_joint_confidence_table():
    agree_both = cx.check(DRAWING, "count:door:drawing", lora(4, 0.6), other=4)
    agree_det_only = cx.check(DRAWING, "count:door:drawing", lora(4, 0.6), other=7)
    assert agree_both.confidence == cx._joint("door", True, True)
    assert agree_det_only.confidence == cx._joint("door", False, True)
    assert any("raster 7" in t for t in agree_det_only.trace)
    assert cx.check(DRAWING, "count:door:drawing", lora(4, 0.6)).confidence == cx._table()["targets"]["door"]["agree"]


def test_detector_only_range_grows_with_the_count_and_never_goes_below_zero():
    lo, hi = cx.detector_interval("windows", 3)
    assert 0 <= lo <= 3 <= hi
    big = cx.detector_interval("window", 15)
    assert big[1] - big[0] >= hi - lo
    assert cx.detector_interval("shower_bath", 2) is None


@needs_cache
def test_raster_cc5k_answers_carry_the_range():
    from stoa.solvers.raster_cc5k import RasterCC5KSolver
    a = RasterCC5KSolver().solve(DRAWING, "How many windows are shown on this floor plan?")
    line = [t for t in a.trace if t.startswith("interval90:")]
    assert a.value == 11 and line
    lo, hi = map(int, line[0].split("[")[1].rstrip("]").split(","))
    assert lo <= 11 <= hi


def test_threshold_confidence_is_lower_when_the_detector_straddles_the_threshold():
    same = cx.threshold_confidence("wc", 2, 3, 2)
    straddle = cx.threshold_confidence("wc", 2, 1, 2)
    assert same is not None and straddle is not None and same > straddle
    assert cx.threshold_confidence("shower_bathtub", 1, 1, 2) is None


def test_raster_cc5k_abstains_on_doors_of_foreign_styles():
    from stoa.solvers.raster_cc5k import RasterCC5KSolver
    a = RasterCC5KSolver().solve("data/swiss_dwellings/site1_bldg1_floor1.png", "How many doors are drawn on this floor plan?")
    assert a.value is None and "does not transfer" in " ".join(a.trace)
