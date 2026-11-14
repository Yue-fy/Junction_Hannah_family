"""W4 c73: second unseen-language probe for the language front end (Portuguese, Slovak, Lithuanian, Croatian; none is
used by any split or by R2's lang4 CS/HU/TR/RO). 16 English dev questions (other drawings than lang4), translated by
hand BEFORE any run; gold = the dataset's gold for the English original.
    python experiments/w4/lang4b.py  -> $JUNCTION_SHARED/artifacts/W4/lang4b.jsonl (64 rows)
"""
import json
import os
from pathlib import Path

from stoa.data import load_questions

T = {  # qid: {lang: question}
    "740cb244e949": {"pt": "Quantas janelas estão representadas nesta planta?",
                     "sk": "Koľko okien je zakreslených na tomto pôdoryse?",
                     "lt": "Kiek langų pavaizduota šiame aukšto plane?",
                     "hr": "Koliko je prozora prikazano na ovom tlocrtu?"},
    "878e4a4aa582": {"pt": "Quantas casas de banho ou lavabos (p. ex. KH, KPH, PH, PESUH, SH) há nesta planta, sem contar as divisões separadas de WC?",
                     "sk": "Koľko kúpeľní alebo umyvární (napr. KH, KPH, PH, PESUH, SH) je na tomto pôdoryse, bez samostatných miestností WC?",
                     "lt": "Kiek vonios kambarių ar prausyklų (pvz., KH, KPH, PH, PESUH, SH) yra šiame plane, neskaičiuojant atskirų WC patalpų?",
                     "hr": "Koliko kupaonica ili praonica (npr. KH, KPH, PH, PESUH, SH) ima na ovom tlocrtu, ne računajući zasebne WC prostorije?"},
    "d515a3507904": {"pt": "Quantas saunas existem nesta planta?",
                     "sk": "Koľko sáun je na tomto pôdoryse?",
                     "lt": "Kiek saunų yra šiame plane?",
                     "hr": "Koliko sauna ima na ovom tlocrtu?"},
    "51c31292d1a8": {"pt": "Quantos quartos de dormir (makuuhuone, normalmente marcados MH) há nesta planta?",
                     "sk": "Koľko spální (makuuhuone, zvyčajne označené MH) je na tomto pôdoryse?",
                     "lt": "Kiek miegamųjų (makuuhuone, paprastai pažymėtų MH) yra šiame plane?",
                     "hr": "Koliko spavaćih soba (makuuhuone, obično označenih MH) ima na ovom tlocrtu?"},
    "c008893fa5d5": {"pt": "Quantas janelas estão desenhadas nesta planta do piso?",
                     "sk": "Koľko okien je nakreslených na tomto pôdoryse podlažia?",
                     "lt": "Kiek langų nubraižyta šiame aukšto plane?",
                     "hr": "Koliko je prozora ucrtano na ovom tlocrtu kata?"},
    "5396efca39a6": {"pt": "Quantos lavatórios estão desenhados nesta planta?",
                     "sk": "Koľko umývadiel je nakreslených na tomto pôdoryse?",
                     "lt": "Kiek praustuvų nubraižyta šiame plane?",
                     "hr": "Koliko je umivaonika ucrtano na ovom tlocrtu?"},
    "ab124fda1414": {"pt": "Quantos chuveiros estão desenhados nesta planta?",
                     "sk": "Koľko spŕch je nakreslených na tomto pôdoryse?",
                     "lt": "Kiek dušų nubraižyta šiame plane?",
                     "hr": "Koliko je tuševa ucrtano na ovom tlocrtu?"},
    "fcc9d7ebe8bb": {"pt": "Quantos apartamentos (unidades residenciais) aparecem nesta planta?",
                     "sk": "Koľko bytov (bytových jednotiek) je zobrazených na tomto pôdoryse?",
                     "lt": "Kiek butų (gyvenamųjų vienetų) parodyta šiame aukšto plane?",
                     "hr": "Koliko je stanova (stambenih jedinica) prikazano na ovom tlocrtu?"},
    "abb2c909ad7d": {"pt": "Quantas portas aparecem na planta do piso '0'?",
                     "sk": "Koľko dverí je zobrazených na pôdoryse podlažia '0'?",
                     "lt": "Kiek durų parodyta aukšto '0' plane?",
                     "hr": "Koliko je vrata prikazano na tlocrtu etaže '0'?"},
    "f85b94dcd5ce": {"pt": "Quantas escadas aparecem na planta do piso '-1'?",
                     "sk": "Koľko schodísk je zobrazených na pôdoryse podlažia '-1'?",
                     "lt": "Kiek laiptų parodyta aukšto '-1' plane?",
                     "hr": "Koliko je stubišta prikazano na tlocrtu etaže '-1'?"},
    "0d6cd7e8c0f2": {"pt": "Quantos compartimentos (espaços) aparecem na planta do piso '-1'?",
                     "sk": "Koľko miestností (priestorov) je zobrazených na pôdoryse podlažia '-1'?",
                     "lt": "Kiek patalpų (erdvių) parodyta aukšto '-1' plane?",
                     "hr": "Koliko je prostorija (prostora) prikazano na tlocrtu etaže '-1'?"},
    "f05967c9bfeb": {"pt": "Quantas janelas existem no modelo 'BIM-Speed Gdynia - semi-detached house Ruchu Oporu 18'?",
                     "sk": "Koľko okien je v modeli 'BIM-Speed Gdynia - semi-detached house Ruchu Oporu 18'?",
                     "lt": "Kiek langų yra modelyje 'BIM-Speed Gdynia - semi-detached house Ruchu Oporu 18'?",
                     "hr": "Koliko prozora ima u modelu 'BIM-Speed Gdynia - semi-detached house Ruchu Oporu 18'?"},
    "58c980ba8fdb": {"pt": "Na folha A-801 dos desenhos do Xcel Sports Complex, quantas portas na tabela de portas têm 7'-0\" de altura?",
                     "sk": "Koľko dverí v tabuľke dverí na výkrese A-801 projektu Xcel Sports Complex má výšku 7'-0\"?",
                     "lt": "Xcel Sports Complex brėžinių lape A-801: kiek durų žiniaraštyje yra 7'-0\" aukščio durų?",
                     "hr": "Na listu A-801 nacrta Xcel Sports Complexa, koliko vrata u tablici vrata ima visinu 7'-0\"?"},
    "f3e6d401e0f8": {"pt": "Qual é a área útil total, em m², de todas as divisões com a etiqueta 'Schlafzimmer' neste piso?",
                     "sk": "Aká je celková čistá plocha v m² všetkých miestností označených 'Schlafzimmer' na tomto podlaží?",
                     "lt": "Koks bendras visų patalpų, pažymėtų 'Schlafzimmer', grynasis plotas m² šiame aukšte?",
                     "hr": "Kolika je ukupna neto površina u m² svih prostorija označenih 'Schlafzimmer' na ovom katu?"},
    "4693f9577549": {"pt": "Qual é a área útil total em m² de todas as divisões interiores numeradas neste piso (excluindo varandas, loggias, terraços e outros espaços exteriores, courettes e vazios)?",
                     "sk": "Aká je celková čistá podlahová plocha v m² všetkých očíslovaných vnútorných miestností na tomto podlaží (bez balkónov, lodžií, terás a iných vonkajších priestorov, šácht a prázdnych priestorov)?",
                     "lt": "Koks bendras visų sunumeruotų vidaus patalpų grynasis grindų plotas m² šiame aukšte (be balkonų, lodžijų, terasų ir kitų lauko erdvių, šachtų ir tuštumų)?",
                     "hr": "Kolika je ukupna neto podna površina u m² svih numeriranih unutarnjih prostorija na ovom katu (bez balkona, loggia, terasa i drugih vanjskih prostora, šahtova i šupljina)?"},
    "9f20737e6768": {"pt": "Qual é a área útil do compartimento 'Room (0.5)' no piso '0', em m²?",
                     "sk": "Aká je čistá podlahová plocha miestnosti 'Room (0.5)' na podlaží '0' v m²?",
                     "lt": "Koks yra patalpos 'Room (0.5)' aukšte '0' grynasis grindų plotas m²?",
                     "hr": "Kolika je neto podna površina prostorije 'Room (0.5)' na etaži '0', u m²?"},
}


def main() -> None:
    qs = {q.qid: q for q in load_questions()}
    out = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")) / "artifacts/W4/lang4b.jsonl"
    rows = []
    for qid, tr in T.items():
        q = qs[qid]
        for lang, text in tr.items():
            rows.append({"path": q.path, "answer": q.answer, "unit": q.unit, "type": q.type, "source": q.source,
                         "qid": f"{qid}-{lang}", "question": text, "meta": {"kind": "lang4b", "lang": lang, "en": q.question}})
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(out, len(rows))


if __name__ == "__main__":
    main()
