"""c6 probe 4 (08:47): derived quantities in fresh wordings, written before running. Gold = arithmetic on the
solver's own atomic answers (100% on the dataset), so this checks parsing + arithmetic, not the model reading.
Run: PYTHONPATH=. python experiments/w1/probes/c6_derived.py"""
from stoa.solvers.ifc.solver import IfcSolver

S = IfcSolver(plan2d="0")
W = "data/ifc_models/bimspeed-warmond_ar_plan-03-1-level.pdf"
G = "data/ifc_models/bimspeed-gdynia_ruchu-oporu-18_plan-03-0.pdf"


def v(p, q):
    return S.solve(p, q).value


area1 = v(W, "What is the total net floor area of all rooms on '1. Level', in m²?")
doors1 = v(W, "How many doors are on '1. Level'?")
win1 = v(W, "How many windows are on '1. Level'?")
walls_len = v(W, "What is the total length of the walls on '1. Level'?")
g_doors = v(G, "How many doors are in the whole building?")
CASES = [
    (W, "What would it cost to put new flooring in every room on '1. Level' at €1,250 per m²?", area1 * 1250),
    (W, "Flooring costs 1.250 EUR pro m². Was kostet der Boden aller Räume auf '1. Level'?", area1 * 1250),
    (W, "If every door on '1. Level' gets a lock costing 1,050 euros, what do the locks cost altogether?", doors1 * 1050),
    (W, "What share of the openings on '1. Level' are windows, in percent?", 100 * win1 / (win1 + doors1)),
    (W, "If 25% of the doors on '1. Level' are replaced, how many doors is that?", doors1 * 0.25),
    (W, "A crew lays 12.5 m of wall a day. How many days for all the walls on '1. Level'?", walls_len / 12.5),
    (W, "How many square metres of room area are there per door on '1. Level'?", area1 / doors1),
    (G, "Each door weighs 35 kg. What is the total weight of all doors in the building?", g_doors * 35),
    (G, "If each door costs PLN 1 899, what do all doors in the building cost?", g_doors * 1899),
    (G, "If replacing a door takes 90 minutes, how many minutes does it take to replace every door in the building?",
     g_doors * 90),
]
ok = 0
for p, q, gold in CASES:
    a = S.solve(p, q)
    try:
        good = abs(float(a.value) - gold) <= 0.02 * abs(gold) + 1e-6
    except (TypeError, ValueError):
        good = False
    ok += good
    print(f"{'OK ' if good else 'BAD'} [{a.confidence:.2f}] {a.value!s:>12} {a.unit or ''} (gold {gold:g}) <- {q}")
print(f"{ok}/{len(CASES)}")
