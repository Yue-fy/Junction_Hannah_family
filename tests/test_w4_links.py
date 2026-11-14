"""W4 D20-4: link questions (plan <-> model, drawing set) on IFC projects go to R1's kg_qa, ifc cross-checks."""
from stoa.pipeline import Pipeline, _link_shape


def test_link_shape():
    assert _link_shape("no: model 55, plan draws 52") == ("yn", "no")
    assert _link_shape("yes (model 15 vs drawn 13)") == ("yn", "yes")
    assert _link_shape(3) == ("num", 3.0)
    assert _link_shape("3") == ("num", 3.0)
    # ifc's unsure prose is not a yes/no reading
    assert _link_shape("No information is provided in the model about it") is None
    assert _link_shape("Basement, Entrance") is None


def test_link_route_only_on_ifc_projects():
    p = Pipeline()
    # a link-sounding question on a non-IFC drawing never takes the route
    assert p._link_question("data/swiss_dwellings/plan_1.pdf",
                            "Do the floor plan and the IFC model agree on the number of doors?", 0.0) is None
    # a plain building fact on an IFC sheet does not fire (R1's narrow trigger)
    assert p._link_question("data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf",
                            "How many doors are on '1.korrus'?", 0.0) is None


def test_question_budget(monkeypatch):
    """D20-2: one LLM budget per question; optional steps are skipped once it is spent, and the answer says so."""
    from stoa.contract import record_cost
    from stoa.router import budget

    monkeypatch.setattr(budget, "QUESTION_TOKENS", 1000)
    assert budget.skip("x") is None  # outside a question nothing is metered
    with budget.question():
        assert budget.skip("the general agent") is None
        record_cost(llm_calls=1, llm_tokens_in=900, llm_tokens_out=200)
        assert budget.spent() == (1100, 1)
        with budget.question():  # nested: the same meter
            assert budget.spent() == (1100, 1)
        assert "budget" in budget.skip("the general agent")
        assert "the general agent skipped" in budget.note()
    assert budget.spent() == (0, 0)


def test_kg_crosscheck_skipped_for_operator_questions():
    """W1 09:25: a threshold count compared with the storey's full room count is a false ✗."""
    from stoa.contract import Answer
    from stoa.router.intent import parse

    q = "How many rooms on '1.korrus' are larger than 50 m²?"
    a = Answer(value=4, unit="count", confidence=0.92, solver="ifc")
    tr: list[str] = []
    Pipeline()._kg_crosscheck("data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf", parse(q), a, tr, q)
    assert a.confidence == 0.92 and tr and "skipped" in tr[0]


def test_clip_cuts_at_a_word():
    from stoa.pipeline import _clip

    t = _clip("no: the IFC model has 55 windows on '1.korrus', the plan draws 52 (the other 3 lie above)", 60)
    assert t.endswith(" …") and len(t) <= 62 and not t[:-2].endswith("dra")
