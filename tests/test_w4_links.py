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
