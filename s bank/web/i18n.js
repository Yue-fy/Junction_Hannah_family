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
  'basket.regular.help': 'Bills that usually repeat, such as rent.',
  'basket.irregular': 'Unexpected essentials',
  'basket.irregular.help': 'Necessary costs that do not happen every month.',
  'basket.everyday': 'Everyday spending',
  'basket.everyday.help': 'Day-to-day choices such as groceries, cafés and transport.',
  'basket.saving': 'Saving and transfers',
  'basket.saving.help': 'Money moved to savings or investments, kept separate from spending.',
  'forecast.title': 'What may happen next',
  'forecast.subtitle': 'A 30-day cash-flow estimate using confirmed recurring items.',
  'forecast.assumptions': 'Review assumptions',
  'forecast.disclaimer': 'This is a planning estimate, not a promise or a probability.',
  'trends.eyebrow': 'Look back and understand',
  'trends.title': 'Your patterns',
  'trends.subtitle': 'Compare complete periods on the same basis.',
  'trends.monthByMonth': 'Month by month',
  'trends.whatChanged': 'What changed?',
  'trends.sameMonth': 'Same month last year',
  'trends.salary': 'Salary, shown separately',
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
  'coach.otherLanguage': 'Finnish, Swedish and English work offline. With AI enabled, the coach can reply in the language you use.',
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
  'basket.regular.help': 'Yleensä toistuvat laskut, kuten vuokra.',
  'basket.irregular': 'Satunnaiset pakolliset menot',
  'basket.irregular.help': 'Välttämättömät kulut, joita ei tule joka kuukausi.',
  'basket.everyday': 'Arjen menot',
  'basket.everyday.help': 'Arjen valinnat, kuten ruokaostokset, kahvilat ja liikkuminen.',
  'basket.saving': 'Säästöt ja siirrot',
  'basket.saving.help': 'Säästöihin tai sijoituksiin siirretty raha, erillään kulutuksesta.',
  'forecast.title': 'Mitä voi tapahtua seuraavaksi',
  'forecast.subtitle': '30 päivän kassavirta-arvio vahvistetuista toistuvista tapahtumista.',
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
  'coach.otherLanguage': 'Suomi, ruotsi ja englanti toimivat ilman tekoälyä. Kun tekoäly on käytössä, valmentaja voi vastata käyttämälläsi kielellä.',
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
  'basket.regular.help': 'Räkningar som brukar återkomma, till exempel hyra.',
  'basket.irregular': 'Oväntade nödvändiga utgifter',
  'basket.irregular.help': 'Nödvändiga kostnader som inte kommer varje månad.',
  'basket.everyday': 'Vardagsutgifter',
  'basket.everyday.help': 'Vardagsval som mat, kaféer och resor.',
  'basket.saving': 'Sparande och överföringar',
  'basket.saving.help': 'Pengar som flyttats till sparande eller investeringar, skilt från konsumtion.',
  'forecast.title': 'Vad som kan hända härnäst',
  'forecast.subtitle': 'En 30-dagars kassaflödesuppskattning med bekräftade återkommande poster.',
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
  'coach.otherLanguage': 'Finska, svenska och engelska fungerar utan AI. När AI är aktiverad kan coachen svara på språket du använder.',
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
