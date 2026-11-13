from stoa.contract import Answer, Evidence
from stoa.data import drawing_group, template_of
from stoa.eval.scoring import convert, parse_number, score, text_fuzzy


def test_count_exact_after_rounding():
    assert score("count", 5, "count", 5, "count")
    assert score("count", 5, "count", 4.6, None)
    assert not score("count", 5, "count", 4.4, None)
    assert score("count", 5, "count", "5 windows", None)
    assert not score("count", 5, "count", None, None)


def test_area_tolerance_and_units():
    assert score("area", 100.0, "m2", 101.9, "m2")
    assert not score("area", 100.0, "m2", 102.1, "m2")
    assert score("area", 100.0, "m2", 1076.39, "ft2")  # 1076.39 ft2 = 100 m2
    assert score("area", 29690, "ft2", 2758.27, "m2")
    assert not score("area", 10.0, "m2", 10.0, "m")  # wrong dimension
    assert score("volume", 3.0, "m3", "3,02 m³", None)
    assert score("length", 2.5, "m", 2500, "mm")


def test_text_not_scored():
    assert score("text", "IFC2X3", None, "IFC2X3", None) is None
    assert text_fuzzy("The model uses IFC2X3", "IFC2X3")
    assert not text_fuzzy("1", "1 water closet, 1 lavatory, 1 shower")


def test_parse_number():
    assert parse_number("1 234.5 m2") == 1234.5
    assert parse_number("12,5") == 12.5
    assert parse_number("about 7") == 7.0
    assert parse_number(True) is None
    assert convert(1.0, "m2", "ft2") > 10.76


def test_answer_json_roundtrip():
    a = Answer(value=3, unit="count", confidence=0.9, solver="x",
               evidence=[Evidence(file="data/a/b.pdf", page=0, bbox=[1, 2, 3, 4], bbox_space="pdf_pt", note="door")])
    b = Answer.model_validate_json(a.model_dump_json())
    assert b == a
    assert Answer.abstain("x", "no idea").abstained


def test_groups_and_templates():
    assert drawing_group("data/swiss_dwellings/site3387_bldg5238_floor23498.pdf") == "swiss_dwellings/site3387"
    assert drawing_group("data/cubicasa5k/colorful-10052.png") == "cubicasa5k/colorful-10052"
    assert drawing_group("data/ifc_bench/dental_clinic_mep.ifc") == "ifc_bench/dental_clinic"
    assert template_of("How many rooms on floor 3?") == "how many rooms on floor <N>?"


def test_cost_backward_compat():
    from stoa.contract import Cost

    a = Answer(value=1)
    assert not a.cost and dict(**a.cost) == {}
    a.cost = {**{"llm_tokens_in": 10, "gpu_seconds": 0.5}, **(a.cost or {})}  # old-style merge
    assert isinstance(a.cost, Cost) and a.cost.llm_tokens_in == 10 and a.cost.gpu_seconds == 0.5
    assert {**a.cost} == {"llm_tokens_in": 10, "gpu_seconds": 0.5}
    assert a.model_dump()["cost"]["llm_tokens_in"] == 10


def test_calibration_metrics():
    from stoa.eval.calibration import calibration

    def row(c, ok, t="count"):
        return {"type": t, "correct": ok, "confidence": c}

    # perfectly ranked and calibrated at the extremes
    good = calibration([row(1.0, True)] * 8 + [row(0.0, False)] * 2)
    assert good["auroc"] == 1.0 and good["ece"] == 0.0 and good["brier"] == 0.0
    assert good["e_aurc"] == 0.0 and good["hi_conf_share"] == 0.8 and good["hi_conf_acc"] == 1.0
    # constant confidence carries no ranking information
    flat = calibration([row(0.3, True)] * 3 + [row(0.3, False)] * 7)
    assert flat["auroc"] == 0.5 and abs(flat["ece"]) < 1e-9 and flat["hi_conf_acc"] is None
    # text rows and missing confidences are skipped
    mixed = calibration([row(0.9, True), row(None, False), {"type": "text", "correct": None, "confidence": 0.5}])
    assert mixed["n"] == 1 and mixed["n_missing_conf"] == 1


def test_select_grep():
    from stoa.data import Question
    from stoa.eval.runner import select

    qs = [Question(qid=str(i), path="data/cubicasa5k/a.png", question=q, answer=1, unit=None, type="count")
          for i, q in enumerate(("How many windows are shown?", "Kuinka monta ikkunaa?", "How many doors?"))]
    assert len(select(qs, grep="window|ikkun")) == 2


def test_resbim_plan_links_to_model():
    from stoa.data import data_root, drawing_group, ifc_model_for, siblings

    if not (data_root() / "data/ifc_models/resbim-0_model.ifc").exists():
        return
    assert ifc_model_for("data/ifc_models/resbim-0_plan.png") == "data/ifc_models/resbim-0_model.ifc"
    assert siblings("data/ifc_models/resbim-0_plan.png")[".ifc"] == "data/ifc_models/resbim-0_model.ifc"
    assert drawing_group("data/ifc_models/resbim-0_plan.png") == drawing_group("data/ifc_models/resbim-0_model.ifc")


def test_ratio_type_scored_and_threshold():
    import random

    from stoa.eval.hard2 import _threshold_any
    from stoa.eval.scoring import score

    assert score("ratio", 8.4, "%", "8.5", "%") is True and score("ratio", 1.07, None, 1.2, None) is False
    for seed in range(20):
        t = _threshold_any([10.0, 20.0], random.Random(seed))
        assert t is None or all(abs(v - t) > 0.05 * max(v, t) for v in (10.0, 20.0))


def test_judge_numeric_precheck():
    from stoa.eval.judge import numeric_verdict as n

    assert n("The total length of exterior walls is 267.45 m.", "284.636")[0] is False
    assert n("The concrete volume is 273.91 cu m.", "273.9 m3")[0] is True
    assert n("Created with Revit 2020.", "Revit 2019")[0] is False  # integers without unit: exact
    assert n("Total: 8 doors", "There are 8 doors")[0] is True
    assert n("10 walls, 472.018 sq ft", "472")[0] is None  # several numbers: LLM decides
