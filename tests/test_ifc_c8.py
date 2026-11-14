"""Cycle-8 fixes: plan <-> model comparatives and their polarity, in several languages, through the deterministic
`plan_vs_model` reading (0 LLM calls; the pipeline's link route can cross-check R1's kg_qa with it). Self-written
wordings (experiments/w1/probes/c8_cmp.jsonl); expected values are the model's own GlobalId set differences
(esplanades 1.korrus: the model has 55 windows, the sheet draws 52; doors 46 / 46; gdynia: 4 plans + 6 other sheets)."""

from __future__ import annotations

from pathlib import Path

import pytest

from stoa.data import abspath
from stoa.solvers.ifc.parse import parse
from stoa.solvers.ifc.solver import plan_vs_model

ESPL = "data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf"
GDY = "data/ifc_models/bimspeed-gdynia_ruchu-oporu-18_plan-03-0.pdf"
need = pytest.mark.skipif(not abspath(ESPL).exists(), reason="dataset not available")


def _yn(v) -> str:
    return str(v).split(":", 1)[0].strip()


@need
@pytest.mark.parametrize("q,want", [
    ("Does this plan show fewer windows than the IFC model has on the same storey?", "yes"),
    ("Does this plan show more windows than the IFC model has on the same storey?", "no"),
    ("Are there fewer windows on this drawing than in the model?", "yes"),  # was 'no' @ 0.85: subject after 'fewer'
    ("Does the model have fewer windows on '1.korrus' than this plan shows?", "no"),
    ("Does this sheet show fewer doors than the IFC model has on the same storey?", "no"),  # 46 = 46
    ("Zeigt dieser Plan weniger Fenster als das IFC-Modell im selben Geschoss hat?", "yes"),
    ("Näyttääkö tämä piirustus vähemmän ikkunoita kuin mallissa on samassa kerroksessa?", "yes"),
    ("Toont deze plattegrond minder ramen dan het IFC-model op dezelfde verdieping?", "yes"),
    ("Does the plan show as many windows as the model has on this storey?", "no"),
    ("Does the plan differ from the model in the number of windows?", "yes"),  # was the 'agree?' answer 'no'
    ("Do the floor plan and the model agree or differ on the doors?", "yes"),
    ("Are there windows in the 3D model that this sheet does not draw?", "yes"),  # was the count 3
])
def test_comparative_polarity(q, want):
    a = plan_vs_model(ESPL, q)
    assert a is not None and _yn(a.value) == want


@need
@pytest.mark.parametrize("q,n", [
    ("How many more windows does the model have on this storey than the plan shows?", 3),
    ("By how many windows does the model exceed this plan on '1.korrus'?", 3),
    ("How many fewer windows does this plan show than the model has?", 3),
    ("By how many doors does this plan differ from the IFC model?", 0),
])
def test_comparative_difference(q, n):
    a = plan_vs_model(ESPL, q)
    assert a is not None and a.value == n and a.unit == "count"


@need
@pytest.mark.skipif(not abspath(GDY).exists(), reason="gdynia not available")
@pytest.mark.parametrize("q,n", [
    ("Wie viele Blätter gehören insgesamt zu diesem Gebäude (Pläne, Schnitte und Aufrisse)?", 10),
    ("Hoeveel bladen zijn er in totaal in deze bouwtekening (plannen, sneden en gevels)?", 10),
    ("How many sheets in total belong to this building (floor plans, sections and elevations)?", 10),
    ("Wie viele Grundrisse gibt es insgesamt für dieses Gebäude?", 4),
    ("How many floor plans are there in total?", 4),
])
def test_sheet_totals(q, n):
    a = plan_vs_model(GDY, q)
    assert a is not None and a.value == n


def test_not_a_link_question_is_none():
    if not abspath(ESPL).exists():
        pytest.skip("dataset not available")
    assert plan_vs_model(ESPL, "Does the model have more windows than doors on '1.korrus'?") is None
    assert plan_vs_model(str(Path(ESPL).with_suffix(".nope")), "How many doors?") is None


def test_dutch_plattegrond_is_not_a_slab():
    assert parse("Toont deze plattegrond minder ramen dan het IFC-model?").kind == "window"
    assert parse("Wie viele Bodenplatten gibt es?").kind == "slab"


GDY_F = "data/ifc_models/bimspeed-gdynia_ruchu-oporu-18_plan-01-foundation.pdf"


@need
@pytest.mark.skipif(not abspath(GDY_F).exists(), reason="gdynia not available")
@pytest.mark.parametrize("q,n", [
    ("How many doors are in this building?", 16),  # F 10:22: was 0 (the foundation sheet's storey)
    ("Wie viele Türen hat dieses Gebäude?", 16),
    ("Hoeveel deuren heeft dit gebouw?", 16),
    ("How many doors does this building's ground floor have?", 6),  # a storey word still wins
    ("How many doors are on this floor plan?", 0),
])
def test_this_building_is_the_whole_model(q, n):
    from stoa.solvers.ifc.solver import IfcSolver

    a = IfcSolver(plan2d="0", llm="0").solve(GDY_F, q)
    assert a.value == n


ESPL2 = "data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-02-2-korrus.pdf"


@need
@pytest.mark.parametrize("path,q,n", [
    # no storey named on a sheet: the sheet's storey (was the whole model: 24 of 211 doors @ 0.85)
    (ESPL2, "How many doors on this floor are wider than 1 m?", 3),
    (ESPL2, "How many windows on this floor are taller than 1.5 m?", 46),
    (ESPL2, "What is the average width of the doors in the whole building?", 1.088),
    (ESPL, "How many different door widths are there on '1.korrus'?", 8),
    (ESPL, "How many doors on '1.korrus' are exactly 900 mm wide?", 2),
    (ESPL, "How many distinct window heights are there on this floor?", 4),
])
def test_dimension_scope_and_counts(path, q, n):
    from stoa.solvers.ifc.solver import IfcSolver

    a = IfcSolver(plan2d="0", llm="0").solve(path, q)
    assert a.value == n and a.confidence >= 0.8


ESPL_IFC = "data/ifc_models/bsc-esplanades_1807-ep-ar-v18.ifc"


@need
@pytest.mark.parametrize("path,q,want", [
    (ESPL, "How big is room 119?", 63.841),  # W5 10:34: the storey total 870.288 @ 0.95
    (ESPL, "What is the area of corridor 119 on floor 1?", 63.841),
    (ESPL_IFC, "Which floor has no MAGAMISTUBA?", "1.korrus"),  # Q v25: the floors WITH one @ 0.9
    (ESPL, "Of the floors that have rooms, which one has the fewest?", "1.korrus"),  # was a room @ 0.9
    (ESPL, "What is the total area of the three largest rooms on '1.korrus'?", 232.887),  # was the list
    (ESPL, "Which three rooms on '1.korrus' are the largest?",
     "FUAJEE-TREPIKODA (101) (90.64 m²); KORIDOR (105) (78.40 m²); KORIDOR (119) (63.84 m²)"),
])
def test_v25_rankings_and_room_numbers(path, q, want):
    from stoa.solvers.ifc.solver import IfcSolver

    a = IfcSolver(plan2d="0", llm="0").solve(path, q)
    assert a.value == want and a.confidence >= 0.8


SMILEY_1OG = "data/ifc_models/kit-smiley-west_ac-20-smiley-west-10-bldg_plan-03-1-og.pdf"


@need
@pytest.mark.parametrize("path,q,want", [
    (ESPL, "How many doors are on the floor above this one?", 42),  # Q: the sheet's own 46 @ 0.97
    (SMILEY_1OG, "How many walls does the floor below this one have?", 81),
])
def test_relative_storey(path, q, want):
    from stoa.solvers.ifc.solver import IfcSolver

    assert IfcSolver(plan2d="0", llm="0").solve(path, q).value == want


@need
def test_whats_the_difference_is_a_count():
    a = plan_vs_model(ESPL, "If I count the doors on this plan and in the model, what's the difference?")
    assert a is not None and a.value == 0 and a.unit == "count"


FRIG = "data/ifc_models/bimspeed-frigento_modello-palazzo-testa-cipriano.ifc"


@pytest.mark.skipif(not abspath(FRIG).exists(), reason="frigento not available")
@pytest.mark.parametrize("q,want", [
    ("Which floor has the greatest number of doors?", "Piano 1"),  # Q v25: the whole-model 27 @ 0.97
    ("Which floor has the lowest number of doors?", "Solaio interrato"),
    ("What is the number of doors?", 27),
])
def test_greatest_number_of_is_a_floor_ranking(q, want):
    from stoa.solvers.ifc.solver import IfcSolver

    assert IfcSolver(plan2d="0", llm="0").solve(FRIG, q).value == want


@need
@pytest.mark.parametrize("q,want", [
    ("How many windows does the storey directly above this one have?", 60),  # Q bug 28: the sheet's 55 @ 0.88
    ("How many rooms are on the storey above?", 60),
    ("Quante finestre del modello IFC non sono disegnate in questa pianta?", 3),  # W4 10:49: 55 @ 0.875
    ("Wie viele Fenster des IFC-Modells sind in diesem Grundriss nicht eingezeichnet?", 3),
])
def test_relative_storey_wordings_and_not_drawn_languages(q, want):
    from stoa.solvers.ifc.solver import IfcSolver

    assert IfcSolver(plan2d="0", llm="0").solve(ESPL, q).value == want


@need
def test_above_ground_level_on_a_sheet_is_not_confident():
    from stoa.solvers.ifc.solver import IfcSolver

    a = IfcSolver(plan2d="0", llm="0").solve(ESPL, "How many windows are on the floors above ground level?")
    assert a.confidence <= 0.5
