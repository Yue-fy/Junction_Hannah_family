"""Offline tests for stoa.llm parsing helpers and vlm_direct number parsing (no server needed). Owner: R2."""

from stoa.llm import ImageInfo, Tile, extract_json, nms_points, parse_boxes, parse_points, tile_image
from stoa.solvers.vlm_direct import infer_kind, parse_number


def test_boxes_rel1000_json_fenced():
    txt = '```json\n[{"bbox_2d": [500, 250, 750, 500], "label": "door"}]\n```'
    (b,) = parse_boxes(txt, ImageInfo(800, 400, 800, 400))
    assert [round(v) for v in b.as_list()] == [400, 100, 600, 200] and b.label == "door"


def test_boxes_map_through_downscale_and_tile_offset():
    # original tile 1000x1000 at offset (2000, 0), sent at half size
    info = ImageInfo(1000, 1000, 500, 500, scale=0.5, offset=(2000.0, 0.0))
    (b,) = parse_boxes('[{"bbox_2d": [0, 0, 1000, 1000]}]', info)
    assert [round(v) for v in b.as_list()] == [2000, 0, 3000, 1000]


def test_points_json_and_molmo_tags():
    (p,) = parse_points('[{"point_2d": [100, 900], "label": "wc"}]', (1000, 1000))
    assert (round(p.x), round(p.y), p.label) == (100, 900, "wc")
    (q,) = parse_points('<point x="50.0" y="25.0" alt="sink">sink</point>', (200, 400))
    assert (round(q.x), round(q.y)) == (100, 100)


def test_extract_json_with_think_and_prose():
    assert extract_json('<think>hmm [1,2</think>Here: {"answer": 7} done') == {"answer": 7}
    assert extract_json("no json here") is None


def test_nms_points():
    from stoa.llm import Point

    pts = [Point(0, 0), Point(1, 1), Point(50, 50)]
    assert len(nms_points(pts, min_dist=5)) == 2


def test_tile_image_covers_image():
    from PIL import Image

    tiles = tile_image(Image.new("RGB", (3000, 1000)), tile=1280, overlap=160)
    assert all(isinstance(t, Tile) for t in tiles)
    assert max(t.x0 + t.image.width for t in tiles) == 3000 and min(t.x0 for t in tiles) == 0


def test_parse_number():
    assert parse_number("ANSWER: 7", integer=True) == 7
    assert parse_number("The total is 12,5 m²", integer=False) == 12.5
    assert parse_number("1 234.5", integer=False) == 1234.5
    assert parse_number("There are 3 sinks and 2 basins, so 5", integer=True) == 5
    assert parse_number("nothing", integer=True) is None


def test_infer_kind():
    assert infer_kind("How many windows are shown on this floor plan?") == ("count", "count")
    assert infer_kind("Kuinka monta ikkunaa pohjapiirustuksessa on?") == ("count", "count")
    assert infer_kind("What is the net floor area of room 3 (Kitchen) in m²?") == ("area", "m2")
    assert infer_kind("What is the total net volume of all walls on '1. Sal', in m³?") == ("volume", "m3")
    assert infer_kind("What is the total length of all walls on 'Erdgeschoss', in metres?") == ("length", "m")
    assert infer_kind("Which software was used?")[0] == "text"


def test_answer_prob_digits_and_max_digits():
    import math

    from stoa.llm import ChatResult, answer_prob

    toks = [{"t": "1", "lp": math.log(0.5), "top": []}, {"t": "2", "lp": math.log(0.8), "top": []},
            {"t": ".", "lp": 0.0, "top": []}, {"t": "5", "lp": math.log(0.5), "top": []},
            {"t": " m²", "lp": 0.0, "top": []}]
    r = ChatResult(text="12.5 m²", logprobs=toks)
    assert abs(answer_prob(r) - 0.2) < 1e-3  # 0.5 * 0.8 * 0.5
    assert abs(answer_prob(r, max_digits=2) - 0.4) < 1e-3
    assert answer_prob(ChatResult(text="x")) is None


def test_map_conf_monotone_table():
    from stoa.solvers import vlm_direct as vd

    old = dict(vd.CONF_MAP)
    try:
        vd.CONF_MAP.clear()
        vd.CONF_MAP["count"] = [(0.5, 0.2), (0.99, 0.4), (1.0, 0.9)]
        assert vd.map_conf(0.1, "count") == 0.2 and vd.map_conf(0.995, "count") == 0.9
        assert vd.map_conf(0.7, "area") == 0.7  # no measure table -> clipped raw probability
    finally:
        vd.CONF_MAP.clear()
        vd.CONF_MAP.update(old)


def test_vlm_lora_adapter_per_source(monkeypatch):
    """cubicasa -> cc-v2 always; other raster plans -> cc-v3 only when the server lists it; explicit model= wins."""
    from stoa import llm
    from stoa.solvers.vlm_direct import VlmLora

    monkeypatch.setattr(llm, "served_models", lambda backend="local", ttl=60.0: frozenset({"default", "cc-v2"}))
    s = VlmLora()
    assert s.model_for("data/cubicasa5k/colorful-1.png") == "cc-v2"
    assert s.model_for("data/swiss_dwellings/a.png") == "cc-v2"
    monkeypatch.setattr(llm, "served_models", lambda backend="local", ttl=60.0: frozenset({"cc-v2", "cc-v3"}))
    assert s.model_for("data/cubicasa5k/colorful-1.png") == "cc-v2"
    assert s.model_for("data/swiss_dwellings/a.png") == "cc-v3"
    assert VlmLora(model="cc-v2").model_for("data/swiss_dwellings/a.png") == "cc-v2"
    assert "washbasin" in VlmLora.TRAINED_BY_MODEL["cc-v3"] and "washbasin" not in VlmLora.TRAINED
