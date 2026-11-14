"""Open probe (c225, 08:55): Swiss COMPOSITIONS in German / French / Italian. The translate front end does not fire on
dataset languages (DE/FR/IT are Swiss dataset languages), so a German "how many more doors than windows" goes straight
to the parsers. Bases: the English Swiss rows of the open `hard` (compositions) and `hard2` (new operators) splits;
same gold; the English row itself is the control (wording 'dataset' → control_compare.py works).

    python experiments/F/comp_ml_probe.py            # -> $JUNCTION_SHARED/artifacts/F/comp_ml.jsonl
    python -m stoa.eval --solver pipeline --split $JUNCTION_SHARED/artifacts/F/comp_ml.jsonl
    python experiments/F/control_compare.py $JUNCTION_SHARED/artifacts/F/comp_ml.jsonl RUN.jsonl
"""
from __future__ import annotations

import hashlib
import json
import os
import re

R2 = r"rooms? (?P<A>\d+\.\d+) \('(?P<SA>.+?)'\) and (?:room )?(?P<B>\d+\.\d+) \('(?P<SB>.+?)'\)"
RECIPES = {
    # recipe: (regex on the English question, {lang: template})
    "apt-a+apt-b": (r"apartments (?P<A>[A-Z]) and (?P<B>[A-Z])", {
        "de": "Wie groß ist die Nettowohnfläche der Wohnungen {A} und {B} zusammen, ohne Balkone und Terrassen?",
        "fr": "Quelle est la surface nette des appartements {A} et {B} réunis, hors balcons et terrasses ?",
        "it": "Qual è la superficie netta complessiva degli appartamenti {A} e {B}, esclusi balconi e terrazze?",
    }),
    "doors+windows": (r"", {
        "de": "Wie viele Türen und Fenster sind auf diesem Grundriss insgesamt eingezeichnet?",
        "fr": "Combien de portes et de fenêtres y a-t-il au total sur ce plan ?",
        "it": "Quante porte e finestre ci sono in totale in questa pianta?",
    }),
    "doors-windows": (r"", {
        "de": "Wie viele Türen mehr als Fenster sind auf diesem Plan eingezeichnet?",
        "fr": "Combien de portes de plus que de fenêtres y a-t-il sur ce plan ?",
        "it": "Quante porte in più rispetto alle finestre ci sono in questa pianta?",
    }),
    "windows-doors": (r"", {
        "de": "Wie viele Fenster mehr als Türen sind auf diesem Plan eingezeichnet?",
        "fr": "Combien de fenêtres de plus que de portes y a-t-il sur ce plan ?",
        "it": "Quante finestre in più rispetto alle porte ci sono in questa pianta?",
    }),
    "room-a+room-b": (R2, {
        "de": "Wie groß sind Raum {A} ('{SA}') und Raum {B} ('{SB}') zusammen, in m²?",
        "fr": "Quelle est la surface cumulée de la pièce {A} ('{SA}') et de la pièce {B} ('{SB}') en m² ?",
        "it": "Qual è la superficie complessiva del locale {A} ('{SA}') e del locale {B} ('{SB}') in m²?",
    }),
    "room-a-minus-room-b": (r"room (?P<A>\d+\.\d+) larger than room (?P<B>\d+\.\d+)", {
        "de": "Um wie viele m² ist Raum {A} größer als Raum {B}?",
        "fr": "De combien de m² la pièce {A} est-elle plus grande que la pièce {B} ?",
        "it": "Di quanti m² il locale {A} è più grande del locale {B}?",
    }),
    # the English item list varies (toilets, washbasins, bathtubs and/or showers): {ITEMS_xx} is built from it
    "sanitary-total": (r"How many (?P<ITEMS>.+?) are drawn on this floor plan altogether", {
        "de": "Wie viele {ITEMS_de} sind insgesamt eingezeichnet?",
        "fr": "Combien de {ITEMS_fr} y a-t-il en tout ?",
        "it": "Quanti {ITEMS_it} ci sono in tutto?",
    }),
    "apartment-ratio": (r"apartment (?P<A>[A-Z]) than apartment (?P<B>[A-Z])", {
        "de": "Wie viel Mal größer ist Wohnung {A} als Wohnung {B} (Nettowohnfläche)? Gib das Verhältnis an.",
        "fr": "Combien de fois l'appartement {A} est-il plus grand que l'appartement {B} en surface nette ? Donne le rapport.",
        "it": "Quante volte l'appartamento {A} è più grande dell'appartamento {B} per superficie netta? Indica il rapporto.",
    }),
    "apartment-share-pct": (r"apartment (?P<A>[A-Z]) take up", {
        "de": "Welchen Anteil in Prozent hat Wohnung {A} an der gesamten Nettofläche aller nummerierten Innenräume "
              "dieses Geschosses?",
        "fr": "Quelle part de la surface nette totale des pièces intérieures numérotées de cet étage l'appartement {A} "
              "occupe-t-il, en pour cent ?",
        "it": "Che percentuale della superficie netta totale dei locali interni numerati di questo piano occupa "
              "l'appartamento {A}?",
    }),
    "average-room-area": (R2, {
        "de": "Wie groß ist die durchschnittliche Nettofläche der Räume {A} ('{SA}') und {B} ('{SB}') in m²?",
        "fr": "Quelle est la surface nette moyenne des pièces {A} ('{SA}') et {B} ('{SB}') en m² ?",
        "it": "Qual è la superficie netta media dei locali {A} ('{SA}') e {B} ('{SB}') in m²?",
    }),
    "doors-per-apartment": (r"", {
        "de": "Wie viele Türen gibt es im Durchschnitt pro Wohnung auf diesem Geschoss?",
        "fr": "Combien de portes y a-t-il en moyenne par appartement sur cet étage ?",
        "it": "Quante porte ci sono in media per appartamento su questo piano?",
    }),
    "floor-minus-apartment": (r"belong to apartment (?P<A>[A-Z])", {
        "de": "Wie groß ist die Nettofläche der nummerierten Innenräume dieses Geschosses, die nicht zu Wohnung {A} "
              "gehören, in m²?",
        "fr": "Quelle est la surface nette, en m², des pièces intérieures numérotées de cet étage qui n'appartiennent "
              "pas à l'appartement {A} ?",
        "it": "Qual è la superficie netta, in m², dei locali interni numerati di questo piano che non appartengono "
              "all'appartamento {A}?",
    }),
    "room-sum-ft2": (R2, {
        "de": "Wie groß sind die Räume {A} ('{SA}') und {B} ('{SB}') zusammen, in Quadratfuß?",
        "fr": "Quelle est la surface cumulée des pièces {A} ('{SA}') et {B} ('{SB}'), en pieds carrés ?",
        "it": "Qual è la superficie complessiva dei locali {A} ('{SA}') e {B} ('{SB}'), in piedi quadrati?",
    }),
    "rooms-above-threshold": (R2 + r" have a net floor area of more than (?P<T>\d+(?:\.\d+)?) m²", {
        "de": "Wie viele der Räume {A} ('{SA}') und {B} ('{SB}') haben eine Nettofläche von mehr als {T} m²?",
        "fr": "Combien des pièces {A} ('{SA}') et {B} ('{SB}') ont une surface nette supérieure à {T} m² ?",
        "it": "Quanti dei locali {A} ('{SA}') e {B} ('{SB}') hanno una superficie netta superiore a {T} m²?",
    }),
}


# --cc (c225, 08:58): CubiCasa count compositions in Finnish and Swedish (the open hard/hard2 rows are English only)
RECIPES_CC = {
    "bedrooms+bathrooms": (r"", {
        "fi": "Montako makuuhuonetta ja kylpyhuonetta (ei erillisiä WC-tiloja) asunnossa on yhteensä?",
        "sv": "Hur många sovrum och badrum (inte separata toaletter) har bostaden sammanlagt?",
    }),
    "doors+windows": (r"", {
        "fi": "Montako ovea ja ikkunaa pohjapiirroksessa on yhteensä?",
        "sv": "Hur många dörrar och fönster finns det totalt på planen?",
    }),
    "doors-windows": (r"", {
        "fi": "Kuinka paljon enemmän ovia kuin ikkunoita pohjapiirroksessa on?",
        "sv": "Hur många fler dörrar än fönster finns det på planen?",
    }),
    "windows-doors": (r"", {
        "fi": "Kuinka paljon enemmän ikkunoita kuin ovia pohjapiirroksessa on?",
        "sv": "Hur många fler fönster än dörrar finns det på planen?",
    }),
    "wc+sinks+showers": (r"", {
        "fi": "Montako saniteettikalustetta pohjapiirroksessa on yhteensä (WC-istuimet, pesu- ja tiskialtaat, suihkut ja "
              "ammeet)?",
        "sv": "Hur många sanitetsenheter finns det totalt på planen (toalettstolar, handfat och diskhoar, duschar och "
              "badkar)?",
    }),
    "wc+showers": (r"", {
        "fi": "Montako WC-istuinta, suihkua ja kylpyammetta pohjapiirroksessa on yhteensä?",
        "sv": "Hur många toalettstolar, duschar och badkar finns det sammanlagt på planen?",
    }),
    "wet-rooms": (r"", {
        "fi": "Montako märkätilaa asunnossa on (kylpyhuoneet, erilliset WC:t ja saunat yhteensä)?",
        "sv": "Hur många våtrum har bostaden (badrum, separata toaletter och bastur tillsammans)?",
    }),
}


_ITEM = {"toilets": {"de": "WCs", "fr": "WC", "it": "WC"},
         "washbasins": {"de": "Lavabos", "fr": "lavabos", "it": "lavabi"},
         "bathtubs": {"de": "Badewannen", "fr": "baignoires", "it": "vasche da bagno"},
         "showers": {"de": "Duschen", "fr": "douches", "it": "docce"}}
_AND = {"de": "und", "fr": "et", "it": "e"}


def _items(en_list: str) -> dict:
    words = [w.strip() for w in re.split(r",|\band\b", en_list) if w.strip()]
    out = {}
    for lang in _AND:
        tr = [_ITEM[w][lang] for w in words]
        if lang == "fr":
            tr = [tr[0]] + ["de " + t for t in tr[1:]]
        out[f"ITEMS_{lang}"] = ", ".join(tr[:-1]) + f" {_AND[lang]} " + tr[-1]
    return out


def main():
    import sys
    cc = "--cc" in sys.argv
    recipes, src = (RECIPES_CC, "cubicasa") if cc else (RECIPES, "swiss")
    sh = os.environ["JUNCTION_SHARED"]
    out = os.path.join(sh, "artifacts", "F", "comp_ml_cc.jsonl" if cc else "comp_ml.jsonl")
    n_rows, skipped = 0, {}
    with open(out, "w", encoding="utf-8") as f:
        for split in ("hard", "hard2"):
            for line in open(os.path.join(sh, "results", "splits", f"{split}.jsonl")):
                r = json.loads(line)
                rec = r.get("meta", {}).get("recipe")
                if not r["source"].startswith(src) or rec not in recipes or r.get("type") == "text":
                    continue
                if r["meta"].get("kind") not in ("composition", "reasoning"):
                    continue
                rx, tpls = recipes[rec]
                m = re.search(rx, r["question"]) if rx else re.match("", "")
                if m is None:
                    skipped[rec] = skipped.get(rec, 0) + 1
                    continue
                base = {k: r[k] for k in ("path", "answer", "unit", "type")}
                kind = f"{split}:{rec}"
                g = m.groupdict()
                if "ITEMS" in g:
                    g.update(_items(g["ITEMS"]))
                rows = [("dataset", r["question"])] + [(lang, t.format(**g)) for lang, t in tpls.items()]
                for wording, q in rows:
                    qid = "cm" + hashlib.sha1(f"{r['qid']}|{wording}".encode()).hexdigest()[:10]
                    f.write(json.dumps(dict(base, qid=qid, question=q,
                                            meta={"kind": f"{kind}:{wording}", "wording": wording, "probe_kind": kind,
                                                  "ambiguous": False, "base_qid": r["qid"]}),
                                       ensure_ascii=False) + "\n")
                    n_rows += 1
    print(f"{n_rows} rows -> {out}; skipped (regex miss): {skipped}")


if __name__ == "__main__":
    main()
