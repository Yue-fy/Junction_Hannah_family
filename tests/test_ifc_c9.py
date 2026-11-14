"""Cycle-9 fix: an unquoted room LongName that exactly one IfcSpace of the model carries is resolved as that room
('How big is the INVA-WC?' summed all 13 toilets of the storey @ 0.85; gold = the one room, 5.96 m²). Probe:
experiments/w1/probes/c9_natural.txt; expected values = the dataset-template wording "What is the area of 'X (code)'?"."""

from __future__ import annotations

import pytest

from stoa.data import abspath
from stoa.solvers.ifc.index import load_index
from stoa.solvers.ifc.solver import IfcSolver, quote_room_refs

ESPL = "data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf"
SMW = "data/ifc_models/kit-smiley-west_ac-20-smiley-west-10-bldg_plan-01-kg.pdf"
need = pytest.mark.skipif(not abspath(ESPL).exists(), reason="dataset not available")


@need
@pytest.mark.parametrize("path,q,want", [
    (ESPL, "How big is the INVA-WC?", 5.96),
    (SMW, "How big is Kellerraum-05-2?", 4.582),
])
def test_unquoted_unique_longname(path, q, want):
    a = IfcSolver().solve(path, q)
    assert a.value == pytest.approx(want, rel=0.01)
    assert a.confidence >= 0.8


@need
def test_longname_quoting_is_narrow():
    idx = load_index(str(abspath("data/ifc_models/bsc-esplanades_1807-ep-ar-v18.ifc")))
    assert quote_room_refs(idx, "How big is the INVA-WC?") == "How big is the 'INVA-WC'?"
    # shared type words, storey names and already quoted questions are left alone
    for q in ("How many ESIK rooms are on this floor?", "How many doors are on 2.korrus?",
              "What is the area of 'INVA-WC (103)'?", "How many toilets on this floor?"):
        assert quote_room_refs(idx, q) == q
