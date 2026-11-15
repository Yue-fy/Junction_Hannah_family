# QA: language review (FI / SV), port 8405

Scope: every page at 390x844 in Suomi and Svenska (Alex, Sep 2026), plus these flows: "Why this amount", all categories, category drill-in, the how-it's-calculated links, assumptions, "More about your money", 6-month range, persona sheet, mortgage plus example, tax example, goal form, profile quiz, year review, topics. I also asked 3 Coach starters per language and spot-checked at 1280x800. Screenshots and text dumps are in `/home/claude/critique/qa-lang/` (`<lang>-390-<page>-N.png`, `flow-<lang>-390-<flow>-N.png`, `<lang>-coach-qN-0.png`, `*.txt`). I found no overflow or truncation at either size: the scripted check was clean and the screenshots show Finnish compounds such as "Asuntolainasuunnitelma" and "Yllätyspuskuri" wrapping cleanly. The problems are wording and consistency.

## P1

1. **English "Rent" in FI/SV.** It appears in Home "Miksi tämä summa?" / "Varför det här beloppet?" (row "Rent 5.10.", `flow-fi-390-why-0.png`) and in the Coach answer "Jo sivussa: laskut ennen palkkapäivää 528,38 € (Rent 5.10.)" / "(Rent 5 okt.)" (`fi-coach-q1.txt`, `sv-coach-q1.txt`). Cause: `scoach/forecast.py:472` stores `'label': labels['en']`, and `catalogue._bill_label()` (`scoach/catalogue.py:923-931`) only maps Utilities/housing_payment. The Home breakdown renders the same `label`. Fix: use `item['labels'][locale]` in both places (forecast already has `('Rent','Vuokra','Hyra')`).
2. **Plural after "1" is wrong.** FI has "Näytä 1 tapahtumaa ›" and "1 tapahtumaa", SV has "Visa 1 transaktioner ›" and "1 transaktioner" (`flow-*-390-cat.txt`, category drill-in on Spending). Fix: use plural rules (`Intl.PluralRules`): "Näytä 1 tapahtuma" / "Visa 1 transaktion".
3. **One buffer, six names.** FI uses Puskuri (Home bar), Turvatyyny, johon ei kosketa (why), turvatyynysi (Spending balance chart), Yllätyspuskuri, Puskurirahasto (Goals chip), Pieni turvatyyny / Hätärahastoosi (`forecast.py` HELD_BACK_LABELS). SV uses Buffert, Säkerhetsbuffert som lämnas orörd, säkerhetsmarginal, Överraskningsbuffert, En buffert, Liten säkerhetsmarginal. Also "Puskuri 705 €" on Home is the sum of 500 + 204,58, but the Coach says "lisäksi puskuri 500,00 €". Fix: pick two terms and use them everywhere. FI: **turvavara** (money you never touch) and **yllätyspuskuri** (irregular costs). SV: **säkerhetsbuffert** and **buffert för oväntade utgifter**. Label the Home bar item so it says it contains both.
4. **Category names differ between modules.** Spending and Coach use Liikenne / Transport / Restaurang / Nöjen. The forecast and plan (`forecast.py` CATEGORY_LABELS) use Liikkuminen / Resor och transport / Restauranger / Nöje. SV "Restaurang" (singular) is also wrong for a category. Fix: one table (`scoach/labels.py`) for everything. SV: "Restauranger", "Nöjen", "Transport".
5. **"Why this amount" math reads as contradictory.** The list ends "= 265,66 €" and the next line says "577,11 € jaettuna 15 päivälle on noin 38,47 €" (SV the same, `flow-*-why-0.png`). The 577 € is never shown in the list. Fix: add the row "Arjen perusmenot 311,45 € + käytettävissä 265,66 € = 577,11 € palkkapäivään asti", or say "Arjen menoihin ja vapaaseen käyttöön jää 577,11 € …".

## P2: awkward or machine-like phrasing

| Where | Now | Better |
|---|---|---|
| Home coach card FI | "Yllättäviä menoja, kuten hammaslääkäri tai korjaus, oli sinulla viime vuonna noin 398 € kuukaudessa. Pieni summa sivuun joka palkkapäivä, niin seuraava ei satu." | "Viime vuonna yllättäviin menoihin, kuten hammaslääkäriin ja korjauksiin, kului noin 398 € kuukaudessa. Kun laitat joka palkkapäivä pienen summan sivuun, seuraava yllätys ei kirpaise." |
| Home coach card SV | "Oväntade kostnader som tandläkare eller reparationer blev ungefär 398 € i månaden för dig förra året." | "Förra året lade du i snitt cirka 398 € i månaden på oväntade kostnader som tandläkare och reparationer." |
| Home SV | "4 777 € i överraskningar" | "4 777 € i oväntade utgifter" |
| Home month compare SV | "▲ 40 € jmf. aug." | "jfr aug." ("jmf." isn't standard Swedish), `web/home-v4.js:80` |
| Home month compare FI | "vrt. elo" (wraps to 2 lines at 390, `fi-390-home-1.png`) | "vrt. elokuu", or drop "vrt." and show "elokuuhun: ▲ 40 €" |
| Home month select FI | "syys 2026", while Spending shows "syyskuu 2026" | use the full month name in both |
| Goals FI | "Mitä haluaisit mahdollistaa?" | "Mihin haluaisit säästää?" |
| Goals SV | "Vad skulle du vilja göra möjligt?" | "Vad vill du spara till?" |
| Goals chips FI | "Puskurirahasto", "Matka, jota odottaa" | "Turvavara", "Unelmien matka" |
| Goal card FI | "Päivään 31.3.2027 mennessä" / "500,00 € tarvitaan kuukaudessa" | "31.3.2027 mennessä" / "Tarvitset 500 € kuukaudessa" |
| Goal card SV | "Till 31 mars 2027" / "500,00 € behövs per månad" / "Kan gå till det här målet nu, enligt din plan fram till lönedagen: 2 913,51 €." | "Senast 31 mars 2027" / "Du behöver spara 500 € i månaden" / "Enligt din lönedagsplan kan 2 913,51 € gå till målet nu." |
| Goal form | FI "Ajoneuvo" / SV "Ett fordon" | "Auto" / "En bil" |
| Mortgage example FI | "Jos korko nousee 1 prosenttiyksikön" (grammar error) | "…nousee 1 prosenttiyksiköllä" / "laskee … prosenttiyksiköllä" (`flow-fi-390-mortex-2.png`) |
| Mortgage example SV | "Om räntan stiger 1 procentenhet" | "…stiger med 1 procentenhet" |
| Mortgage example | "Maksettu maaliskuu 2047" / "Betalt mars 2047" | "Maksettu maaliskuussa 2047" (use the existing `{x:in}` filter) / "Betalt i mars 2047" |
| Mortgage example SV | "Första året är 46 % av det du betalar ränta" | "Första året går 46 % av det du betalar till ränta" |
| Mortgage form FI | "Laina-aikaa jäljellä (vuotta) (valinnainen)" | "Laina-aikaa jäljellä, vuotta (valinnainen)" |
| Tax example | FI "Näkymä" / SV "Utsikter" heading | "Ennuste" / "Prognos" |
| Tax example SV | "Skattekortets procent" | "Skatteprocent på skattekortet" |
| Spending SV howcalc | "Vi fortsätter din vanliga lön, hyra…" | "Vi räknar framåt med din vanliga lön, hyra, räkningar och vardagsutgifter." |
| Spending SV | "Snävaste dagen" | "Lägsta saldot" |
| Spending FI | "Pienin 3 541 €" | "Alin 3 541 €" |
| Spending FI | "Lisää rahoistasi" / "Ymmärrä ostosten arvonlisävero" | "Lisää raha-asioistasi" / "Ostostesi arvonlisävero" |
| Coach starter FI | "Miten vertaudun ikäisiini?" | "Miten pärjään ikäisiini verrattuna?" |
| Coach starter SV | "Vilken typ av spenderare är jag?" | "Hurdan är jag med pengar?" |
| Coach card FI | "Käyttövarasi palkkapäivään asti / 38,47 € / päivässä palkkapäivään 15.10.2026 asti" (says "asti" twice) | heading "Käyttövarasi", subline "päivässä palkkapäivään 15.10. asti" |
| Year review SV | "DITT ÅR I PENGAR / 2025 / i pengar" (said twice, `flow-sv-390-year-0.png`) | drop `label.intro` for SV, or use "Ditt år / 2025 / i siffror" (`web/year-review.js:63`); FI "rahan silmin" → "rahan näkökulmasta" or drop it |
| Profile SV | "Mellan jobb" | "Arbetssökande" |
| Persona sheet | "Päiväkirja" / "Dagbok" (EN "Journal") | "Tapahtumaloki" / "Händelselogg", if it is a dev log |
| Footer SV | "S-mobiili-koncept" | "Koncept för S-mobiili" |

**Formats and consistency (P2):**
- **"About" with cents.** Rounded and cent amounts are mixed in the same flow: Home "38 €" vs Coach "38,47 €", Me "noin 228 €" vs "227,74 € kuukaudessa", Goals "528,38 €" vs Me "528 €", Coach "noin 40,57 €" / "ungefär 269,29 €". Rule: amounts after "noin/ungefär" are whole euros, and exact figures only appear without "about". Goal card "500,00 €" / "3 000,00 €" should be "500 €" / "3 000 €", as on Home.
- **Thousands abbreviation on chart axes.** Axes read "1 t. €" (FI) and "1 tn €" (SV, `sv-390-spending-*`, mortgage "180 tn €"). "tn" means *ton* in Swedish. Use "1 000 €" / "180 000 €", or "t€" / "tusen €" (`web/charts.js:432`, `web/plans-mortgage.js:133`).
- **Capital letter after a colon.** "Tulojen tasaisuus: Suunnilleen samat…", "Säännöllinen sijoittaminen: Kyllä, …", SV "Hur jämn min inkomst är: Ungefär samma…" should be lowercase after the colon in FI/SV (Me page).
- **Date ranges.** SV "1 sep. 2026–30 sep. 2026" should be "1–30 sep. 2026". FI "1.9.2026–30.9.2026" should be "1.–30.9.2026". Number range "1 590 €–2 740 €" should be "1 590–2 740 €".
- **Day-of-month wording.** Goals "yleensä noin 5. päivä" vs Me "kuun 5. päivän tienoilla", and SV "runt den 5." vs "runt den 5:e". Pick "kuun 5. päivän tienoilla" and "runt den 5:e".
- **"How it's calculated" links.** Spending has both "Näin luku lasketaan" and "Miten tämä lasketaan?" (SV: "Så räknas siffran" / "Hur räknas det här ut?"). Use one phrasing.
- **Spending vs consumption.** The Coach says "Kulutus syyskuussa" while the page and tab say "Menot". The plan uses "Arjen perusmenot" next to the basket "Arjen pikkumenot", and SV uses "Vardagsutgifter" next to "Vardagens småutgifter": two near-identical names for different things. Rename the plan item "Ruoka ja liikkuminen" / "Mat och resor".
- **Coach footer.** It changes after the first answer, from "Luvut tarkistetaan tilitapahtumistasi · Pikavastaukset toimivat myös ilman tekoälyä" to "Pikavastaukset · Luvut tulevat tililtäsi". Keep one.
- **Desktop header.** "Kokeile esimerkkiä" / "Prova ett exempel" (the demo stories) clashes with "Katso esimerkki" / "Se ett exempel" (plan examples) on Goals (`sv-1280-goals-0.png`). Rename the header button "Kokeile tarinaa" / "Prova en berättelse", or "Demotarinat" / "Demohistorier".

## P3
- The seeded goal "A summer in Italy" is shown in English in FI/SV (it is user data in `base.sqlite3`). For demos, seed a neutral name or a localized one ("Kesä Italiassa" / "En sommar i Italien").
- Mortgage "Katso esimerkki ›" has a chevron and Tax "Katso esimerkki" has none. Make them match.
- Coach Q2 (peers) shows Ravintolat at 40,57 €/month on average, while Spending shows 225,70 € in September. That may be a category-mapping difference; it is worth a sanity check because users will compare the two.
- Topics sheet: one group shows "3 kysymystä" with no title in the text dump (`flow-fi-390-topics.txt`). Check that every topic group has a heading.
- Wording that works well: "Palkkapäivään 15 päivää · to 15.10.", "Lönedag om 15 dagar · tors 15 okt.", "MinSkatt"/"OmaVero", 9,6 %-style percentages with a space, "1 138,27 €"-style amounts, and Finnish inessive months in the Coach ("syyskuussa 2026").

## Top 8
1. P1 English "Rent" in the Home "why" breakdown and the Coach answer, FI and SV (`catalogue._bill_label`, `forecast.py:472` uses `labels['en']`).
2. P1 "Näytä 1 tapahtumaa" / "Visa 1 transaktioner": plural agreement on the category drill-in.
3. P1 Buffer has six different names per language, and the Home "Puskuri 705 €" doesn't match the Coach's "puskuri 500 €".
4. P1 Category names differ between Spending/Coach (`labels.py`) and the plan/forecast (`forecast.py` CATEGORY_LABELS); SV "Restaurang" should be plural.
5. P1 The "why" list ends at 265,66 € but the next line divides 577,11 €; the 577 € is never shown.
6. P2 SV "1 tn €" (means ton) and FI "1 t. €" on chart axes; SV "jmf." should be "jfr".
7. P2 FI grammar errors "nousee 1 prosenttiyksikön" and "Maksettu maaliskuu 2047" (should be prosenttiyksiköllä / maaliskuussa); SV needs "stiger med" and "Betalt i".
8. P2 Mixed "about" + cents and rounded/exact amounts (38 € vs 38,47 €, 228 vs 227,74, 500,00 €). Use whole euros after noin/ungefär and with goal amounts.
