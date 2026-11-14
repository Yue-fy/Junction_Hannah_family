"""Record real answers from the running API for the demo questions, so the mock can replay them offline.

    $JUNCTION_VENV/bin/python web/fixtures/record.py [--api http://127.0.0.1:8100]

Writes web/fixtures/recorded.json ([{path, question, answer, recorded_at, api}]). The mock API
(web/mock/stoaApi.ts) prefers these over fixtures/answers.json. Re-run after solvers improve.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent

# Keep in sync with TOUR in web/src/main.ts (plus the hand-computed fixtures).
QUESTIONS = [
    ("data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf",
     "What is the net floor area of the room 'KORIDOR (119)' on '1.korrus', in m²?"),
    ("data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf",
     "How many doors are shown on the floor plan of '1.korrus'?"),
    ("data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf",
     "How many windows are shown on the floor plan of '1.korrus'?"),
    ("data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf",
     "How many doors are there in the model 'Maleva tänav 18 korterelamu (Esplanades example model)'?"),
    ("data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf",
     "What share of the total room area on '1.korrus' does the room 'KORIDOR (119)' take, in percent?"),
    ("data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf",
     "If each door costs 450 euros, what do all the doors on '1.korrus' cost in total?"),
    ("data/ifc_bench/4351_arc.ifc", "What plumbing fixtures are in this building and their respective counts?"),
    ("data/swiss_dwellings/site1000_bldg2082_floor9385.pdf",
     "How many doors (interior doors and entrance doors together) are drawn on this floor plan?"),
    ("data/swiss_dwellings/site1000_bldg2082_floor9385.pdf",
     "How many rooms labelled 'Zimmer' are there on this floor?"),
    ("data/swiss_dwellings/site1000_bldg2082_floor9385.pdf",
     "Wie viele Türen und Fenster sind insgesamt auf diesem Grundriss eingezeichnet?"),
    ("data/cubicasa5k/colorful-4539.png",
     "Kuinka monta makuuhuonetta (MH) pohjapiirustuksessa on?"),
    ("data/cubicasa5k/high_quality_architectural-14797.png", "How many saunas are on this floor plan?"),
    ("data/habs/vi0026_sheet_00003.jpg",
     "What kind of drawing is this (floor plan, elevation, section, site plan)?"),
]


# On-demand second opinions (hosted NVIDIA Nemotron) the tour may click: (path, question).
SECOND = [
    ("data/cubicasa5k/colorful-4539.png", "Kuinka monta makuuhuonetta (MH) pohjapiirustuksessa on?"),
    ("data/habs/vi0026_sheet_00003.jpg",
     "What kind of drawing is this (floor plan, elevation, section, site plan)?"),
]
SECOND_SOLVER = ("vlm_direct", {"backend": "nvidia"})
# "Show where" on CubiCasa answers without evidence (web/src/card.ts locatorFor): room counts → the label reader
# (raster), symbol counts → R1's pretrained CubiCasa5K detector (raster_cc5k, cached). (path, question, solver)
LOCATE = [("data/cubicasa5k/colorful-4539.png", "Kuinka monta makuuhuonetta (MH) pohjapiirustuksessa on?", "raster"),
          ("data/cubicasa5k/high_quality_architectural-14797.png", "How many saunas are on this floor plan?", "raster"),
          ("data/cubicasa5k/high_quality_architectural-816.png", "How many doors are shown on this floor plan?", "raster_cc5k")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8100")
    args = ap.parse_args()
    out = []
    jobs = ([(p, q, None) for p, q in QUESTIONS] + [(p, q, SECOND_SOLVER) for p, q in SECOND]
            + [(p, q, (solver, {})) for p, q, solver in LOCATE])
    for path, q, solver in jobs:
        body = {"path": path, "question": q}
        if solver:
            body.update(solver=solver[0], **({"solver_args": solver[1]} if solver[1] else {}))
        req = urllib.request.Request(f"{args.api}/ask", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            ans = json.load(r)
        ans.pop("cached", None)
        rec = {"path": path, "question": q, "answer": ans, "recorded_at": time.strftime("%Y-%m-%d %H:%M"),
               "api": args.api}
        if solver:
            rec.update(solver=solver[0], **({"solver_args": solver[1]} if solver[1] else {}))
        out.append(rec)
        print(f"{path.split('/')[-1][:48]:48} {ans.get('value')!s:>10} {ans.get('unit')} conf={ans.get('confidence')} "
              f"{ans.get('solver')} ev={len(ans.get('evidence', []))}")
    (HERE / "recorded.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
