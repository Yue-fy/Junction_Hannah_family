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
    assert any(e["rel"] == "drawn_on" for e in L["edges"])


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
