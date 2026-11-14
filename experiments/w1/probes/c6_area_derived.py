"""c6 probe 5 (09:03): AREA-typed derived quantities (S0 08:22 hard3 class: area x rate / stated constant / share /
area of a derived set), 15 fresh wordings on non-test models in en/de/es, written BEFORE any fix. Gold = arithmetic on
the solver's own atomic answers to dataset-style wordings (100% on the dataset). Run with SOLVER=pipeline for end to end.
Run: PYTHONPATH=. python experiments/w1/probes/c6_area_derived.py"""
import os

from stoa.solvers import get_solver
from stoa.solvers.ifc.solver import IfcSolver

ATOM = IfcSolver(plan2d="0")
S = get_solver(os.environ.get("SOLVER", "ifc"))
W = "data/ifc_models/bimspeed-warmond_ar_plan-03-1-level.pdf"
G = "data/ifc_models/bimspeed-gdynia_ruchu-oporu-18_plan-03-0.pdf"
SM = "data/ifc_models/kit-smiley-west_ac-20-smiley-west-10-bldg_plan-02-eg.pdf"
D = "data/ifc_models/bsc-duplex_duplex-a-20110907.ifc"


def v(p, q):
    return float(ATOM.solve(p, q).value)


wl1, wa1, ra1 = (v(W, "What is the total length of the walls on '1. Level'?"),
                 v(W, "What is the total wall area on '1. Level'?"),
                 v(W, "What is the total net floor area of all rooms on '1. Level', in m²?"))
big1 = v(W, "What is the total area of the rooms on '1. Level' that are larger than 20 m²?")
kit = v(W, "What is the net floor area of the room 'Kitchen (414B-1-001-007)' on '1. Level', in m²?")
gwl0, gwa0, gra1, gra0 = (v(G, "What is the total length of the walls on '0'?"), v(G, "What is the total wall area on '0'?"),
                          v(G, "What is the total net floor area of all rooms on '1', in m²?"),
                          v(G, "What is the total net floor area of all rooms on '0', in m²?"))
hall = v(G, "What is the net floor area of the room 'Hall (0.1)' on '0', in m²?")
sra, sdoors, skg = (v(SM, "What is the total net floor area of all rooms on 'EG', in m²?"),
                    v(SM, "How many doors are on 'EG'?"), v(SM, "What is the total net floor area of all rooms on 'KG', in m²?"))
small = v(SM, "What is the total area of the rooms on 'EG' that are smaller than 5 m²?")
dwl, dra, dbig = (v(D, "What is the total length of the walls on 'Level 1'?"),
                  v(D, "What is the total net floor area of all rooms on 'Level 1', in m²?"),
                  v(D, "What is the total area of the rooms on 'Level 1' that are larger than 15 m²?"))
CASES = [
    (W, "If the walls on '1. Level' are 2.6 m high, what is their total side area?", wl1 * 2.6),
    (W, "What does it cost to paint all walls on '1. Level' on one side at 12 € per m²?", wa1 * 12),
    (W, "If the rooms on '1. Level' have a ceiling height of 2.5 m, what is their total volume in m³?", ra1 * 2.5),
    (W, "What percentage of the net floor area on '1. Level' is taken by rooms larger than 20 m²?", 100 * big1 / ra1),
    (W, "What is the usable room area on '1. Level' if 10% is lost to furniture?", ra1 * 0.9),
    (W, "If tiling costs 60 EUR per square metre, what does it cost to tile the floor of 'Kitchen (414B-1-001-007)' on '1. Level'?",
     kit * 60),
    (G, "Wie groß ist die Wandfläche aller Wände auf '0', wenn die Wände 2,8 m hoch sind?", gwl0 * 2.8),
    (G, "¿Cuánto cuesta pintar todas las paredes de '0' a 15 € por m²?", gwa0 * 15),
    (G, "Si los techos de '1' miden 2,5 m de alto, ¿cuál es el volumen total de las habitaciones?", gra1 * 2.5),
    (G, "¿Qué porcentaje de la superficie de '0' ocupa la habitación 'Hall (0.1)'?", 100 * hall / gra0),
    (SM, "How much floor area do the rooms on 'EG' have per door?", sra / sdoors),
    (SM, "What is the floor area of the rooms on 'EG' without the rooms smaller than 5 m²?", sra - small),
    (SM, "Was kostet ein neuer Bodenbelag für alle Räume auf 'KG' bei 45 € pro m²?", skg * 45),
    (D, "If the walls on 'Level 1' are 3 m tall, how many square metres of wall is that?", dwl * 3),
    (D, "What share of the room area on 'Level 1' is in rooms larger than 15 m², in percent?", 100 * dbig / dra),
]
ok = cw = 0
for p, q, gold in CASES:
    a = S.solve(p, q)
    try:
        good = abs(float(a.value) - gold) <= 0.02 * abs(gold) + 1e-6
    except (TypeError, ValueError):
        good = False
    ok += good
    cw += (not good) and a.confidence >= 0.8
    print(f"{'OK ' if good else 'BAD'} [{a.confidence:.2f}] {str(a.value)[:40]:>14} {a.unit or ''} (gold {gold:.2f}) <- {q}")
print(f"{ok}/{len(CASES)} right, {cw} confident-wrong (>=0.8)")
