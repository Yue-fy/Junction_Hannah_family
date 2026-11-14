"""Open wording probe for the most common Swiss question kinds (F 08:25, after the 'B apartment in m²' → apartment 'IN'
confident-wrong). Bases: dev Swiss English questions of four templates (one base per drawing and kind); each is
re-asked in natural English wordings a judge might type, with the SAME gold. Wordings that drop an exclusion the
dataset's definition relies on are tagged ambiguous. OPEN probe (dev drawings): fine to read, quote and fix against.

    python experiments/F/apt_wording_probe.py [N_PER_KIND]   # -> $JUNCTION_SHARED/artifacts/F/apt_wording.jsonl
    python -m stoa.eval --solver pipeline --split $JUNCTION_SHARED/artifacts/F/apt_wording.jsonl
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sys

from stoa.eval.splits import load_split

KINDS = {
    # kind: (base regex on the dev question, {wording: (template, ambiguous)})
    "apt": (r"^What is the net floor area of apartment (?P<L>[A-Z]) in m², summing all its rooms except balconies", {
        "letter_first_in_m2": ("What is the net floor area of {L} apartment in m², excluding balconies and terraces?", False),
        "the_letter_first": ("What is the net floor area of the {L} apartment, without balconies?", False),
        "flat": ("What is the net floor area of flat {L} in m², excluding balconies, loggias and terraces?", False),
        "unit": ("What is the net floor area of unit {L} in square metres, excluding balconies?", False),
        "quoted": ("What is the net floor area of apartment '{L}' (all rooms, no balconies or terraces)?", False),
        "hyphen": ("What is the net area of apartment-{L} in m2, excluding outdoor spaces?", False),
        "abbrev": ("Net floor area of apt. {L} in m², excluding balconies?", False),
        "fronted": ("Apartment {L}: what is its net floor area in m², balconies excluded?", False),
        "how_big_flat": ("How big is flat {L}?", True),
        "sqm_apartment": ("How many square meters is apartment {L}?", True),
    }),
    "room": (r"^What is the net floor area of room (?P<N>\d+\.\d+) \('(?P<S>[^']+)'\) in m²\?$", {
        "how_big": ("How big is room {N}?", False),
        "no": ("What's the area of room no. {N}?", False),
        "space": ("Area of space {N} in square meters?", False),
        "numbered": ("What is the floor area of the room numbered {N} ({S})?", False),
        "label_first": ("How large is the {S} (room {N})?", False),
        "dash": ("Room {N} - how many m²?", False),
        "hash": ("What is the size of room #{N}?", False),
        "terse": ("Give me the area of {N} {S}.", False),
    }),
    "count_label": (r"^How many rooms labelled '(?P<S>[^']+)' are there on this floor\?$", {
        "adj": ("How many {S} rooms are on this floor?", False),
        "called": ("How many rooms are called {S}?", False),
        "imperative": ("Count the rooms named '{S}'.", False),
        "bare": ("How many '{S}' are there on this plan?", False),
        "number_of": ("Number of rooms with the label {S} on this floor plan?", False),
    }),
    "area_label": (r"^What is the total net area in m² of all rooms labelled '(?P<S>[^']+)' on this floor\?$", {
        "combined": ("What is the combined area of all {S} rooms?", False),
        "sum": ("Sum the floor areas of the rooms named '{S}'.", False),
        "sqm_of": ("How many square metres of {S} are there on this floor?", False),
        "every": ("Total area of every '{S}' in m²?", False),
    }),
    # Swiss counts (08:25): the dataset's long wordings vs what a judge types
    "doors": (r"^How many doors \(interior doors and entrance doors together\) are drawn on this floor plan\?$", {
        "plain": ("How many doors are there on this floor?", False),
        "total": ("What is the total number of doors in this plan?", False),
        "count_imp": ("Count all the doors on this drawing.", False),
        "incl": ("How many doors does this floor have, including the apartment entrance doors?", False),
    }),
    "washbasins": (r"^How many washbasins are drawn on this floor plan\?$", {
        "sinks": ("How many bathroom sinks are on this floor?", False),
        "wash_basins": ("How many wash basins does this plan show?", False),
        "number": ("Number of washbasins on the floor plan?", False),
    }),
    "bathtubs": (r"^How many bathtubs are drawn on this floor plan\?$", {
        "baths": ("How many baths are on this floor?", True),
        "tubs": ("How many bath tubs can you see in this plan?", False),
        "count_imp": ("Count the bathtubs on this drawing.", False),
    }),
    "apartments": (r"^How many apartments \(residential units\) are shown on this floor plan\?$", {
        "flats": ("How many flats are on this floor?", False),
        "units": ("How many residential units does this floor have?", False),
        "dwellings": ("How many dwellings are there on this level?", False),
        "number": ("Number of apartments on this floor plan?", False),
    }),
    "windows": (r"^How many windows are drawn on this floor plan\?$", {
        "plain": ("How many windows does this floor have?", False),
        "total": ("What is the total window count on this plan?", False),
        "count_imp": ("Count the windows in this drawing.", False),
    }),
}


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    dev = [q for q in load_split("dev") if q.source == "swiss_dwellings"]
    out = os.path.join(os.environ["JUNCTION_SHARED"], "artifacts", "F", "apt_wording.jsonl")
    total = 0
    with open(out, "w", encoding="utf-8") as f:
        for kind, (rx, wordings) in KINDS.items():
            bases, seen = [], set()
            for q in dev:
                m = re.match(rx, q.question)
                if m and q.path not in seen:
                    seen.add(q.path)
                    bases.append((q, m.groupdict()))
            random.Random(7).shuffle(bases)
            for q, g in bases[:n]:
                for name, (tpl, amb) in wordings.items():
                    qid = "aw" + hashlib.sha1(f"{q.qid}|{kind}|{name}".encode()).hexdigest()[:10]
                    f.write(json.dumps({"qid": qid, "path": q.path, "question": tpl.format(**g), "answer": q.answer,
                                        "unit": q.unit, "type": q.type,
                                        "meta": {"kind": f"{kind}:{name}", "wording": name, "probe_kind": kind,
                                                 "ambiguous": amb, "base_qid": q.qid}}, ensure_ascii=False) + "\n")
                    total += 1
            print(f"{kind}: {min(n, len(bases))} bases x {len(wordings)} wordings")
    print(f"{total} rows -> {out}")


if __name__ == "__main__":
    main()
