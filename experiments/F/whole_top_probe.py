"""Same-gold probe (c227, OPEN: dev IFC drawings only): building-wide and 'top floor' scope words.

Now that a plan sheet knows its own storey (W1 6f1edf1: title line / SVG tag vote), a question about the WHOLE building
asked on a sheet must not shrink to that sheet's storey, and a storey ROLE word ('the top floor') must resolve to the
highest storey that has rooms, not to the sheet's storey or the whole model.

  whole_*: base = dataset "How many N are there in the model 'M'?" (asked on a plan sheet, gold = whole model),
           re-asked without naming the model ("in the whole building", "across all floors", nl/de/fr).
           Also asked on the MODEL path (kinds wholeM_*).
  top_*:   base = dataset per-storey questions on the highest storey with rooms, where that storey is unambiguous
           (gdynia '1' under a room-less 'Roof'; smiley '2.OG' under an empty 'Dach'), re-asked with 'top floor'
           words on the model path and on another storey's sheet (kinds top_model / top_othersheet).

    python experiments/F/whole_top_probe.py  -> $JUNCTION_SHARED/artifacts/F/whole_top.jsonl
Every row carries meta.kind = "<kind>:<wording>", meta.base_qid; wording 'dataset' = the base question as a control.
"""
import hashlib
import json
import os
import re

from stoa.data import dataset_rel, ifc_model_for
from stoa.eval.splits import load_split

NOUNS = {  # en: (nl, de, fr)
    "doors": ("deuren", "Türen", "portes"), "windows": ("ramen", "Fenster", "fenêtres"),
    "walls": ("wanden", "Wände", "murs"), "rooms": ("ruimtes", "Räume", "pièces"),
    "columns": ("kolommen", "Stützen", "poteaux"), "stairs": ("trappen", "Treppen", "escaliers"),
    "beams": ("balken", "Träger", "poutres"), "sanitary fixtures": ("sanitaire objecten", "Sanitärobjekte",
                                                                    "appareils sanitaires"),
}
NL_EN = {"ruimtes": "rooms", "ramen": "windows", "wanden": "walls", "balken": "beams", "deuren": "doors"}
WHOLE = {
    "building": "How many {n} are there in the whole building?",
    "total_floors": "How many {n} does the building have in total, across all floors?",
    "entire_model": "Total number of {n} in the entire model?",
    "this_building": "How many {n} are in this building?",
    "nl": "Hoeveel {nl} heeft het hele gebouw?",
    "de": "Wie viele {de} hat das gesamte Gebäude?",
    "fr": "Combien de {fr} y a-t-il dans tout le bâtiment ?",
}
TOP_STOREY = {"bimspeed-gdynia_ruchu-oporu-18.ifc": "1", "kit-smiley-west_ac-20-smiley-west-10-bldg.ifc": "2.OG"}
OTHER_SHEET = {"bimspeed-gdynia_ruchu-oporu-18.ifc": "data/ifc_models/bimspeed-gdynia_ruchu-oporu-18_plan-03-0.pdf",
               "kit-smiley-west_ac-20-smiley-west-10-bldg.ifc":
                   "data/ifc_models/kit-smiley-west_ac-20-smiley-west-10-bldg_plan-02-eg.pdf"}
TOP_COUNT = {"top": "How many {n} are there on the top floor?", "upper": "How many {n} are on the uppermost storey?",
             "de": "Wie viele {de} hat das oberste Geschoss?", "nl": "Hoeveel {nl} zijn er op de bovenste verdieping?"}
TOP_TOTAL = {"top": "What is the {q} on the top floor, in {u}?", "upper": "{Q} on the highest storey, in {u}?"}


def row(base, kind, wording, path, question, out):
    qid = "wt" + hashlib.sha1(f"{base.qid}|{kind}|{wording}|{path}".encode()).hexdigest()[:10]
    out.append({"qid": qid, "path": path, "question": question, "answer": base.answer, "unit": base.unit,
                "type": base.type, "meta": {"kind": f"{kind}:{wording}", "wording": wording, "probe_kind": kind,
                                            "ambiguous": False, "base_qid": base.qid}})


def main():
    out = []
    dev = [q for q in load_split("dev") if q.source == "ifc_models"]
    for q in dev:
        m = (re.match(r"^How many (?P<N>[a-z ]+?)(?: \(spaces\))? are there in the model '[^']+'\?$", q.question)
             or re.match(r"^Hoeveel (?P<NL>\w+) bevat het model '[^']+'\?$", q.question))
        if not m:
            continue
        n = m.groupdict().get("N") or NL_EN.get(m.groupdict().get("NL") or "")
        if n not in NOUNS:
            continue
        nl, de, fr = NOUNS[n]
        model = dataset_rel(str(ifc_model_for(q.path)))
        for kind, path in (("whole_sheet", q.path), ("wholeM", model)):
            row(q, kind, "dataset", path, q.question, out)
            for w, tpl in WHOLE.items():
                row(q, kind, w, path, tpl.format(n=n, nl=nl, de=de, fr=fr), out)
    for q in dev:
        model = ifc_model_for(q.path)
        name = os.path.basename(str(model)) if model else ""
        st = TOP_STOREY.get(name)
        if not st:
            continue
        mc = re.match(rf"^How many (?P<N>walls|doors|windows|rooms) (?:\(spaces\) )?are shown on the floor plan of '{re.escape(st)}'\?$",
                      q.question)
        mt = re.match(rf"^What is the (?P<Q>total net (?:floor area of all rooms \(spaces\)|side area of all walls|volume of all "
                      rf"slabs|volume of all walls)|total length of all walls) on '{re.escape(st)}', in (?P<U>m²|m³|metres)\?$",
                      q.question)
        if not (mc or mt):
            continue
        for kind, path in (("top_model", dataset_rel(str(model))), ("top_othersheet", OTHER_SHEET[name])):
            row(q, kind, "dataset", path, q.question, out)
            if mc:
                n = mc["N"]
                nl, de, _ = NOUNS[n]
                for w, tpl in TOP_COUNT.items():
                    row(q, kind, w, path, tpl.format(n=n, nl=nl, de=de), out)
            else:
                qq = mt["Q"].replace(" (spaces)", "")
                for w, tpl in TOP_TOTAL.items():
                    row(q, kind, w, path, tpl.format(q=qq, Q=qq[0].upper() + qq[1:], u=mt["U"]), out)
    dst = os.path.join(os.environ["JUNCTION_SHARED"], "artifacts", "F", "whole_top.jsonl")
    with open(dst, "w", encoding="utf-8") as f:
        for d in out:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    kinds = {}
    for d in out:
        kinds[d["meta"]["probe_kind"]] = kinds.get(d["meta"]["probe_kind"], 0) + 1
    print(kinds, len(out), "rows ->", dst)


if __name__ == "__main__":
    main()
