"""W4: intent parser, routing, pipeline never refuses, API path safety."""

import pytest

from stoa.router.intent import parse


@pytest.mark.parametrize("q,key,filters", [
    ("How many windows are shown on this floor plan?", "count:window:drawing", {}),
    ("Kuinka monta ikkunaa pohjapiirustuksessa on?", "count:window:drawing", {}),
    ("Wie viele Fenster sind auf diesem Grundriss eingezeichnet?", "count:window:drawing", {}),
    ("How many bathrooms or washrooms (e.g. KH, KPH, PH, PESUH, SH) are on this floor plan, not counting separate WC rooms?",
     "count:bathroom:drawing", {}),
    ("Kuinka monta kylpy- tai pesuhuonetta (esim. KH, KPH, PH, PESUH, SH) pohjapiirustuksessa on, erillisiä WC-tiloja lukuun ottamatta?",
     "count:bathroom:drawing", {}),
    ("How many separate WC rooms (toilet rooms marked WC) are on this floor plan?", "count:wc_room:drawing", {}),
    ("How many rooms labelled 'Cage d'escalier' are there on this floor?", "count:room:label", {"label": "Cage d'escalier"}),
    ("What is the net floor area of room 7.01 ('Balkon') in m²?", "area:room:room", {"room_no": "7.01"}),
    ("Wie gross ist die Nettowohnfläche von Wohnung B in m² (Summe aller Räume ohne Balkone, Loggien, Terrassen und andere Aussenräume)?",
     "area:apartment:apartment", {"apartment": "B"}),
    ("What is the total net floor area in m² of all numbered indoor rooms on this floor (excluding balconies, loggias, terraces and other outdoor spaces, shafts and voids)?",
     "area:room:floor_total", {}),
    ("How many doors are shown on the floor plan of 'Level 1'?", "count:door:storey", {"storey": "Level 1"}),
    ("Wie viele Fenster enthält das Modell „FZK-Haus“?", "count:window:model", {"model": "FZK-Haus"}),
    ("What is the total net volume of all walls on 'Grundplan', in m³?", "volume:wall:storey_total", {"storey": "Grundplan"}),
])
def test_parse(q, key, filters):
    it = parse(q)
    assert it.key == key
    for k, v in filters.items():
        assert it.filters.get(k) == v


def test_route_orders_deterministic_first():
    from stoa.pipeline import route

    r = route("data/swiss_dwellings/site1000_bldg2082_floor9385.pdf")
    assert r.index("dxf") < r.index("vlm_direct")
    assert route("data/cubicasa5k/colorful-10052.png")[0] == "raster"


def test_prior_never_refuses():
    from stoa.pipeline import Pipeline

    p = Pipeline(use_gate=0, max_tries=0)  # no solver tried -> prior
    a = p.solve("data/cubicasa5k/colorful-10052.png", "How many kitchens are on this floor plan?")
    assert a.value is not None and a.assumptions and a.missing and 0 < a.confidence < 1


def test_api_rejects_escape():
    from fastapi.testclient import TestClient

    from stoa.api import app

    c = TestClient(app)
    assert c.get("/file", params={"path": "../etc/passwd"}).status_code == 400
    assert c.get("/file", params={"path": "data/nope.png"}).status_code == 404


@pytest.mark.parametrize("src,q,op,labels", [
    ("cubicasa5k", "How many doors and windows are shown on this floor plan in total?", "sum", ["door", "window"]),
    ("cubicasa5k", "How many more windows than doors are shown on this floor plan?", "diff", ["window", "door"]),
    ("cubicasa5k", "Does this apartment have a sauna? Answer yes or no.", "exists", ["sauna"]),
    ("swiss_dwellings", "How many toilets, washbasins, bathtubs and showers are drawn on this floor plan altogether?", "sum",
     ["wc", "washbasin", "shower", "bathtub"]),
    ("swiss_dwellings", "By how many m² is room 1.06 larger than room 1.04 (net floor area)?", "diff", ["room 1.06", "room 1.04"]),
    ("ifc_models", "Which of the rooms 'A (1)', 'B (2)' and 'C (3)' on 'Level 1' has the largest net floor area?", "argmax",
     ["A (1)", "B (2)", "C (3)"]),
])
def test_decompose(src, q, op, labels):
    from stoa.router.compose import combine, decompose

    p = decompose(src, q)
    assert p is not None and p.op == op and p.labels == labels
    if op == "sum":
        assert combine(p, [2] * len(labels))[0] == 2 * len(labels)


def test_atomic_questions_not_decomposed():
    from stoa.router.compose import decompose

    q = ("How many sinks and wash basins (kitchen and bathroom combined; a double-bowl sink counts as one) "
         "are drawn on this floor plan?")
    assert decompose("cubicasa5k", q) is None
