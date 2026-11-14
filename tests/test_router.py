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


def test_modifiers_and_agent_calc():
    from stoa.router.agent import calc
    from stoa.router.intent import modifiers

    assert modifiers("On average, how large (net m²) is a room labelled 'Bad' on this floor?") == ["avg"]
    assert "share" in modifiers("What percentage of the total net indoor floor area is taken up by rooms labelled 'Zimmer'?")
    assert modifiers("How many rooms in this home are meant for sleeping?") == []  # 'meant' is not 'mean'
    assert modifiers("What are the different wall thicknesses used?") == []
    assert "multi" in modifiers("How many wet rooms are there (bathrooms, separate WC rooms and saunas all count)?")
    # dataset templates never carry modifiers (the sinks definition in parentheses is not an enumeration)
    assert modifiers("How many sinks and wash basins (kitchen and bathroom combined; a double-bowl sink counts as one) "
                     "are drawn on this floor plan?") == []
    assert modifiers("Kuinka monta ikkunaa pohjapiirustuksessa on?") == []
    assert abs(calc("(42.34)/3") - 14.1133) < 1e-3 and calc("abs(70.75-48.61)") == 22.14
    import pytest

    with pytest.raises(Exception):
        calc("__import__('os').system('true')")


def test_operator_modifiers_cycle3():
    """F's hard2 kinds: complement, ratio, word thresholds, comparisons, two scopes go to the agent, not a template."""
    from stoa.router.intent import modifiers

    assert "rest" in modifiers("What is the total net floor area, in m², of the numbered indoor rooms on this floor that "
                               "do not belong to apartment A?")
    assert "ratio" in modifiers("How many times larger is apartment B than apartment A by net floor area?")
    assert "threshold" in modifiers("Does this floor plan show at least two toilet seats (WC bowls)? Answer yes or no.")
    assert "threshold" in modifiers("How many of the rooms 3.01 ('Wohnen') and 3.05 ('Bad') have a net floor area of "
                                    "more than 15 m²?")
    assert "compare" in modifiers("Which is smaller by net floor area, apartment B or apartment H?")
    assert "compare" in modifiers("Which storey has more doors on its floor plan, '0' or '-1'?")
    assert "multi_scope" in modifiers("What is the combined net floor area of all rooms (spaces) on '2. Level' and on "
                                      "'Attic', in m²?")
    assert modifiers("How many doors are shown on the floor plan of 'Level 1'?") == []
    assert modifiers("What is the net floor area of the room 'Kitchen (1.2)' on '1', in m²?") == []


def test_atleast_plan_and_calc_compare():
    from stoa.router.agent import Agent, calc
    from stoa.router.compose import combine, decompose

    p = decompose("cubicasa5k", "Does this floor plan show at least two toilet seats (WC bowls)? Answer yes or no.")
    assert p is not None and p.op == "atleast" and p.note == "2"
    assert combine(p, [1])[0] == "no" and combine(p, [2])[0] == "yes"
    assert calc("(38.65 > 31) + (12.07 > 31)") == 1.0
    # grounding: every calc number must come from a tool result / the table / the question / a constant
    res = [(113.02, 0.976, [], "ask: B"), (105.93, 0.976, [], "ask: A"), (1.067, -1.0, [], "calc: 113.02 / 105.93")]
    used, n_table, bad = Agent._grounding("113.02 / 105.93", res, "How many times larger is B than A?")
    assert len(used) == 2 and not bad and n_table == 0
    assert Agent._grounding("113.02 / 99.5", res, "?")[2] == ["99.5"]


def test_gate_keeps_near_perfect_solver_first():
    from stoa.router import gating

    order, _ = gating.plan("swiss_dwellings", "area:room:room", ["dxf", "pdf_vector", "vlm_direct"])
    assert order[0] == "dxf"


def test_apartment_scope_kept_for_counts():
    """W2: dxf answers apartment-scoped counts; the router must not canonicalise them to the whole floor."""
    from stoa.router.canonical import canonical
    from stoa.router.compose import decompose
    from stoa.router.intent import modifiers, parse

    it = parse("How many windows are in apartment B?")
    assert it.key == "count:window:apartment" and it.filters == {"apartment": "B"}
    assert canonical("swiss_dwellings", it) is None and modifiers("How many windows are in apartment B?") == []
    it = parse("How many rooms labelled 'Zimmer' are in apartment C?")
    assert it.filters.get("apartment") == "C" and canonical("swiss_dwellings", it) is None
    assert decompose("swiss_dwellings", "How many doors and windows does apartment C have in total?") is None
    assert parse("How many bedrooms does this apartment have?").filters == {}


def test_cc5k_switch(monkeypatch, tmp_path):
    """D8: cc5k=1 sends cubicasa window counts to raster_cc5k with its cc5k_heldout rate; cc5k=0 never calls it."""
    import json

    import stoa.pipeline as pl
    import stoa.solvers.raster_cc5k  # noqa: F401  (register the real one first, or it replaces the stub on first use)
    from stoa.contract import Answer
    from stoa.solvers import _REGISTRY
    from stoa.solvers.base import BaseSolver

    calls = []

    class Stub(BaseSolver):
        def can_handle(self, path, question):
            return True

        def solve(self, path, question):
            calls.append(question)
            return Answer(value=7, unit="count", confidence=0.5, solver="raster_cc5k")

    gate = tmp_path / "gating_cc5k.json"
    gate.write_text(json.dumps({"meta": {}, "entries": {"cubicasa5k|count:window:drawing": {
        "n": 100, "acc": {"prior": 0.15, "raster_cc5k": 0.40}, "cost_usd": {}}}}))
    monkeypatch.setattr(pl, "GATING_CC5K", gate)
    monkeypatch.setitem(_REGISTRY, "raster_cc5k", Stub)
    q, path = "How many windows are shown on this floor plan?", "data/cubicasa5k/x.png"
    off = pl.Pipeline(cc5k=0, crosscheck=0)._solve_atomic(path, q)
    assert not calls and off.solver != "pipeline/raster_cc5k"
    on = pl.Pipeline(cc5k=1, crosscheck=0)._solve_atomic(path, q)
    assert calls and on.value == 7 and on.solver == "pipeline/raster_cc5k"
    assert abs(on.confidence - (0.40 * 100 + 1) / 102) < 1e-3


def test_unit_fit_and_multilingual_threshold():
    from stoa.contract import Answer
    from stoa.pipeline import _fits
    from stoa.router.intent import modifiers

    assert not _fits("count", Answer(value=275.05, unit="m2", confidence=0.3))
    assert _fits("count", Answer(value=12, unit="count", confidence=0.9)) and _fits("text", Answer(value="B", confidence=0.5))
    for q in ("Wie viele Räume sind größer als 10 m²?", "Combien de pièces font plus de 12 m² ?",
              "Hoeveel ruimtes zijn groter dan 10 m²?", "Hur många rum är större än 10 m²?"):
        assert "threshold" in modifiers(q), q


def test_agent_rows_condition_is_restricted():
    from stoa.router.agent import Agent

    ok = Agent._COND_OK
    assert ok.fullmatch("area_m2 > 10 and numbered and not outdoor")
    ag = Agent()
    for bad in ('__import__("os")', "name.str.len() > 3", "open('x')"):
        assert ag._rows("data/swiss_dwellings/none.pdf", bad, []).startswith("error")


def test_count_cue_with_unit_is_a_quantity():
    from stoa.router.intent import parse

    assert (parse("How many square feet of net floor area do rooms 1.01 and 1.02 have together?").task, "area") == ("area", "area")
    assert parse("How many square feet of net floor area do rooms 1.01 and 1.02 have together?").unit == "ft2"
    assert parse("How many metres of wall are there on 'KG'?").task == "length"
    assert parse("Wie viele Quadratmeter hat Wohnung A?").task == "area"
    assert parse("How many doors are there?").task == "count"
    assert parse("How many rooms are larger than 10 m²?").task == "count"


def test_derived_quantity_modifiers():
    """Rates, prices and constants stated in the question are operators (W5 01:49: '46 count' at conf 0.97 for a
    door-cost question); 'per apartment' stays an average and plain templates get none."""
    from stoa.router.intent import DERIVED, modifiers

    def d(q):
        return [m for m in modifiers(q) if m in DERIVED]

    assert "cost" in d("If each door costs 450 euros, how much do the doors on '1.korrus' cost in total, in euros?")
    assert "cost" in d("Wie viel kosten die Türen im '1.korrus', wenn eine Tür 450 Euro kostet?")
    assert d("How many square metres of floor per door are there on '1.korrus'?") == ["rate"]
    assert d("Montako ikkunaa kerroksessa '1' on 100 neliömetriä kohden?") == ["rate"]
    assert d("If every bedroom gets two beds, how many beds are needed for this home?") == ["given"]
    assert d("How many litres of paint are needed for the walls of 'A' if one litre covers 8 m2 of wall?") == ["given"]
    assert d("What is the average area per apartment?") == []
    assert d("Quanti locali ci sono per l'appartamento A?") == []
    assert d("How many windows are shown on this floor plan?") == []
    assert d("How many rooms labelled 'Bad' are there on this floor?") == []


def test_extra_structure():
    from stoa.router.intent import extra_structure

    assert not extra_structure("I need a quick count for a quantity takeoff: bedrooms (rooms marked MH) on this sheet?")
    assert not extra_structure("Wie viele Saunen gibt es auf diesem Grundriss?")
    assert not extra_structure("How many sinks (kitchen and bathroom combined; a double sink counts as one) are drawn?")
    assert extra_structure("Hur många fler sovrum än badrum finns det?")
    assert extra_structure("How many more bedrooms than bathrooms are there?")
    assert extra_structure("How many rooms are larger than 10 m²?")


def test_compose_yesno_comparison():
    from stoa.router.compose import combine, decompose

    p = decompose("cubicasa5k", "Does this apartment have more bedrooms (MH) than bathrooms or washrooms? Answer yes or no.")
    assert p is not None and p.op == "gt" and p.labels == ["bedroom", "bathroom"]
    assert combine(p, [2, 2])[0] == "no" and combine(p, [3, 1])[0] == "yes"
    assert decompose("cubicasa5k", "Does this apartment have a sauna?").op == "exists"


def test_absence_cap():
    """Q 09:58: a VLM's '0 stairs' with no located evidence is an unverified absence claim (capped); '0 pools' is not."""
    from stoa.contract import Answer, Evidence
    from stoa.pipeline import ABSENCE_CAP, _absence_cap

    stairs, pools = parse("How many stairs are shown on the floor plan of '1.OG'?"), parse("How many swimming pools are there?")
    c, a = _absence_cap(stairs, 0.89, Answer(value=0, unit="count", confidence=0.89), [])
    assert c == ABSENCE_CAP and a.missing
    assert _absence_cap(stairs, 0.89, Answer(value=3, unit="count", confidence=0.89), [])[0] == 0.89
    assert _absence_cap(pools, 0.89, Answer(value=0, unit="count", confidence=0.89), [])[0] == 0.89
    boxed = Answer(value=0, unit="count", confidence=0.89,
                   evidence=[Evidence(file="a.pdf", page=0, bbox=[0, 0, 1, 1], bbox_space="pdf_pt", note="x")])
    assert _absence_cap(stairs, 0.89, boxed, [])[0] == 0.89


def test_listed_total():
    """Q v25: a total asked of a listed top-N (ifc's 'NAME (ID) (90.64 m²); …') is the list's sum; list requests stay."""
    from stoa.contract import Answer
    from stoa.pipeline import _listed_total

    lst = "FUAJEE-TREPIKODA (101) (90.64 m²); KORIDOR (105) (78.40 m²); KORIDOR (119) (63.84 m²)"
    q = "What is the total area of the three largest rooms on '1.korrus'?"
    out = _listed_total(q, parse(q), Answer(value=lst, confidence=0.9))
    assert out.value == 232.88 and out.unit == "m²" and out.confidence == 0.9
    tie = "Bedroom 2 (A203) (22.04 m²); Bedroom 1 (A202) (22.04 m²) (tie at 22.04 m² with Bedroom 2 (B203))"
    q2 = "What is the total area of the two largest rooms on 'Level 2'?"
    assert _listed_total(q2, parse(q2), Answer(value=tie, confidence=0.8)).value == 44.08
    for q3 in ("What are the three largest rooms on '1.korrus'?", "Which rooms have a total area above 50 m²?"):
        assert _listed_total(q3, parse(q3), Answer(value=lst, confidence=0.9)) is None
    assert _listed_total(q, parse(q), Answer(value="FUAJEE (101); KORIDOR (105)", confidence=0.9)) is None


def test_link_route_plan_vs_model_overrules_kg_qa(monkeypatch):
    """W1 10:26: W1's deterministic GlobalId reading checks kg_qa on link questions; same -> ✓, different -> its value at the cap."""
    import experiments.r1.kg_qa.kgqa as kq
    import stoa.pipeline as pl
    import stoa.solvers.ifc as ifcmod
    from stoa.contract import Answer

    monkeypatch.setattr(kq, "is_link_question", lambda q: {"fire": True, "why": "plan and model named"})
    monkeypatch.setattr(kq, "solve", lambda p, q: Answer(value="no (model 55, plan draws 52)", confidence=0.85))
    monkeypatch.setattr(ifcmod, "plan_vs_model", lambda p, q: Answer(value="yes: 55 vs 52", confidence=0.85))
    path = "data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf"
    q = "Does this plan show fewer windows than the IFC model has?"
    out = pl.Pipeline(crosscheck=0)._link_question(path, q, 0.0)  # disagree -> GlobalId value, capped, kg_qa named
    assert out.value.startswith("yes") and out.confidence == pl.LINK_DISAGREE and out.solver == "pipeline/ifc"
    assert any("knowledge-graph reader answered no" in m for m in out.missing)
    monkeypatch.setattr(kq, "solve", lambda p, q: Answer(value=None, confidence=0.0))  # no KG -> GlobalId reading
    assert pl.Pipeline(crosscheck=0)._link_question(path, q, 0.0).solver == "pipeline/ifc"
    monkeypatch.setattr(kq, "solve", lambda p, q: Answer(value="yes (52 < 55)", confidence=0.85))
    out = pl.Pipeline(crosscheck=0)._link_question(path, q, 0.0)
    assert out.solver == "pipeline/kg_qa" and any("GlobalId reading says" in t and "✓" in t for t in out.trace)
    off = pl.Pipeline(crosscheck=0, pvm=0)._link_question(path, q, 0.0)
    assert not any("GlobalId" in t for t in off.trace)


def test_shape_guard():
    """Q 10:38/10:40: a which-floor question answered by a number, a yes/no question by a number, 'how many' by yes."""
    from stoa.contract import Answer
    from stoa.pipeline import SHAPE_CAP, _shape_guard

    def c(q, v):
        return _shape_guard(q, Answer(value=v, confidence=0.9)).confidence

    assert c("Quale piano ha il maggior numero di porte?", 27) == SHAPE_CAP
    assert c("Which floor has the biggest room?", "yes (model 55 vs drawn 52)") == SHAPE_CAP
    assert c("Is the door count on this drawing the same as in the BIM model?", "50") == SHAPE_CAP
    assert c("By how many doors does this plan differ from the IFC model?", "yes: both have 46") == SHAPE_CAP
    for q, v in [("Which storey has more doors on its floor plan, '0' or '-1'?", "0"), ("Which sheet number is this?", "2"),
                 ("How many doors are there?", 12), ("Does the plan show fewer windows than the model?", "yes (52 < 55)"),
                 ("Which spaces have supply air?", "No spaces are explicitly linked"),
                 ("Quelle est la surface nette de la pièce 3.03 ?", "10.48"), ("Mikä on asunnon B pinta-ala?", 80.83)]:
        assert c(q, v) == 0.9, q
