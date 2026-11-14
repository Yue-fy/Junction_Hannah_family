"""Outer arithmetic around IFC quantities (stoa.solvers.ifc.arith + IfcSolver._outer): self-written wordings,
not from any split. Values are checked against the solver's own atomic answers, so the test checks the
arithmetic and the routing, not the dataset."""

from __future__ import annotations

import pytest

from stoa.data import abspath
from stoa.solvers.ifc.arith import detect, leftover_numbers

ESPL = "data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf"


@pytest.mark.parametrize("q,op,n,unit,basis,kind", [
    ("If each door costs 450 euros, how much do the doors on 'X' cost in total?", "mul", 450, "EUR", "count", "door"),
    ("At 35 EUR per square metre, what would it cost to clean all rooms on 'X'?", "mul", 35, "EUR", "area", None),
    ("If every window needs 2 curtains, how many curtains are needed on 'X'?", "mul", 2, "count", "count", "window"),
    ("Doors cost €320 each. What is the total cost of the doors on 'X'?", "mul", 320, "EUR", "count", None),
    ("How many doors would remain on 'X' if 5 were removed?", "sub", 5, None, None, None),
    ("How many doors are on 'X' if we add 3 more?", "add", 3, None, None, None),
    ("Are there more than 40 doors on 'X'?", "cmp", 40, None, None, None),
    ("Is the total room area on 'X' larger than 800 m²?", "cmp", 800, None, None, None),
])
def test_detect(q, op, n, unit, basis, kind):
    o = detect(q)
    assert o is not None and o.op == op and o.n == n
    assert o.unit == unit and o.basis == basis and o.basis_kind == kind


@pytest.mark.parametrize("q", [
    "How many doors are shown on the floor plan of '1.korrus'?",
    "What is the average net floor area per room (space) on 'Attic', in m²?",
    "How many of the rooms 'A (1.5)' and 'B (1.4)' on '1' have a net floor area of more than 13 m²?",
    "Which storey has more doors, '1.korrus' or '2.korrus'?",
    "How many doors per storey are there?",
])
def test_detect_leaves_templates_alone(q):
    o = detect(q)
    assert o is None or o.op != "mul"
    assert detect("What is the total net floor area of all spaces on '1.korrus', in m²?") is None


def test_leftover_numbers():
    assert leftover_numbers("How many walls are there on '1.korrus', minus 10?", []) == ["10"]
    assert leftover_numbers("What is the net floor area of the room 'Room (1.4)' on '1', in m²?", []) == []
    assert leftover_numbers("How many doors are on level 4 and on the 2nd floor?", []) == []
    assert leftover_numbers("What furniture is in room 112?", []) == []
    assert leftover_numbers("List the 5 largest rooms on '1.korrus'.", []) == []


@pytest.fixture(scope="module")
def solver():
    from stoa.solvers import get_solver

    return get_solver("ifc")


@pytest.mark.skipif(not abspath(ESPL).exists(), reason="dataset not available")
def test_outer_arithmetic_on_a_model(solver):
    doors = solver.solve(ESPL, "How many doors are there on '1.korrus'?").value
    windows = solver.solve(ESPL, "How many windows are there on '1.korrus'?").value
    rooms = solver.solve(ESPL, "How many rooms are there on '1.korrus'?").value
    area = solver.solve(ESPL, "What is the total net floor area of all spaces on '1.korrus'?").value
    a = solver.solve(ESPL, "If each door costs 450 euros, how much do the doors on '1.korrus' cost in total, in euros?")
    assert a.value == pytest.approx(doors * 450) and a.unit == "EUR" and a.confidence > 0.8 and a.evidence
    a = solver.solve(ESPL, "How many square metres of floor per door are there on '1.korrus'?")
    assert a.value == pytest.approx(area / doors, rel=1e-3)
    a = solver.solve(ESPL, "How many windows per room are there on '1.korrus' on average?")
    assert a.value == pytest.approx(windows / rooms, rel=1e-3)
    a = solver.solve(ESPL, "What is the ratio of doors to windows on '1.korrus'?")
    assert a.value == pytest.approx(doors / windows, rel=1e-3)
    assert solver.solve(ESPL, "How many doors would remain on '1.korrus' if 5 were removed?").value == doors - 5
    assert solver.solve(ESPL, f"Are there more than {doors - 1} doors on '1.korrus'?").value == "yes"
    assert solver.solve(ESPL, f"Are there more than {doors} doors on '1.korrus'?").value == "no"
    a = solver.solve(ESPL, "How many walls are there on '1.korrus', minus 10?")  # not modelled -> guard
    assert a.confidence <= 0.3 and any("10" in m for m in a.missing)


@pytest.mark.skipif(not abspath(ESPL).exists(), reason="dataset not available")
def test_scope_and_superlatives(solver):
    whole = solver.solve(ESPL, "How many doors are there in the whole building?")
    plan = solver.solve(ESPL, "How many doors are there on '1.korrus'?")
    assert whole.value > plan.value
    big = solver.solve(ESPL, "What is the area of the largest room on '1.korrus'?")
    total = solver.solve(ESPL, "What is the total net floor area of all spaces on '1.korrus'?")
    assert 0 < big.value < total.value and len({e.ifc_guid for e in big.evidence if e.ifc_guid}) == 1
    name = solver.solve(ESPL, "What is the name of the largest room on '1.korrus'?")
    assert isinstance(name.value, str) and f"{big.value:.2f}" in name.value
    st = solver.solve(ESPL, "Which storey has the most doors?")
    assert st.value == "1.korrus"


FZK = "data/ifc_models/kit-fzk-haus_ac20-fzk-haus_plan-01-erdgeschoss.pdf"


@pytest.mark.skipif(not abspath(FZK).exists(), reason="dataset not available")
def test_geometry_room_types_and_guards(solver):
    doors = solver.solve(FZK, "How many doors are there on 'Erdgeschoss'?").value
    a = solver.solve(FZK, "Wenn jede Tür 450 Euro kostet, wie viel kosten alle Türen im Erdgeschoss?")
    assert a.value == pytest.approx(doors * 450) and a.unit == "EUR"
    # the KIT FZK-Haus is a 12 m x 10 m house
    assert solver.solve(FZK, "What is the gross floor area of 'Erdgeschoss'?").value == pytest.approx(120, rel=0.02)
    assert solver.solve(FZK, "What is the perimeter of the building?").value == pytest.approx(44, rel=0.02)
    h = solver.solve(FZK, "How tall is the building?")
    assert 5 < h.value < 8 and h.unit == "m"
    ext = solver.solve(FZK, "What is the total length of external walls on 'Erdgeschoss'?")
    assert ext.value > 30 and ext.confidence <= 0.6  # no IsExternal in the model: walls on the outline
    w = solver.solve(FZK, "What is the window-to-wall ratio of the building?")
    assert w.unit == "%" and 5 < w.value < 40
    bath = solver.solve(FZK, "What is the total area of all bathrooms in the building?")
    rooms = solver.solve(FZK, "What is the total net floor area of all spaces in the whole building?")
    assert 0 < bath.value < rooms.value / 3  # 'Bad' only, not every room
    width = solver.solve(FZK, "What is the average door width on 'Erdgeschoss'?")
    assert width.unit == "m" and 0.7 < width.value < 1.5
    rel = solver.solve(FZK, "How many rooms on 'Erdgeschoss' have a balcony door facing the garden?")
    assert rel.confidence <= 0.3  # not modelled: guarded
    win = solver.solve(FZK, "What is the total window area on 'Erdgeschoss'?")
    assert win.unit == "m2" and 5 < win.value < 60
    share = solver.solve(FZK, "What percentage of the floor area on 'Erdgeschoss' is taken by the 'Wohnen' room?")
    assert 5 < share.value < 60


DUPLEX_L1 = "data/ifc_models/bsc-duplex_duplex-a-20110907.ifc"


@pytest.mark.skipif(not abspath(DUPLEX_L1).exists(), reason="dataset not available")
def test_room_type_scope_thresholds_and_ranges(solver):
    s = solver.solve
    n_bed = s(DUPLEX_L1, "How many bedrooms are there in the building?").value
    avg = s(DUPLEX_L1, "What is the average area of the bedrooms?")  # the sheet's storey has none: whole model
    assert n_bed >= 2 and avg.value > 5
    assert "Bedroom" in s(DUPLEX_L1, "What is the smallest bedroom?").value
    big = s(DUPLEX_L1, "What is the area of the largest room on 'Level 1'?").value
    small = s(DUPLEX_L1, "What is the area of the smallest room on 'Level 1'?").value
    rng = s(DUPLEX_L1, "How much bigger is the largest room than the smallest room on 'Level 1'?")
    assert rng.value == pytest.approx(big - small, abs=0.01) and rng.unit == "m2"
    l1 = s(DUPLEX_L1, "What is the total net floor area of all spaces on 'Level 1'?").value
    l2 = s(DUPLEX_L1, "What is the total net floor area of all spaces on 'Level 2'?").value
    assert s(DUPLEX_L1, "What is the total area of 'Level 1' and 'Level 2'?").value == pytest.approx(l1 + l2, abs=0.01)
    many = s(DUPLEX_L1, "How many rooms are larger than 20 m² in the whole building?")
    assert many.unit == "count" and 0 < many.value < 20
    tot = s(DUPLEX_L1, "What is the total floor area of rooms smaller than 10 m² on 'Level 2'?")
    assert tot.unit == "m2" and 0 < tot.value < l2
    each = s(DUPLEX_L1, "How many doors are there on each floor?")
    assert "Level 2" in each.value  # every storey, not only the sheet's
    assert s(DUPLEX_L1, "How many windows are on the north facade?").confidence <= 0.3
    assert s(DUPLEX_L1, "Which room has the most doors?").confidence <= 0.3
    share = s(DUPLEX_L1, "What percentage of the rooms on 'Level 1' are bathrooms?")
    assert share.unit == "%" and 0 < share.value < 50


ESPL2 = "data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-02-2-korrus.pdf"


@pytest.mark.skipif(not abspath(ESPL2).exists(), reason="dataset not available")
def test_lists_ranks_heights_and_storeys(solver):
    s = solver.solve
    big = s(ESPL2, "Which rooms on '2.korrus' are larger than 40 m²?")
    assert isinstance(big.value, str) and big.value.startswith("3 rooms") and "KORIDOR (202)" in big.value
    first = s(ESPL2, "What is the area of the largest room on '2.korrus'?").value
    second = s(ESPL2, "How many square metres is the second largest room on '2.korrus'?").value
    assert 0 < second < first
    assert s(ESPL2, "What is the median room area on '2.korrus'?").unit == "m2"
    assert s(ESPL2, "What is the ceiling height of the rooms on '2.korrus'?").value == pytest.approx(3.0, abs=0.05)
    assert s(ESPL2, "How many storeys does the building have above ground level?").value == 6  # not 'Vundament'
    assert s(ESPL2, "What is the elevation of the top storey?").value == pytest.approx(17.0)
    assert s(ESPL2, "Is the building taller than 15 m?").value == "yes"
    cmpd = s(ESPL2, "How many doors are there on '2.korrus' compared to '3.korrus'?")
    assert "2.korrus" in cmpd.value and "3.korrus" in cmpd.value
    assert s(ESPL2, "How many doors does the room 'KORIDOR (219)' have?").confidence <= 0.3


@pytest.mark.skipif(not abspath(FZK).exists(), reason="dataset not available")
def test_room_relations_by_geometry(solver):
    s = solver.solve
    ifc = "data/ifc_models/kit-fzk-haus_ac20-fzk-haus.ifc"
    no_win = s(ifc, "How many rooms on 'Erdgeschoss' have no window?")
    rooms = s(ifc, "How many rooms are there on 'Erdgeschoss'?").value
    assert no_win.unit == "count" and 0 <= no_win.value < rooms and no_win.confidence <= 0.7
    assert "Flur" in s(ifc, "Which rooms have more than one door?").value
    assert 1 <= s(ifc, "How many windows does the room 'Wohnen' have?").value <= 5


@pytest.mark.skipif(not abspath(ESPL).exists(), reason="dataset not available")
def test_rest_exclusion_and_revit_families(solver):
    s = solver.solve
    tot = s(ESPL, "What is the total net floor area of all spaces on '1.korrus'?").value
    k = s(ESPL, "What is the net floor area of the room 'KORIDOR (119)' on '1.korrus'?").value
    a = s(ESPL, "How much net floor area (m²) do all the other rooms on '1.korrus' have together, leaving out 'KORIDOR (119)'?")
    assert a.value == pytest.approx(tot - k, abs=0.01) and a.confidence > 0.8
    n = s(ESPL, "How many rooms are on '1.korrus' besides 'KORIDOR (119)'?").value
    assert n == s(ESPL, "How many rooms are there on '1.korrus'?").value - 1


def test_revit_family_prefix():
    from stoa.solvers.ifc.index import Element, type_key_fn

    e = Element(guid="g", cls="IfcBuildingElementProxy", name='Sink Vanity-Round:19" x 19":19" x 19":123456',
                type_name='19" x 19"')
    assert type_key_fn([e])(e) == 'Sink Vanity-Round:19" x 19"'
    e2 = Element(guid="h", cls="IfcWall", name="22_Wall_DD-ytong", type_name="22_Wall_DD-ytong")
    assert type_key_fn([e2])(e2) == "22_Wall_DD-ytong"


@pytest.mark.skipif(not abspath(ESPL).exists(), reason="dataset not available")
def test_fresh_wordings_of_operators(solver):
    s = solver.solve
    d1 = s(ESPL, "How many doors are there on '1.korrus'?").value
    d5 = s(ESPL, "How many doors are there on '5.korrus'?").value
    allv = s(ESPL, "How many doors are there in the whole building?").value
    assert s(ESPL, "Does '1.korrus' or '2.korrus' contain more doors?").value == "1.korrus"
    assert s(ESPL, f"By how many doors does '1.korrus' exceed '5.korrus'?").value == d1 - d5
    assert s(ESPL, "Out of all doors in the model, what percentage sit on '1.korrus'?").value == \
        pytest.approx(d1 / allv * 100, abs=0.01)
    a1 = s(ESPL, "What is the total net floor area of all spaces on '1.korrus'?").value
    a5 = s(ESPL, "What is the total net floor area of all spaces on '5.korrus'?").value
    assert s(ESPL, "How many times larger is the room area on '1.korrus' than on '5.korrus'?").value == \
        pytest.approx(a1 / a5, abs=0.001)
    n = s(ESPL, "How many rooms are there on '1.korrus'?").value
    assert s(ESPL, "Divide the total room area of '1.korrus' by its number of rooms. What do you get?").value == \
        pytest.approx(a1 / n, abs=0.01)


@pytest.mark.skipif(not abspath(ESPL).exists(), reason="dataset not available")
def test_false_premises_and_units(solver):
    s = solver.solve
    smiley = "data/ifc_models/kit-smiley-west_ac-20-smiley-west-10-bldg.ifc"
    assert s(smiley, "How many doors are in the model 'Empire State Building'?").confidence <= 0.3
    assert s(smiley, "Count all columns in the model 'Smiley West (terraced houses)'.").confidence > 0.9  # a nickname
    a = s(ESPL, "What is the total net floor area of all rooms on '7.korrus'?")  # no such storey: not '1.korrus'
    assert a.value is None or a.confidence <= 0.3
    m = s(ESPL, "What is the total length of the walls on '1.korrus'?")
    mm = s(ESPL, "What is the total length of the walls on '1.korrus', in millimetres?")
    assert mm.unit == "mm" and mm.value == pytest.approx(m.value * 1000, rel=1e-6)
