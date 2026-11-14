from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pymupdf
import pytest
from openai import APIStatusError

import stoa.solvers.piping as piping_module
from stoa.solvers.piping import PipingSolver, parse_sizes, parse_tags


def _write_two_sheet_pdf(path):
    doc = pymupdf.open()
    other = doc.new_page()
    other.insert_text((72, 72), "M-100 OTHER PLAN\nDRAWING INDEX: M-101A M-101B\nFSCV-99 CV-99 PG")
    piping = doc.new_page()
    piping.insert_text(
        (72, 72),
        "M-101A PIPING PLAN\n"
        "CV-1 CV-2 FSCV-1 FSCV-2\n"
        "PS-1 PS-1 PS-3\n"
        "PG PG MAV",
    )
    doc.save(path)
    doc.close()


def _write_lookup_pdf(path):
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "M-101A PIPING PLAN")
    page.insert_text((72, 120), '16" SUCTION HEADER')
    page.insert_text((72, 150), '16" SS FROM OPERATING TANKS')
    page.insert_text((72, 180), '12" TO HYDRANT LOOP AND PIG LAUNCH TRAP')
    page.insert_text(
        (72, 230),
        "2. ALL PRESSURIZED HYDRANT FUELING SYSTEM PIPE MATERIALS SHALL BE PER UFC 3-460-01.",
    )
    page.insert_text((72, 280), 'SCALE: 1/4" = 1\'-0"')
    page.insert_text((100, 360), "FP-1")
    # Text anchors are slightly offset from their branch centerlines on real plans;
    # the solver reports approximate scale measurements to the nearest half foot.
    page.insert_text((215.44, 360), "FP-2")
    page.insert_text((72, 420), '2" SS TO PRODUCT RECOVERY TANK')
    page.insert_text((72, 450), '8" SS TO OPERATING')
    page.insert_text((166, 450), "TANK NO. 1")
    page.insert_text((72, 490), '12" F/S DISCHARGE HEADER')
    page.insert_text((72, 520), '12" PUMP DISCHARGE HEADER')
    page.insert_text((72, 560), '8" CROSS CONNECTION FROM RETURN LINE')
    page.insert_text((72, 590), '8" RETURN LINE')
    doc.save(path)
    doc.close()


def test_parse_tags_keeps_families_separate_and_normalizes_separators():
    text = "CV-1 cv - 2 FP–3 FSI-4 FSR - 5 FSCV-6 PS-12 PG MAV CVX-9"

    assert parse_tags(text) == [
        "CV-1",
        "CV-2",
        "FP-3",
        "FSI-4",
        "FSR-5",
        "FSCV-6",
        "PS-12",
        "PG",
        "MAV",
    ]


def test_parse_sizes_supports_whole_fractional_and_typographic_inches():
    text = 'Lines are 8", 16”, 1 1/2", and 3/4"; the run is 10 feet.'

    assert parse_sizes(text) == ['8"', '16"', '1 1/2"', '3/4"']


def test_parse_sizes_preserves_decimal_and_hyphenated_values_without_tail_matches():
    text = 'Valid sizes: 1.5", 1-1/2", and 2″. Invalid equipment label: ABC123".'

    assert parse_sizes(text) == ['1.5"', '1 1/2"', '2"']


def test_solver_counts_only_the_named_sheet_and_cites_each_tag(tmp_path):
    pdf = tmp_path / "plans.pdf"
    _write_two_sheet_pdf(pdf)

    answer = PipingSolver().solve(
        str(pdf),
        "On sheet M-101A, how many distinct FSCV-tagged components are shown?",
    )

    assert answer.value == 2
    assert answer.unit == "count"
    assert answer.solver == "piping"
    assert answer.confidence >= 0.9
    assert [item.page for item in answer.evidence] == [1, 1]
    assert [item.note for item in answer.evidence] == ["FSCV-1", "FSCV-2"]
    assert all(item.file == str(pdf) for item in answer.evidence)
    assert all(item.bbox_space == "pdf_pt" and item.bbox for item in answer.evidence)


def test_solver_reassembles_split_tag_words_and_unions_their_boxes(tmp_path):
    pdf = tmp_path / "split-tags.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "M-101A PIPING PLAN")
    page.insert_text((72, 120), "CV - 1 CV-2")
    doc.save(pdf)
    doc.close()

    answer = PipingSolver().solve(
        str(pdf),
        "On M-101A, how many distinct CV-tagged components are shown?",
    )

    assert answer.value == 2
    assert [item.note for item in answer.evidence] == ["CV-1", "CV-2"]
    assert answer.evidence[0].bbox[2] > answer.evidence[0].bbox[0]


def test_solver_distinguishes_distinct_pipe_support_ids_from_callouts(tmp_path):
    pdf = tmp_path / "plans.pdf"
    _write_two_sheet_pdf(pdf)
    solver = PipingSolver()

    distinct = solver.solve(
        str(pdf),
        "On M-101A, how many distinct numbered PS-n pipe-support IDs occur?",
    )
    occurrences = solver.solve(
        str(pdf),
        "On M-101A, how many printed PS-n pipe-support callouts occur, including repeated IDs?",
    )

    assert distinct.value == 2
    assert len(distinct.evidence) == 2
    assert occurrences.value == 3
    assert len(occurrences.evidence) == 3


def test_solver_abstains_for_non_piping_question(tmp_path):
    pdf = tmp_path / "plans.pdf"
    _write_two_sheet_pdf(pdf)
    solver = PipingSolver()

    answer = solver.solve(str(pdf), "How many bedrooms are shown?")

    assert answer.abstained
    assert answer.solver == "piping"
    assert "unsupported" in " ".join(answer.trace).lower()


def test_solver_looks_up_named_line_size_with_evidence(tmp_path):
    pdf = tmp_path / "lookups.pdf"
    _write_lookup_pdf(pdf)

    answer = PipingSolver().solve(str(pdf), "What is the labeled suction-header size on M-101A?")

    assert answer.value == "16 inches"
    assert answer.unit is None
    assert answer.evidence[0].page == 0
    assert "16" in answer.evidence[0].note


def test_size_lookup_prefers_specific_equipment_and_direct_label(tmp_path):
    pdf = tmp_path / "lookups.pdf"
    _write_lookup_pdf(pdf)
    solver = PipingSolver()

    pump = solver.solve(str(pdf), "What is the pump-discharge-header size on M-101A?")
    direct_return = solver.solve(str(pdf), "What is the return-line size on M-101A?")
    operating = solver.solve(
        str(pdf),
        "What size and material is the line to operating tank No. 1 on M-101A?",
    )

    assert pump.value == "12 inches"
    assert "PUMP DISCHARGE" in pump.evidence[0].note
    assert direct_return.value == "8 inches"
    assert direct_return.evidence[0].note == '8" RETURN LINE'
    assert operating.value == "8-inch stainless steel"
    assert "OPERATING" in operating.evidence[0].note and "TANK NO. 1" in operating.evidence[0].note


def test_solver_reads_material_spec_from_designer_note(tmp_path):
    pdf = tmp_path / "lookups.pdf"
    _write_lookup_pdf(pdf)

    answer = PipingSolver().solve(
        str(pdf),
        "According to M-101A designer note 2, which standard governs pipe materials?",
    )

    assert answer.value == "UFC 3-460-01"
    assert answer.evidence[0].page == 0
    assert "UFC 3-460-01" in answer.evidence[0].note


def test_connection_falls_back_to_labeled_callout_without_key(tmp_path, monkeypatch):
    pdf = tmp_path / "lookups.pdf"
    _write_lookup_pdf(pdf)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    answer = PipingSolver().solve(
        str(pdf),
        "On M-101A, what does the 16-inch stainless-steel line come from?",
    )

    assert answer.value == "Operating tanks"
    assert answer.evidence
    assert "keyless deterministic fallback" in " ".join(answer.trace).lower()


def test_connection_uses_validated_gemini_evidence_ids_when_key_exists(tmp_path, monkeypatch):
    pdf = tmp_path / "lookups.pdf"
    _write_lookup_pdf(pdf)
    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    seen = {}

    def fake_chat(prompt, images, **kwargs):
        seen["prompt"] = prompt
        seen["image_size"] = images[0].size
        seen["kwargs"] = kwargs
        return type(
            "Result",
            (),
            {"text": '{"value":"Operating tanks","evidence_ids":["b1"],"confidence":0.91}'},
        )()

    monkeypatch.setattr(piping_module.llm, "chat", fake_chat)
    monkeypatch.setattr(piping_module.llm, "gemini_calls_today", lambda: 0)

    answer = PipingSolver().solve(
        str(pdf),
        "On M-101A, what does the 16-inch stainless-steel line come from?",
    )

    assert answer.value == "Operating tanks"
    assert answer.confidence == 0.91
    assert answer.evidence and answer.evidence[0].note
    assert seen["image_size"][0] > 0 and seen["image_size"][1] > 0
    assert seen["kwargs"]["backend"] == "gemini"
    assert seen["kwargs"]["model"] == "gemini-3.1-pro-preview"
    assert "b1" in seen["prompt"]


def test_connection_falls_back_when_gemini_rejects_the_request(tmp_path, monkeypatch):
    pdf = tmp_path / "lookups.pdf"
    _write_lookup_pdf(pdf)
    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    monkeypatch.setattr(piping_module.llm, "gemini_calls_today", lambda: 0)

    def rejected_chat(*args, **kwargs):
        response = type(
            "Response",
            (),
            {"request": object(), "status_code": 400, "headers": {}},
        )()
        raise APIStatusError("rejected", response=response, body=None)

    monkeypatch.setattr(piping_module.llm, "chat", rejected_chat)

    answer = PipingSolver().solve(
        str(pdf),
        "On M-101A, what does the 16-inch stainless-steel line come from?",
    )

    assert answer.value == "Operating tanks"
    assert "deterministic fallback" in " ".join(answer.trace).lower()


def test_connection_falls_back_when_crop_rendering_fails(tmp_path, monkeypatch):
    pdf = tmp_path / "lookups.pdf"
    _write_lookup_pdf(pdf)
    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    monkeypatch.setattr(piping_module.llm, "gemini_calls_today", lambda: 0)

    def broken_crop(*args, **kwargs):
        raise OSError("render failed")

    monkeypatch.setattr(piping_module, "_render_crop", broken_crop)

    answer = PipingSolver().solve(
        str(pdf),
        "On M-101A, what does the 16-inch stainless-steel line come from?",
    )

    assert answer.value == "Operating tanks"


@pytest.mark.parametrize(
    "payload",
    [
        '{"value":null,"evidence_ids":["b1"],"confidence":0.9}',
        '{"value":"Hallucinated","evidence_ids":["b1","invented"],"confidence":0.9}',
        '{"value":"Hallucinated","evidence_ids":["b1"],"confidence":true}',
        '{"value":"Hallucinated","evidence_ids":{"first":"b1"},"confidence":0.9}',
    ],
)
def test_connection_rejects_schema_invalid_gemini_payloads(tmp_path, monkeypatch, payload):
    pdf = tmp_path / "lookups.pdf"
    _write_lookup_pdf(pdf)
    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    monkeypatch.setattr(piping_module.llm, "gemini_calls_today", lambda: 0)
    monkeypatch.setattr(
        piping_module.llm,
        "chat",
        lambda *args, **kwargs: type("Result", (), {"text": payload})(),
    )

    answer = PipingSolver().solve(
        str(pdf),
        "On M-101A, what does the 16-inch stainless-steel line come from?",
    )

    assert answer.value == "Operating tanks"
    assert answer.confidence == 0.78


def test_named_lookups_abstain_when_requested_line_is_absent(tmp_path):
    pdf = tmp_path / "lookups.pdf"
    _write_lookup_pdf(pdf)
    solver = PipingSolver()

    size = solver.solve(str(pdf), "What is the oxygen-line size on M-101A?")
    connection = solver.solve(str(pdf), "Where does the oxygen pipe come from on M-101A?")

    assert size.abstained
    assert connection.abstained


def test_solver_measures_straight_header_span_between_tagged_branches(tmp_path):
    pdf = tmp_path / "lookups.pdf"
    _write_lookup_pdf(pdf)

    answer = PipingSolver().solve(
        str(pdf),
        "Approximately how long is the straight suction-header segment between FP-1 and FP-2 on M-101A?",
    )

    assert answer.value == "6.5 ft"
    assert answer.unit is None
    assert [item.note for item in answer.evidence] == ["FP-1", "FP-2"]


def test_parallel_questions_parse_one_cold_pdf_once(tmp_path, monkeypatch):
    pdf = tmp_path / "parallel.pdf"
    _write_two_sheet_pdf(pdf)
    real_open = piping_module.pymupdf.open
    calls = 0
    calls_lock = threading.Lock()

    def slow_open(*args, **kwargs):
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return real_open(*args, **kwargs)

    monkeypatch.setattr(piping_module.pymupdf, "open", slow_open)
    question = "On M-101A, how many distinct CV-tagged components are shown?"
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda _: PipingSolver().solve(str(pdf), question).value, range(8)))

    assert values == [2] * 8
    assert calls == 1
