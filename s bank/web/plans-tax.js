// Tax plan UI (V5 lane TX), moved out of plans.js. The plan is optional: when it is off the card still says what
// it does and when the next official tax date is (from data/tax via GET /api/plans/tax), and offers "Turn on" and
// "See an example". The example is GET /api/plans/tax/preview with no inputs: the real calculation on clearly
// labelled example numbers, never saved. "Use my own numbers" opens the form prefilled with what we know.
// The server does every calculation; this module renders and wires. Text exists in EN, FI and SV.
// Finnish terms: verokortti (tax card), verotuspäätös (tax decision), OmaVero (Swedish: MinSkatt).

import { emptyStateHTML, emptyText } from './empty-states.js';
import { planHead, offActions, exampleActions, wholeEuros } from './plans-mortgage.js';

const LOCALES = ['en', 'fi', 'sv'];
const COPY = {
  // Shared plan words (also in plans.js; repeated so this module stands alone)
  'on': ['On', 'Käytössä', 'På'],
  'off': ['Off', 'Ei käytössä', 'Av'],
  'turnOn': ['Turn on', 'Ota käyttöön', 'Slå på'],
  'turnOff': ['Turn off', 'Poista käytöstä', 'Stäng av'],
  'estimate': ['Estimate', 'Arvio', 'Uppskattning'],
  'perMonth': ['a month', 'kuukaudessa', 'i månaden'],
  'saved': ['Plan saved. It is now held back on each payday.', 'Suunnitelma tallennettu. Se varataan nyt jokaisena palkkapäivänä.', 'Planen är sparad. Den hålls nu undan varje lönedag.'],
  // Tax plan card (moved from plans.js)
  't.title': ['Tax plan', 'Verosuunnitelma', 'Skatteplan'],
  't.benefit': ['Put a little aside each month for back taxes, know when a refund is coming, and get a nudge if your tax card looks off.', 'Varaa joka kuukausi vähän jäännösveroa varten, tiedä milloin veronpalautus tulee ja saat vinkin, jos verokorttisi näyttää väärältä.', 'Lägg undan lite varje månad för kvarskatt, vet när en skatteåterbäring kommer och få en påminnelse om skattekortet verkar fel.'],
  't.setAside': ['for back taxes, until {date}', 'jäännösveroa varten {date} asti', 'för kvarskatt, fram till {date}'],
  't.needsInputs': ['Add your tax card numbers (gross salary and tax rate) or an expected back tax to check this.', 'Lisää verokorttisi tiedot (bruttopalkka ja veroprosentti) tai odotettu jäännösvero, niin voimme tarkistaa tämän.', 'Lägg till uppgifterna från ditt skattekort (bruttolön och skatteprocent) eller en väntad kvarskatt så kan vi kontrollera det här.'],
  't.nothing': ['Nothing to put aside for taxes right now.', 'Veroja varten ei tarvitse varata juuri nyt.', 'Inget att lägga undan för skatt just nu.'],
  't.estimateDate': ['The date is our estimate; your tax decision shows the exact one.', 'Päivä on arviomme; verotuspäätöksessäsi on tarkka päivä.', 'Datumet är vår uppskattning; ditt beskattningsbeslut visar det exakta.'],
  't.refund': ['Tax refund of about {amount} expected on {date}.', 'Veronpalautusta noin {amount} odotetaan {date}.', 'Skatteåterbäring på cirka {amount} väntas {date}.'],
  't.refundNoDate': ['You expect a tax refund of about {amount} after your tax decision.', 'Odotat noin {amount} veronpalautusta verotuspäätöksen jälkeen.', 'Du väntar en skatteåterbäring på cirka {amount} efter beskattningsbeslutet.'],
  't.refundSeen': ['Your tax refund of {amount} arrived on {date}.', 'Veronpalautuksesi {amount} saapui {date}.', 'Din skatteåterbäring på {amount} kom {date}.'],
  't.cardOk': ['Your tax card looks right for this year’s income.', 'Verokorttisi näyttää sopivan tämän vuoden tuloihin.', 'Ditt skattekort ser rätt ut för årets inkomster.'],
  't.cardAbove': ['Your income this year looks higher than the income limit on your tax card. If the difference is large, a new tax card can help you avoid back taxes. You can change it in {omavero}.', 'Tämän vuoden tulosi näyttävät suuremmilta kuin verokorttisi tuloraja. Jos ero on suuri, uusi verokortti voi auttaa välttämään jäännösveroa. Voit muuttaa sen {omavero}-palvelussa.', 'Dina inkomster i år ser högre ut än inkomstgränsen på ditt skattekort. Om skillnaden är stor kan ett nytt skattekort hjälpa dig att undvika kvarskatt. Du kan ändra det i {omavero}.'],
  't.cardBelow': ['Your income this year looks clearly lower than your tax card expects. You may get a refund, or you can lower your rate in {omavero}.', 'Tämän vuoden tulosi näyttävät selvästi pienemmiltä kuin verokorttisi olettaa. Saatat saada palautusta, tai voit laskea prosenttia {omavero}-palvelussa.', 'Dina inkomster i år ser klart lägre ut än skattekortet räknar med. Du kan få återbäring, eller sänka procenten i {omavero}.'],
  't.cardDiffers': ['Your pay in the account differs from your tax card numbers. That is often other payroll deductions; if anything changed, check your tax card in {omavero}.', 'Tilillesi tullut palkka poikkeaa verokortin luvuista. Syy on usein muut palkasta tehtävät vähennykset; jos jokin muuttui, tarkista verokorttisi {omavero}-palvelussa.', 'Lönen på kontot skiljer sig från skattekortets siffror. Det beror ofta på andra löneavdrag; om något ändrats, kontrollera skattekortet i {omavero}.'],
  't.cardMissing': ['Add your gross monthly salary and tax-card rate, and I can check whether your tax card fits your income.', 'Lisää bruttokuukausipalkkasi ja verokortin prosentti, niin voin tarkistaa, sopiiko verokorttisi tuloihisi.', 'Lägg till din bruttolön per månad och skattekortets procent, så kan jag kolla om skattekortet passar dina inkomster.'],
  't.dates': ['Coming up', 'Tulossa', 'På gång'],
  't.kind.back_tax': ['Back tax due', 'Jäännösveron eräpäivä', 'Kvarskatt förfaller'],
  't.kind.refund': ['Refund expected', 'Palautus odotettavissa', 'Återbäring väntas'],
  't.kind.return_coming': ['Pre-completed tax return arrives', 'Esitäytetty veroilmoitus saapuu', 'Förhandsifylld skattedeklaration kommer'],
  't.kind.check_return': ['Check your tax return', 'Tarkista veroilmoitus', 'Kontrollera skattedeklarationen'],
  't.kind.decision_pending': ['Tax decisions ready by', 'Verotuspäätökset valmiina viimeistään', 'Beskattningsbesluten klara senast'],
  't.expect': ['Change numbers', 'Muuta lukuja', 'Ändra siffror'],
  't.card': ['Tax card details', 'Verokortin tiedot', 'Skattekortets uppgifter'],
  't.footer': ['Estimate from what you entered. Your tax decision in OmaVero is the official source.', 'Arvio antamistasi tiedoista. Virallinen lähde on verotuspäätöksesi OmaVerossa.', 'Uppskattning utifrån det du angett. Den officiella källan är ditt beskattningsbeslut i MinSkatt.'],
  'f.tTitle': ['Help me plan taxes', 'Auta minua suunnittelemaan verot', 'Hjälp mig planera skatten'],
  'f.tIntro': ['Copy the tax-card numbers from OmaVero or your payslip, and add any back tax or refund you already expect for this year. Only you see them, and you can change them later.', 'Katso verokortin luvut OmaVerosta tai palkkalaskelmasta ja lisää jäännösvero tai palautus, jota jo odotat tältä vuodelta. Vain sinä näet luvut, ja voit muuttaa niitä myöhemmin.', 'Ta skattekortets siffror från MinSkatt eller lönebeskedet och lägg till kvarskatt eller återbäring som du redan väntar dig för i år. Bara du ser dem, och du kan ändra dem senare.'],
  'f.backTax': ['Back taxes I expect for this year', 'Odotan jäännösveroa tältä vuodelta', 'Kvarskatt jag väntar mig för i år'],
  'f.refund': ['Refund I expect for this year', 'Odotan veronpalautusta tältä vuodelta', 'Återbäring jag väntar mig för i år'],
  't.save': ['Turn on my tax plan', 'Ota verosuunnitelma käyttöön', 'Slå på min skatteplan'],
  // V5 lane TX: off card, example, form fields, Me row
  'v5.tx.calendar': ['Tax calendar', 'Verokalenteri', 'Skattekalender'],
  'v5.tx.next.return_coming': ['Pre-completed tax returns for {year} arrive in {omavero} in April.', 'Vuoden {year} esitäytetyt veroilmoitukset tulevat {omavero}-palveluun huhtikuussa.', 'De förhandsifyllda skattedeklarationerna för {year} kommer till {omavero} i april.'],
  'v5.tx.next.check_return': ['Check your {year} tax return in {omavero}. The next due date is {date}.', 'Tarkista vuoden {year} veroilmoituksesi {omavero}-palvelussa. Seuraava määräpäivä on {date}.', 'Granska din skattedeklaration för {year} i {omavero}. Nästa sista dag är {date}.'],
  'v5.tx.next.decision_pending': ['Your {year} tax decision will be in {omavero} by {date} at the latest.', 'Vuoden {year} verotuspäätöksesi on {omavero}-palvelussa viimeistään {date}.', 'Ditt beskattningsbeslut för {year} finns i {omavero} senast {date}.'],
  'v5.tx.next.refund_expected': ['Your tax refund is expected on {date}.', 'Veronpalautuksesi maksetaan arviolta {date}.', 'Din skatteåterbäring väntas {date}.'],
  'v5.tx.next.back_tax_due': ['Your next back-tax due date is {date}.', 'Jäännösveron seuraava eräpäivä on {date}.', 'Nästa förfallodag för kvarskatten är {date}.'],
  'v5.tx.next.year_end': ['Nothing to do right now. If your income changes a lot, you can update your tax card in {omavero}.', 'Juuri nyt ei ole tehtävää. Jos tulosi muuttuvat paljon, voit päivittää verokorttisi {omavero}-palvelussa.', 'Inget att göra just nu. Om din inkomst ändras mycket kan du uppdatera ditt skattekort i {omavero}.'],
  'v5.tx.next.undated': ['Your exact tax dates are in {omavero}.', 'Tarkat veropäiväsi näet {omavero}-palvelusta.', 'Dina exakta skattedatum finns i {omavero}.'],
  'v5.tx.example': ['See an example', 'Katso esimerkki', 'Se ett exempel'],
  'v5.tx.exampleClose': ['Close the example', 'Sulje esimerkki', 'Stäng exemplet'],
  'v5.tx.badge': ['Example — not your numbers', 'Esimerkki – ei sinun lukujasi', 'Exempel – inte dina siffror'],
  'v5.tx.exampleIntro': ['Here is what the plan shows for someone with these numbers:', 'Näin suunnitelma näyttää henkilölle, jolla on nämä luvut:', 'Så här ser planen ut för någon med de här siffrorna:'],
  'v5.tx.in.gross': ['Gross salary', 'Bruttopalkka', 'Bruttolön'],
  'v5.tx.in.rate': ['Tax card rate', 'Verokortin pidätysprosentti', 'Skatteprocent på skattekortet'],
  'v5.tx.in.limit': ['Income limit for the year', 'Vuoden tuloraja', 'Inkomstgräns för året'],
  'v5.tx.in.backTax': ['Expected back tax', 'Odotettu jäännösvero', 'Väntad kvarskatt'],
  'v5.tx.in.refund': ['Expected refund', 'Odotettu palautus', 'Väntad återbäring'],
  'v5.tx.perMonthShort': ['{amount}/month', '{amount}/kk', '{amount}/mån'],
  'v5.tx.outlook': ['Outlook', 'Ennuste', 'Prognos'],
  'v5.tx.outlookBack': ['Back tax of about {amount} expected, due about {date}.', 'Jäännösveroa odotetaan noin {amount}, eräpäivä arviolta {date}.', 'Kvarskatt på cirka {amount} väntas, förfaller omkring {date}.'],
  'v5.tx.outlookNone': ['No back tax or refund expected.', 'Jäännösveroa tai palautusta ei odoteta.', 'Ingen kvarskatt eller återbäring väntas.'],
  'v5.tx.cardCheck': ['Tax card check', 'Verokortin tarkistus', 'Kontroll av skattekortet'],
  'v5.tx.incomeVsLimit': ['Income this year about {income}; limit on the tax card {limit}.', 'Tämän vuoden tulot noin {income}; verokortin tuloraja {limit}.', 'Årets inkomster cirka {income}; gränsen på skattekortet {limit}.'],
  'v5.tx.exampleFooter': ['Worked out with the same calculation as your own plan. Nothing is saved, and none of this is your money.', 'Laskettu samalla tavalla kuin oma suunnitelmasi. Mitään ei tallenneta, eivätkä luvut ole sinun rahojasi.', 'Uträknat på samma sätt som din egen plan. Inget sparas, och inget av detta är dina pengar.'],
  'v5.tx.useOwn': ['Use my own numbers', 'Käytä omia lukujani', 'Använd mina egna siffror'],
  'v5.tx.exampleLoading': ['Working out the example…', 'Lasketaan esimerkkiä…', 'Räknar ut exemplet…'],
  'v5.tx.exampleError': ['The example is not available right now.', 'Esimerkki ei ole juuri nyt saatavilla.', 'Exemplet är inte tillgängligt just nu.'],
  'v5.tx.f.gross': ['Gross salary a month (before tax)', 'Bruttopalkka kuukaudessa (ennen veroja)', 'Bruttolön per månad (före skatt)'],
  'v5.tx.f.grossHelp': ['From your payslip.', 'Palkkalaskelmasta.', 'Från lönebeskedet.'],
  'v5.tx.f.grossHelpNet': ['From your payslip. Your salary arrives as about {amount} after tax.', 'Palkkalaskelmasta. Palkkasi tulee tilille noin {amount} verojen jälkeen.', 'Från lönebeskedet. Lönen kommer in som cirka {amount} efter skatt.'],
  'v5.tx.f.rate': ['Tax card rate (%)', 'Verokortin pidätysprosentti (%)', 'Skatteprocent på skattekortet (%)'],
  'v5.tx.f.rateHelp': ['The base rate on your tax card (verokortti) in OmaVero.', 'Verokortin perusprosentti OmaVerosta.', 'Grundprocenten på ditt skattekort i MinSkatt.'],
  'v5.tx.f.limit': ['Income limit for the year', 'Tuloraja vuodelle', 'Inkomstgräns för året'],
  'v5.tx.f.limitHelp': ['Also on the tax card. Leave empty if you do not know it.', 'Myös verokortissa. Jätä tyhjäksi, jos et tiedä.', 'Står också på skattekortet. Lämna tomt om du inte vet.'],
  'v5.tx.preview': ['About {amount} a month for back taxes, until {date}.', 'Noin {amount} kuukaudessa jäännösveroa varten, {date} asti.', 'Cirka {amount} i månaden för kvarskatt, fram till {date}.'],
  'v5.tx.previewNone': ['Nothing to put aside for back taxes.', 'Jäännösveroa varten ei tarvitse varata.', 'Inget att lägga undan för kvarskatt.'],
  'v5.tx.previewAbove': ['Your income looks higher than the tax card limit.', 'Tulosi näyttävät suuremmilta kuin verokortin tuloraja.', 'Inkomsten ser högre ut än skattekortets gräns.'],
  'v5.tx.previewBelow': ['Your income looks clearly lower than the tax card expects.', 'Tulosi näyttävät selvästi pienemmiltä kuin verokortti olettaa.', 'Inkomsten ser klart lägre ut än skattekortet räknar med.'],
  'v5.tx.me.off': ['Turn it on, or see an example first, on the Goals page.', 'Ota käyttöön tai katso ensin esimerkki Tavoitteet-sivulla.', 'Slå på den, eller se ett exempel först, på sidan Mål.'],
  'v5.tx.me.on': ['On.', 'Käytössä.', 'På.'],
  'v5.tx.me.monthly': ['{amount} a month for back taxes, until {date}.', '{amount} kuukaudessa jäännösveroa varten, {date} asti.', '{amount} i månaden för kvarskatt, fram till {date}.'],
  'v5.tx.me.open': ['Open tax plan', 'Avaa verosuunnitelma', 'Öppna skatteplanen'],
  'v5.tx.me.change': ['Change', 'Muuta', 'Ändra'],
  'v5.tx.me.details': ['Your tax details', 'Verotietosi', 'Dina skatteuppgifter'],
  // V5 fix lane GL: an empty plan says what it needs instead of "looks enough"; back tax and refund are one or the other
  'v5.tx.needInputs': ['Nothing is set aside yet. Add the numbers from your tax card, or a back tax you expect, and the plan can check whether your withholding is enough.', 'Mitään ei vielä varata. Lisää verokorttisi luvut tai odottamasi jäännösvero, niin suunnitelma voi tarkistaa, riittääkö ennakonpidätyksesi.', 'Inget läggs undan ännu. Lägg till siffrorna från skattekortet, eller en kvarskatt du väntar dig, så kan planen kolla om skatteavdraget räcker.'],
  'v5.tx.addNumbers': ['Add tax card numbers', 'Lisää verokortin luvut', 'Lägg till skattekortets siffror'],
  'v5.tx.bothError': ['Enter either a back tax or a refund for this year, not both. Your tax decision has only one of them.', 'Anna tälle vuodelle joko jäännösvero tai palautus, ei molempia. Verotuspäätöksessä on vain toinen niistä.', 'Ange antingen kvarskatt eller återbäring för i år, inte båda. Beskattningsbeslutet har bara det ena.'],
};
const OMAVERO = {en: 'OmaVero', fi: 'OmaVero', sv: 'MinSkatt'};

const lang = locale => (LOCALES.includes(String(locale).slice(0, 2)) ? String(locale).slice(0, 2) : 'en');
export function taxText(locale, key, values = {}) {
  const row = COPY[key];
  const text = row ? row[LOCALES.indexOf(lang(locale))] || row[0] : key;
  return text.replace(/\{(\w+)\}/g, (_, name) => (values[name] === undefined ? '{' + name + '}' : String(values[name])));
}
export const TAX_COPY_KEYS = Object.freeze(Object.keys(COPY));
/** Vero's e-service name in the customer's language (OmaVero; MinSkatt in Swedish). */
export const omaVero = locale => OMAVERO[lang(locale)];

const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
function pct(bp, locale) {
  const text = ((Number(bp) || 0) / 100).toFixed(2).replace(/0$/, '').replace(/\.0$/, '');
  return lang(locale) === 'en' ? text + '%' : text.replace('.', ',') + ' %';
}
function row(label, value, extra = '') { return `<div class="plan-row${extra}"><dt>${escape(label)}</dt><dd>${escape(value)}</dd></div>`; }

// ---------------------------------------------------------------- form (draft-card.js spec)

/** Form for "Turn on" / "Use my own numbers": tax-card numbers and expectations, prefilled with what we know. */
export function taxSpec(locale, {value = null, prefill = null} = {}) {
  const t = (key, values) => taxText(locale, key, values);
  const v = value || {};
  const p = prefill || {};
  const pick = key => v[key] ?? p[key] ?? '';
  const rate = v.base_rate_bp ?? p.base_rate_bp;
  return {id: 'plan-tax', kind: 'plan', title: t('f.tTitle'), intro: t('f.tIntro'), saveLabel: t('t.save'), mode: 'edit', fields: [
    {name: 'gross_monthly_cents', label: t('v5.tx.f.gross'), type: 'amount', value: pick('gross_monthly_cents'), min: 0,
      help: Number.isInteger(p.net_salary_cents) && p.money ? t('v5.tx.f.grossHelpNet', {amount: p.money(p.net_salary_cents)}) : t('v5.tx.f.grossHelp')},
    {name: 'base_rate_pct', label: t('v5.tx.f.rate'), type: 'percent', value: Number.isInteger(rate) ? rate / 100 : '', min: 0, max: 100, help: t('v5.tx.f.rateHelp')},
    {name: 'income_limit_cents', label: t('v5.tx.f.limit'), type: 'amount', value: pick('income_limit_cents'), min: 0, help: t('v5.tx.f.limitHelp')},
    {name: 'expected_back_tax_cents', label: t('f.backTax'), type: 'amount', value: pick('expected_back_tax_cents'), min: 0},
    {name: 'expected_refund_cents', label: t('f.refund'), type: 'amount', value: pick('expected_refund_cents'), min: 0},
  ]};
}

const positive = value => (Number.isSafeInteger(value) && value > 0 ? value : null);
/** Form values -> {value: plan_tax value, card: tax-card fields (cents / basis points) or null, inputs: preview query}. */
export function taxValue(values) {
  const value = {on: true};
  for (const key of ['expected_back_tax_cents', 'expected_refund_cents']) if (positive(values[key])) value[key] = values[key];
  const card = {};
  if (positive(values.gross_monthly_cents)) card.gross_monthly_cents = values.gross_monthly_cents;
  if (Number.isFinite(values.base_rate_pct) && values.base_rate_pct >= 0) card.base_rate_bp = Math.round(values.base_rate_pct * 100);
  if (positive(values.income_limit_cents)) card.income_limit_cents = values.income_limit_cents;
  const inputs = {...card};
  for (const key of ['expected_back_tax_cents', 'expected_refund_cents']) if (value[key]) inputs[key] = value[key];
  return {value, card: Object.keys(card).length ? card : null, inputs};
}

/** The tax-profile value to save for this year's tax card: the existing same-year entry with the form's card fields. */
export function mergeTaxCard(existing, card, taxYear) {
  const value = {...(existing && existing.tax_year === taxYear ? existing : {}), tax_year: taxYear};
  for (const key of ['gross_monthly_cents', 'base_rate_bp', 'income_limit_cents']) {
    if (card && card[key] !== undefined) value[key] = card[key]; else delete value[key];
  }
  return value;
}

/** One-line live preview under the form, from a /api/plans/tax/preview result. */
export function previewLine(data, locale, h) {
  const t = (key, values) => taxText(locale, key, values);
  const s = data?.set_aside || {};
  const parts = [s.monthly_cents > 0 ? t('v5.tx.preview', {amount: h.money(s.monthly_cents), date: h.dateLabel(s.until)}) : t('v5.tx.previewNone')];
  const status = data?.tax_card?.status;
  if (status === 'income_above_limit') parts.push(t('v5.tx.previewAbove'));
  if (status === 'income_below_limit') parts.push(t('v5.tx.previewBelow'));
  return parts.join(' ');
}

/** Plain one-liner for the Me page entry (money-profile.js describeEntry via plans.js describePlan). */
export function describeTaxPlan(entry, locale, money) {
  const v = entry?.value || {};
  const parts = [taxText(locale, 'on')];
  if (v.expected_back_tax_cents) parts.push(taxText(locale, 'f.backTax') + ': ' + money(v.expected_back_tax_cents));
  if (v.expected_refund_cents) parts.push(taxText(locale, 'f.refund') + ': ' + money(v.expected_refund_cents));
  return parts.join(' · ');
}

// ---------------------------------------------------------------- rendering (pure)

/** The next official date in plain words, from the tax calendar stage: "Your 2025 tax decision will be in OmaVero by 31 Oct at the latest." */
export function nextTaxDateText(stage, locale, dateLabel) {
  if (!stage?.stage) return '';
  const values = {year: stage.tax_year ?? '', omavero: omaVero(locale), date: stage.next_date ? dateLabel(stage.next_date) : ''};
  const dated = ['check_return', 'decision_pending', 'refund_expected', 'back_tax_due'];
  if (dated.includes(stage.stage) && !stage.next_date) return taxText(locale, 'v5.tx.next.undated', values);
  const key = 'v5.tx.next.' + stage.stage;
  return COPY[key] ? taxText(locale, key, values) : '';
}

const CALENDAR_ICON = '<svg class="tax-next__icon" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false"><rect x="3.5" y="5" width="17" height="15.5" rx="3" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M3.5 9.5h17M8 3v4M16 3v4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="12" cy="14.5" r="1.6" fill="currentColor"/></svg>';

function nextDateBlock(data, h) {
  const text = nextTaxDateText(data?.stage, h.locale, h.dateLabel);
  if (!text) return '';
  return `<div class="tax-next">${CALENDAR_ICON}<div><p class="tax-next__label">${escape(taxText(h.locale, 'v5.tx.calendar'))}</p><p class="tax-next__text">${escape(text)}</p></div></div>`;
}

function cardCheckText(data, h) {
  const key = {looks_ok: 't.cardOk', income_above_limit: 't.cardAbove', income_below_limit: 't.cardBelow', pay_differs: 't.cardDiffers', missing: 't.cardMissing'}[data?.tax_card?.status] || 't.cardMissing';
  // English keeps the server's 'OmaVero (vero.fi)' hint; Finnish and Swedish use the service's own name.
  return taxText(h.locale, key, {omavero: lang(h.locale) === 'en' && data?.omavero_text ? data.omavero_text : omaVero(h.locale)});
}

function datesList(data, h) {
  const dates = (data?.dates || []).slice(0, 3);
  return dates.length ? `<dl class="plan-rows">${dates.map(item => row(taxText(h.locale, 't.kind.' + item.kind), h.dateLabel(item.date))).join('')}</dl>` : '';
}

/** The read-only example (or an error/loading line). `example` = {open, loading, error, data}. */
export function renderTaxExample(example, h) {
  const {locale, money, dateLabel} = h;
  const t = (key, values) => taxText(locale, key, values);
  const whole = cents => wholeEuros(cents, locale);
  const closeOnly = `<div class="plan-actions plan-example-actions"><button type="button" class="text-button" data-plan-tax-example-close>${escape(t('v5.tx.exampleClose'))}</button></div>`;
  let body;
  if (example?.error) body = `<p class="plan-note">${escape(t('v5.tx.exampleError'))}</p>${closeOnly}`;
  else if (!example?.data) body = `<p class="plan-note" role="status">${escape(t('v5.tx.exampleLoading'))}</p>`;
  else {
    const d = example.data;
    const i = d.inputs || {};
    const inputs = [
      Number.isInteger(i.gross_monthly_cents) ? row(t('v5.tx.in.gross'), t('v5.tx.perMonthShort', {amount: whole(i.gross_monthly_cents)})) : '',
      Number.isInteger(i.base_rate_bp) ? row(t('v5.tx.in.rate'), pct(i.base_rate_bp, locale)) : '',
      Number.isInteger(i.income_limit_cents) ? row(t('v5.tx.in.limit'), whole(i.income_limit_cents)) : '',
      Number.isInteger(i.expected_back_tax_cents) ? row(t('v5.tx.in.backTax'), whole(i.expected_back_tax_cents)) : '',
      Number.isInteger(i.expected_refund_cents) ? row(t('v5.tx.in.refund'), whole(i.expected_refund_cents)) : '',
    ].join('');
    const s = d.set_aside || {};
    const amount = s.monthly_cents > 0
      ? `<p class="plan-amount">${escape(money(s.monthly_cents))} <span>${escape(t('perMonth'))}</span></p><p class="plan-sub">${escape(t('t.setAside', {date: dateLabel(s.until)}))}</p>`
      : `<p class="plan-sub">${escape(t('t.nothing'))}</p>`;
    const back = (s.instalments || []).find(item => item.status === 'upcoming');
    // "about" amounts are whole euros (V5 money format).
    const outlook = back ? t('v5.tx.outlookBack', {amount: whole(back.amount_cents), date: dateLabel(back.due_date)})
      : d.refund ? (d.refund.expected_date ? t('t.refund', {amount: whole(d.refund.amount_cents), date: dateLabel(d.refund.expected_date)}) : t('t.refundNoDate', {amount: whole(d.refund.amount_cents)}))
        : t('v5.tx.outlookNone');
    const tc = d.tax_card || {};
    const incomeLine = Number.isInteger(tc.projected_gross_cents) && Number.isInteger(tc.income_limit_cents)
      ? `<p class="small-text">${escape(t('v5.tx.incomeVsLimit', {income: whole(tc.projected_gross_cents), limit: whole(tc.income_limit_cents)}))}</p>` : '';
    body = `<div class="tax-example__cols"><div class="tax-example__col"><p class="tax-example__intro">${escape(t('v5.tx.exampleIntro'))}</p><dl class="plan-rows tax-example__inputs">${inputs}</dl>`
      + `<div class="tax-example__result">${amount}</div></div><div class="tax-example__col">`
      + `<h4>${escape(t('v5.tx.outlook'))}</h4><p class="plan-note">${escape(outlook)}</p>`
      + `<h4>${escape(t('v5.tx.cardCheck'))}</h4><p class="plan-note">${escape(cardCheckText(d, h))}</p>${incomeLine}`
      + `<h4>${escape(t('t.dates'))}</h4>${datesList(d, h)}</div></div>`
      + `<p class="small-text">${escape(t('v5.tx.exampleFooter'))}</p>`
      + exampleActions('tax', t('v5.tx.useOwn'), t('v5.tx.exampleClose'));
  }
  return `<section class="tax-example" aria-label="${escape(t('v5.tx.badge'))}" aria-live="polite">${body}</section>`;
}

/** The tax plan card. `data` is GET /api/plans/tax (+ `example` {open, loading, error, data} from the controller). */
export function renderTaxCard(data, h) {
  const {locale, money, dateLabel} = h;
  const t = (key, values) => taxText(locale, key, values);
  if (!data?.on) {
    // Same pattern as the mortgage plan: the example replaces the card body and closes from the bottom.
    if (data?.example?.open) {
      return `<article class="plan-card plan-card--example plan-card--wide tax-plan tax-plan--off tax-plan--example" data-plan="tax">${planHead(t('t.title'), t('off'), false, t('v5.tx.badge'))}${renderTaxExample(data.example, h)}</article>`;
    }
    return `<article class="plan-card plan-card--off tax-plan tax-plan--off" data-plan="tax">${planHead(t('t.title'), t('off'), false)}`
      + `<p class="plan-benefit">${escape(t('t.benefit'))}</p>${nextDateBlock(data, h)}`
      + `${offActions('tax', t('turnOn'), t('v5.tx.example'), 'data-plan-tax-example')}</article>`;
  }
  const s = data.set_aside || {};
  const entered = data.tax_card?.status && data.tax_card.status !== 'missing';
  const expects = Boolean(data.refund) || (s.instalments || []).length > 0;
  // The server says so directly (needs_inputs, lane NB); older responses fall back to the same check here.
  const needsInputs = typeof data.needs_inputs === 'boolean' ? data.needs_inputs : !(s.monthly_cents > 0) && !entered && !expects;
  if (needsInputs) {
    return `<article class="plan-card plan-card--on tax-plan" data-plan="tax">${planHead(t('t.title'), t('on'), true)}<p class="plan-note">${escape(t('v5.tx.needInputs'))}</p>`
      + `<div class="plan-actions plan-off-actions"><button type="button" class="secondary-button plan-turn-on" data-plan-edit="tax">${escape(t('v5.tx.addNumbers'))}</button></div>`
      + `${nextDateBlock(data, h)}<p class="small-text">${escape(t('t.footer'))}</p><div class="plan-actions"><button type="button" class="text-button" data-plan-off="tax">${escape(t('turnOff'))}</button></div></article>`;
  }
  const head = s.monthly_cents > 0
    ? `<p class="plan-amount">${escape(money(s.monthly_cents))} <span>${escape(t('perMonth'))}</span></p><p class="plan-sub">${escape(t('t.setAside', {date: dateLabel(s.until)}))} · ${escape(t('estimate'))}</p>${(s.instalments || []).some(item => item.status === 'upcoming' && item.date_is_estimate) ? `<p class="small-text">${escape(t('t.estimateDate'))}</p>` : ''}`
    : data.needs_inputs
      // Nothing entered yet: ask for the numbers, never claim the withholding looks enough.
      ? `<p class="plan-sub tax-plan__needs">${escape(data.needs_inputs_text?.[locale] || t('t.needsInputs'))}</p>`
      : emptyStateHTML({kind: 'calm', celebrate: true, compact: true, title: emptyText(h.locale, 'v5.em.plans.taxNothing.title'), body: emptyText(h.locale, 'v5.em.plans.taxNothing.body'), esc: escape, id: 'tax-nothing'});
  const r = data.refund;
  const refund = r ? `<p class="plan-note">${escape(r.seen && r.seen_date ? t('t.refundSeen', {amount: money(r.amount_cents), date: dateLabel(r.seen_date)})
    : r.expected_date ? t('t.refund', {amount: money(r.amount_cents), date: dateLabel(r.expected_date)}) : t('t.refundNoDate', {amount: money(r.amount_cents)}))}</p>` : '';
  const card = `<p class="plan-note">${escape(cardCheckText(data, h))}</p>`;
  const dates = datesList(data, h);
  const dateList = dates ? `<h4>${escape(t('t.dates'))}</h4>${dates}` : '';
  return `<article class="plan-card plan-card--on tax-plan" data-plan="tax">${planHead(t('t.title'), t('on'), true)}${head}${refund}${card}${dateList}`
    + `<p class="small-text">${escape(t('t.footer'))}</p><div class="plan-actions"><button type="button" class="text-button" data-plan-edit="tax">${escape(t('t.expect'))}</button><button type="button" class="text-button" data-plan-tax-card>${escape(t('t.card'))}</button><button type="button" class="text-button" data-plan-off="tax">${escape(t('turnOff'))}</button></div></article>`;
}

/**
 * Me page: one compact tax row pointing to the plan on Goals (replaces the old "Taxes / Open my taxes" block).
 * @param {object|null} entry the plan_tax profile entry (null when off)
 * @param {object|null} data GET /api/plans/tax when already loaded (adds the monthly amount or the next tax date)
 * @param {{locale, money, dateLabel}} h
 * Data attributes: data-profile-open-tax-plan, data-profile-edit="<entry id>".
 */
export function meTaxRowHTML(entry, data, h) {
  const t = (key, values) => taxText(h.locale, key, values);
  const on = Boolean(entry) || Boolean(data?.on);
  let line;
  if (on && data?.set_aside?.monthly_cents > 0) line = t('v5.tx.me.monthly', {amount: h.money(data.set_aside.monthly_cents), date: h.dateLabel(data.set_aside.until)});
  else if (on) line = entry ? describeTaxPlan(entry, h.locale, h.money) : t('v5.tx.me.on');
  else line = t('v5.tx.me.off');
  const next = data ? nextTaxDateText(data.stage, h.locale, h.dateLabel) : '';
  const change = on && entry?.id ? `<button type="button" class="profile-button" data-profile-edit="${escape(entry.id)}">${escape(t('v5.tx.me.change'))}</button>` : '';
  return `<div class="me-tax-row" data-me-tax-row><div class="me-tax-row__text"><p class="me-tax-row__title"><strong>${escape(t('t.title'))}</strong> <span class="plan-pill${on ? '' : ' plan-pill--off'}">${escape(t(on ? 'on' : 'off'))}</span></p>`
    + `<p class="me-tax-row__line">${escape(line)}</p>${next ? `<p class="me-tax-row__next">${escape(next)}</p>` : ''}</div>`
    + `<div class="me-tax-row__actions">${change}<button type="button" class="profile-button profile-button-primary" data-profile-open-tax-plan>${escape(t('v5.tx.me.open'))} ›</button></div></div>`;
}

/** Scroll the Goals tax card into view once it is painted (after navigating from Me). */
export function revealTaxCard(doc = globalThis.document, tries = 20) {
  const card = doc?.querySelector?.('#plans-root [data-plan="tax"]');
  if (card && !card.closest?.('[hidden]')) {
    card.scrollIntoView?.({behavior: 'smooth', block: 'start'});
    card.classList?.add?.('tax-plan--flash');
    setTimeout(() => card.classList?.remove?.('tax-plan--flash'), 1600);
    return;
  }
  if (tries > 0) setTimeout(() => revealTaxCard(doc, tries - 1), 100);
}

// ---------------------------------------------------------------- wiring

/**
 * Tax-plan controller used by plans.js initPlans.
 * @param {object} deps {request, captureContext, isCurrent, openDraft, money, dateLabel, locale: () => string,
 *   referenceDate: () => string|null, updatePreview(card, text), planEntry(key), getData(): tax data, setData(data) (repaints),
 *   saved(context, messageKey)}
 */
export function createTaxPlan(deps) {
  const {request, captureContext, isCurrent, openDraft, money, dateLabel, locale, referenceDate} = deps;
  const asOf = () => (referenceDate() ? {as_of: referenceDate()} : {});
  let example = {open: false, data: null, error: false};
  const h = () => ({locale: locale(), money, dateLabel});
  const withExample = data => (data ? {...data, example} : data);
  const repaint = () => deps.setData(withExample(deps.getData()));

  async function load(context) {
    const data = await request(context, 'get', '/api/plans/tax', asOf());
    return withExample(data);
  }
  async function toggleExample() {
    if (example.open) { example = {...example, open: false}; repaint(); deps.reveal?.(); return; }
    example = {...example, open: true, error: false};
    repaint();
    deps.reveal?.();
    if (example.data) return;
    const context = captureContext();
    try {
      const data = await request(context, 'get', '/api/plans/tax/preview', asOf());
      if (!isCurrent(context)) return;
      example = {...example, data, error: false};
    } catch {
      if (!isCurrent(context)) return;
      example = {...example, error: true};
    }
    repaint();
  }
  let previewTimer = null;
  function livePreview(values, card, context, lang) {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(async () => {
      const {inputs, value} = taxValue(values);
      // A back tax and a refund for the same year cannot both happen: say so right away (saving is refused too).
      if (value.expected_back_tax_cents && value.expected_refund_cents) { deps.updatePreview?.(card, taxText(lang, 'v5.tx.bothError')); return; }
      if (!Object.keys(inputs).length) { deps.updatePreview?.(card, ''); return; }
      try {
        const data = await request(context, 'get', '/api/plans/tax/preview', {...asOf(), ...inputs});
        deps.updatePreview?.(card, previewLine(data, lang, {money, dateLabel}));
      } catch { deps.updatePreview?.(card, ''); }
    }, 300);
  }
  function openSetup(provenance = 'user') {
    const context = captureContext();
    const lang = locale();
    const data = deps.getData();
    const current = data?.on ? deps.planEntry?.('plan_tax')?.value : null;
    const spec = taxSpec(lang, {value: current, prefill: {...(data?.prefill || example.data?.prefill || {}), money}});
    openDraft(spec, {
      onChange: (values, card) => livePreview(values, card, context, lang),
      onSave: async values => {
        const converted = taxValue(values);
        if (converted.value.expected_back_tax_cents && converted.value.expected_refund_cents) throw new Error(taxText(lang, 'v5.tx.bothError'));
        const prefill = data?.prefill || example.data?.prefill || {};
        const year = Number((referenceDate() || data?.as_of || String(data?.tax_year || '')).slice(0, 4)) || data?.tax_year;
        const changedCard = ['gross_monthly_cents', 'base_rate_bp', 'income_limit_cents'].some(key => (converted.card?.[key] ?? null) !== (prefill[key] ?? null));
        if (changedCard && (converted.card || prefill.tax_card_entry_id)) {
          const entries = deps.planEntry?.('tax');
          const existing = (Array.isArray(entries) ? entries : entries ? [entries] : []).find(entry => entry.id === prefill.tax_card_entry_id);
          const value = mergeTaxCard(existing?.value, converted.card, year);
          if (existing?.id) await request(context, 'post', '/api/profile/entries/update', {entry_id: existing.id, value, confirmed: true, provenance});
          else await request(context, 'post', '/api/profile/entries', {key: 'tax', value, source: provenance === 'user' ? 'you_told_me' : 'from_our_chat', confirmed: true, provenance});
        }
        await request(context, 'post', '/api/plans/tax', {plan: converted.value, confirmed: true, provenance,
          ...(provenance === 'user' ? {} : {source: 'from_our_chat'})});
        example = {...example, open: false};
        await deps.saved(context, 'saved');
      }});
  }
  /** Handles the tax-only buttons; returns true when the click was one of them. */
  function handleClick(event) {
    const target = event.target?.closest?.('[data-plan-tax-example],[data-plan-tax-example-close],[data-plan-tax-own]');
    const has = name => Boolean(target?.hasAttribute?.(name));
    if (!has('data-plan-tax-example') && !has('data-plan-tax-example-close') && !has('data-plan-tax-own')) return false;
    if (has('data-plan-tax-own')) openSetup();
    else if (has('data-plan-tax-example-close')) { example = {...example, open: false}; repaint(); deps.reveal?.(); }
    else toggleExample();
    return true;
  }
  return {load, openSetup, handleClick, reset() { example = {open: false, data: null, error: false}; }, render: (data, helpers) => renderTaxCard(data, helpers || h())};
}
