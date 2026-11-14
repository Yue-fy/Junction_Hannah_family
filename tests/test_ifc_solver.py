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


def test_storeys_filters_and_room_types(solver):
    st = _val(solver, "How many storeys does the building have?")  # T/FDN: no room/door; Roof: a roof space only
    assert st.value == 2 and st.confidence <= 0.6 and any("with them: 4" in m for m in st.missing)
    assert _val(solver, "What is the elevation of storey 'Level 2'?").value == pytest.approx(3.1, abs=0.01)
    ext = _val(solver, "How many external walls are on 'Level 1'?")
    allw = _val(solver, "How many walls are shown on the floor plan of 'Level 1'?")
    assert 0 < ext.value < allw.value
    assert _val(solver, "How many bathrooms are there on 'Level 2'?").value == 2  # bare noun vs the model's labels
    a = _val(solver, "What is the total floor area of all 'Bedroom' rooms on 'Level 2'?")
    assert a.unit == "m2" and len(a.evidence) == 4


def test_geometry_fallback_lowers_confidence():
    from stoa.solvers import get_solver

    s = get_solver("ifc", qto="0")
    q = "What is the total length of all walls on 'Level 1', in metres?"
    a = s.solve(DUPLEX, q)
    assert a.value and a.confidence < 0.7 and any("geometry" in x for x in a.assumptions)


GDYNIA = "data/ifc_models/bimspeed-gdynia_ruchu-oporu-18.ifc"


@pytest.mark.skipif(not abspath(GDYNIA).exists(), reason="gdynia not available")
@pytest.mark.parametrize("q, gold", [
    ("What is the average net floor area per room (space) on '1', in m²?", 8.293),
    ("What percentage of the total net floor area of '0' does the room 'Comunication (0.2)' take up?", 13.09),
    ("How many of the rooms 'Bathroom (1.5)', 'Room (1.4)', 'Kitchen (1.2)' and 'Room (1.3)' on '1' have a net "
     "floor area of more than 13 m²?", 1),
    ("Which storey has more doors on its floor plan, '0' or '-1'?", "0"),
    ("What is the combined net floor area of all rooms (spaces) on '0' and on '-1', in m²?", 102.92),
])
def test_operators_compose_atomic_answers(solver, q, gold):
    """hard2 kinds (average, share, threshold, which storey, multi-storey sum): composed in code from atomic
    answers; the storey name '1' must not swallow the '1' of '13 m²'."""
    a = solver.solve(GDYNIA, q)
    if isinstance(gold, str):
        assert a.value == gold
    else:
        assert a.value == pytest.approx(gold, rel=0.02)
    assert a.evidence and a.confidence >= 0.8


ARC4351 = "data/ifc_bench/4351_arc.ifc"


@pytest.mark.skipif(not abspath(ARC4351).exists(), reason="4351 not available")
def test_material_filter_dimensions_and_fallbacks():
    """IFC-Bench style (own wording): material filters by type name, else by layer share; foundations without
    IfcFooting; door widths from OverallWidth; switches modelled as proxies; Revit ids stripped from type names."""
    from stoa.solvers import get_solver

    s = get_solver("ifc", llm="0", plan2d="0")
    # 4 walls are typed '... Concrete' (name beats the 'Concrete Masonry Units' layer of the brick walls)
    a = s.solve(ARC4351, "How many cubic metres of concrete are in the walls?")
    assert a.value == pytest.approx(31.484, rel=0.01)
    # insulation is one layer of the brick walls: volume x layer share
    a = s.solve(ARC4351, "Total volume of insulation in the walls?")
    assert a.value == pytest.approx(81.70, rel=0.01)
    # no IfcFooting: the pad slab + the foundation walls
    a = s.solve(ARC4351, "What volume of concrete do the foundations need?")
    assert a.value == pytest.approx(153.754, rel=0.01)
    # floor slabs exclude the pad
    a = s.solve(ARC4351, "Concrete volume of the floor slabs?")
    assert a.value == pytest.approx(273.91, rel=0.01)
    a = s.solve(ARC4351, "What is the mean width of the doors?")
    assert a.value == pytest.approx(0.992, abs=0.002) and a.unit == "m"
    assert s.solve(ARC4351, "How many doors are narrower than 1 m?").value == 14  # 14 x 914 mm, 3 wider
    assert s.solve(ARC4351, "How many walls are thicker than 200 mm?").value == 14
    a = s.solve(ARC4351, "How many light switches does the building have?")
    assert a.value == 16 and a.confidence <= 0.6  # counted by name: capped
    a = s.solve(ARC4351, "Which wall types are used, with their quantities and materials?")
    assert "Basic Wall:Exterior - Brick on CMU: 8" in a.value and ":250" not in a.value
    assert "Masonry - Brick" in a.value
    a = s.solve(ARC4351, "Give me the space breakdown of the first floor with the areas of each room")
    assert "Kitchen" in a.value


def test_parse_material_and_negated_loadbearing():
    assert parse("Volume of steel beams?").material == "steel"
    assert parse("Volume of beams?").material is None
    assert parse("How many non-load-bearing walls are there?").filters == {"LoadBearing": False}
    assert parse("How many load-bearing walls are there?").filters == {"LoadBearing": True}
    assert parse("What pipe accessories are installed?").kind == "pipe_accessory"
