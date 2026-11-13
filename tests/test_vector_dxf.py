"""W2: the `dxf` solver on one swiss floor (needs the dataset; skipped without it)."""

import pytest

from stoa.data import abspath
from stoa.solvers.vector import qparse

P = "data/swiss_dwellings/site1000_bldg2082_floor9385.pdf"
needs_data = pytest.mark.skipif(not abspath(P).exists(), reason="dataset not available")


def test_parse_compositions():
    q = qparse.parse("How many more doors than windows are shown on this floor plan?")
    assert q.op == "diff" and [t.arg for t in q.terms] == ["door", "window"]
    q = qparse.parse("What is the combined net floor area of apartments C and B in m² (all rooms except balconies)?")
    assert [t.arg for t in q.terms] == ["C", "B"] and q.unit == "m2"
    q = qparse.parse("What is the net floor area of room 0.04 ('Korridor') in square feet?", ["Korridor"])
    assert q.terms[0].kind == "area_room" and q.unit == "ft2"
    q = qparse.parse("How many rooms labelled 'Cage d'escalier' are there on this floor?", ["Cage d'escalier"])
    assert q.terms[0].kind == "count_label" and q.terms[0].arg == "Cage d'escalier"
    q = qparse.parse("Combien de pièces portant la désignation « Pièce » y a-t-il à cet étage ?", ["Pièce"])
    assert q.terms[0].arg == "Pièce"


@needs_data
def test_dxf_solver_floor():
    from stoa.solvers import get_solver

    s = get_solver("dxf")
    a = s.solve(P, "How many toilets (WC) are drawn on this floor plan?")
    assert a.value == 4 and len(a.evidence) == 4 and a.evidence[0].bbox_space == "pdf_pt"
    assert s.solve(P, "Wie viele Lavabos sind auf diesem Grundriss eingezeichnet?").value == 4
    a = s.solve(P, "What is the net floor area of room 2.10 ('Zimmer') in m²?")
    assert abs(a.value - 16.78) < 0.02 and "✓" in a.evidence[0].note
    a = s.solve(P, "How many windows are drawn on this floor plan?")
    assert a.value == 28 and len(a.evidence) == 28


def test_parse_scope_and_area_options():
    q = qparse.parse("How many windows are there in apartment B?")
    assert [(t.kind, t.arg, t.scope) for t in q.terms] == [("count", "window", ["B"])]
    assert qparse.covered("How many windows are there in apartment B?", q)
    # Swiss German "wie gross" means "how large", not "gross area"
    q = qparse.parse("Wie gross ist die Nettowohnfläche von Wohnung A in m² (Summe aller Räume ohne Balkone)?")
    assert not q.gross and not q.include_outdoor and q.terms[0].kind == "area_apartment"
    assert qparse.parse("What is the gross floor area of apartment B?").gross
    assert qparse.parse("Net floor area of apartment A in m² including balconies?").include_outdoor


@needs_data
def test_dxf_scoped_counts():
    from stoa.solvers import get_solver

    s = get_solver("dxf", llm=0)
    a = s.solve(P, "How many windows are there in apartment B?")
    assert 0 < a.value < 28 and len(a.evidence) == a.value


def test_parse_reasoning_ops():
    v = ["Bad", "Zimmer"]
    assert qparse.parse("What is the average net floor area of rooms 2.03 ('Bad') and 2.01 ('Zimmer'), in m²?", v).op == "mean"
    q = qparse.parse("On average, how many doors are drawn per apartment on this floor plan?")
    assert q.op == "ratio" and [t.arg for t in q.terms] == ["door", "apartment"]
    q = qparse.parse("What share of the total net floor area of all numbered indoor rooms on this floor does apartment C "
                     "take up, in percent?")
    assert q.op == "pct" and [t.kind for t in q.terms] == ["area_apartment", "area_total"]
    q = qparse.parse("What is the total net floor area, in m², of the numbered indoor rooms on this floor that do not "
                     "belong to apartment A?")
    assert q.op == "diff" and [t.kind for t in q.terms] == ["area_total", "area_apartment"]
    q = qparse.parse("How many of the rooms 3.01 ('Bad') and 3.05 ('Zimmer') have a net floor area of more than 15 m²?", v)
    assert q.op == "count_gt" and q.threshold == 15.0 and qparse.covered("How many of the rooms 3.01 ('Bad') and 3.05 "
                                                                         "('Zimmer') have a net floor area of more than 15 m²?", q)
