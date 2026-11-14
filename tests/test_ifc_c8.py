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
