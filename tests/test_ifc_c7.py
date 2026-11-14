"""Cycle-7 fixes from Q's red-team v19 (list answers): a room label / type narrows a threshold list, sets of
storeys by a count or area threshold, and where a room is. Self-written wordings, not from any split; expected
values are the model's own rooms and counts (esplanades: rooms per floor 1..5.korrus = 50/60/60/60/55, doors
46/42/42/42/39; one MAGAMISTUBA on each of 2..5.korrus; SERVER (117) on 1.korrus)."""

from __future__ import annotations

import re

import pytest

from stoa.data import abspath
from stoa.solvers.ifc.index import load_index
from stoa.solvers.ifc.solver import IfcSolver, model_for, room_filter

ESPL = "data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf"
WARM = "data/ifc_models/bimspeed-warmond_ar_plan-03-1-level.pdf"
HUB = "data/ifc_models/rwth-digitalhub_digitalhub-fm-arc-v2_plan-02-e00-okrd.pdf"
need = pytest.mark.skipif(not abspath(ESPL).exists(), reason="dataset not available")


@pytest.fixture(scope="module")
def solver():
    return IfcSolver(plan2d="0", llm="0")


@need
@pytest.mark.parametrize("q,what,how,n", [
    ("Which ELUTUBA+KÖÖK rooms on '1.korrus' are smaller than 25 m²?", "ELUTUBA+KÖÖK", "label", 80),
    ("What is the total area of the TUALETTRUUM rooms that are larger than 5 m²?", "TUALETTRUUM", "label", None),
    ("Which rooms on '1.korrus' are larger than 50 m²?", None, "", 0),
    ("Which rooms on the first floor are larger than 20 m²?", None, "", 0),
])
def test_room_filter_esplanades(q, what, how, n):
    idx = load_index(model_for(ESPL))
    w, grp, h = room_filter(idx, q)
    assert (w, h) == (what, how)
    if n is not None:
        assert len(grp) == n


@need
def test_room_filter_plural_and_type():
    hub = load_index(model_for(HUB))
    assert room_filter(hub, "Welche Gruppenbüros sind größer als 37 m²?")[0] == "Gruppenbüro"
    assert room_filter(hub, "Which WCs are larger than 14 m²?")[2] == "type"
    warm = load_index(model_for(WARM))
    assert room_filter(warm, "Which floors have more than 50 rooms?")[0] is None  # 'Floor' is a warmond room label


@need
@pytest.mark.parametrize("q,want,not_want", [
    ("Which ELUTUBA+KÖÖK rooms on '1.korrus' are smaller than 25 m²?", [r"\b6-1\b"], [r"TUALETTRUUM", r"ESIK"]),
    ("Which floors have more than 55 rooms?", [r"2\.korrus", r"3\.korrus", r"4\.korrus"], [r"1\.korrus", r"5\.korrus"]),
    ("Which floors have fewer than 42 doors?", [r"5\.korrus"], [r"[1-4]\.korrus", r"Katus", r"Vundament"]),
    ("On which floors is there a room called MAGAMISTUBA?", [r"2\.korrus", r"5\.korrus"], [r"1\.korrus"]),
    ("On which floor is the room SERVER?", [r"1\.korrus"], [r"[2-5]\.korrus"]),
    ("On which storey is the space 'LIFT'?", [r"1\.korrus"], [r"\b50\b"]),
    ("Name the rooms on '1.korrus' whose net floor area is between 20 and 25 m².", [r"between 20 and 25", r"\b110\b"], []),
])
def test_lists_esplanades(solver, q, want, not_want):
    a = solver.solve(ESPL, q)
    v = str(a.value)
    assert all(re.search(x, v) for x in want), v
    assert not any(re.search(x, v) for x in not_want), v
    assert a.confidence >= 0.8


@need
@pytest.mark.parametrize("path,q,n", [
    (ESPL, "How many ELUTUBA+KÖÖK rooms on '1.korrus' are larger than 25 m²?", 9),
    (ESPL, "How many floors have more than 55 rooms?", 3),
    (ESPL, "How many floors have rooms called ESIK?", 5),
    (WARM, "How many bedrooms on '1. Level' are larger than 10.8 m²?", 4),
])
def test_counts(solver, path, q, n):
    a = solver.solve(path, q)
    assert a.value == n and a.unit == "count"


@need
def test_threshold_sum_room_set(solver):
    a = solver.solve(ESPL, "What is the total area of the TUALETTRUUM rooms on '1.korrus' that are larger than 5 m²?")
    assert a.unit == "m2" and a.value == pytest.approx(52.11, rel=0.01)


@need
def test_storey_area_threshold(solver):
    a = solver.solve(ESPL, "Which floors have a total floor area of more than 860 m²?")
    assert re.search(r"1\.korrus", str(a.value)) and not re.search(r"[2-5]\.korrus", str(a.value))


@need
@pytest.mark.parametrize("q,want,not_want", [
    ("Does this drawing show every window that the model has on '1.korrus'?", [r"^no\b", r"\b52\b", r"\b55\b"], []),
    ("Are all the doors of the model on '1.korrus' drawn on this plan?", [r"^yes\b", r"\b46\b"], []),
    ("Which sheet shows the server room?", [r"plan-01", r"1\.korrus"], [r"plan-0[2-5]"]),
    ("On which drawing is the room 'MAGAMISTUBA (41-2)'?", [r"plan-03", r"3\.korrus"], [r"plan-0[1245]"]),
])
def test_plan_and_sheet(solver, q, want, not_want):
    a = solver.solve(ESPL, q)
    v = str(a.value)
    assert all(re.search(x, v) for x in want), v
    assert not any(re.search(x, v) for x in not_want), v


SMILEY_IFC = "data/ifc_models/kit-smiley-west_ac-20-smiley-west-10-bldg.ifc"
SMILEY_1OG = "data/ifc_models/kit-smiley-west_ac-20-smiley-west-10-bldg_plan-03-1-og.pdf"
WARM_IFC = "data/ifc_models/bimspeed-warmond_ar.ifc"


@need
@pytest.mark.parametrize("path,q,n", [
    (SMILEY_IFC, "How many walls are there on the ground floor?", 81),   # 'EG' by name (F 09:24: 281 whole model)
    (SMILEY_IFC, "Count the walls at ground level.", 81),
    (SMILEY_IFC, "Wie viele Türen gibt es im Erdgeschoss?", 50),
    ("data/ifc_models/bsc-esplanades_1807-ep-ar-v18.ifc", "How many doors are on the ground floor?", 46),  # elevation 0
    (WARM_IFC, "How many doors are on the ground floor?", 46),  # '1. Level' at 0.0, not 'Entrance' at -1.6
])
def test_ground_floor_role(solver, path, q, n):
    a = solver.solve(path, q)
    assert a.value == n


@need
@pytest.mark.parametrize("path,q,want", [
    (ESPL, "How many of the model's windows on '1.korrus' does this drawing not show?", r"^3$"),
    (ESPL, "Stimmen Grundriss und IFC-Modell bei der Anzahl der Fenster überein?", r"^no\b"),
    (ESPL, "Which sheet is the floor plan of '3.korrus'?", r"plan-03-3-korrus"),
    (SMILEY_1OG, "Which sheet shows the ground floor?", r"plan-02-eg"),
    ("data/ifc_models/bimspeed-warmond_ar_plan-03-1-level.pdf", "How many section drawings belong to this model?", r"^2$"),
    ("data/ifc_models/bimspeed-warmond_ar_plan-03-1-level.pdf", "Which sheet shows the attic?", r"plan-08-attic"),
])
def test_v20_links(solver, path, q, want):
    a = solver.solve(path, q)
    assert re.search(want, str(a.value)), a.value


@pytest.mark.parametrize("q,two", [
    ("Montako ovea ja montako ikkunaa kerroksessa '1.korrus' on?", True),
    ("Ile drzwi i ile okien jest na kondygnacji '1.korrus'?", True),
    ("Quante porte e quante finestre ci sono su '1.korrus'?", True),
    ("How many doors and how many windows are there on '1.korrus'?", True),
    ("Which window types are present in this building, including their sizing and quantities?", False),
    ("How many doors and windows are there on '1.korrus'?", False),
])
def test_two_questions_any_language(q, two):
    assert bool(IfcSolver._two_q(q)) is two


GDYNIA = "data/ifc_models/bimspeed-gdynia_ruchu-oporu-18_plan-03-0.pdf"
TUW_DG1 = "data/ifc_models/tuwien-escape-route_real-world-escape-route-test-model-zdb_plan-05-dg1.pdf"
TUW_UG2 = "data/ifc_models/tuwien-escape-route_real-world-escape-route-test-model-zdb_plan-01-ug2.pdf"
INST_EG = "data/ifc_models/kit-institute_ac20-institute-var-2_plan-02-erdgeschoss.pdf"
WARM2 = "data/ifc_models/bimspeed-warmond_ar_plan-05-2-level.pdf"


@need
@pytest.mark.parametrize("path,q,want", [   # R1's link probe (experiments/r1/kg_qa/probe_kg.jsonl on night-R1)
    (GDYNIA, "How many sheets in total belong to this building (plans, sections and elevations)?", r"^10$"),
    (GDYNIA, "Is there a section drawing of this building in the set?", r"^yes"),
    (INST_EG, "Le plan et la maquette IFC indiquent-ils le même nombre de portes au niveau 'Erdgeschoss' ?", r"^yes"),
    (TUW_DG1, "Does the model contain more windows on storey 'DG1' than the 'DG1' floor plan shows?", r"^yes"),
    (TUW_UG2, "Does the 'UG2' floor plan show doors that the model does not assign to 'UG2'?", r"^yes"),
    (WARM2, "Which storeys of the model have no rooms at all?", r"^Basement; Entrance; Intermediate level 1; Intermediate level 2$"),
    (WARM2, "Wie viele Grundrisse gibt es für dieses Gebäude?", r"^8$"),
    (WARM2, "Kuinka monta leikkauspiirustusta tästä rakennuksesta on?", r"^2$"),
    (SMILEY_1OG, "Welche Geschosse des Modells haben keinen eigenen Grundriss?", r"^Dach$"),
    (SMILEY_1OG, "How many walls are there on the ground floor?", r"^81$"),  # Q 09:45: not the sheet's 1.OG (70)
])
def test_r1_links(solver, path, q, want):
    a = solver.solve(path, q)
    assert re.search(want, str(a.value)), a.value
    assert a.confidence >= 0.8


DUPLEX_IFC = "data/ifc_models/bsc-duplex_duplex-a-20110907.ifc"


@need
@pytest.mark.parametrize("q,want,not_want", [   # Q v24 (duplex lists)
    ("Apart from the living rooms and kitchens, which rooms on 'Level 1' are larger than 10 m²?", [r"A101", r"B101"],
     [r"A102", r"A103", r"B103"]),
    ("Which rooms on 'Level 1' larger than 10 m² are not living rooms?", [r"A101", r"A103"], [r"A102", r"B102"]),
    ("What is the largest room on 'Level 2'?", [r"tie", r"A202", r"A203", r"B202", r"B203"], []),
    ("What is the smallest room on 'Level 2'?", [r"B205"], [r"A205", r"tie"]),   # 1.40 vs 1.42 is not a tie
])
def test_v24_lists(solver, q, want, not_want):
    v = str(solver.solve(DUPLEX_IFC, q).value)
    assert all(re.search(x, v) for x in want), v
    assert not any(re.search(x, v) for x in not_want), v
