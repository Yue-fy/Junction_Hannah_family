"""Open wording probe for the most common Swiss question kinds (F 08:25, after the 'B apartment in m²' → apartment 'IN'
confident-wrong). Bases: dev Swiss English questions of four templates (one base per drawing and kind); each is
re-asked in natural English wordings a judge might type, with the SAME gold. Wordings that drop an exclusion the
dataset's definition relies on are tagged ambiguous. OPEN probe (dev drawings): fine to read, quote and fix against.

    python experiments/F/apt_wording_probe.py [N_PER_KIND]   # -> $JUNCTION_SHARED/artifacts/F/apt_wording.jsonl
    python -m stoa.eval --solver pipeline --split $JUNCTION_SHARED/artifacts/F/apt_wording.jsonl
"""
from __future__ import annotations

import collections
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


# v7 (c225, 08:45): CubiCasa casual Finnish / English wordings (the LoRA was trained on the dataset's long wordings;
# does a judge's wording still reach it?). Base = the EN or FI dataset template of the same concept and drawing.
def _either(en, fi):
    return r"^(?:" + re.escape(en) + "|" + re.escape(fi) + r")$"


KINDS_CC = {
    "cc7_windows": (_either("How many windows are shown on this floor plan?", "Kuinka monta ikkunaa pohjapiirustuksessa on?"), {
        "fi_asunto": ("Montako ikkunaa asunnossa on?", False),
        "fi_plan": ("Montako ikkunaa tässä pohjapiirroksessa on?", False),
        "fi_laske": ("Laske ikkunat.", False),
        "en_plain": ("How many windows are there?", False),
    }),
    "cc7_wc": (_either("How many toilet bowls (WC seats) are drawn on this floor plan?",
                       "Kuinka monta WC-istuinta pohjapiirustukseen on piirretty?"), {
        "fi_asunto": ("Montako WC-istuinta tässä asunnossa on?", False),
        "fi_pontto": ("Kuinka monta wc-pönttöä piirustuksessa on?", False),
        "en_toilets_plan": ("How many toilets are drawn on the plan?", False),
    }),
    "cc7_floors": (_either("How many floors (storeys) does this floor plan show?",
                           "Kuinka monta kerrosta pohjapiirustuksessa on esitetty?"), {
        "en_storeys_home": ("How many storeys does this home have?", False),
        "en_levels": ("How many levels are shown?", False),
        "fi_asunto": ("Montako kerrosta asunnossa on?", False),
        "en_floors_plain": ("How many floors?", False),
    }),
    "cc7_showers": (_either("How many showers and bathtubs are drawn on this floor plan in total?",
                            "Kuinka monta suihkua ja kylpyammetta pohjapiirustukseen on piirretty yhteensä?"), {
        "en_plus": ("How many showers plus bathtubs are there?", False),
        "en_together": ("Count the showers and bathtubs together.", False),
        "fi_yhteensa": ("Montako suihkua ja ammetta asunnossa on yhteensä?", False),
    }),
    "cc7_sinks": (_either("How many sinks and wash basins (kitchen and bathroom combined; a double-bowl sink counts as one) "
                          "are drawn on this floor plan?",
                          "Kuinka monta pesu- ja tiskiallasta (keittiö ja kylpytilat yhteensä; kaksoisallas lasketaan "
                          "yhdeksi) pohjapiirustukseen on piirretty?"), {
        "en_total": ("How many sinks are there in total, kitchen and bathroom together?", False),
        "fi_altaat": ("Montako allasta asunnossa on keittiössä ja kylpyhuoneessa yhteensä?", False),
    }),
    "cc7_saunas": (_either("How many saunas are on this floor plan?", "Kuinka monta saunaa pohjapiirustuksessa on?"), {
        "fi_asunto": ("Montako saunaa asunnossa on?", False),
        "en_plain": ("How many saunas are there?", False),
    }),
    "cc7_doors": (_either("How many doors are shown on this floor plan? Count doorways fitted with a door; open doorways "
                          "without a door leaf do not count.",
                          "Kuinka monta ovea pohjapiirustuksessa on? Laske oviaukot, joissa on ovi; pelkkiä oviaukkoja "
                          "ilman ovilehteä ei lasketa."), {
        "en_plain": ("How many doors are there?", False),
        "fi_asunto": ("Montako ovea asunnossa on?", False),
    }),
    "cc7_kitchens": (_either("How many kitchens (including kitchenettes, open kitchens and utility kitchens) are on this "
                             "floor plan?",
                             "Kuinka monta keittiötä (myös keittokomerot, avo- ja tupakeittiöt sekä apukeittiöt) "
                             "pohjapiirustuksessa on?"), {
        "en_short": ("How many kitchens are there, kitchenettes included?", False),
        "fi_asunto": ("Montako keittiötä asunnossa on?", True),
    }),
    "cc7_bedrooms": (_either("How many bedrooms (makuuhuone, usually marked MH) are on this floor plan?",
                             "Kuinka monta makuuhuonetta (MH) pohjapiirustuksessa on?"), {
        "fi_asunto": ("Montako makuuhuonetta asunnossa on?", False),
        "en_home": ("How many bedrooms does this home have?", False),
    }),
    "cc7_bathrooms": (_either("How many bathrooms or washrooms (e.g. KH, KPH, PH, PESUH, SH) are on this floor plan, not "
                              "counting separate WC rooms?",
                              "Kuinka monta kylpy- tai pesuhuonetta (esim. KH, KPH, PH, PESUH, SH) pohjapiirustuksessa on, "
                              "erillisiä WC-tiloja lukuun ottamatta?"), {
        "en_short": ("How many bathrooms are there (not counting separate toilets)?", False),
        "fi_asunto": ("Montako kylpyhuonetta asunnossa on, erillisiä vessoja lukuun ottamatta?", False),
    }),
}


# v8 (c225, 08:50): IFC wordings in languages a Nordic/Baltic/central-European judge might type (dataset IFC
# templates are English and Dutch). Up to 4 bases per model (distinct rooms/storeys).
_IFC_ROOM_ANY = (r"^(?:What is the net floor area of the room|Wat is de netto vloeroppervlakte van de ruimte) "
                 r"'(?P<R>[^']+)' (?:on|op) '(?P<S>[^']+)', in m²\?$")
_IFC_COUNT_EN = r"^How many (?P<K>walls|doors|windows|rooms \(spaces\)) are shown on the floor plan of '(?P<S>[^']+)'\?$"
_NOUNS = {"de": {"walls": "Wände", "doors": "Türen", "windows": "Fenster", "rooms": "Räume"},
          "fi": {"walls": "seinää", "doors": "ovea", "windows": "ikkunaa", "rooms": "huonetta"},
          "nl": {"walls": "muren", "doors": "deuren", "windows": "ramen", "rooms": "ruimtes"},
          "et": {"walls": "seina", "doors": "ust", "windows": "akent", "rooms": "ruumi"},
          "sv": {"walls": "väggar", "doors": "dörrar", "windows": "fönster", "rooms": "rum"}}
KINDS_IFC = {
    "ifc8_room": (_IFC_ROOM_ANY, {
        "de": ("Wie groß ist der Raum '{R}' im Geschoss '{S}'?", False),
        "fi": ("Mikä on tilan '{R}' pinta-ala kerroksessa '{S}'?", False),
        "et": ("Kui suur on ruum '{R}' korrusel '{S}'?", False),
        "sv": ("Hur stor är rummet '{R}' på våning '{S}'?", False),
        "fr": ("Quelle est la surface de la pièce '{R}' au niveau '{S}' ?", False),
        "nl_casual": ("Hoe groot is de ruimte '{R}' op '{S}'?", False),
        "en_sqm": ("How many square metres is the room '{R}' on '{S}'?", False),
    }),
    "ifc8_count": (_IFC_COUNT_EN, {
        "de": ("Wie viele {N_de} gibt es im Geschoss '{S}'?", False),
        "fi": ("Montako {N_fi} kerroksessa '{S}' on?", False),
        "nl": ("Hoeveel {N_nl} zijn er op '{S}'?", False),
        "et": ("Mitu {N_et} on korrusel '{S}'?", False),
        "sv": ("Hur många {N_sv} finns det på våning '{S}'?", False),
    }),
}


# v9 (c225, 08:50): Swiss room / label / fixture questions in German, French and Italian (bases: English dev templates).
_ROOM_EN = r"^What is the net floor area of room (?P<N>\d+\.\d+) \('(?P<S>[^']+)'\) in m²\?$"
KINDS_ML2 = {
    "ml_room": (_ROOM_EN, {
        "de_raum": ("Wie groß ist Raum {N}?", False),
        "de_zimmer_label": ("Fläche von Zimmer {N} ({S}) in m²?", False),
        "fr_piece": ("Quelle est la surface de la pièce {N} ?", False),
        "fr_local": ("Surface du local {N} en m² ?", False),
        "it_locale": ("Quanto è grande il locale {N}?", False),
    }),
    "ml_count_label": (r"^How many rooms labelled '(?P<S>[^']+)' are there on this floor\?$", {
        "de_heissen": ("Wie viele Räume heißen '{S}'?", False),
        "de_anzahl": ("Anzahl der Räume mit der Bezeichnung {S}?", False),
        "fr_nommees": ("Combien de pièces sont nommées '{S}' ?", False),
        "it_chiamano": ("Quanti locali si chiamano '{S}'?", False),
    }),
    "ml_area_label": (r"^What is the total net area in m² of all rooms labelled '(?P<S>[^']+)' on this floor\?$", {
        "de_gesamt": ("Gesamtfläche aller Räume '{S}' in m²?", False),
        "de_zusammen": ("Wie viel Fläche haben alle '{S}' zusammen?", False),
        "fr_totale": ("Surface totale des pièces '{S}' ?", False),
        "it_totale": ("Superficie totale dei locali '{S}'?", False),
    }),
    "ml_doors": (r"^How many doors \(interior doors and entrance doors together\) are drawn on this floor plan\?$", {
        "de": ("Wie viele Türen hat dieses Geschoss?", False),
        "fr": ("Combien de portes y a-t-il sur ce plan ?", False),
        "it": ("Quante porte ci sono in questa pianta?", False),
    }),
    "ml_windows": (r"^How many windows are drawn on this floor plan\?$", {
        "de": ("Wie viele Fenster sind eingezeichnet?", False),
        "fr": ("Combien de fenêtres sur ce plan ?", False),
        "it": ("Quante finestre ci sono?", False),
    }),
    "ml_washbasins": (r"^How many washbasins are drawn on this floor plan\?$", {
        "de_lavabo": ("Wie viele Lavabos gibt es auf diesem Plan?", False),
        "de_waschbecken": ("Anzahl Waschbecken?", False),
        "fr": ("Combien de lavabos ?", False),
        "it": ("Quanti lavabi ci sono?", False),
    }),
    "ml_bathtubs": (r"^How many bathtubs are drawn on this floor plan\?$", {
        "de": ("Wie viele Badewannen?", False),
        "fr": ("Combien de baignoires ?", False),
        "it": ("Quante vasche da bagno?", False),
    }),
}


# v12 (c225, 09:10): Swiss fixture synonyms in English (bases: EN/DE/FR dataset templates of the same drawing).
def _any(*qs):
    return r"^(?:" + "|".join(re.escape(q) for q in qs) + r")$"


KINDS_SYN = {
    "syn_wc": (_any("How many toilets (WC) are drawn on this floor plan?", "Wie viele WCs sind auf diesem Grundriss eingezeichnet?",
                    "Combien de WC sont dessinés sur ce plan ?"), {
        "wcs": ("How many WCs are there on this floor?", False),
        "toilet_bowls": ("How many toilet bowls does this plan show?", False),
        "loos": ("How many loos are on this floor?", False),
        "water_closets": ("How many water closets are drawn?", False),
        "toilet_seats": ("Count the toilet seats.", False),
    }),
    "syn_shower": (_any("How many showers are drawn on this floor plan?"), {
        "trays": ("How many shower trays are on this floor?", False),
        "have": ("How many showers does this floor have?", False),
        "cubicles": ("Number of shower cubicles on the plan?", False),
    }),
    "syn_bathtub": (_any("How many bathtubs are drawn on this floor plan?", "Wie viele Badewannen sind auf diesem Grundriss eingezeichnet?",
                         "Combien de baignoires sont dessinées sur ce plan ?"), {
        "tubs": ("How many tubs are there?", False),
        "bath_tubs": ("How many bath tubs are drawn on this plan?", False),
    }),
    "syn_washbasin": (_any("How many washbasins are drawn on this floor plan?", "Wie viele Lavabos sind auf diesem Grundriss eingezeichnet?",
                           "Combien de lavabos sont dessinés sur ce plan ?"), {
        "hand_basins": ("How many hand basins are on this floor?", False),
        "lavabos": ("How many lavabos are on this plan?", False),
        "wash_hand_basins": ("Count the wash-hand basins.", False),
    }),
    "syn_window": (_any("How many windows are drawn on this floor plan?", "Wie viele Fenster sind auf diesem Grundriss eingezeichnet?",
                        "Combien de fenêtres sont dessinées sur ce plan ?"), {
        "glazed": ("How many windows are there in the exterior walls of this floor?", False),
        "count": ("Window count for this floor?", False),
    }),
}


# v13 (c225, 09:12): quick-typing wordings (lower-case ids/labels, common misspellings, no punctuation).
KINDS_TYPO = {
    "typo_apt": (r"^What is the net floor area of apartment (?P<L>[A-Z]) in m², summing all its rooms except balconies", {
        "lower_id": ("what is the net floor area of apartment {l} without balconies", False),
        "appartment": ("What is the net floor area of appartment {L}, excluding balconies?", False),
        "apartmnet": ("net floor area of apartmnet {L} excluding balconies?", False),
        "flat_lower": ("how big is flat {l} without the balcony", False),
        "caps": ("WHAT IS THE NET FLOOR AREA OF APARTMENT {L} EXCLUDING BALCONIES?", False),
        "squ_meters": ("apartment {L} net area in sq m (no balconies)", False),
    }),
    "typo_room": (r"^What is the net floor area of room (?P<N>\d+\.\d+) \('(?P<S>[^']+)'\) in m²\?$", {
        "lower_label": ("area of the {s} room {N}?", False),
        "comma_no": ("what is the area of room {Nc}", False),
        "roon": ("How big is roon {N}?", False),
    }),
    "typo_count_label": (r"^How many rooms labelled '(?P<S>[^']+)' are there on this floor\?$", {
        "lower_label": ("how many {s} rooms are there", False),
        "labeled_us": ("How many rooms labeled '{S}' are on this floor?", False),
        "quoted_lower": ("how many rooms are labelled '{s}'", False),
    }),
    "typo_doors": (r"^How many doors \(interior doors and entrance doors together\) are drawn on this floor plan\?$", {
        "dors": ("how many dors are on this floor", False),
        "no_q": ("number of doors on this plan", False),
    }),
}


def main():
    ml = "--ml" in sys.argv
    cc = "--cc" in sys.argv
    ifc8 = "--ifc" in sys.argv
    ml2 = "--ml2" in sys.argv
    syn = "--syn" in sys.argv
    typo = "--typo" in sys.argv
    argv = [a for a in sys.argv[1:] if a not in ("--ml", "--cc", "--ifc", "--ml2", "--syn", "--typo")]
    n = int(argv[0]) if argv else 30
    dev_all = load_split("dev")
    out = os.path.join(os.environ["JUNCTION_SHARED"], "artifacts", "F",
                       "apt_wording_ml.jsonl" if ml else "apt_wording_cc.jsonl" if cc else
                       "apt_wording_ifc.jsonl" if ifc8 else "apt_wording_ml2.jsonl" if ml2 else
                       "apt_wording_syn.jsonl" if syn else
                       "apt_wording_typo.jsonl" if typo else "apt_wording.jsonl")
    total = 0
    with open(out, "w", encoding="utf-8") as f:
        for kind, (rx, wordings) in (KINDS_ML if ml else KINDS_CC if cc else KINDS_IFC if ifc8 else KINDS_ML2 if ml2 else KINDS_SYN if syn else KINDS_TYPO if typo else KINDS).items():
            bases, seen = [], collections.Counter()
            per_path = 4 if kind.startswith("ifc8") else 1
            source = ("ifc_models" if kind.startswith("ifc") else "cubicasa5k" if kind.startswith("cc")
                      else "swiss_dwellings")
            for q in dev_all:
                m = re.match(rx, q.question) if q.source == source else None
                if m and seen[q.path] < per_path:
                    seen[q.path] += 1
                    g = m.groupdict()
                    if "K" in g:
                        g["N"] = g["K"].replace(" (spaces)", "")
                        g.update({f"N_{lang}": nouns[g["N"]] for lang, nouns in _NOUNS.items()})
                    if "L" in g:
                        g["l"] = g["L"].lower()
                    if "S" in g:
                        g["s"] = g["S"].lower()
                    if "N" in g and "." in g["N"]:
                        g["Nc"] = g["N"].replace(".", ",")
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
