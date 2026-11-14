export const SUPPORTED_LOCALES = Object.freeze(['en', 'fi', 'sv']);
export const STORAGE_KEY = 'scoach.locale';

const EN = {
  'app.skip': 'Skip to your money',
  'app.prototype': 'Prototype',
  'app.disclosure': 'S-mobiili concept · Synthetic demo data · Planning support, with you in control.',
  'language.label': 'Language',
  'language.en': 'English',
  'language.fi': 'Finnish',
  'language.sv': 'Swedish',
  'persona.open': 'Choose demo customer',
  'persona.label': 'Demo customer',
  'persona.description': 'Synthetic accounts. Coach context is saved only on this demo server.',
  'persona.reset': 'Reset this customer’s demo',
  'navigation.label': 'Main navigation',
  'nav.home': 'Home',
  'nav.trends': 'Trends',
  'nav.goals': 'Goals',
  'action.close': 'Close',
  'action.retry': 'Try again',
  'action.details': 'Show details',
  'action.seeNumbers': 'See the numbers',
  'action.askCoach': 'Ask coach',
  'action.send': 'Send question',
  'action.reset': 'Reset',
  'action.undo': 'Undo last change',
  'common.observed': 'Observed',
  'common.scenario': 'Scenario',
  'common.estimate': 'Estimate',
  'common.completeMonths': 'Complete months',
  'common.perMonth': 'per month',
  'common.account': 'Account',
  'common.period': 'Period',
  'common.status': 'Status',
  'home.eyebrow': 'Your everyday money, made clearer',
  'home.title': 'A fresh view of your money',
  'home.subtitle': 'Start with what matters now.',
  'home.priority.title': 'Worth a quick look',
  'home.priority.loading': 'Finding a useful next step…',
  'home.priority.description': 'We use your transactions to find one manageable action.',
  'home.priority.open': 'Take a closer look',
  'home.priority.basis': 'Based on your own activity',
  'period.month.label': 'Month',
  'period.month.help': 'Choose a complete month from this account.',
  'period.range.label': 'Time range',
  'period.range.3': 'Last 3 months',
  'period.range.6': 'Last 6 months',
  'period.range.12': 'Last 12 months',
  'period.range.24': 'Last 24 months',
  'money.title': 'This month at a glance',
  'money.balance': 'Available now',
  'money.loading': 'Loading your account…',
  'money.where': 'Where the money went',
  'money.income': 'Income',
  'basket.regular': 'Regular essentials',
  'basket.regular.help': 'Recurring needs such as housing, utilities, groceries and everyday transport.',
  'basket.irregular': 'Irregular essentials',
  'basket.irregular.help': 'Necessary but less regular costs, such as healthcare or replacing a broken appliance.',
  'basket.everyday': 'Everyday spending',
  'basket.everyday.help': 'Choices such as restaurants, entertainment and travel.',
  'basket.saving': 'Saving and transfers',
  'basket.saving.help': 'Money moved to savings or investments, kept separate from spending.',
  'forecast.title': 'What may happen next',
  'forecast.subtitle': 'A 30-day cash-flow estimate using qualified recurring patterns from your history.',
  'forecast.assumptions': 'Review assumptions',
  'forecast.disclaimer': 'This is a planning estimate, not a promise or a probability.',
  'trends.eyebrow': 'Look back and understand',
  'trends.title': 'Your patterns',
  'trends.subtitle': 'Compare complete periods on the same basis.',
  'trends.monthByMonth': 'Month by month',
  'trends.whatChanged': 'What changed?',
  'trends.sameMonth': 'Same month, last year',
  'trends.salary': 'Salary, on its own',
  'goals.eyebrow': 'Make room for what matters',
  'goals.title': 'Your goals',
  'goals.subtitle': 'Choose the goal and explore a realistic pace.',
  'goals.empty': 'You have not created a goal yet.',
  'goal.form.title': 'Create a goal',
  'goal.template': 'Start with',
  'goal.template.custom': 'My own goal',
  'goal.template.buffer': 'Emergency buffer',
  'goal.template.trip': 'A trip',
  'goal.template.vehicle': 'A vehicle',
  'goal.template.home': 'A home',
  'goal.template.purchase': 'A large purchase',
  'goal.name': 'What are you saving for?',
  'goal.target': 'Target',
  'goal.saved': 'Already saved',
  'goal.date': 'Target date',
  'goal.reserve': 'Amount to keep as a reserve',
  'goal.create': 'Create my plan',
  'goal.disclosure': 'This is a planning scenario. It does not create a transfer.',
  'coach.eyebrow': 'Your money in plain language',
  'coach.title': 'Ask your coach',
  'coach.greeting': 'What would you like to understand? We can take it one step at a time.',
  'coach.input.label': 'Your question',
  'coach.input.placeholder': 'Ask about your money…',
  'coach.verified': 'Verified calculations · Offline coaching available',
  'coach.otherLanguage': 'Finnish, Swedish and English work offline. Questions in other languages require configured AI; this does not change the interface language.',
  'loading.account': 'Loading your account…',
  'loading.insight': 'Looking for a useful insight…',
  'loading.coach': 'Checking your numbers…',
  'empty.transactions': 'No transactions match this selection.',
  'empty.trends': 'There are not enough complete months for this view yet.',
  'empty.goals': 'No goals yet. Create one when you are ready.',
  'empty.flow': 'No money flow is available for this period.',
  'error.generic': 'Something went wrong. Your bank data was not changed.',
  'error.network': 'We could not connect. Check the local demo server and try again.',
  'error.database': 'The demo data is not ready yet.',
  'error.period': 'That period is outside this account’s available history.',
  'error.customer': 'This demo customer is not available.',
  'error.validation': 'Check the highlighted information and try again.',
  'safe.title': 'Safe to spend',
  'safe.amount': 'Estimated amount for the next {days} days',
  'safe.horizon': 'Until {date}',
  'safe.reserve': 'Reserve kept aside',
  'safe.obligations': 'Known bills kept aside',
  'safe.everydayAllowance': 'Everyday spending allowance kept aside',
  'safe.evidence': 'See what is included',
  'safe.disclaimer': 'This is an estimate, not a guarantee. New or unusual costs can change it.',
  'investment.title': 'Saving and investment transfers',
  'investment.contributions': 'Moved to investments',
  'investment.withdrawals': 'Moved back from investments',
  'investment.salarySweep': 'Moved automatically from salary',
  'investment.consistency': 'Months with a contribution',
  'investment.noData': 'No investment transfers were found in this period.',
  'investment.limitation': 'This shows account transfers only. It cannot show holdings, returns, risk or investment advice.',
};

const FI = {
  'app.skip': 'Siirry raha-asioihin',
  'app.prototype': 'Prototyyppi',
  'app.disclosure': 'S-mobiili-konsepti · Synteettinen demodata · Suunnittelun tueksi, sinä päätät.',
  'language.label': 'Kieli',
  'language.en': 'Englanti',
  'language.fi': 'Suomi',
  'language.sv': 'Ruotsi',
  'persona.open': 'Valitse demoasiakas',
  'persona.label': 'Demoasiakas',
  'persona.description': 'Tilit ovat synteettisiä. Valmentajan tiedot tallennetaan vain tälle demopalvelimelle.',
  'persona.reset': 'Palauta tämän asiakkaan demo',
  'navigation.label': 'Päänavigointi',
  'nav.home': 'Etusivu',
  'nav.trends': 'Kehitys',
  'nav.goals': 'Tavoitteet',
  'action.close': 'Sulje',
  'action.retry': 'Yritä uudelleen',
  'action.details': 'Näytä tiedot',
  'action.seeNumbers': 'Katso luvut',
  'action.askCoach': 'Kysy valmentajalta',
  'action.send': 'Lähetä kysymys',
  'action.reset': 'Palauta',
  'action.undo': 'Kumoa viimeisin muutos',
  'common.observed': 'Toteutunut',
  'common.scenario': 'Skenaario',
  'common.estimate': 'Arvio',
  'common.completeMonths': 'Täydet kuukaudet',
  'common.perMonth': 'kuukaudessa',
  'common.account': 'Tili',
  'common.period': 'Ajanjakso',
  'common.status': 'Tila',
  'home.eyebrow': 'Selkeämpi kuva arjen rahasta',
  'home.title': 'Tuore näkymä raha-asioihisi',
  'home.subtitle': 'Aloita siitä, mikä on nyt tärkeää.',
  'home.priority.title': 'Tämä kannattaa vilkaista',
  'home.priority.loading': 'Etsitään hyödyllistä seuraavaa askelta…',
  'home.priority.description': 'Etsimme tapahtumistasi yhden hallittavan seuraavan askeleen.',
  'home.priority.open': 'Katso tarkemmin',
  'home.priority.basis': 'Perustuu omaan tilitoimintaasi',
  'period.month.label': 'Kuukausi',
  'period.month.help': 'Valitse täysi kuukausi tältä tililtä.',
  'period.range.label': 'Aikaväli',
  'period.range.3': 'Viimeiset 3 kuukautta',
  'period.range.6': 'Viimeiset 6 kuukautta',
  'period.range.12': 'Viimeiset 12 kuukautta',
  'period.range.24': 'Viimeiset 24 kuukautta',
  'money.title': 'Kuukausi yhdellä silmäyksellä',
  'money.balance': 'Käytettävissä nyt',
  'money.loading': 'Ladataan tiliäsi…',
  'money.where': 'Mihin raha meni',
  'money.income': 'Tulot',
  'basket.regular': 'Säännölliset pakolliset menot',
  'basket.regular.help': 'Toistuvat välttämättömät menot, kuten asuminen, sähkö, ruokaostokset ja liikkuminen.',
  'basket.irregular': 'Epäsäännölliset pakolliset menot',
  'basket.irregular.help': 'Tarpeelliset mutta harvemmin toistuvat kulut, kuten terveydenhoito tai rikkoutuneen kodinkoneen korvaaminen.',
  'basket.everyday': 'Arjen menot',
  'basket.everyday.help': 'Valinnat, kuten ravintolat, viihde ja matkailu.',
  'basket.saving': 'Säästöt ja siirrot',
  'basket.saving.help': 'Säästöihin tai sijoituksiin siirretty raha, erillään kulutuksesta.',
  'forecast.title': 'Mitä voi tapahtua seuraavaksi',
  'forecast.subtitle': '30 päivän kassavirta-arvio historian perusteella tunnistetuista toistuvista tapahtumista.',
  'forecast.assumptions': 'Tarkista oletukset',
  'forecast.disclaimer': 'Tämä on suunnitteluarvio, ei lupaus eikä todennäköisyys.',
  'trends.eyebrow': 'Katso taakse ja ymmärrä',
  'trends.title': 'Omat tapasi',
  'trends.subtitle': 'Vertaa kokonaisia ajanjaksoja samoilla perusteilla.',
  'trends.monthByMonth': 'Kuukausi kuukaudelta',
  'trends.whatChanged': 'Mikä muuttui?',
  'trends.sameMonth': 'Sama kuukausi viime vuonna',
  'trends.salary': 'Palkka erikseen',
  'goals.eyebrow': 'Tee tilaa tärkeälle',
  'goals.title': 'Tavoitteesi',
  'goals.subtitle': 'Valitse tavoite ja kokeile realistista tahtia.',
  'goals.empty': 'Et ole vielä luonut tavoitetta.',
  'goal.form.title': 'Luo tavoite',
  'goal.template': 'Aloita tästä',
  'goal.template.custom': 'Oma tavoite',
  'goal.template.buffer': 'Puskurirahasto',
  'goal.template.trip': 'Matka',
  'goal.template.vehicle': 'Ajoneuvo',
  'goal.template.home': 'Koti',
  'goal.template.purchase': 'Suuri hankinta',
  'goal.name': 'Mihin säästät?',
  'goal.target': 'Tavoitesumma',
  'goal.saved': 'Säästetty jo',
  'goal.date': 'Tavoitepäivä',
  'goal.reserve': 'Puskuriksi jätettävä summa',
  'goal.create': 'Luo suunnitelma',
  'goal.disclosure': 'Tämä on suunnitteluskenaario. Se ei tee tilisiirtoa.',
  'coach.eyebrow': 'Rahasi selkokielellä',
  'coach.title': 'Kysy valmentajalta',
  'coach.greeting': 'Mitä haluaisit ymmärtää? Edetään yksi askel kerrallaan.',
  'coach.input.label': 'Kysymyksesi',
  'coach.input.placeholder': 'Kysy raha-asioistasi…',
  'coach.verified': 'Tarkistetut laskelmat · Valmennus toimii myös ilman verkkoyhteyttä',
  'coach.otherLanguage': 'Suomi, ruotsi ja englanti toimivat ilman tekoälyä. Muunkieliset kysymykset vaativat käyttöön otetun tekoälyn. Tekoäly ei vaihda käyttöliittymän kieltä.',
  'loading.account': 'Ladataan tiliäsi…',
  'loading.insight': 'Etsitään hyödyllistä havaintoa…',
  'loading.coach': 'Tarkistetaan lukuja…',
  'empty.transactions': 'Tähän valintaan sopivia tapahtumia ei ole.',
  'empty.trends': 'Tähän näkymään ei ole vielä tarpeeksi kokonaisia kuukausia.',
  'empty.goals': 'Ei vielä tavoitteita. Luo tavoite, kun olet valmis.',
  'empty.flow': 'Tältä ajalta ei ole rahavirtaa.',
  'error.generic': 'Jokin meni vikaan. Pankkitietojasi ei muutettu.',
  'error.network': 'Yhteys ei onnistunut. Tarkista paikallinen demopalvelin ja yritä uudelleen.',
  'error.database': 'Demodata ei ole vielä valmis.',
  'error.period': 'Ajanjakso ei kuulu tämän tilin saatavilla olevaan historiaan.',
  'error.customer': 'Tämä demoasiakas ei ole saatavilla.',
  'error.validation': 'Tarkista merkityt tiedot ja yritä uudelleen.',
  'safe.title': 'Turvallisesti käytettävissä',
  'safe.amount': 'Arvio seuraavalle {days} päivälle',
  'safe.horizon': 'Päivään {date} asti',
  'safe.reserve': 'Sivuun jätetty puskuri',
  'safe.obligations': 'Sivuun jätetyt tiedossa olevat laskut',
  'safe.everydayAllowance': 'Sivuun jätetty arjen käyttövara',
  'safe.evidence': 'Katso, mitä arvio sisältää',
  'safe.disclaimer': 'Tämä on arvio, ei takuu. Uudet tai poikkeavat kulut voivat muuttaa sitä.',
  'investment.title': 'Säästö- ja sijoitussiirrot',
  'investment.contributions': 'Siirretty sijoituksiin',
  'investment.withdrawals': 'Siirretty takaisin sijoituksista',
  'investment.salarySweep': 'Siirretty automaattisesti palkasta',
  'investment.consistency': 'Kuukaudet, joina teit siirron',
  'investment.noData': 'Tältä ajalta ei löytynyt sijoitussiirtoja.',
  'investment.limitation': 'Tämä näyttää vain tilisiirrot. Se ei kerro omistuksista, tuotoista tai riskeistä eikä anna sijoitusneuvoja.',
};

const SV = {
  'app.skip': 'Gå till din ekonomi',
  'app.prototype': 'Prototyp',
  'app.disclosure': 'S-mobiili-koncept · Syntetiska demodata · Stöd för planering, du bestämmer.',
  'language.label': 'Språk',
  'language.en': 'Engelska',
  'language.fi': 'Finska',
  'language.sv': 'Svenska',
  'persona.open': 'Välj demokund',
  'persona.label': 'Demokund',
  'persona.description': 'Kontona är syntetiska. Coachens uppgifter sparas endast på den här demoservern.',
  'persona.reset': 'Återställ den här kundens demo',
  'navigation.label': 'Huvudnavigering',
  'nav.home': 'Start',
  'nav.trends': 'Utveckling',
  'nav.goals': 'Mål',
  'action.close': 'Stäng',
  'action.retry': 'Försök igen',
  'action.details': 'Visa detaljer',
  'action.seeNumbers': 'Se siffrorna',
  'action.askCoach': 'Fråga coachen',
  'action.send': 'Skicka frågan',
  'action.reset': 'Återställ',
  'action.undo': 'Ångra senaste ändringen',
  'common.observed': 'Utfall',
  'common.scenario': 'Scenario',
  'common.estimate': 'Uppskattning',
  'common.completeMonths': 'Hela månader',
  'common.perMonth': 'per månad',
  'common.account': 'Konto',
  'common.period': 'Period',
  'common.status': 'Status',
  'home.eyebrow': 'Tydligare bild av vardagsekonomin',
  'home.title': 'En ny bild av din ekonomi',
  'home.subtitle': 'Börja med det som är viktigt nu.',
  'home.priority.title': 'Värt en snabb titt',
  'home.priority.loading': 'Vi letar efter ett användbart nästa steg…',
  'home.priority.description': 'Vi använder dina transaktioner för att hitta ett hanterbart nästa steg.',
  'home.priority.open': 'Titta närmare',
  'home.priority.basis': 'Bygger på din egen kontoaktivitet',
  'period.month.label': 'Månad',
  'period.month.help': 'Välj en hel månad från det här kontot.',
  'period.range.label': 'Tidsintervall',
  'period.range.3': 'Senaste 3 månaderna',
  'period.range.6': 'Senaste 6 månaderna',
  'period.range.12': 'Senaste 12 månaderna',
  'period.range.24': 'Senaste 24 månaderna',
  'money.title': 'Månaden i korthet',
  'money.balance': 'Tillgängligt nu',
  'money.loading': 'Ditt konto laddas…',
  'money.where': 'Vart pengarna gick',
  'money.income': 'Inkomster',
  'basket.regular': 'Regelbundna nödvändiga utgifter',
  'basket.regular.help': 'Återkommande behov som boende, el, matvaror och vardagstransport.',
  'basket.irregular': 'Oregelbundna nödvändiga utgifter',
  'basket.irregular.help': 'Nödvändiga men mer sällan återkommande kostnader, som vård eller att ersätta en trasig hushållsmaskin.',
  'basket.everyday': 'Vardagsutgifter',
  'basket.everyday.help': 'Val som restauranger, nöjen och resor.',
  'basket.saving': 'Sparande och överföringar',
  'basket.saving.help': 'Pengar som flyttats till sparande eller investeringar, skilt från konsumtion.',
  'forecast.title': 'Vad som kan hända härnäst',
  'forecast.subtitle': 'En 30-dagars kassaflödesuppskattning med kvalificerade återkommande mönster från din historik.',
  'forecast.assumptions': 'Granska antaganden',
  'forecast.disclaimer': 'Detta är en uppskattning för planering, inte ett löfte eller en sannolikhet.',
  'trends.eyebrow': 'Se tillbaka och förstå',
  'trends.title': 'Dina mönster',
  'trends.subtitle': 'Jämför hela perioder på samma grund.',
  'trends.monthByMonth': 'Månad för månad',
  'trends.whatChanged': 'Vad förändrades?',
  'trends.sameMonth': 'Samma månad förra året',
  'trends.salary': 'Lön, visad separat',
  'goals.eyebrow': 'Ge plats åt det viktiga',
  'goals.title': 'Dina mål',
  'goals.subtitle': 'Välj mål och utforska en realistisk takt.',
  'goals.empty': 'Du har inte skapat något mål ännu.',
  'goal.form.title': 'Skapa ett mål',
  'goal.template': 'Börja med',
  'goal.template.custom': 'Eget mål',
  'goal.template.buffer': 'Buffert för oväntade utgifter',
  'goal.template.trip': 'En resa',
  'goal.template.vehicle': 'Ett fordon',
  'goal.template.home': 'Ett hem',
  'goal.template.purchase': 'Ett stort inköp',
  'goal.name': 'Vad sparar du till?',
  'goal.target': 'Målbelopp',
  'goal.saved': 'Redan sparat',
  'goal.date': 'Måldatum',
  'goal.reserve': 'Belopp att behålla som buffert',
  'goal.create': 'Skapa min plan',
  'goal.disclosure': 'Detta är ett planeringsscenario. Ingen överföring skapas.',
  'coach.eyebrow': 'Din ekonomi på klarspråk',
  'coach.title': 'Fråga din coach',
  'coach.greeting': 'Vad vill du förstå? Vi kan ta ett steg i taget.',
  'coach.input.label': 'Din fråga',
  'coach.input.placeholder': 'Fråga om din ekonomi…',
  'coach.verified': 'Kontrollerade beräkningar · Coaching fungerar även utan nätanslutning',
  'coach.otherLanguage': 'Finska, svenska och engelska fungerar utan AI. Frågor på andra språk kräver konfigurerad AI. AI ändrar inte gränssnittets språk.',
  'loading.account': 'Ditt konto laddas…',
  'loading.insight': 'Vi letar efter en användbar insikt…',
  'loading.coach': 'Vi kontrollerar siffrorna…',
  'empty.transactions': 'Inga transaktioner passar det här urvalet.',
  'empty.trends': 'Det finns ännu inte tillräckligt många hela månader för den här vyn.',
  'empty.goals': 'Inga mål ännu. Skapa ett när du är redo.',
  'empty.flow': 'Det finns inget kassaflöde för den här perioden.',
  'error.generic': 'Något gick fel. Dina bankuppgifter ändrades inte.',
  'error.network': 'Anslutningen misslyckades. Kontrollera den lokala demoservern och försök igen.',
  'error.database': 'Demodata är inte klara ännu.',
  'error.period': 'Perioden ligger utanför den tillgängliga historiken för kontot.',
  'error.customer': 'Den här demokunden är inte tillgänglig.',
  'error.validation': 'Kontrollera de markerade uppgifterna och försök igen.',
  'safe.title': 'Tryggt att spendera',
  'safe.amount': 'Uppskattat belopp för de nästa {days} dagarna',
  'safe.horizon': 'Till och med {date}',
  'safe.reserve': 'Buffert som lagts åt sidan',
  'safe.obligations': 'Kända räkningar som lagts åt sidan',
  'safe.everydayAllowance': 'Vardagsutrymme som lagts åt sidan',
  'safe.evidence': 'Se vad som ingår',
  'safe.disclaimer': 'Detta är en uppskattning, inte en garanti. Nya eller ovanliga utgifter kan ändra den.',
  'investment.title': 'Spar- och investeringsöverföringar',
  'investment.contributions': 'Överfört till investeringar',
  'investment.withdrawals': 'Överfört tillbaka från investeringar',
  'investment.salarySweep': 'Överfört automatiskt från lön',
  'investment.consistency': 'Månader med en överföring',
  'investment.noData': 'Inga investeringsöverföringar hittades under perioden.',
  'investment.limitation': 'Detta visar bara kontoöverföringar. Det visar inte innehav, avkastning eller risk och ger inga investeringsråd.',
};

const JOURNEY_MESSAGES = {
  "coach.requestFuture": ["Show cash flow", "Näytä kassavirta", "Visa kassaflöde"],
  "category.restaurants": ["Restaurants", "Ravintolat", "Restauranger"],
  "basket.income.help": [
    "Money received, such as salary and other income.",
    "Saadut rahat, kuten palkka ja muut tulot.",
    "Pengar du fått, till exempel lön och andra inkomster."
  ],
  "basket.review": [
    "Needs review",
    "Tarkistettavaa",
    "Behöver granskas"
  ],
  "basket.review.help": [
    "Activity that needs your context before it can be grouped.",
    "Tapahtumat, joiden ryhmittelyyn tarvitaan tietojasi.",
    "Transaktioner som behöver ditt sammanhang innan de grupperas."
  ],
  "home.noticed": [
    "Your coach noticed",
    "Valmentajasi huomasi",
    "Din coach lade märke till"
  ],
  "home.demoHeadline": [
    "Restaurant spending rose {amount} in September.",
    "Ravintolamenot kasvoivat {amount} syyskuussa.",
    "Restaurangutgifterna ökade med {amount} i september."
  ],
  "home.demoDescription": [
    "You went out the same number of times. A closer look can help you find a comfortable next step.",
    "Kävit ravintolassa yhtä monta kertaa. Tarkempi katsaus auttaa löytämään sopivan seuraavan askeleen.",
    "Du gick ut lika många gånger. En närmare titt kan hjälpa dig att hitta ett lämpligt nästa steg."
  ],
  "home.genericHeadline": [
    "Restaurant spending changed by {amount} in {period}.",
    "Ravintolamenojen muutos: {amount}, {period}.",
    "Restaurangutgifterna förändrades med {amount} i {period}."
  ],
  "home.genericDescription": [
    "Compare the purchase count and average to understand the change.",
    "Vertaa ostojen määrää ja keskiostosta ymmärtääksesi muutoksen.",
    "Jämför antal köp och genomsnitt för att förstå förändringen."
  ],
  "home.noComparison": [
    "Explore this month's money flow",
    "Tutustu kuukauden rahavirtaan",
    "Utforska månadens pengaflöde"
  ],
  "home.noComparisonHelp": [
    "A full comparison is not available for this period. Your account activity is still available below.",
    "Täyttä vertailua ei ole saatavilla tälle ajalle. Tilin tapahtumat näkyvät alla.",
    "En fullständig jämförelse saknas för perioden. Kontoaktiviteten finns nedan."
  ],
  "story.eyebrow": [
    "A little more clarity",
    "Hieman lisää selkeyttä",
    "Lite mer klarhet"
  ],
  "story.title": [
    "What changed in restaurant spending?",
    "Mikä ravintolamenoissa muuttui?",
    "Vad förändrades i restaurangutgifterna?"
  ],
  "story.sameTitle": [
    "Same number of meals. A little more each time.",
    "Yhtä monta ateriaa. Hieman enemmän kerralla.",
    "Lika många måltider. Lite mer varje gång."
  ],
  "story.change": [
    "{current} compared with {previous}: {amount} change.",
    "{current} verrattuna jaksoon {previous}: muutos {amount}.",
    "{current} jämfört med {previous}: förändring {amount}."
  ],
  "story.sameCount": [
    "The same number of purchases.",
    "Yhtä monta ostoa.",
    "Lika många köp."
  ],
  "story.changedCount": [
    "Purchase count changed by {count}.",
    "Ostojen määrä muuttui: {count}.",
    "Antalet köp förändrades med {count}."
  ],
  "story.count": [
    "Purchase count",
    "Ostojen määrä",
    "Antal köp"
  ],
  "story.average": [
    "Average purchase",
    "Keskiostos",
    "Genomsnittligt köp"
  ],
  "story.averageObserved": [
    "Observed, per purchase",
    "Toteutunut, ostoa kohti",
    "Utfall per köp"
  ],
  "story.transactions": [
    "See the {count} purchases in {period}",
    "Katso {count} ostoa: {period}",
    "Se de {count} köpen i {period}"
  ],
  "story.questionEyebrow": [
    "One quick question",
    "Yksi nopea kysymys",
    "En snabb fråga"
  ],
  "story.oneOffQuestion": [
    "Was the {amount} purchase a one-off?",
    "Oliko {amount} osto kertaluonteinen?",
    "Var köpet på {amount} en engångsutgift?"
  ],
  "story.oneOffHelp": [
    "It stays in actual spending. Leave it out of the repeatable pattern you want to adjust.",
    "Osto säilyy toteutuneissa menoissa. Jätä se pois toistuvasta kulutuksesta, jota haluat muuttaa.",
    "Köpet finns kvar i faktiska utgifter. Lämna det utanför mönstret du vill justera."
  ],
  "story.markOneOff": [
    "Yes, mark it as one-off",
    "Kyllä, merkitse kertaluonteiseksi",
    "Ja, markera som engångsutgift"
  ],
  "story.userExclusion": [
    "You added this · Excluded from this estimate only",
    "Lisäsit tämän · Pois vain tästä arviosta",
    "Du lade till detta · Undantas bara från denna uppskattning"
  ],
  "scenario.title": [
    "A small adjustment",
    "Pieni muutos",
    "En liten justering"
  ],
  "scenario.question": [
    "What if repeatable restaurant spending were 20% lower?",
    "Entä jos toistuvat ravintolamenot olisivat 20 % pienemmät?",
    "Vad händer om återkommande restaurangutgifter är 20 % lägre?"
  ],
  "scenario.base": [
    "20% × {base} repeatable spending.",
    "20 % × {base} toistuvia menoja.",
    "20 % × {base} återkommande utgifter."
  ],
  "scenario.excluded": [
    "The one-off is excluded from this estimate.",
    "Kertaluonteinen osto on poistettu tästä arviosta.",
    "Engångsköpet ingår inte i denna uppskattning."
  ],
  "scenario.included": [
    "All selected restaurant purchases are included.",
    "Kaikki valitun ajan ravintolaostot ovat mukana.",
    "Alla valda restaurangköp ingår."
  ],
  "scenario.link": [
    "Put this toward a goal",
    "Kohdista tämä tavoitteeseen",
    "Lägg detta till ett mål"
  ],
  "scenario.disclaimer": [
    "Estimated contribution. Your actual spending stays unchanged.",
    "Arvioitu säästösumma. Toteutuneet menot eivät muutu.",
    "Uppskattat bidrag. Dina faktiska utgifter ändras inte."
  ],
  "calculation.action": [
    "How is this calculated?",
    "Miten tämä lasketaan?",
    "Hur beräknas detta?"
  ],
  "calculation.title": [
    "The numbers, explained",
    "Lukujen selitys",
    "Siffrorna förklarade"
  ],
  "transactions.title": [
    "The activity behind it",
    "Taustalla olevat tapahtumat",
    "Transaktionerna bakom siffrorna"
  ],
  "transactions.summary": [
    "{label} · {count} rows · Observed",
    "{label} · {count} tapahtumaa · Toteutunut",
    "{label} · {count} transaktioner · Utfall"
  ],
  "transactions.unknownMerchant": [
    "Unknown merchant",
    "Tuntematon kauppias",
    "Okänd handlare"
  ],
  "transactions.unknownCategory": [
    "Unknown category",
    "Tuntematon luokka",
    "Okänd kategori"
  ],
  "transactions.unknown": [
    "Unknown",
    "Tuntematon",
    "Okänd"
  ],
  "transactions.open": [
    "Open transaction detail",
    "Avaa tapahtuman tiedot",
    "Öppna transaktionsdetaljer"
  ],
  "transactions.evidence": [
    "How is this selection calculated?",
    "Miten tämä valinta lasketaan?",
    "Hur beräknas detta urval?"
  ],
  "transactions.hostHelp": [
    "Missing merchant information stays unknown. Connected transaction details belong to S-mobiili.",
    "Puuttuva kauppiastieto säilyy tuntemattomana. Yhdistetyt tapahtumatiedot kuuluvat S-mobiiliin.",
    "Saknad handlarinformation förblir okänd. Anslutna transaktionsdetaljer hör till S-mobiili."
  ],
  "loading.rows": [
    "Loading the source rows…",
    "Ladataan lähdetapahtumia…",
    "Källtransaktionerna laddas…"
  ],
  "loading.action": [
    "One moment…",
    "Hetkinen…",
    "Ett ögonblick…"
  ],
  "feedback.excluded": [
    "You added this: the one-off stays in actual spending and is excluded only from the 20% estimate.",
    "Lisäsit tämän: kertaluonteinen osto säilyy toteutuneissa menoissa ja poistuu vain 20 % arviosta.",
    "Du lade till detta: engångsköpet finns kvar i faktiska utgifter men ingår inte i 20 %-uppskattningen."
  ],
  "feedback.undo": [
    "Last change undone. Your actual history is unchanged.",
    "Viimeisin muutos kumottu. Toteutuneet tapahtumat eivät muuttuneet.",
    "Senaste ändringen ångrades. Din faktiska historik är oförändrad."
  ],
  "feedback.reset": [
    "Demo reset. Seeded account history is ready to explore again.",
    "Demo palautettu. Voit tutkia alkuperäistä tilihistoriaa uudelleen.",
    "Demon är återställd. Du kan utforska den ursprungliga kontohistoriken igen."
  ],
  "feedback.preview": [
    "Estimate recalculated. These assumptions apply only to this preview.",
    "Arvio päivitetty. Oletukset koskevat vain tätä esikatselua.",
    "Uppskattningen är uppdaterad. Antagandena gäller bara denna förhandsvisning."
  ],
  "feedback.goal": [
    "Your goal is saved. This estimate protects your chosen reserve.",
    "Tavoite tallennettu. Valitsemasi puskuri on suojattu arviossa.",
    "Ditt mål har sparats. Uppskattningen skyddar din valda buffert."
  ],
  "feedback.linked": [
    "Your modeled contribution is attached to your goal. No money has been moved.",
    "Arvioitu säästösumma on liitetty tavoitteeseen. Rahaa ei ole siirretty.",
    "Ditt uppskattade bidrag har kopplats till målet. Inga pengar har flyttats."
  ],
  "goal.placeholder": [
    "e.g. A summer in Italy",
    "esim. Kesä Italiassa",
    "t.ex. En sommar i Italien"
  ],
  "goal.intro": [
    "A trip, a buffer, something just for you.",
    "Matka, puskuri tai jotain juuri sinulle.",
    "En resa, en buffert, något för dig."
  ],
  "goal.required": [
    "required / month",
    "tarvitaan kuukaudessa",
    "behövs per månad"
  ],
  "goal.by": [
    "By {date}",
    "Päivään {date} mennessä",
    "Till {date}"
  ],
  "goal.capacity": [
    "Cautious monthly capacity: {amount}. Based on six complete months of free cash flow.",
    "Varovainen kuukausittainen säästövara: {amount}. Perustuu kuuden täyden kuukauden kassavirtaan.",
    "Försiktigt månadsutrymme: {amount}. Bygger på sex hela månaders fria kassaflöde."
  ],
  "goal.reserveDetail": [
    "Protected reserve: {reserve}. Available above it: {upfront}, separate from monthly capacity.",
    "Suojattu puskuri: {reserve}. Sen yli käytettävissä: {upfront}, erillään kuukausittaisesta säästövarasta.",
    "Skyddad buffert: {reserve}. Tillgängligt utöver den: {upfront}, skilt från månadsutrymmet."
  ],
  "goal.linked": [
    "{amount} modeled monthly contribution linked. No transfer created.",
    "Liitetty arvioitu kuukausisumma: {amount}. Tilisiirtoa ei tehty.",
    "{amount} uppskattat månadsbidrag kopplat. Ingen överföring skapad."
  ],
  "goal.gap": [
    "Planning gap: {amount} / month. Try a later date or a smaller target.",
    "Arvion vaje: {amount} kuukaudessa. Kokeile myöhempää päivää tai pienempää tavoitetta.",
    "Gap i planen: {amount} per månad. Prova ett senare datum eller ett mindre mål."
  ],
  "goal.assumptions": [
    "See this plan's assumptions",
    "Katso suunnitelman oletukset",
    "Se planens antaganden"
  ],
  "handoff.confirm": [
    "{amount} / month modeled from your restaurant estimate. Creating this plan will link it. No transfer is created.",
    "Ravintola-arvion kuukausisumma: {amount}. Suunnitelman luominen liittää summan tavoitteeseen. Tilisiirtoa ei tehdä.",
    "{amount} per månad från din restauranguppskattning. När planen skapas kopplas beloppet till målet. Ingen överföring skapas."
  ],
  "handoff.submit": [
    "Create plan & link {amount} / month",
    "Luo suunnitelma ja liitä {amount} kuukaudessa",
    "Skapa plan och koppla {amount} per månad"
  ],
  "handoff.finishLink": [
    "Finish linking {amount} / month",
    "Viimeistele {amount} kuukausisumman liittäminen",
    "Slutför koppling av {amount} per månad"
  ],
  "handoff.saved": [
    "Your goal is saved. Finish linking the {amount} / month estimate to it.",
    "Tavoite on tallennettu. Viimeistele {amount} kuukausiarvion liittäminen.",
    "Ditt mål är sparat. Slutför kopplingen av uppskattningen {amount} per månad."
  ],
  "handoff.host": [
    "Your goal and contribution are saved. Finish the S-mobiili handoff; no transfer is created.",
    "Tavoite ja säästösumma on tallennettu. Viimeistele siirtyminen S-mobiiliin. Tilisiirtoa ei tehdä.",
    "Ditt mål och bidrag är sparade. Slutför överlämningen till S-mobiili. Ingen överföring skapas."
  ],
  "handoff.finishHost": [
    "Finish goal handoff",
    "Viimeistele tavoitteen luovutus",
    "Slutför överlämningen av målet"
  ],
  "evidence.scope": [
    "Scope and period",
    "Rajaus ja ajanjakso",
    "Urval och period"
  ],
  "evidence.customer": [
    "Customer",
    "Asiakas",
    "Kund"
  ],
  "evidence.filter": [
    "Selection",
    "Valinta",
    "Urval"
  ],
  "evidence.facts": [
    "Fact references",
    "Lähdelukujen tunnisteet",
    "Faktareferenser"
  ],
  "evidence.refs": [
    "{count} included source references",
    "{count} mukana olevaa lähdeviitettä",
    "{count} inkluderade källreferenser"
  ],
  "evidence.allFlows": [
    "All monthly money flows",
    "Kaikki kuukauden rahavirrat",
    "Alla månadens pengaflöden"
  ],
  "evidence.mapIntro": [
    "Only the selected account, month and spending group are included.",
    "Mukana ovat vain valittu tili, kuukausi ja menoryhmä.",
    "Bara valt konto, månad och utgiftsgrupp ingår."
  ],
  "evidence.netFlow": [
    "Net flow: {amount}. A minus means money left the account.",
    "Nettorahavirta: {amount}. Miinus tarkoittaa tililtä lähtenyttä rahaa.",
    "Nettoflöde: {amount}. Minus betyder att pengar lämnade kontot."
  ],
  "evidence.mapFormula": [
    "Add the signed source amounts in this selection. Income and transfers stay separate from consumption.",
    "Laske valinnan lähdesummat yhteen etumerkkeineen. Tulot ja siirrot pysyvät erillään kulutuksesta.",
    "Summera källbeloppen med tecken i urvalet. Inkomster och överföringar hålls skilda från konsumtion."
  ],
  "evidence.actual": [
    "Actual restaurant spending: {amount}. An estimate never changes this history.",
    "Toteutuneet ravintolamenot: {amount}. Arvio ei muuta tilihistoriaa.",
    "Faktiska restaurangutgifter: {amount}. En uppskattning ändrar aldrig historiken."
  ],
  "evidence.comparison": [
    "Comparison",
    "Vertailu",
    "Jämförelse"
  ],
  "evidence.formula": [
    "Formula and source rows",
    "Kaava ja lähdetapahtumat",
    "Formel och källtransaktioner"
  ],
  "evidence.averageFormula": [
    "Total is the sum of restaurant purchases in each period. Average = total / purchase count, rounded half up to cents.",
    "Summa lasketaan kunkin ajanjakson ravintolaostoista. Keskiarvo = summa / ostojen määrä, pyöristettynä senttiin puolikkaat ylöspäin.",
    "Totalen summerar restaurangköp i varje period. Genomsnitt = total / antal köp, avrundat till cent med halvor uppåt."
  ],
  "evidence.scenarioFormula": [
    "{base} × 20% = {amount} per month, rounded half up to cents. This is an estimate, never promised savings.",
    "{base} × 20 % = {amount} kuukaudessa, pyöristettynä senttiin puolikkaat ylöspäin. Tämä on arvio, ei säästölupaus.",
    "{base} × 20 % = {amount} per månad, avrundat till cent med halvor uppåt. Det är en uppskattning, inget löfte om sparande."
  ],
  "evidence.excluded": [
    "Excluded row",
    "Poistettu tapahtuma",
    "Undantagen transaktion"
  ],
  "evidence.none": [
    "None",
    "Ei yhtään",
    "Ingen"
  ],
  "evidence.source": [
    "Source",
    "Lähde",
    "Källa"
  ],
  "evidence.user": [
    "You added this · User-confirmed",
    "Lisäsit tämän · Käyttäjän vahvistama",
    "Du lade till detta · Bekräftat av användaren"
  ],
  "evidence.deterministic": [
    "Verified calculation",
    "Tarkistettu laskelma",
    "Kontrollerad beräkning"
  ],
  "evidence.memory": [
    "Remembered choices and undo",
    "Tallennetut valinnat ja kumoaminen",
    "Sparade val och ångra"
  ],
  "evidence.memoryHelp": [
    "Confirmed changes are saved with an audit event. Undo records a reversing event; reset restores demo choices.",
    "Vahvistetut muutokset tallennetaan tapahtumalokiin. Kumoaminen lisää vastatapahtuman ja palautus palauttaa demon valinnat.",
    "Bekräftade ändringar sparas i en logg. Ångra skapar en återföring; återställning återför demoval."
  ],
  "evidence.host": [
    "Transaction details and real transfers belong to S-mobiili. This prototype has no private bank connection.",
    "Tapahtumatiedot ja oikeat siirrot kuuluvat S-mobiiliin. Prototyyppi ei ole yhteydessä pankin yksityisiin rajapintoihin.",
    "Transaktionsdetaljer och riktiga överföringar hör till S-mobiili. Prototypen saknar privat bankanslutning."
  ],
  "evidence.goalFormula": [
    "Remaining = target minus saved, at least zero. Monthly requirement = remaining / months, rounded up to cents. Cautious capacity uses the lower quartile of six complete months' free cash flow. Transfers are kept separate.",
    "Jäljellä = tavoite miinus säästetty, vähintään nolla. Kuukausitarve = jäljellä oleva summa / kuukaudet, pyöristettynä senttiin ylöspäin. Varovainen säästövara perustuu kuuden täyden kuukauden vapaan kassavirran alakvartiiliin. Siirrot käsitellään erikseen.",
    "Kvar = mål minus sparat, minst noll. Månadsbehov = kvar / månader, avrundat uppåt till cent. Försiktigt utrymme använder den undre kvartilen av sex hela månaders fria kassaflöde. Överföringar hålls skilda."
  ],
  "evidence.noApproval": [
    "This plan creates no transfer and does not predict credit approval.",
    "Suunnitelma ei tee siirtoa eikä ennusta lainapäätöstä.",
    "Planen skapar ingen överföring och förutsäger inget kreditbeslut."
  ],
  "forecast.observedLine": [
    "━ Observed balance",
    "━ Toteutunut saldo",
    "━ Faktiskt saldo"
  ],
  "forecast.estimatedLine": [
    "┄ Estimated balance",
    "┄ Arvioitu saldo",
    "┄ Uppskattat saldo"
  ],
  "forecast.band": [
    "The shaded area shows past spending variation, not the chance of a future outcome.",
    "Varjostus kuvaa menojen aiempaa vaihtelua, ei tulevan tapahtuman todennäköisyyttä.",
    "Det skuggade området visar tidigare utgiftsvariation, inte sannolikheten för ett framtida utfall."
  ],
  "forecast.include": [
    "Include in this estimate",
    "Ota mukaan arvioon",
    "Ta med i uppskattningen"
  ],
  "forecast.amount": [
    "Amount (€)",
    "Summa (€)",
    "Belopp (€)"
  ],
  "forecast.day": [
    "Day of month",
    "Kuukauden päivä",
    "Dag i månaden"
  ],
  "forecast.apply": [
    "Recalculate preview",
    "Laske arvio uudelleen",
    "Beräkna på nytt"
  ],
  "forecast.temporary": [
    "These edits apply only to this estimate. Your ledger and saved rules stay unchanged.",
    "Muutokset koskevat vain tätä arviota. Tilitapahtumat ja tallennetut säännöt eivät muutu.",
    "Ändringarna gäller bara denna uppskattning. Kontohistoriken och sparade regler ändras inte."
  ],
  "forecast.method": [
    "Recurring bills and income use typical dates and amounts from history. Everyday spending uses historical variation. Future income and taxes are never invented.",
    "Toistuvissa laskuissa ja tuloissa käytetään historian tyypillisiä päiviä ja summia. Arjen menoissa käytetään aiempaa vaihtelua. Tulevia tuloja tai veroja ei keksitä.",
    "Återkommande räkningar och inkomster använder typiska historiska datum och belopp. Vardagsutgifter använder tidigare variation. Framtida inkomster eller skatter hittas aldrig på."
  ],
  "trends.description": [
    "{count} complete months · Observed restaurant spending.",
    "{count} täyttä kuukautta · Toteutuneet ravintolamenot.",
    "{count} hela månader · Faktiska restaurangutgifter."
  ],
  "trends.yoy": [
    "Same-month change: {amount}. Both periods are complete.",
    "Saman kuukauden muutos: {amount}. Molemmat ajanjaksot ovat täysiä.",
    "Förändring samma månad: {amount}. Båda perioderna är hela."
  ],
  "trends.salaryMedians": [
    "Recent three-month median: {recent}. Prior six-month median: {prior}. Other income stays separate.",
    "Viimeisten kolmen kuukauden mediaani: {recent}. Edellisten kuuden kuukauden mediaani: {prior}. Muut tulot pidetään erillään.",
    "Median de senaste tre månaderna: {recent}. Median de föregående sex månaderna: {prior}. Andra inkomster hålls skilda."
  ],
  "trends.annual": [
    "Compare two complete 12-month windows",
    "Vertaa kahta täyttä 12 kuukauden jaksoa",
    "Jämför två hela 12-månadersperioder"
  ],
  "trends.priorYear": [
    "Preceding 12 months",
    "Edelliset 12 kuukautta",
    "Föregående 12 månader"
  ],
  "trends.latestYear": [
    "Latest 12 months",
    "Viimeiset 12 kuukautta",
    "Senaste 12 månaderna"
  ],
  "trends.noAnnual": [
    "Two complete 12-month windows are not available yet.",
    "Kahta täyttä 12 kuukauden jaksoa ei ole vielä saatavilla.",
    "Två hela 12-månadersperioder finns ännu inte."
  ],
  "coach.here": [
    "Here to help",
    "Apunasi",
    "Här för att hjälpa"
  ],
  "coach.promptRestaurants": [
    "What changed in restaurants?",
    "Mikä ravintolamenoissa muuttui?",
    "Vad förändrades i restaurangutgifterna?"
  ],
  "coach.promptMonth": [
    "What changed this month?",
    "Mikä muuttui tässä kuussa?",
    "Vad förändrades den här månaden?"
  ],
  "coach.promptFuture": [
    "What is coming up?",
    "Mitä on tulossa?",
    "Vad är på väg?"
  ],
  "coach.offlineMode": [
    "Deterministic offline coach · Numbers from verified facts · Changes require your confirmation",
    "Ilman tekoälyä toimiva valmentaja · Tarkistetut luvut · Muutokset vaativat vahvistuksesi",
    "Coach utan AI · Kontrollerade siffror · Ändringar kräver din bekräftelse"
  ],
  "coach.aiMode": [
    "AI-assisted response · Numbers from verified facts · Changes require your confirmation",
    "Tekoälyn tukema vastaus · Tarkistetut luvut · Muutokset vaativat vahvistuksesi",
    "AI-stött svar · Kontrollerade siffror · Ändringar kräver din bekräftelse"
  ],
  "coach.fallback": [
    "You can also use the comparison, estimate controls and goals directly.",
    "Voit käyttää myös vertailua, arvion säätimiä ja tavoitteita suoraan.",
    "Du kan också använda jämförelsen, uppskattningens reglage och målen direkt."
  ],
  "support.unavailable": [
    "This view is unavailable right now. Your other account views still work.",
    "Tämä näkymä ei ole nyt saatavilla. Muut tilinäkymät toimivat edelleen.",
    "Den här vyn är inte tillgänglig just nu. Dina övriga kontovyer fungerar fortfarande."
  ],
  "support.needsHistory": [
    "More account history is needed for this estimate.",
    "Arvion tekemiseen tarvitaan lisää tilihistoriaa.",
    "Mer kontohistorik behövs för uppskattningen."
  ],
  "safe.demoReserve": [
    "€500 demo reserve, chosen for this preview.",
    "Tähän arvioon valittu 500 € demopuskuri.",
    "500 € demobuffert, vald för denna förhandsvisning."
  ],
  "investment.monthsCount": [
    "{count} of {total} months",
    "{count} / {total} kuukautta",
    "{count} av {total} månader"
  ],
  "chart.comparison": [
    "Restaurant spending comparison",
    "Ravintolamenojen vertailu",
    "Jämförelse av restaurangutgifter"
  ],
  "chart.purchases": [
    "{count} purchases",
    "{count} ostoa",
    "{count} köp"
  ],
  "chart.average": [
    "{amount} average",
    "keskiarvo {amount}",
    "genomsnitt {amount}"
  ],
  "chart.noAverage": [
    "Average unavailable",
    "Keskiarvo ei saatavilla",
    "Genomsnitt saknas"
  ],
  "chart.noComparison": [
    "No complete comparison periods available.",
    "Täysiä vertailujaksoja ei ole saatavilla.",
    "Inga hela jämförelseperioder finns."
  ],
  "chart.trend": [
    "Complete-month spending trend",
    "Täysien kuukausien menokehitys",
    "Utveckling av utgifter för hela månader"
  ],
  "chart.noTrend": [
    "No complete periods available for this trend.",
    "Tähän kehitykseen ei ole täysiä ajanjaksoja.",
    "Det finns inga hela perioder för denna utveckling."
  ],
  "chart.runway": [
    "Pattern-based cash-flow preview",
    "Historiaan perustuva kassavirta-arvio",
    "Mönsterbaserad kassaflödesöversikt"
  ],
  "chart.noRunway": [
    "A cash-flow estimate is not available for this account yet.",
    "Tilin kassavirta-arviota ei ole vielä saatavilla.",
    "En kassaflödesuppskattning saknas ännu för kontot."
  ],
  "chart.runwayDescription": [
    "Observed starting balance {start}. Estimated ending balance {end}. Historical variation, not a probability interval.",
    "Toteutunut alkusaldo {start}. Arvioitu loppusaldo {end}. Historiallista vaihtelua, ei todennäköisyysväli.",
    "Faktiskt startsaldo {start}. Uppskattat slutsaldo {end}. Historisk variation, inte ett sannolikhetsintervall."
  ],
  "chart.recent": [
    "Recent observed activity",
    "Viimeisimmät toteutuneet tapahtumat",
    "Senaste faktiska aktivitet"
  ],
  "chart.next30": [
    "30-day estimate",
    "30 päivän arvio",
    "30-dagarsuppskattning"
  ],
  "chart.goal": [
    "Goal progress",
    "Tavoitteen edistyminen",
    "Målets utveckling"
  ],
  "chart.goalDescription": [
    "{current} saved toward {target}. {percent}% complete.",
    "Säästetty {current}, tavoite {target}. Valmis {percent} %.",
    "{current} sparat mot {target}. {percent} % klart."
  ],
  "chart.saved": [
    "{percent}% saved",
    "{percent} % säästetty",
    "{percent} % sparat"
  ],
  "chart.target": [
    "{amount} target",
    "tavoite {amount}",
    "mål {amount}"
  ],
  "chart.noGoal": [
    "Choose a target to see your progress.",
    "Valitse tavoitesumma nähdäksesi edistymisen.",
    "Välj ett målbelopp för att se utvecklingen."
  ],
  "error.oneOffMissing": [
    "That one-off purchase is not present in this account and period. No change was made.",
    "Kertaluonteista ostoa ei löydy valitulta tililtä ja ajalta. Muutoksia ei tehty.",
    "Engångsköpet finns inte på valt konto och period. Ingen ändring gjordes."
  ],
  "error.assumption": [
    "Use a valid euro amount and a day from 1 to 31.",
    "Anna kelvollinen euromäärä ja päivä väliltä 1–31.",
    "Ange ett giltigt eurobelopp och en dag från 1 till 31."
  ],
  "error.account": [
    "Account unavailable",
    "Tili ei saatavilla",
    "Kontot är inte tillgängligt"
  ],
  "home.priority.payday.title": [
    "A tighter stretch before payday",
    "Tiukempi jakso ennen palkkapäivää",
    "En stramare period före lönedagen"
  ],
  "home.priority.payday.description": [
    "Your observed balance has repeatedly run low before salary arrives. Review the timing, not just the monthly total.",
    "Havaittu saldosi on toistuvasti pienentynyt ennen palkan saapumista. Tarkastele ajoitusta, ei vain kuukausisummaa.",
    "Ditt observerade saldo har upprepade gånger blivit lågt innan lönen kommer. Granska tidpunkten, inte bara månadssumman."
  ],
  "home.priority.payday.question": [
    "Explain my balance pattern before payday",
    "Selitä saldoni kehitys ennen palkkapäivää",
    "Förklara mitt saldomönster före lönedagen"
  ],
  "home.priority.salary.title": [
    "Your salary pattern changed",
    "Palkkatasosi muuttui",
    "Ditt lönemönster förändrades"
  ],
  "home.priority.salary.description": [
    "Compare recent salary-only income with your earlier baseline. Other income stays separate.",
    "Vertaa viimeaikaisia palkkatuloja aiempaan perustasoon. Muut tulot pidetään erillään.",
    "Jämför den senaste lönen med din tidigare basnivå. Andra inkomster hålls åtskilda."
  ],
  "home.priority.salary.question": [
    "Explain the change in my salary pattern",
    "Selitä palkkatasoni muutos",
    "Förklara förändringen i mitt lönemönster"
  ],
  "home.priority.unusual.title": [
    "One purchase is unusual for you",
    "Yksi ostos poikkeaa tavallisesta",
    "Ett köp är ovanligt för dig"
  ],
  "home.priority.unusual.description": [
    "It differs from your earlier activity in the same category. Review the transaction before drawing a conclusion.",
    "Se poikkeaa saman luokan aiemmista tapahtumistasi. Tarkista tapahtuma ennen johtopäätöksiä.",
    "Det skiljer sig från din tidigare aktivitet i samma kategori. Granska transaktionen innan du drar en slutsats."
  ],
  "home.priority.unusual.question": [
    "Explain the purchase that is unusual for me",
    "Selitä minulle poikkeava ostos",
    "Förklara köpet som är ovanligt för mig"
  ],
  "home.priority.home.title": [
    "Past home-financing context is available",
    "Aiempi asuntorahoituksen tausta on saatavilla",
    "Tidigare bostadsfinansiering finns som bakgrund"
  ],
  "home.priority.home.description": [
    "Linked history can help you prepare questions. It is not a current approval or affordability assessment.",
    "Linkitetty historia auttaa valmistelemaan kysymyksiä. Se ei ole nykyinen hyväksyntä- tai maksukykyarvio.",
    "Länkad historik kan hjälpa dig att förbereda frågor. Den är inte ett aktuellt godkännande eller en betalningsförmågebedömning."
  ],
  "home.priority.home.question": [
    "Explain my linked home-financing history",
    "Selitä linkitetty asuntorahoitushistoriani",
    "Förklara min länkade bostadsfinansieringshistorik"
  ],
  "forecast.subtitle": [
    "A 30-day cash-flow estimate using qualified recurring patterns from your history.",
    "30 päivän kassavirta-arvio historian perusteella tunnistetuista toistuvista tapahtumista.",
    "En 30-dagars kassaflödesuppskattning med kvalificerade återkommande mönster från din historik."
  ],
  "safe.obligations": [
    "Qualified recurring outflows kept aside",
    "Sivuun jätetyt tunnistetut toistuvat menot",
    "Kvalificerade återkommande utflöden som lagts åt sidan"
  ],
  "safe.everydayAllowance": [
    "Historical unscheduled-spending buffer",
    "Historiallinen puskuri aikatauluttamattomille menoille",
    "Historisk buffert för ej schemalagda utgifter"
  ],
  "evidence.assumptions": [
    "Assumptions used",
    "Käytetyt oletukset",
    "Antaganden som används"
  ],
  "evidence.calculationSources": [
    "Starting balance and recurring-pattern sources",
    "Alkusaldon ja toistuvien mallien lähteet",
    "Källor för startsaldo och återkommande mönster"
  ],
  "evidence.historySources": [
    "Historical spending comparison sources",
    "Historiallisten menojen vertailulähteet",
    "Källor för historisk utgiftsjämförelse"
  ],
  "safe.assumption.0": [
    "Expected income is excluded until it actually arrives.",
    "Odotettu tulo jätetään pois, kunnes se todella saapuu.",
    "Förväntad inkomst räknas inte med förrän den faktiskt kommer."
  ],
  "safe.assumption.1": [
    "Upcoming outflows use qualified recurring patterns, including committed transfers.",
    "Tulevat menot perustuvat tunnistettuihin toistuviin malleihin, myös sitoviin siirtoihin.",
    "Kommande utflöden bygger på kvalificerade återkommande mönster, inklusive bundna överföringar."
  ],
  "safe.assumption.2": [
    "The spending buffer scales the upper quartile of historical thirty-day unscheduled spending.",
    "Menopuskuri skaalataan aiempien 30 päivän aikatauluttamattomien menojen yläkvartiilista.",
    "Utgiftsbufferten skalar den övre kvartilen av historiska trettiodagarsutgifter utan schema."
  ],
  "safe.assumption.3": [
    "Taxes and obligations missing from the transaction history are not inferred.",
    "Tapahtumahistoriasta puuttuvia veroja tai velvoitteita ei päätellä.",
    "Skatter och skyldigheter som saknas i transaktionshistoriken antas inte."
  ],
  "evidence.oneOffSaved": [
    "Saved one-off transaction",
    "Tallennettu kertaluonteinen tapahtuma",
    "Sparad engångstransaktion"
  ],
  "vat.title": [
    "VAT inside your spending",
    "Ostoksiin sisältyvä ALV",
    "Moms i dina utgifter"
  ],
  "vat.disclaimer": [
    "Estimated from each purchase date and merchant category. This is not a personal tax calculation.",
    "Arvio perustuu kunkin ostoksen päivään ja kauppiasluokkaan. Tämä ei ole henkilökohtainen verolaskelma.",
    "Uppskattat från varje köpdatum och handlarkategori. Detta är ingen personlig skatteberäkning."
  ],
  "vat.amount": [
    "≈ {amount} of this month's spending was VAT",
    "Tämän kuun menoihin sisältyi arviolta {amount} ALV:tä",
    "≈ {amount} av månadens utgifter var moms"
  ],
  "vat.gross": [
    "Gross spending in scope",
    "Tarkasteltavat bruttomenot",
    "Bruttoutgifter i urvalet"
  ],
  "vat.coverage": [
    "Rate mapping coverage",
    "Verokantakartoituksen kattavuus",
    "Täckning för momssatsmappning"
  ],
  "vat.breakdown": [
    "How the estimate is split",
    "Arvion jakautuminen",
    "Så delas uppskattningen"
  ],
  "vat.rateRow": [
    "{rate} · {count} purchases · ≈ {amount}",
    "{rate} · {count} ostosta · noin {amount}",
    "{rate} · {count} köp · ≈ {amount}"
  ],
  "vat.method": [
    "VAT inside = gross price × rate / (1 + rate), rounded to cents per transaction. MCC is used first; category is a fallback.",
    "Sisältyvä ALV = bruttohinta × verokanta / (1 + verokanta), pyöristettynä senttiin tapahtumittain. Ensin käytetään MCC:tä, muuten luokkaa.",
    "Moms inuti = bruttopris × sats / (1 + sats), avrundat till cent per transaktion. MCC används först och kategori som reserv."
  ],
  "vat.taxInside": [
    "Estimated VAT inside: ≈ {amount} · {rate}",
    "Sisältyvä ALV-arvio: noin {amount} · {rate}",
    "Uppskattad moms: ≈ {amount} · {rate}"
  ],
  "vat.unmapped": [
    "VAT rate not mapped",
    "ALV-kantaa ei voitu määrittää",
    "Momssatsen kunde inte mappas"
  ],
  "vat.coverageNote": [
    "Rate mapping coverage shows how much spending received a rate; it is not an accuracy or confidence score.",
    "Verokantakartoituksen kattavuus kertoo, kuinka suurelle osalle menoista löytyi verokanta; se ei ole tarkkuus- tai luottamusluku.",
    "Täckningen visar hur stor del av utgifterna som fick en momssats; den är inte ett mått på exakthet eller säkerhet."
  ],
  "vat.limitationsTitle": ["Important limits", "Tärkeät rajaukset", "Viktiga begränsningar"],
  "vat.limitation.mixed": [
    "Mixed grocery baskets and restaurant alcohol can contain products with another VAT rate.",
    "Ruokaostokset ja ravintola-annokset voivat sisältää tuotteita, joilla on toinen ALV-kanta.",
    "Blandade matkassar och restaurangalkohol kan innehålla produkter med en annan momssats."
  ],
  "vat.limitation.ambiguous": [
    "Broad mappings are labelled per purchase; ambiguous rows can remain unmapped.",
    "Laajat arviot merkitään ostoksittain; epäselvä tapahtuma voidaan jättää kartoittamatta.",
    "Breda uppskattningar märks per köp; tvetydiga rader kan lämnas utan mappning."
  ],
  "vat.limitation.excise": [
    "Excise duties on fuel, alcohol and tobacco are not included.",
    "Polttoaineen, alkoholin ja tupakan valmisteverot eivät sisälly arvioon.",
    "Punktskatter på bränsle, alkohol och tobak ingår inte."
  ],
  "vat.limitation.tax": [
    "This is not a personal tax liability, deduction or filing calculation.",
    "Tämä ei ole henkilökohtaisen verovelan, vähennyksen tai veroilmoituksen laskelma.",
    "Detta är ingen beräkning av personlig skatteskuld, avdrag eller deklaration."
  ],
  "vat.mapping.direct_mcc": ["Direct MCC mapping", "Suora MCC-kartoitus", "Direkt MCC-mappning"],
  "vat.mapping.broad_mcc_estimate": ["Broad MCC estimate", "Laaja MCC-arvio", "Bred MCC-uppskattning"],
  "vat.mapping.category_fallback": ["Category fallback", "Luokkaan perustuva varakartoitus", "Kategori som reserv"],
  "vat.mapping.broad_category_estimate": ["Broad category estimate", "Laaja luokka-arvio", "Bred kategoriuppskattning"],
  "vat.mapping.unmapped": ["No reliable rate mapping", "Luotettavaa verokantakartoitusta ei löytynyt", "Ingen tillförlitlig momssatsmappning"],
  "vat.source.category": ["Category", "Luokka", "Kategori"],
  "vat.source.unmapped": ["No mapping source", "Ei kartoituslähdettä", "Ingen mappningskälla"],
  "investment.coverageLimited": [
    "Only {count} observed months are available in the requested range.",
    "Pyydetyltä ajalta on saatavilla vain {count} havaittua kuukautta.",
    "Endast {count} observerade månader finns i det begärda intervallet."
  ],
  "coach.greeting": [
    "What would you like to understand? Choose a topic or ask in your own words.",
    "Mitä haluaisit ymmärtää? Valitse aihe tai kysy omin sanoin.",
    "Vad vill du förstå? Välj ett ämne eller fråga med egna ord."
  ],
  "coach.directory.title": [
    "Explore your money",
    "Tutki raha-asioitasi",
    "Utforska din ekonomi"
  ],
  "coach.directory.help": [
    "Start with a topic. Every amount is checked against this account.",
    "Aloita aiheesta. Jokainen summa tarkistetaan tältä tililtä.",
    "Börja med ett ämne. Varje belopp kontrolleras mot det här kontot."
  ],
  "coach.topic.spending": ["Spending & statistics", "Menot ja tilastot", "Utgifter och statistik"],
  "coach.topic.cashflow": ["Safe to spend & cash flow", "Turvallinen käyttövara ja kassavirta", "Tryggt att spendera och kassaflöde"],
  "coach.topic.investing": ["Saving & investments", "Säästäminen ja sijoitukset", "Sparande och investeringar"],
  "coach.topic.goals": ["Goals & large purchases", "Tavoitteet ja suuret hankinnat", "Mål och stora inköp"],
  "coach.topic.homeVehicle": ["Home or vehicle preparation", "Kotiin tai ajoneuvoon valmistautuminen", "Förberedelse för bostad eller fordon"],
  "coach.topic.tax": ["Tax & VAT", "Verot ja ALV", "Skatt och moms"],
  "coach.question.taxi": ["How much did I spend on taxis last month?", "Paljonko käytin takseihin viime kuussa?", "Hur mycket spenderade jag på taxi förra månaden?"],
  "coach.question.dining": ["How much could I save by reducing dining out by 20%?", "Paljonko voisin säästää vähentämällä ravintolamenoja 20 %?", "Hur mycket kan jag spara genom att minska restaurangutgifterna med 20 %?"],
  "coach.question.profile": ["What kind of spender am I?", "Millainen rahankäyttäjä olen?", "Vilken typ av spenderare är jag?"],
  "coach.question.safe": ["What is safe for me to spend this week?", "Paljonko voin käyttää turvallisesti tällä viikolla?", "Hur mycket är tryggt för mig att spendera den här veckan?"],
  "coach.question.investing": ["Show my investment transfers", "Näytä sijoitussiirtoni", "Visa mina investeringsöverföringar"],
  "coach.question.buffer": ["Plan an emergency buffer", "Suunnittele hätävara", "Planera en nödbuffert"],
  "coach.question.goal": ["Plan my own savings goal", "Suunnittele oma säästötavoitteeni", "Planera mitt eget sparmål"],
  "coach.question.purchase": ["Prepare for a large purchase", "Valmistaudu suureen hankintaan", "Förbered ett stort inköp"],
  "coach.question.homeGoal": ["Prepare a home goal", "Valmistaudu asuntotavoitteeseen", "Förbered ett bostadsmål"],
  "coach.question.vehicleGoal": ["Prepare a vehicle goal", "Valmistaudu ajoneuvotavoitteeseen", "Förbered ett fordonsmål"],
  "coach.question.homeHistory": ["Explain linked home-financing history", "Selitä linkitetty asuntorahoitushistoria", "Förklara länkad bostadsfinansieringshistorik"],
  "coach.question.taxRecords": ["Check explicit tax records this month", "Tarkista tämän kuun nimenomaiset verotiedot", "Kontrollera uttryckliga skatteuppgifter den här månaden"],
  "coach.question.vat": ["See estimated VAT inside purchases", "Katso ostoksiin sisältyvä ALV-arvio", "Se uppskattad moms i inköpen"],
  "coach.homeDisclaimer": ["Planning only. No approval or affordability decision is inferred.", "Vain suunnitteluun. Hyväksyntää tai maksukykyä ei päätellä.", "Endast för planering. Inget godkännande eller beslut om betalningsförmåga antas."],
  "coach.input.label": ["Ask in your own words", "Kysy omin sanoin", "Fråga med egna ord"],
  "taxPlan.title": ["Plan a user-declared tax amount", "Suunnittele itse ilmoittamasi verosumma", "Planera ett skattebelopp som du själv anger"],
  "taxPlan.help": ["This unsaved scenario combines what you enter with the current observed balance and reserve.", "Tallentamaton arvio yhdistää antamasi tiedot nykyiseen havaittuun saldoon ja puskuriin.", "Det osparade scenariot kombinerar dina uppgifter med det aktuella observerade saldot och bufferten."],
  "taxPlan.amount": ["Amount due", "Maksettava summa", "Belopp som ska betalas"],
  "taxPlan.saved": ["Already set aside", "Jo sivuun laitettu", "Redan avsatt"],
  "taxPlan.location": ["Where is that set-aside amount?", "Missä sivuun laitettu summa on?", "Var finns det avsatta beloppet?"],
  "taxPlan.inside": ["Inside this account balance", "Tämän tilin saldossa", "I saldot på det här kontot"],
  "taxPlan.outside": ["Outside this account balance", "Tämän tilin saldon ulkopuolella", "Utanför saldot på det här kontot"],
  "taxPlan.date": ["Due date", "Eräpäivä", "Förfallodag"],
  "taxPlan.submit": ["Calculate monthly set-aside", "Laske kuukausittainen varaus", "Beräkna månatlig avsättning"],
  "taxPlan.disclaimer": ["Unsaved scenario · Not tax advice", "Tallentamaton arvio · Ei veroneuvontaa", "Osparat scenario · Inte skatterådgivning"],
  "taxPlan.resultTitle": ["Your declared planning scenario", "Itse ilmoittamasi suunnitteluarvio", "Ditt angivna planeringsscenario"],
  "taxPlan.remaining": ["Still to set aside", "Vielä sivuun laitettava", "Återstår att avsätta"],
  "taxPlan.due": ["Due", "Eräpäivä", "Förfaller"],
  "taxPlan.reference": ["Reference date", "Vertailupäivä", "Referensdatum"],
  "taxPlan.balance": ["Observed balance", "Havaittu saldo", "Observerat saldo"],
  "taxPlan.reserve": ["Reserve", "Puskuri", "Buffert"],
  "taxPlan.afterSetAside": ["Available above reserve after full set-aside", "Käytettävissä puskurin ja koko varauksen jälkeen", "Tillgängligt över bufferten efter full avsättning"],
  "taxPlan.notAdvice": ["Not tax advice. No liability, rate, deduction or filing rule was calculated, and this scenario was not saved.", "Ei veroneuvontaa. Verovelkaa, verokantaa, vähennystä tai ilmoitussääntöä ei laskettu, eikä arviota tallennettu.", "Inte skatterådgivning. Ingen skatteskuld, skattesats, avdrags- eller deklarationsregel beräknades, och scenariot sparades inte."],
  "coach.result.evidence": ["Source rows ({count})", "Lähderivit ({count})", "Källrader ({count})"],
  "coach.result.allActivity": ["All matching activity", "Kaikki vastaavat tapahtumat", "All matchande aktivitet"],
  "coach.result.statistics": ["Exact account result", "Tarkka tilitulos", "Exakt kontoresultat"],
  "coach.result.count": ["Transactions", "Tapahtumia", "Transaktioner"],
  "coach.result.average": ["Average outflow", "Keskimääräinen meno", "Genomsnittligt utflöde"],
  "coach.result.largest": ["Largest outflow", "Suurin meno", "Största utflödet"],
  "coach.result.comparison": ["Exact period comparison", "Tarkka ajanjaksovertailu", "Exakt periodjämförelse"],
  "coach.result.delta": ["Difference: {amount}", "Ero: {amount}", "Skillnad: {amount}"],
  "coach.result.unsaved": ["Unsaved scenario", "Tallentamaton arvio", "Osparat scenario"],
  "coach.result.adjustment": ["Reduce {category} by {percent}%", "Vähennä luokkaa {category} {percent} %", "Minska {category} med {percent} %"],
  "coach.result.actual": ["Observed spending", "Havaitut menot", "Observerade utgifter"],
  "coach.result.base": ["Adjustable base", "Muokattava perusta", "Justerbar bas"],
  "coach.result.noMutation": ["Your actual transactions stay unchanged. This preview has not been saved.", "Toteutuneet tapahtumat eivät muutu. Arviota ei ole tallennettu.", "Dina faktiska transaktioner ändras inte. Översikten har inte sparats."],
  "coach.result.profile": ["Your three-basket breakdown", "Kolmen korin erittelysi", "Din uppdelning i tre korgar"],
  "coach.result.noScore": ["Description only — not a score or judgment", "Vain kuvaus — ei pisteytys tai arvio", "Endast beskrivning — inget betyg eller omdöme"],
  "coach.result.total": ["Total consumption", "Kulutus yhteensä", "Total konsumtion"],
  "coach.result.tax": ["Explicit tax evidence", "Nimenomaiset verotiedot", "Uttryckliga skatteuppgifter"],
  "coach.result.noExplicitTax": ["No explicit tax records were found for this period.", "Tältä ajalta ei löytynyt nimenomaisia verotietoja.", "Inga uttryckliga skatteposter hittades för perioden."],
  "coach.result.missingTaxWarning": ["Missing records do not mean no tax was paid.", "Puuttuvat tiedot eivät tarkoita, ettei veroa olisi maksettu.", "Saknade uppgifter betyder inte att ingen skatt betalades."],
  "coach.result.paid": ["Paid", "Maksettu", "Betalat"],
  "coach.result.refunds": ["Refunds", "Palautukset", "Återbetalningar"],
  "coach.result.rows": ["View matching transactions", "Näytä vastaavat tapahtumat", "Visa matchande transaktioner"],
  "coach.result.exploreScenario": ["Explore the scenario", "Tutki arviota", "Utforska scenariot"],
  "coach.filter.category": ["Category", "Luokka", "Kategori"],
  "coach.filter.role": ["Basket", "Kori", "Korg"],
  "coach.filter.transaction_type": ["Transaction type", "Tapahtumatyyppi", "Transaktionstyp"],
  "coach.filter.merchant_id": ["Merchant", "Kauppias", "Handlare"],
  "coach.debug.title": ["Demo diagnostics", "Demon diagnostiikka", "Demodiagnostik"],
  "coach.debug.source": ["Response source", "Vastauksen lähde", "Svarskälla"],
  "coach.debug.fallback": ["Fallback reason", "Varasyy", "Reservorsak"],
  "coach.debug.none": ["none", "ei mitään", "ingen"],
  "coach.debug.tool": ["Calculation source", "Laskennan lähde", "Beräkningskälla"],
  "app.noScript": [
    "Enable JavaScript to explore your account and estimates.",
    "Ota JavaScript käyttöön tutkiaksesi tiliä ja arvioita.",
    "Aktivera JavaScript för att utforska kontot och uppskattningarna."
  ]
};
for (const [key, values] of Object.entries(JOURNEY_MESSAGES)) { EN[key]=values[0]; FI[key]=values[1]; SV[key]=values[2]; }

export const MESSAGES = Object.freeze({
  en: Object.freeze(EN),
  fi: Object.freeze(FI),
  sv: Object.freeze(SV),
});

const INTL_LOCALES = Object.freeze({en: 'en-FI', fi: 'fi-FI', sv: 'sv-FI'});

function supportedLocale(value) {
  if (typeof value !== 'string') return null;
  const base = value.trim().toLowerCase().split(/[-_]/, 1)[0];
  return SUPPORTED_LOCALES.includes(base) ? base : null;
}

export function normalizeLocale(value) {
  return supportedLocale(value) || 'en';
}

export function intlLocale(value) {
  return INTL_LOCALES[normalizeLocale(value)];
}

function browserLanguages() {
  try {
    if (Array.isArray(globalThis.navigator?.languages) && globalThis.navigator.languages.length) {
      return globalThis.navigator.languages;
    }
    return globalThis.navigator?.language ? [globalThis.navigator.language] : [];
  } catch (_error) {
    return [];
  }
}

function browserStorage() {
  try {
    return globalThis.localStorage || null;
  } catch (_error) {
    return null;
  }
}

function readStoredLocale(storage) {
  if (!storage) return null;
  try {
    return supportedLocale(storage.getItem(STORAGE_KEY));
  } catch (_error) {
    return null;
  }
}

function chooseBrowserLocale(languages) {
  for (const language of languages || []) {
    const locale = supportedLocale(language);
    if (locale) return locale;
  }
  return 'en';
}

function interpolate(template, values) {
  return String(template).replace(/\{([A-Za-z0-9_]+)\}/g, (match, key) =>
    Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : match
  );
}

export function createI18n(options = {}) {
  const catalog = options.catalog || MESSAGES;
  const storage = Object.prototype.hasOwnProperty.call(options, 'storage')
    ? options.storage
    : browserStorage();
  const languages = options.navigatorLanguages || browserLanguages();
  let current = readStoredLocale(storage) || chooseBrowserLocale(languages);

  return {
    get locale() {
      return current;
    },
    get localeTag() {
      return intlLocale(current);
    },
    setLocale(value) {
      current = normalizeLocale(value);
      if (storage) {
        try {
          storage.setItem(STORAGE_KEY, current);
        } catch (_error) {
          // Language changes must remain usable when storage is unavailable.
        }
      }
      return current;
    },
    t(key, values = {}) {
      const template = catalog[current]?.[key] ?? catalog.en?.[key] ?? key;
      return interpolate(template, values);
    },
  };
}
