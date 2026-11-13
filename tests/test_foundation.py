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
