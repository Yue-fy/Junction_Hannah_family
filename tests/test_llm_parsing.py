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


# --- question translation front end (stoa.llm.to_english); offline: chat is monkeypatched ---

def test_lang_guess_ignores_quoted_names():
    from stoa.llm import lang_guess

    assert lang_guess("How many rooms labelled 'Pièce' are there on this floor?") == "en"
    assert lang_guess("Kuinka monta WC-istuinta pohjapiirustukseen on piirretty?") == "fi"
    assert lang_guess("Ile pomieszczeń jest na kondygnacji „-1”?") == "pl"
    assert lang_guess("Hány ajtó látható a(z) 'KG' szint alaprajzán?") == "hu"
    assert lang_guess("Bu kat planında kaç sauna var?") == "tr"


def test_protect_restore_roundtrip_keeps_names_numbers_letters():
    from stoa.llm import _protect, _restore

    q = "Mekkora az A lakás és az 1.11-es helyiség ('Zimmer') területe a „5.korrus” szinten, 2,40 €?"
    masked, spans = _protect(q)
    assert "Zimmer" not in masked and "5.korrus" not in masked and "2,40" not in masked
    assert "-es" in masked  # the case ending stays outside the placeholder so the model can translate it
    assert _restore(masked, spans) == (q, True)
    # the model dropped the quote marks around a name: they come back anyway
    txt = masked.replace("'[[", "[[").replace("]]'", "]]")
    assert "('Zimmer')" in _restore(txt, spans)[0]


def test_to_english_skips_covered_languages_and_checks_placeholders(monkeypatch):
    import stoa.llm as L

    calls = []

    class R:
        def __init__(self, text):
            self.text = text

    def fake_chat(masked, **kw):
        calls.append(masked)
        src = masked if isinstance(masked, str) else masked[0]["content"]  # the corrective retry sends a list
        if "kaç" in src:  # loses the placeholder (also on the retry) -> must fall back to the original
            return R('{"lang": "tr", "english": "How many rooms are there?"}')
        return R('{"lang": "cs", "english": "How many doors are on floor \'[[1]]\'?"}')

    monkeypatch.setattr(L, "chat", fake_chat)
    L._tr_memo.clear()
    de = L.to_english("Wie viele Türen gibt es im Geschoss 'EG'?")
    assert not de.translated and de.text.startswith("Wie viele") and calls == []
    cs = L.to_english("Kolik dveří je na podlaží 'KG'?")
    assert cs.translated and cs.ok and cs.text == "How many doors are on floor 'KG'?" and cs.lang == "cs"
    tr = L.to_english("Bu katta 'Bad' etiketli kaç oda var?")
    assert not tr.translated and not tr.ok and tr.text == "Bu katta 'Bad' etiketli kaç oda var?"
    L._tr_memo.clear()


def test_should_translate_fires_only_on_unparsed_non_english():
    from stoa.llm import should_translate

    assert not should_translate("How many doors are shown on the floor plan of 'KG'?")
    assert not should_translate("Kuinka monta WC-istuinta pohjapiirustukseen on piirretty?")  # fi template
    assert not should_translate("Wie viele WC-Schüsseln sind auf diesem Grundriss eingezeichnet?")
    assert should_translate("Kolik saun je na tomto půdorysu?")  # Czech: the rules can't read it
    assert should_translate("Mekkora a(z) '00 Begane grond' szinten lévő összes fal teljes hossza méterben?")


def test_protect_keeps_grouped_thousands_as_one_number():
    from stoa.llm import _protect, _restore

    for q, num in [("Wenn eine Tür 1'200 CHF kostet, was kosten alle Türen auf 'Level 2'?", "1'200"),
                   ("Ile kosztują drzwi, jeśli jedne kosztują 1 200 zł?", "1 200"),
                   ("Quanto costa se una porta costa 1’200 CHF?", "1’200")]:
        masked, spans = _protect(q)
        assert num in spans and "'200" not in masked and "200" not in masked
        assert _restore(masked, spans) == (q, True)


def test_should_translate_fires_on_unread_compositions_outside_rule_languages():
    from stoa.llm import should_translate

    from stoa.router.compose import _TOGETHER
    from stoa.router.intent import targets_mentioned

    # Swedish 'och' with no 'total' word at all: the composer never splits it, so the front end must
    assert should_translate("Hur många sovrum och bastur finns det på planritningen?")
    assert should_translate("Hur många toalettstolar och balkonger finns det på planritningen?")
    # Swedish 'och' + 'totalt' reached the LoRA as ONE class (balconies only). W4 08:54: once the composer reads
    # 'totalt' / the Swedish nouns, these are EITHER composed (two classes + a total word) OR translated, never neither
    for q in ("Hur många toalettstolar och balkonger finns det totalt på planritningen?",
              "Hur många sovrum och bastur finns det totalt på planritningen?",
              "Hur många sovrum och bastur finns det sammanlagt på planritningen?"):
        composed = len(set(targets_mentioned(q)) - {"apartment", "room"}) >= 2 and _TOGETHER.search(q)
        assert should_translate(q) or composed, q
    # two classes + a 'total' word the composer reads (NL 'in totaal'): keep the original (no translation cap)
    assert not should_translate("Hoeveel deuren en ramen staan er in totaal op deze plattegrond?")
    # rule languages compose themselves; no conjunction -> nothing to split
    assert not should_translate("Wie viele Türen und Fenster gibt es insgesamt?")
    assert not should_translate("Hur många dörrar finns det?")


def test_to_english_repairs_single_brackets_and_retries_a_lost_placeholder(monkeypatch):
    import stoa.llm as L

    class R:
        def __init__(self, text):
            self.text = text

    def fake_chat(msgs, **kw):
        if isinstance(msgs, str):  # first answer: [1] for [[1]], and [[2]] dropped
            return R('{"lang": "et", "english": "What share of floor \'[1]\' is the room?"}')
        return R('{"lang": "et", "english": "What share of floor \'[[1]]\' is the room \'[[2]]\'?"}')

    monkeypatch.setattr(L, "chat", fake_chat)
    L._tr_memo.clear()
    t = L.to_english("Kui suure osa korruse '2. Level' netopinnast hõivab ruum 'Office (2.14)'?", force=True)
    assert t.ok and t.translated and t.text == "What share of floor '2. Level' is the room 'Office (2.14)'?"
    assert L._restore("floor '[1]' and room '[[2]]'", ["'A'", "'B'"]) == ("floor 'A' and room 'B'", True)
    assert L.lang_guess("Milline protsent korruse '3. korrus' netopinnast on ruum 'WC (3.05)'?") == "et"
    L._tr_memo.clear()


def test_text_backend_is_opt_in_and_falls_back(monkeypatch):
    import stoa.llm as L

    monkeypatch.delenv("STOA_TEXT_BACKEND", raising=False)
    assert L.text_backend() == "local"
    monkeypatch.setenv("STOA_TEXT_BACKEND", "local2")
    L._TB_SEEN.clear()

    class Down:
        def with_options(self, **kw):
            raise ConnectionError("no server on :8002")

    monkeypatch.setattr(L, "_client", lambda b: Down())
    assert L.text_backend() == "local"  # second server down -> shared server
    L._TB_SEEN.clear()
    monkeypatch.setenv("STOA_TEXT_BACKEND", "no-such-backend")
    assert L.text_backend() == "local"


def test_lang_guess_terse_wordings_and_shared_words():
    from stoa.llm import _LANG_DF, _LANG_WORDS2, lang_guess
    from stoa.llm import _lang_score as score

    def v2(q):
        return score(q, _LANG_WORDS2, _LANG_DF)

    # R2 09:40: terse wordings without a question word were read as English on a tie ('in' vs 'und'); a word several
    # languages share now counts 1/(number of languages listing it) in the v2 scorer
    assert v2("Nettofläche Whg. B in m², ohne Balkon und Loggia?") == "de"
    assert v2("Quante porte ci sono in tutto l'edificio?") == "it"
    assert v2("Laske ikkunat.") == "fi"
    assert v2("Hvor mange rum er vist på plantegningen for 'Grundplan'?") == "da"
    # ... but lang_guess takes v2 only when it moves a question to an UNCOVERED language (the pipeline skips
    # translation for covered ones: terse Finnish lost its translation fallback when it became 'fi')
    assert lang_guess("Laske ikkunat.") == "?"
    assert lang_guess("Tel de ramen op deze plattegrond.") == "nl"          # was 'fr' -> never translated
    assert lang_guess("Aantal deuren op deze plattegrond?") == "nl"
    assert lang_guess("Número de puertas en la planta baja?") == "es"       # was 'fr'
    assert lang_guess("Har lägenheten en bastu?") == "sv"                   # was 'es'
    assert lang_guess("Mekkora a 3.09-es szoba ('Küche') nettó alapterülete m²-ban?") == "hu"  # was 'de'
    # English stays English, also with an unquoted Dutch storey name and short keyword questions
    for q in ("Room 'kleedkamer (12)' (00 Begane grond): area in square metres?", "Net area apartment C in m²?",
              "Total wall length on 2.OG?", "Number of doors on this plan?"):
        assert lang_guess(q) == "en" and v2(q) == "en", q
    # a non-Latin script is never a rule language (Greek 'netto' must not make it Italian)
    assert v2("Πόσες φορές είναι μεγαλύτερο το διαμέρισμα Α από το Β κατά netto επιφάνεια;") == "?"
