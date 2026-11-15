/**
 * Money profile UI (WP-I): onboarding intro, Profile page, entry descriptions and draft-card specs.
 *
 * Everything here is pure: no fetch, no storage, no globals. Render functions return HTML strings;
 * the attach helpers only add event listeners to a root element you pass in and call your callbacks.
 * Money is integer cents. Pass your own money(cents) formatter where available; a locale-aware EUR
 * fallback is used otherwise.
 */
import { describePlan } from './plans.js';

export const PROFILE_KEYS = Object.freeze([
  'life_stage', 'household', 'income_stability', 'saving_rate_target_pct', 'emergency_fund_target_months',
  'regular_investing', 'debts', 'risk_attitude', 'coaching_style', 'protected_categories', 'upcoming',
  'life_event', 'note', 'year_review', 'tax',
]);
export const PROFILE_SOURCES = Object.freeze(['you_told_me', 'from_your_transactions', 'from_our_chat', 'year_review']);
export const LIFE_STAGES = Object.freeze(['student', 'working', 'self_employed', 'between_jobs', 'parental_leave', 'retired']);
export const INCOME_STABILITY = Object.freeze(['steady', 'varies', 'irregular']);
export const RISK_ATTITUDES = Object.freeze(['cautious', 'balanced', 'adventurous']);
export const COACHING_STYLES = Object.freeze(['gentle', 'direct']);
export const DEBT_TYPES = Object.freeze(['mortgage', 'student_loan', 'car_loan', 'consumer_credit', 'other']);
export const LIFE_EVENT_TYPES = Object.freeze(['job_loss', 'income_drop', 'large_loss', 'new_child', 'moving', 'other']);
export const STEADY_EVENT_TYPES = Object.freeze(['job_loss', 'income_drop', 'large_loss']);
export const TAX_DECISIONS = Object.freeze(['refund', 'back_tax', 'none']);
const ONBOARDING_LOANS = ['mortgage', 'student_loan', 'car_loan', 'other'];
const ASSESSMENT_MONTHS = [5, 6, 7, 8, 9, 10];
const NOTE_MAX = 500;

/** Profile page sections in display order: {id, keys}. Entries of a key not listed here are not shown. */
export const PROFILE_SECTIONS = Object.freeze([
  {id: 'about', keys: ['life_stage', 'household', 'income_stability', 'risk_attitude', 'coaching_style', 'protected_categories']},
  {id: 'income', keys: ['saving_rate_target_pct', 'emergency_fund_target_months', 'regular_investing']},
  {id: 'loans', keys: ['debts']},
  {id: 'upcoming', keys: ['upcoming']},
  {id: 'events', keys: ['life_event']},
  {id: 'taxes', keys: ['tax']},
  {id: 'plans', keys: ['plan_mortgage', 'plan_tax']},
  {id: 'notes', keys: ['note']},
  {id: 'reviews', keys: ['year_review']},
].map(Object.freeze));

/** Keys offered by the "Add something" menu (tax and year_review have their own flows). */
export const ADDABLE_KEYS = Object.freeze([
  'note', 'upcoming', 'debts', 'life_event', 'saving_rate_target_pct', 'emergency_fund_target_months',
  'regular_investing', 'life_stage', 'household', 'income_stability', 'risk_attitude', 'coaching_style',
  'protected_categories',
]);

/* ---------------------------------------------------------------- messages (EN / FI / SV) */
const COPY = {
  'key.life_stage': ['Life stage', 'Elämäntilanne', 'Livssituation'],
  'key.household': ['Household', 'Kotitalous', 'Hushåll'],
  'key.income_stability': ['How steady my income is', 'Tulojen tasaisuus', 'Hur jämn min inkomst är'],
  'key.saving_rate_target_pct': ['Saving target', 'Säästötavoite', 'Sparmål'],
  'key.emergency_fund_target_months': ['Emergency fund target', 'Puskurin tavoite', 'Buffertmål'],
  'key.regular_investing': ['Regular investing', 'Säännöllinen sijoittaminen', 'Regelbundet investerande'],
  'key.debts': ['Loans', 'Lainat', 'Lån'],
  'key.risk_attitude': ['Attitude to risk', 'Suhtautuminen riskiin', 'Inställning till risk'],
  'key.coaching_style': ['Coaching style', 'Valmennustyyli', 'Coachningsstil'],
  'key.protected_categories': ['Spending I leave alone', 'Menot, joista en halua tinkiä', 'Utgifter jag inte vill dra ner på'],
  'key.upcoming': ['Coming up', 'Tulossa', 'På gång'],
  'key.life_event': ['Life event', 'Elämäntapahtuma', 'Livshändelse'],
  'key.note': ['Note', 'Muistiinpano', 'Anteckning'],
  'key.tax': ['Taxes', 'Verot', 'Skatter'],
  'key.year_review': ['Year in review', 'Vuosikatsaus', 'Årsöversikt'],

  'source.you_told_me': ['You told me', 'Kerroit minulle', 'Du berättade'],
  'source.from_your_transactions': ['From your transactions', 'Tilitapahtumistasi', 'Från dina transaktioner'],
  'source.from_our_chat': ['From our chat', 'Keskustelustamme', 'Från vårt samtal'],
  'source.year_review': ['Year in review', 'Vuosikatsaus', 'Årsöversikt'],

  'life_stage.student': ['Student', 'Opiskelija', 'Studerande'],
  'life_stage.working': ['Working', 'Töissä', 'Arbetar'],
  'life_stage.self_employed': ['Self-employed', 'Yrittäjä', 'Egenföretagare'],
  'life_stage.between_jobs': ['Between jobs', 'Työnhaussa', 'Mellan jobb'],
  'life_stage.parental_leave': ['On parental leave', 'Perhevapaalla', 'Föräldraledig'],
  'life_stage.retired': ['Retired', 'Eläkkeellä', 'Pensionär'],
  'income_stability.steady': ['About the same every month', 'Suunnilleen samat joka kuukausi', 'Ungefär samma varje månad'],
  'income_stability.varies': ['It varies a little', 'Vaihtelevat jonkin verran', 'Den varierar lite'],
  'income_stability.irregular': ['It is irregular', 'Epäsäännölliset', 'Den är oregelbunden'],
  'risk_attitude.cautious': ['Play it safe', 'Varman päälle', 'Hellre säkert'],
  'risk_attitude.balanced': ['Somewhere in between', 'Jotain siltä väliltä', 'Någonstans mittemellan'],
  'risk_attitude.adventurous': ['Take some risk', 'Otan vähän riskiä', 'Tar gärna lite risk'],
  'coaching_style.gentle': ['Gentle', 'Lempeä', 'Varsam'],
  'coaching_style.direct': ['Direct', 'Suora', 'Rakt på sak'],
  'debt.mortgage': ['Mortgage', 'Asuntolaina', 'Bolån'],
  'debt.student_loan': ['Student loan', 'Opintolaina', 'Studielån'],
  'debt.car_loan': ['Car loan', 'Autolaina', 'Billån'],
  'debt.consumer_credit': ['Consumer credit', 'Kulutusluotto', 'Konsumtionskredit'],
  'debt.other': ['Other loan', 'Muu laina', 'Annat lån'],
  'event.job_loss': ['Lost my job', 'Menetin työpaikkani', 'Jag förlorade jobbet'],
  'event.income_drop': ['Income dropped', 'Tuloni pienenivät', 'Min inkomst minskade'],
  'event.large_loss': ['Large unexpected cost', 'Iso odottamaton meno', 'Stor oväntad kostnad'],
  'event.new_child': ['New child in the family', 'Perheeseen syntyi lapsi', 'Vi fick barn'],
  'event.moving': ['Moving', 'Muutto', 'Flytt'],
  'event.other': ['Something else', 'Jotain muuta', 'Något annat'],
  'decision.refund': ['Refund', 'Veronpalautus', 'Skatteåterbäring'],
  'decision.back_tax': ['Back taxes', 'Jäännösvero', 'Kvarskatt'],
  'decision.none': ['Nothing to pay or receive', 'Ei maksettavaa eikä palautusta', 'Inget att betala eller få tillbaka'],
  'decision.unknown': ['No decision yet', 'Ei vielä päätöstä', 'Inget beslut än'],
  'common.yes': ['Yes', 'Kyllä', 'Ja'],
  'common.no': ['No', 'Ei', 'Nej'],
  'common.blank': ['—', '—', '—'],

  'describe.household.alone': ['Just you', 'Vain minä', 'Bara jag'],
  'describe.adults.one': ['1 adult', '1 aikuinen', '1 vuxen'],
  'describe.adults.many': ['{n} adults', '{n} aikuista', '{n} vuxna'],
  'describe.children.none': ['no children', 'ei lapsia', 'inga barn'],
  'describe.children.one': ['1 child', '1 lapsi', '1 barn'],
  'describe.children.many': ['{n} children', '{n} lasta', '{n} barn'],
  'describe.pct': ['{pct}% of income', '{pct} % tuloista', '{pct} % av inkomsten'],
  'describe.months.one': ['1 month of expenses', '1 kuukauden menot', '1 månads utgifter'],
  'describe.months.many': ['{n} months of expenses', '{n} kuukauden menot', '{n} månaders utgifter'],
  'describe.investing.amount': ['Yes, {amount} a month', 'Kyllä, {amount} kuukaudessa', 'Ja, {amount} per månad'],
  'describe.investing.yes': ['Yes, every month', 'Kyllä, joka kuukausi', 'Ja, varje månad'],
  'describe.investing.no': ['Not at the moment', 'Ei tällä hetkellä', 'Inte just nu'],
  'describe.debts.none': ['No loans', 'Ei lainoja', 'Inga lån'],
  'describe.debt': ['{loan} {amount} a month', '{loan} {amount} kuukaudessa', '{loan} {amount} per månad'],
  'describe.debt.remaining': ['{amount} left', '{amount} jäljellä', '{amount} kvar'],
  'describe.upcoming.none': ['Nothing planned', 'Ei mitään suunniteltua', 'Inget planerat'],
  'describe.upcoming.cost': ['about {amount}', 'noin {amount}', 'cirka {amount}'],
  'describe.event.since': ['{event} since {date}', '{event} ({date} alkaen)', '{event} (sedan {date})'],
  'describe.protected.none': ['None', 'Ei mitään', 'Inga'],
  'describe.tax.rate': ['Tax card {rate}%', 'Verokortti {rate} %', 'Skattekort {rate} %'],
  'describe.tax.additional': ['{rate}% above the income limit', '{rate} % tulorajan ylittävältä osalta', '{rate} % över inkomstgränsen'],
  'describe.tax.gross': ['gross {amount} a month', 'bruttopalkka {amount} kuukaudessa', 'bruttolön {amount} per månad'],
  'describe.tax.ytd': ['gross {amount} so far this year', 'bruttopalkka tänä vuonna {amount}', 'bruttolön hittills i år {amount}'],
  'describe.tax.refund': ['refund {amount}', 'veronpalautus {amount}', 'skatteåterbäring {amount}'],
  'describe.tax.back_tax': ['back taxes {amount}', 'jäännösvero {amount}', 'kvarskatt {amount}'],
  'describe.tax.year': ['Tax year {year}', 'Verovuosi {year}', 'Skatteår {year}'],
  'describe.tax.empty': ['Tax details saved', 'Verotiedot tallennettu', 'Skatteuppgifter sparade'],
  'describe.review': ['Your {year} in money', 'Rahavuotesi {year}', 'Ditt år i pengar {year}'],
  'describe.review.generic': ['A saved year in review', 'Tallennettu vuosikatsaus', 'En sparad årsöversikt'],

  'onboarding.intro': ['Let’s get to know each other. A few quick questions, and you can skip any of them.', 'Tutustutaan! Muutama nopea kysymys – voit ohittaa minkä tahansa.', 'Vi bekantar oss! Några snabba frågor – du kan hoppa över vilken som helst.'],
  'onboarding.progress': ['Question {n} of {total}', 'Kysymys {n}/{total}', 'Fråga {n} av {total}'],
  'onboarding.progressSummary': ['Summary', 'Yhteenveto', 'Sammanfattning'],
  'onboarding.skip': ['Skip', 'Ohita', 'Hoppa över'],
  'onboarding.back': ['Back', 'Takaisin', 'Tillbaka'],
  'onboarding.next': ['Next', 'Seuraava', 'Nästa'],
  'onboarding.skipAll': ['Skip the intro', 'Ohita kysymykset', 'Hoppa över frågorna'],
  'onboarding.q.life_stage': ['What best describes you right now?', 'Mikä kuvaa sinua parhaiten juuri nyt?', 'Vad beskriver dig bäst just nu?'],
  'onboarding.q.household': ['Who do you share money with?', 'Keiden kanssa jaat arjen raha-asiat?', 'Vem delar du vardagsekonomin med?'],
  'onboarding.q.income_stability': ['How steady is your income?', 'Kuinka tasaiset tulosi ovat?', 'Hur jämn är din inkomst?'],
  'onboarding.q.saving_rate_target_pct': ['How much of your income would you like to keep?', 'Kuinka suuren osan tuloistasi haluaisit jättää säästöön?', 'Hur stor del av inkomsten vill du lägga undan?'],
  'onboarding.q.regular_investing': ['Do you invest a fixed amount every month?', 'Sijoitatko joka kuukausi saman summan?', 'Investerar du ett fast belopp varje månad?'],
  'onboarding.q.debts': ['Any loans?', 'Onko sinulla lainoja?', 'Har du några lån?'],
  'onboarding.q.risk_attitude': ['When money surprises you, do you prefer to play it safe or take some risk?', 'Kun raha-asioissa tulee yllätyksiä, pelaatko mieluummin varman päälle vai otatko vähän riskiä?', 'När det kommer överraskningar i ekonomin, spelar du hellre säkert eller tar du lite risk?'],
  'onboarding.q.upcoming': ['Anything big coming up in the next year?', 'Onko seuraavan vuoden aikana tulossa jotain isoa?', 'Är det något stort på gång under det närmaste året?'],
  'onboarding.household.alone': ['Just me', 'Vain minä', 'Bara jag'],
  'onboarding.household.partner': ['Me and my partner', 'Minä ja kumppanini', 'Jag och min partner'],
  'onboarding.household.kids': ['Me and my children', 'Minä ja lapseni', 'Jag och mina barn'],
  'onboarding.household.partner_kids': ['My partner and children', 'Minä, kumppanini ja lapset', 'Jag, min partner och barnen'],
  'onboarding.children': ['How many children?', 'Montako lasta?', 'Hur många barn?'],
  'onboarding.slider': ['{pct}% of income', '{pct} % tuloista', '{pct} % av inkomsten'],
  'onboarding.notSure': ['Not sure yet', 'En ole vielä varma', 'Inte säker än'],
  'onboarding.investing.no': ['No', 'En', 'Nej'],
  'onboarding.investing.yes': ['Yes', 'Kyllä', 'Ja'],
  'onboarding.investing.amount': ['How much a month?', 'Paljonko kuukaudessa?', 'Hur mycket per månad?'],
  'onboarding.loans.none': ['No loans', 'Ei lainoja', 'Inga lån'],
  'onboarding.loans.help': ['Choose all that apply.', 'Valitse kaikki sopivat.', 'Välj alla som stämmer.'],
  'onboarding.loans.payment': ['{loan}: monthly payment', '{loan}: kuukausierä', '{loan}: månadsbetalning'],
  'onboarding.upcoming.placeholder': ['For example moving, a wedding or a new car', 'Esimerkiksi muutto, häät tai uusi auto', 'Till exempel flytt, bröllop eller ny bil'],
  'onboarding.upcoming.what': ['What is coming up?', 'Mitä on tulossa?', 'Vad är på gång?'],
  'onboarding.upcoming.when': ['Roughly when?', 'Suunnilleen milloin?', 'Ungefär när?'],
  'onboarding.upcoming.cost': ['Rough cost (optional)', 'Arvioitu hinta (vapaaehtoinen)', 'Ungefärlig kostnad (valfritt)'],
  'onboarding.summary.title': ['Here’s what you told me', 'Tässä, mitä kerroit', 'Det här berättade du'],
  'onboarding.summary.help': ['Nothing is saved until you tap Save.', 'Mitään ei tallenneta ennen kuin napautat Tallenna.', 'Inget sparas förrän du trycker på Spara.'],
  'onboarding.summary.skipped': ['Skipped', 'Ohitettu', 'Överhoppad'],
  'onboarding.summary.change': ['Change', 'Muuta', 'Ändra'],
  'onboarding.summary.changeLabel': ['Change: {label}', 'Muuta: {label}', 'Ändra: {label}'],
  'onboarding.noticed': ['Here’s what I noticed in your account', 'Tätä huomasin tililläsi', 'Det här märkte jag på ditt konto'],
  'onboarding.noticed.none': ['Nothing new to suggest right now.', 'Ei uusia ehdotuksia juuri nyt.', 'Inga nya förslag just nu.'],
  'onboarding.save': ['Save to my money profile', 'Tallenna talousprofiiliini', 'Spara i min ekonomiprofil'],
  'onboarding.skipForNow': ['Skip for now', 'Ohita toistaiseksi', 'Hoppa över tills vidare'],

  'error.needChoice': ['Choose one option.', 'Valitse yksi vaihtoehto.', 'Välj ett alternativ.'],
  'error.badAmount': ['Enter an amount like 250 or 1 200,50.', 'Kirjoita summa, esimerkiksi 250 tai 1 200,50.', 'Ange ett belopp, till exempel 250 eller 1 200,50.'],
  'error.needAmount': ['Enter the monthly payment.', 'Kirjoita kuukausierä.', 'Ange månadsbetalningen.'],
  'error.needLoan': ['Choose at least one loan, or No loans.', 'Valitse vähintään yksi laina tai Ei lainoja.', 'Välj minst ett lån eller Inga lån.'],
  'error.needText': ['Tell me what is coming up.', 'Kerro, mitä on tulossa.', 'Berätta vad som är på gång.'],
  'error.needMonth': ['Choose roughly when.', 'Valitse suunnilleen milloin.', 'Välj ungefär när.'],
  'error.needDate': ['Choose a date.', 'Valitse päivämäärä.', 'Välj ett datum.'],
  'error.badRange': ['Choose a value between {min} and {max}.', 'Valitse arvo väliltä {min}–{max}.', 'Välj ett värde mellan {min} och {max}.'],
  'error.tooLong': ['Keep it under {max} characters.', 'Enintään {max} merkkiä.', 'Högst {max} tecken.'],
  'error.required': ['This is needed.', 'Tämä tieto tarvitaan.', 'Det här behövs.'],

  'page.title': ['What your coach knows about you', 'Mitä valmentajasi tietää sinusta', 'Vad din coach vet om dig'],
  'page.subtitle': ['Only what you told me or confirmed. Change or delete anything at any time.', 'Vain se, minkä kerroit tai vahvistit. Voit muuttaa tai poistaa mitä tahansa milloin vain.', 'Bara det du berättat eller bekräftat. Du kan ändra eller ta bort vad som helst när som helst.'],
  'section.about': ['About me', 'Minusta', 'Om mig'],
  'section.income': ['Income & saving', 'Tulot ja säästäminen', 'Inkomst och sparande'],
  'section.loans': ['Loans', 'Lainat', 'Lån'],
  'section.upcoming': ['Coming up', 'Tulossa', 'På gång'],
  'section.events': ['Life events', 'Elämäntapahtumat', 'Livshändelser'],
  'section.taxes': ['Taxes', 'Verot', 'Skatter'],
  'section.plans': ['My plans', 'Suunnitelmani', 'Mina planer'],
  'key.plan_mortgage': ['Mortgage plan', 'Asuntolainasuunnitelma', 'Bolåneplan'],
  'key.plan_tax': ['Tax plan', 'Verosuunnitelma', 'Skatteplan'],
  'section.notes': ['My notes', 'Muistiinpanoni', 'Mina anteckningar'],
  'section.reviews': ['My yearly reviews', 'Vuosikatsaukseni', 'Mina årsöversikter'],
  'entry.edit': ['Edit', 'Muokkaa', 'Ändra'],
  'entry.delete': ['Delete', 'Poista', 'Ta bort'],
  'entry.editLabel': ['Edit {label}', 'Muokkaa: {label}', 'Ändra {label}'],
  'entry.deleteLabel': ['Delete {label}', 'Poista: {label}', 'Ta bort {label}'],
  'entry.updated': ['Updated {date}', 'Päivitetty {date}', 'Uppdaterad {date}'],
  'taxes.open': ['Open my taxes', 'Avaa verotietoni', 'Öppna mina skatteuppgifter'],
  'taxes.help': ['Add your tax card and tax decision to follow your taxes.', 'Lisää verokorttisi ja veropäätöksesi tiedot, niin voit seurata verojasi.', 'Lägg till ditt skattekort och beskattningsbeslut för att följa dina skatter.'],
  'reviews.open': ['Watch again', 'Katso uudelleen', 'Se igen'],
  'steady.title': ['Steady mode is on', 'Rauhallinen tahti on käytössä', 'Lugnt tempo är på'],
  'steady.reason.job_loss': ['Steady mode is on because you told me you lost your job.', 'Kerroit menettäneesi työpaikkasi, joten etenemme nyt rauhallisemmin.', 'Du berättade att du har förlorat jobbet, så vi tar det lite lugnare nu.'],
  'steady.reason.income_drop': ['Steady mode is on because you told me your income has dropped.', 'Kerroit tulojesi pienentyneen, joten etenemme nyt rauhallisemmin.', 'Du berättade att din inkomst har minskat, så vi tar det lite lugnare nu.'],
  'steady.reason.large_loss': ['Steady mode is on because you told me about a large unexpected cost.', 'Kerroit isosta odottamattomasta menosta, joten etenemme nyt rauhallisemmin.', 'Du berättade om en stor oväntad kostnad, så vi tar det lite lugnare nu.'],
  'steady.reason.generic': ['Steady mode is on while things settle.', 'Etenemme rauhallisemmin, kunnes tilanne tasaantuu.', 'Vi tar det lite lugnare tills läget har stabiliserats.'],
  'steady.help': ['I’ll focus on must-pays and your buffer, and keep saving suggestions small.', 'Keskityn välttämättömiin maksuihin ja puskuriin, ja säästöehdotukset pidän pieninä.', 'Jag fokuserar på det som måste betalas och på din buffert, och håller sparförslagen små.'],
  'steady.off': ['Turn off', 'Lopeta', 'Avsluta'],
  'noticed.title': ['Things I noticed', 'Huomasin nämä', 'Saker jag märkt'],
  'noticed.help': ['Nothing is saved until you choose Keep.', 'Mitään ei tallenneta, ennen kuin valitset Tallenna.', 'Inget sparas förrän du väljer Spara.'],
  'noticed.keep': ['Keep', 'Tallenna', 'Spara'],
  'noticed.dismiss': ['Not this', 'Ei, kiitos', 'Nej tack'],
  'noticed.evidence': ['Based on: {label}', 'Perusteena: {label}', 'Baserat på: {label}'],
  'noticed.fallback': ['Should I note this: {value}?', 'Merkitäänkö tämä muistiin: {value}?', 'Ska jag anteckna det här: {value}?'],
  'actions.add': ['Add something', 'Lisää jotain', 'Lägg till något'],
  'actions.addTitle': ['What would you like to add?', 'Mitä haluat lisätä?', 'Vad vill du lägga till?'],
  'actions.onboarding': ['Start the intro again', 'Vastaa alkukysymyksiin uudelleen', 'Svara på startfrågorna igen'],
  'actions.forget': ['Forget everything', 'Unohda kaikki', 'Glöm allt'],
  'actions.forgetHelp': ['Deletes your whole money profile. Your transactions stay as they are.', 'Poistaa koko talousprofiilisi. Tilitapahtumasi pysyvät ennallaan.', 'Raderar hela din ekonomiprofil. Dina transaktioner påverkas inte.'],
  'empty.title': ['Your coach doesn’t know you yet', 'Valmentajasi ei vielä tunne sinua', 'Din coach känner dig inte än'],
  'empty.body': ['Answer a few quick questions so tips fit your life. It takes about a minute, and you can skip anything.', 'Vastaa muutamaan nopeaan kysymykseen, niin vinkit sopivat elämääsi. Se vie noin minuutin, ja voit ohittaa minkä tahansa.', 'Svara på några snabba frågor så att tipsen passar ditt liv. Det tar ungefär en minut och du kan hoppa över vad som helst.'],
  'empty.start': ['Start the intro', 'Aloitetaan', 'Kom igång'],

  'draft.editTitle': ['Edit: {label}', 'Muokkaa: {label}', 'Ändra: {label}'],
  'draft.addTitle': ['{label}', 'Lisää: {label}', 'Lägg till: {label}'],
  'draft.save': ['Save to my profile', 'Tallenna profiiliin', 'Spara i profilen'],
  'field.adults': ['Adults', 'Aikuisia', 'Vuxna'],
  'field.children': ['Children', 'Lapsia', 'Barn'],
  'field.pct': ['Share of income to save (%)', 'Säästettävä osuus tuloista (%)', 'Andel av inkomsten att spara (%)'],
  'field.months': ['Months of expenses', 'Montako kuukauden menot', 'Hur många månaders utgifter'],
  'field.investing': ['Investing every month?', 'Sijoitatko kuukausittain?', 'Investerar du varje månad?'],
  'field.monthly': ['Amount a month', 'Summa kuukaudessa', 'Belopp per månad'],
  'field.loanType': ['Loan {n}', 'Laina {n}', 'Lån {n}'],
  'field.loanMonthly': ['Loan {n}: monthly payment', 'Laina {n}: kuukausierä', 'Lån {n}: månadsbetalning'],
  'field.loanRemaining': ['Loan {n}: still to pay', 'Laina {n}: jäljellä', 'Lån {n}: kvar att betala'],
  'field.what': ['What is coming up ({n})', 'Mitä on tulossa ({n})', 'Vad är på gång ({n})'],
  'field.when': ['When ({n})', 'Milloin ({n})', 'När ({n})'],
  'field.cost': ['Rough cost ({n})', 'Arvioitu hinta ({n})', 'Ungefärlig kostnad ({n})'],
  'field.eventType': ['What happened', 'Mitä tapahtui', 'Vad hände'],
  'field.since': ['Since', 'Alkaen', 'Sedan'],
  'field.eventNote': ['A few words', 'Muutama sana (valinnainen)', 'Några ord (valfritt)'],
  'field.note': ['Note', 'Muistiinpano', 'Anteckning'],
  'field.protected': ['Categories, separated by commas', 'Luokat pilkulla erotettuina', 'Kategorier, åtskilda med kommatecken'],
  'field.taxYear': ['Tax year', 'Verovuosi', 'Skatteår'],
  'field.baseRate': ['Tax card base rate (%)', 'Verokortin perusprosentti (%)', 'Skattekortets grundprocent (%)'],
  'field.additionalRate': ['Additional rate (%)', 'Lisäprosentti (%)', 'Tilläggsprocent (%)'],
  'field.incomeLimit': ['Income limit for the year', 'Vuoden tuloraja', 'Årets inkomstgräns'],
  'field.grossMonthly': ['Gross salary a month', 'Bruttopalkka kuukaudessa', 'Bruttolön per månad'],
  'field.grossYtd': ['Gross salary so far this year', 'Bruttopalkka tänä vuonna tähän mennessä', 'Bruttolön hittills i år'],
  'field.assessmentEnd': ['Tax assessment ends in', 'Verotus päättyy', 'Beskattningen avslutas i'],
  'field.decision': ['Tax decision', 'Veropäätös', 'Beskattningsbeslut'],
  'field.decisionAmount': ['Amount on the decision', 'Summa veropäätöksessä', 'Belopp i beslutet'],
  'field.setAside': ['Already set aside', 'Jo varattu', 'Redan avsatt'],
  'field.year': ['Year', 'Vuosi', 'År'],
  'field.closing': ['Closing message', 'Loppuviesti', 'Avslutande meddelande'],
};

/** Frozen message maps {en, fi, sv} with identical keys. */
export const PROFILE_MESSAGES = Object.freeze(Object.fromEntries(['en', 'fi', 'sv'].map((locale, index) => [
  locale, Object.freeze(Object.fromEntries(Object.entries(COPY).map(([key, values]) => [key, values[index]]))),
])));

/** Normalise a locale string to 'en' | 'fi' | 'sv'. */
export function profileLocale(locale) {
  const code = String(locale || 'en').toLowerCase().slice(0, 2);
  return PROFILE_MESSAGES[code] ? code : 'en';
}

/**
 * Translate a message key.
 * @param {string} locale  'en' | 'fi' | 'sv' (others fall back to English)
 * @param {string} key     message key, e.g. 'page.title'
 * @param {object} values  {name: value} replacements for {name} placeholders
 * @returns {string} translated text (the key itself if unknown)
 */
export function pm(locale, key, values = {}) {
  const text = PROFILE_MESSAGES[profileLocale(locale)][key] || PROFILE_MESSAGES.en[key] || key;
  return text.replace(/\{(\w+)\}/g, (_, name) => values[name] === undefined ? '{' + name + '}' : String(values[name]));
}

/* ---------------------------------------------------------------- small helpers */
const INTL = {en: 'en-GB', fi: 'fi-FI', sv: 'sv-FI'};

/** Escape text for HTML element content and attribute values. */
export function escapeHtml(value) {
  return String(value === null || value === undefined ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
const esc = escapeHtml;
const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const clone = value => value === undefined ? undefined : JSON.parse(JSON.stringify(value));
const isCents = value => Number.isSafeInteger(value) && value >= 0;
const cleanText = (value, max = NOTE_MAX) => typeof value === 'string' ? value.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '').trim().slice(0, max) : '';
const isMonth = value => typeof value === 'string' && /^\d{4}-(0[1-9]|1[0-2])$/.test(value);
const isDate = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}/.test(value) && Number.isFinite(Date.parse(value.slice(0, 10)));

function number(value, locale, digits = 1) {
  return new Intl.NumberFormat(INTL[profileLocale(locale)], {maximumFractionDigits: digits}).format(value);
}
/** Default money formatter: integer cents -> e.g. "€1,200" / "1 200 €" (no decimals when whole euros). */
export function defaultMoney(cents, locale = 'en') {
  const euros = Number(cents || 0) / 100;
  return new Intl.NumberFormat(INTL[profileLocale(locale)], {
    style: 'currency', currency: 'EUR', minimumFractionDigits: Number.isInteger(euros) ? 0 : 2, maximumFractionDigits: 2,
  }).format(euros);
}
function defaultMonthLabel(month, locale) {
  if (!isMonth(month)) return String(month || '');
  const [y, m] = month.split('-').map(Number);
  return new Intl.DateTimeFormat(INTL[profileLocale(locale)], {month: 'long', year: 'numeric', timeZone: 'UTC'}).format(new Date(Date.UTC(y, m - 1, 1)));
}
function defaultDateLabel(iso, locale) {
  if (!isDate(iso)) return String(iso || '');
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Intl.DateTimeFormat(INTL[profileLocale(locale)], {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'}).format(new Date(Date.UTC(y, m - 1, d)));
}
function monthName(month, locale) {
  return new Intl.DateTimeFormat(INTL[profileLocale(locale)], {month: 'long', timeZone: 'UTC'}).format(new Date(Date.UTC(2026, month - 1, 1)));
}
function helpersFor(locale, helpers = {}) {
  return {
    money: typeof helpers.money === 'function' ? helpers.money : cents => defaultMoney(cents, locale),
    monthLabel: typeof helpers.monthLabel === 'function' ? helpers.monthLabel : month => defaultMonthLabel(month, locale),
    dateLabel: typeof helpers.dateLabel === 'function' ? helpers.dateLabel : iso => defaultDateLabel(iso, locale),
  };
}

/**
 * Parse a typed euro amount into integer cents. Accepts "1 200,50", "1,200.50", "1.200,50", "900", "900 €".
 * @param {string|number} input  typed text, or a number of euros
 * @returns {number|null} non-negative integer cents, or null when empty/invalid
 */
export function parseAmountToCents(input) {
  if (typeof input === 'number') return Number.isFinite(input) && input >= 0 ? Math.round(input * 100) : null;
  if (typeof input !== 'string') return null;
  let text = input.replace(/[\s  €]/g, '').replace(/eur$/i, '');
  if (!text || !/^[0-9.,]+$/.test(text)) return null;
  const lastComma = text.lastIndexOf(','), lastDot = text.lastIndexOf('.');
  if (lastComma >= 0 && lastDot >= 0) {
    const decimal = lastComma > lastDot ? ',' : '.';
    text = text.split(decimal === ',' ? '.' : ',').join('').replace(decimal, '.');
  } else if (lastComma >= 0 || lastDot >= 0) {
    const sep = lastComma >= 0 ? ',' : '.';
    const parts = text.split(sep);
    text = parts.length === 2 && parts[1].length > 0 && parts[1].length <= 2 ? parts[0] + '.' + parts[1] : parts.join('');
  }
  if (!/^\d+(\.\d{1,2})?$/.test(text)) return null;
  const [whole, frac = ''] = text.split('.');
  const cents = Number(whole) * 100 + Number((frac + '00').slice(0, 2));
  return Number.isSafeInteger(cents) ? cents : null;
}
const centsToInput = cents => isCents(cents) ? (cents % 100 === 0 ? String(cents / 100) : (cents / 100).toFixed(2)) : '';

/* ---------------------------------------------------------------- describeEntry */
/**
 * Human-readable value of a profile entry (or suggestion) in the customer's language.
 * @param {{key:string, value:any}} entry  profile entry or suggestion
 * @param {string} locale                   'en' | 'fi' | 'sv'
 * @param {{money?:(cents)=>string, monthLabel?:('YYYY-MM')=>string, dateLabel?:(iso)=>string}} helpers
 * @returns {string} plain text (not escaped)
 */
export function describeEntry(entry, locale = 'en', helpers = {}) {
  const h = helpersFor(locale, helpers);
  const t = (key, values) => pm(locale, key, values);
  const key = entry?.key;
  const value = entry?.value;
  switch (key) {
    case 'life_stage': return LIFE_STAGES.includes(value) ? t('life_stage.' + value) : String(value ?? '');
    case 'income_stability': return INCOME_STABILITY.includes(value) ? t('income_stability.' + value) : String(value ?? '');
    case 'risk_attitude': return RISK_ATTITUDES.includes(value) ? t('risk_attitude.' + value) : String(value ?? '');
    case 'coaching_style': return COACHING_STYLES.includes(value) ? t('coaching_style.' + value) : String(value ?? '');
    case 'household': {
      const adults = Number(value?.adults) || 1, children = Number(value?.children) || 0;
      if (adults === 1 && children === 0) return t('describe.household.alone');
      const a = adults === 1 ? t('describe.adults.one') : t('describe.adults.many', {n: adults});
      const c = children === 0 ? t('describe.children.none') : children === 1 ? t('describe.children.one') : t('describe.children.many', {n: children});
      return a + ', ' + c;
    }
    case 'saving_rate_target_pct': return t('describe.pct', {pct: number(Number(value) || 0, locale)});
    case 'emergency_fund_target_months': {
      const n = Number(value) || 0;
      return n === 1 ? t('describe.months.one') : t('describe.months.many', {n: number(n, locale)});
    }
    case 'regular_investing':
      if (!value?.active) return t('describe.investing.no');
      return isCents(value.monthly_cents) ? t('describe.investing.amount', {amount: h.money(value.monthly_cents)}) : t('describe.investing.yes');
    case 'debts': {
      const items = Array.isArray(value) ? value : [];
      if (!items.length) return t('describe.debts.none');
      return items.map(item => {
        const loan = DEBT_TYPES.includes(item?.type) ? t('debt.' + item.type) : t('debt.other');
        let text = t('describe.debt', {loan, amount: h.money(item?.monthly_payment_cents || 0)});
        if (isCents(item?.remaining_cents)) text += ' (' + t('describe.debt.remaining', {amount: h.money(item.remaining_cents)}) + ')';
        return text;
      }).join('; ');
    }
    case 'upcoming': {
      const items = Array.isArray(value) ? value : [];
      if (!items.length) return t('describe.upcoming.none');
      return items.map(item => {
        const parts = [cleanText(item?.what, 200)];
        if (item?.month) parts.push(h.monthLabel(item.month));
        if (isCents(item?.amount_cents)) parts.push(t('describe.upcoming.cost', {amount: h.money(item.amount_cents)}));
        return parts.filter(Boolean).join(', ');
      }).join('; ');
    }
    case 'life_event': {
      const event = LIFE_EVENT_TYPES.includes(value?.type) ? t('event.' + value.type) : t('event.other');
      let text = value?.since ? t('describe.event.since', {event, date: isMonth(value.since) ? h.monthLabel(value.since) : h.dateLabel(value.since)}) : event;
      const note = cleanText(value?.note, 200);
      if (note) text += ' — ' + note;
      return text;
    }
    case 'protected_categories': {
      const items = (Array.isArray(value) ? value : []).map(item => cleanText(item, 60)).filter(item => item && item !== 'none');
      return items.length ? items.join(', ') : t('describe.protected.none');
    }
    case 'note': return cleanText(typeof value === 'string' ? value : value?.text);
    case 'tax': {
      const v = isObject(value) ? value : {};
      const parts = [];
      if (Number.isFinite(v.base_rate_bp)) parts.push(t('describe.tax.rate', {rate: number(v.base_rate_bp / 100, locale, 2)}));
      if (Number.isFinite(v.additional_rate_bp)) parts.push(t('describe.tax.additional', {rate: number(v.additional_rate_bp / 100, locale, 2)}));
      if (isCents(v.gross_monthly_cents)) parts.push(t('describe.tax.gross', {amount: h.money(v.gross_monthly_cents)}));
      else if (isCents(v.gross_ytd_cents)) parts.push(t('describe.tax.ytd', {amount: h.money(v.gross_ytd_cents)}));
      if ((v.decision_result === 'refund' || v.decision_result === 'back_tax') && isCents(v.decision_amount_cents)) {
        parts.push(t('describe.tax.' + v.decision_result, {amount: h.money(v.decision_amount_cents)}));
      }
      const body = parts.length ? parts.join(', ') : t('describe.tax.empty');
      return Number.isInteger(v.tax_year) ? t('describe.tax.year', {year: v.tax_year}) + ': ' + body : body;
    }
    case 'plan_mortgage':
    case 'plan_tax': return describePlan(entry, locale, h.money);
    case 'year_review': {
      const year = Number(value?.year);
      return Number.isInteger(year) && year > 0 ? t('describe.review', {year}) : t('describe.review.generic');
    }
    default: return typeof value === 'string' ? value : JSON.stringify(value ?? '');
  }
}

/* ---------------------------------------------------------------- onboarding */
/**
 * The intro questions in order. Each: {key, type, ...}. Types:
 *  - 'choice': tap one of `options` (values are the profile value)
 *  - 'household': tap one of `options` ({id, adults, children:number|'ask'}); children count chips for 'ask'
 *  - 'slider': `min`..`max` percent in `step`, with a "Not sure yet" button (acts as Skip)
 *  - 'yes_amount': No -> {active:false}; Yes + optional monthly amount -> {active:true, monthly_cents?}
 *  - 'loans': multi-select loan types (or "No loans" -> []), each with a required monthly payment
 *  - 'text': free text `what`, required month, optional amount -> [{what, month, amount_cents?}]
 */
export const ONBOARDING_STEPS = Object.freeze([
  {key: 'life_stage', type: 'choice', options: LIFE_STAGES},
  {key: 'household', type: 'household', options: [
    {id: 'alone', adults: 1, children: 0}, {id: 'partner', adults: 2, children: 0},
    {id: 'kids', adults: 1, children: 'ask'}, {id: 'partner_kids', adults: 2, children: 'ask'},
  ], childrenOptions: [1, 2, 3, 4, 5]},
  {key: 'income_stability', type: 'choice', options: INCOME_STABILITY},
  {key: 'saving_rate_target_pct', type: 'slider', min: 0, max: 30, step: 1, initial: 10},
  {key: 'regular_investing', type: 'yes_amount'},
  {key: 'debts', type: 'loans', options: ONBOARDING_LOANS},
  {key: 'risk_attitude', type: 'choice', options: RISK_ATTITUDES},
  {key: 'upcoming', type: 'text', maxLength: 200},
].map(step => Object.freeze(step)));
const SUMMARY_STEP = ONBOARDING_STEPS.length;

/**
 * Fresh onboarding state.
 * @param {{suggestions?:Array, answers?:object}} options  suggestions from the profile_suggestions endpoint
 * @returns {{step:number, answers:object, skipped:string[], suggestions:Array, decisions:object, draft:object, error:string|null, done:boolean}}
 *   step 0..7 are questions, 8 is the summary; answers maps profile key -> value; decisions maps suggestion id -> 'keep'|'dismiss'.
 */
export function createOnboardingState({suggestions = [], answers = {}} = {}) {
  return {step: 0, answers: clone(answers) || {}, skipped: [], suggestions: Array.isArray(suggestions) ? clone(suggestions) : [], decisions: {}, draft: {}, error: null, done: false};
}

/**
 * Validate and normalise an answer for an onboarding step.
 * @returns {{value?:any, error?:string, errorValues?:object}} error is a message key
 */
export function validateOnboardingAnswer(step, value) {
  switch (step.type) {
    case 'choice': return step.options.includes(value) ? {value} : {error: 'error.needChoice'};
    case 'household': {
      const adults = Number(value?.adults), children = Number(value?.children);
      if (!Number.isInteger(adults) || adults < 1 || adults > 10 || !Number.isInteger(children) || children < 0 || children > 20) return {error: 'error.needChoice'};
      return {value: {adults, children}};
    }
    case 'slider': {
      const pct = Number(value);
      if (value === null || value === '' || !Number.isFinite(pct) || pct < step.min || pct > step.max) return {error: 'error.badRange', errorValues: {min: step.min, max: step.max}};
      return {value: pct};
    }
    case 'yes_amount': {
      if (!isObject(value) || typeof value.active !== 'boolean') return {error: 'error.needChoice'};
      if (!value.active) return {value: {active: false}};
      if (value.monthly_cents === undefined || value.monthly_cents === null) return {value: {active: true}};
      return isCents(value.monthly_cents) && value.monthly_cents > 0 ? {value: {active: true, monthly_cents: value.monthly_cents}} : {error: 'error.badAmount'};
    }
    case 'loans': {
      if (!Array.isArray(value)) return {error: 'error.needLoan'};
      const out = [];
      for (const item of value) {
        if (!DEBT_TYPES.includes(item?.type)) return {error: 'error.needLoan'};
        if (!isCents(item.monthly_payment_cents) || item.monthly_payment_cents <= 0) return {error: 'error.needAmount'};
        const row = {type: item.type, monthly_payment_cents: item.monthly_payment_cents};
        if (isCents(item.remaining_cents)) row.remaining_cents = item.remaining_cents;
        out.push(row);
      }
      return {value: out};
    }
    case 'text': {
      const item = Array.isArray(value) ? value[0] : value;
      const what = cleanText(item?.what, step.maxLength || 200);
      if (!what) return {error: 'error.needText'};
      if (!isMonth(item?.month)) return {error: 'error.needMonth'};
      const row = {what, month: item.month};
      if (item.amount_cents !== undefined && item.amount_cents !== null) {
        if (!isCents(item.amount_cents)) return {error: 'error.badAmount'};
        row.amount_cents = item.amount_cents;
      }
      return {value: [row]};
    }
    default: return {error: 'error.needChoice'};
  }
}

/**
 * Pure onboarding state machine.
 * @param {object} state   from createOnboardingState
 * @param {object} action  one of
 *   {type:'answer', value}           validate + store the answer for the current step, then advance
 *   {type:'skip'}                    forget the current step's answer, mark skipped, advance
 *   {type:'back'}                    previous step (no-op at step 0)
 *   {type:'goto', step}              jump to a step (0..8), e.g. "Change" on the summary
 *   {type:'draft', patch}            merge UI-only values (selected loans, children count, typed amounts)
 *   {type:'toggleSuggestion', id, decision:'keep'|'dismiss'}  set; same decision again clears it
 *   {type:'setSuggestions', suggestions}  replace suggestions (e.g. after async load); drops stale decisions
 *   {type:'finish'}                  mark done (go to summary)
 * @returns {object} a new state; the input is never mutated. Invalid answers set `error` (message key) and stay.
 */
export function reduceOnboarding(state, action) {
  const next = clone(state || createOnboardingState());
  next.error = null;
  next.errorValues = undefined;
  const current = ONBOARDING_STEPS[next.step];
  switch (action?.type) {
    case 'answer': {
      if (!current) return next;
      const result = validateOnboardingAnswer(current, action.value);
      if (result.error) { next.error = result.error; next.errorValues = result.errorValues; return next; }
      next.answers[current.key] = result.value;
      next.skipped = next.skipped.filter(key => key !== current.key);
      next.draft = {};
      next.step += 1;
      return next;
    }
    case 'skip':
      if (!current) return next;
      delete next.answers[current.key];
      if (!next.skipped.includes(current.key)) next.skipped.push(current.key);
      next.draft = {};
      next.step += 1;
      return next;
    case 'back':
      if (next.step > 0) { next.step -= 1; next.draft = {}; next.done = false; }
      return next;
    case 'goto': {
      const step = Number(action.step);
      if (Number.isInteger(step) && step >= 0 && step <= SUMMARY_STEP) { next.step = step; next.draft = {}; next.done = false; }
      return next;
    }
    case 'draft':
      next.draft = {...next.draft, ...(isObject(action.patch) ? clone(action.patch) : {})};
      return next;
    case 'toggleSuggestion': {
      if (!next.suggestions.some(item => item?.id === action.id) || !['keep', 'dismiss'].includes(action.decision)) return next;
      if (next.decisions[action.id] === action.decision) delete next.decisions[action.id];
      else next.decisions[action.id] = action.decision;
      return next;
    }
    case 'setSuggestions': {
      next.suggestions = Array.isArray(action.suggestions) ? clone(action.suggestions) : [];
      const ids = new Set(next.suggestions.map(item => item?.id));
      next.decisions = Object.fromEntries(Object.entries(next.decisions).filter(([id]) => ids.has(id)));
      return next;
    }
    case 'finish':
      next.step = SUMMARY_STEP;
      next.done = true;
      return next;
    default:
      return next;
  }
}

/**
 * What to save when the customer taps "Save to my money profile".
 * @returns {{entries:Array<{key,value,source:'you_told_me'}>, acceptedSuggestions:string[], dismissedSuggestions:string[]}}
 *   entries in question order (skipped questions omitted; "No loans" is saved as debts: []).
 */
export function onboardingResult(state) {
  const answers = state?.answers || {};
  const entries = ONBOARDING_STEPS.filter(step => Object.prototype.hasOwnProperty.call(answers, step.key))
    .map(step => ({key: step.key, value: clone(answers[step.key]), source: 'you_told_me'}));
  const decisions = state?.decisions || {};
  const ids = (state?.suggestions || []).map(item => item?.id).filter(id => typeof id === 'string');
  return {
    entries,
    acceptedSuggestions: ids.filter(id => decisions[id] === 'keep'),
    dismissedSuggestions: ids.filter(id => decisions[id] === 'dismiss'),
  };
}

function dots(state, locale) {
  const total = ONBOARDING_STEPS.length + 1;
  const label = state.step >= SUMMARY_STEP ? pm(locale, 'onboarding.progressSummary') : pm(locale, 'onboarding.progress', {n: state.step + 1, total: ONBOARDING_STEPS.length});
  const items = Array.from({length: total}, (_, index) => {
    const cls = index < state.step ? 'is-done' : index === state.step ? 'is-current' : '';
    return '<li class="onboarding-dot ' + cls + '"' + (index === state.step ? ' aria-current="step"' : '') + '></li>';
  }).join('');
  return '<div class="onboarding-progress"><ol class="onboarding-dots" aria-hidden="true">' + items + '</ol><p class="onboarding-progress-label">' + esc(label) + '</p></div>';
}
function bubble(text, extra = '') {
  return '<div class="onboarding-bubble coach-turn-answer">' + extra + '<p>' + esc(text) + '</p></div>';
}
function errorLine(state, locale) {
  return state.error ? '<p class="onboarding-error" role="alert" data-onboarding-error>' + esc(pm(locale, state.error, state.errorValues || {})) + '</p>' : '';
}
function optionButton(attr, id, label, pressed) {
  return '<button type="button" class="onboarding-option" ' + attr + '="' + esc(id) + '" aria-pressed="' + (pressed ? 'true' : 'false') + '">' + esc(label) + '</button>';
}
function stepControls(step, state, locale, h) {
  const t = (key, values) => pm(locale, key, values);
  const answer = state.answers[step.key];
  const draft = state.draft || {};
  const next = '<button type="button" class="primary-button onboarding-next" data-onboarding-next>' + esc(t('onboarding.next')) + '</button>';
  const amountInput = (attr, id, label, value) => '<label class="onboarding-field"><span>' + esc(label) + '</span><input type="text" inputmode="decimal" autocomplete="off" ' + attr + '="' + esc(id) + '" value="' + esc(value) + '" placeholder="0 €"></label>';
  switch (step.type) {
    case 'choice': {
      const prefix = step.key === 'life_stage' ? 'life_stage.' : step.key + '.';
      return '<div class="onboarding-options" role="group">' + step.options.map(option => optionButton('data-onboarding-choice', option, t(prefix + option), answer === option)).join('') + '</div>';
    }
    case 'household': {
      const currentId = draft.household || (answer ? (answer.adults === 1 ? (answer.children ? 'kids' : 'alone') : (answer.children ? 'partner_kids' : 'partner')) : null);
      const children = Number(draft.children) || (answer?.children > 0 ? answer.children : 1);
      let html = '<div class="onboarding-options" role="group">' + step.options.map(option => optionButton('data-onboarding-household', option.id, t('onboarding.household.' + option.id), currentId === option.id)).join('') + '</div>';
      const option = step.options.find(item => item.id === currentId);
      if (option && option.children === 'ask' && draft.household) {
        html += '<p class="onboarding-subquestion">' + esc(t('onboarding.children')) + '</p><div class="onboarding-options onboarding-options-row" role="group">'
          + step.childrenOptions.map(n => optionButton('data-onboarding-children', n, n === step.childrenOptions[step.childrenOptions.length - 1] ? n + '+' : String(n), children === n)).join('') + '</div>' + next;
      }
      return html;
    }
    case 'slider': {
      const value = Number.isFinite(Number(draft.pct)) && draft.pct !== undefined ? Number(draft.pct) : Number.isFinite(answer) ? answer : step.initial;
      return '<div class="onboarding-slider"><output class="onboarding-slider-value" data-onboarding-output aria-live="polite">' + esc(t('onboarding.slider', {pct: value})) + '</output>'
        + '<input type="range" min="' + step.min + '" max="' + step.max + '" step="' + step.step + '" value="' + value + '" data-onboarding-field="pct" aria-label="' + esc(t('onboarding.q.saving_rate_target_pct')) + '">'
        + '<div class="onboarding-slider-scale" aria-hidden="true"><span>' + step.min + ' %</span><span>' + step.max + ' %</span></div></div>'
        + '<div class="onboarding-options">' + next + '<button type="button" class="secondary-button" data-onboarding-notsure>' + esc(t('onboarding.notSure')) + '</button></div>';
    }
    case 'yes_amount': {
      const yes = draft.investing === true || (draft.investing === undefined && answer?.active === true);
      const no = draft.investing === false || (draft.investing === undefined && answer?.active === false);
      let html = '<div class="onboarding-options onboarding-options-row" role="group">' + optionButton('data-onboarding-yesno', 'no', t('onboarding.investing.no'), no) + optionButton('data-onboarding-yesno', 'yes', t('onboarding.investing.yes'), yes) + '</div>';
      if (yes) {
        const value = draft.amount !== undefined ? draft.amount : centsToInput(answer?.monthly_cents);
        html += amountInput('data-onboarding-field', 'amount', t('onboarding.investing.amount'), value) + next;
      }
      return html;
    }
    case 'loans': {
      const selected = Array.isArray(draft.loans) ? draft.loans : Array.isArray(answer) ? answer.map(item => item.type).filter(type => step.options.includes(type)) : [];
      const amounts = isObject(draft.amounts) ? draft.amounts : Object.fromEntries((Array.isArray(answer) ? answer : []).map(item => [item.type, centsToInput(item.monthly_payment_cents)]));
      let html = '<p class="onboarding-subquestion">' + esc(t('onboarding.loans.help')) + '</p><div class="onboarding-options" role="group">'
        + optionButton('data-onboarding-loans-none', 'none', t('onboarding.loans.none'), Array.isArray(answer) && answer.length === 0 && !draft.loans)
        + step.options.map(type => optionButton('data-onboarding-loan', type, t('debt.' + type), selected.includes(type))).join('') + '</div>';
      if (selected.length) {
        html += selected.map(type => amountInput('data-onboarding-amount', type, t('onboarding.loans.payment', {loan: t('debt.' + type)}), amounts[type] || '')).join('') + next;
      }
      return html;
    }
    case 'text': {
      const item = Array.isArray(answer) ? answer[0] : null;
      const what = draft.what !== undefined ? draft.what : item?.what || '';
      const month = draft.month !== undefined ? draft.month : item?.month || '';
      const amount = draft.amount !== undefined ? draft.amount : centsToInput(item?.amount_cents);
      return '<label class="onboarding-field"><span>' + esc(t('onboarding.upcoming.what')) + '</span><input type="text" maxlength="' + (step.maxLength || 200) + '" data-onboarding-field="what" value="' + esc(what) + '" placeholder="' + esc(t('onboarding.upcoming.placeholder')) + '"></label>'
        + '<label class="onboarding-field"><span>' + esc(t('onboarding.upcoming.when')) + '</span><input type="month" data-onboarding-field="month" value="' + esc(month) + '"></label>'
        + amountInput('data-onboarding-field', 'amount', t('onboarding.upcoming.cost'), amount) + next;
    }
    default: return '';
  }
}
function suggestionCard(item, locale, h, decision) {
  const t = (key, values) => pm(locale, key, values);
  const value = describeEntry(item, locale, h);
  const question = cleanText(item?.question, 300) || t('noticed.fallback', {value});
  const evidence = cleanText(item?.evidence?.label, 300);
  const id = esc(item?.id);
  return '<article class="profile-suggestion" data-suggestion="' + id + '">'
    + '<p class="profile-suggestion-question">' + esc(question) + '</p>'
    + (cleanText(item?.question, 300) && item?.key !== 'observation' ? '<p class="profile-suggestion-value">' + esc(pm(locale, 'key.' + item.key)) + ': ' + esc(value) + '</p>' : '')
    + (evidence ? '<p class="profile-suggestion-evidence">' + esc(t('noticed.evidence', {label: evidence})) + '</p>' : '')
    + '<div class="profile-actions">'
    + '<button type="button" class="profile-button profile-button-keep" data-suggestion-keep="' + id + '" aria-pressed="' + (decision === 'keep' ? 'true' : 'false') + '">' + esc(t('noticed.keep')) + '</button>'
    + '<button type="button" class="profile-button" data-suggestion-dismiss="' + id + '" aria-pressed="' + (decision === 'dismiss' ? 'true' : 'false') + '">' + esc(t('noticed.dismiss')) + '</button>'
    + '</div></article>';
}

/**
 * Render the current onboarding step for the Coach chat area.
 * @param {object} state   onboarding state (createOnboardingState / reduceOnboarding)
 * @param {string} locale  'en' | 'fi' | 'sv'
 * @param {{money?, monthLabel?, dateLabel?}} helpers  optional formatters (summary step)
 * @returns {string} HTML for one <section class="onboarding" data-onboarding-step="n">
 *   Data attributes: data-onboarding-choice|household|children|yesno|loan|loans-none="<value>", data-onboarding-field,
 *   data-onboarding-amount="<loan>", data-onboarding-next, -skip, -back, -notsure, -skipall, -goto="<step>", -finish,
 *   data-suggestion-keep|dismiss="<id>".
 */
export function renderOnboarding(state, locale = 'en', helpers = {}) {
  const s = state || createOnboardingState();
  const h = helpersFor(locale, helpers);
  const t = (key, values) => pm(locale, key, values);
  if (s.step >= SUMMARY_STEP) {
    const rows = ONBOARDING_STEPS.map((step, index) => {
      const has = Object.prototype.hasOwnProperty.call(s.answers, step.key);
      const text = has ? describeEntry({key: step.key, value: s.answers[step.key]}, locale, h) : t('onboarding.summary.skipped');
      const label = t('key.' + step.key);
      return '<li class="onboarding-summary-row' + (has ? '' : ' is-skipped') + '"><div><span class="onboarding-summary-label">' + esc(label) + '</span><span class="onboarding-summary-value">' + esc(text) + '</span></div>'
        + '<button type="button" class="text-button" data-onboarding-goto="' + index + '" aria-label="' + esc(t('onboarding.summary.changeLabel', {label})) + '">' + esc(t('onboarding.summary.change')) + '</button></li>';
    }).join('');
    const suggestions = (s.suggestions || []).filter(item => item && typeof item.id === 'string');
    return '<section class="onboarding onboarding-summary" data-onboarding-step="' + SUMMARY_STEP + '">' + dots(s, locale)
      + bubble(t('onboarding.summary.title')) + '<ul class="onboarding-summary-list">' + rows + '</ul>'
      + '<h3 class="onboarding-noticed-title">' + esc(t('onboarding.noticed')) + '</h3>'
      + (suggestions.length ? '<div class="profile-suggestions">' + suggestions.map(item => suggestionCard(item, locale, h, s.decisions?.[item.id])).join('') + '</div>' : '<p class="subtle">' + esc(t('onboarding.noticed.none')) + '</p>')
      + '<p class="subtle onboarding-summary-help">' + esc(t('onboarding.summary.help')) + '</p>'
      + '<div class="onboarding-nav onboarding-nav-final"><button type="button" class="primary-button" data-onboarding-finish>' + esc(t('onboarding.save')) + '</button>'
      + '<button type="button" class="secondary-button" data-onboarding-skipall>' + esc(t('onboarding.skipForNow')) + '</button>'
      + '<button type="button" class="text-button" data-onboarding-back>' + esc(t('onboarding.back')) + '</button></div></section>';
  }
  const step = ONBOARDING_STEPS[s.step];
  const intro = s.step === 0 ? '<p class="onboarding-intro">' + esc(t('onboarding.intro')) + '</p>' : '';
  return '<section class="onboarding" data-onboarding-step="' + s.step + '" data-onboarding-key="' + esc(step.key) + '">' + dots(s, locale)
    + bubble(t('onboarding.q.' + step.key), intro)
    + '<div class="onboarding-answer">' + stepControls(step, s, locale, h) + errorLine(s, locale) + '</div>'
    + '<div class="onboarding-nav">'
    + '<button type="button" class="text-button" data-onboarding-back' + (s.step === 0 ? ' disabled' : '') + '>' + esc(t('onboarding.back')) + '</button>'
    + '<button type="button" class="text-button" data-onboarding-skip>' + esc(t('onboarding.skip')) + '</button>'
    + '</div><button type="button" class="text-button onboarding-skipall" data-onboarding-skipall>' + esc(t('onboarding.skipAll')) + '</button></section>';
}

/** Read the in-progress inputs of the current step into a draft patch (keeps typed text across re-renders). */
function readDraft(root, step) {
  const field = name => root.querySelector('[data-onboarding-field="' + name + '"]');
  if (!step) return {};
  if (step.type === 'loans') {
    const amounts = {};
    root.querySelectorAll('[data-onboarding-amount]').forEach(input => { amounts[input.getAttribute('data-onboarding-amount')] = input.value; });
    return {amounts};
  }
  if (step.type === 'text') return {what: field('what')?.value ?? '', month: field('month')?.value ?? '', amount: field('amount')?.value ?? ''};
  if (step.type === 'yes_amount' && field('amount')) return {amount: field('amount').value};
  if (step.type === 'slider' && field('pct')) return {pct: Number(field('pct').value)};
  return {};
}
const BAD = Symbol('bad');
const optionalCents = text => (text === undefined || String(text).trim() === '') ? undefined : (parseAmountToCents(String(text)) ?? BAD);

/** Collect the answer value for the "Next" button of the current step from the DOM + draft. Returns {value} or {error}. */
function collectAnswer(root, state, step) {
  const draft = {...(state.draft || {}), ...readDraft(root, step)};
  switch (step.type) {
    case 'household': {
      const option = step.options.find(item => item.id === draft.household);
      if (!option) return {error: 'error.needChoice'};
      return {value: {adults: option.adults, children: option.children === 'ask' ? (Number(draft.children) || 1) : option.children}};
    }
    case 'slider': return {value: draft.pct};
    case 'yes_amount': {
      const cents = optionalCents(draft.amount);
      if (cents === BAD) return {error: 'error.badAmount'};
      return {value: cents === undefined ? {active: true} : {active: true, monthly_cents: cents}};
    }
    case 'loans': {
      const selected = Array.isArray(draft.loans) ? draft.loans : [];
      if (!selected.length) return {error: 'error.needLoan'};
      const rows = [];
      for (const type of selected) {
        const cents = optionalCents(draft.amounts?.[type]);
        if (cents === undefined) return {error: 'error.needAmount'};
        if (cents === BAD) return {error: 'error.badAmount'};
        rows.push({type, monthly_payment_cents: cents});
      }
      return {value: rows};
    }
    case 'text': {
      const cents = optionalCents(draft.amount);
      if (cents === BAD) return {error: 'error.badAmount'};
      const row = {what: draft.what, month: draft.month};
      if (cents !== undefined) row.amount_cents = cents;
      return {value: [row]};
    }
    default: return {error: 'error.needChoice'};
  }
}

/**
 * Wire an onboarding root element (event delegation; call once per root).
 * @param {Element} root  container whose innerHTML you set to renderOnboarding(...)
 * @param {{state:object, onState:(newState)=>void, onFinish:(result)=>void, onSkipAll:()=>void, locale?:string, helpers?:object, render?:boolean}} options
 *   onState receives each new state; by default (render !== false) the root is also re-rendered with it.
 *   onFinish receives onboardingResult(state) after "Save to my money profile"; onSkipAll is called for
 *   "Skip the intro" / "Skip for now" (save nothing).
 * @returns {{getState:()=>object, setState:(state)=>void, dispatch:(action)=>object, detach:()=>void}}
 */
export function attachOnboarding(root, {state, onState = () => {}, onFinish = () => {}, onSkipAll = () => {}, locale = 'en', helpers = {}, render = true} = {}) {
  let current = state || createOnboardingState();
  const update = newState => {
    current = newState;
    if (render) root.innerHTML = renderOnboarding(current, locale, helpers);
    onState(current);
    return current;
  };
  const dispatch = action => update(reduceOnboarding(current, action));
  const handler = event => {
    const target = event.target?.closest?.('button');
    if (!target || !root.contains(target) || target.disabled) return;
    const step = ONBOARDING_STEPS[current.step];
    const attr = name => target.getAttribute(name);
    const keepDraft = patch => dispatch({type: 'draft', patch: {...readDraft(root, step), ...patch}});
    if (target.hasAttribute('data-onboarding-choice')) return dispatch({type: 'answer', value: attr('data-onboarding-choice')});
    if (target.hasAttribute('data-onboarding-household')) {
      const option = step.options.find(item => item.id === attr('data-onboarding-household'));
      if (option && option.children !== 'ask') return dispatch({type: 'answer', value: {adults: option.adults, children: option.children}});
      return keepDraft({household: option?.id});
    }
    if (target.hasAttribute('data-onboarding-children')) return keepDraft({children: Number(attr('data-onboarding-children'))});
    if (target.hasAttribute('data-onboarding-yesno')) {
      if (attr('data-onboarding-yesno') === 'no') return dispatch({type: 'answer', value: {active: false}});
      return keepDraft({investing: true});
    }
    if (target.hasAttribute('data-onboarding-loans-none')) return dispatch({type: 'answer', value: []});
    if (target.hasAttribute('data-onboarding-loan')) {
      const type = attr('data-onboarding-loan');
      const base = Array.isArray(current.draft?.loans) ? current.draft.loans : (Array.isArray(current.answers[step.key]) ? current.answers[step.key].map(item => item.type) : []);
      const loans = base.includes(type) ? base.filter(item => item !== type) : [...base, type];
      return keepDraft({loans: ONBOARDING_LOANS.filter(item => loans.includes(item))});
    }
    if (target.hasAttribute('data-onboarding-next')) {
      const result = collectAnswer(root, current, step);
      if (result.error) return update({...reduceOnboarding(current, {type: 'draft', patch: readDraft(root, step)}), error: result.error});
      return dispatch({type: 'answer', value: result.value});
    }
    if (target.hasAttribute('data-onboarding-notsure') || target.hasAttribute('data-onboarding-skip')) return dispatch({type: 'skip'});
    if (target.hasAttribute('data-onboarding-back')) return dispatch({type: 'back'});
    if (target.hasAttribute('data-onboarding-goto')) return dispatch({type: 'goto', step: Number(attr('data-onboarding-goto'))});
    if (target.hasAttribute('data-suggestion-keep')) return dispatch({type: 'toggleSuggestion', id: attr('data-suggestion-keep'), decision: 'keep'});
    if (target.hasAttribute('data-suggestion-dismiss')) return dispatch({type: 'toggleSuggestion', id: attr('data-suggestion-dismiss'), decision: 'dismiss'});
    if (target.hasAttribute('data-onboarding-skipall')) return onSkipAll();
    if (target.hasAttribute('data-onboarding-finish')) {
      const finished = dispatch({type: 'finish'});
      return onFinish(onboardingResult(finished));
    }
  };
  const input = event => {
    const target = event.target;
    if (target?.getAttribute?.('data-onboarding-field') !== 'pct') return;
    const output = root.querySelector('[data-onboarding-output]');
    if (output) output.textContent = pm(locale, 'onboarding.slider', {pct: target.value});
  };
  root.addEventListener('click', handler);
  root.addEventListener('input', input);
  if (render) root.innerHTML = renderOnboarding(current, locale, helpers);
  return {
    getState: () => current,
    setState: newState => update(newState),
    dispatch,
    detach: () => { root.removeEventListener('click', handler); root.removeEventListener('input', input); },
  };
}

/* ---------------------------------------------------------------- profile page */
const isActive = entry => entry && entry.active !== false && entry.active !== 0;

/** The active life event that keeps steady mode on (most recent first), or null. */
export function steadyReasonEntry(profile) {
  const entries = (profile?.entries || []).filter(entry => isActive(entry) && entry.key === 'life_event' && STEADY_EVENT_TYPES.includes(entry.value?.type));
  entries.sort((a, b) => String(b.updated_at || b.created_at || '').localeCompare(String(a.updated_at || a.created_at || '')));
  return entries[0] || null;
}

/**
 * Group active entries into PROFILE_SECTIONS order.
 * @returns {Array<{id:string, entries:Array}>} every section (possibly with empty entries), keys in section order, newest first within a key
 */
export function groupProfileEntries(entries) {
  const active = (Array.isArray(entries) ? entries : []).filter(isActive);
  return PROFILE_SECTIONS.map(section => ({
    id: section.id,
    entries: section.keys.flatMap(key => active.filter(entry => entry.key === key)
      .sort((a, b) => String(b.updated_at || b.created_at || '').localeCompare(String(a.updated_at || a.created_at || '')))),
  }));
}

function entryCard(entry, locale, h) {
  const t = (key, values) => pm(locale, key, values);
  const label = t('key.' + entry.key);
  const id = esc(entry.id);
  const source = PROFILE_SOURCES.includes(entry.source) ? entry.source : 'you_told_me';
  const date = entry.updated_at || entry.created_at;
  const note = entry.key !== 'note' ? cleanText(entry.note, 300) : '';
  const valueText = describeEntry(entry, locale, h);
  const valueHtml = entry.key === 'note' ? '<blockquote class="profile-entry-value profile-note">' + esc(valueText) + '</blockquote>' : '<p class="profile-entry-value">' + esc(valueText) + '</p>';
  const extra = entry.key === 'year_review'
    ? '<button type="button" class="profile-button profile-button-primary" data-profile-open-review="' + id + '">' + esc(t('reviews.open')) + '</button>'
    : '<button type="button" class="profile-button" data-profile-edit="' + id + '" aria-label="' + esc(t('entry.editLabel', {label})) + '">' + esc(t('entry.edit')) + '</button>';
  return '<article class="profile-entry" data-profile-entry="' + id + '" data-profile-key="' + esc(entry.key) + '">'
    + '<h4 class="profile-entry-label">' + esc(label) + '</h4>' + valueHtml
    + (note ? '<p class="profile-entry-note">' + esc(note) + '</p>' : '')
    + '<p class="profile-entry-meta"><span class="profile-source profile-source-' + esc(source) + '">' + esc(t('source.' + source)) + '</span>'
    + (date ? '<span class="profile-entry-date">' + esc(h.dateLabel(date)) + '</span>' : '') + '</p>'
    + '<div class="profile-actions">' + extra
    + '<button type="button" class="profile-button profile-button-quiet" data-profile-delete="' + id + '" aria-label="' + esc(t('entry.deleteLabel', {label})) + '">' + esc(t('entry.delete')) + '</button>'
    + '</div></article>';
}

/**
 * Render the Profile page.
 * @param {{entries:Array, by_key?:object, mode?:'normal'|'steady'}} profile  GET profile response
 * @param {Array<{id,key,value,question,evidence:{label},source}>} suggestions  pending suggestions
 * @param {string} locale  'en' | 'fi' | 'sv'
 * @param {{money?:(cents)=>string, dateLabel?:(iso)=>string, monthLabel?:('YYYY-MM')=>string}} helpers
 * @returns {string} HTML. Data attributes: data-profile-mode-off="<life event id or ''>", data-profile-edit="<id>",
 *   data-profile-delete="<id>", data-profile-open-tax, data-profile-open-review="<id>", data-suggestion-keep="<id>",
 *   data-suggestion-dismiss="<id>", data-profile-add, data-profile-onboarding, data-profile-forget.
 */
export function renderProfilePage(profile, suggestions = [], locale = 'en', helpers = {}) {
  const h = helpersFor(locale, helpers);
  const t = (key, values) => pm(locale, key, values);
  const entries = (profile?.entries || []).filter(isActive);
  const pending = (Array.isArray(suggestions) ? suggestions : []).filter(item => item && typeof item.id === 'string');
  let html = '<div class="profile-page"><header class="profile-header"><h1>' + esc(t('page.title')) + '</h1><p class="subtle">' + esc(t('page.subtitle')) + '</p></header>';
  if (profile?.mode === 'steady') {
    const reason = steadyReasonEntry(profile);
    const text = reason ? t('steady.reason.' + reason.value.type) : t('steady.reason.generic');
    html += '<section class="profile-banner" role="status" data-profile-banner="steady"><h2>' + esc(t('steady.title')) + '</h2><p>' + esc(text) + '</p><p class="small-text">' + esc(t('steady.help')) + '</p>'
      + '<button type="button" class="profile-button" data-profile-mode-off="' + esc(reason?.id || '') + '">' + esc(t('steady.off')) + '</button></section>';
  }
  if (!entries.length) {
    html += '<section class="profile-section profile-empty" data-profile-empty><h2>' + esc(t('empty.title')) + '</h2><p>' + esc(t('empty.body')) + '</p>'
      + '<button type="button" class="primary-button" data-profile-onboarding>' + esc(t('empty.start')) + '</button></section>'
      + '<section class="profile-section" data-profile-section="taxes"><h2>' + esc(t('section.taxes')) + '</h2><p class="subtle">' + esc(t('taxes.help')) + '</p>'
      + '<button type="button" class="secondary-button" data-profile-open-tax>' + esc(t('taxes.open')) + '</button></section>';
  } else {
    for (const section of groupProfileEntries(entries)) {
      if (section.id === 'taxes') {
        html += '<section class="profile-section" data-profile-section="taxes"><h2>' + esc(t('section.taxes')) + '</h2>'
          + (section.entries.length ? section.entries.map(entry => entryCard(entry, locale, h)).join('') : '<p class="subtle">' + esc(t('taxes.help')) + '</p>')
          + '<button type="button" class="secondary-button" data-profile-open-tax>' + esc(t('taxes.open')) + '</button></section>';
        continue;
      }
      if (!section.entries.length) continue;
      html += '<section class="profile-section" data-profile-section="' + section.id + '"><h2>' + esc(t('section.' + section.id)) + '</h2>'
        + section.entries.map(entry => entryCard(entry, locale, h)).join('') + '</section>';
    }
  }
  if (pending.length) {
    html += '<section class="profile-section profile-noticed" data-profile-section="noticed"><h2>' + esc(t('noticed.title')) + '</h2><p class="subtle">' + esc(t('noticed.help')) + '</p>'
      + '<div class="profile-suggestions">' + pending.map(item => suggestionCard(item, locale, h, null)).join('') + '</div></section>';
  }
  html += '<section class="profile-footer-actions"><button type="button" class="primary-button" data-profile-add>' + esc(t('actions.add')) + '</button>';
  if (entries.length) html += '<button type="button" class="secondary-button" data-profile-onboarding>' + esc(t('actions.onboarding')) + '</button>';
  html += '<div class="profile-forget"><button type="button" class="profile-button profile-button-danger" data-profile-forget>' + esc(t('actions.forget')) + '</button><p class="small-text">' + esc(t('actions.forgetHelp')) + '</p></div></section></div>';
  return html;
}

/**
 * The "Add something" chooser: one button per addable key (data-profile-add-key="<key>"); pass the key to draftSpecForEntry.
 * @returns {string} HTML
 */
export function renderAddMenu(locale = 'en') {
  return '<div class="profile-add-menu"><h3>' + esc(pm(locale, 'actions.addTitle')) + '</h3><div class="profile-add-options">'
    + ADDABLE_KEYS.map(key => '<button type="button" class="onboarding-option" data-profile-add-key="' + key + '">' + esc(pm(locale, 'key.' + key)) + '</button>').join('') + '</div></div>';
}

/**
 * Wire the Profile page (event delegation). Calls onAction with one of:
 *   {type:'mode_off', id}, {type:'edit', id}, {type:'delete', id}, {type:'open_tax'}, {type:'open_review', id},
 *   {type:'suggestion_keep', id}, {type:'suggestion_dismiss', id}, {type:'add'}, {type:'add_key', key},
 *   {type:'onboarding'}, {type:'forget'}.
 * @returns {() => void} detach function
 */
export function attachProfilePage(root, {onAction = () => {}} = {}) {
  const map = [
    ['data-profile-mode-off', 'mode_off', 'id'], ['data-profile-edit', 'edit', 'id'], ['data-profile-delete', 'delete', 'id'],
    ['data-profile-open-tax', 'open_tax'], ['data-profile-open-review', 'open_review', 'id'],
    ['data-suggestion-keep', 'suggestion_keep', 'id'], ['data-suggestion-dismiss', 'suggestion_dismiss', 'id'],
    ['data-profile-add-key', 'add_key', 'key'], ['data-profile-add', 'add'], ['data-profile-onboarding', 'onboarding'], ['data-profile-forget', 'forget'],
  ];
  const handler = event => {
    const target = event.target?.closest?.('button');
    if (!target || !root.contains(target) || target.disabled) return;
    for (const [attr, type, field] of map) {
      if (target.hasAttribute(attr)) {
        const action = {type};
        if (field) action[field] = target.getAttribute(attr);
        onAction(action);
        return;
      }
    }
  };
  root.addEventListener('click', handler);
  return () => root.removeEventListener('click', handler);
}

/* ---------------------------------------------------------------- draft card specs */
const selectOptions = (values, locale, prefix) => values.map(value => ({value, label: pm(locale, prefix + value)}));
const yesNo = locale => [{value: 'yes', label: pm(locale, 'common.yes')}, {value: 'no', label: pm(locale, 'common.no')}];

/**
 * Spec for the shared draft card (draft-card.js) to add or edit a profile entry.
 * @param {object|string} entryOrKey  an existing entry {id,key,value,...} (edit) or a key string (add)
 * @param {string} locale
 * @returns {{id:string, kind:'profile', key:string, entryId:string|null, title:string, saveLabel:string,
 *   fields:Array<{name,label,type:'text'|'amount'|'date'|'month'|'percent'|'select'|'number',value,options?,required?,min?,max?,maxLength?}>}}
 *   Amount field values are integer cents (or '' when empty); percent/number values are numbers (or '').
 *   List keys (debts, upcoming) use indexed fields (type_0, monthly_0, ...) plus one blank row to add another.
 */
export function draftSpecForEntry(entryOrKey, locale = 'en') {
  const entry = typeof entryOrKey === 'string' ? null : entryOrKey;
  const key = entry ? entry.key : entryOrKey;
  if (!PROFILE_KEYS.includes(key)) throw new Error('Unknown profile key: ' + key);
  const t = (k, values) => pm(locale, k, values);
  const value = entry ? entry.value : undefined;
  const label = t('key.' + key);
  const cents = v => isCents(v) ? v : '';
  let fields;
  switch (key) {
    case 'life_stage': fields = [{name: 'value', label, type: 'select', value: value ?? '', options: selectOptions(LIFE_STAGES, locale, 'life_stage.'), required: true}]; break;
    case 'income_stability': fields = [{name: 'value', label, type: 'select', value: value ?? '', options: selectOptions(INCOME_STABILITY, locale, 'income_stability.'), required: true}]; break;
    case 'risk_attitude': fields = [{name: 'value', label, type: 'select', value: value ?? '', options: selectOptions(RISK_ATTITUDES, locale, 'risk_attitude.'), required: true}]; break;
    case 'coaching_style': fields = [{name: 'value', label, type: 'select', value: value ?? '', options: selectOptions(COACHING_STYLES, locale, 'coaching_style.'), required: true}]; break;
    case 'household': fields = [
      {name: 'adults', label: t('field.adults'), type: 'number', value: value?.adults ?? 1, min: 1, max: 10, required: true},
      {name: 'children', label: t('field.children'), type: 'number', value: value?.children ?? 0, min: 0, max: 20, required: true},
    ]; break;
    case 'saving_rate_target_pct': fields = [{name: 'value', label: t('field.pct'), type: 'percent', value: Number.isFinite(value) ? value : '', min: 0, max: 80, required: true}]; break;
    case 'emergency_fund_target_months': fields = [{name: 'value', label: t('field.months'), type: 'number', value: Number.isFinite(value) ? value : '', min: 0, max: 24, required: true}]; break;
    case 'regular_investing': fields = [
      {name: 'active', label: t('field.investing'), type: 'select', value: value ? (value.active ? 'yes' : 'no') : '', options: yesNo(locale), required: true},
      {name: 'monthly', label: t('field.monthly'), type: 'amount', value: cents(value?.monthly_cents)},
    ]; break;
    case 'debts': {
      const items = Array.isArray(value) ? value : [];
      const rows = [...items, null];
      fields = rows.flatMap((item, i) => [
        {name: 'type_' + i, label: t('field.loanType', {n: i + 1}), type: 'select', value: item?.type || '', options: [{value: '', label: t('common.blank')}, ...selectOptions(DEBT_TYPES, locale, 'debt.')], required: i === 0 && !items.length},
        {name: 'monthly_' + i, label: t('field.loanMonthly', {n: i + 1}), type: 'amount', value: cents(item?.monthly_payment_cents)},
        {name: 'remaining_' + i, label: t('field.loanRemaining', {n: i + 1}), type: 'amount', value: cents(item?.remaining_cents)},
      ]);
      break;
    }
    case 'upcoming': {
      const items = Array.isArray(value) ? value : [];
      const rows = [...items, null];
      fields = rows.flatMap((item, i) => [
        {name: 'what_' + i, label: t('field.what', {n: i + 1}), type: 'text', value: item?.what || '', maxLength: 200, required: i === 0 && !items.length},
        {name: 'month_' + i, label: t('field.when', {n: i + 1}), type: 'month', value: item?.month || ''},
        {name: 'amount_' + i, label: t('field.cost', {n: i + 1}), type: 'amount', value: cents(item?.amount_cents)},
      ]);
      break;
    }
    case 'life_event': fields = [
      {name: 'type', label: t('field.eventType'), type: 'select', value: value?.type || '', options: selectOptions(LIFE_EVENT_TYPES, locale, 'event.'), required: true},
      {name: 'since', label: t('field.since'), type: 'date', value: value?.since || '', required: true},
      {name: 'note', label: t('field.eventNote'), type: 'text', value: value?.note || '', maxLength: 200},
    ]; break;
    case 'protected_categories': fields = [{name: 'value', label: t('field.protected'), type: 'text', value: (Array.isArray(value) ? value : []).filter(item => item !== 'none').join(', '), maxLength: 300}]; break;
    case 'note': fields = [{name: 'value', label: t('field.note'), type: 'text', value: typeof value === 'string' ? value : value?.text || '', maxLength: NOTE_MAX, required: true}]; break;
    case 'tax': {
      const v = isObject(value) ? value : {};
      const pct = bp => Number.isFinite(bp) ? bp / 100 : '';
      fields = [
        {name: 'tax_year', label: t('field.taxYear'), type: 'number', value: v.tax_year ?? '', min: 2000, max: 2100},
        {name: 'base_rate', label: t('field.baseRate'), type: 'percent', value: pct(v.base_rate_bp), min: 0, max: 100},
        {name: 'additional_rate', label: t('field.additionalRate'), type: 'percent', value: pct(v.additional_rate_bp), min: 0, max: 100},
        {name: 'income_limit', label: t('field.incomeLimit'), type: 'amount', value: cents(v.income_limit_cents)},
        {name: 'gross_monthly', label: t('field.grossMonthly'), type: 'amount', value: cents(v.gross_monthly_cents)},
        {name: 'gross_ytd', label: t('field.grossYtd'), type: 'amount', value: cents(v.gross_ytd_cents)},
        {name: 'assessment_end_month', label: t('field.assessmentEnd'), type: 'select', value: v.assessment_end_month ?? '', options: [{value: '', label: t('common.blank')}, ...ASSESSMENT_MONTHS.map(m => ({value: m, label: monthName(m, locale)}))]},
        {name: 'decision_result', label: t('field.decision'), type: 'select', value: v.decision_result || '', options: [{value: '', label: t('decision.unknown')}, ...selectOptions(TAX_DECISIONS, locale, 'decision.')]},
        {name: 'decision_amount', label: t('field.decisionAmount'), type: 'amount', value: cents(v.decision_amount_cents)},
        {name: 'already_set_aside', label: t('field.setAside'), type: 'amount', value: cents(v.already_set_aside_cents)},
      ];
      break;
    }
    case 'year_review': fields = [
      {name: 'year', label: t('field.year'), type: 'number', value: value?.year ?? '', min: 2000, max: 2100, required: true},
      {name: 'closing', label: t('field.closing'), type: 'text', value: value?.closing || '', maxLength: NOTE_MAX},
    ]; break;
  }
  return {
    id: entry?.id ? 'profile-' + entry.id : 'profile-new-' + key,
    kind: 'profile', key, entryId: entry?.id || null,
    title: entry ? t('draft.editTitle', {label}) : t('draft.addTitle', {label}),
    fields, saveLabel: t('draft.save'),
  };
}

/** Accepts integer cents, a typed string ("1 200,50") or '' / null. Returns cents, undefined (empty) or BAD. */
function amountValue(raw) {
  if (raw === undefined || raw === null || raw === '') return undefined;
  if (typeof raw === 'number') return isCents(raw) ? raw : BAD;
  const text = String(raw).trim();
  if (!text) return undefined;
  return parseAmountToCents(text) ?? BAD;
}
function numberValue(raw) {
  if (raw === undefined || raw === null || String(raw).trim() === '') return undefined;
  const n = typeof raw === 'number' ? raw : Number(String(raw).trim().replace(',', '.').replace(/\s|%/g, ''));
  return Number.isFinite(n) ? n : BAD;
}

/**
 * Convert draft-card field values back into a profile entry value.
 * @param {string} key     profile key
 * @param {object} values  {fieldName: value} as edited in the draft card; amount fields may be integer cents or typed text
 * @param {object} base    optional previous value to merge onto (tax and year_review keep fields the form does not show)
 * @returns {{key:string, value:any, errors:object}} errors maps field name -> message key; value is null when errors exist
 */
export function draftValueToEntry(key, values = {}, base = undefined) {
  const errors = {};
  const v = values || {};
  const fail = (field, message) => { errors[field] = message; };
  const choice = (list, field = 'value') => list.includes(v[field]) ? v[field] : (fail(field, 'error.needChoice'), null);
  const ranged = (field, min, max, required = true, integer = false) => {
    const n = numberValue(v[field]);
    if (n === undefined) { if (required) fail(field, 'error.required'); return undefined; }
    if (n === BAD || n < min || n > max || (integer && !Number.isInteger(n))) { fail(field, 'error.badRange'); return undefined; }
    return n;
  };
  const amount = (field, required = false) => {
    const c = amountValue(v[field]);
    if (c === BAD) { fail(field, 'error.badAmount'); return undefined; }
    if (c === undefined && required) fail(field, 'error.needAmount');
    return c;
  };
  let value;
  switch (key) {
    case 'life_stage': value = choice(LIFE_STAGES); break;
    case 'income_stability': value = choice(INCOME_STABILITY); break;
    case 'risk_attitude': value = choice(RISK_ATTITUDES); break;
    case 'coaching_style': value = choice(COACHING_STYLES); break;
    case 'household': value = {adults: ranged('adults', 1, 10, true, true), children: ranged('children', 0, 20, true, true)}; break;
    case 'saving_rate_target_pct': value = ranged('value', 0, 80); break;
    case 'emergency_fund_target_months': value = ranged('value', 0, 24); break;
    case 'regular_investing': {
      const active = v.active === true || v.active === 'yes' ? true : v.active === false || v.active === 'no' ? false : (fail('active', 'error.needChoice'), null);
      value = {active};
      if (active) { const c = amount('monthly'); if (c !== undefined) value.monthly_cents = c; }
      break;
    }
    case 'debts': {
      value = [];
      for (const index of indexes(v, 'type_')) {
        const type = v['type_' + index];
        const monthly = amount('monthly_' + index);
        const remaining = amount('remaining_' + index);
        if (!type) { if (monthly !== undefined) fail('type_' + index, 'error.needChoice'); continue; }
        if (!DEBT_TYPES.includes(type)) { fail('type_' + index, 'error.needChoice'); continue; }
        if (monthly === undefined) { if (!errors['monthly_' + index]) fail('monthly_' + index, 'error.needAmount'); continue; }
        const row = {type, monthly_payment_cents: monthly};
        if (remaining !== undefined) row.remaining_cents = remaining;
        value.push(row);
      }
      break;
    }
    case 'upcoming': {
      value = [];
      for (const index of indexes(v, 'what_')) {
        const what = cleanText(v['what_' + index], 200);
        const month = v['month_' + index];
        const c = amount('amount_' + index);
        if (!what) { if (month || c !== undefined) fail('what_' + index, 'error.needText'); continue; }
        if (!isMonth(month)) { fail('month_' + index, 'error.needMonth'); continue; }
        const row = {what, month};
        if (c !== undefined) row.amount_cents = c;
        value.push(row);
      }
      if (!value.length && !Object.keys(errors).length) fail('what_0', 'error.needText');
      break;
    }
    case 'life_event': {
      const type = choice(LIFE_EVENT_TYPES, 'type');
      const since = typeof v.since === 'string' ? v.since.trim() : '';
      if (!isDate(since) && !isMonth(since)) fail('since', 'error.needDate');
      value = {type, since};
      const note = cleanText(v.note, 200);
      if (note) value.note = note;
      break;
    }
    case 'protected_categories':
      value = String(v.value || '').split(',').map(item => cleanText(item, 60)).filter(Boolean);
      break;
    case 'note': {
      const raw = typeof v.value === 'string' ? v.value.trim() : '';
      if (!raw) fail('value', 'error.required');
      else if (raw.length > NOTE_MAX) fail('value', 'error.tooLong');
      value = cleanText(raw);
      break;
    }
    case 'tax': {
      value = isObject(base) ? clone(base) : {};
      const set = (name, val) => { if (val === undefined) delete value[name]; else value[name] = val; };
      set('tax_year', ranged('tax_year', 2000, 2100, false, true));
      const bp = field => { const n = ranged(field, 0, 100, false); return n === undefined ? undefined : Math.round(n * 100); };
      set('base_rate_bp', bp('base_rate'));
      set('additional_rate_bp', bp('additional_rate'));
      set('income_limit_cents', amount('income_limit'));
      set('gross_monthly_cents', amount('gross_monthly'));
      set('gross_ytd_cents', amount('gross_ytd'));
      const end = v.assessment_end_month === '' || v.assessment_end_month === undefined || v.assessment_end_month === null ? undefined : Number(v.assessment_end_month);
      if (end !== undefined && !ASSESSMENT_MONTHS.includes(end)) fail('assessment_end_month', 'error.needChoice');
      set('assessment_end_month', ASSESSMENT_MONTHS.includes(end) ? end : undefined);
      const decision = v.decision_result || undefined;
      if (decision !== undefined && !TAX_DECISIONS.includes(decision)) fail('decision_result', 'error.needChoice');
      set('decision_result', TAX_DECISIONS.includes(decision) ? decision : undefined);
      set('decision_amount_cents', amount('decision_amount', decision === 'refund' || decision === 'back_tax'));
      set('already_set_aside_cents', amount('already_set_aside'));
      break;
    }
    case 'year_review': {
      value = isObject(base) ? clone(base) : {};
      value.year = ranged('year', 2000, 2100, true, true);
      const closing = cleanText(v.closing);
      if (closing) value.closing = closing; else delete value.closing;
      break;
    }
    default:
      fail('key', 'error.needChoice');
  }
  return {key, value: Object.keys(errors).length ? null : value, errors};
}
function indexes(values, prefix) {
  return Object.keys(values).filter(name => name.startsWith(prefix) && /^\d+$/.test(name.slice(prefix.length)))
    .map(name => Number(name.slice(prefix.length))).sort((a, b) => a - b);
}
