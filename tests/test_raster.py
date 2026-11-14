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


def test_cond_prior_uses_room_counts(monkeypatch):
    import json
    from stoa.solvers.raster import COND_FILE, RasterSolver, vlm

    spec = json.loads(COND_FILE.read_text())["door"]
    items = [vlm.Item(10, 10, "MH", "bedroom"), vlm.Item(50, 10, "MH", "bedroom"), vlm.Item(90, 10, "S", "sauna")]
    monkeypatch.setattr(vlm, "read_labels", lambda img, key, backend="local": (items, vlm.CallLog(), False))
    a = RasterSolver()._cond_prior("x.png", None, "x.png", "door", (7.0, 0.13, 100), [], {})
    cell = spec["table"]["2,0,1"]
    assert a.value == cell["mode"] and 0 < a.confidence <= 0.9 and len(a.evidence) == 3
    assert a.assumptions and "statistical estimate" in a.assumptions[0]


def test_tiled_labels_merge_overlap_and_charge_cost(monkeypatch):
    from PIL import Image
    from stoa import llm
    from stoa.contract import CostMeter
    from stoa.solvers.raster import vlm

    # every tile sees one "MH" in its own centre and one "S" at its top-left; neighbours overlap
    def fake_chat(prompt, images=None, **kw):  # like llm.chat, bills itself to the caller's meter (llm._charge)
        return llm._charge(llm.ChatResult(text='[{"bbox_2d": [480, 480, 520, 520], "text": "MH"}, '
                                               '{"bbox_2d": [0, 0, 20, 20], "text": "S"}]',
                                          prompt_tokens=100, completion_tokens=20, latency_s=0.1, backend="local"))
    monkeypatch.setattr(vlm.llm, "chat", fake_chat)
    with CostMeter() as m:
        items, log = vlm.read_labels_tiled(Image.new("RGB", (1000, 800), "white"))
    assert sum(i.text == "MH" for i in items) == 4  # 4 distinct tile centres
    # cost reaches the caller's meter from the threads, once per call (raster no longer bills on top of llm.chat)
    assert log.tokens_in == 400 and m.cost.llm_calls == 4 and m.cost.llm_tokens_in == 400


def test_tk_is_a_vestibule_not_a_kitchen():
    assert label_class("TK") is None and label_class("K") == "kitchen" and label_class("TUPAKEITTIÖ") == "kitchen"


def test_textlayer_parsers_and_merge():
    from stoa.solvers.raster import textlayer as T

    assert T.parse_scales('SCALE: 1/4" = 1\'-0"')[0]["ratio"] == 48
    assert T.parse_scales("MITTAKAAVA 1:50")[0]["ratio"] == 50
    assert T.parse_scales("SCALE: 1:125,000")[0]["ratio"] == 125000
    assert T.parse_scales("drawn 12:30") == []
    # Qwen bbox_2d JSON (0..1000) -> pixels of a 2000x1000 tile; loops (> 6 repeats) dropped
    items = T.parse_items('[{"bbox_2d": [100, 100, 200, 150], "text": "SAUNA"}, '
                          '{"bbox_2d": [500, 500, 600, 550], "text": "12\'-6\\""}]', 2000, 1000)
    assert [i.text for i in items] == ["SAUNA", "12'-6\""] and items[0].box == [200, 100, 400, 150]
    # a text read twice in a tile overlap (once cut) is kept once, the longer reading wins
    a = T.TextItem("HISTORIC AMERICAN BUILDINGS SURVEY", [100, 100, 500, 120])
    b = T.TextItem("BUILDINGS SURVEY", [300, 101, 500, 119])
    assert [i.text for i in T.merge_items([b, a])] == ["HISTORIC AMERICAN BUILDINGS SURVEY"]
    tl = T.TextLayer("x.png", (1000, 1000), [a, T.TextItem("LIVING 14'-6\" x 12'", [0, 0, 10, 10]),
                                            T.TextItem("Olohuone 21,5 m2", [0, 0, 10, 10])])
    assert [d["feet"] for d in T.dimensions(tl)] == [14.5, 12]
    assert T.areas(tl)[0]["value"] == 21.5
    assert T.find_text("x.png", "buildings survey", layer=tl)[0]["score"] == 1.0
    assert T.match_score("SAUNA", "SAUNNA") >= 0.8 and T.match_score("kitchen", "SAUNA") < 0.5
    # tiles cover the image, 1x1 for small images
    assert T.tile_boxes(768, 695) == [(0, 0, 768, 695)]
    bx = T.tile_boxes(3000, 2000)
    assert len(bx) == 6 and bx[-1][2] == 3000 and bx[-1][3] == 2000


def test_off_domain_symbol_counts_abstain_and_scans_go_to_text_mode():
    from stoa.solvers.raster import RasterSolver

    s = RasterSolver()
    a = s._off_domain("data/swiss_dwellings/x.png", "window", [])
    assert a.value is None and "detector" in a.missing[0]  # no Finnish prior on a Swiss/scan drawing
    assert s._text_mode("data/habs/x_sheet_00001.jpg", "What is the scale of this drawing?")
    assert not s._text_mode("data/cubicasa5k/x.png", "What is the scale of this drawing?")
    assert not RasterSolver(text=0)._text_mode("data/habs/x.jpg", "What is the scale of this drawing?")


def _bar_image(tmp_path, x0=100, x1=500, y=60, stepped=False):
    """A white image with a drawn scale bar from x0 to x1 (a 6 px thick black band, or a HABS-style stepped bar)."""
    import numpy as np
    from PIL import Image

    a = np.full((140, 700), 255, np.uint8)
    if stepped:
        seg = (x1 - x0) // 4
        for k in range(4):
            yy = y if k % 2 == 0 else y + 8
            a[yy:yy + 4, x0 + k * seg:x0 + (k + 1) * seg + 1] = 0
            a[y:y + 12, x0 + k * seg:x0 + k * seg + 2] = 0
        a[y:y + 12, x1 - 1:x1 + 1] = 0
    else:
        a[y:y + 6, x0:x1] = 0
    a[120:122, :] = 0  # a frame line running through both margins must not be taken as the bar
    p = tmp_path / "bar.png"
    Image.fromarray(a).save(p)
    return str(p)


def test_scalebar_labels_fit_and_snap_to_the_drawn_bar(tmp_path):
    from stoa.solvers.raster import scalebar as S
    from stoa.solvers.raster.textlayer import TextItem

    assert S.unit_of("FEET") == "ft" and S.unit_of("Meter.") == "m" and S.unit_of("METERS 1:48") == "m"
    assert S.unit_of("100'") == "ft" and S.unit_of("SCALE B") is None
    for stepped in (False, True):
        path = _bar_image(tmp_path, stepped=stepped)
        # VLM label boxes: evenly spaced guesses that put '20' at x 470 although the bar ends at 500 (10% short)
        items = [TextItem(str(v), [x - 6, 40, x + 6, 54]) for v, x in [(0, 100), (5, 192), (10, 285), (15, 377),
                                                                       (20, 470)]]
        items.append(TextItem("FEET", [30, 58, 80, 70]))
        bars = S._bars_from_items(items, items, "layer")
        assert len(bars) == 1 and bars[0].unit == "ft" and abs(bars[0].px_per_unit - 18.5) < 0.2
        b = S.snap(path, bars[0])
        assert "+drawn" in b.source and abs(b.px_per_unit - 20.0) < 0.15, (stepped, b.notes)
        assert abs(S.to_units(200, b) - 10.0) < 0.1 and abs(S.meters(200, b) - 3.048) < 0.03


def test_scalebar_rejects_rows_that_are_not_bars():
    from stoa.solvers.raster import scalebar as S
    from stoa.solvers.raster.textlayer import TextItem

    # room numbers in a row (no 0, no linear spacing) and a single number are not bars
    items = [TextItem(str(v), [x, 40, x + 20, 54]) for v, x in [(101, 100), (102, 300), (104, 350)]]
    items += [TextItem("FEET", [10, 40, 50, 54])]
    assert S._bars_from_items(items, items, "layer") == []
    items = [TextItem(str(v), [x, 40, x + 12, 54]) for v, x in [(0, 100), (10, 200), (20, 420)]]
    assert S._bars_from_items(items, items, "layer") == []  # not linear
    # a FEET and a METERS bar with the units swapped by proximity: the px ratio 3.28 fixes them
    ft = S.Bar("m", 15.65, [(0, 0, [0, 0, 1, 1]), (20, 313, [0, 0, 1, 1])], [0, 0, 313, 12], 0.5, "layer")
    m = S.Bar("ft", 51.35, [(0, 0, [0, 30, 1, 31]), (5, 257, [0, 30, 1, 31])], [0, 30, 257, 42], 0.5, "layer")
    S._resolve_ft_m([ft, m])
    assert (ft.unit, m.unit) == ("ft", "m") and S.consistency([ft, m])[0].endswith("✓")


def test_room_area_flood_fill_keeps_corner_fixtures_and_finds_the_label(tmp_path):
    import numpy as np
    from PIL import Image

    from stoa.solvers.raster import measure as M
    from stoa.solvers.raster.textlayer import TextItem, TextLayer

    a = np.full((200, 300), 255, np.uint8)
    a[20:160, 20:220] = 0
    a[26:154, 26:214] = 255  # one room, interior 188 x 128 px, 6 px walls
    a[26:48, 50:52] = 0  # a shower tray in the corner, drawn with thin lines
    a[46:48, 26:52] = 0
    a[80:88, 100:101] = a[80:88, 110:111] = a[84:85, 100:124] = 0  # the label's own thin strokes
    a[40:120, 230:232] = 0  # a stray line outside
    p = tmp_path / "room.png"
    Image.fromarray(a).save(p)
    full = 188 * 128 / 40 ** 2  # 15.04 m2 at 40 px per m (6 px walls = 0.15 m; 2 px fixture lines = 5 cm)
    r = M.room_area(str(p), [100, 80, 124, 88], 40.0, **M.FILL)
    plain = M.room_area(str(p), [100, 80, 124, 88], 40.0, door_m=0.0)
    assert r and abs(r["m2"] / full - 1) < 0.04, r
    assert plain["m2"] < r["m2"]  # without the hull the bathtub corner is lost
    tl = TextLayer(path=str(p), size=(300, 200), items=[TextItem("1.01", [100, 80, 124, 88]),
                                                         TextItem("Bad", [100, 90, 124, 98])])
    assert M.find_label(tl, "What is the net floor area of room 1.01 ('Bad') in m²?").text == "1.01"
    assert M.find_label(tl, "Wie gross ist der Raum «Bad»?").text == "Bad"
    assert M.find_label(tl, "What is the area of room 2.02?") is None


def test_swiss_png_without_twin_goes_to_text_mode(monkeypatch):
    import stoa.solvers.raster as R

    q = "What is the net floor area of room 1.19 ('Corridoio') in m²?"
    monkeypatch.setattr(R, "_siblings", lambda p: {".png": p, ".pdf": p[:-4] + ".pdf", ".dxf": p[:-4] + ".dxf"})
    assert not R.RasterSolver()._text_mode("data/swiss_dwellings/x.png", q)  # dxf answers it
    assert R.RasterSolver(twins=0)._text_mode("data/swiss_dwellings/x.png", q)
    monkeypatch.setattr(R, "_siblings", lambda p: {".png": p})
    assert R.RasterSolver()._text_mode("data/swiss_dwellings/x.png", q)
    assert not R.RasterSolver()._text_mode("data/cubicasa5k/x.png", q)
