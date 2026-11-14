"""W4 c235: question normalisers, the compose 'list' plan, the unused-class guard and the room-relation trigger."""
from stoa.contract import Answer
from stoa.pipeline import ROOM_REL, _unused_classes, normalise_numbers, normalise_refs
from stoa.router.compose import combine, decompose
from stoa.router.intent import parse


def test_thousands_next_to_currency():
    assert normalise_numbers("Wenn eine Tür 1'200 CHF kostet, was kosten alle Türen auf '1.korrus'?") == \
        "Wenn eine Tür 1200 CHF kostet, was kosten alle Türen auf '1.korrus'?"
    assert normalise_numbers("If each door costs 1,200 euros, what") == "If each door costs 1200 euros, what"
    assert normalise_numbers("If each door costs €1,500, what") == "If each door costs €1500, what"
    assert normalise_numbers("Jos yksi ovi maksaa 1 200 euroa") == "Jos yksi ovi maksaa 1200 euroa"
    assert normalise_numbers("1.250,50 CHF") == "1250.50 CHF"


def test_numbers_left_alone():
    for q in ["If each door costs 450,50 euros", "Ist Wohnung B grösser als 80,5 m²?", "door 1,250 m wide",
              "room '2' and '200'", "EUR 1.200.50"]:
        assert normalise_numbers(q) == q


def test_apartment_references():
    assert normalise_refs("What is the net floor area of D apartment in m², excluding balconies?") == \
        "What is the net floor area of apartment D in m², excluding balconies?"
    assert normalise_refs("Net floor area of apt. D in m²?") == "Net floor area of apartment D in m²?"
    assert normalise_refs("What is the net area of apartment-D in m2?") == "What is the net area of apartment D in m2?"
    assert normalise_refs("area of apartment 'D' (all rooms)") == "area of apartment D (all rooms)"
    assert normalise_refs("How big is flat D?") == "How big is apartment D?"
    assert normalise_refs("Apartment D: what is its net floor area in m², balconies excluded?") == \
        "Apartment D: what is its net floor area in m², excluding balconies?"
    for q in ["How many apartments are there?", "What is the area of a apartment?", "price per unit area",
              "unit of measure", "How many windows in apartment B?"]:
        assert normalise_refs(q) == q


def test_apartment_id_not_a_word():
    assert parse("What is the net floor area of apartment B in m²?").filters.get("apartment") == "B"
    assert parse("What is the net floor area of apartment in m² B?").filters.get("apartment") is None


def test_list_plan_for_two_counting_cues():
    p = decompose("ifc_models", "How many doors and how many windows are on '1.korrus'?")
    assert p is not None and p.op == "list" and p.labels == ["door", "window"]
    assert combine(p, [46, 55])[0] == "door: 46; window: 55"
    assert decompose("swiss_dwellings", "How many doors and windows are on this floor plan in total?").op == "sum"


def test_unused_classes_scope_words_and_synonyms():
    assert _unused_classes("How many bathroom sinks are on this floor?",
                           Answer(value=4, unit="count", confidence=0.95, trace=["washbasins = 4"])) == set()
    assert _unused_classes("How many toilets and sinks are on this floor plan?",
                           Answer(value=6, unit="count", confidence=0.95, trace=["toilets = 6"])) == {"sink"}
    assert parse("How many doors does this floor have, including the apartment entrance doors?").target == "door"


def test_room_relation_trigger():
    assert ROOM_REL.search("Through which room is the sauna entered?")
    assert ROOM_REL.search("How many windows does the kitchen have?")
    assert not ROOM_REL.search("How many windows are shown on this floor plan?")
    assert not ROOM_REL.search("How many bedrooms (makuuhuone, usually marked MH) are on this floor plan?")
