"""IFC solver tests on the duplex model (train split, CC BY): phrasings that are NOT in questions.jsonl or the
hard split, to check the parser generalises. Values come from the model itself (geometry / Qto)."""

from __future__ import annotations

import pytest

from stoa.data import abspath
from stoa.solvers.ifc.parse import parse

DUPLEX = "data/ifc_models/bsc-duplex_duplex-a-20110907.ifc"

pytestmark = pytest.mark.skipif(not abspath(DUPLEX).exists(), reason="dataset not available")


@pytest.fixture(scope="module")
def solver():
    from stoa.solvers import get_solver

    return get_solver("ifc")


@pytest.mark.parametrize("q,metric,kinds,op", [
    ("How many doors are shown on the floor plan of 'Level 1'?", "count", ["door"], None),
    ("Count the windows on 'Level 2'.", "count", ["window"], None),
    ("Number of columns on '1.korrus'?", "count", ["column"], None),
    ("Wie viele Fenster und Türen gibt es im Geschoss 'EG' insgesamt?", "count", ["window", "door"], "sum"),
    ("Hoeveel deuren staan er op de plattegrond van '00 Begane grond'?", "count", ["door"], None),
    ("Wat is de netto vloeroppervlakte van de ruimte 'Kitchen (A103)' op 'Level 1', in m²?", "area", ["space"], None),
    ("What is the total net side area of all walls on 'Level 1', in m²?", "area", ["wall"], None),
    ("Wie groß ist das gesamte Netto-Volumen aller Wände im Geschoss „EG“ in m³?", "volume", ["wall"], None),
    ("Which room on 'Level 2' is bigger: 'Bedroom 1 (A202)' or 'Hallway (A201)'?", "area", ["space"], "argmax"),
    ("Are there more doors than windows on 'Level 1'?", "count", ["door", "window"], "diff"),
])
def test_parse(q, metric, kinds, op):
    it = parse(q)
    assert it.metric == metric
    assert it.kinds[: len(kinds)] == kinds
    assert it.op == op
    assert not it.gross  # "wie groß" must not read as a gross quantity


def _val(solver, q, path=DUPLEX):
    a = solver.solve(path, q)
    assert a.value is not None, a.trace
    return a


def test_room_area_both_orders_and_units(solver):
    a1 = _val(solver, "What is the net floor area of the room 'Living Room (A102)' on 'Level 1', in m²?")
    assert a1.value == pytest.approx(27.66, rel=0.02) and a1.unit == "m2"
    assert a1.evidence and a1.evidence[0].ifc_guid
    a2 = _val(solver, "On 'Level 1', how large is the living room 'Living Room (A102)' in square feet?")
    assert a2.unit == "ft2" and a2.value == pytest.approx(27.66 * 10.7639, rel=0.02)


def test_counts_with_evidence(solver):
    a = _val(solver, "How many doors are shown on the floor plan of 'Level 1'?")
    assert a.value == 6 and len(a.evidence) == 6 and all(e.ifc_guid for e in a.evidence)
    b = _val(solver, "Count the doors and windows on 'Level 1' together.")
    w = _val(solver, "How many windows are shown on the floor plan of 'Level 1'?")
    assert b.value == a.value + w.value
    m = _val(solver, "How many windows are there in the model 'Duplex Apartment - architectural'?")
    assert m.value == 24


def test_argmax_returns_the_asked_label(solver):
    a = _val(solver, "Which of the rooms 'Kitchen (A103)', 'Living Room (A102)' and 'Foyer (A101)' on 'Level 1' "
                     "has the largest net floor area?")
    assert a.value == "Living Room (A102)"


def test_plan_pdf_storey(solver):
    from stoa.solvers.ifc import load_index, plan_storey

    idx = load_index("data/ifc_models/bimspeed-gdynia_ruchu-oporu-18.ifc")
    st, why = plan_storey("data/ifc_models/bimspeed-gdynia_ruchu-oporu-18_plan-02-1.pdf", idx)
    assert st.name == "-1", why  # slug '1' is ambiguous between '-1' and '1': plan number decides
    st, _ = plan_storey("data/ifc_models/bimspeed-gdynia_ruchu-oporu-18_plan-04-1.pdf", idx)
    assert st.name == "1"
