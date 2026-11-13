"""Generate `hard2p`: the `hard2` questions reworded (other English phrasing, German/French for swiss, German for
ifc, Finnish for cubicasa). Same drawings, same answers.

Why: solvers were fixed while looking at `hard2` failures (W2's dxf v5 went 47.6% -> 96.7% at 00:53). `hard2p`
checks whether those fixes are general (operators understood) or keyword-matched (overfit to hard2 wording).
Use `hard2` for development; treat `hard2p` as held out: look at aggregates, not at individual failures.

Run:  python -m stoa.eval.hard2p --write -> $JUNCTION_SHARED/results/splits/hard2p.jsonl (refuses to overwrite)
"""
from __future__ import annotations

import collections
import hashlib
import json
import random
import re

from stoa.eval.splits import SEED, splits_dir

# recipe -> (regex on the hard2 question, [templates using the groups])
REWORD: dict[str, tuple[str, list[str]]] = {
    # swiss
    "rooms-above-threshold": (r"^How many of the rooms (.+) have a net floor area of more than (\S+) m²\?$", [
        "Of rooms {1}, how many exceed {2} m² of net floor area?",
        "Wie viele der Räume {1} haben eine Nettofläche von über {2} m²?"]),
    "average-room-area": (r"^What is the average net floor area of rooms (.+), in m²\?$", [
        "What is the mean net area (m²) of rooms {1}?",
        "Quelle est la surface nette moyenne des pièces {1}, en m² ?"]),
    "room-sum-ft2": (r"^What is the combined net floor area of rooms (.+), in square feet\?$", [
        "Add up the net floor areas of rooms {1} and give the result in sq ft.",
        "Wie gross ist die Nettofläche der Räume {1} zusammen, in Quadratfuss (sq ft)?"]),
    "apartment-share-pct": (r"^What share of the total net floor area of all numbered indoor rooms on this floor does "
                            r"apartment (\w+) take up, in percent\?$", [
        "Apartment {1} accounts for what percentage of this floor's total net area of numbered indoor rooms?",
        "Quel pourcentage de la surface nette totale des pièces intérieures numérotées de cet étage occupe "
        "l'appartement {1} ?"]),
    "floor-minus-apartment": (r"^What is the total net floor area, in m², of the numbered indoor rooms on this floor "
                              r"that do not belong to apartment (\w+)\?$", [
        "Excluding apartment {1}, what is the total net area in m² of the numbered indoor rooms on this floor?",
        "Wie gross ist die Nettofläche aller nummerierten Innenräume dieses Geschosses ohne Wohnung {1}, in m²?"]),
    "apartment-ratio": (r"^How many times larger is apartment (\w+) than apartment (\w+) by net floor area\? "
                        r"Give the ratio\.$", [
        "What is the ratio of apartment {1}'s net floor area to apartment {2}'s?",
        "Um welchen Faktor ist Wohnung {1} grösser als Wohnung {2} (Nettofläche)?"]),
    "smaller-apartment": (r"^Which is smaller by net floor area, apartment (\w+) or apartment (\w+)\?$", [
        "Between apartments {1} and {2}, which one has less net floor area?",
        "Lequel est le plus petit en surface nette : l'appartement {1} ou l'appartement {2} ?"]),
    "doors-per-apartment": (r"^On average, how many doors are drawn per apartment on this floor plan \(all doors on "
                            r"the floor divided by the number of apartments\)\?$", [
        "What is the mean number of doors per residential unit on this floor (total doors / number of apartments)?",
        "Wie viele Türen gibt es durchschnittlich pro Wohnung auf diesem Grundriss (alle Türen geteilt durch die "
        "Anzahl Wohnungen)?"]),
    # ifc
    "average-room-area-storey": (r"^What is the average net floor area per room \(space\) on '(.+)', in m²\?$", [
        "On '{1}', what is the mean net floor area of a room (space), in m²?",
        "Wie gross ist die durchschnittliche Nettofläche pro Raum auf '{1}', in m²?"]),
    "two-storeys-area": (r"^What is the combined net floor area of all rooms \(spaces\) on '(.+)' and on '(.+)', in m²\?$", [
        "Sum the net floor areas of all spaces on '{1}' and on '{2}' (m²).",
        "Wie gross ist die Nettofläche aller Räume auf '{1}' und '{2}' zusammen, in m²?"]),
    "storey-more-doors": (r"^Which storey has more doors on its floor plan, '(.+)' or '(.+)'\?$", [
        "Does '{1}' or '{2}' have the larger number of doors on its floor plan?",
        "Welches Geschoss hat mehr Türen im Grundriss, '{1}' oder '{2}'?"]),
    "wall-length-ft": (r"^What is the total length of all walls on '(.+)', in feet\?$", [
        "How many feet of wall are there on '{1}' in total?",
        "Wie lang sind alle Wände auf '{1}' zusammen, in Fuss (ft)?"]),
    "rooms-above-threshold@ifc": (r"^How many of the rooms (.+) on '(.+)' have a net floor area of more than (\S+) m²\?$", [
        "On '{2}', how many of the rooms {1} exceed {3} m² of net floor area?",
        "Wie viele der Räume {1} auf '{2}' haben mehr als {3} m² Nettofläche?"]),
    "room-share-pct": (r"^What percentage of the total net floor area of '(.+)' does the room '(.+)' take up\?$", [
        "Room '{2}' makes up what percent of the total net floor area on '{1}'?",
        "Welchen Anteil in Prozent hat der Raum '{2}' an der gesamten Nettofläche von '{1}'?"]),
    # cubicasa
    "wet-rooms": (r"^How many wet rooms does this floor plan have, .*$", [
        "Count the wet rooms on this plan: bathrooms/washrooms (KH, KPH, PH, PESUH, SH), separate WCs and saunas combined.",
        "Kuinka monta märkätilaa pohjapiirustuksessa on yhteensä (kylpy- ja pesuhuoneet, erilliset WC:t ja saunat)?"]),
    "wc+showers": (r"^How many toilet seats, showers and bathtubs are drawn on this floor plan together\?$", [
        "What is the total number of WC bowls, showers and bathtubs drawn on this plan?",
        "Kuinka monta WC-istuinta, suihkua ja kylpyammetta pohjapiirustukseen on piirretty yhteensä?"]),
    "two-wc-yes-no": (r"^Does this floor plan show at least two toilet seats \(WC bowls\)\? Answer yes or no\.$", [
        "Are there two or more toilet seats on this plan? Answer yes or no.",
        "Onko pohjapiirustuksessa vähintään kaksi WC-istuinta? Vastaa yes tai no."]),
    "more-bedrooms-than-bathrooms": (r"^Does this apartment have more bedrooms .*$", [
        "Are there more bedrooms (MH) than bathrooms/washrooms (separate WC rooms excluded)? Answer yes or no.",
        "Onko makuuhuoneita (MH) enemmän kuin kylpy- tai pesuhuoneita (erillisiä WC-tiloja ei lasketa)? "
        "Vastaa yes tai no."]),
}


# hard2q: a THIRD wording (01:12). hard2p wordings were quoted in messages to W1/W2, so hard2p stopped being held
# out for dxf/ifc. hard2q is the clean held-out set: report aggregates only and never quote its questions.
REWORD_Q: dict[str, tuple[str, list[str]]] = {
    "rooms-above-threshold": (REWORD["rooms-above-threshold"][0], [
        "Count how many of rooms {1} are bigger than {2} m² (net).",
        "Quante delle stanze {1} hanno una superficie netta superiore a {2} m²?"]),
    "average-room-area": (REWORD["average-room-area"][0], [
        "Rooms {1}: what is their net floor area on average, in square metres?",
        "Qual è la superficie netta media delle stanze {1}, in m²?"]),
    "room-sum-ft2": (REWORD["room-sum-ft2"][0], [
        "Taken together, how many square feet of net floor area do rooms {1} have?",
        "Qual è la superficie netta complessiva delle stanze {1}, in piedi quadrati (sq ft)?"]),
    "apartment-share-pct": (REWORD["apartment-share-pct"][0], [
        "As a percentage, how much of the net area of all numbered indoor rooms on this floor lies in apartment {1}?",
        "Che percentuale della superficie netta di tutti i locali interni numerati di questo piano occupa "
        "l'appartamento {1}?"]),
    "floor-minus-apartment": (REWORD["floor-minus-apartment"][0], [
        "Leaving out apartment {1}, how many m² of net area do the numbered indoor rooms on this floor add up to?",
        "Qual è la superficie netta dei locali interni numerati di questo piano escluso l'appartamento {1}, in m²?"]),
    "apartment-ratio": (REWORD["apartment-ratio"][0], [
        "Divide the net floor area of apartment {1} by that of apartment {2}. What do you get?",
        "Quante volte è più grande l'appartamento {1} rispetto all'appartamento {2} (superficie netta)?"]),
    "smaller-apartment": (REWORD["smaller-apartment"][0], [
        "Apartment {1} or apartment {2}: which has the smaller net floor area?",
        "Quale appartamento ha la superficie netta minore, {1} o {2}?"]),
    "doors-per-apartment": (REWORD["doors-per-apartment"][0], [
        "Dividing the number of doors on this floor by the number of apartments, how many doors per apartment is that?",
        "In media quante porte ci sono per appartamento su questa pianta (porte totali diviso numero di appartamenti)?"]),
    "average-room-area-storey": (REWORD["average-room-area-storey"][0], [
        "Taking all rooms (spaces) on '{1}', what is the average size of one in m² of net floor area?",
        "Wat is de gemiddelde netto vloeroppervlakte per ruimte op '{1}', in m²?"]),
    "two-storeys-area": (REWORD["two-storeys-area"][0], [
        "Together, how many m² of net floor area do the spaces on '{1}' and '{2}' have?",
        "Wat is de totale netto vloeroppervlakte van alle ruimtes op '{1}' en '{2}' samen, in m²?"]),
    "storey-more-doors": (REWORD["storey-more-doors"][0], [
        "Comparing the floor plans of '{1}' and '{2}', on which one are more doors drawn?",
        "Op welke verdieping staan meer deuren op de plattegrond, '{1}' of '{2}'?"]),
    "wall-length-ft": (REWORD["wall-length-ft"][0], [
        "Express the combined length of the walls on '{1}' in feet.",
        "Wat is de totale lengte van alle wanden op '{1}', in voet (ft)?"]),
    "rooms-above-threshold@ifc": (REWORD["rooms-above-threshold@ifc"][0], [
        "Among rooms {1} on '{2}', how many are bigger than {3} m² (net)?",
        "Hoeveel van de ruimtes {1} op '{2}' zijn groter dan {3} m² netto?"]),
    "room-share-pct": (REWORD["room-share-pct"][0], [
        "What fraction of the net floor area of '{1}', as a percent, is taken by room '{2}'?",
        "Welk percentage van de totale netto vloeroppervlakte van '{1}' neemt de ruimte '{2}' in?"]),
    "wet-rooms": (REWORD["wet-rooms"][0], [
        "Add up the bathrooms or washrooms (KH, KPH, PH, PESUH, SH), the separate WC rooms and the saunas on this plan.",
        "Hur många våtrum finns det på planritningen totalt (badrum/tvättrum, separata WC och bastur)?"]),
    "wc+showers": (REWORD["wc+showers"][0], [
        "Toilet seats plus showers plus bathtubs: how many are drawn on this plan?",
        "Hur många toalettstolar, duschar och badkar är ritade på planritningen sammanlagt?"]),
    "two-wc-yes-no": (REWORD["two-wc-yes-no"][0], [
        "Is the number of WC bowls on this plan two or higher? Answer yes or no.",
        "Finns det minst två toalettstolar på planritningen? Svara yes eller no."]),
    "more-bedrooms-than-bathrooms": (REWORD["more-bedrooms-than-bathrooms"][0], [
        "Do bedrooms (MH) outnumber bathrooms/washrooms (separate WC rooms not counted) here? Answer yes or no.",
        "Finns det fler sovrum (MH) än badrum eller tvättrum (separata WC räknas inte)? Svara yes eller no."]),
}


def build(seed: int = SEED, table: dict | None = None, kind: str = "reasoning-reworded",
          prefix: str = "p", seed_off: int = 3) -> list[dict]:
    table = table or REWORD
    rng = random.Random(seed + seed_off)
    src = splits_dir() / "hard2.jsonl"
    rows = [json.loads(line) for line in open(src, encoding="utf-8") if line.strip()]
    out = []
    for r in rows:
        recipe = r["meta"]["recipe"]
        key = f"{recipe}@ifc" if (recipe == "rooms-above-threshold" and r["source"] == "ifc_models") else recipe
        rx, tpls = table[key]
        m = re.match(rx, r["question"])
        if not m:
            raise ValueError(f"{key}: no match for {r['question']!r}")
        i = rng.randrange(len(tpls))
        q = tpls[i]
        for k, g in enumerate(m.groups(), 1):
            q = q.replace("{" + str(k) + "}", g)
        qid = prefix + hashlib.sha1(f"{r['path']}\n{q}".encode()).hexdigest()[:11]
        out.append({**r, "qid": qid, "question": q,
                    "meta": {**r["meta"], "kind": kind, "variant": "en" if i == 0 else "other-language",
                             "from_hard2": r["qid"]}})
    return out


def write(seed: int = SEED, force: bool = False, q: bool = False) -> dict:
    f = splits_dir() / ("hard2q.jsonl" if q else "hard2p.jsonl")
    if f.exists() and not force:
        raise SystemExit(f"{f} exists; splits are frozen (use --force only if nobody has run on it)")
    rows = build(seed, REWORD_Q, "reasoning-reworded-q", "q", 5) if q else build(seed)
    with open(f, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    c = collections.Counter((r["source"], r["meta"]["variant"]) for r in rows)
    return {"n": len(rows), "path": str(f), "by": {"/".join(k): v for k, v in sorted(c.items())}}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--q", action="store_true", help="write hard2q (third wording, the clean held-out set)")
    a = ap.parse_args()
    if a.write:
        print(json.dumps(write(force=a.force, q=a.q), indent=1, ensure_ascii=False))
    else:
        for r in random.Random(2).sample(build(), 10):
            print(r["source"][:5], r["meta"]["recipe"], "|", r["question"], "->", r["answer"])
