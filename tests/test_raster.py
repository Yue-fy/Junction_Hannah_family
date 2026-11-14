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
    # Finnish/Swedish slash form (W5 04:31): a scale only next to a scale word or with a standard denominator
    assert T.parse_scales("ASEMAPIIRROS M.K. 1/500")[0]["ratio"] == 500
    assert T.parse_scales("POHJA 1/100")[0]["ratio"] == 100
    assert T.parse_scales("Skala 1/75")[0]["ratio"] == 75
    assert T.parse_scales("1/16") == [] and T.parse_scales("3/4 1/2") == []
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
    assert s._text_mode("data/cubicasa5k/x.png", "What is the scale of this drawing?")  # non-count: text mode (W3 c5)
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
    assert R.RasterSolver()._text_mode("data/cubicasa5k/x.png", q)  # non-count questions on CubiCasa: text mode


def test_sheet_kind_titles_and_room_questions():
    """sheet.py (Q 05:04): view titles from a text layer; only count/size questions about rooms need a floor plan."""
    from stoa.solvers.raster import sheet as S
    from stoa.solvers.raster.textlayer import TextItem, TextLayer

    tl = TextLayer(path="x.jpg", size=(1000, 800), items=[
        TextItem("NORTH ELEVATION", [100, 700, 300, 730]), TextItem("PLAN OF PINTLE", [500, 100, 600, 110]),
        TextItem("SEE THE FLOOR PLAN ON SHEET 3 FOR ALL ROOM NAMES AND DOORS", [10, 10, 400, 20])])
    kinds = [(h["kind"], h["title"]) for h in S.title_kinds(tl)]
    assert kinds[0] == ("elevation", True)  # biggest short title first
    assert ("floor_plan", False) in kinds  # the long note is not a title
    assert all(k != "floor_plan" for k, t in kinds if t)  # 'PLAN OF PINTLE' is a detail view, not a floor plan
    k = S.sheet_kind("x.jpg", use_vlm=False, layer=tl)
    assert k["has_plan"] is None  # a 'plan' word is present -> the text rule does not decide
    tl.items = tl.items[:1]
    assert S.sheet_kind("x.jpg", use_vlm=False, layer=tl)["has_plan"] is False
    tl.items.append(TextItem("POHJA 1/100", [100, 100, 200, 120]))
    assert S.sheet_kind("x.jpg", use_vlm=False, layer=tl)["has_plan"] is True
    assert S.needs_plan("How many bedrooms are shown on this floor plan?")
    assert S.needs_plan("Montako makuuhuonetta asunnossa on?") and S.needs_plan("Wie viele Zimmer hat die Wohnung?")
    assert not S.needs_plan("How many windows are on the north elevation?")
    assert not S.needs_plan("What is the name of the hall?")
    assert S.veto("data/cubicasa5k/x.png", "How many bedrooms?") is None  # CubiCasa sheets are plans


def test_apartment_net_area_sums_printed_rooms_inside_the_unit_boundary(tmp_path):
    """apartment.py (Q 05:16): two units split by a red dash-dot boundary; the asked unit's rooms are summed, the
    other unit's and outdoor rooms are not; an unknown-unit scale bar resolves to metres from '1:200 (A3)'."""
    import numpy as np
    from PIL import Image

    from stoa.solvers.raster import apartment as A
    from stoa.solvers.raster import scalebar as SB
    from stoa.solvers.raster.textlayer import TextItem, TextLayer

    img = np.full((400, 600, 3), 255, np.uint8)
    red = (176, 58, 46)

    def dashed(x0, y0, x1, y1):  # dash 10 px, gap 4 px
        n = max(abs(x1 - x0), abs(y1 - y0))
        for t in range(n + 1):
            if t % 14 < 10:
                x, y = x0 + (x1 - x0) * t // n, y0 + (y1 - y0) * t // n
                img[y - 1:y + 2, x - 1:x + 2] = red
    for (a, b) in [((50, 50), (550, 50)), ((550, 50), (550, 350)), ((550, 350), (50, 350)), ((50, 350), (50, 50)),
                   ((300, 50), (300, 350))]:
        dashed(*a, *b)
    p = tmp_path / "plan.png"
    Image.fromarray(img).save(p)
    tl = TextLayer(path=str(p), size=(600, 400), items=[
        TextItem("Whg. A", [100, 70, 150, 85]), TextItem("Whg. B", [350, 70, 400, 85]),
        TextItem("Zimmer", [100, 120, 150, 132]), TextItem("1.01", [110, 134, 140, 146]),
        TextItem("15.50 m²", [100, 148, 150, 160]),
        TextItem("Küche", [100, 220, 150, 232]), TextItem("1.02", [110, 234, 140, 246]),
        TextItem("8.25 m²", [100, 248, 150, 260]),
        TextItem("Balkon", [200, 220, 250, 232]), TextItem("1.03", [210, 234, 240, 246]),
        TextItem("6.00 m²", [200, 248, 250, 260]),
        TextItem("Zimmer", [400, 120, 450, 132]), TextItem("1.04", [410, 134, 440, 146]),
        TextItem("20.00 m²", [400, 148, 450, 160])])
    q = "What is the net floor area of apartment A in m², summing all its rooms except balconies and terraces?"
    assert A.unit_letter(q) == "A" and A.unit_letter("Wie gross ist die Nettowohnfläche von Wohnung B?") == "B"
    assert A.unit_letter("Quelle est la surface nette de l'appartement C en m² ?") == "C"
    assert set(A.unit_labels(tl)) == {"A", "B"}
    r = A.net_area(str(p), tl, q, px_per_m=30.0)
    assert r is not None and r["value"] == 23.75 and [d["id"] for d in r["dropped"]] == ["1.03"]
    assert A.net_area(str(p), tl, q.replace("apartment A", "apartment B"), px_per_m=30.0)["value"] == 20.0
    assert A.net_area(str(p), tl, q.replace("apartment A", "apartment C"), px_per_m=30.0) is None
    assert A.unit_letter("Is this apartment a duplex?") is None  # the letter must be a capital
    lab = A.room_set(str(p), tl, "What is the total net area in m² of all rooms labelled 'Zimmer' on this floor?", 30.0)
    assert lab["scope"] == "floor" and lab["value"] == 35.5
    floor = A.room_set(str(p), tl, "What is the total net floor area in m² of all numbered indoor rooms on this floor "
                                   "(excluding balconies, loggias, terraces and other outdoor spaces, shafts and voids)?",
                       30.0)
    assert floor["value"] == 43.75 and [d["id"] for d in floor["dropped"]] == ["1.03"]
    assert A.room_set(str(p), tl, "What is the area of the kitchen?", 30.0) is None  # not a summed-area question
    # unknown-unit bar: '1:200 (A3)' on a 2480-px sheet = 29.52 px/m
    bar = SB.Bar(unit=None, px_per_unit=29.6, labels=[(0, 0, [0, 0, 1, 1]), (10, 296, [0, 0, 1, 1])],
                 box=[0, 0, 296, 10], residual=1.0, source="layer")
    SB._resolve_unknown([bar], TextLayer(path="x.png", size=(2480, 1753), items=[TextItem("1:200 (A3)", [0, 0, 9, 9])]))
    assert bar.unit == "m"


def test_cubicasa_non_count_questions_go_to_text_mode(monkeypatch):
    """An unseen non-count question on a CubiCasa plan ('area of the living room', printed 'OH 22.8') is read from
    the text layer; count questions stay with the counting methods."""
    import stoa.solvers.raster as R

    s = R.RasterSolver()
    assert s._text_mode("data/cubicasa5k/x.png", "What is the area of the living room (OH) in m²?")
    assert not s._text_mode("data/cubicasa5k/x.png", "How many rooms have a window?")
    assert not s._text_mode("data/cubicasa5k/x.png", "Kuinka monta makuuhuonetta on?")


def test_label_count_in_a_unit_is_scoped_to_its_boundary(monkeypatch, tmp_path):
    """'How many rooms labelled X in apartment B' counts inside B's drawn boundary; a unit the plan does not name is a
    false premise (low confidence, said in `missing`)."""
    import numpy as np
    from PIL import Image

    import stoa.solvers.raster as R
    from stoa.solvers.raster import textlayer as T
    from stoa.solvers.raster.textlayer import TextItem, TextLayer

    img = np.full((200, 400, 3), 255, np.uint8)
    img[20:23, 20:380] = img[177:180, 20:380] = (176, 58, 46)
    img[20:180, 20:23] = img[20:180, 377:380] = img[20:180, 199:202] = (176, 58, 46)
    p = tmp_path / "u.png"
    Image.fromarray(img).save(p)
    tl = TextLayer(path=str(p), size=(400, 200), items=[
        TextItem("Whg. A", [40, 30, 90, 42]), TextItem("Whg. B", [240, 30, 290, 42]),
        TextItem("Bad", [50, 100, 70, 110]), TextItem("Bad", [250, 100, 270, 110]), TextItem("Bad", [300, 140, 320, 150])])
    monkeypatch.setattr(T, "text_layer", lambda *a, **k: tl)
    s = R.RasterSolver()
    a = s._text_count(str(p), None, "Bad", [], "How many rooms labelled 'Bad' are there in apartment B?")
    assert a.value == 2 and a.confidence == 0.85
    a = s._text_count(str(p), None, "Bad", [], "How many rooms labelled 'Bad' are there in apartment E?")
    assert a.value == 3 and a.confidence <= 0.1 and "no apartment E" in a.missing[0]
    assert s._text_count(str(p), None, "Bad", [], "How many rooms labelled 'Bad' are on this floor?").value == 3


def test_compared_units_parsing():
    from stoa.solvers.raster import apartment as A
    from stoa.solvers.raster.textlayer import TextItem, TextLayer

    tl = TextLayer(path="x.png", size=(100, 100), items=[TextItem(f"Whg. {L}", [0, 0, 1, 1]) for L in "ABCD"])
    assert A.compared_units("Which apartment on this floor has the largest net floor area?", tl) == (list("ABCD"), "max")
    assert A.compared_units("Is apartment A larger than apartment B?", tl) == (["A", "B"], "max")
    assert A.compared_units("Which is smaller, apartment C or D?", tl) == (["C", "D"], "min")
    assert A.compared_units("Welche Wohnung ist die grösste?", tl) == (list("ABCD"), "max")
    assert A.compared_units("What is the net floor area of apartment B in m²?", tl) is None
    assert A.compared_units("Is apartment B the largest?", tl) is None  # one unit named: not handled as a comparison


def test_doorarcs_quarter_arc_not_circle(tmp_path):
    """One drawn quarter arc (r 0.9 m at 59 px/m) is a door; a full circle (north arrow, round fixture) is not."""
    from PIL import Image, ImageDraw

    from stoa.solvers.raster import doorarcs as DA

    im = Image.new("L", (600, 400), 255)
    d = ImageDraw.Draw(im)
    r = 0.9 * 59
    d.arc([150 - r, 200 - r, 150 + r, 200 + r], 270, 360, fill=0, width=2)  # hinge (150, 200), swing up-right
    d.line([150, 200, 150 + r, 200], fill=0, width=2)  # the leaf
    d.ellipse([420 - r, 200 - r, 420 + r, 200 + r], outline=0, width=2)  # a full circle
    p = tmp_path / "plan.png"
    im.save(p)
    dets = DA.detect(str(p), 59.0)
    assert len(dets) == 1
    assert abs(dets[0]["c"][0] - 150) < 6 and abs(dets[0]["c"][1] - 200) < 6
    assert abs(dets[0]["r_m"] - 0.9) < 0.06


def test_text_layer_cache_key_is_per_content_for_uploads(tmp_path, monkeypatch):
    """Uploads are all saved as <dir>/<sha>/plan.png: two different uploads must not share a text-layer cache entry,
    while a dataset file keeps its name-only key (existing caches stay valid)."""
    from PIL import Image

    from stoa.solvers.raster import textlayer as T

    data = tmp_path / "data_root"
    (data / "data" / "swiss_dwellings").mkdir(parents=True)
    monkeypatch.setenv("STOA_DATA", str(data))
    a, b = tmp_path / "up" / "aa" / "plan.png", tmp_path / "up" / "bb" / "plan.png"
    for p, c in ((a, 0), (b, 255)):
        p.parent.mkdir(parents=True)
        Image.new("RGB", (8, 8), (c, c, c)).save(p)
    assert T.file_tag(str(a)) and T.file_tag(str(a)) != T.file_tag(str(b))
    assert T._disk_key(str(a), 1100, "local") != T._disk_key(str(b), 1100, "local")
    ds = data / "data" / "swiss_dwellings" / "site1_bldg1_floor1.png"
    Image.new("RGB", (8, 8)).save(ds)
    assert T.file_tag("data/swiss_dwellings/site1_bldg1_floor1.png") == ""


def test_window_symbols_four_line_wall_stretch(tmp_path):
    """A wall stretch drawn as 2 dark faces + 2 grey glass lines, split by a mullion = 2 windows; hatched wall = 0."""
    import numpy as np
    from PIL import Image

    from stoa.solvers.raster import windows as WS

    g = np.full((300, 400), 255, np.uint8)
    for x0, x1 in ((50, 120), (124, 194)):  # two windows side by side, mullion at 120..124
        g[100, x0:x1] = 0
        g[142, x0:x1] = 0
        g[114, x0:x1] = 59
        g[128, x0:x1] = 59
    g[100:143, 120:124] = 0
    g[200:243, 50:200] = 170  # a filled (hatched) wall: not a window
    p = tmp_path / "w.png"
    Image.fromarray(g).save(p)
    dets = WS.detect(str(p), 59.0)
    assert len(dets) == 2 and all(d["dir"] == "h" for d in dets)
    assert dets[0]["box"][1] == 100 and dets[0]["box"][3] == 143


def test_window_symbols_none_found_abstains(tmp_path, monkeypatch):
    """No 4-line symbol on a drawing with a metric bar = another convention: abstain, never '0 windows'."""
    import numpy as np
    from PIL import Image

    from stoa.solvers.raster import RasterSolver
    from stoa.solvers.raster import scalebar as SB
    from stoa.solvers.raster import textlayer as T

    p = tmp_path / "plan.png"
    g = np.full((200, 300), 255, np.uint8)
    g[40:44, 30:270] = 0  # a plain wall, no window symbol
    Image.fromarray(g).save(p)
    bar = SB.Bar(unit="m", px_per_unit=59.0, labels=[], box=[0, 0, 10, 10], residual=0.0, source="t")
    monkeypatch.setattr(T, "text_layer", lambda *a, **k: None)
    monkeypatch.setattr(SB, "bars", lambda *a, **k: [bar])
    s = RasterSolver()
    trace: list[str] = []
    assert s._window_symbols(str(p), trace) is None
    assert any("none of the known" in t for t in trace)


def test_clean_render_gate(tmp_path):
    """A flat render passes; a noisy 'scan' (paper texture, many grey levels) does not."""
    import numpy as np
    from PIL import Image

    from stoa.solvers.raster import windows as WS

    g = np.full((200, 200), 255, np.uint8)
    g[50:52, 20:180] = 0
    g[100, 20:180] = 59
    Image.fromarray(g).save(tmp_path / "r.png")
    assert WS.clean_render(str(tmp_path / "r.png"))[0]
    rng = np.random.default_rng(0)
    s = np.clip(225 + rng.normal(0, 12, (200, 200)), 0, 255).astype(np.uint8)
    Image.fromarray(s).save(tmp_path / "s.png")
    assert not WS.clean_render(str(tmp_path / "s.png"))[0]
