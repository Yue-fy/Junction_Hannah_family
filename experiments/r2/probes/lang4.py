"""Unseen-language probe (owner: R2): 12 English DEV questions (4 cubicasa, 4 swiss, 4 ifc; gold from the dataset)
hand-translated by R2 into Czech, Hungarian, Turkish and Romanian = 48 probes, plus the 12 English originals.
Languages chosen because NO split uses them (sealed hard2r uses ES/ET/PL; the dataset uses EN/FI/DE/FR/IT and
IFC template translations in NL/DA/ET/ES/PL/RO-ish). Written before any run of the translation front end.

    $JUNCTION_VENV/bin/python experiments/r2/probes/lang4.py   ->  $JUNCTION_SHARED/artifacts/R2/lang4{,_en}.jsonl
    then e.g.  python -m stoa.eval --solver pipeline --split $JUNCTION_SHARED/artifacts/R2/lang4.jsonl
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

P = {  # qid -> {lang: question}
    "7c35a1412bac": {
        "cs": "Kolik záchodových mís (WC) je zakresleno na tomto půdorysu?",
        "hu": "Hány WC-csésze van berajzolva ezen az alaprajzon?",
        "tr": "Bu kat planında kaç adet klozet (WC taşı) çizilmiştir?",
        "ro": "Câte vase de toaletă (WC-uri) sunt desenate pe acest plan de etaj?"},
    "113c91374fb4": {
        "cs": "Kolik saun je na tomto půdorysu?",
        "hu": "Hány szauna található ezen az alaprajzon?",
        "tr": "Bu kat planında kaç sauna var?",
        "ro": "Câte saune sunt pe acest plan de etaj?"},
    "630688f479f4": {
        "cs": "Kolik ložnic (makuuhuone, obvykle označených MH) je na tomto půdorysu?",
        "hu": "Hány hálószoba (makuuhuone, általában MH jelöléssel) van ezen az alaprajzon?",
        "tr": "Bu kat planında kaç yatak odası (makuuhuone, genellikle MH ile işaretli) var?",
        "ro": "Câte dormitoare (makuuhuone, de obicei marcate MH) sunt pe acest plan de etaj?"},
    "0d23c5e2b482": {
        "cs": "Kolik kuchyní (včetně kuchyňských koutů, otevřených kuchyní a pomocných kuchyní) je na tomto půdorysu?",
        "hu": "Hány konyha (beleértve a teakonyhákat, a nyitott konyhákat és a kiszolgáló konyhákat) van ezen az "
              "alaprajzon?",
        "tr": "Bu kat planında kaç mutfak (mini mutfaklar, açık mutfaklar ve hizmet mutfakları dahil) var?",
        "ro": "Câte bucătării (inclusiv chicinete, bucătării deschise și bucătării de serviciu) sunt pe acest plan de "
              "etaj?"},
    "72d910375ff9": {
        "cs": "Jaká je čistá podlahová plocha místnosti 1.11 ('Zimmer') v m²?",
        "hu": "Mekkora az 1.11-es helyiség ('Zimmer') nettó alapterülete m²-ben?",
        "tr": "1.11 numaralı odanın ('Zimmer') net taban alanı kaç m²'dir?",
        "ro": "Care este suprafața netă a camerei 1.11 ('Zimmer') în m²?"},
    "c3ce4a72041a": {
        "cs": "Kolik místností s označením 'Bad' je na tomto podlaží?",
        "hu": "Hány 'Bad' feliratú helyiség van ezen a szinten?",
        "tr": "Bu katta 'Bad' etiketli kaç oda var?",
        "ro": "Câte camere etichetate 'Bad' sunt la acest etaj?"},
    "213e49220a98": {
        "cs": "Jaká je čistá podlahová plocha bytu A v m², tedy součet všech jeho místností kromě balkonů, lodžií, "
              "teras a dalších venkovních prostor?",
        "hu": "Mekkora az A lakás nettó alapterülete m²-ben, az összes helyiségét összeadva, kivéve az erkélyeket, "
              "loggiákat, teraszokat és egyéb kültéri tereket?",
        "tr": "A dairesinin net taban alanı kaç m²'dir (balkonlar, lojalar, teraslar ve diğer dış mekânlar hariç "
              "tüm odalarının toplamı)?",
        "ro": "Care este suprafața netă a apartamentului A în m², însumând toate camerele sale cu excepția "
              "balcoanelor, logiilor, teraselor și a altor spații exterioare?"},
    "ca6c6d336701": {
        "cs": "Kolik dveří (vnitřních a vstupních dohromady) je zakresleno na tomto půdorysu?",
        "hu": "Hány ajtó (belső és bejárati ajtók együtt) van berajzolva ezen az alaprajzon?",
        "tr": "Bu kat planında kaç kapı (iç kapılar ve giriş kapıları birlikte) çizilmiştir?",
        "ro": "Câte uși (uși interioare și uși de intrare împreună) sunt desenate pe acest plan de etaj?"},
    "437c554c9bb8": {
        "cs": "Jaká je čistá podlahová plocha místnosti 'Bedroom (414B-1-001-001)' na podlaží '1. Level' v m²?",
        "hu": "Mekkora a(z) 'Bedroom (414B-1-001-001)' helyiség nettó alapterülete a(z) '1. Level' szinten, m²-ben?",
        "tr": "'1. Level' katındaki 'Bedroom (414B-1-001-001)' odasının net taban alanı kaç m²'dir?",
        "ro": "Care este suprafața netă a camerei 'Bedroom (414B-1-001-001)' de la nivelul '1. Level', în m²?"},
    "15ceaf9b4e17": {
        "cs": "Kolik dveří je zobrazeno na půdorysu podlaží 'KG'?",
        "hu": "Hány ajtó látható a(z) 'KG' szint alaprajzán?",
        "tr": "'KG' katının planında kaç kapı gösterilmektedir?",
        "ro": "Câte uși sunt afișate pe planul nivelului 'KG'?"},
    "6fb39a265afb": {
        "cs": "Jaká je celková délka všech stěn na podlaží '00 Begane grond' v metrech?",
        "hu": "Mekkora a(z) '00 Begane grond' szinten lévő összes fal teljes hossza méterben?",
        "tr": "'00 Begane grond' katındaki tüm duvarların toplam uzunluğu kaç metredir?",
        "ro": "Care este lungimea totală a tuturor pereților de la nivelul '00 Begane grond', în metri?"},
    "ca83282f8edd": {
        "cs": "Jaký je celkový čistý objem všech stropních desek na podlaží 'Entrance' v m³?",
        "hu": "Mekkora az 'Entrance' szinten lévő összes födém teljes nettó térfogata m³-ben?",
        "tr": "'Entrance' katındaki tüm döşemelerin toplam net hacmi kaç m³'tür?",
        "ro": "Care este volumul net total al tuturor plăcilor de la nivelul 'Entrance', în m³?"},
}


def main() -> None:
    from stoa.eval.splits import load_split

    dev = {q.qid: q for q in load_split("dev")}
    out = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")) / "artifacts/R2"
    rows, en = [], []
    for qid, tr in P.items():
        q = dev[qid]
        base = {"path": q.path, "answer": q.answer, "unit": q.unit, "type": q.type, "source": q.source}
        en.append({**base, "qid": f"{qid}-en", "question": q.question, "meta": {"kind": "lang4", "lang": "en"}})
        for lang, text in tr.items():
            rows.append({**base, "qid": f"{qid}-{lang}", "question": text, "meta": {"kind": "lang4", "lang": lang}})
    for name, rr in (("lang4.jsonl", rows), ("lang4_en.jsonl", en)):
        (out / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rr))
        print(out / name, len(rr))


if __name__ == "__main__":
    main()
