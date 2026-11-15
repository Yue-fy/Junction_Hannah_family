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
  'basket.regular': 'Must-pays',
  'basket.regular.help': 'Bills that come every month: rent, electricity, phone, groceries and commuting.',
  'basket.irregular': 'Surprise must-pays',
  'basket.irregular.help': 'Necessary but hard to predict: a broken washing machine, the dentist.',
  'basket.everyday': 'Little leaks',
  'basket.everyday.help': 'Small everyday choices that add up: coffee, takeaway, taxis, going out.',
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
  'common.scenario': 'Arvio',
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
  'basket.regular': 'Pakolliset kuukausimenot',
  'basket.regular.help': 'Laskut, jotka tulevat joka kuukausi: vuokra, sähkö, puhelin, ruokaostokset ja työmatkat.',
  'basket.irregular': 'Yllättävät pakolliset menot',
  'basket.irregular.help': 'Välttämättömiä mutta vaikeasti ennakoitavia: rikkoutunut pesukone, hammaslääkäri.',
  'basket.everyday': 'Arjen pikkumenot',
  'basket.everyday.help': 'Pienet arjen valinnat, jotka kertyvät: kahvit, noutoruoka, taksit, illanvietot.',
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
  'goal.template.buffer': 'Turvatyyny',
  'goal.template.trip': 'Matka',
  'goal.template.vehicle': 'Auto',
  'goal.template.home': 'Koti',
  'goal.template.purchase': 'Suuri hankinta',
  'goal.name': 'Mihin säästät?',
  'goal.target': 'Tavoitesumma',
  'goal.saved': 'Säästetty jo',
  'goal.date': 'Tavoitepäivä',
  'goal.reserve': 'Turvatyynyksi jätettävä summa',
  'goal.create': 'Luo suunnitelma',
  'goal.disclosure': 'Tämä on suunnitelma. Se ei siirrä rahaa.',
  'coach.eyebrow': 'Rahasi selkokielellä',
  'coach.title': 'Kysy valmentajalta',
  'coach.greeting': 'Mitä haluaisit ymmärtää? Edetään yksi askel kerrallaan.',
  'coach.input.label': 'Kysymyksesi',
  'coach.input.placeholder': 'Kysy raha-asioistasi…',
  'coach.verified': 'Luvut tulevat tililtäsi. Mitään ei muuteta ilman lupaasi.',
  'coach.otherLanguage': 'Kysy suomeksi, ruotsiksi tai englanniksi.',
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
  'safe.reserve': 'Turvatyyny, pidetään sivussa',
  'safe.obligations': 'Sivuun jätetyt tiedossa olevat laskut',
  'safe.everydayAllowance': 'Sivuun jätetty arjen käyttövara',
  'safe.evidence': 'Katso, mitä arvio sisältää',
  'safe.disclaimer': 'Tämä on arvio, ei takuu. Uudet tai poikkeavat kulut voivat muuttaa sitä.',
  'investment.title': 'Säästöön siirretyt rahat',
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
  'app.disclosure': 'Koncept för S-mobiili · Syntetiska demodata · Stöd för planering, du bestämmer.',
  'language.label': 'Språk',
  'language.en': 'Engelska',
  'language.fi': 'Finska',
  'language.sv': 'Svenska',
  'persona.open': 'Välj demokund',
  'persona.label': 'Demokund',
  'persona.description': 'Kontona är syntetiska. Coachens uppgifter sparas endast på den här demoservern.',
  'persona.reset': 'Återställ den här kundens demo',
  'navigation.label': 'Huvudnavigering',
  'nav.home': 'Hem',
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
  'common.scenario': 'Uppskattning',
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
  'money.income': 'Pengar in',
  'basket.regular': 'Fasta måsten',
  'basket.regular.help': 'Räkningar som kommer varje månad: hyra, el, telefon, matvaror och pendling.',
  'basket.irregular': 'Oväntade måsten',
  'basket.irregular.help': 'Nödvändigt men svårt att förutse: en trasig tvättmaskin, tandläkaren.',
  'basket.everyday': 'Vardagens småutgifter',
  'basket.everyday.help': 'Små vardagsval som blir mycket tillsammans: kaffe, hämtmat, taxi, nöjen.',
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
  'goal.template.buffer': 'Säkerhetsmarginal',
  'goal.template.trip': 'En resa',
  'goal.template.vehicle': 'En bil',
  'goal.template.home': 'Ett hem',
  'goal.template.purchase': 'Ett stort inköp',
  'goal.name': 'Vad sparar du till?',
  'goal.target': 'Målbelopp',
  'goal.saved': 'Redan sparat',
  'goal.date': 'Måldatum',
  'goal.reserve': 'Säkerhetsmarginal att behålla',
  'goal.create': 'Skapa min plan',
  'goal.disclosure': 'Det här är en plan. Inga pengar flyttas.',
  'coach.eyebrow': 'Din ekonomi på klarspråk',
  'coach.title': 'Fråga din coach',
  'coach.greeting': 'Vad vill du förstå? Vi kan ta ett steg i taget.',
  'coach.input.label': 'Din fråga',
  'coach.input.placeholder': 'Fråga om din ekonomi…',
  'coach.verified': 'Siffrorna kommer från ditt konto. Inget ändras utan ditt ok.',
  'coach.otherLanguage': 'Fråga på svenska, finska eller engelska.',
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
  'safe.reserve': 'Säkerhetsmarginal, hålls undan',
  'safe.obligations': 'Kända räkningar som lagts åt sidan',
  'safe.everydayAllowance': 'Vardagsutrymme som lagts åt sidan',
  'safe.evidence': 'Se vad som ingår',
  'safe.disclaimer': 'Detta är en uppskattning, inte en garanti. Nya eller ovanliga utgifter kan ändra den.',
  'investment.title': 'Pengar som flyttats till sparande',
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
    "Ravintolamenot muuttuivat {amount} {period:in}.",
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
    "Katso {count} {count|osto|ostoa}: {period}",
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
    "{label} · {count} {count|tapahtuma|tapahtumaa} · Toteutunut",
    "{label} · {count} {count|transaktion|transaktioner} · Utfall"
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
    "Tavoite tallennettu. Suunnitelma ei koske turvatyynyysi.",
    "Ditt mål har sparats. Planen rör inte din säkerhetsmarginal."
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
    "Matka, turvatyyny tai jotain juuri sinulle.",
    "En resa, en säkerhetsmarginal eller något bara för dig."
  ],
  "goal.required": [
    "required / month",
    "kuukaudessa",
    "i månaden"
  ],
  "goal.by": [
    "By {date}",
    "{date} mennessä",
    "Senast {date}"
  ],
  "goal.capacity": [
    "In a usual month about {amount} is left over (your last six months).",
    "Laskujen ja tavallisten menojesi jälkeen sinulle jää noin {amount} kuukaudessa.",
    "Efter räkningar och dina vanliga utgifter har du ungefär {amount} kvar i månaden."
  ],
  "goal.reserveDetail": [
    "Could go to this goal now, from your plan until payday: {upfront}.",
    "Palkkapäivän suunnitelmasi mukaan tähän tavoitteeseen voisi siirtää nyt {upfront}.",
    "Enligt din lönedagsplan kan {upfront} gå till målet nu."
  ],
  "goal.linked": [
    "{amount} modeled monthly contribution linked. No transfer created.",
    "Menomuutoksestasi ohjataan tähän tavoitteeseen {amount} kuukaudessa. Rahaa ei siirretä.",
    "{amount} i månaden från din utgiftsändring går till det här målet. Inga pengar flyttas."
  ],
  "goal.gap": [
    "Still missing after that: {amount} / month. Try a later date or a smaller target.",
    "Sinun pitäisi laittaa sivuun {amount} kuukaudessa. Myöhäisempi päivä pienentää summaa.",
    "Du skulle behöva lägga undan {amount} i månaden. Ett senare datum gör beloppet mindre."
  ],
  "goal.assumptions": [
    "See this plan's assumptions",
    "Miten tämä lasketaan?",
    "Hur räknas det här ut?"
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
    "{count} {count|lähdeviite|lähdeviitettä} mukana",
    "{count} {count|källreferens|källreferenser} ingår"
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
    "Miten tämä lasketaan?",
    "Hur räknas det här ut?"
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
    "Tarkistettu tilitapahtumistasi",
    "Kontrollerat mot dina transaktioner"
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
    "Jäljellä = tavoite miinus jo säästetty. Kuukausisumma = jäljellä oleva summa ÷ kuukaudet tavoitepäivään. Kuukausittainen liikkumavarasi perustuu kuuteen viime täyteen kuukauteen laskujen jälkeen. Säästösiirrot lasketaan erikseen.",
    "Kvar = målet minus det du redan sparat. Månadsbelopp = det som är kvar ÷ månaderna fram till datumet. Ditt månatliga utrymme bygger på de senaste sex hela månaderna, efter räkningar. Sparöverföringar räknas separat."
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
    "Menot {count} täyden kuukauden ajalta.",
    "Utgifter under {count} {count|hel månad|hela månader}."
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
    "Pikavastaukset · Luvut tulevat tililtäsi · Mitään ei muuteta ilman lupaasi",
    "Snabbsvar · Siffrorna kommer från ditt konto · Inget ändras utan ditt ok"
  ],
  "coach.aiMode": [
    "AI-assisted response · Numbers from verified facts · Changes require your confirmation",
    "Tekoälyvalmentaja · Luvut tulevat tililtäsi · Mitään ei muuteta ilman lupaasi",
    "AI-coach · Siffrorna kommer från ditt konto · Inget ändras utan ditt ok"
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
    "{amount} pidetään sivussa turvatyynynäsi.",
    "{amount} hålls undan som din säkerhetsmarginal."
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
    "{count} {count|osto|ostoa}",
    "{count} köp"
  ],
  "chart.average": [
    "{amount} average",
    "keskiarvo {amount}",
    "genomsnitt {amount}"
  ],
  "chart.noAverage": [
    "Average unavailable",
    "Ei vielä keskiarvoa",
    "Inget genomsnitt än"
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
    "Saldon arvio aiempien tapahtumien perusteella",
    "Saldots utveckling enligt tidigare mönster"
  ],
  "chart.noRunway": [
    "A cash-flow estimate is not available for this account yet.",
    "Tilin kassavirta-arviota ei ole vielä saatavilla.",
    "En kassaflödesuppskattning saknas ännu för kontot."
  ],
  "chart.runwayDescription": [
    "Observed starting balance {start}. Estimated ending balance {end}. Historical variation, not a probability interval.",
    "Saldo nyt {start}. Arvioitu saldo jakson lopussa {end}. Vaihteluväli perustuu aiempiin menoihisi, ei todennäköisyyksiin.",
    "Saldo nu {start}. Uppskattat saldo i slutet av perioden {end}. Spannet bygger på dina tidigare utgifter, inte på sannolikheter."
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
    "Expected bills from past patterns",
    "Aiempien tapahtumien perusteella odotetut laskut",
    "Väntade räkningar utifrån tidigare mönster"
  ],
  "safe.everydayAllowance": [
    "Historical unscheduled-spending buffer",
    "Tavalliset arjen menot siihen asti",
    "Vanliga vardagsutgifter fram till dess"
  ],
  "evidence.assumptions": [
    "Assumptions used",
    "Mitä oletimme",
    "Vad vi antog"
  ],
  "evidence.calculationSources": [
    "Starting balance and recurring-pattern sources",
    "Maksut tämän taustalla",
    "Betalningarna bakom detta"
  ],
  "evidence.historySources": [
    "Historical spending comparison sources",
    "Kuukaudet, joihin vertasimme",
    "Tidigare månader vi jämförde med"
  ],
  "safe.assumption.0": [
    "Expected income is excluded until it actually arrives.",
    "Odotetut tulot lasketaan mukaan vasta, kun ne ovat tilillä.",
    "Pengar du väntar på räknas först när de har kommit in."
  ],
  "safe.assumption.1": [
    "Upcoming outflows use qualified recurring patterns, including committed transfers.",
    "Säännöllisesti toistuvat laskut ja siirrot varataan etukäteen.",
    "Räkningar och överföringar som återkommer regelbundet hålls undan."
  ],
  "safe.assumption.2": [
    "The spending buffer scales the upper quartile of historical thirty-day unscheduled spending.",
    "Arjen menoihin varataan lisäksi pelivaraa kalliimpien kuukausiesi perusteella.",
    "Vi lägger också undan lite extra för vardagsutgifter, utifrån dina dyrare månader."
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
    "Laskettu jokaiselle ostokselle kaupan tyypin mukaan. Tämä ei ole henkilökohtainen verolaskelma.",
    "Uträknat för varje köp utifrån typen av butik. Det här är ingen personlig skatteberäkning."
  ],
  "vat.amount": [
    "≈ {amount} of this month's spending was VAT",
    "Tämän kuun menoihin sisältyi arviolta {amount} ALV:tä",
    "≈ {amount} av månadens utgifter var moms"
  ],
  "vat.gross": [
    "Gross spending in scope",
    "Tämän kuun menot",
    "Utgifter den här månaden"
  ],
  "vat.coverage": [
    "Rate mapping coverage",
    "Menot, joille löytyi ALV-kanta",
    "Utgifter med känd momssats"
  ],
  "vat.breakdown": [
    "How the estimate is split",
    "Arvion jakautuminen",
    "Så delas uppskattningen"
  ],
  "vat.rateRow": [
    "{rate} · {count} purchases · ≈ {amount}",
    "{rate} · {count} {count|osto|ostoa} · ≈ {amount}",
    "{rate} · {count} köp · ≈ {amount}"
  ],
  "vat.method": [
    "VAT inside = gross price × rate / (1 + rate), rounded to cents per transaction. MCC is used first; category is a fallback.",
    "Hintaan sisältyvä ALV = hinta × verokanta ÷ (1 + verokanta), laskettuna jokaiselle ostokselle kaupan tyypin mukaan.",
    "Momsen i priset = pris × momssats ÷ (1 + momssats), uträknad för varje köp utifrån typen av butik."
  ],
  "vat.taxInside": [
    "Estimated VAT inside: ≈ {amount} · {rate}",
    "Sisältyvä ALV-arvio: noin {amount} · {rate}",
    "Uppskattad moms: ≈ {amount} · {rate}"
  ],
  "vat.unmapped": [
    "VAT rate not mapped",
    "ALV-kantaa ei löytynyt",
    "Ingen momssats hittades"
  ],
  "vat.coverageNote": [
    "Rate mapping coverage shows how much spending received a rate; it is not an accuracy or confidence score.",
    "Luku kertoo, kuinka suurelle osalle menoista löytyi verokanta. Se ei kerro arvion tarkkuudesta.",
    "Siffran visar hur stor del av utgifterna som fick en momssats. Den säger inget om hur exakt uppskattningen är."
  ],
  "vat.limitationsTitle": ["Important limits", "Tärkeät rajaukset", "Viktiga begränsningar"],
  "vat.limitation.mixed": [
    "Mixed grocery baskets and restaurant alcohol can contain products with another VAT rate.",
    "Ruokaostokset ja ravintola-annokset voivat sisältää tuotteita, joilla on toinen ALV-kanta.",
    "Blandade matkassar och restaurangalkohol kan innehålla produkter med en annan momssats."
  ],
  "vat.limitation.ambiguous": [
    "Broad mappings are labelled per purchase; ambiguous rows can remain unmapped.",
    "Jotkin kaupat myyvät tuotteita eri verokannoilla, joten osalle ostoksista ei löydy verokantaa.",
    "Vissa butiker säljer varor med olika momssatser, så några köp saknar momssats."
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
  "vat.mapping.direct_mcc": ["Direct MCC mapping", "Kaupan tyypin mukaan", "Enligt typen av butik"],
  "vat.mapping.broad_mcc_estimate": ["Broad MCC estimate", "Arvioitu kaupan tyypin mukaan", "Uppskattad utifrån typen av butik"],
  "vat.mapping.category_fallback": ["Category fallback", "Ostoluokan mukaan", "Enligt kategori"],
  "vat.mapping.broad_category_estimate": ["Broad category estimate", "Arvio ostoluokan mukaan", "Uppskattning enligt kategori"],
  "vat.mapping.unmapped": ["No reliable rate mapping", "ALV-kantaa ei löytynyt", "Ingen momssats hittades"],
  "vat.source.category": ["Category", "Luokka", "Kategori"],
  "vat.source.unmapped": ["No mapping source", "ALV-kantaa ei löytynyt", "Ingen momssats hittades"],
  "investment.coverageLimited": [
    "Only {count} observed months are available in the requested range.",
    "Tältä jaksolta on historiaa vain {count} kuukauden ajalta.",
    "Det finns bara {count} {count|månads|månaders} historik för den här perioden."
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
  "coach.question.profile": ["What kind of spender am I?", "Millainen rahankäyttäjä olen?", "Hurdan är jag med pengar?"],
  "coach.question.safe": ["What is safe for me to spend this week?", "Paljonko voin käyttää turvallisesti tällä viikolla?", "Hur mycket är tryggt för mig att spendera den här veckan?"],
  "coach.question.investing": ["Show my investment transfers", "Näytä sijoitussiirtoni", "Visa mina investeringsöverföringar"],
  "coach.question.buffer": ["Plan an emergency buffer", "Suunnittele turvatyyny", "Planera en säkerhetsmarginal"],
  "coach.question.goal": ["Plan my own savings goal", "Suunnittele oma säästötavoitteeni", "Planera mitt eget sparmål"],
  "coach.question.purchase": ["Prepare for a large purchase", "Valmistaudu suureen hankintaan", "Förbered ett stort inköp"],
  "coach.question.homeGoal": ["Prepare a home goal", "Valmistaudu asuntotavoitteeseen", "Förbered ett bostadsmål"],
  "coach.question.vehicleGoal": ["Prepare a vehicle goal", "Valmistaudu ajoneuvotavoitteeseen", "Förbered ett fordonsmål"],
  "coach.question.homeHistory": ["Explain linked home-financing history", "Selitä linkitetty asuntorahoitushistoria", "Förklara länkad bostadsfinansieringshistorik"],
  "coach.question.taxRecords": ["Check explicit tax records this month", "Tarkista tämän kuun nimenomaiset verotiedot", "Kontrollera uttryckliga skatteuppgifter den här månaden"],
  "coach.question.vat": ["See estimated VAT inside purchases", "Katso ostoksiin sisältyvä ALV-arvio", "Se uppskattad moms i inköpen"],
  "coach.homeDisclaimer": ["Planning only. No approval or affordability decision is inferred.", "Vain suunnitteluun. Hyväksyntää tai maksukykyä ei päätellä.", "Endast för planering. Inget godkännande eller beslut om betalningsförmåga antas."],
  "coach.input.label": ["Ask in your own words", "Kysy omin sanoin", "Fråga med egna ord"],
  "taxPlan.title": ["Plan a user-declared tax amount", "Suunnittele verojen maksu", "Planera skatten du ska betala"],
  "taxPlan.help": ["This unsaved scenario combines what you enter with the current observed balance and reserve.", "Laskelmaa ei tallenneta. Se yhdistää antamasi tiedot saldoosi ja turvatyynyysi.", "Uppskattningen sparas inte. Den kombinerar dina uppgifter med ditt saldo och din säkerhetsmarginal."],
  "taxPlan.amount": ["Amount due", "Maksettava summa", "Belopp som ska betalas"],
  "taxPlan.saved": ["Already set aside", "Jo sivuun laitettu", "Redan avsatt"],
  "taxPlan.location": ["Where is that set-aside amount?", "Missä sivuun laitettu summa on?", "Var finns det avsatta beloppet?"],
  "taxPlan.inside": ["Inside this account balance", "Tämän tilin saldossa", "I saldot på det här kontot"],
  "taxPlan.outside": ["Outside this account balance", "Tämän tilin saldon ulkopuolella", "Utanför saldot på det här kontot"],
  "taxPlan.date": ["Due date", "Eräpäivä", "Förfallodag"],
  "taxPlan.submit": ["Calculate monthly set-aside", "Laske kuukausittainen varaus", "Beräkna månatlig avsättning"],
  "taxPlan.disclaimer": ["Unsaved scenario · Not tax advice", "Ei tallenneta · Ei veroneuvontaa", "Sparas inte · Ingen skatterådgivning"],
  "taxPlan.resultTitle": ["Your declared planning scenario", "Verovaraussuunnitelmasi", "Din plan för skatteavsättning"],
  "taxPlan.remaining": ["Still to set aside", "Vielä sivuun laitettava", "Återstår att avsätta"],
  "taxPlan.due": ["Due", "Eräpäivä", "Förfaller"],
  "taxPlan.reference": ["Reference date", "Laskettu päivänä", "Uträknat den"],
  "taxPlan.balance": ["Observed balance", "Tilin saldo", "Kontots saldo"],
  "taxPlan.reserve": ["Reserve", "Turvatyyny", "Säkerhetsmarginal"],
  "taxPlan.afterSetAside": ["Available above reserve after full set-aside", "Turvatyynyn yli jää, kun kaikki on varattu", "Kvar över säkerhetsmarginalen när allt är avsatt"],
  "taxPlan.notAdvice": ["Not tax advice. No liability, rate, deduction or filing rule was calculated, and this scenario was not saved.", "Ei veroneuvontaa. Emme laskeneet veroja, veroprosenttia tai vähennyksiä, eikä laskelmaa tallennettu.", "Ingen skatterådgivning. Vi har inte räknat ut någon skatt, skattesats eller avdrag, och uppskattningen sparades inte."],
  "coach.result.evidence": ["Source rows ({count})", "Lähderivit ({count})", "Källrader ({count})"],
  "coach.result.allActivity": ["All matching activity", "Kaikki vastaavat tapahtumat", "All matchande aktivitet"],
  "coach.result.statistics": ["Exact account result", "Tarkka tilitulos", "Exakt kontoresultat"],
  "coach.result.count": ["Transactions", "Tapahtumia", "Transaktioner"],
  "coach.result.average": ["Average outflow", "Keskimääräinen meno", "Genomsnittligt utflöde"],
  "coach.result.largest": ["Largest outflow", "Suurin meno", "Största utflödet"],
  "coach.result.comparison": ["Exact period comparison", "Tarkka ajanjaksovertailu", "Exakt periodjämförelse"],
  "coach.result.delta": ["Difference: {amount}", "Ero: {amount}", "Skillnad: {amount}"],
  "coach.result.unsaved": ["Unsaved scenario", "Ei tallennettu", "Inte sparad"],
  "coach.result.adjustment": ["Reduce {category} by {percent}%", "Vähennä luokkaa {category} {percent} %", "Minska {category} med {percent} %"],
  "coach.result.actual": ["Observed spending", "Havaitut menot", "Observerade utgifter"],
  "coach.result.base": ["Adjustable base", "Muokattava perusta", "Justerbar bas"],
  "coach.result.noMutation": ["Your actual transactions stay unchanged. This preview has not been saved.", "Toteutuneet tapahtumasi eivät muutu, eikä laskelmaa ole tallennettu.", "Dina faktiska transaktioner ändras inte och kalkylen har inte sparats."],
  "coach.result.profile": ["Your three-basket breakdown", "Kolmen korin erittelysi", "Din uppdelning i tre korgar"],
  "coach.result.noScore": ["Description only — not a score or judgment", "Vain kuvaus — ei pisteytys tai arvio", "Endast beskrivning — inget betyg eller omdöme"],
  "coach.result.total": ["Total consumption", "Menot yhteensä", "Utgifter totalt"],
  "coach.result.tax": ["Explicit tax evidence", "Nimenomaiset verotiedot", "Uttryckliga skatteuppgifter"],
  "coach.result.noExplicitTax": ["No explicit tax records were found for this period.", "Tältä ajalta ei löytynyt nimenomaisia verotietoja.", "Inga uttryckliga skatteposter hittades för perioden."],
  "coach.result.missingTaxWarning": ["Missing records do not mean no tax was paid.", "Puuttuvat tiedot eivät tarkoita, ettei veroa olisi maksettu.", "Saknade uppgifter betyder inte att ingen skatt betalades."],
  "coach.result.paid": ["Paid", "Maksettu", "Betalat"],
  "coach.result.refunds": ["Refunds", "Palautukset", "Återbetalningar"],
  "coach.result.rows": ["View matching transactions", "Näytä vastaavat tapahtumat", "Visa matchande transaktioner"],
  "coach.result.exploreScenario": ["Explore the scenario", "Tutki tätä muutosta", "Utforska ändringen"],
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

const EXPERIENCE_CLARITY = {
  'forecast.title':['30-day balance forecast','Saldon 30 päivän ennuste','Saldoprognos för 30 dagar'],
  'forecast.subtitle':['See how your balance could change if recent patterns continue.','30 päivän arvio, joka perustuu historiassasi toistuviin laskuihin ja tuloihin.','En uppskattning för 30 dagar, baserad på räkningar och inkomster som återkommer i din historik.'],
  'trends.monthByMonth':['Your spending over time','Menosi ajan mittaan','Dina utgifter över tid'],
  'trends.whatChanged':['Eating out, a closer look','Ravintolamenot tarkemmin','Restaurangutgifter, en närmare titt'],
  'coach.result.statistics':['Your selected spending','Valitsemasi menot','Dina valda utgifter'],
  'chart.spendingCategories':['Spending by category','Menot luokittain','Utgifter per kategori'],
  'chart.selectCategory':['Select a segment or category to explore its transactions.','Valitse lohko tai luokka nähdäksesi tapahtumat.','Välj en del eller kategori för att se transaktionerna.'],
};
for (const [key,values] of Object.entries(EXPERIENCE_CLARITY)) {EN[key]=values[0];FI[key]=values[1];SV[key]=values[2];}

const EXPERIENCE_V2_MESSAGES = {
  "nav.home": [
    "Home",
    "Etusivu",
    "Hem"
  ],
  "nav.coach": [
    "Coach",
    "Valmentaja",
    "Coach"
  ],
  "demo.open": [
    "Try a story",
    "Kokeile tarinaa",
    "Prova en berättelse"
  ],
  "period.recorded": [
    "Recorded activity",
    "Kirjatut tapahtumat",
    "Registrerade händelser"
  ],
  "home.eyebrow": [
    "Your money, with a little perspective",
    "Uusi näkökulma rahaasi",
    "Perspektiv på dina pengar"
  ],
  "home.title": [
    "Make room for what matters.",
    "Rahaa sille, mikä on tärkeää.",
    "Gör plats för det viktiga."
  ],
  "home.help": [
    "Understand your month. Find your next small step.",
    "Ymmärrä kuukautesi. Löydä seuraava pieni askel.",
    "Förstå din månad. Hitta ditt nästa lilla steg."
  ],
  "home.ask": [
    "Ask your own question ↗",
    "Kysy omin sanoin ↗",
    "Ställ en egen fråga ↗"
  ],
  "home.baskets": [
    "Your month in three baskets",
    "Kuukautesi kolmessa korissa",
    "Din månad i tre korgar"
  ],
  "home.explore": [
    "Explore spending ↗",
    "Tutki menoja ↗",
    "Utforska utgifter ↗"
  ],
  "home.basketsHelp": [
    "A starting point for understanding your spending. You decide what can change.",
    "Lähtökohta menojesi ymmärtämiseen. Sinä päätät, mikä voi muuttua.",
    "En utgångspunkt för att förstå dina utgifter. Du väljer vad som kan ändras."
  ],
  "goal.next": [
    "Something to look forward to",
    "Jotain odotettavaa",
    "Något att se fram emot"
  ],
  "goal.start": [
    "A wish is enough to start.",
    "Toive riittää alkuun.",
    "En önskan räcker för att börja."
  ],
  "goal.explore": [
    "Explore my goals ↗",
    "Tutki tavoitteitani ↗",
    "Utforska mina mål ↗"
  ],
  "spending.filter": [
    "Filter spending",
    "Rajaa menoja",
    "Filtrera utgifter"
  ],
  "spending.eyebrow": [
    "Follow the money",
    "Seuraa rahaa",
    "Följ pengarna"
  ],
  "spending.title": [
    "Where did it go?",
    "Mihin rahat menivät?",
    "Vart tog pengarna vägen?"
  ],
  "spending.help": [
    "Explore a category, see the transactions, ask what changed.",
    "Tutki luokkaa, katso tapahtumat ja kysy muutoksista.",
    "Utforska en kategori, se transaktionerna och fråga vad som ändrats."
  ],
  "spending.history": [
    "How spending changes over time",
    "Miten menot muuttuvat ajan myötä",
    "Hur utgifterna ändras över tid"
  ],
  "spending.forecast": [
    "Explore the coming days",
    "Tutki tulevia päiviä",
    "Utforska de kommande dagarna"
  ],
  "spending.investments": [
    "Savings and investment transfers",
    "Säästöön siirretyt rahat",
    "Pengar som flyttats till sparande"
  ],
  "spending.vat": [
    "Understand VAT inside purchases",
    "Ostostesi arvonlisävero",
    "Momsen i dina köp"
  ],
  "goal.calculate": [
    "Make a detailed plan",
    "Tee tarkempi suunnitelma",
    "Gör en detaljerad plan"
  ],
  "goals.title": [
    "Start with a wish.",
    "Aloita toiveesta.",
    "Börja med en önskan."
  ],
  "goals.help": [
    "You do not need an amount, a deadline, or all the answers yet.",
    "Et tarvitse vielä summaa, määräaikaa tai kaikkia vastauksia.",
    "Du behöver inte ha ett belopp, ett datum eller alla svar än."
  ],
  "wish.question": [
    "What would you like to make possible?",
    "Mihin haluaisit säästää?",
    "Vad vill du spara till?"
  ],
  "wish.placeholder": [
    "A little more breathing room",
    "Hieman enemmän liikkumavaraa",
    "Lite mer utrymme i vardagen"
  ],
  "wish.help": [
    "A few words are enough. We can work out the numbers together.",
    "Muutama sana riittää. Voimme pohtia summia yhdessä.",
    "Några ord räcker. Vi kan räkna på det tillsammans."
  ],
  "wish.buffer": [
    "An emergency buffer",
    "Turvatyyny",
    "En säkerhetsmarginal"
  ],
  "wish.home": [
    "A future home",
    "Tuleva koti",
    "Ett framtida hem"
  ],
  "wish.trip": [
    "A trip to look forward to",
    "Unelmien matka",
    "En drömresa"
  ],
  "wish.remember": [
    "Remember my wishes and preferences on this browser",
    "Muista toiveeni ja mieltymykseni tässä selaimessa",
    "Kom ihåg mina önskemål i den här webbläsaren"
  ],
  "wish.save": [
    "Keep this wish",
    "Säilytä toive",
    "Spara önskan"
  ],
  "goal.ready": [
    "I have an amount and a date in mind",
    "Minulla on summa ja päivämäärä mielessä",
    "Jag har ett belopp och ett datum i åtanke"
  ],
  "coach.title": [
    "Let's figure it out.",
    "Selvitetään yhdessä.",
    "Vi tar reda på det tillsammans."
  ],
  "coach.help": [
    "A question, a what-if, or a goal you haven't quite figured out.",
    "Kysymys, mitä jos -tilanne tai tavoite, joka on vielä avoin.",
    "En fråga, ett tänk om eller ett mål som ännu är oklart."
  ],
  "coach.empty": [
    "What is on your mind?",
    "Mitä mielessäsi on?",
    "Vad funderar du på?"
  ],
  "coach.emptyHelp": [
    "Start with your own question, or try one of these.",
    "Aloita omalla kysymykselläsi tai kokeile näitä.",
    "Börja med din egen fråga eller prova en av dessa."
  ],
  "coach.vague": [
    "I want to save, but I don't know how much.",
    "Haluan säästää, mutta en tiedä kuinka paljon.",
    "Jag vill spara, men vet inte hur mycket."
  ],
  "coach.context": [
    "The picture we're using",
    "Käyttämämme tiedot",
    "Underlaget vi använder"
  ],
  "coach.evidence": [
    "Every answer uses the account and dates shown. Open its evidence to see the transactions.",
    "Vastaukset koskevat näytettyä tiliä ja päivämääriä. Avaa perusteet nähdäksesi tapahtumat.",
    "Svaren gäller kontot och datumen som visas. Öppna underlaget för att se transaktionerna."
  ],
  "coach.preferences": [
    "Tell me what matters to you ↗",
    "Kerro, mikä on sinulle tärkeää ↗",
    "Berätta vad som är viktigt för dig ↗"
  ],
  "coach.more": [
    "More ways to explore",
    "Lisää tutkittavaa",
    "Fler sätt att utforska"
  ],
  "demo.title": [
    "Three lives. Different questions.",
    "Kolme elämää. Erilaisia kysymyksiä.",
    "Tre liv. Olika frågor."
  ],
  "demo.help": [
    "Explore recorded synthetic accounts. Wishes are examples, never inferred personal facts.",
    "Tutki synteettisiä tilitietoja. Toiveet ovat esimerkkejä, eivät pääteltyjä henkilötietoja.",
    "Utforska syntetiska konton. Önskemålen är exempel, aldrig härledda personliga fakta."
  ],
  "demo.kai": [
    "Make it through the week",
    "Selviä viikosta",
    "Få veckan att gå ihop"
  ],
  "demo.kaiHelp": [
    "See how expected bills and a buffer change the picture.",
    "Katso, miten odotetut laskut ja turvatyyny vaikuttavat.",
    "Se hur väntade räkningar och en säkerhetsmarginal påverkar bilden."
  ],
  "demo.alex": [
    "Turn a small change into a possibility",
    "Pieni muutos, uusi mahdollisuus",
    "En liten förändring, en ny möjlighet"
  ],
  "demo.alexHelp": [
    "Explore spending, change a percentage, and keep a wish.",
    "Tutki menoja, muuta prosenttia ja säilytä toive.",
    "Utforska utgifter, ändra procenten och spara en önskan."
  ],
  "demo.taylor": [
    "Understand a home-financing history",
    "Ymmärrä asuntorahoituksen historiaa",
    "Förstå en bostadsfinansieringshistorik"
  ],
  "demo.taylorHelp": [
    "Review historical records, then explore a future home wish.",
    "Tutki historiatietoja ja pohdi sitten tulevaa kotitoivetta.",
    "Granska historiska uppgifter och utforska sedan en önskan om ett hem."
  ]
};
for (const [key, values] of Object.entries(EXPERIENCE_V2_MESSAGES)) { EN["v2."+key]=values[0]; FI["v2."+key]=values[1]; SV["v2."+key]=values[2]; }

const AGENT_MESSAGES = {
  title: ['Coach','Valmentaja','Coach'],
  newChat: ['New chat','Uusi keskustelu','Ny chatt'],
  context: ['Account & dates','Tili ja päivämäärät','Konto och datum'],
  conversation: ['Conversation','Keskustelu','Samtal'],
  work: ['How I worked this out','Näin selvitin asian','Så räknade jag ut det'],
  suggestions: ['Continue the conversation','Jatka keskustelua','Fortsätt samtalet'],
  looking: ['Looking at your transactions…','Tarkastelen tapahtumiasi…','Tittar på dina transaktioner…'],
  calculating: ['Working through your question…','Selvitän kysymystäsi…','Arbetar med din fråga…'],
  mode: ['AI coach · numbers verified against your transactions','Tekoälyvalmentaja · luvut tarkistettu tapahtumistasi','AI-coach · siffrorna kontrollerade mot dina transaktioner'],
  chart: ['Recorded amounts','Kirjatut summat','Registrerade belopp'],
  'starter.where': ['Where did my money go this month?','Mihin rahani menivät tässä kuussa?','Vart gick mina pengar den här månaden?'],
  'starter.save': ['How could I save more?','Miten voisin säästää enemmän?','Hur skulle jag kunna spara mer?'],
  'starter.compare': ['How do I compare with others my age?','Miten pärjään ikäisiini verrattuna?','Hur står jag mig mot andra i min ålder?'],
  'starter.baskets': ['Explain the three baskets','Selitä kolme koria','Förklara de tre korgarna'],
  'action.create_goal': ['Review goal','Tarkista tavoite','Granska mål'],
  'action.save_scenario': ['Review spending scenario','Tarkista muutos','Granska ändringen'],
  'action.open_view': ['Open view','Avaa näkymä','Öppna vy'],
  scenarioReview: ['Reduce {category} by {percent}% for {month}.','Vähennä luokan {category} menoja {percent} % ajalta {month}.','Minska {category} med {percent} % för {month}.'],
  scenarioHelp: ['This saves a planning scenario. It does not change your transactions or move money.','Tämä tallentaa suunnitelman. Se ei muuta tapahtumiasi eikä siirrä rahaa.','Det här sparar en plan. Den ändrar inte dina transaktioner och flyttar inga pengar.'],
  confirmScenario: ['Confirm & save scenario','Vahvista ja tallenna','Bekräfta och spara'],
  'step.get_overview': ['Reviewed your account overview','Tarkastelin tilisi yleiskuvaa','Granskade kontoöversikten'],
  'step.spending_total': ['Counted spending in the selected period','Laskin valitun ajanjakson menot','Räknade utgifterna under vald period'],
  'step.compare_periods': ['Compared spending across the selected periods','Vertasin valittujen ajanjaksojen menoja','Jämförde utgifter mellan valda perioder'],
  'step.monthly_trend': ['Reviewed monthly spending','Tarkastelin kuukausimenoja','Granskade månadsutgifter'],
  'step.list_transactions': ['Reviewed matching transactions','Tarkastelin vastaavia tapahtumia','Granskade matchande transaktioner'],
  'step.safe_to_spend': ['Estimated spending room until payday after bills and saving','Arvioin käyttövaran palkkapäivään asti laskujen ja säästön jälkeen','Uppskattade utrymmet till lönedagen efter räkningar och sparande'],
  'step.spender_profile': ['Described your spending style from recent months','Kuvasin kulutustyyliäsi viime kuukausilta','Beskrev din utgiftsstil de senaste månaderna'],
  'step.irregular_buffer': ['Reviewed your Surprise must-pays','Tarkastelin yllättäviä pakollisia menojasi','Granskade dina oväntade måsten'],
  'step.safe_to_save': ['Estimated what could be saved before payday','Arvioin, paljonko voisi säästää ennen palkkapäivää','Uppskattade vad som kan sparas före lönedagen'],
  'step.forecast_30_days': ['Reviewed the cash-flow forecast','Tarkastelin saldon 30 päivän ennustetta','Granskade saldoprognosen för 30 dagar'],
  'step.what_if_reduce': ['Calculated an unsaved spending adjustment','Laskin, mitä menojen pienentäminen tekisi (ei tallennettu)','Räknade på en minskning av utgifterna (inte sparad)'],
  'step.goal_plan': ['Calculated a goal plan without saving it','Laskin tavoitesuunnitelman tallentamatta sitä','Räknade fram en plan för målet utan att spara den'],
  'step.list_goals': ['Reviewed saved goals','Tarkastelin tallennettuja tavoitteita','Granskade sparade mål'],
  'step.payday_pattern': ['Reviewed salary timing and balances','Tarkastelin palkan ajoitusta ja saldoja','Granskade lönetidpunkter och saldon'],
  'step.recurring_payments': ['Reviewed recurring payments','Tarkastelin toistuvia maksuja','Granskade återkommande betalningar'],
  'step.calculate': ['Calculated using sourced figures','Laskin tilisi luvuilla','Räknade med siffror från ditt konto'],
  'step.explain_concept': ['Checked the financial glossary','Tarkistin taloussanaston','Kontrollerade den ekonomiska ordlistan'],
  'step.propose_action': ['Prepared an optional next step','Valmistelin valinnaisen seuraavan askeleen','Förberedde ett valfritt nästa steg'],
};
for (const [key, values] of Object.entries(AGENT_MESSAGES)) { EN['agent.'+key]=values[0]; FI['agent.'+key]=values[1]; SV['agent.'+key]=values[2]; }

const RECAP_MESSAGES = {
  label:['Monthly recap','Kuukauden yhteenveto','Månadssammanfattning'],
  title:['Your month · {period}','Kuukautesi · {period}','Din månad · {period}'],
  income:['Recorded income was {amount}.','Tuloja tuli {amount}.','Det kom in {amount}.'],
  spending:['Spending came to {amount}.','Menot olivat {amount}.','Utgifterna uppgick till {amount}.'],
  saving:['Transfers to savings totaled {amount}.','Säästöihin siirrettiin yhteensä {amount}.','Överföringar till sparande var totalt {amount}.'],
  noFacts:['Monthly figures are not available yet.','Kuukauden luvut eivät ole vielä saatavilla.','Månadens siffror är inte tillgängliga ännu.'],
  unavailable:["We couldn't load this month's figures.",'Kuukauden lukuja ei voitu ladata.','Det gick inte att läsa in månadens siffror.'],
  pending:['Writing your monthly recap…','Kirjoitetaan kuukausiyhteenvetoa…','Skriver din månadssammanfattning…'],
  ai:['AI recap · based on recorded transactions','Tekoälykooste · perustuu kirjattuihin tapahtumiin','AI-sammanfattning · baserad på registrerade transaktioner'],
  recorded:['Account summary · based on recorded figures','Tiliyhteenveto · perustuu kirjattuihin lukuihin','Kontosammanfattning · baserad på registrerade siffror'],
  open:['Explore with Coach','Tutki valmentajan kanssa','Utforska med coachen'],
  question:['Help me understand my income, spending and savings transfers in {period}.','Auta minua ymmärtämään tulojani, menojani ja säästösiirtojani {period:in}.','Hjälp mig förstå mina inkomster, utgifter och överföringar till sparande under {period}.'],
  followup:['Where did most of my spending go in {period}?','Mihin suurin osa menoistani meni {period:in}?','Vart gick största delen av mina utgifter under {period}?'],
};
for (const [key, values] of Object.entries(RECAP_MESSAGES)) { EN['home.recap.'+key]=values[0]; FI['home.recap.'+key]=values[1]; SV['home.recap.'+key]=values[2]; }

// V3 strings (docs/COACH_V3_PLAN.md). Keys are exposed as 'v3.<key>'.
const V3_MESSAGES = {
  offlineAnswer:['Quick answer (offline)','Pikavastaus','Snabbsvar'],
  retryAgent:['Try again with the AI coach','Yritä uudelleen tekoälyvalmentajalla','Försök igen med AI-coachen'],
  basketExamples:['This month: {items}','Tässä kuussa: {items}','Den här månaden: {items}'],
  'safe.week':['You can spend this week','Voit käyttää tällä viikolla','Du kan spendera den här veckan'],
  'safe.perDay':['About {amount} a day until payday on {date} ({days} days).','Noin {amount} päivässä palkkapäivään {date} asti ({days} {days|päivä|päivää}).','Ungefär {amount} om dagen fram till lönedagen {date} ({days} {days|dag|dagar}).'],
  'safe.balance':['Balance now','Saldo nyt','Saldo nu'],
  'safe.bills':['Bills before payday, set aside','Laskut ennen palkkapäivää, varattu','Räkningar före lönedagen, avsatta'],
  'safe.reserve':['Small reserve, set aside','Turvatyyny, pidetään sivussa','Säkerhetsmarginal, hålls undan'],
  'safe.saving':['Your planned saving, set aside','Suunniteltu säästösi, varattu','Ditt planerade sparande, avsatt'],
  'safe.save':['The other {amount} is more than you usually spend, so it could be saved.','Loput {amount} on enemmän kuin tavallisesti käytät, joten sen voisi säästää.','Resten, {amount}, är mer än du brukar spendera, så det kan sparas.'],
  'safe.everyday':['Everyday costs until payday, set aside','Arjen menot palkkapäivään asti, varattu','Vardagsutgifter fram till lönedagen, avsatta'],
  'safe.buffer':['Surprise costs, set aside','Yllätyspuskuri, varattu','Buffert för oväntat, avsatt'],
  'safe.free':['Free until payday','Vapaana palkkapäivään asti','Fritt fram till lönedagen'],
  'safe.shortfall':['Bills, everyday costs and your cushion need {amount} more than you have before payday.','Ennen palkkapäivää erääntyvät laskut ovat {amount} enemmän kuin turvatyynyn jälkeen jää.','Räkningarna före lönedagen är {amount} mer än det som blir kvar efter säkerhetsmarginalen.'],
  'safe.steady':['Steady mode: a full month of Must-pays is kept as your reserve.','Rauhallinen tahti: turvatyynyksi pidetään sivussa koko kuukauden pakolliset menot.','Lugnt tempo: en hel månads fasta måsten hålls undan som säkerhetsmarginal.'],
  'safe.note':['Estimate from your recorded bills and pay dates, not a guarantee.','Arvio kirjattujen laskujen ja palkkapäivien perusteella, ei takuu.','Uppskattning utifrån registrerade räkningar och lönedagar, ingen garanti.'],
  'safe.noPayday':['No regular payday found, so this looks 30 days ahead.','Säännöllistä palkkapäivää ei löytynyt, joten arvio katsoo 30 päivää eteenpäin.','Ingen regelbunden lönedag hittades, så uppskattningen gäller 30 dagar framåt.'],
  'nav.profile':['Me','Minä','Jag'],
  delete:['Delete','Poista','Ta bort'],
  'cashflow.summary':['Money in vs money out','Tulot ja menot','Pengar in och ut'],
  'cashflow.title':['Money in vs money out','Tulot ja menot','Pengar in och ut'],
  'cashflow.month':['Month','Kuukausi','Månad'],
  'cashflow.year':['Year','Vuosi','År'],
  'cashflow.net':['Stayed in your account','Jäi tilille','Blev kvar på kontot'],
  'cashflow.leftOver':['Left over after spending','Menojen jälkeen jäi','Kvar efter utgifter'],
  'cashflow.rate':['Share of income left over','Osuus tuloista, joka jäi yli','Andel av inkomsten som blev över'],
  'cashflow.partial':['Partial period','Vajaa jakso','Ofullständig period'],
  'cashflow.rateSame':['You kept {to} of your income after spending in both {start} and {end}.','Sekä {start} että {end} tuloistasi jäi menojen jälkeen {to}.','Både {start} och {end} blev {to} av inkomsten kvar efter utgifterna.'],
  'cashflow.rateChange':['After spending, {from} of your income was left in {start} and {to} in {end}.','Menojen jälkeen tuloistasi jäi {from} ({start}) ja {to} ({end}).','Efter utgifterna blev {from} av inkomsten kvar ({start}) och {to} ({end}).'],
  'cashflow.ask':['How did my money in and out look in {period}?','Miltä tuloni ja menoni näyttivät {period:in}?','Hur såg mina inkomster och utgifter ut under {period}?'],
  'cashflow.askLabel':['Ask coach about this period','Kysy valmentajalta tästä jaksosta','Fråga coachen om perioden'],
  'trend.ask':['What happened with my spending in {month}?','Mitä menoilleni tapahtui {month:in}?','Vad hände med mina utgifter i {month}?'],
  'goal.newTitle':['I can save this goal for you','Voin tallentaa tämän tavoitteen','Jag kan spara det här målet'],
  'goal.editTitle':['Change this goal','Muuta tavoitetta','Ändra målet'],
  'goal.intro':['Check the details and change anything before saving. Saving a goal does not move money.','Tarkista tiedot ja muuta niitä ennen tallennusta. Tavoitteen tallentaminen ei siirrä rahaa.','Kontrollera uppgifterna och ändra innan du sparar. Att spara ett mål flyttar inga pengar.'],
  'goal.name':['Goal name','Tavoitteen nimi','Målets namn'],
  'goal.target':['Target amount','Tavoitesumma','Målbelopp'],
  'goal.date':['Target date','Tavoitepäivä','Måldatum'],
  'goal.saved':['Already saved','Jo säästetty','Redan sparat'],
  'goal.save':['Save goal','Tallenna tavoite','Spara målet'],
  'goal.preview':['About {amount} a month for {months} months, until {date}.','Noin {amount} kuukaudessa {months} kuukauden ajan, {date} asti.','Ungefär {amount} i månaden i {months} {months|månad|månader}, till {date}.'],
  'goal.edit':['Edit','Muokkaa','Redigera'],
  'goal.delete':['Delete goal','Poista tavoite','Ta bort målet'],
  'goal.deleteTitle':['Delete "{name}"?','Poistetaanko "{name}"?','Ta bort "{name}"?'],
  'goal.deleteIntro':['The goal is removed and any linked plan is unlinked. You can undo this from the demo menu.','Tavoite poistetaan ja siihen liitetty suunnitelma irrotetaan. Voit perua tämän demovalikosta.','Målet tas bort och kopplade planer kopplas loss. Du kan ångra detta i demomenyn.'],
  'profile.deleteTitle':['Remove this from your profile?','Poistetaanko tämä profiilistasi?','Ta bort detta från din profil?'],
  'profile.forgetTitle':['Forget everything in your profile?','Unohdetaanko kaikki profiilisi tiedot?','Glöm allt i din profil?'],
  'profile.forgetIntro':['Your coach will no longer use anything you shared. Transactions are not affected.','Valmentaja ei enää käytä mitään kertomaasi. Tapahtumiin tämä ei vaikuta.','Coachen använder inte längre något du har delat. Transaktionerna påverkas inte.'],
  'profile.noteTitle':["I'd like to note this in your profile",'Haluaisin merkitä tämän profiiliisi','Jag skulle vilja anteckna detta i din profil'],
  'profile.migrate':['You have notes saved in this browser from earlier. Move them into your money profile?','Tähän selaimeen on tallennettu aiempia muistiinpanoja. Siirretäänkö ne talousprofiiliisi?','Du har tidigare anteckningar sparade i webbläsaren. Flytta dem till din ekonomiprofil?'],
  'profile.migrateAction':['Move my notes','Siirrä muistiinpanot','Flytta anteckningarna'],
  'onboarding.saved':['Saved to your money profile. You can change it anytime under Me.','Tallennettu talousprofiiliisi. Voit muuttaa tietoja milloin vain kohdassa Minä.','Sparat i din ekonomiprofil. Du kan ändra det när som helst under Jag.'],
  'tax.eyebrow':['Taxes','Verot','Skatter'],
  'tax.title':['My taxes','Omat veroni','Mina skatter'],
  'tax.explainer':['Your account only shows salary after tax, because income tax is withheld by your tax card. Add your tax card details to follow it.','Tililläsi näkyy vain verojen jälkeinen palkka, koska tulovero pidätetään verokortin mukaan. Lisää verokorttisi tiedot seurataksesi sitä.','Kontot visar bara lön efter skatt eftersom inkomstskatten dras enligt skattekortet. Lägg till dina skattekortsuppgifter för att följa den.'],
  'tax.missing':['Add your tax card rate and gross salary from a payslip to see an estimate.','Lisää verokortin pidätysprosentti ja bruttopalkka palkkalaskelmasta nähdäksesi arvion.','Lägg till skattekortets procent och bruttolön från lönebeskedet för att se en uppskattning.'],
  'tax.next':['Next date: {date} ({days} days)','Seuraava päivä: {date} ({days} {days|päivä|päivää})','Nästa datum: {date} ({days} {days|dag|dagar})'],
  'tax.setAside':['Setting aside about {amount} a month covers your back taxes on time.','Noin {amount} kuukaudessa riittää jäännösveron maksamiseen ajallaan.','Ungefär {amount} i månaden räcker för att betala kvarskatten i tid.'],
  'tax.refundSeen':['Your tax refund of {amount} arrived on {date}.','Veronpalautuksesi {amount} saapui {date}.','Din skatteåterbäring på {amount} kom {date}.'],
  'tax.add':['Add my tax card details','Lisää verokorttini tiedot','Lägg till mina skattekortsuppgifter'],
  'tax.edit':['Edit my tax details','Muokkaa verotietojani','Redigera mina skatteuppgifter'],
  'tax.footer':['Estimate from what you entered. Your tax decision in MyTax is the official source.','Arvio antamiesi tietojen perusteella. OmaVeron veropäätös on virallinen lähde.','Uppskattning utifrån det du angett. Beskattningsbeslutet i MinSkatt är den officiella källan.'],
  'vat.eyebrow':['Did you know?','Tiesitkö?','Visste du?'],
  'vat.line':['About {vat} of the {spent} you spent on {category} was VAT ({rate}).','{category}: menoistasi {spent} noin {vat} oli arvonlisäveroa ({rate:pct}).','{category}: av dina utgifter på {spent} var ungefär {vat} moms ({rate:pct}).'],
  'vat.note':['VAT is already inside shop prices; the shop pays it to the state.','Arvonlisävero sisältyy jo hintoihin; kauppa tilittää sen valtiolle.','Momsen ingår redan i priset; butiken betalar den till staten.'],
  'year.saved':['Saved to your profile.','Tallennettu profiiliisi.','Sparat i din profil.'],
  'year.ask':['Tell me about my {year} in money.','Kerro minulle rahavuodestani {year}.','Berätta om mitt {year} i pengar.'],
  'recap.income':['Money in','Tulot','Pengar in'],
  'recap.spent':['Spent','Menot','Utgifter'],
  'recap.saved':['To savings','Säästöön','Till sparande'],
  'recap.vs':['{amount} vs {month}','{amount} vs. {month}','{amount} jämfört med {month}'],
  'recap.same':['Same as last month','Sama kuin viime kuussa','Samma som förra månaden'],
  'recap.good':['Went well:','Meni hyvin:','Gick bra:'],
  'recap.watch':['Worth a look:','Kannattaa katsoa:','Värt att titta på:'],
};
for (const [key, values] of Object.entries(V3_MESSAGES)) { EN['v3.'+key]=values[0]; FI['v3.'+key]=values[1]; SV['v3.'+key]=values[2]; }


// Keys used by the V3 chart, range and agent components (no prefix).
const V3_COMPONENT_MESSAGES = {
  'chart.detail.label':['{month}','{month}','{month}'],
  'chart.detail.total':['Spent','Menot','Utgifter'],
  'chart.detail.change.up':['{amount} more than the month before ({percent}%)','{amount} enemmän kuin edellisenä kuukautena ({percent} %)','{amount} mer än månaden innan ({percent} %)'],
  'chart.detail.change.down':['{amount} less than the month before ({percent}%)','{amount} vähemmän kuin edellisenä kuukautena ({percent} %)','{amount} mindre än månaden innan ({percent} %)'],
  'chart.detail.change.upNoPercent':['{amount} more than the month before','{amount} enemmän kuin edellisenä kuukautena','{amount} mer än månaden innan'],
  'chart.detail.change.downNoPercent':['{amount} less than the month before','{amount} vähemmän kuin edellisenä kuukautena','{amount} mindre än månaden innan'],
  'chart.detail.change.same':['Same as the month before','Sama kuin edellisenä kuukautena','Samma som månaden innan'],
  'chart.detail.noPrevious':['No previous month to compare','Ei edellistä kuukautta vertailuun','Ingen tidigare månad att jämföra med'],
  'chart.detail.topCategories':['Biggest categories','Suurimmat luokat','Största kategorierna'],
  'chart.detail.noCategories':['Category details are loading or unavailable','Luokkatiedot latautuvat tai eivät ole saatavilla','Kategoriuppgifterna laddas eller saknas'],
  'chart.detail.transactions':['See transactions','Katso tapahtumat','Se transaktioner'],
  'chart.detail.ask':['Ask coach about this month','Kysy valmentajalta tästä kuukaudesta','Fråga coachen om månaden'],
  'chart.cashflow.title':['Money in vs money out','Tulot ja menot','Pengar in och ut'],
  'chart.cashflow.empty':['No periods to show yet.','Ei vielä näytettäviä jaksoja.','Inga perioder att visa än.'],
  'chart.cashflow.income':['Money in','Tulot','Pengar in'],
  'chart.cashflow.spending':['Money out','Menot','Utgifter'],
  'chart.cashflow.net':['Left over','Jäi yli','Blev över'],
  'chart.cashflow.savings':['To savings','Säästöön','Till sparande'],
  'chart.cashflow.netNote':['Left over = money in − money out − savings transfers','Jäi yli = tulot − menot − säästöön siirretyt','Blev över = pengar in − utgifter − flyttat till sparande'],
  'chart.cashflow.partial':['Partial','Vajaa','Ofullständig'],
  'chart.cashflow.partialLegend':['Partial period','Vajaa jakso','Ofullständig period'],
  'chart.cashflow.partialPeriod':['partial period','vajaa jakso','ofullständig period'],
  'chart.cashflow.bar':['{label}: money in {income}, money out {spending}, left over {net}','{label}: tulot {income}, menot {spending}, jäi yli {net}','{label}: pengar in {income}, utgifter {spending}, blev över {net}'],
  'range.label':['Time range','Aikaväli','Tidsperiod'],
  'range.from':['From','Alkaen','Från'],
  'range.to':['To','Asti','Till'],
  'range.earlier':['−1 month','−1 kk','−1 mån'],
  'range.later':['+1 month','+1 kk','+1 mån'],
  'range.last12':['Last 12 months','Viimeiset 12 kk','Senaste 12 mån'],
  'range.summary':['{count} months: {start} – {end}','{count} kk: {start} – {end}','{count} mån: {start} – {end}'],
  'agent.action.update_goal':['Review goal change','Tarkista tavoitteen muutos','Granska måländringen'],
  'agent.action.delete_goal':['Review goal removal','Tarkista tavoitteen poisto','Granska borttagningen'],
  'agent.action.update_profile':['Review what to note','Tarkista muistiin merkittävä','Granska vad som antecknas'],
  'agent.action.open_year_review':['Open my year in money','Avaa rahavuoteni','Öppna mitt år i pengar'],
  'agent.step.explore':['Explored your spending patterns','Tutkin kulutustottumuksiasi','Utforskade dina utgiftsmönster'],
  'agent.step.cashflow_summary':['Compared money in and out over time','Vertasin tulojen ja menojen kehitystä','Jämförde inkomster och utgifter över tid'],
  'agent.step.get_profile':['Checked what you have shared with me','Tarkistin, mitä olet kertonut','Kontrollerade vad du har delat'],
  'agent.step.propose_profile_update':['Prepared something to note, for your review','Valmistelin muistiinpanon tarkistettavaksesi','Förberedde en anteckning för din granskning'],
  'agent.step.tax_overview':['Reviewed your tax details','Tarkastelin verotietojasi','Granskade dina skatteuppgifter'],
  'agent.step.vat_in_my_spending':['Estimated the VAT inside your purchases','Arvioin ostoksiin sisältyvän arvonlisäveron','Uppskattade momsen i dina köp'],
  'agent.step.compare_to_peers':['Compared with Finnish households of your age (Statistics Finland 2022)','Vertasin ikäisiisi suomalaisiin kotitalouksiin (Tilastokeskus 2022)','Jämförde med finländska hushåll i din ålder (Statistikcentralen 2022)'],
  'agent.step.year_review':['Looked back at your year','Katsoin vuottasi taaksepäin','Såg tillbaka på ditt år'],
};
for (const [key, values] of Object.entries(V3_COMPONENT_MESSAGES)) { EN[key]=values[0]; FI[key]=values[1]; SV[key]=values[2]; }

// V5 lane TR: "How spending changes over time" line chart, tooltip and summary sentence.
const V5_TREND_MESSAGES = {
  'chartTitle':['Monthly spending','Kuukauden menot','Utgifter per månad'],
  'point':['{month}: {amount} spent','{month}: menot {amount}','{month}: utgifter {amount}'],
  'hint.tap':['Tap a month to see what you spent.','Napauta kuukautta, niin näet menosi.','Tryck på en månad för att se vad du spenderade.'],
  'hint.hover':['Point at or tap a month to see what you spent.','Osoita tai napauta kuukautta, niin näet menosi.','Peka på eller tryck på en månad för att se vad du spenderade.'],
  'tip.spent':['spent','menot','utgifter'],
  'tip.loading':['Finding the biggest categories…','Haetaan suurimpia menoluokkia…','Hämtar de största kategorierna…'],
  'tip.none':['No category breakdown for this month','Tälle kuukaudelle ei ole luokkajakoa','Ingen kategorifördelning för den här månaden'],
  'tip.transactions':['See transactions','Katso tapahtumat','Se transaktioner'],
  'summary.one':['You spent {amount} in {month}.','{month}: menosi olivat {amount}.','{month}: du spenderade {amount}.'],
  'summary.steady':['Your spending has been fairly steady, between {low} and {high} a month.','Menosi ovat pysyneet melko tasaisina, {low}–{high} kuukaudessa.','Dina utgifter har varit ganska jämna, mellan {low} och {high} i månaden.'],
  'summary.up':['Your spending has gone up, from about {from} to about {to} a month.','Menosi ovat kasvaneet: aiemmin noin {from}, nyt noin {to} kuukaudessa.','Dina utgifter har ökat, från ungefär {from} till ungefär {to} i månaden.'],
  'summary.down':['Your spending has come down, from about {from} to about {to} a month.','Menosi ovat pienentyneet: aiemmin noin {from}, nyt noin {to} kuukaudessa.','Dina utgifter har minskat, från ungefär {from} till ungefär {to} i månaden.'],
  'summary.varied':['Your spending has moved between {low} and {high} a month; {month} was the biggest month.','Menosi ovat vaihdelleet {low}–{high} kuukaudessa (eniten: {month}).','Dina utgifter har varierat mellan {low} och {high} i månaden; mest gick det åt i {month}.'],
  'salary':['Your salary has been about {amount} a month lately.','Palkkasi on viime aikoina ollut noin {amount} kuukaudessa.','Din lön har på senare tid varit ungefär {amount} i månaden.'],
};
for (const [key, values] of Object.entries(V5_TREND_MESSAGES)) { EN['v5.tr.'+key]=values[0]; FI['v5.tr.'+key]=values[1]; SV['v5.tr.'+key]=values[2]; }

// V4 lane F (docs/V4_SPEC.md). Plain English copy and one term per concept:
// Money in · Spent · To savings · Goal · Safety cushion. FI/SV values of existing keys belong to the language pass,
// so English rewrites of existing keys live here as overrides instead of editing the shared lines above.
const V4_EN_COPY = {
  'coach.verified': 'Numbers come from your account. Nothing changes without your OK.',
  'coach.offlineMode': 'Quick answers · Numbers come from your account · Nothing changes without your OK',
  'coach.aiMode': 'AI coach · Numbers come from your account · Nothing changes without your OK',
  'evidence.deterministic': 'Checked against your transactions',
  'evidence.formula': 'How we calculated this',
  'evidence.goalFormula': 'What is left = goal minus what you have saved. Monthly amount = what is left ÷ months until the date. Your monthly room comes from the last six full months, after bills. Transfers to savings are counted separately.',
  'evidence.calculationSources': 'Payments behind this',
  'evidence.historySources': 'Past months we compared with',
  'evidence.assumptions': 'What we assumed',
  'goal.capacity': 'After bills and your usual spending, you have about {amount} left each month.',
  'goal.reserveDetail': 'We keep {reserve} untouched as your safety cushion. You have {upfront} more in your account.',
  'goal.gap': 'You would need to put aside {amount} a month. A later date makes that smaller.',
  'goal.required': 'a month',
  'goal.linked': '{amount} a month from your spending change is set towards this goal. No money is moved.',
  'goal.assumptions': 'How we worked this out',
  'goal.reserve': 'Safety cushion to keep',
  'goal.disclosure': 'This is a plan. It does not move any money.',
  'goal.intro': 'A trip, a safety cushion, something just for you.',
  'goal.template.buffer': 'Safety cushion',
  'feedback.goal': 'Your goal is saved. The plan keeps your safety cushion untouched.',
  'trends.description': 'Spending in {count} full months.',
  'chart.noAverage': 'No average yet',
  'common.scenario': 'Estimate',
  'money.income': 'Money in',
  'safe.reserve': 'Safety cushion kept aside',
  'safe.demoReserve': '{amount} is kept aside as your safety cushion.',
  'safe.everydayAllowance': 'Usual everyday spending until then',
  'safe.assumption.0': 'Money you expect to get is only counted once it arrives.',
  'safe.assumption.1': 'Bills and transfers that come back regularly are held back.',
  'safe.assumption.2': 'We also hold back a margin for everyday spending, based on your busier months.',
  'v3.safe.reserve': 'Safety cushion, kept aside',
  'v3.safe.shortfall': 'Bills before payday are {amount} more than what is left after your safety cushion.',
  'v3.safe.steady': 'Steady mode: a full month of Must-pays is kept as your safety cushion.',
  'forecast.subtitle': 'A 30-day estimate based on the bills and income that repeat in your history.',
  'vat.coverage': 'Spending matched to a VAT rate',
  'vat.coverageNote': 'Shows how much of your spending we could match to a VAT rate. It does not say how exact the estimate is.',
  'vat.method': 'VAT inside a price = price × rate ÷ (1 + rate), worked out for each purchase from the kind of shop.',
  'vat.mapping.direct_mcc': 'Rate from the kind of shop',
  'vat.mapping.broad_mcc_estimate': 'Estimated from the kind of shop',
  'vat.mapping.unmapped': 'No VAT rate found',
  'vat.source.unmapped': 'No VAT rate found',
  'vat.limitation.ambiguous': 'Some shops sell things at different VAT rates, so a few purchases have no rate.',
  'investment.title': 'Money moved to savings',
  'v2.spending.investments': 'Money moved to savings',
  'investment.coverageLimited': 'Only {count} months of history are available for this range.',
  'chart.cashflow.spending': 'Spent',
  'chart.cashflow.bar': '{label}: money in {income}, spent {spending}, left over {net}',
  'chart.cashflow.netNote': 'Left over = money in − spent − moved to savings',
  'home.recap.income': 'Money in was {amount}.',
  'taxPlan.help': 'This estimate is not saved. It combines what you enter with your balance and safety cushion.',
  'taxPlan.disclaimer': 'Not saved · Not tax advice',
  'taxPlan.resultTitle': 'Your tax set-aside plan',
  'taxPlan.reference': 'Worked out on',
  'taxPlan.reserve': 'Safety cushion',
  'taxPlan.afterSetAside': 'Left above your safety cushion after setting it all aside',
  'taxPlan.notAdvice': 'Not tax advice. We did not calculate any tax, rate or deduction, and this estimate was not saved.',
  'coach.result.unsaved': 'Not saved',
  'coach.result.exploreScenario': 'Explore this change',
  'coach.question.buffer': 'Plan a safety cushion',
  'agent.action.save_scenario': 'Review this change',
  'agent.scenarioHelp': 'This saves a plan. It does not change your transactions or move money.',
  'agent.confirmScenario': 'Confirm and save',
  'v2.wish.buffer': 'A safety cushion',
  'vat.gross': 'Spending this month',
  'coach.otherLanguage': 'Ask in English, Finnish or Swedish.',
  'vat.disclaimer': 'Worked out from the kind of shop for each purchase. This is not a personal tax calculation.',
};
for (const [key, value] of Object.entries(V4_EN_COPY)) {
  if (!(key in EN)) throw new Error('V4 EN override for unknown key ' + key);
  EN[key] = value;
}
// New V4 keys (EN, FI, SV).
const V4_MESSAGES = {
  'chat.reset.month': ['Started a new chat for {period}.', 'Aloitettiin uusi keskustelu: {period}.', 'Ett nytt samtal för {period} har börjat.'],
  'chat.reset.persona': ['Started a new chat for {name}.', 'Aloitettiin uusi keskustelu: {name}.', 'Ett nytt samtal för {name} har börjat.'],
  'chat.reset.language': ['Started a new chat in English.', 'Aloitettiin uusi keskustelu suomeksi.', 'Ett nytt samtal på svenska har börjat.'],
  'chat.reset.reset': ['The demo was reset, so the chat started again.', 'Demo palautettiin alkutilaan, joten keskustelu alkoi alusta.', 'Demon återställdes, så samtalet började om.'],
  'investment.sources': ['Transfers behind this', 'Siirrot tämän takana', 'Överföringarna bakom detta'],
  'vat.source.shop': ['Kind of shop', 'Kauppatyyppi', 'Typ av butik'],
  'vat.rateRowOne': ['{rate} · 1 purchase · ≈ {amount}', '{rate} · 1 ostos · ≈ {amount}', '{rate} · 1 köp · ≈ {amount}'],
  'spending.period.label': ['Period', 'Jakso', 'Period'],
  'spending.period.month': ['Month', 'Kuukausi', 'Månad'],
  'spending.period.3': ['3 months', '3 kk', '3 mån'],
  'spending.period.6': ['6 months', '6 kk', '6 mån'],
  'spending.period.12': ['12 months', '12 kk', '12 mån'],
  'month.previous': ['Previous month', 'Edellinen kuukausi', 'Föregående månad'],
  'month.next': ['Next month', 'Seuraava kuukausi', 'Nästa månad'],
};
for (const [key, values] of Object.entries(V4_MESSAGES)) { EN[key] = values[0]; FI[key] = values[1]; SV[key] = values[2]; }
// V5 lane SP: Spending page structure (EN, FI, SV).
const V5_SP_MESSAGES = {
  'v5.sp.where': ['Where it went', 'Mihin rahat menivät', 'Vart pengarna gick'],
  'v5.sp.baskets': ['Look by basket', 'Katso koreittain', 'Visa per korg'],
  'v5.sp.basketsIntro': ['Baskets sort your spending by how much choice you had.', 'Korit jakavat menot sen mukaan, kuinka paljon niihin voi itse vaikuttaa.', 'Korgarna delar upp utgifterna efter hur mycket du själv kan påverka dem.'],
  'v5.sp.more': ['More about your money', 'Lisää raha-asioistasi', 'Mer om dina pengar'],
  'v5.sp.moreHint': ['Money in and out, savings transfers, VAT', 'Tulot ja menot, siirrot säästöön, arvonlisävero', 'Pengar in och ut, överföringar till sparande, moms'],
  'v5.sp.byType': ["This month's money, group by group", 'Kuukauden rahat ryhmittäin', 'Månadens pengar, grupp för grupp'],
  'v5.sp.byTypeHelp': ['Open a group to see the purchases behind it.', 'Avaa ryhmä, niin näet sen takana olevat ostokset.', 'Öppna en grupp för att se köpen bakom den.'],
};
for (const [key, values] of Object.entries(V5_SP_MESSAGES)) { EN[key] = values[0]; FI[key] = values[1]; SV[key] = values[2]; }
// V5 fix wave, lane SP2: Spending charts, category sheet, baskets and the assumptions form (EN, FI, SV).
const V5_SP2_MESSAGES = {
  'v5.sp.tx.purchases.one': ['{count} purchase', '{count} ostos', '{count} köp'],
  'v5.sp.tx.purchases.other': ['{count} purchases', '{count} ostosta', '{count} köp'],
  'v5.sp.tx.rows.one': ['{count} transaction', '{count} tapahtuma', '{count} transaktion'],
  'v5.sp.tx.rows.other': ['{count} transactions', '{count} tapahtumaa', '{count} transaktioner'],
  'v5.sp.tx.all': ['All transactions', 'Kaikki tapahtumat', 'Alla transaktioner'],
  'v5.sp.tx.footnote': ['Shop names are not shown here, so purchases are listed by date.', 'Kauppojen nimiä ei näytetä, joten ostokset on listattu päivämäärän mukaan.', 'Butiksnamn visas inte här, så köpen listas efter datum.'],
  'v5.sp.viewTx.one': ['View 1 transaction', 'Näytä 1 tapahtuma', 'Visa 1 transaktion'],
  'v5.sp.viewTx.other': ['View {count} transactions', 'Näytä {count} tapahtumaa', 'Visa {count} transaktioner'],
  'v5.sp.share.regular': ['{percent}% of must-pays', '{percent} % pakollisista kuukausimenoista', '{percent} % av de fasta måstena'],
  'v5.sp.share.irregular': ['{percent}% of surprise must-pays', '{percent} % yllättävistä pakollisista menoista', '{percent} % av de oväntade måstena'],
  'v5.sp.share.leaks': ['{percent}% of little leaks', '{percent} % arjen pikkumenoista', '{percent} % av vardagens småutgifter'],
  'v5.sp.trendScope': ['Showing {basket} only', 'Näytetään vain: {basket}', 'Visar bara: {basket}'],
  'v5.sp.trendShowAll': ['Show all spending', 'Näytä kaikki menot', 'Visa alla utgifter'],
  'v5.sp.trendRange': ['Months shown', 'Näytettävät kuukaudet', 'Visade månader'],
  'v5.sp.fa.intro': ['Change an amount or a day, or switch an item off, to see how the next 30 days could look.', 'Muuta summaa tai päivää tai jätä erä pois, niin näet, miltä seuraavat 30 päivää voisivat näyttää.', 'Ändra ett belopp eller en dag, eller stäng av en post, för att se hur de kommande 30 dagarna kan se ut.'],
  'v5.sp.fa.in': ['Money in', 'Tuloa', 'Pengar in'],
  'v5.sp.fa.out': ['Money out', 'Menoa', 'Pengar ut'],
  'v5.sp.fa.include': ['Include {name}', 'Ota mukaan: {name}', 'Ta med {name}'],
  'v5.sp.fa.amount': ['Amount', 'Summa', 'Belopp'],
  'v5.sp.fa.day': ['Day of month', 'Päivä kuussa', 'Dag i månaden'],
  'v5.sp.fa.apply': ['Update the chart', 'Päivitä kuvaaja', 'Uppdatera diagrammet'],
  'v5.sp.fa.note': ['This only changes the chart above. Nothing is saved.', 'Tämä muuttaa vain yllä olevaa kuvaajaa. Mitään ei tallenneta.', 'Det här ändrar bara diagrammet ovan. Inget sparas.'],
  'v5.sp.fa.name.payday': ['Salary', 'Palkka', 'Lön'],
  'v5.sp.fa.name.income': ['Other money in', 'Muut tulot', 'Övriga inkomster'],
  'v5.sp.fa.name.rent': ['Rent', 'Vuokra', 'Hyra'],
  'v5.sp.fa.name.loan': ['Loan payment', 'Lainanlyhennys', 'Låneavbetalning'],
  'v5.sp.fa.name.homeBills': ['Home bills', 'Kotilaskut', 'Hemräkningar'],
  'chart.cashflow.leftShort': ['Left over', 'Jäi yli', 'Kvar'],
  'v5.fc.today': ['Today', 'Tänään', 'Idag'],
};
for (const [key, values] of Object.entries(V5_SP2_MESSAGES)) { EN[key] = values[0]; FI[key] = values[1]; SV[key] = values[2]; }

// V5 lane FC: the 30-day balance chart (EN, FI, SV).
const V5_FC_MESSAGES = {
  'title': ['Your balance over the next 30 days', 'Saldosi seuraavat 30 päivää', 'Ditt saldo de kommande 30 dagarna'],
  'tightest': ['Tightest day: {amount} on {date}.', 'Alin saldo: {amount} ({date}).', 'Lägsta saldot: {amount} ({date}).'],
  'tightestBeforePayday': ['Tightest day: {amount} on {date}, the day before payday.', 'Alin saldo: {amount} ({date}), päivää ennen palkkapäivää.', 'Lägsta saldot: {amount} ({date}), dagen före lönedagen.'],
  'aboveCushion': ['You stay above your safety cushion.', 'Pysyt koko ajan turvatyynysi yläpuolella.', 'Du håller dig hela tiden över din säkerhetsmarginal.'],
  'aboveZero': ['Your balance stays above zero.', 'Saldosi pysyy plussalla.', 'Ditt saldo håller sig på plus.'],
  'belowCushion': ['That dips under your {cushion} safety cushion, so go gently until then.', 'Silloin saldo käy alle {cushion} turvatyynysi, joten ota siihen asti rauhallisesti.', 'Då går saldot under din säkerhetsmarginal på {cushion}, så ta det lugnt fram till dess.'],
  'belowZero': ['Your balance could go below zero from {date}. Moving a payment or setting money aside before then would help.', 'Saldosi voi mennä miinukselle {date} alkaen. Maksun siirtäminen tai rahan varaaminen ennen sitä auttaisi.', 'Ditt saldo kan gå på minus från {date}. Det hjälper att flytta en betalning eller lägga undan pengar innan dess.'],
  'soFar': ['So far', 'Tähän asti', 'Hittills'],
  'expected': ['Expected', 'Odotettu', 'Väntat'],
  'expectedBalance': ['Expected balance', 'Odotettu saldo', 'Väntat saldo'],
  'usualRange': ['Usual range', 'Tavallinen vaihtelu', 'Vanligt spann'],
  'tipRange': ['Usually {low}–{high}', 'Tavallisesti {low}–{high}', 'Vanligtvis {low}–{high}'],
  'lowest': ['Lowest {amount}', 'Alin {amount}', 'Lägst {amount}'],
  'cushionLabel': ['Safety cushion', 'Turvatyyny', 'Säkerhetsmarginal'],
  'event.payday': ['Payday', 'Palkkapäivä', 'Lönedag'],
  'event.income': ['Money in', 'Tuloja', 'Pengar in'],
  'event.rent': ['Rent', 'Vuokra', 'Hyra'],
  'event.loan': ['Loan', 'Laina', 'Lån'],
  'event.homeBills': ['Home bills', 'Kotilaskut', 'Hemräkningar'],
  'event.bill': ['Bill', 'Lasku', 'Räkning'],
  'chartDescription': ['Balance from {start} to {end}, ending around {amount}. Lowest {lowest} on {date}. The shaded area is your usual range.', 'Saldo {start}–{end}, lopussa noin {amount}. Alimmillaan {lowest} ({date}). Varjostus näyttää tavallisen vaihtelun.', 'Saldo från {start} till {end}, i slutet cirka {amount}. Lägst {lowest} ({date}). Det skuggade området visar det vanliga spannet.'],
  'chartDescriptionPlain': ['Ending around {amount}. Lowest {lowest}. The shaded area is your usual range.', 'Lopussa noin {amount}. Alimmillaan {lowest}. Varjostus näyttää tavallisen vaihtelun.', 'I slutet cirka {amount}. Lägst {lowest}. Det skuggade området visar det vanliga spannet.'],
  'keyboard': ['Use the arrow keys to read each day.', 'Lue päivä kerrallaan nuolinäppäimillä.', 'Läs dag för dag med piltangenterna.'],
  'tapHint': ['Tap the chart to see any day.', 'Napauta kuvaajaa: näet päivän saldon.', 'Tryck på diagrammet för att se en dag.'],
  'howTitle': ['How is this worked out?', 'Miten tämä lasketaan?', 'Hur räknas det här ut?'],
  'how': ['We continue your usual pay, rent, bills and day-to-day spending from your own history. The shaded usual range shows how much your spending normally varies. New or unusual costs can change it.', 'Arvio laskee eteenpäin tavallisella palkallasi, vuokrallasi, laskuillasi ja arjen menoillasi omasta historiastasi. Varjostettu alue näyttää, kuinka paljon menosi tavallisesti vaihtelevat. Uudet tai yllättävät menot voivat muuttaa arviota.', 'Vi räknar framåt med din vanliga lön, hyra, räkningar och vardagsutgifter utifrån din egen historik. Det skuggade området visar hur mycket dina utgifter brukar variera. Nya eller ovanliga kostnader kan ändra bilden.'],
  'unavailable': ['We need a little more account history to draw your next 30 days.', 'Tarvitsemme vähän enemmän tilihistoriaa, jotta voimme näyttää seuraavat 30 päivää.', 'Vi behöver lite mer kontohistorik för att visa de kommande 30 dagarna.'],
};
for (const [key, values] of Object.entries(V5_FC_MESSAGES)) { EN['v5.fc.' + key] = values[0]; FI['v5.fc.' + key] = values[1]; SV['v5.fc.' + key] = values[2]; }

// V5 lane NV (app shell): the one-line context chip and the customer-and-month sheet.
const V5_NV_MESSAGES = {
  'v5.nv.sheetTitle': ['Customer and month', 'Asiakas ja kuukausi', 'Kund och månad'],
  'v5.nv.chipLabel': ['Change customer or month', 'Vaihda asiakas tai kuukausi', 'Byt kund eller månad'],
};
for (const [key, values] of Object.entries(V5_NV_MESSAGES)) { EN[key] = values[0]; FI[key] = values[1]; SV[key] = values[2]; }

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

// Finnish month labels ("syyskuu 2026") and years take the inessive ("syyskuussa 2026",
// "vuonna 2026") when a template writes {name:in}. Other values and locales are left as they are.
function finnishInessive(text) {
  const month = /^(\S*kuu)(\s+\d{4})?$/i.exec(text);
  if (month) return month[1] + 'ssa' + (month[2] || '');
  if (/^\d{4}$/.test(text)) return 'vuonna ' + text;
  return text;
}

function formatValue(value, locale, filter) {
  // Decimal numbers follow the language: 9.6 → "9,6" in Finnish and Swedish.
  // The API sends some percentages as strings ("9.6"), so plain decimal strings count too.
  const decimalText = typeof value === 'string' && /^-?\d+\.\d+$/.test(value.trim());
  let text = locale !== 'en' && ((typeof value === 'number' && Number.isFinite(value) && !Number.isInteger(value)) || decimalText)
    ? new Intl.NumberFormat(intlLocale(locale), {maximumFractionDigits: 2, useGrouping: false}).format(Number(value))
    : String(value);
  if (filter === 'in' && locale === 'fi') text = finnishInessive(text);
  // Rate labels from the server ("13.5% and 25.5%") get a decimal comma, a spaced % and a local "and".
  if (filter === 'pct' && locale !== 'en') {
    text = text.replace(/(\d)\.(\d)/g, '$1,$2').replace(/\s*%/g, ' %').replace(/\s+(?:and|&)\s+/g, locale === 'fi' ? ' ja ' : ' och ');
  }
  return text;
}

// Plural choice: "{count|tapahtuma|tapahtumaa}" gives the first form after exactly 1, the second
// otherwise. Finnish, Swedish and English all use "one" only for 1, so no locale table is needed.
export function choosePlural(template, values = {}) {
  return String(template).replace(/\{(\w+)\|([^|{}]*)\|([^{}]*)\}/g, (_, key, one, other) => (Number(values?.[key]) === 1 ? one : other));
}

export function interpolate(template, values, locale = 'en') {
  return choosePlural(template, values).replace(/\{([A-Za-z0-9_]+)(?::([a-z]+))?\}/g, (match, key, filter) =>
    Object.prototype.hasOwnProperty.call(values, key) ? formatValue(values[key], normalizeLocale(locale), filter) : match
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
      return interpolate(template, values, current);
    },
  };
}

/* ---------------------------------------------------------------- server sentences (FI / SV)
 * Finnish and Swedish versions of short English sentences that the server still sends as
 * plain text (safe-to-spend and forecast assumptions). Matching is by sentence, never by
 * position, so a reordered or new server list can't put the wrong translation on a line.
 * Unknown sentences are returned unchanged.
 */
const serverDecimal = value => String(value).replace('.', ',');

// [pattern, fi, sv]; fi/sv may be functions of the RegExp match.
const SERVER_SENTENCES = [
  [/^Expected income is excluded until it arrives\.?$/,
    'Tulevia tuloja ei lasketa mukaan ennen kuin ne ovat tilillä.',
    'Väntade inkomster räknas inte med förrän de har kommit in.'],
  [/^Taxes or obligations not present in the transaction history or your profile are not inferred\.?$/,
    'Veroja tai muita maksuja, jotka eivät näy tapahtumissa tai profiilissasi, ei arvata.',
    'Skatter eller andra betalningar som inte syns i transaktionerna eller i din profil gissas inte.'],
  [/^No regular salary found, so a 30-day horizon is used instead of payday\.?$/,
    'Säännöllistä palkkaa ei löytynyt, joten arvio katsoo 30 päivää eteenpäin.',
    'Ingen regelbunden lön hittades, så uppskattningen gäller 30 dagar framåt.'],
  [/^Next payday uses the usual salary day \((\d{1,2})\), moved to the month end in shorter months\.?$/,
    m => `Seuraava palkkapäivä on tavallinen palkkapäiväsi, kuun ${m[1]}. päivä (lyhyempinä kuukausina kuun viimeinen päivä).`,
    m => `Nästa lönedag är din vanliga lönedag, den ${m[1]} i månaden (i kortare månader den sista dagen).`],
  [/^Declared debts and investing count once this pay cycle.*$/,
    'Kertomasi lainat ja sijoitukset lasketaan kerran tällä palkkajaksolla. Samaa maksua ei vähennetä kahdesti.',
    'Lån och investeringar som du har berättat om räknas en gång under den här löneperioden. Samma betalning dras inte av två gånger.'],
  [/^Steady mode: the reserve covers at least one month of Must-pays.*$/,
    'Rauhallinen tahti: turvatyyny kattaa vähintään kuukauden pakolliset menot, eikä säästöä suunnitella.',
    'Lugnt tempo: säkerhetsmarginalen täcker minst en månads fasta måsten och inget sparande planeras.'],
  [/^Steady mode: no saving is planned this pay cycle\.?$/,
    'Rauhallinen tahti: tällä palkkajaksolla ei suunnitella säästöä.',
    'Lugnt tempo: inget sparande planeras under den här löneperioden.'],
  [/^No saving target set, so nothing is set aside for saving\.?$/,
    'Säästötavoitetta ei ole asetettu, joten säästöön ei varata mitään.',
    'Inget sparmål är satt, så inget läggs undan för sparande.'],
  [/^Saving target set, but no salary was found to apply it to\.?$/,
    'Säästötavoite on asetettu, mutta palkkaa, josta säästää, ei löytynyt.',
    'Det finns ett sparmål, men ingen lön att spara från hittades.'],
  [/^([\d.]+)% saving target of your last salary.*$/,
    m => `Säästötavoite: ${serverDecimal(m[1])} % viimeisestä palkastasi.`,
    m => `Sparmål: ${serverDecimal(m[1])} % av din senaste lön.`],
  [/^Safe to save needs at least thirty days of history.*$/,
    'Säästövaran arvioon tarvitaan vähintään 30 päivän tapahtumat, joten se näytetään nollana.',
    'Sparutrymmet kräver minst 30 dagars historik, så det visas som noll.'],
  [/^Safe to save keeps back a busy.*month of everyday spending.*$/,
    'Säästövaraa laskettaessa arjen menoihin jätetään palkkapäivään asti sen verran kuin kalliimpana kuukautena yleensä kuluu.',
    'Sparutrymmet lämnar kvar så mycket som en dyrare månad av vardagsutgifter brukar kosta, fram till lönedagen.'],
  [/^Qualified recurring patterns use robust median dates and amounts\.?$/,
    'Toistuvat maksut arvioidaan niiden tavallisen päivän ja summan mukaan.',
    'Återkommande betalningar uppskattas utifrån deras vanliga datum och belopp.'],
  [/^Unscheduled consumption uses historical 30-day variation.*$/,
    'Muut menot arvioidaan aiemman 30 päivän vaihtelun perusteella.',
    'Övriga utgifter uppskattas utifrån hur de har varierat under tidigare 30-dagarsperioder.'],
  [/^No unconfirmed income or tax inference\.?$/,
    'Vahvistamattomia tuloja tai veroja ei arvata.',
    'Obekräftade inkomster eller skatter gissas inte.'],
  [/^Transfers affect balance and remain separate from consumption\.?$/,
    'Siirrot vaikuttavat saldoon, mutta niitä ei lasketa kulutukseksi.',
    'Överföringar påverkar saldot men räknas inte som konsumtion.'],
  [/^Median amount and calendar day from up to six complete months\.?$/,
    'Tavallinen summa ja päivä enintään kuuden täyden kuukauden ajalta.',
    'Vanligt belopp och datum från högst sex hela månader.'],
  [/^Salary\/housing seed recurrence; utilities are a monthly envelope\.?$/,
    'Palkka ja asumismenot toistuvat kuukausittain; laskut arvioidaan kuukausisummana.',
    'Lön och boende återkommer varje månad; räkningar uppskattas som en månadssumma.'],
];

/**
 * @param {string} text   English sentence from the server
 * @param {string} locale 'en' | 'fi' | 'sv'
 * @returns {string} the FI/SV sentence when known, otherwise text unchanged
 */
export function localizeServerText(text, locale) {
  if (typeof text !== 'string' || (locale !== 'fi' && locale !== 'sv')) return text;
  const trimmed = text.trim();
  for (const [pattern, fi, sv] of SERVER_SENTENCES) {
    const match = pattern.exec(trimmed);
    if (!match) continue;
    const value = locale === 'fi' ? fi : sv;
    return typeof value === 'function' ? value(match) : value;
  }
  return text;
}

