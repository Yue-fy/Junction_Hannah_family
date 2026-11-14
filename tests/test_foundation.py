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


def test_adhoc_split_file_without_answers(tmp_path):
    """Hand-written question files (e.g. Stoa's example questions) load even without answer/qid, and are not scored."""
    import json
    from stoa.data import make_qid
    from stoa.eval.scoring import score
    from stoa.eval.splits import load_split
    f = tmp_path / "adhoc.jsonl"
    rows = [{"qid": "a1", "path": "data/cubicasa5k/x.png", "question": "How many doors?", "answer": 3, "type": "count"},
            {"path": "data/cubicasa5k/x.png", "question": "How many windows?", "type": "count"},
            {"path": "data/cubicasa5k/x.png", "question": "What is this drawing?"}]
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    qs = load_split(str(f))
    assert [q.qid for q in qs] == ["a1", make_qid("data/cubicasa5k/x.png", "How many windows?"),
                                   make_qid("data/cubicasa5k/x.png", "What is this drawing?")]
    assert qs[1].answer is None and qs[2].type == "other"
    assert score("count", None, None, 4, "count") is None
    assert score("count", 3, None, 3, "count") is True


def test_source_of_absolute_paths(tmp_path):
    """R1 03:44: an absolute path used to give source '/' (no gate, no LoRA, no CC5K)."""
    from stoa.data import data_root, dataset_rel, source_of
    rel = "data/cubicasa5k/high_quality_architectural-6652.png"
    assert source_of(rel) == "cubicasa5k"
    assert source_of(str(data_root() / rel)) == "cubicasa5k"
    assert dataset_rel(str(data_root() / rel)) == rel
    assert source_of(str(tmp_path / "plan.png")) == "unknown"
    assert dataset_rel(rel) == rel


def test_dataset_rel_foreign_file_in_dataset_layout(tmp_path):
    """Q 04:13: a NEW drawing in a folder laid out like ours (.../data/cubicasa5k/<file>) must keep its absolute path
    (it used to be cut and looked up under $STOA_DATA: FileNotFoundError -> prior answer at conf 0.8), but still get
    its source from the folder name. A true copy of a dataset file (same relative path, same size) is still cut."""
    import shutil
    from stoa.data import data_root, dataset_rel, ifc_model_for, source_of
    rel = "data/cubicasa5k/high_quality_architectural-6652.png"
    foreign = tmp_path / "stoa" / "data" / "cubicasa5k" / "high_quality_architectural-6652.png"
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b"not the dataset image")
    assert dataset_rel(str(foreign)) == str(foreign)
    assert source_of(str(foreign)) == "cubicasa5k"
    new = foreign.parent / "brand-new-plan.png"
    new.write_bytes(b"x")
    assert dataset_rel(str(new)) == str(new) and source_of(str(new)) == "cubicasa5k"
    if (data_root() / rel).is_file():
        copy = tmp_path / "copy" / rel
        copy.parent.mkdir(parents=True)
        shutil.copyfile(data_root() / rel, copy)
        assert dataset_rel(str(copy)) == rel
    other = tmp_path / "x" / "data" / "not_a_source" / "a.png"
    other.parent.mkdir(parents=True)
    other.write_bytes(b"x")
    assert source_of(str(other)) == "unknown"
    # ifc_models outside the dataset: the plan's model is looked up next to it, never in $STOA_DATA
    ifc_dir = tmp_path / "stoa" / "data" / "ifc_models"
    ifc_dir.mkdir(parents=True)
    (ifc_dir / "house.ifc").write_text("ISO-10303-21;")
    (ifc_dir / "house_plan-01-EG.pdf").write_bytes(b"%PDF")
    assert ifc_model_for(str(ifc_dir / "house_plan-01-EG.pdf")) == str(ifc_dir / "house.ifc")
    assert ifc_model_for(str(ifc_dir / "other_plan-01.pdf")) is None


def test_outside_sheet_next_to_its_model(tmp_path):
    """F c226 neutral-path probe: an IFC plan sheet outside the dataset (no data/ifc_models/ folder) next to its
    model was source 'unknown' -> no model sibling, no `ifc` route (ifc_models dev 100% -> 0-21%)."""
    from stoa.data import ifc_model_for, siblings, source_of
    pkg = tmp_path / "upload1"
    pkg.mkdir()
    (pkg / "house.ifc").write_text("ISO-10303-21;")
    sheet = pkg / "house_plan-01-EG.pdf"
    sheet.write_bytes(b"%PDF")
    assert source_of(str(sheet)) == "ifc_models"
    assert siblings(str(sheet))[".ifc"] == str(pkg / "house.ifc")
    # one model in a project folder: sheets under any name belong to it
    other = pkg / "A101 Ground floor.pdf"
    other.write_bytes(b"%PDF")
    assert ifc_model_for(str(other)) == str(pkg / "house.ifc") and source_of(str(other)) == "ifc_models"
    # two models and no name match: no guess
    (pkg / "garage.ifc").write_text("ISO-10303-21;")
    other2 = pkg / "A102 First floor.pdf"
    other2.write_bytes(b"%PDF")
    assert ifc_model_for(str(other2)) is None and source_of(str(other2)) == "unknown"
    assert source_of(str(pkg / "house_plan-01-EG.pdf")) == "ifc_models"
    # a lone drawing, a model file itself, a CubiCasa-like PNG: unchanged
    lone = tmp_path / "lone" / "plan.png"
    lone.parent.mkdir()
    lone.write_bytes(b"x")
    assert source_of(str(lone)) == "unknown"
    assert source_of(str(pkg / "house.ifc")) == "unknown"
