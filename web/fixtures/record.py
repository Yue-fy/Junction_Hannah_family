"""Record real answers from the running API for the demo questions, so the mock can replay them offline.

    $JUNCTION_VENV/bin/python web/fixtures/record.py [--api http://127.0.0.1:8100]

Writes web/fixtures/recorded.json ([{path, question, answer, recorded_at, api}]). The mock API
(web/mock/stoaApi.ts) prefers these over fixtures/answers.json. Re-run after solvers improve. Entries with
"pinned": true are kept (not overwritten).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent

# The demo tour's questions (web/fixtures/tour.json, also read by src/main.ts) plus a few extra ones the card or the
# README shows.
TOUR = json.loads((HERE / "tour.json").read_text())
EXTRA = [
    ("data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf",
     "What share of the total room area on '1.korrus' does the room 'KORIDOR (119)' take, in percent?"),
    ("data/swiss_dwellings/site1000_bldg2082_floor9385.pdf", "How many rooms labelled 'Zimmer' are there on this floor?"),
    # scans: answered from the printed text (raster text layer), the cited line boxed
    ("data/habs/vi0026_sheet_00003.jpg", "What is the title of this sheet?"),
    ("data/habs/vi0026_sheet_00003.jpg", "What is the scale of this drawing?"),
    ("data/habs/vi0026_sheet_00003.jpg", "When was this drawing made?"),
]
QUESTIONS = [(t["file"], t["q"]) for t in TOUR if t.get("file") and t.get("q")] + EXTRA


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
    ap.add_argument("--no-write", action="store_true",
                    help="only ask (warms the API's answer cache before a demo, web/demo.sh); recorded.json unchanged")
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
    if args.no_write:
        return
    # entries marked "pinned": true (a known-good answer kept on purpose, e.g. when a regression is being fixed) stay
    # as they are and replace the fresh recording of the same (path, question, solver)
    try:
        old = json.loads((HERE / "recorded.json").read_text())
    except (OSError, ValueError):
        old = []
    key = lambda r: (r["path"], r["question"], r.get("solver"))  # noqa: E731
    pinned = {key(r): r for r in old if r.get("pinned")}
    out = [pinned.pop(key(r), r) for r in out] + list(pinned.values())
    # an empty fresh answer (a hosted model rate-limited, a timeout) never replaces an earlier recording that had a value
    prev = {key(r): r for r in old if r.get("answer", {}).get("value") is not None}
    for i, r in enumerate(out):
        if r["answer"].get("value") is None and key(r) in prev:
            print(f"kept previous (fresh answer empty): {r['path'].split('/')[-1][:40]} {r.get('solver') or ''}")
            out[i] = prev[key(r)]
    for r in out:
        if r.get("pinned"):
            print(f"kept pinned: {r['path'].split('/')[-1][:40]} {r['question'][:50]} ({r.get('recorded_at')})")
    (HERE / "recorded.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    record_rooms()


def record_rooms() -> None:
    """Room graphs (R1's experiments/r1/room_graph, from the cached CubiCasa5K segmentation) of the tour's "rooms" steps
    -> fixtures/rooms.json, so the "Rooms & doors" overlay also works where the middleware cannot run Python."""
    paths = sorted({t["file"] for t in TOUR if t.get("rooms") and t.get("file")})
    if not paths:
        return
    sys.path.insert(0, str(HERE.parents[1]))
    try:
        from experiments.r1.room_graph.graph import room_graph
    except ImportError as e:
        print(f"room graphs not recorded ({e})")
        return
    out = {}
    for p in paths:
        g = room_graph(p, live=False)
        if g:
            out[p] = g
            print(f"rooms: {p.split('/')[-1]} {len(g['rooms'])} rooms, {len(g['doors'])} doors")
    if out:
        (HERE / "rooms.json").write_text(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
