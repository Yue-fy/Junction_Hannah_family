"""stoa.kg: links + crosscheck on the esplanades demo model (train split) and one swiss floor."""

from __future__ import annotations

import pytest

from stoa.data import abspath

PLAN = "data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf"
pytestmark = pytest.mark.skipif(not abspath(PLAN).exists(), reason="dataset not available")


def test_links_plan():
    from stoa.kg import links

    L = links(PLAN)
    assert L["kind"] == "plan" and L["storey"]["name"] == "1.korrus"
    assert L["model"].endswith(".ifc")
    rooms = {r["name"]: r for r in L["rooms"]}
    r = rooms["119"]  # two KORIDOR rooms on this storey (105, 119): key by number
    assert r["bbox_pt"] and r["label"] == "KORIDOR 119"
    assert r["drawn_area_m2"] == pytest.approx(r["area_m2"], rel=0.02)  # 2D polygon (fitted scale) = 3D footprint
    doors = next(c for c in L["crosschecks"] if c["what"] == "doors")
    assert doors["model"] == doors["drawn"] == 46
    assert any(e["rel"] == "drawn_on" for e in L["graph"]["edges"])
    assert any(n["relation"] == "model this sheet was cut from" and n["kind"] == "ifc" for n in L["nodes"])
    assert {"text", "ok"} <= set(L["checks"][0])


def test_crosscheck_flags_a_wrong_count_from_any_solver():
    from stoa.kg import crosscheck

    ok = crosscheck(PLAN, {"task": "count", "target": "door", "scope": "drawing"}, {"value": 46})
    bad = crosscheck(PLAN, {"task": "count", "target": "door", "scope": "drawing"}, {"value": 41})
    assert "✓" in ok and "✗" not in ok
    assert "✗" in bad


def test_crosscheck_room_area_by_name():
    from stoa.kg import crosscheck

    note = crosscheck(PLAN, {"task": "area", "target": "room", "filters": {"storey": "1.korrus", "room": "KORIDOR (119)"}},
                      {"value": 63.84})
    assert note and "✗" not in note and "polygon on the plan" in note


def test_cut_plane_checks_explain_undrawn_elements():
    """Barlad: Revit lintel 'walls' above the 1.2 m cut are in the storey but not drawn; the CTA sheet draws the
    Ground Level elements its cut plane crosses. Neither is a disagreement."""
    from stoa.kg import links

    base = "data/ifc_models/bimspeed-barlad_ro-arc-m3-e-pth-0000_plan-0"
    if not abspath(base + "2-ground-level.pdf").exists():
        pytest.skip("barlad not available")
    gl = {c["text"].split(":")[0]: c for c in links(base + "2-ground-level.pdf")["checks"]}
    assert gl["walls on 'Ground Level'"]["ok"] is True and "345 cut by the plan plane" in gl["walls on 'Ground Level'"]["text"]
    cta = links(base + "1-cta.pdf")["checks"]
    assert cta and all(c["ok"] is None for c in cta)


SWISS = "data/swiss_dwellings/site851_bldg1805_floor9278.pdf"


@pytest.mark.skipif(not abspath(SWISS).exists(), reason="swiss floor not available")
def test_swiss_totals_are_compared_with_totals_not_one_room():
    from stoa.kg import crosscheck
    from stoa.router.intent import parse

    q = "What is the total net floor area in m² of all numbered indoor rooms on this floor?"
    ev = [{"file": SWISS, "page": 0, "bbox": [100, 100, 140, 140]}]
    note = crosscheck(SWISS, parse(q), {"value": 165.63, "evidence": ev})
    assert note and "polygon of room" not in note and "numbered indoor rooms" in note
    assert "sum of their printed areas 165.64 m² ✓" in note
    apt = crosscheck(SWISS, {"task": "area", "target": "apartment", "scope": "apartment", "filters": {"apartment": "Z"}},
                     {"value": 50.0, "evidence": ev})
    assert apt is None  # unknown apartment: no comparison rather than a false ✗


def test_swiss_total_unnamed_rooms_are_not_a_check():
    """W2 10:25: unnamed numbered rooms (>= 2% of the total) make the polygon sum a reading choice: '?', never ✓."""
    from stoa.kg.graph import _swiss_total_check

    rooms = [{"number": "1.01", "name": "Bain", "apartment": "B", "area_m2_dxf": 50.0, "area_m2_printed": 50.0},
             {"number": "1.02", "name": "Séjour", "apartment": "B", "area_m2_dxf": 47.0, "area_m2_printed": 47.0},
             {"number": "1.03", "name": "", "apartment": "B", "area_m2_dxf": 3.0}]
    note = _swiss_total_check(100.0, "apartment", {"apartment": "B"}, rooms)
    assert "✓" not in note and "reading choice" in note
    assert "✗" in _swiss_total_check(120.0, "apartment", {"apartment": "B"}, rooms)
    rooms[2]["name"] = "Réduit"  # all named -> the sums are a check again
    assert "✓" in _swiss_total_check(100.0, "apartment", {"apartment": "B"}, rooms)
