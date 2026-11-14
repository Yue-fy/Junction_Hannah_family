"""Estimate, don't refuse: questions a drawing cannot answer (rent, occupants, price, construction cost, U-value,
construction year, energy use) get a best estimate + interval + stated assumptions + the record that would settle it.

Stoa (COMMON point 3): "you know what you don't know, but refusing is not useful". Q's audit (KNOWLEDGE 09:16): the
pipeline answers exactly these questions with the string "unknown" ("What is the monthly rent of this apartment?",
"How many people live in this apartment?", "U-value of the exterior walls?", "What did this building cost?",
"What year was this building constructed?"). Method: a quantity the drawing DOES hold (dwelling floor area from the
DXF rooms / IFC spaces / CubiCasa room graph; bedroom count) x a published reference rate for the country the
dataset source is from (Statistics Finland, Swiss FSO, ...), with the rate's range as the interval. 0 LLM calls.
Evidence = the rooms whose areas were summed. Confidence is low by construction (<= 0.2): the answer is a flagged
estimate, never a reading.

    from experiments.r1.estimate.estimate import kind_of, solve
    kind_of("How many people live in this apartment?")  -> {"fire": True, "kind": "occupants", ...}
    solve(path, question) -> stoa.contract.Answer | None   (None: not an out-of-drawing question we model)
    python experiments/r1/estimate/estimate.py PATH "question"

Not ours (kind_of does not fire): questions that STATE their own rate/constant ("if each person needs 12 m2 ...",
"at 15 EUR per m2 ..."): those are derived quantities, answered exactly by the pipeline (W4/W1, hard3 family).
"""
from __future__ import annotations

import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stoa.contract import Answer, Cost, Evidence  # noqa: E402

# ---------------------------------------------------------------------------------------------------------------
# question kinds (en/fi/sv/de/fr/it/nl/et/es)
# ---------------------------------------------------------------------------------------------------------------
_PEOPLE = (r"(people|persons?|residents?|occupants?|inhabitants?|tenants?|family members|ihmis\w*|henke\w*|henki\w*|"
           r"asukka\w*|personer|människor|boende|personen|menschen|bewohner\w*|leute|personnes|habitants|"
           r"occupants|persone|abitanti|inquilini|mensen|bewoners|inimes\w*|elanik\w*|personas|habitantes)")
_LIVE = (r"(live|lives|living|reside|stay|occupy|sleep|accommodat\w*|house[ds]?|fit|asuu|asuvat|asua|majoittu\w*|"
         r"mahtuu|nukkuu|bor|bo|ryms|wohn\w*|leben|unterbring\w*|platz|vivent|habitent|loger|dormir|vivono|abitano|"
         r"ospitar\w*|wonen|woont|elab|elavad|mahub|viven|habitan|alojar)")
KINDS = [
    ("occupants", rf"\b(how many|wie viele|kuinka monta|montako|hur många|combien de|quante|quanti|hoeveel|mitu|"
                  rf"cuántas|cuantas|number of)\s+(\w+\s+)?{_PEOPLE}\b.{{0,60}}\b{_LIVE}\b|"
                  rf"\b(household size|asukasmäärä\w*|asukasluku\w*|bewohnerzahl|antal (boende|personer)|occupancy (count|number|"
                  rf"capacity)|occupant (count|number))\b|"
                  rf"\b{_PEOPLE}\b.{{0,20}}\b(live|lives|wohnen|asuu|bor|vivent|vivono|wonen|elab|viven)\s+(here|in (this|the))"),
    ("rent", r"\b(rent|rental (price|cost|income)|monthly rent|miete\w*|mietzins\w*|kaltmiete\w*|vuokra\w*|hyra\w*|hyran|hyres\w*|"
             r"loyer|affitto|canone|huur|huurprijs\w*|üür\w*|alquiler|renta mensual)\b"),
    ("price", r"\b(market value|sale price|selling price|asking price|purchase price|property value|what is .{0,30}worth|"
              r"how much .{0,40}(sell|buy|worth)|kauppahinta\w*|myyntihinta\w*|velaton hinta|markkina-arvo\w*|"
              r"verkaufspreis|marktwert\w*|kaufpreis\w*|verkehrswert\w*|prix de vente|valeur (vénale|marchande|du bien)|"
              r"prezzo di vendita|valore di mercato|marknadsvärde\w*|försäljningspris\w*|köpeskilling\w*|vraagprijs\w*|"
              r"marktwaarde|koopprijs\w*|turuhind\w*|müügihind\w*|precio de venta|valor de mercado)\b"),
    ("repaint", r"\b(cost to (re)?paint|(re)?painting costs?|cost of (re)?painting|maalauskustannu\w*|malerkosten|"
                r"kosten (für )?(den )?(neu)?anstrich\w*|coût de (la )?peinture|costo (della )?(tinteggiatura|pittura)|"
                r"målningskostnad\w*|schilderkosten|värvimise (hind|maksumus)|costo de (la )?pintura)\b"),
    ("construction_cost", r"\b(construction cost|cost to (build|construct)|cost .{0,30}to (build|construct)|"
                          r"build(ing)? cost|did .{0,40}cost|cost of (building|constructing|construction)|"
                          r"rakennuskustannu\w*|rakentamis\w* (hinta|kustannu\w*|maksoi)|maksoi rakentaa|"
                          r"baukosten|erstellungskosten\w*|kosten .{0,20}(bau|errichtung)|coût de (construction|la construction)|"
                          r"costo di costruzione|costi di costruzione|byggkostnad\w*|kostade .{0,20}bygga|bouwkosten\w*|"
                          r"ehituskulu\w*|ehitusmaksumus\w*|costo de construcción|coste de construcción)\b"),
    ("u_value", r"\b(u[- ]?values?|u[- ]?factor|thermal transmittance|u[- ]?wert|wärmedurchgangskoeffizient|u[- ]?arvo\w*|"
                r"lämmönläpäisy\w*|valeur u|coefficient de transmission thermique|trasmittanza( termica)?|"
                r"u[- ]?värde|värmegenomgångskoefficient|warmtedoorgangsco\w*|u[- ]?waarde|soojusläbivus\w*|"
                r"transmitancia( térmica)?)\b"),
    ("year_built", r"\b((what|which) year .{0,40}(built|constructed|completed|erected)|when was .{0,40}"
                   r"(built|constructed|completed|erected)|year of (construction|completion)|construction year|"
                   r"year built|built in (what|which) year|how old is (this|the) (building|house)|"
                   r"rakennusvuo\w*|valmistumisvuo\w*|milloin .{0,40}rakennettu|baujahr\w*|wann wurde .{0,40}(gebaut|errichtet)|"
                   r"année de construction|quand .{0,40}construit|anno di costruzione|quando .{0,40}costruit\w*|"
                   r"byggår|byggnadsår\w*|när byggdes|bouwjaar\w*|wanneer .{0,40}gebouwd|ehitusaasta\w*|millal .{0,40}ehitati|"
                   r"año de construcción|cuándo se construyó)\b"),
    ("energy", r"\b(energy (consumption|use|demand)|heating (energy|demand|need)|annual (energy|heating)|"
               r"energiankulutu\w*|lämmitysenergi\w*|energieverbrauch\w*|heizwärmebedarf\w*|heizenergie\w*|"
               r"consommation (d'énergie|énergétique)|besoin de chauffage|consumo (energetico|di energia|de energía)|"
               r"fabbisogno termico|energiförbrukning\w*|uppvärmningsbehov\w*|energieverbruik\w*|warmtevraag\w*|"
               r"energiatarbimine|energiakulu\w*)\b"),
]
# language-general co-occurrence forms (tuned on half A of probe_para.jsonl; R1 09:21 lesson: verb lists miss
# unseen wordings): a count word + a people word; a cost word near a build word; a market word near a value word; ...
_COUNTW = (r"(how many|number of|wie viele|anzahl|kuinka (monta|paljon)|montako|hur många|antal|combien|nombre de|"
           r"quant[ie]|numero di|hoeveel|aantal|mitu|kui palju|cuánt[oa]s|cuant[oa]s|número de)")
_COSTW = (r"(cost|costs|costed|expense|expenditure|spent|kosten|gekostet|kostete|kostet|coût\w*|coute|coûté|costo|"
          r"costato|costò|costi|kostnad\w*|kostade|kostte|kulu\w*|maksoi|maksumus|maksma|costó|coste|gast\w*|rahaa)")
_BUILDW = (r"(build|built|building it|construct\w*|bau|baus|bauen|errichtung|erbau\w*|errichte\w*|rakent\w*|"
           r"construire|construit\w*|costruire|costruzione|costruit\w*|bygga|bygge|byggde|byggt|bouw|bouwen|bouwkosten\w*|"
           r"ehita\w*|ehitus\w*|ehitati|construir\w*|edificar|construcción)\b")
_MARKET = r"(market|markkina\w*|markt\w*|marché|mercato|marknad\w*|turu\w*|mercado)"
_VALUEW = (r"(value|price|worth|hinta|arvo|wert|preis|valeur|prix|valore|prezzo|värde|värd|pris|waarde|prijs|"
           r"väärtus\w*|hind\w*|valor|precio)")
_WALLW = r"(walls?|wände|wand|seinä\w*|murs?|pareti|parete|väggar|vägg\w*|muren|muur|sein\w*|paredes|muros|envelope|facade)"
_INSUL_TERM = (r"(thermal (transmittance|performance|resistance)|trasmission\w* termic\w*|värmeledning\w*|"
               r"varmeledning\w*|warmteoverdracht\w*|warmtedoorgang\w*|wärmedurchgang\w*|lämmönläpäis\w*)")
# bare 'insulation' asks for a property of the model (thickness, type, volume: IFC-Bench) unless asked as a QUALITY
_INSUL = (rf"({_INSUL_TERM}|(how well|how good|how (thermally )?efficient|kuinka hyvin|miten hyvin|wie gut|"
          r"comment|quanto bene|hur (bra|väl)|hoe goed|kui hea|qué tan( bien)?)\b.{0,30}\b(insulat\w*|eriste\w*|"
          r"eristy\w*|gedämmt|dämm\w*|isol\w*|soojust\w*|aislad\w*|aislamiento))")
_WHENW = (r"(what year|which year|when|vuonna|vuosi|milloin|jahr|wann|année|quand|anno|quando|år|när|jaar|wanneer|"
          r"aasta\w*|millal|año|cuándo|cuando|date|datum|how old|wie alt|kuinka vanha|quel âge|quanti anni|hur gammal|"
          r"hoe oud|kui vana|qué antigüedad)")
_BUILTW = (r"(built|constructed|construction|completed|erected|rakennettu|rakennettiin|valmistui|valmistunut|gebaut|"
           r"erbaut|errichtet|fertiggestellt|construit\w*|achevé|costruit\w*|completat\w*|byggd\w*|byggdes|uppförd\w*|"
           r"gebouwd|opgeleverd|ehitati|ehitatud|valmis|construy\w*|construid\w*|terminad\w*)")
_ENERGYW = (r"(energy|energi\w*|énergie|energia|energie|energía|kwh|kilowatt\w*|heat|heating|lämmit\w*|heiz\w*|"
            r"chauffage|riscaldamento|värme\w*|verwarming\w*|küte\w*|calefacción)")
_USEW = (r"(consum\w*|use|uses|used|usage|demand|need|kulut\w*|verbrauch\w*|bedarf|consomm\w*|consuma\w*|consumo|"
         r"använd\w*|förbruk\w*|gebruik\w*|verbruik\w*|tarbi\w*|kulu\w*)")
_PERYEAR = (r"(per year|a year|each year|annual\w*|yearly|vuodessa|vuosittain|jährlich|pro jahr|im jahr|par an|annuel\w*|"
            r"all'anno|annu\w*|per år|om året|årlig\w*|per jaar|jaarlijks|aastas|al año|anual\w*)")
_PERMONTH = (r"(per month|a month|each month|monthly|kuussa|kuukaudessa|kuukausi\w*|pro monat|im monat|monatlich\w*|"
             r"par mois|mensuel\w*|al mese|mensil\w*|per månad|i månaden|månatlig\w*|per maand|maandelijks|kuus|"
             r"kuu kohta|igakuu\w*|al mes|mensual\w*)")
_HOLD = (r"(hold|house|accommodat\w*|sisältää|majoittaa|aufnehmen|beherbergen|accueillir|loger|ospitare|accogliere|"
         r"innehålla|rymma|huisvesten|herbergen|hoida|mahutada|albergar|alojar)")
_PAINTW = (r"((re)?paint\w*|maalat\w*|maalaa\w*|maalau\w*|maalaus\w*|(neu )?streich\w*|anstreich\w*|anstrich\w*|"
           r"maler\w*|(re)?peind\w*|peinture\w*|(ri)?diping\w*|tinteggi\w*|imbianc\w*|måla\w*|målning\w*|"
           r"(over)?schilder\w*|verven|värvi\w*|pintar\w*|pintura\w*|repint\w*)")
_PCOST = (rf"({_COSTW[1:-1]}|cost\w*|kost\w*|coût\w*|maksa\w*|cuest\w*|price\w*|prix|preis\w*|hinta\w*|hinnan|"
          r"pris\w*|prijs\w*|hind\w*|precio\w*|prezzo\w*|budget\w*)")
_GENERAL = {
    "repaint": rf"\b{_PCOST}\b.{{0,60}}\b{_PAINTW}\b|\b{_PAINTW}\b.{{0,60}}\b{_PCOST}\b",
    "occupants": rf"\b{_COUNTW}\s+(\w+\s+){{0,2}}{_PEOPLE}\b|\b{_PEOPLE}\b.{{0,40}}\b{_HOLD}\b",
    "rent": rf"\b{_COSTW}\b.{{0,40}}\b{_PERMONTH}|\b{_PERMONTH}.{{0,30}}\b{_COSTW}\b|\bkuukausi(maksu|vuokra)\w*",
    "price": rf"\b{_MARKET}\W{{0,3}}{_VALUEW}|\b{_VALUEW}\b.{{0,30}}\b{_MARKET}\b|\b{_MARKET}\w*\b.{{0,30}}\b{_VALUEW}\b|"
             rf"\b(sell|sold|sale)\b.{{0,30}}\b(for|price)\b|\bprice point\b",
    "construction_cost": rf"\b{_COSTW}\b.{{0,50}}\b{_BUILDW}|\b{_BUILDW}\b.{{0,50}}\b{_COSTW}\b",
    "u_value": rf"\b{_INSUL}\b.{{0,50}}\b{_WALLW}\b|\b{_WALLW}\b.{{0,50}}\b{_INSUL_TERM}|"
               rf"\b(how well|how good|kuinka hyvin|miten hyvin|wie gut|quanto bene|hur (bra|väl)|hoe goed|kui hea|"
               rf"qué tan)\b.{{0,15}}\b{_WALLW}\b.{{0,30}}\b(insulat\w*|eriste\w*|eristy\w*|gedämmt|isol\w*|"
               rf"soojust\w*|aislad\w*)",
    "year_built": rf"\b{_WHENW}\b.{{0,50}}\b{_BUILTW}\b|\b(how old|wie alt|kuinka vanha|quel âge|quanti anni|"
                  rf"hur gammal|hoe oud|kui vana|qué antigüedad|age of|alter de[sr]|ikä|âge d\w*|età|ålder|leeftijd|"
                  rf"vanus|antigüedad|edad)\b.{{0,30}}\b(building|house|home|structure|gebäude|haus|hauses|rakennus\w*|"
                  rf"talo\w*|bâtiment|maison|edifici\w*|casa|byggnad\w*|hus|huset|gebouw|huis|hoone|maja|estructura)\b",
    "energy": rf"\b{_ENERGYW}\b.{{0,50}}\b{_USEW}\b.{{0,40}}\b{_PERYEAR}|\b{_PERYEAR}.{{0,50}}\b{_ENERGYW}|"
              rf"\b{_ENERGYW}\b.{{0,60}}\b{_PERYEAR}",
}
KINDS = [(k, f"(?:{p})|(?:{_GENERAL[k]})" if k in _GENERAL else p) for k, p in KINDS]
_KINDS = [(k, re.compile(p, re.I)) for k, p in KINDS]
# a question that STATES its own rate / constant is a derived quantity (answered exactly elsewhere): not ours
_STATED = re.compile(r"(\d[\d\s.,']*\s*(€|eur\w*|chf|fr\.?|francs?|\$|usd|dollars?|kr|sek|%|percent|prosent\w*|"
                     r"prozent|pour ?cent|per ?cento|procent\w*|kwh|w/|m²|m2|sq\.? ?(m|ft)|square|ft²|ft2|"
                     r"neliö\w*|quadratmeter|qm|mètres? carrés?|metri quadrati|kvadratmeter|vierkante|ruutmeet\w*)"
                     r"|[€$]\s*\d|\b(per|each|every|jokais\w*|kutakin|pro|je|par|chaque|ogni|varje|per|elke|iga)\s+"
                     r"(\w+\s+){0,2}(person|people|m²|m2|square|resident|henki\w*|asukas\w*|neliö\w*|bewohner|person\w*|"
                     r"habitant|abitant\w*|persona|inimene|inimese))", re.I)
_CAPACITY = re.compile(r"\b(could|can|might|would|max(imum)?|at most|sleep|accommodat\w*|fit|mahtuu|voi(si)? asua|"
                       r"könnte\w*|können|kann|maximal|pourrai\w*|peu(vent|t)|potrebbe\w*|possono|kan|skulle|"
                       r"zou(den)?|kunnen|saaks|mahub|podría\w*|pueden)\b", re.I)


_SPEC = re.compile(r"\b(specified|stated|noted|listed|given|shown|printed|according to|required|minimum|maximum "
                   r"allowed|per code|schedule|angegeben|vorgeschrieben|ilmoitettu|merkitty|vaadittu|indiqué|spécifié|"
                   r"indicato|specificat\w*|angiven|angivet|vermeld|aangegeven|märgitud|indicad\w*|especificad\w*)\b", re.I)


def kind_of(question: str) -> dict:
    q = " ".join(question.split())
    if _SPEC.search(q):
        return {"fire": False, "kind": None, "why": "asks for a value the drawing specifies (a reading, not an estimate)"}
    for k, rx in _KINDS:
        m = rx.search(q)
        if m:
            if _STATED.search(q):
                return {"fire": False, "kind": k, "why": f"{k} but the question states its own rate/constant (derived)"}
            return {"fire": True, "kind": k, "why": f"{k}: '{m.group(0)[:40]}'",
                    "capacity": bool(k == "occupants" and _CAPACITY.search(q))}
    return {"fire": False, "kind": None, "why": "no out-of-drawing kind"}


# ---------------------------------------------------------------------------------------------------------------
# reference rates by country of the dataset source (central, low, high) + source line
# ---------------------------------------------------------------------------------------------------------------
COUNTRY = {"cubicasa5k": "FI", "finna": "FI", "swiss_dwellings": "CH", "habs": "US", "opening_design": "US"}
CUR = {"FI": "EUR", "CH": "CHF", "US": "USD", "EU": "EUR"}
TO_EUR = {"EUR": 1.0, "CHF": 1.06, "USD": 0.90}  # assumed exchange rates (stated in the answer)
M2_PER_PERSON = {  # dwelling floor area per resident
    "FI": (41.7, 30.0, 60.0, "Statistics Finland, Finland in Figures: 41.7 m2 of floor area per person (2023)"),
    "CH": (46.6, 35.0, 65.0, "Swiss FSO: 46.6 m2 of living area per occupant (2021-2024)"),
    "US": (65.0, 40.0, 100.0, "US: ~2.5 persons per household in ~160 m2 homes (Census, rounded)"),
    "EU": (45.0, 30.0, 65.0, "EU-typical ~45 m2 per person (DE 47, FI 41.7, CH 46.6)"),
}
RENT = {  # local currency per m2 per month, non-subsidised
    "FI": (16.3, 12.0, 23.0, "Statistics Finland: non-subsidised rents 16.3 EUR/m2/month on average 2023 (Helsinki > 22)"),
    "CH": (19.0, 15.0, 25.0, "Swiss FSO: average rent CHF 1,485/month (2024), ~CHF 17-23/m2/month"),
    "US": (19.0, 12.0, 32.0, "US: ~USD 1.75/ft2/month (~19/m2) typical apartment rent"),
    "EU": (12.0, 7.0, 20.0, "EU-typical 7-20 EUR/m2/month"),
}
PRICE = {  # local currency per m2 (market value of a dwelling)
    "FI": (3300.0, 1500.0, 6500.0, "Statistics Finland: old dwellings in housing companies ~3,300 EUR/m2 nationally (Helsinki ~5,500)"),
    "CH": (8000.0, 5500.0, 13000.0, "Swiss condominium prices ~CHF 6,000-12,000/m2"),
    "US": (2500.0, 1300.0, 6000.0, "US median home ~USD 230/ft2 (~2,500/m2)"),
    "EU": (3500.0, 1500.0, 7000.0, "EU-typical 1,500-7,000 EUR/m2"),
}
BUILD = {  # local currency per m2 GROSS floor area, residential new build (today's money)
    "FI": (3500.0, 2600.0, 4800.0, "Finland: residential new-build ~2,600-4,800 EUR per gross m2"),
    "CH": (4000.0, 3000.0, 5500.0, "Switzerland: residential construction (BKP 2) ~CHF 3,000-5,500 per gross m2"),
    "US": (2200.0, 1500.0, 3500.0, "US: residential construction ~USD 150-320/ft2"),
    "EU": (3000.0, 2000.0, 4500.0, "EU-typical 2,000-4,500 EUR per gross m2"),
}
GROSS_PER_NET = 1.25  # gross floor area / net room area (walls, shafts, circulation share)
U_WALL = {  # W/m2K exterior wall
    "FI": (0.17, 0.15, 0.40, "Finnish energy decree 1010/2017: reference U 0.17 for new walls; 1970s-90s stock 0.25-0.40"),
    "CH": (0.17, 0.12, 0.40, "SIA 380/1 / MuKEn: limit 0.17 for new walls; older stock up to ~0.4+"),
    "US": (0.35, 0.25, 0.60, "US IECC wood-frame walls ~U 0.06 Btu (0.34 W/m2K); older stock higher"),
    "EU": (0.25, 0.15, 0.60, "EU new-build 0.15-0.30, older stock up to 0.6+"),
}
U_HISTORIC = (1.4, 0.8, 2.2, "uninsulated pre-1950 masonry/timber walls ~0.8-2.2 W/m2K")
PAINT = {  # local currency per m2 of painted SURFACE (labour + paint, 2 coats, VAT incl.); rules of thumb, not statistics
    "FI": (15.0, 10.0, 25.0, "assumed Finnish painter price ~10-25 EUR per m2 of wall (labour + paint, 2 coats)"),
    "CH": (30.0, 20.0, 45.0, "assumed Swiss painter price ~CHF 20-45 per m2 of wall (Malerarbeiten, 2 coats)"),
    "US": (30.0, 15.0, 55.0, "assumed US painter price ~USD 1.5-5 per ft2 of wall (~15-55 per m2)"),
    "EU": (15.0, 8.0, 30.0, "assumed EU-typical painter price 8-30 EUR per m2 of wall"),
}
# paintable wall surface per m2 of floor: square rooms of a m2, 2.6 m high, ~12% doors/windows ->
# 4 * 2.6 * sqrt(a) * 0.88 / a = 9.15 / sqrt(a): a = 10 -> 2.9, 15 -> 2.4, 20 -> 2.0, 25 -> 1.8; tiled wet rooms left out
WALL_PER_FLOOR = (2.4, 1.8, 3.2)
_CEIL = re.compile(r"\b(ceiling\w*|katto\w*|katot|katon|decke\w*|plafond\w*|soffitt\w*|tak|taket|taken|plafonds?|"
                   r"lagi|lae|techo\w*|cielo ?rasos?)\b", re.I)
_WALLS = re.compile(r"\b(walls?|seinä\w*|seinät|wand|wände\w*|murs?|pareti|parete|vägg\w*|muren|muur|seina\w*|"
                    r"seinte|paredes?)\b", re.I)
ENERGY = {  # kWh per m2 per year, space heating + hot water
    "FI": (130.0, 60.0, 220.0, "Finnish dwelling stock ~60-220 kWh/m2/a heating energy (newer < 100)"),
    "CH": (100.0, 40.0, 180.0, "Swiss stock ~40-180 kWh/m2/a (Minergie new builds ~40)"),
    "US": (110.0, 50.0, 200.0, "US residential ~50-200 kWh/m2/a (RECS)"),
    "EU": (120.0, 50.0, 220.0, "EU residential ~50-220 kWh/m2/a"),
}
YEAR = {  # construction year prior of the source's buildings
    "cubicasa5k": (1985, 1955, 2015, "Finnish apartment stock (CubiCasa5K: Finnish real-estate listings) mostly built 1955-2015"),
    "swiss_dwellings": (1990, 1950, 2020, "Swiss Dwellings: Swiss multi-family housing, mostly 1950-2020"),
    "ifc_models": (2015, 1990, 2024, "IFC models are mostly recent designs (BIM era)"),
    "ifc_bench": (2015, 1990, 2024, "IFC models are mostly recent designs (BIM era)"),
    "opening_design": (2015, 1990, 2024, "US practice drawing sets, mostly recent projects"),
}
MISSING = {
    "occupants": "who lives there is not recorded on a drawing: a population register / tenancy record would settle it",
    "rent": "rent is not on a drawing: a lease, rent roll or listing would settle it",
    "price": "price is not on a drawing: a sale record or listing would settle it",
    "construction_cost": "cost is not on a drawing: the project's final account / cost report would settle it",
    "u_value": "the wall build-up (layers, insulation thickness) or an energy certificate would settle it",
    "year_built": "the construction year is not printed here: a building permit, register entry or title block date would settle it",
    "energy": "an energy certificate or metered consumption would settle it",
    "repaint": "a painter's quote (or a stated rate) and the real wall areas (IFC wall faces or a room-by-room take-off) would settle it",
}
UNIT = {"occupants": "count", "rent": "{cur}/month", "price": "{cur}", "construction_cost": "{cur}",
        "u_value": "W/m2K", "year_built": "year", "energy": "kWh/year", "repaint": "{cur}"}
CONF = {"occupants": 0.2, "rent": 0.1, "price": 0.1, "construction_cost": 0.1, "u_value": 0.15, "year_built": 0.1,
        "energy": 0.1, "repaint": 0.1}


def _source(path: str) -> str:
    try:
        from stoa.data import source_of

        return source_of(path)
    except Exception:  # noqa: BLE001
        parts = Path(path).parts
        return parts[parts.index("data") + 1] if "data" in parts else ""


def _currency(question: str, country: str) -> str:
    q = question.lower()
    if re.search(r"\b(chf|francs?|franken|franchi)\b", q):
        return "CHF"
    if re.search(r"\b(usd|dollars?|\$)", q) or "$" in q:
        return "USD"
    if re.search(r"(€|\beur\w*|euro\w*)", q):
        return "EUR"
    return CUR.get(country, "EUR")


# ---------------------------------------------------------------------------------------------------------------
# what the drawing holds: dwelling floor area + bedrooms (deterministic, cached graphs)
# ---------------------------------------------------------------------------------------------------------------
_BED = re.compile(r"(bed ?room|schlaf\w*|makuu\w*|mh\b|sovrum|chambre|camera da letto|slaapkamer|magamis\w*|dormitorio)",
                  re.I)
_SCOPE_BUILDING = re.compile(r"\b(building|house|block|whole|entire|all apartments|gebäude|haus|rakennus\w*|talo\w*|"
                             r"byggnad\w*|huset|bâtiment|immeuble|edificio|palazzo|gebouw|hoone\w*)\b", re.I)
_APT = re.compile(r"\b(apartment|flat|unit|wohnung|asunto|lägenhet|appartement|logement|appartamento|woning|korter|"
                  r"piso|vivienda)\s+['\"]?([A-Z0-9]{1,3})\b['\"]?")


_AGE = re.compile(r"\b(how old|age of|wie alt|alter de[sr]|kuinka vanha|ikä|quel âge|âge d\w*|quanti anni|età|"
                  r"hur gammal|ålder|hoe oud|leeftijd|kui vana|vanus|qué antigüedad|antigüedad|edad)\b", re.I)
_GENERIC = re.compile(r"^(zimmer|pièce|piece|stanza|chambre|room|rum|huone)$", re.I)
_LIVING = re.compile(r"(wohn|séjour|sejour|soggiorno|living|vardagsrum|olohuone)", re.I)


def _swiss_bedrooms(rooms: list[dict], apts: list) -> int:
    """Swiss room names: explicit bedrooms (Schlafzimmer, Camera da letto, Chambre à coucher) + generic rooms
    (Zimmer / Pièce / Stanza); in an apartment with no named living room one generic room is the living room."""
    n = 0
    for a in (apts or [None]):
        rs = [r for r in rooms if a is None or r.get("apartment") == a]
        names = [str(r.get("name") or "") for r in rs]
        bed = sum(1 for x in names if _BED.search(x))
        gen = sum(1 for x in names if _GENERIC.match(x.strip()))
        liv = any(_LIVING.search(x) for x in names)
        n += bed + (gen if liv else max(0, gen - 1))
    return n


def dwelling(path: str, question: str) -> dict:
    """{'area': (m2, lo, hi) | None, 'bedrooms': int | None, 'how': str, 'evidence': [Evidence], 'n_dwellings': int}"""
    src = _source(path)
    out = {"area": None, "bedrooms": None, "how": "", "evidence": [], "n_dwellings": 1, "scope": "dwelling"}
    whole = bool(_SCOPE_BUILDING.search(question))
    try:
        if src == "swiss_dwellings":
            from stoa.kg.graph import links

            L = links(path)
            rooms = [r for r in L.get("rooms", []) if not r.get("outdoor") and not r.get("shaft")]
            apts = sorted({r.get("apartment") for r in rooms if r.get("apartment")})
            if apts and not whole:  # stairwells / lifts / cellars belong to no apartment
                rooms = [r for r in rooms if r.get("apartment")]
            m = _APT.search(question)
            pick = None
            if m and m.group(2).upper() in apts:
                pick = m.group(2).upper()
            if pick:
                rs, out["how"] = [r for r in rooms if r.get("apartment") == pick], f"apartment {pick}"
            elif whole or len(apts) <= 1:
                rs, out["scope"] = rooms, "building" if whole else "dwelling"
                out["how"] = f"the whole floor ({len(apts)} apartment(s); this building has one drawn floor)"
                out["n_dwellings"] = max(1, len(apts)) if whole else 1
            else:  # 'this apartment' on a floor with several: the mean apartment
                rs = rooms
                out["n_dwellings"] = len(apts)
                out["how"] = f"mean of the {len(apts)} apartments on this floor ({', '.join(apts)})"
            a = sum(r.get("area_m2_printed", r["area_m2_dxf"]) for r in rs)
            if out["n_dwellings"] > 1 and not whole:
                a /= out["n_dwellings"]
            out["area"] = (round(a, 1), round(a * 0.98, 1), round(a * 1.02, 1))
            out["how"] = f"{out['how']}: {a:.1f} m2 net from the DXF room polygons ({len(rs)} rooms)"
            nb = _swiss_bedrooms(rs, apts if not pick else [pick])
            out["bedrooms"] = (round(nb / out["n_dwellings"]) if out["n_dwellings"] > 1 and not whole else nb) or None
            if out["bedrooms"]:
                out["how"] += (f"; {out['bedrooms']} bedroom(s) (named bedrooms + generic 'Zimmer/Pièce/Stanza' rooms, "
                               "one per apartment taken as the living room when none is named)")
            out["evidence"] = [Evidence(file=path, page=0, bbox=r["bbox_pt"], bbox_space="pdf_pt",
                                        note=f"{r.get('number')} {r.get('name') or ''} {r['area_m2_dxf']} m2".strip())
                               for r in rs if r.get("bbox_pt")][:20]
        elif src in ("ifc_models", "ifc_bench"):
            from stoa.kg.graph import project_graph

            g = project_graph(path) or {}
            rooms = g.get("rooms", [])
            plan_rooms = [r for r in rooms if r.get("plan") == path]
            rs = rooms if (whole or path.endswith(".ifc") or not plan_rooms) else plan_rooms
            a = sum(float(r.get("area_m2") or 0) for r in rs)
            if a > 0:
                out["area"] = (round(a, 1), round(a * 0.98, 1), round(a * 1.02, 1))
                where = "the whole model" if rs is rooms else f"storey '{rs[0].get('storey_name')}'"
                out["how"] = f"{where}: {a:.1f} m2 net from {len(rs)} IfcSpace areas"
                out["scope"] = "building" if rs is rooms else "storey"
                nb = sum(1 for r in rs if _BED.search(f"{r.get('long_name') or ''} {r.get('name') or ''}"))
                out["bedrooms"] = nb or None
                if nb:
                    out["how"] += f"; {nb} bedroom space(s)"
                out["evidence"] = [Evidence(file=r["plan"], page=0, bbox=r["bbox_pt"], bbox_space="pdf_pt",
                                            note=f"{r.get('label') or r.get('name')} {float(r.get('area_m2') or 0):.1f} m2")
                                   for r in rs if r.get("bbox_pt") and r.get("plan")][:20]
        elif src == "cubicasa5k":
            from experiments.r1.room_graph.graph import room_graph

            g = room_graph(path, printed=True)
            rs = [r for r in g.get("rooms", []) if r.get("cls") != "outdoor"]
            pt = g.get("printed_total")
            if isinstance(pt, (int, float)) and pt > 0:
                out["area"] = (float(pt), float(pt) * 0.98, float(pt) * 1.02)
                out["how"] = f"{pt} m2 printed on the plan (apartment total)"
            else:
                s, lo, hi, np_ = 0.0, 0.0, 0.0, 0
                for r in rs:
                    pr = r.get("printed") or []
                    if pr:
                        v = sum(p["m2"] for p in pr)
                        s, lo, hi, np_ = s + v, lo + v, hi + v, np_ + 1
                    elif r.get("m2"):
                        b = r.get("m2_80") or [r["m2"], r["m2"]]
                        s, lo, hi = s + r["m2"], lo + b[0], hi + b[1]
                if s > 0:
                    out["area"] = (round(s, 1), round(lo, 1), round(hi, 1))
                    sc = (g.get("scale") or {}).get("assumptions") or []
                    out["how"] = (f"{s:.0f} m2 (80%: {lo:.0f}-{hi:.0f}) summed over {len(rs)} segmented rooms"
                                  f"{f', {np_} with printed areas' if np_ else ''}" + (f"; {sc[0]}" if sc and np_ < len(rs) else ""))
            nb = sum(1 for r in rs if r.get("cls") == "bedroom")
            out["bedrooms"] = nb or None
            if nb:
                out["how"] += f"; {nb} bedroom(s) in the segmentation/labels"
            out["evidence"] = [Evidence(file=path, bbox=r["bbox"], bbox_space="image_px",
                                        note=f"{r.get('label') or r.get('cls')} ~{r.get('m2')} m2")
                               for r in rs if r.get("bbox")][:20]
    except Exception as ex:  # noqa: BLE001 - a missing graph only means a wider prior
        out["how"] = f"no floor area read ({type(ex).__name__})"
    return out


# ---------------------------------------------------------------------------------------------------------------
# the estimate
# ---------------------------------------------------------------------------------------------------------------
def _round(kind: str, x: float) -> float | int:
    if kind in ("occupants", "year_built"):
        return int(round(x))
    if kind == "u_value":
        return round(x, 2)
    if kind == "rent":
        return int(round(x / 10.0) * 10)
    if kind in ("energy", "repaint"):
        return int(round(x / 100.0) * 100)
    return int(round(x / 1000.0) * 1000)


def _catalogue_year(path: str) -> tuple[int, int] | None:
    """A drawing date in the archive catalogue title (data/<source>/LICENSE.md), e.g. 'Site Plan (1935-1936)'."""
    try:
        from stoa.data import abspath

        lic = abspath(str(Path(path).parent / "LICENSE.md"))
        name = Path(path).name
        for line in lic.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(f"| {name} |"):
                yrs = [int(y) for y in re.findall(r"\b(1[5-9]\d\d|20[0-2]\d)\b", line.split("|")[2])]
                return (min(yrs), max(yrs)) if yrs else None
    except Exception:  # noqa: BLE001
        return None
    return None


def solve(path: str, question: str, kind: dict | None = None, as_text: bool = False) -> Answer | None:
    """as_text: the value is a sentence ("Not recorded on this drawing; estimate ~ 1,330 EUR/month (range ...)") for
    text-judged sources (IFC-Bench golds say "This information is not available ...")."""
    t0 = time.perf_counter()
    k = kind or kind_of(question)
    if not k.get("fire"):
        return None
    kind = k["kind"]
    src = _source(path)
    country = COUNTRY.get(src, "EU")
    cur = _currency(question, country)
    fx = TO_EUR[CUR.get(country, "EUR")] / TO_EUR[cur]  # local currency -> asked currency
    d = dwelling(path, question) if kind not in ("year_built", "u_value") else {"area": None, "bedrooms": None,
                                                                               "how": "", "evidence": [], "scope": ""}
    assumptions, trace = [], [f"estimate: {k['why']}; source {src} -> country {country}"]
    if d.get("how"):
        trace.append(f"drawing: {d['how']}")
    area = d.get("area")
    if area is None and kind in ("occupants", "rent", "price", "construction_cost", "energy", "repaint"):
        # no floor area read: a typical dwelling of the country, much wider
        typ = {"FI": 80.6, "CH": 95.0, "US": 150.0, "EU": 90.0}[country]
        area = (typ, typ * 0.5, typ * 1.8)
        assumptions.append(f"floor area not read from this drawing: assumed a typical dwelling of {typ:g} m2 "
                           f"(range {area[1]:.0f}-{area[2]:.0f})")
    elif area is not None:
        assumptions.append(f"floor area {area[0]:g} m2 ({d['how']})")
    if kind == "occupants":
        c, lo_r, hi_r, ref = M2_PER_PERSON[country]
        est = [area[0] / c]
        lo, hi = area[1] / hi_r, area[2] / lo_r
        b = d.get("bedrooms")
        if k.get("capacity"):
            if b:
                est = [2.0 * b]
                lo, hi = b, 2 * b + 1
                assumptions.append(f"capacity: 2 people per bedroom x {b} bedroom(s) (+1 on a sofa at most)")
            else:
                est = [area[0] / 20.0]
                assumptions.append("capacity: ~20 m2 per person when the bedroom count is unknown")
        else:
            assumptions.append(f"typical occupancy: {ref}")
            if b:
                nd = d.get("n_dwellings", 1) if d.get("scope") != "storey" else 1
                per = (b + nd) if d.get("scope") != "building" or nd > 1 else 1.3 * b
                est.append(float(per))
                lo, hi = min(lo, b), max(hi, 2 * b)
                assumptions.append(f"cross-check by bedrooms: {b} bedroom(s) -> about {per:.0f} people "
                                   "(one couple per dwelling + one person per other bedroom)")
        val = max(1.0, sum(est) / len(est))
        lo, hi = max(1.0, math.floor(lo)), max(1.0, math.ceil(hi))
    elif kind in ("rent", "price", "construction_cost", "energy"):
        table = {"rent": RENT, "price": PRICE, "construction_cost": BUILD, "energy": ENERGY}[kind]
        c, lo_r, hi_r, ref = table[country]
        g = GROSS_PER_NET if kind == "construction_cost" else 1.0
        if kind == "construction_cost":
            assumptions.append(f"gross floor area = net room area x {GROSS_PER_NET} (walls, shafts, circulation)")
        f = fx if kind != "energy" else 1.0
        val, lo, hi = area[0] * g * c * f, area[1] * g * lo_r * f, area[2] * g * hi_r * f
        assumptions.append(f"rate: {ref}")
        if f != 1.0:
            assumptions.append(f"currency: 1 {CUR[country]} = {TO_EUR[CUR[country]] / TO_EUR[cur]:.2f} {cur} (assumed)")
        if kind == "construction_cost" and src in ("habs", "finna", "europeana", "wikimedia"):
            assumptions.append("historical building: this is the cost to build it today, not what it cost then")
    elif kind == "repaint":
        c, lo_r, hi_r, ref = PAINT[country]
        ceil = bool(_CEIL.search(question))
        walls = bool(_WALLS.search(question)) or not ceil  # no surface named -> walls only
        wf, wlo, whi = WALL_PER_FLOOR if walls else (0.0, 0.0, 0.0)
        f, flo, fhi = wf + (1.0 if ceil else 0.0), wlo + (0.95 if ceil else 0.0), whi + (1.05 if ceil else 0.0)
        surf = area[0] * f
        what = " + ".join(x for x, on in (("walls", walls), ("ceilings", ceil)) if on)
        if walls:
            assumptions.append(f"painted wall area ~ {wf:g} x floor area (range {wlo:g}-{whi:g}): 2.6 m ceilings, "
                               "rooms of 10-20 m2, doors/windows and tiled wet-room walls left out")
        if ceil:
            assumptions.append("ceiling area = floor area")
        if not _CEIL.search(question) and not _WALLS.search(question):
            assumptions.append("walls only (ceilings not included)")
        assumptions.append(f"{what}: ~{surf:.0f} m2 to paint")
        val, lo, hi = surf * c * fx, area[1] * flo * lo_r * fx, area[2] * fhi * hi_r * fx
        assumptions.append(f"rate: {ref}")
        if fx != 1.0:
            assumptions.append(f"currency: 1 {CUR[country]} = {TO_EUR[CUR[country]] / TO_EUR[cur]:.2f} {cur} (assumed)")
    elif kind == "u_value":
        yrs = _catalogue_year(path) if src in ("habs", "finna", "europeana", "wikimedia") else None
        if src in ("habs", "europeana", "wikimedia", "finna") and (yrs is None or yrs[0] < 1960):
            val, lo, hi, ref = U_HISTORIC
            assumptions.append(f"historical drawing{f' dated {yrs[0]}' if yrs else ''}: {ref}")
        else:
            val, lo, hi, ref = U_WALL[country]
            assumptions.append(f"assumed built to the current energy code: {ref}")
    else:  # year_built
        yrs = _catalogue_year(path)
        if yrs:
            val, lo, hi = yrs[0], yrs[0] - 80, yrs[1]
            assumptions.append(f"the archive catalogue dates this drawing {yrs[0]}"
                               f"{'-' + str(yrs[1]) if yrs[1] != yrs[0] else ''}: built then or earlier "
                               "(measured drawings document existing buildings)")
        else:
            val, lo, hi, ref = YEAR.get(src, (1975, 1900, 2024, "no source prior: wide range"))
            assumptions.append(f"prior for this collection: {ref}")
    unit = UNIT[kind].format(cur=cur)
    if kind == "year_built" and _AGE.search(question):  # 'how old is it' asks for an age, not a year
        now = time.localtime().tm_year
        val, lo, hi = now - val, now - hi, now - lo
        unit = "years"
        assumptions.append(f"age = {now} - construction year")
    v, lo, hi = _round(kind, val), _round(kind, lo), _round(kind, hi)
    assumptions.insert(0, f"ESTIMATE, not read from the drawing: {v} {unit} (plausible range {lo}-{hi})")
    if d.get("scope") == "building" and kind in ("occupants", "rent", "price") and d.get("n_dwellings", 1) > 1:
        assumptions.append(f"scope: all {d['n_dwellings']} apartments of the floor together")
    trace.append(f"value {v} {unit}, range {lo}-{hi}; conf {CONF[kind]} (an estimate, not a reading)")
    if as_text:
        why = next((x for x in assumptions[1:] if x.startswith(("rate:", "typical occupancy", "assumed built",
                                                                "historical", "prior", "the archive", "capacity"))), "")
        v = (f"Not recorded on this drawing/model; estimate ~ {v:,} {unit} (plausible range {lo:,}-{hi:,})"
             + (f", {why}" if why else "") + f". {MISSING[kind][0].upper()}{MISSING[kind][1:]}.")
        unit = None
    return Answer(value=v, unit=unit, confidence=CONF[kind], evidence=d.get("evidence") or [], trace=trace,
                  solver="estimate", assumptions=assumptions, missing=[MISSING[kind]],
                  cost=Cost(wall_seconds=round(time.perf_counter() - t0, 4)))


if __name__ == "__main__":
    a = solve(sys.argv[1], sys.argv[2])
    print(kind_of(sys.argv[2]))
    print(a.model_dump_json(indent=1, exclude={"evidence"}) if a else None)
    if a:
        print(f"{len(a.evidence)} evidence boxes")
