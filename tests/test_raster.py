"""raster solver (W3): question/label classification and label parsing. No model calls."""

from stoa.solvers.raster.classes import label_class, question_class, type_code
from stoa.solvers.raster.vlm import parse_labels


def test_question_classes_en_fi():
    cases = {
        "How many windows are shown on this floor plan?": "window",
        "Kuinka monta ovea pohjapiirustuksessa on? Laske oviaukot, joissa on ovi.": "door",
        "How many toilet bowls (WC seats) are drawn on this floor plan?": "wc_seat",
        "How many sinks and wash basins (kitchen and bathroom combined; a double-bowl sink counts as one) are "
        "drawn on this floor plan?": "sink",
        "Kuinka monta suihkua ja kylpyammetta pohjapiirustukseen on piirretty yhteensä?": "shower_bath",
        "How many bathrooms or washrooms (e.g. KH, KPH, PH, PESUH, SH) are on this floor plan, not counting "
        "separate WC rooms?": "bathroom",
        "Kuinka monta erillistä WC-tilaa pohjapiirustuksessa on?": "wc_room",
        "How many saunas are on this floor plan?": "sauna",
        "How many bedrooms (makuuhuone, usually marked MH) are on this floor plan?": "bedroom",
        "Kuinka monta parveketta (myös lasitetut parvekkeet) pohjapiirustuksessa on?": "balcony",
        "How many floors (storeys) does this floor plan show?": "storey",
    }
    for q, c in cases.items():
        assert question_class(q) == c, q


def test_label_classes():
    assert label_class("MH 12.0") == "bedroom"
    assert label_class("KHH") is None  # utility room, not a bathroom
    assert label_class("KPH/WC") == "bathroom"  # combined room counts once, as the bathroom
    assert label_class("WC") == "wc_room"
    assert label_class("Lasitettu parveke") == "balcony"
    assert label_class("4H+K+S") is None  # apartment type code is not a room
    assert type_code("4H+K+S") == {"rooms": 4, "classes": {"kitchen", "sauna"}}


def test_parse_labels_dedupes_and_flags_loops():
    text = ('[{"bbox_2d": [100, 100, 120, 120], "text": "MH"}, {"bbox_2d": [101, 101, 121, 121], "text": "MH"}, '
            '{"bbox_2d": [500, 500, 520, 520], "text": "MH"}]')
    items, looped = parse_labels(text, 1000, 1000)
    assert [i.text for i in items] == ["MH", "MH"] and not looped
    loop = ", ".join(f'{{"bbox_2d": [{i}, 0, {i + 5}, 5], "text": "X"}}' for i in range(0, 80, 10))
    assert parse_labels(f"[{loop}]", 1000, 1000)[1]


def test_question_op_compositions():
    from stoa.solvers.raster.classes import question_op

    assert question_op("How many doors and windows are shown on this floor plan in total?") == \
        ("sum", ["door", "window"])
    assert question_op("How many more windows than doors are shown on this floor plan?") == \
        ("diff", ["window", "door"])
    assert question_op("Does this apartment have a sauna? Answer yes or no.") == ("exists", ["sauna"])
    # dataset questions stay single-class (hints in parentheses / negations are not extra classes)
    assert question_op("How many bathrooms or washrooms (e.g. KH, KPH, PH, PESUH, SH) are on this floor plan, "
                       "not counting separate WC rooms?") == ("single", ["bathroom"])
    assert question_op("Kuinka monta kylpy- tai pesuhuonetta (esim. KH, KPH, PH, PESUH, SH) pohjapiirustuksessa "
                       "on, erillisiä WC-tiloja lukuun ottamatta?") == ("single", ["bathroom"])
    assert question_op("Hur många fönster finns på planritningen?") == ("single", ["window"])


def test_type_codes_without_plus_are_not_rooms():
    # "2HK+S" (2 rooms + kitchenette + sauna) used to be counted as a sauna ROOM
    assert label_class("2HK+S") is None and type_code("2HK+S") == {"rooms": 2, "classes": {"kitchen", "sauna"}}
    assert type_code("H+KK") == {"rooms": None, "classes": {"kitchen"}}  # digit not read
    assert type_code("H") is None and type_code("KH") is None and label_class("S") == "sauna"


def test_sink_rule_from_room_labels(monkeypatch):
    from stoa.solvers.raster import RasterSolver, vlm

    items = [vlm.Item(10, 10, "KH", "bathroom"), vlm.Item(50, 10, "WC", "wc_room"), vlm.Item(90, 10, "K", "kitchen"),
             vlm.Item(90, 90, "MH", "bedroom")]
    monkeypatch.setattr(vlm, "read_labels", lambda img, key, backend="local": (items, vlm.CallLog(), False))
    s = RasterSolver()
    a = s._rooms_rule("x.png", None, "x.png", "sink", (2, 0.57, 100), [], {"rooms_rule": 0.7})
    assert a.value == 3 and a.confidence == 0.7 and len(a.evidence) == 3  # kitchen + KH basin + WC basin
    items[:] = [vlm.Item(90, 90, "MH", "bedroom")]
    assert s._rooms_rule("x.png", None, "x.png", "sink", None, [], {}).value == 2  # assumed kitchen + 1 bathroom
