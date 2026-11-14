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
