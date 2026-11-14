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


P2 = "data/swiss_dwellings/site760_bldg1652_floor10897.pdf"  # French labels, apartments A and B


def test_parse_sets_and_superlatives():
    # superlatives over a set, not a sum (cycle 2: these returned the floor total at conf 0.95)
    q = qparse.parse("What is the area of the largest room on this floor?")
    assert (q.qtype, q.op, q.terms[0].kind) == ("area", "max", "rooms")
    assert qparse.parse("Which is the largest room on this floor?").qtype == "text"
    q = qparse.parse("Quelle est la surface de la plus grande pièce ?")
    assert (q.qtype, q.op, q.terms[0].kind) == ("area", "max", "rooms")
    assert qparse.parse("Qual è la stanza più grande?").terms[0].kind == "rooms"
    q = qparse.parse("Which apartment is the largest?")
    assert (q.qtype, q.terms[0].kind, q.terms[0].arg) == ("text", "area_apartment", "<all>")
    assert qparse.parse("What is the average apartment size on this floor in m²?").op == "mean"
    q = qparse.parse("How many apartments are larger than 60 m²?")
    assert (q.op, q.threshold, q.terms[0].arg) == ("count_gt", 60.0, "<all>")
    # comparatives stay comparisons (not superlatives)
    q = qparse.parse("De combien la pièce 2.04 est-elle plus grande que la pièce 2.05 en m² ?")
    assert q.op == "diff" and not qparse.operator_unapplied("De combien la pièce 2.04 est-elle plus grande que la pièce 2.05 en m² ?", q)
    # concept words inside exclusion clauses are not the subject
    for txt in ("What is the net floor area of apartment A in m², summing all its rooms except balconies, loggias, "
                "terraces and other outdoor spaces?",
                "Wie gross ist die Nettowohnfläche von Wohnung A in m² (Summe aller Räume ohne Balkone, Loggien)?",
                "Quelle est la surface nette de l'appartement B en m² (somme de toutes ses pièces, hors balcons) ?"):
        assert qparse.parse(txt).terms[0].kind == "area_apartment", txt
    # a nested superlative is not covered by the rules
    q = qparse.parse("How many rooms does the largest apartment have?")
    assert not qparse.covered("How many rooms does the largest apartment have?", q)


@needs_data
def test_dxf_sets_and_scopes():
    from stoa.solvers import get_solver

    s = get_solver("dxf", llm=0)
    a = s.solve(P2, "What is the area of the largest room on this floor?")
    assert abs(a.value - 24.03) < 0.02 and len(a.evidence) == 1
    assert s.solve(P2, "Which apartment is the largest?").value == "apartment B"
    assert abs(s.solve(P2, "What is the area of the kitchen in apartment A?").value - 9.84) < 0.02
    assert abs(s.solve(P2, "What is the total area of all bathrooms on this floor?").value - 14.29) < 0.05
    assert s.solve(P2, "How many bathrooms does apartment A have?").value == 2
    assert s.solve(P2, "How many rooms are smaller than 5 m²?").value == 11
    assert s.solve(P2, "What is the smallest room in apartment B?").value == "room 2.12 (Réduit)"
    a = s.solve(P2, "How many bedrooms are on this floor?")  # no 'Chambre à coucher' label: 'Pièce' rooms, said so
    assert a.value == 8 and a.confidence <= 0.5 and any("bedroom" in x for x in a.assumptions)
    a = s.solve(P2, "What is the net floor area of apartment A in m², summing all its rooms except balconies, loggias, "
                    "terraces and other outdoor spaces?")
    assert abs(a.value - 105.93) < 0.02


@needs_data
def test_dxf_unknown_undotted_room_abstains():
    # W4: "room 1" (no dot, not on this floor) was read as the floor total at conf 0.96
    from stoa.solvers import get_solver

    s = get_solver("dxf", llm=0)
    a = s.solve(P2, "What is the net floor area of room 1 in m²?")
    assert a.value is None and a.missing
    assert abs(s.solve(P2, "What is the net floor area of room 2.05 ('Cuisine') in m²?").value - 9.84) < 0.02


def test_schedule_legend_explains_bare_codes():
    """A bare code answer gets its meaning from the sheet's own legend, matched to the question's topic."""
    from stoa.solvers.vector.pdftables import Cell, Row
    from stoa.solvers.vector.schedule_solver import _explain_codes, _legend

    def row(y, *texts):
        return Row(y=y, cells=[Cell(t, 10.0 * i, 10.0 * i + 8, y, (10.0 * i, y, 10.0 * i + 8, y + 2))
                               for i, t in enumerate(texts)])
    rows = [row(0, "FLOOR FINISH LEGEND"), row(1, "F2", "ARTIFICIAL TURF"), row(2, "F4", "RESILIENT FLOORING"),
            row(3, "BASE LEGEND"), row(4, "B2", "CERAMIC TILE")]
    leg = _legend(rows)
    value, found = _explain_codes("F4", "What floor finish is specified for room 101?", rows, leg)
    assert value == "F4 - RESILIENT FLOORING" and found[0][2] == (0.0, 2, 18.0, 4)  # code + meaning cells
    value, _ = _explain_codes("F2 & F4", "Which floor finishes are used in the gym?", rows, leg)
    assert value == "F2 (ARTIFICIAL TURF) & F4 (RESILIENT FLOORING)"
    # a door type "B2" must not be explained by the base legend
    assert _explain_codes("B2", "What door type is door 104?", rows, leg) is None
    assert _explain_codes("3 rooms, 4541 SF", "How many rooms are offices?", rows, leg) is None


def _cells(y, *spec):
    """spec: (text, x0) pairs -> cells with one word each (word boxes = visual boxes)."""
    from stoa.solvers.vector.pdftables import Cell, Row
    cells = []
    for text, x0 in spec:
        x1 = x0 + 6 * len(text)
        words, x = [], x0
        for w in text.split():
            words.append((x, x + 6 * len(w), w, (x, y, x + 6 * len(w), y + 8)))
            x += 6 * len(w) + 6
        cells.append(Cell(text, x0, x1, y, (x0, y, x1, y + 8), tuple(words)))
    return Row(y=y, cells=cells)


def test_pdftables_grouped_headers_and_glued_cells():
    """Group labels over duplicated sub-headers become prefixes; a dimension glued to the next column's word is split."""
    from stoa.solvers.vector.pdftables import find_tables
    rows = [_cells(0, ("Door", 230), ("Frame", 330)),
            _cells(12, ("No", 100), ("Width", 160), ("Matl", 230), ("Matl", 300), ("Type", 360)),
            _cells(24, ("101", 100), ("3' - 0\"", 160), ("WD", 230), ("HM", 300), ("A", 360)),
            _cells(36, ("102", 100), ("3' - 0\"", 160), ("AL", 230), ("AL", 300), ("B", 360)),
            _cells(48, ("103", 100), ("2' - 6\" SLIDER", 160), ("WD", 230), ("HM", 300), ("A", 360)),
            _cells(60, ("104", 100), ("3' - 0\"", 160), ("WD", 230), ("STL", 300), ("A", 360))]
    # the glued row: "SLIDER" sits under no column of its own here, so it must stay (no empty column to its right)
    t = find_tables(rows, h=8.0)[0]
    assert t.columns == ["No", "Width", "Door Matl", "Frame Matl", "Frame Type"], t.columns
    assert list(t.df["Frame Matl"]) == ["HM", "AL", "HM", "STL"]


def test_pdftables_split_glued_dimension_into_empty_column():
    from stoa.solvers.vector.pdftables import _split_glued
    from stoa.solvers.vector.pdftables import Cell
    words = ((100, 130, "6'", (0, 0, 1, 1)), (136, 142, "-", (0, 0, 1, 1)), (148, 154, "5", (0, 0, 1, 1)),
             (160, 178, "3/8\"", (0, 0, 1, 1)), (215, 251, "SLIDER", (2, 0, 3, 1)))
    c = Cell("6' - 5 3/8\" SLIDER", 100, 251, 0, (0, 0, 3, 1), words)
    xs, vals, cb = [130.0, 240.0, 320.0], ["6' - 5 3/8\" SLIDER", "", "T.B.D."], [None, None, None]
    _split_glued([c], xs, vals, cb, lambda cell: 0)
    assert vals == ["6' - 5 3/8\"", "SLIDER", "T.B.D."]
    # the right-hand column is already filled: keep the cell as it is
    vals2 = ["6' - 5 3/8\" SLIDER", "SWING", ""]
    _split_glued([c], xs, vals2, [None] * 3, lambda cell: 0)
    assert vals2[0] == "6' - 5 3/8\" SLIDER"


def test_pdftables_stacked_schedules_and_totals():
    """Two schedules side by side, a third stacked under the right one (repeated header words), printed totals."""
    import pandas as pd
    from stoa.solvers.vector.pdftables import Table, _pull_totals, _split_stacked
    data = [["BASEMENT", "BATH", "57 SF", "01", "Window-Casement", "7"],
            ["BASEMENT", "STORAGE", "46 SF", "02", "Window-Picture", "4"],
            ["BASEMENT: 2", "", "103 SF", "Grand total: 11", "", ""],
            ["GARAGE", "GARAGE", "486 SF", "Mark", "Family", "Count"],
            ["GARAGE", "KITCHEN", "247 SF", "01", "Door-Inswing", "1"],
            ["GARAGE", "CLOSET", "15 SF", "02", "Door-Sidelight", "2"]]
    cols = ["Level", "ROOM SCHEDULE - SIMPLIFIED Name", "Area", "Type Mark", "Family", "WINDOW SCHEDULE Count"]
    t = Table(title="", columns=cols, df=pd.DataFrame(data, columns=cols), row_boxes=[(0, i, 1, i + 1) for i in range(6)],
              bbox=(0, 0, 1, 6), run=[0], xs=[10, 20, 30, 40, 50, 60],
              cell_boxes=[[(c, i, c + 1, i + 1) for c in range(6)] for i in range(6)])
    parts = _split_stacked(t)
    for p in parts:
        _pull_totals(p)
    by_title = {p.title: p for p in parts}
    rooms, windows, doors = by_title["ROOM SCHEDULE - SIMPLIFIED"], by_title["WINDOW SCHEDULE"], by_title[""]
    assert list(rooms.df.columns) == ["Level", "Name", "Area"] and len(rooms.df) == 5
    assert [x[0] for x in rooms.totals] == ["BASEMENT: 2 | 103 SF"]
    assert list(windows.df["Count"]) == ["7", "4"] and [x[0] for x in windows.totals] == ["Grand total: 11"]
    assert list(doors.df.columns) == ["Type Mark Mark", "Family Family", "Count"] or list(doors.df["Family"]) == [
        "Door-Inswing", "Door-Sidelight"]


def test_schedule_count_sums_quantity_column():
    import pandas as pd
    from stoa.solvers.vector.schedule_solver import _qty_sum
    t = {"t1": pd.DataFrame({"row_id": [0, 1, 2], "Count": [118, 4, 4]}), "notes": pd.DataFrame({"row_id": [900000]})}
    assert _qty_sum(3, [0, 1, 2], t, "How many 2-wide window assemblies (types SS, TT and UU) are scheduled?") == 126
    assert _qty_sum(3, [0, 1, 2], t, "How many window types are scheduled?") is None
    assert _qty_sum(2, [0, 1], t, "How many doors use hardware set 18?") == 122
    assert _qty_sum(3, [0, 1], t, "How many doors?") is None  # value is not a row count


def test_tableqa_guards():
    import pandas as pd
    from stoa.solvers.vector.tableqa import _extract_code, _render, _typed_cell, _where
    t = {"t2": pd.DataFrame({"row_id": [1, 2], "Family": ["Window-Casement-A", "Window-Picture"],
                             "Size": ['14"x6"', '24"x6"']})}
    assert _typed_cell('answer = "Window-Picture"\nused = [2]', t) == "Window-Picture"
    assert _typed_cell('answer = "2 rooms, 40 SF"', t) is None
    assert "t2['Family'] (1 rows)" in _where("x = t2[t2['Size'].str.contains('Casement')]", t)
    assert _extract_code("```python\nanswer = 1") == "answer = 1"
    assert '14"x6"' in _render(t, sep="|") and '""' not in _render(t, sep="|")


def test_qparse_pctdiff_and_unused_numbers():
    from stoa.solvers.vector import qparse
    q = "By what percentage is apartment B larger than apartment A (net floor area)?"
    qr = qparse.parse(q, ["Bad"], room_numbers=set())
    assert qr.op == "pctdiff" and [t.arg for t in qr.terms] == ["B", "A"] and qr.unit == "%"
    qr = qparse.parse("What share of the floor's net area does apartment C take up, in %?", ["Bad"], room_numbers=set())
    assert qr.op == "pct"
    q = "If each door costs 450 euros, how much do the doors on this floor cost in total?"
    assert qparse.unused_numbers(q, qparse.parse(q, ["Bad"], room_numbers=set())) == ["450"]
    for q in ["What is the net floor area of room 2.05 ('Bad') in m²?", "How many rooms are larger than 20 m²?",
              "What is the total net floor area of apartment A in m2, rounded to 2 decimal places?",
              "How many rooms are labelled 'Zimmer 1'?"]:
        assert qparse.unused_numbers(q, qparse.parse(q, ["Bad", "Zimmer"], room_numbers={"2.05"})) == [], q


def test_qparse_size_wording_names_and_attributes():
    from stoa.solvers.vector import qparse
    vocab = ["Küche", "Bad", "Korridor", "Zimmer", "Séjour/repas", "Vano cantina", "Treppenhaus"]
    rn = {"3.09", "3.12", "3.45", "2.23"}
    # "size" / "floor space" without an area word is an area, not a count of Küche rooms (Q red team 9)
    qr = qparse.parse("what's the size of the küche, room 3.09?", vocab, room_numbers=rn)
    assert qr.qtype == "area" and qr.terms[0].kind == "area_room" and qr.terms[0].arg == "3.09"
    qr = qparse.parse("Give me the floor space of the Bad in apartment C.", vocab, room_numbers=rn)
    assert qr.terms[0].kind == "area_label" and qr.terms[0].scope == ["C"]
    qr = qparse.parse("Floor area of the Séjour/repas in apartment B?", vocab, room_numbers=rn)
    assert [t.arg for t in qr.terms] == ["Séjour/repas"]
    qr = qparse.parse("How many cellar compartments (Vano cantina) are there?", vocab, room_numbers=rn)
    assert qr.terms[0].kind == "count_label" and qr.terms[0].arg == "Vano cantina"
    # what the question calls a numbered room, and whether the drawing's label fits (Q red team 10)
    for q, n, asked in [("What is the net floor area of room 2.23 ('Sauna') in m²?", "2.23", "Sauna"),
                        ("What's the area of the bedroom 3.45?", "3.45", "bedroom"),
                        ("what's the size of the küche, room 3.09?", "3.09", "küche")]:
        qr = qparse.parse(q, vocab, room_numbers=rn)
        assert qparse.asked_room_names(q, qr, vocab) == {n: asked}, q
    q = "What is the net floor area of room 3.12 in m²?"
    assert qparse.asked_room_names(q, qparse.parse(q, vocab, room_numbers=rn), vocab) == {}
    assert qparse.name_fits("Küche", "kitchen") and qparse.name_fits("Wohnen/Essen", "living room")
    assert qparse.name_fits("Zimmer", "bedroom") and qparse.name_fits("Cuisine", "Küche")
    assert not qparse.name_fits("Korridor", "Sauna") and not qparse.name_fits("Treppenhaus", "bedroom")
    assert not qparse.name_fits("Bad", "Küche")
    assert qparse.ATTR_W.search("What is the fire rating of the entrance door of apartment A?")
    assert qparse.ATTR_W.search("How tall is the stair core?")
    assert not qparse.ATTR_W.search("What is the net floor area of apartment A in m²?")
    assert not qparse.ATTR_W.search("Which apartment has the larger net floor area, A or B?")


@needs_data
def test_dxf_false_premise_and_guards():
    from stoa.solvers import get_solver

    s = get_solver("dxf", llm=0)
    a = s.solve(P, "What is the net floor area of room 2.10 ('Sauna') in m²?")  # 2.10 is a Zimmer
    assert a.confidence <= 0.3 and any("labelled 'Zimmer'" in m for m in a.missing)
    a = s.solve(P, "What is the net floor area of room 2.10 ('Zimmer') in m²?")
    assert a.confidence >= 0.9
    a = s.solve(P, "What is the fire rating of the doors?")
    assert a.value is None or a.confidence <= 0.2


def test_qparse_conjunctions_and_singular_labels():
    from stoa.solvers.vector import qparse
    q = "How many toilets and sinks are there in total on this floor plan?"
    qr = qparse.parse(q, ["Bad"], room_numbers=set())
    assert [t.arg for t in qr.terms] == ["toilet", "washbasin"] and qparse.unparsed_conjunct(q, qr) is None
    q = "How many doors and elevators are there on this floor?"
    assert qparse.unparsed_conjunct(q, qparse.parse(q, ["Bad"], room_numbers=set())) == "elevators"
    for q in ["I need a quick count for a quantity takeoff: windows on this sheet?",
              "How many doors (interior doors and entrance doors together) are drawn on this floor plan?"]:
        assert qparse.unparsed_conjunct(q, qparse.parse(q, ["Bad"], room_numbers=set())) is None, q
    assert qparse.singular_label("How big is the Küche?")
    assert not qparse.singular_label("What is the total net floor area of all rooms labelled 'Küche' in m²?")
    assert not qparse.singular_label("How big are the kitchens?")


def test_qparse_yes_no_size_comparison():
    from stoa.solvers.vector import qparse
    vocab = ["Küche", "Bad"]
    qr = qparse.parse("Is apartment A bigger than apartment B?", vocab, room_numbers=set())
    assert qr.op == "yes_gt" and [t.arg for t in qr.terms] == ["A", "B"] and qparse.covered("Is apartment A bigger than apartment B?", qr)
    qr = qparse.parse("Is apartment B's kitchen bigger than apartment A's kitchen?", vocab, room_numbers=set())
    assert qr.op == "yes_gt" and [t.scope for t in qr.terms] == [["B"], ["A"]]
    qr = qparse.parse("Is the kitchen in apartment C larger than 7 m²?", vocab, room_numbers=set())
    assert qr.op == "yes_gt" and qr.threshold == 7.0
    qr = qparse.parse("Ist Wohnung F kleiner als Wohnung E?", vocab, room_numbers=set())
    assert qr.op == "yes_lt"


def test_pdftext_groups_tags_and_views(tmp_path):
    """Stacked short lines become one tag; a tag belongs to the view whose title (with a scale) is below-left of it;
    the page rotation is undone (tags on a 90-degree sheet are found in visual space)."""
    import pymupdf

    from stoa.solvers.vector.pdftext import text_groups

    for rot in (0, 90):
        doc = pymupdf.open()
        page = doc.new_page(width=800, height=600)
        lines = [(100, 100, "COMMUNITY"), (100, 111, "ROOM"), (100, 122, "115 - 410 SF"), (100, 133, "27.3 O.L."),
                 (500, 100, "FITNESS"), (500, 111, "113 - 210 SF"),
                 (60, 300, "LIFE SAFETY PLAN - BASEMENT"), (60, 313, "3/32\" = 1'-0\""),
                 (450, 300, "LIFE SAFETY PLAN - 1ST FLOOR"), (450, 313, "3/32\" = 1'-0\"")]
        page.set_rotation(rot)  # text is written so that it reads horizontally on the displayed (rotated) sheet
        for x, y, t in lines:
            page.insert_text(pymupdf.Point(x, y) * page.derotation_matrix, t, fontsize=9, rotate=rot)
        path = tmp_path / f"tags{rot}.pdf"
        doc.save(path)
        gs = {g.text: g for g in text_groups(str(path))}
        assert "COMMUNITY / ROOM / 115 - 410 SF / 27.3 O.L." in gs, list(gs)
        assert gs["COMMUNITY / ROOM / 115 - 410 SF / 27.3 O.L."].view == "LIFE SAFETY PLAN - BASEMENT"
        assert gs["FITNESS / 113 - 210 SF"].view == "LIFE SAFETY PLAN - 1ST FLOOR"
        assert sum(g.is_title for g in gs.values()) == 2


def test_pdf_text_only_for_pdfs_outside_the_dataset_sources():
    """`pdf_text` (the pipeline's route for unknown vector PDFs) reads schedules + sheet text like `schedule`, but never
    takes a dataset PDF (swiss/ifc_models have twins, opening_design goes to `schedule`)."""
    from stoa.solvers import get_solver
    s = get_solver("pdf_text")
    assert s.can_handle("/somewhere/uploads/life_safety.pdf", "Who is the architect?")
    for p in ("data/swiss_dwellings/site1_bldg2_floor3.pdf", "data/opening_design/CTR/A700.pdf",
              "data/ifc_models/x_plan-01.pdf", "/somewhere/plan.png"):
        assert not s.can_handle(p, "How many doors?"), p


def test_sheettext_feet_inch_arithmetic():
    """Aggregates over printed feet-inch lengths are computed in feet and printed back (not '7' - 10 1/4"' -> 7)."""
    from stoa.solvers.vector.sheettext import _fmt_ftin, _ftin
    assert abs(_ftin("7' - 10 1/4\"") - (7 + 10.25 / 12)) < 1e-9 and _ftin("-12' - 8\"") == -(12 + 8 / 12)
    assert _ftin("4000 PSI") is None and _ftin("3\"") is None
    assert _fmt_ftin(_ftin("22' - 5\"") - _ftin("11' - 3 1/8\"")) == "11' - 1 7/8\""


@needs_data
def test_dxf_whole_building_on_a_one_floor_plan():
    """Every swiss building in the data has one floor drawn: 'the whole building' is answered for this floor at <= 0.5,
    saying so (Q: 36 doors @0.99)."""
    from stoa.solvers import get_solver
    s = get_solver("dxf", llm=0)
    p = "data/swiss_dwellings/site1000_bldg2082_floor9385.pdf"
    a = s.solve(p, "Wie viele Türen gibt es im ganzen Gebäude?")
    assert a.value == 36 and a.confidence <= 0.5 and any("floor 9385 of building 2082" in x for x in a.assumptions)
    b = s.solve(p, "How many doors are there on this floor plan?")
    assert b.value == 36 and b.confidence > 0.9


def test_qparse_inbox_c6_wordings():
    """Cycle 6 inbox (F/Q/W4/W5 08:20-08:55): apartment letters before the noun / after 'apt.' or a hyphen,
    post-positive exclusions, m² and ft² words in DE/FR/IT, qualifier nouns, two questions in one, by-how-much
    comparatives, count ratios."""
    from stoa.solvers.vector import qparse
    P = lambda q, nums=None: qparse.parse(q, ["Küche", "Bad", "Balkon"], room_numbers=nums)  # noqa: E731
    for q in ("What is the net floor area of the D apartment?", "Net floor area of apartment-D?",
              "What is the net floor area of apt. D?", "What is the net floor area of D apartment in m²?",
              "Apartment D: what is its net floor area in m², balconies excluded?",
              "Wie viele Quadratmeter hat die Wohnung D, Balkone und Terrassen nicht mitgerechnet?",
              "Quanti metri quadrati ha l'appartamento D, terrazze escluse?",
              "Surface nette du logement D en m², hors balcons ?"):
        qr = P(q)
        assert [(t.kind, t.arg) for t in qr.terms] == [("area_apartment", "D")], (q, qr.describe())
    assert P("A flat roof: how many doors are there?").terms[0].scope is None
    qr = P("How many doors does this floor have, including the apartment entrance doors?")
    assert [(t.kind, t.arg) for t in qr.terms] == [("count", "door")]
    qr = P("Count the doors, including the entrance doors of the apartments.")
    assert [(t.kind, t.arg, t.scope) for t in qr.terms] == [("count", "door", None)]
    qr = P("How many doors are in the apartments?")
    assert [(t.kind, t.arg, t.scope) for t in qr.terms] == [("count", "door", ["*"])]
    assert P("How many apartments have a bathtub?").describe().count("count(") == 2  # a verb between: not a modifier
    assert P("Wie viele Türen und wie viele Fenster sind auf diesem Grundriss eingezeichnet?").op == "list"
    assert P("How many doors and windows are there, respectively?").op == "list"
    assert P("Wie viele Türen und Fenster gibt es insgesamt auf diesem Grundriss?").op == "sum"
    assert P("How many doors and windows are drawn on this floor plan?").op == "sum"  # ambiguous: keep the sum
    qr = P("Di quanti m² il locale 2.05 è più grande del locale 2.02?", {"2.05", "2.02"})
    assert qr.op == "diff" and qr.qtype == "area" and qr.op_sure and [t.arg for t in qr.terms] == ["2.05", "2.02"]
    assert P("Di quanto è più grande la stanza 2.27 rispetto alla 2.28?", {"2.27", "2.28"}).op == "diff"
    assert P("Di quanti locali è composto l'appartamento A?").op != "diff"
    qr = P("What is the ratio of window count to door count on this floor?")
    assert qr.op == "ratio" and [t.arg for t in qr.terms] == ["window", "door"]
    assert P("Wie groß sind die Räume 2.05 und 2.02 zusammen, in Quadratfuß?", {"2.05", "2.02"}).unit == "ft2"
    assert P("Qual è il numero totale di porte e finestre su questa pianta?").qtype == "count"


def test_dxf_price_times_count_and_outdoor_exclusion():
    from stoa.solvers.vector import qparse
    from stoa.solvers.vector.dxf_solver import _outdoor_only_exclusion, _price, _same_number
    P = lambda q: qparse.parse(q, [], room_numbers=None)  # noqa: E731
    for q, n, cur in (("If each door costs 1,200 euros, what do all the doors on this floor plan cost in total?", 1200, "EUR"),
                      ("Wenn jede Tür 1.200 Euro kostet, was kosten alle Türen auf diesem Grundriss zusammen?", 1200, "EUR"),
                      ("At 450 euros per washbasin, how much do all the washbasins on this floor cost?", 450, "EUR"),
                      ("How much do the bathtubs cost if one bathtub costs 2,000 euros?", 2000, "EUR"),
                      ("Flooring costs 45 euros per m². What does flooring apartment B cost?", 45, "EUR")):
        p = _price(q, P(q))
        assert p is not None and p[0] == n and p[1] == cur, (q, p)
    assert _price("If all doors together cost 43,200 euros, what does one door cost?", P("how many doors")) is None
    assert _same_number("1,200", 1200) and _same_number("1.200", 1200) and not _same_number("12", 1200)
    assert _outdoor_only_exclusion("What is the net floor area of apartment A in m², excluding balconies, loggias and terraces?")
    assert not _outdoor_only_exclusion("What is the area of all rooms excluding apartment A?")
