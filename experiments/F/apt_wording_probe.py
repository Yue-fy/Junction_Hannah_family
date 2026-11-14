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
    # CubiCasa (08:32): the LoRA was trained on these exact wordings; does a judge's wording still reach it?
    "cc_wc": (r"^How many toilet bowls \(WC seats\) are drawn on this floor plan\?$", {
        "toilets": ("How many toilets are there in this apartment?", False),
        "count_imp": ("Count the WC seats on this plan.", False),
        "number": ("What is the number of toilet bowls in this floor plan?", False),
    }),
    "cc_windows": (r"^How many windows are shown on this floor plan\?$", {
        "apartment": ("How many windows does this apartment have?", False),
        "count_imp": ("Count the windows.", False),
        "number": ("What's the number of windows in this plan?", False),
    }),
    "cc_saunas": (r"^How many saunas are on this floor plan\?$", {
        "is_there": ("Is there a sauna, and if so how many?", True),
        "apartment": ("How many saunas does this flat have?", False),
        "number": ("Number of saunas on the plan?", False),
    }),
    "cc_bedrooms": (r"^How many bedrooms \(makuuhuone, usually marked MH\) are on this floor plan\?$", {
        "plain": ("How many bedrooms are there?", False),
        "apartment": ("How many bedrooms does this apartment have?", False),
        "number": ("What is the number of bedrooms on this floor plan?", False),
    }),
    # IFC (08:33): room by name + storey, per-storey counts and totals
    "ifc_room": (r"^What is the net floor area of the room '(?P<R>[^']+)' on '(?P<S>[^']+)', in m²\?$", {
        "unquoted": ("What is the area of {R} on {S}?", False),
        "room_storey": ("What's the floor area of the '{R}' room on the '{S}' storey?", False),
        "fronted": ("Room '{R}' ({S}): area in square metres?", False),
        "called": ("On {S}, how large is the room called {R}?", False),
        "space_level": ("Give me the net area of space '{R}' on level '{S}'.", False),
        "no_storey": ("How big is room '{R}'?", True),
    }),
    "ifc_count": (r"^How many (?P<K>walls|doors|windows|rooms \(spaces\)) are shown on the floor plan of '(?P<S>[^']+)'\?$", {
        "on": ("How many {N} are on {S}?", False),
        "number_storey": ("Number of {N} on storey '{S}'?", False),
        "count_level": ("Count the {N} on level {S}.", False),
        "there": ("How many {N} are there on the '{S}' floor?", False),
    }),
    "ifc_room_total": (r"^What is the total net floor area of all rooms \(spaces\) on '(?P<S>[^']+)', in m²\?$", {
        "combined": ("What is the combined room area on {S}?", False),
        "sum": ("Sum of all room areas on storey '{S}' in m²?", False),
        "how_much": ("How much net floor area do the rooms on '{S}' have?", False),
    }),
    "ifc_wall_side": (r"^What is the total net side area of all walls on '(?P<S>[^']+)', in m²\?$", {
        "surface": ("How much wall surface (net side area) is there on {S}?", False),
        "sum": ("Total net side area of the walls on storey '{S}'?", False),
    }),
    "ifc_slab_vol": (r"^What is the total net volume of all slabs on '(?P<S>[^']+)', in m³\?$", {
        "how_much": ("How much slab volume is on {S}, in cubic metres?", False),
        "sum": ("Total volume of the slabs on level '{S}'?", False),
    }),
}


# v6 (c225, 08:45): German / French / Italian wordings a Swiss judge might type. The base is any dataset-language
# apartment template of the same drawing (gold is language-independent). Written to apt_wording_ml.jsonl (`--ml`).
_APT_ANY = (r"^(?:What is the net floor area of apartment|Wie gross ist die Nettowohnfläche von Wohnung|"
            r"Quelle est la surface nette de l'appartement|Qual è la superficie netta dell'appartamento) "
            r"(?P<L>[A-Z]) in m²")
_APTS_ANY = (r"^(?:How many apartments \(residential units\) are shown on this floor plan\?|"
             r"Wie viele Wohnungen sind auf diesem Grundriss dargestellt\?|"
             r"Combien d'appartements \(logements\) figurent sur ce plan d'étage \?)$")
KINDS_ML = {
    "de_apt": (_APT_ANY, {
        "gross_ohne": ("Wie groß ist Wohnung {L} ohne Balkone?", False),
        "whg": ("Nettofläche Whg. {L} in m², ohne Balkon und Loggia?", False),
        "qm": ("Wie viele Quadratmeter hat die Wohnung {L}, Balkone und Terrassen nicht mitgerechnet?", False),
        "fronted": ("Wohnung {L}: Nettowohnfläche in m² ohne Aussenräume?", False),
        "letter_first": ("Welche Wohnfläche hat die {L}-Wohnung (ohne Balkon)?", False),
        "einheit": ("Wie groß ist die Nettofläche der Wohneinheit {L} exkl. Balkone?", False),
        "bare": ("Wie groß ist Wohnung {L}?", True),
    }),
    "fr_apt": (_APT_ANY, {
        "sans": ("Quelle est la surface de l'appartement {L}, sans les balcons ?", False),
        "logement": ("Surface nette du logement {L} en m², hors balcons ?", False),
        "m2": ("Combien de mètres carrés fait l'appartement {L} (hors balcons et terrasses) ?", False),
        "fronted": ("Appartement {L} : surface habitable nette en m², balcons exclus ?", False),
        "appt": ("Quelle est la superficie de l'appt {L} hors espaces extérieurs ?", False),
    }),
    "it_apt": (_APT_ANY, {
        "grande": ("Quanto è grande l'appartamento {L}, esclusi i balconi?", False),
        "alloggio": ("Superficie netta dell'alloggio {L} in m² (senza balconi)?", False),
        "mq": ("Quanti metri quadrati ha l'appartamento {L}, terrazze escluse?", False),
        "fronted": ("Appartamento {L}: superficie netta in m², senza spazi esterni?", False),
    }),
    "ml_apartments": (_APTS_ANY, {
        "de_einheiten": ("Wie viele Wohneinheiten hat dieses Geschoss?", False),
        "de_anzahl": ("Anzahl Wohnungen auf diesem Plan?", False),
        "fr_logements": ("Combien de logements y a-t-il à cet étage ?", False),
        "fr_nombre": ("Nombre d'appartements sur ce plan ?", False),
        "it_quanti": ("Quanti appartamenti ci sono su questo piano?", False),
        "en_how_many_units": ("How many units are on this floor?", False),
    }),
}


def main():
    ml = "--ml" in sys.argv
    argv = [a for a in sys.argv[1:] if a != "--ml"]
    n = int(argv[0]) if argv else 30
    dev_all = load_split("dev")
    out = os.path.join(os.environ["JUNCTION_SHARED"], "artifacts", "F",
                       "apt_wording_ml.jsonl" if ml else "apt_wording.jsonl")
    total = 0
    with open(out, "w", encoding="utf-8") as f:
        for kind, (rx, wordings) in (KINDS_ML if ml else KINDS).items():
            bases, seen = [], set()
            source = ("ifc_models" if kind.startswith("ifc_") else "cubicasa5k" if kind.startswith("cc_")
                      else "swiss_dwellings")
            for q in dev_all:
                m = re.match(rx, q.question) if q.source == source else None
                if m and q.path not in seen:
                    seen.add(q.path)
                    g = m.groupdict()
                    if "K" in g:
                        g["N"] = g["K"].replace(" (spaces)", "")
                    bases.append((q, g))
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
