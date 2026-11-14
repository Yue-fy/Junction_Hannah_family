"""W4 cycle 236: Finnish/Swedish wording gaps from F / R2 open probes (0 of 6,789 dataset parses change)."""
from stoa.router.intent import parse


def test_fi_basin_and_count_imperatives():
    assert parse("Montako allasta keittiössä on?").target == "sink"  # F 08:45: was a kitchen count
    assert parse("Montako pesuallasta on?").target == "washbasin"
    it = parse("Laske ikkunat tässä pohjapiirroksessa.")  # 'count the windows' was a text question
    assert (it.task, it.target, it.lang) == ("count", "window", "fi")
    it = parse("Räkna fönstren på planritningen.")
    assert (it.task, it.target, it.lang) == ("count", "window", "sv")


def test_room_code_list_means_bathrooms():
    # R2 08:52: a parenthesised list of Finnish wet-room codes names rooms
    assert parse("How many bathrooms or toilets (e.g. KH, KPH, PH, PESUH, SH) does this apartment have?").target == "bathroom"
    assert parse("How many toilets (WC) are there?").target == "wc"


def test_agent_assumed_value_regex():
    from stoa.router.agent import _ASSUMED

    assert _ASSUMED.search("No definitive evidence of sheet count in the drawing. Assume standard practice for small sets.")
    assert _ASSUMED.search("No label for bathroom sinks found; assume zero based on data.")
    assert not _ASSUMED.search("The vision model identified 3 sheets in the drawing set.")
    assert not _ASSUMED.search("The total area of the floor plan is 77.3 m2.")


def test_typo_normalisers():
    from stoa.pipeline import normalise_refs

    assert normalise_refs("What is the area of room 5,11?") == "What is the area of room 5.11?"
    assert normalise_refs("rooms 2,03, 2,04 and 2,05") == "rooms 2.03, 2.04 and 2.05"
    assert normalise_refs("what is the net floor area of apartment d without balconies") == \
        "what is the net floor area of apartment D without balconies"
    assert normalise_refs("how big is flat d without the balcony?") == "how big is apartment D without the balcony?"
    assert normalise_refs("What is the area of the appartment B?") == "What is the area of the apartment B?"
    assert normalise_refs("Area in sqm of apartment B?") == "Area in m² of apartment B?"
    # untouched: an article after 'apartment', square feet, a three-part number
    assert normalise_refs("Is there an apartment a tenant could rent?") == "Is there an apartment a tenant could rent?"
    assert normalise_refs("What is the area in sq ft?") == "What is the area in sq ft?"
    assert normalise_refs("room 1,20,30") == "room 1,20,30"


def test_no_balconies_is_an_exclusion():
    from stoa.pipeline import normalise_refs

    assert normalise_refs("apartment D net area in sq m (no balconies)") == "Apartment D net area in m² (excluding balconies)"
    assert normalise_refs("area of apartment C with no balcony") == "area of apartment C excluding balcony"
    assert normalise_refs("Are there no balconies?") == "Are there no balconies?"


def test_swedish_compositions():
    from stoa.router.compose import decompose

    p = decompose("cubicasa5k", "Hur många sovrum och badrum (inte separata toaletter) har bostaden sammanlagt?")
    assert p and p.op == "sum" and p.labels == ["bedroom", "bathroom"]
    p = decompose("cubicasa5k", "Hur många våtrum har bostaden (badrum, separata toaletter och bastur tillsammans)?")
    assert p and p.op == "sum" and p.labels == ["bathroom", "wc_room", "sauna"]
    p = decompose("cubicasa5k", "Hur många toalettstolar, duschar och badkar finns det sammanlagt på planen?")
    assert p and p.labels == ["wc", "shower_bathtub"]
    # a single class inside parentheses stays a definition
    assert decompose("cubicasa5k", "How many bedrooms (MH) are there in total?") is None


def test_swedish_totalt():
    from stoa.router.compose import decompose

    p = decompose("cubicasa5k", "Hur många sanitetsenheter finns det totalt på planen (toalettstolar, handfat och "
                                "diskhoar, duschar och badkar)?")
    assert p and p.labels == ["wc", "sink", "shower_bathtub"]
    assert decompose("cubicasa5k", "Hur många dörrar finns det totalt?") is None


def test_name_sheet_from_file_name():
    from stoa.pipeline import name_sheet

    p = "data/opening_design/x/The Downtowner_ARCH - Sheet - A000 - SITE PLAN & CODE SUMMARY.pdf"
    assert name_sheet("How long is the wood fence?", p, "opening_design") == \
        "On sheet A000 (Site Plan & Code Summary), how long is the wood fence?"
    assert name_sheet("On sheet A000, how long is the fence?", p, "opening_design") == "On sheet A000, how long is the fence?"
    assert name_sheet("How many sheets are in this set?", p, "opening_design") == "How many sheets are in this set?"
    assert name_sheet("How long is the wood fence?", p, "swiss_dwellings") == "How long is the wood fence?"
