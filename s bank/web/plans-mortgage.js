// Mortgage plan UI (V5 lane MG): the off card with "See an example", the read-only example and the rich result
// (monthly payment, payoff, years left, interest, total, balance chart, principal-vs-interest split, what-ifs).
// The server does every calculation (scoach/mortgage.py via /api/plans/mortgage/preview and /projection);
// this module only renders it. Moved here from plans.js; plans.js re-exports the old names.

const LOCALES = ['en', 'fi', 'sv'];
const COPY = {
  'on': ['On', 'Käytössä', 'På'],
  'off': ['Off', 'Ei käytössä', 'Av'],
  'turnOn': ['Turn on', 'Ota käyttöön', 'Slå på'],
  'turnOff': ['Turn off', 'Poista käytöstä', 'Stäng av'],
  'change': ['Change numbers', 'Muuta lukuja', 'Ändra siffror'],
  'estimate': ['Estimate', 'Arvio', 'Uppskattning'],
  'perMonth': ['a month', 'kuukaudessa', 'i månaden'],
  'heldBack': ['held back on each payday', 'varataan jokaisena palkkapäivänä', 'hålls undan varje lönedag'],
  // Mortgage
  'm.title': ['Mortgage plan', 'Asuntolainasuunnitelma', 'Bolåneplan'],
  'm.benefit': ['If you have a home loan: see the payment held back each payday, when the loan ends, and what a little extra would do.', 'Jos sinulla on asuntolaina: näet jokaisena palkkapäivänä varattavan erän, milloin laina päättyy ja mitä pieni lisälyhennys tekisi.', 'Om du har ett bolån: se betalningen som hålls undan varje lönedag, när lånet är betalt och vad lite extra skulle göra.'],
  'm.detected': ['You pay about {amount} for housing each month, around the {day:ord}. If that is your loan payment, we can start from it.', 'Maksat asumisesta noin {amount} kuukaudessa, yleensä kuun {day}. päivän tienoilla. Jos se on lainanlyhennyksesi, voimme aloittaa siitä.', 'Du betalar cirka {amount} för boendet varje månad, oftast runt den {day} i månaden. Om det är din lånebetalning kan vi börja med den.'],
  'm.payoff': ['Paid off', 'Laina maksettu', 'Lånet betalt'],
  'm.interest': ['Interest still to pay', 'Korkoa vielä maksettavana', 'Ränta kvar att betala'],
  'm.left': ['Loan left', 'Lainaa jäljellä', 'Kvar på lånet'],
  'm.rate': ['Interest rate', 'Korko', 'Ränta'],
  'm.rateParts': ['{ref} {refRate} + bank margin {margin}', '{ref} {refRate} + pankin marginaali {margin}', '{ref} {refRate} + bankens marginal {margin}'],
  'm.rateFixed': ['Fixed rate', 'Kiinteä korko', 'Fast ränta'],
  'm.rateCheck': ['Next rate check', 'Seuraava koron tarkistus', 'Nästa räntejustering'],
  'm.falls': ['With equal principal the payment gets a little smaller every month.', 'Tasalyhennyksessä erä pienenee hieman joka kuukausi.', 'Med rak amortering blir betalningen lite mindre varje månad.'],
  'm.differs': ['The payment you entered differs from the calculated {amount}. It may include fees, or the years left may be different.', 'Antamasi erä poikkeaa lasketusta ({amount}). Siihen voi sisältyä kuluja, tai jäljellä oleva laina-aika voi olla eri.', 'Betalningen du angav skiljer sig från den beräknade ({amount}). Den kan innehålla avgifter, eller så är löptiden en annan.'],
  'm.extraTitle': ['What if I paid a little extra each month?', 'Entä jos lyhentäisin vähän enemmän joka kuukausi?', 'Tänk om jag betalade lite extra varje månad?'],
  'm.extraResult': ['With {extra} extra a month: paid off in {month}, {months} months sooner, about {saved} less interest.', 'Kun lyhennät {extra} enemmän kuukaudessa: laina maksettu {month:in}, {months} kuukautta aiemmin, noin {saved} vähemmän korkoa.', 'Med {extra} extra i månaden: betalt i {month}, {months} månader tidigare, cirka {saved} mindre ränta.'],
  'm.steady': ['Right now it makes sense to keep your cushion first, so we are not suggesting extra payments.', 'Juuri nyt on järkevää pitää turvatyyny ensin, joten emme ehdota lisälyhennyksiä.', 'Just nu är det klokt att behålla säkerhetsmarginalen först, så vi föreslår inga extra amorteringar.'],
  'm.thin': ['Your cushion looks thin. Before paying extra on the loan, it may help to keep a little more in your account for surprises.', 'Turvatyynysi näyttää ohuelta. Ennen lisälyhennyksiä voi olla hyvä pitää tilillä vähän enemmän yllätyksiä varten.', 'Din säkerhetsmarginal ser tunn ut. Innan du amorterar extra kan det vara bra att ha lite mer på kontot för oväntade utgifter.'],
  'm.rateTitle': ['If the rate changed', 'Jos korko muuttuisi', 'Om räntan ändrades'],
  'm.rateUp': ['Rate +1 %-point', 'Korko +1 %-yks.', 'Ränta +1 %-enhet'],
  'm.rateDown': ['Rate −1 %-point', 'Korko −1 %-yks.', 'Ränta −1 %-enhet'],
  'm.rateResult': ['At {rate}: about {amount} a month ({change}).', 'Korolla {rate}: noin {amount} kuukaudessa ({change}).', 'Med {rate}: cirka {amount} i månaden ({change}).'],
  'm.rateResultTerm': ['At {rate}: the same payment, paid off in {months} months.', 'Korolla {rate}: sama erä, laina maksettu {months} kuukaudessa.', 'Med {rate}: samma betalning, betalt på {months} månader.'],
  'm.footer': ['Estimate from the numbers you entered. Check the exact figures with your bank.', 'Arvio antamistasi luvuista. Tarkista tarkat luvut pankistasi.', 'Uppskattning utifrån siffrorna du angav. Kontrollera de exakta siffrorna med din bank.'],
  'm.error': ['These numbers do not add up to a loan that gets repaid. Please check them.', 'Näillä luvuilla laina ei tule maksetuksi. Tarkista luvut.', 'Med de här siffrorna blir lånet inte betalt. Kontrollera dem.'],
  // Mortgage form
  'f.mTitle': ['Your home loan', 'Asuntolainasi', 'Ditt bolån'],
  'f.mIntro': ['Copy these from your loan statement or online bank. Only you see them, and you can change them later.', 'Katso luvut lainalaskelmasta tai verkkopankista. Vain sinä näet ne, ja voit muuttaa niitä myöhemmin.', 'Ta siffrorna från ditt lånebesked eller din internetbank. Bara du ser dem, och du kan ändra dem senare.'],
  'f.principal': ['Loan left to pay', 'Lainaa jäljellä', 'Kvar att betala på lånet'],
  'f.type': ['How you repay', 'Lyhennystapa', 'Hur du amorterar'],
  'f.annuity': ['Annuity: same payment', 'Tasaerä: sama erä', 'Annuitet: samma betalning'],
  'f.equal': ['Equal principal: payment falls', 'Tasalyhennys: erä pienenee', 'Rak amortering: betalningen minskar'],
  'f.ref': ['Reference rate', 'Viitekorko', 'Referensränta'],
  'f.euribor_12m': ['12-month Euribor', '12 kk euribor', '12 månaders Euribor'],
  'f.euribor_6m': ['6-month Euribor', '6 kk euribor', '6 månaders Euribor'],
  'f.euribor_3m': ['3-month Euribor', '3 kk euribor', '3 månaders Euribor'],
  'f.fixed': ['Fixed rate', 'Kiinteä korko', 'Fast ränta'],
  'f.other': ['Other', 'Muu', 'Annan'],
  'f.refRate': ['Reference rate now (%)', 'Viitekorko nyt (%)', 'Referensränta nu (%)'],
  'f.refRateHelp': ['From your latest loan statement. For a fixed rate, enter the whole rate here and 0 as the margin.', 'Viimeisimmästä lainalaskelmasta. Kiinteässä korossa anna koko korko tähän ja marginaaliksi 0.', 'Från ditt senaste lånebesked. Vid fast ränta: ange hela räntan här och 0 som marginal.'],
  'f.margin': ['Bank margin (%)', 'Pankin marginaali (%)', 'Bankens marginal (%)'],
  'f.years': ['Years left', 'Laina-aikaa jäljellä, vuotta', 'År kvar'],
  'f.payment': ['Monthly payment', 'Kuukausierä', 'Månadsbetalning'],
  'f.paymentHelp': ['Leave empty to calculate it from the years left.', 'Jätä tyhjäksi, niin erä lasketaan jäljellä olevasta laina-ajasta.', 'Lämna tomt för att räkna ut den från åren kvar.'],
  'f.day': ['Payment day of the month', 'Eräpäivä (kuukauden päivä)', 'Betalningsdag i månaden'],
  'f.check': ['Next rate check', 'Seuraava koron tarkistus', 'Nästa räntejustering'],
  'f.needTerm': ['Enter the years left or the monthly payment.', 'Anna jäljellä oleva laina-aika tai kuukausierä.', 'Ange år kvar eller månadsbetalningen.'],
  'f.preview': ['About {amount} a month, paid off in {month}.', 'Noin {amount} kuukaudessa, laina maksettu {month:in}.', 'Cirka {amount} i månaden, betalt i {month}.'],
  'f.save': ['Save my plan', 'Tallenna suunnitelma', 'Spara min plan'],
  // V5 lane MG: example and rich result
  'v5.mg.seeExample': ['See an example', 'Katso esimerkki', 'Se ett exempel'],
  'v5.mg.exampleBadge': ['Example — not your numbers', 'Esimerkki – ei sinun lukujasi', 'Exempel – inte dina siffror'],
  'v5.mg.exampleIntro': ['A typical Finnish home loan: {principal} left, {ref} {refRate} + bank margin {margin}, {years} years left, the same payment every month (annuity).', 'Tyypillinen suomalainen asuntolaina: {principal} jäljellä, {ref} {refRate} + pankin marginaali {margin}, laina-aikaa {years} vuotta, sama erä joka kuukausi (tasaerä).', 'Ett typiskt finskt bolån: {principal} kvar, {ref} {refRate} + bankens marginal {margin}, {years} år kvar, samma betalning varje månad (annuitet).'],
  'v5.mg.exampleSized': ['The example loan is sized so its payment is close to the {amount} you pay for housing each month.', 'Esimerkkilaina on mitoitettu niin, että sen erä on lähellä sitä {amount}, jonka maksat asumisesta kuukaudessa.', 'Exempellånet är anpassat så att betalningen ligger nära de {amount} du betalar för boendet varje månad.'],
  'v5.mg.useOwn': ['Use my own numbers', 'Käytä omia lukujani', 'Använd mina egna siffror'],
  'v5.mg.closeExample': ['Close the example', 'Sulje esimerkki', 'Stäng exemplet'],
  'v5.mg.exampleLoading': ['Calculating the example…', 'Lasketaan esimerkkiä…', 'Räknar ut exemplet…'],
  'v5.mg.exampleError': ['The example could not be calculated right now. Please try again.', 'Esimerkkiä ei voitu laskea juuri nyt. Yritä uudelleen.', 'Exemplet kunde inte räknas ut just nu. Försök igen.'],
  'v5.mg.exampleFooter': ['Example calculation with sample numbers. Your loan statement and your bank have your exact figures.', 'Esimerkkilaskelma malliluvuilla. Tarkat lukusi ovat lainalaskelmassasi ja pankissasi.', 'Exempelberäkning med exempelsiffror. Ditt lånebesked och din bank har dina exakta siffror.'],
  'v5.mg.monthly': ['Monthly payment', 'Kuukausierä', 'Månadsbetalning'],
  'v5.mg.payoff': ['Paid off', 'Laina maksettu', 'Lånet betalt'],
  'v5.mg.timeLeft': ['Time left', 'Aikaa jäljellä', 'Tid kvar'],
  'v5.mg.interestLeft': ['Interest still to pay', 'Korkoa vielä maksettavana', 'Ränta kvar att betala'],
  'v5.mg.totalLeft': ['Total still to pay', 'Maksettavaa yhteensä', 'Totalt kvar att betala'],
  'v5.mg.years': ['{years} years', '{years} vuotta', '{years} år'],
  'v5.mg.oneYear': ['1 year', '1 vuosi', '1 år'],
  'v5.mg.yearsMonths': ['{years} {yearWord} {months} {monthWord}', '{years} v {months} kk', '{years} år {months} mån'],
  'v5.mg.months': ['{months} {monthWord}', '{months} kk', '{months} mån'],
  'v5.mg.summaryExample': ['You would pay {payment} a month for {time}, until {month}. Of the {total} you would pay in all, {interest} is interest.', 'Maksaisit {payment} kuukaudessa {time} (viimeinen erä {month}). Maksaisit yhteensä {total}, josta korkoa on {interest}.', 'Du skulle betala {payment} i månaden i {time} (sista betalningen {month}). Av totalt {total} är {interest} ränta.'],
  'v5.mg.summaryOwn': ['You pay about {payment} a month for {time}, until {month}. Of the {total} still to pay, {interest} is interest.', 'Maksat noin {payment} kuukaudessa {time} (viimeinen erä {month}). Maksettavaa on vielä {total}, josta korkoa on {interest}.', 'Du betalar cirka {payment} i månaden i {time} (sista betalningen {month}). Av de {total} som är kvar att betala är {interest} ränta.'],
  'v5.mg.chartTitle': ['Loan left over time', 'Lainaa jäljellä ajan myötä', 'Kvar på lånet över tid'],
  'v5.mg.chartLabel': ['Loan left from {start} to {end}: falls from {from} to zero.', 'Lainaa jäljellä {start}–{end}: laskee {from} nollaan.', 'Kvar på lånet {start}–{end}: sjunker från {from} till noll.'],
  'v5.mg.chartHint': ['Tap or hover the chart to see any year.', 'Napauta tai osoita kaaviota nähdäksesi minkä tahansa vuoden.', 'Tryck eller peka på diagrammet för att se ett visst år.'],
  'v5.mg.tipLeft': ['{amount} left', '{amount} jäljellä', '{amount} kvar'],
  'v5.mg.legendExtra': ['With +{extra} a month', '+{extra} kuukaudessa', 'Med +{extra} i månaden'],
  'v5.mg.legendPlanPaid': ['As planned · paid off {year}', 'Nykyisellä erällä · maksettu {year}', 'Som planerat · betalt {year}'],
  'v5.mg.legendExtraPaid': ['With +{extra} a month · paid off {year}', '+{extra} kuukaudessa · maksettu {year}', 'Med +{extra} i månaden · betalt {year}'],
  'v5.mg.splitTitle': ['Where your payments go', 'Mihin erät menevät', 'Vart betalningarna går'],
  'v5.mg.firstYear': ['First year', 'Ensimmäinen vuosi', 'Första året'],
  'v5.mg.lastYear': ['Last year', 'Viimeinen vuosi', 'Sista året'],
  'v5.mg.principalPart': ['Pays off the loan', 'Lyhennys', 'Amortering'],
  'v5.mg.interestPart': ['Interest', 'Korko', 'Ränta'],
  'v5.mg.splitSentence': ['In the first year {first} of what you pay is interest; in the last year only {last}.', 'Ensimmäisenä vuonna maksamastasi summasta {first} on korkoa, viimeisenä vuonna vain {last}.', 'Första året går {first} av det du betalar till ränta, sista året bara {last}.'],
  'v5.mg.extraOption': ['{time} sooner · {saved} less interest', '{time} aiemmin · {saved} vähemmän korkoa', '{time} tidigare · {saved} mindre ränta'],
  'v5.mg.extraPaid': ['Paid off in {month}', 'Maksettu {month:in}', 'Betalt i {month}'],
  'v5.mg.extraAmount': ['+{amount} a month', '+{amount} kuukaudessa', '+{amount} i månaden'],
  'v5.mg.extraHint': ['Tap an option to see it on the chart.', 'Napauta vaihtoehtoa, niin näet sen kaaviossa.', 'Tryck på ett alternativ för att se det i diagrammet.'],
  'v5.mg.rateUp': ['If the rate rises by 1 percentage point', 'Jos korko nousee 1 prosenttiyksiköllä', 'Om räntan stiger med 1 procentenhet'],
  'v5.mg.rateDown': ['If the rate falls by 1 percentage point', 'Jos korko laskee 1 prosenttiyksiköllä', 'Om räntan sjunker med 1 procentenhet'],
  'v5.mg.rateChange': ['{change} · rate {rate}', '{change} · korko {rate}', '{change} · ränta {rate}'],
  'v5.mg.rateTerm': ['Same payment · paid off in {time}', 'Sama erä · maksettu {time} kuluessa', 'Samma betalning · betalt på {time}'],
  // V5 fix lane GL: what-if feedback next to the options, the chart's "today" tick and the table hint
  'v5.mg.extraNote': ['With +{extra} a month the loan is paid off in {month}, {time} sooner. The dashed line on the chart shows it.', 'Kun lyhennät {extra} enemmän kuukaudessa, laina on maksettu {month:in}, {time} aiemmin. Kaavion katkoviiva näyttää sen.', 'Med {extra} extra i månaden är lånet betalt i {month}, {time} tidigare. Den streckade linjen i diagrammet visar det.'],
  'v5.mg.seeChart': ['See it on the chart', 'Katso kaaviosta', 'Se det i diagrammet'],
  'v5.mg.now': ['Now', 'Nyt', 'Nu'],
  'v5.mg.yearTable': ['Year by year', 'Vuosi vuodelta', 'År för år'],
  'v5.mg.colYear': ['Year', 'Vuosi', 'År'],
  'v5.mg.colPaid': ['Paid', 'Maksettu', 'Betalt'],
  'v5.mg.colInterest': ['Of which interest', 'Josta korkoa', 'Varav ränta'],
  'v5.mg.colLeft': ['Left at year end', 'Jäljellä vuoden lopussa', 'Kvar vid årets slut'],
};

const lang = locale => (LOCALES.includes(String(locale).slice(0, 2)) ? String(locale).slice(0, 2) : 'en');
const INTL = {en: 'en-IE', fi: 'fi-FI', sv: 'sv-FI'};
export const MORTGAGE_COPY = COPY;
export const MORTGAGE_COPY_KEYS = Object.freeze(Object.keys(COPY));
// Template filters: {month:in} puts a Finnish month or year in the inessive ("maaliskuussa 2047"); {day:ord} writes
// a day of the month as an ordinal (en "5th", sv "5:e"; Finnish templates write "{day}." themselves).
function inessive(text) {
  const month = /^(\S*kuu)(\s+\d{4})?$/i.exec(text);
  if (month) return month[1] + 'ssa' + (month[2] || '');
  return /^\d{4}$/.test(text) ? 'vuonna ' + text : text;
}
export function ordinalDay(day, locale) {
  const n = Number(day);
  if (!Number.isInteger(n)) return String(day ?? '');
  const l = lang(locale);
  if (l === 'sv') return n + ((n % 10 === 1 || n % 10 === 2) && n % 100 !== 11 && n % 100 !== 12 ? ':a' : ':e');
  if (l === 'fi') return n + '.';
  const tail = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({1: 'st', 2: 'nd', 3: 'rd'}[n % 10] || 'th');
  return n + tail;
}
export function mortgageText(locale, key, values = {}) {
  const row = COPY[key];
  const text = row ? row[LOCALES.indexOf(lang(locale))] || row[0] : key;
  return text.replace(/\{(\w+)(?::(in|ord))?\}/g, (_, name, filter) => {
    if (values[name] === undefined) return '{' + name + '}';
    if (filter === 'in') return lang(locale) === 'fi' ? inessive(String(values[name])) : String(values[name]);
    if (filter === 'ord') return ordinalDay(values[name], locale);
    return String(values[name]);
  });
}

/** Percentage from basis points in the customer's language: en '2.85%', fi/sv '2,85 %'. */
export function formatRate(bp, locale) {
  const value = (Number(bp) || 0) / 100;
  const text = value.toFixed(2).replace(/0$/, '').replace(/\.0$/, '');
  return lang(locale) === 'en' ? text + '%' : text.replace('.', ',') + ' %';
}

/** Whole euros (large totals): en '€243,694', fi/sv '243 694 €'. */
export function wholeEuros(cents, locale) {
  return new Intl.NumberFormat(INTL[lang(locale)], {style: 'currency', currency: 'EUR', maximumFractionDigits: 0}).format(Math.round((Number(cents) || 0) / 100));
}
/** Short chart label: en '€180k'; fi/sv write the full amount '180 000 €' (no 't.' / 'tn'). */
export function compactEuros(cents, locale) {
  if (lang(locale) !== 'en') return new Intl.NumberFormat(INTL[lang(locale)], {style: 'currency', currency: 'EUR', maximumFractionDigits: 0}).format(Math.round((Number(cents) || 0) / 100));
  const text = new Intl.NumberFormat(INTL[lang(locale)], {style: 'currency', currency: 'EUR', notation: 'compact', maximumFractionDigits: 0}).format(Math.round((Number(cents) || 0) / 100));
  return lang(locale) === 'en' ? text.replace(/K$/, 'k') : text;
}
/** A length of time in months, in plain words: '22 years', '21 y 4 mo', '18 months'. */
export function formatTerm(months, locale) {
  const m = Math.max(0, Math.round(Number(months) || 0));
  const years = Math.floor(m / 12), rest = m % 12;
  const words = {yearWord: years === 1 ? 'year' : 'years', monthWord: rest === 1 ? 'month' : 'months'};
  if (!years) return mortgageText(locale, 'v5.mg.months', {months: rest, ...words});
  if (!rest) return years === 1 ? mortgageText(locale, 'v5.mg.oneYear') : mortgageText(locale, 'v5.mg.years', {years});
  return mortgageText(locale, 'v5.mg.yearsMonths', {years, months: rest, ...words});
}
const percent = (part, whole, locale) => {
  const value = whole > 0 ? Math.round(part / whole * 100) : 0;
  return lang(locale) === 'en' ? value + '%' : value + ' %';
};

/** Monthly annuity payment (cents, rounded up) — only for the live form preview; the server is the source. */
export function annuityPayment(principal, rateBp, months) {
  if (!(principal > 0) || !(months >= 1)) return null;
  const r = rateBp / 10000 / 12;
  if (r === 0) return Math.ceil(principal / months);
  const f = Math.pow(1 + r, months);
  return Math.ceil(principal * r * f / (f - 1));
}

const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const EXTRA_STEPS = [5000, 10000, 20000];

/** Form spec for the mortgage plan (draft-card.js). Rates are percent numbers in the form, basis points on the server. */
export function mortgageSpec(locale, {value = null, prefill = null} = {}) {
  const t = key => mortgageText(locale, key);
  const v = value || {};
  // Editing a saved plan starts from the saved numbers only: a cleared payment must stay cleared (the detected
  // housing payment is a starting point for a new plan, never refilled into an existing one).
  if (value) prefill = null;
  const pct = bp => (Number.isInteger(bp) ? bp / 100 : '');
  return {id: 'plan-mortgage', kind: 'plan', title: t('f.mTitle'), intro: t('f.mIntro'), saveLabel: t('f.save'), mode: 'edit', fields: [
    {name: 'principal_cents', label: t('f.principal'), type: 'amount', value: v.principal_cents ?? prefill?.principal_cents ?? '', required: true, min: 100},
    {name: 'loan_type', label: t('f.type'), type: 'select', value: v.loan_type || 'annuity', required: true,
      options: [{value: 'annuity', label: t('f.annuity')}, {value: 'equal_principal', label: t('f.equal')}]},
    {name: 'reference_rate', label: t('f.ref'), type: 'select', value: v.reference_rate || 'euribor_12m', required: true,
      options: ['euribor_12m', 'euribor_6m', 'euribor_3m', 'fixed', 'other'].map(key => ({value: key, label: t('f.' + key)}))},
    {name: 'reference_rate_pct', label: t('f.refRate'), type: 'percent', value: pct(v.reference_rate_bp), required: true, min: -10, max: 20, help: t('f.refRateHelp')},
    {name: 'margin_pct', label: t('f.margin'), type: 'percent', value: pct(v.margin_bp), required: true, min: 0, max: 20},
    {name: 'remaining_years', label: t('f.years'), type: 'number', value: Number.isInteger(v.remaining_months) ? Math.round(v.remaining_months / 12 * 10) / 10 : '', min: 0.1, max: 50},
    {name: 'monthly_payment_cents', label: t('f.payment'), type: 'amount', value: v.monthly_payment_cents ?? prefill?.monthly_payment_cents ?? '', min: 100, help: t('f.paymentHelp')},
    {name: 'payment_day', label: t('f.day'), type: 'number', value: v.payment_day ?? prefill?.payment_day ?? '', min: 1, max: 31},
    {name: 'next_rate_check', label: t('f.check'), type: 'month', value: v.next_rate_check || ''},
  ]};
}

/** Form values -> plan_mortgage value. Returns {value} or {error}. */
export function mortgageValue(values) {
  const months = Number.isFinite(values.remaining_years) && values.remaining_years > 0 ? Math.round(values.remaining_years * 12) : null;
  const payment = Number.isSafeInteger(values.monthly_payment_cents) && values.monthly_payment_cents > 0 ? values.monthly_payment_cents : null;
  if (!months && !payment) return {error: 'f.needTerm'};
  if (values.loan_type === 'equal_principal' && !months) return {error: 'f.needTerm'};
  const value = {principal_cents: values.principal_cents, loan_type: values.loan_type, reference_rate: values.reference_rate,
    reference_rate_bp: Math.round((values.reference_rate_pct || 0) * 100), margin_bp: Math.round((values.margin_pct || 0) * 100)};
  if (months) value.remaining_months = months;
  if (payment) value.monthly_payment_cents = payment;
  if (Number.isInteger(values.payment_day)) value.payment_day = values.payment_day;
  if (values.next_rate_check) value.next_rate_check = values.next_rate_check;
  return {value};
}

// ---------------------------------------------------------------- chart (pure HTML + SVG string)

// The SVG holds only the lines and the area (stretched to the box, strokes stay 2px); labels, dots,
// the crosshair and the tooltip are HTML placed by percentages, so text is never distorted at any width.
const CHART = {w: 100, h: 100, top: 14, bottom: 4};
const pct = value => value.toFixed(2) + '%';

/**
 * Loan balance over time: the plan as a green line over a light area, and (optionally) the chosen
 * extra-payment what-if as a dashed blue line. Points come from the server's balance_curve.
 * Carries the data for the tooltip in data-points (JSON), so the hover layer needs no extra request.
 */
export function balanceChartSVG(curve, extraCurve, h, {extraCents = 0} = {}) {
  const {locale} = h;
  const t = (key, values) => mortgageText(locale, key, values);
  if (!Array.isArray(curve) || curve.length < 2) return '';
  const maxN = curve[curve.length - 1].n || 1;
  const top = curve[0].balance_cents || 1;
  const innerH = CHART.h - CHART.top - CHART.bottom;
  const x = n => CHART.w * (n / maxN);
  const y = cents => CHART.top + innerH * (1 - cents / top);
  const path = points => points.map((p, i) => (i ? 'L' : 'M') + x(p.n).toFixed(2) + ' ' + y(p.balance_cents).toFixed(2)).join(' ');
  const base = CHART.top + innerH;
  const area = path(curve) + ` L${x(maxN).toFixed(2)} ${base} L0 ${base} Z`;
  const year = month => String(month || '').slice(0, 4);
  const hasExtra = Array.isArray(extraCurve) && extraCurve.length > 1;
  const extraEnd = hasExtra ? extraCurve[extraCurve.length - 1] : null;
  const grid = [top, Math.round(top / 2)].map(v => `<line class="mg-grid" x1="0" x2="100" y1="${y(v).toFixed(2)}" y2="${y(v).toFixed(2)}"/>`).join('');
  const yLabels = [top, Math.round(top / 2)].map(v => `<span class="mg-ylab" style="top:${pct(y(v))}">${escape(compactEuros(v, locale))}</span>`).join('');
  const dots = `<span class="mg-pt" style="left:100%;top:${pct(base)}"></span>`
    + (hasExtra ? `<span class="mg-pt mg-pt-extra" style="left:${pct(x(extraEnd.n))};top:${pct(base)}"></span>` : '');
  const data = curve.map(p => {
    const match = hasExtra ? extraCurve.find(q => q.n === p.n) || (p.n > extraEnd.n ? {balance_cents: 0} : null) : null;
    return {n: p.n, m: p.month, b: p.balance_cents, e: match ? match.balance_cents : null};
  });
  // x axis: the first and last year plus round years in between (every 1, 2, 5 or 10 years, by length), with a faint
  // vertical guide for each, so a 22-year loan reads 2026 · 2030 · 2035 · 2040 · 2045 · 2048 instead of two labels.
  const [startY, startM] = String(curve[0].month || '').split('-').map(Number);
  const endY = Number(year(curve[curve.length - 1].month));
  const span = endY - startY;
  const step = span <= 6 ? 1 : span <= 12 ? 2 : span <= 30 ? 5 : 10;
  const ticks = [];
  if (Number.isInteger(startY) && Number.isInteger(endY)) {
    for (let y = Math.ceil((startY + 1) / step) * step; y < endY; y += step) {
      const pos = x((y - startY) * 12 - ((startM || 1) - 1));
      if (pos >= 12 && pos <= 88) ticks.push({y, pos});
    }
  }
  const vgrid = ticks.map(tick => `<line class="mg-vgrid" x1="${tick.pos.toFixed(2)}" x2="${tick.pos.toFixed(2)}" y1="${CHART.top}" y2="${base}"/>`).join('');
  const xaxis = `<span class="mg-xtick mg-xtick--start">${escape(year(curve[0].month))}</span>`
    + ticks.map(tick => `<span class="mg-xtick" style="left:${pct(tick.pos)}">${tick.y}</span>`).join('')
    + `<span class="mg-xtick mg-xtick--end">${escape(year(curve[curve.length - 1].month))}</span>`;
  const label = t('v5.mg.chartLabel', {start: year(curve[0].month), end: year(curve[curve.length - 1].month), from: wholeEuros(top, locale)});
  const legend = hasExtra ? `<div class="mg-legend"><span><i class="mg-key mg-key-plan"></i>${escape(t('v5.mg.legendPlanPaid', {year: year(curve[curve.length - 1].month)}))}</span><span><i class="mg-key mg-key-extra"></i>${escape(t('v5.mg.legendExtraPaid', {extra: wholeEuros(extraCents, locale), year: year(extraEnd.month)}))}</span></div>` : '';
  return `<figure class="mg-chart" tabindex="0" role="img" aria-label="${escape(label)}" data-mg-chart data-points="${escape(JSON.stringify(data))}" data-max-n="${maxN}" data-top="${top}" data-extra="${escape(extraCents ? wholeEuros(extraCents, locale) : '')}">`
    + `<div class="mg-plot"><svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" focusable="false">${grid}<line class="mg-base" x1="0" x2="100" y1="${base}" y2="${base}"/>`
    + `${vgrid}<path class="mg-area" d="${area}"/><path class="mg-line" d="${path(curve)}"/>${hasExtra ? `<path class="mg-line-extra" d="${path(extraCurve)}"/>` : ''}</svg>`
    + `${yLabels}${dots}<span class="mg-cross" hidden></span><span class="mg-pt mg-pt-hover" hidden></span></div>`
    + `<div class="mg-xaxis" aria-hidden="true">${xaxis}</div>`
    // The read-out: floats beside the crosshair for a mouse; on touch it sits under the axis (never over the line),
    // and while idle it shows the hint. Light card, like the Spending charts.
    + `<div class="mg-tip is-idle" role="status" aria-live="polite"><span class="mg-tip-hint">${escape(t('v5.mg.chartHint'))}</span></div></figure>${legend}`;
}

/** Hover / tap / arrow-key layer for every balance chart under root. Safe to call after every paint. */
export function bindMortgageCharts(root, h) {
  if (!root?.querySelectorAll) return;
  for (const figure of root.querySelectorAll('[data-mg-chart]')) {
    if (figure.dataset.bound) continue;
    figure.dataset.bound = '1';
    let points;
    try { points = JSON.parse(figure.dataset.points || '[]'); } catch { points = []; }
    if (!points.length) continue;
    const maxN = Number(figure.dataset.maxN) || 1, top = Number(figure.dataset.top) || 1;
    const innerH = CHART.h - CHART.top - CHART.bottom;
    const plot = figure.querySelector('.mg-plot');
    const cross = figure.querySelector('.mg-cross'), dot = figure.querySelector('.mg-pt-hover'), tip = figure.querySelector('.mg-tip');
    let index = -1;
    const show = i => {
      index = Math.max(0, Math.min(points.length - 1, i));
      const p = points[index];
      const px = 100 * p.n / maxN, py = CHART.top + innerH * (1 - p.b / top);
      cross.style.left = pct(px); cross.hidden = false;
      dot.style.left = pct(px); dot.style.top = pct(py); dot.hidden = false;
      const lines = [`<strong>${escape(mortgageText(h.locale, 'v5.mg.tipLeft', {amount: wholeEuros(p.b, h.locale)}))}</strong>`, `<span>${escape(h.monthLabel(p.m))}</span>`];
      if (p.e !== null && p.e !== undefined) lines.push(`<span class="mg-tip-extra">${escape(mortgageText(h.locale, 'v5.mg.legendExtra', {extra: figure.dataset.extra}))}: ${escape(wholeEuros(p.e, h.locale))}</span>`);
      if (!figure.dataset.hint) figure.dataset.hint = tip.innerHTML;
      tip.innerHTML = lines.join('');
      tip.classList.remove('is-idle');
      figure.classList.add('is-active');
      const width = plot.getBoundingClientRect().width;
      const centre = width * px / 100;
      // Keep the tooltip inside the plot, on the side away from the point when there is room.
      const left = centre > width / 2 ? centre - tip.offsetWidth - 12 : centre + 12;
      tip.style.left = getComputedStyle(tip).position === 'absolute' ? Math.max(0, Math.min(width - tip.offsetWidth, left)) + 'px' : '';
    };
    const hide = () => {
      index = -1; cross.hidden = true; dot.hidden = true; figure.classList.remove('is-active');
      if (figure.dataset.hint) tip.innerHTML = figure.dataset.hint;
      tip.classList.add('is-idle'); tip.style.left = '';
    };
    // x labels: drop a middle year that would touch its neighbour (narrow phones), keeping the first and the last.
    const fitTicks = () => {
      const labels = [...figure.querySelectorAll('.mg-xtick')];
      if (labels.length < 3) return;
      labels.forEach(label => { label.style.visibility = ''; });
      const end = labels[labels.length - 1].getBoundingClientRect();
      let right = labels[0].getBoundingClientRect().right;
      for (const label of labels.slice(1, -1)) {
        const box = label.getBoundingClientRect();
        if (box.left < right + 8 || box.right > end.left - 8) label.style.visibility = 'hidden';
        else right = box.right;
      }
    };
    fitTicks();
    if (globalThis.ResizeObserver) new ResizeObserver(fitTicks).observe(figure);
    const nearest = event => {
      const box = plot.getBoundingClientRect();
      const n = (event.clientX - box.left) / box.width * maxN;
      let best = 0;
      points.forEach((p, i) => { if (Math.abs(p.n - n) < Math.abs(points[best].n - n)) best = i; });
      return best;
    };
    figure.addEventListener('pointermove', event => show(nearest(event)));
    figure.addEventListener('pointerdown', event => show(nearest(event)));
    figure.addEventListener('pointerleave', event => { if (event.pointerType === 'mouse') hide(); });
    figure.addEventListener('blur', hide);
    figure.addEventListener('keydown', event => {
      if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); show((index < 0 ? 0 : index) + (event.key === 'ArrowRight' ? 1 : -1)); }
      else if (event.key === 'Escape') hide();
    });
  }
}

// ---------------------------------------------------------------- rendering (pure)

function row(label, value) { return `<div class="plan-row"><dt>${escape(label)}</dt><dd>${escape(value)}</dd></div>`; }

// V5 fix lane GL: one card pattern for the mortgage and the tax plan (plans-tax.js imports these).
// Head: title + On/Off pill, and in an example the "Example — not your numbers" badge under it.
// Off card: the benefit, one info block, then "Turn on" (compact, centred) and "See an example ›" pinned to the bottom.
// Example: replaces the card body; "Use my own numbers ›" and "Close the example" at the bottom, one close control.
export function planHead(title, pill, on, badge = '') {
  return `<div class="plan-head"><h3>${escape(title)}</h3><span class="plan-pill${on ? '' : ' plan-pill--off'}">${escape(pill)}</span></div>`
    + (badge ? `<p class="mg-badge plan-badge">${escape(badge)}</p>` : '');
}
export function offActions(plan, turnOn, seeExample, exampleAttr) {
  return `<div class="plan-actions plan-off-actions"><button type="button" class="secondary-button plan-turn-on" data-plan-on="${escape(plan)}">${escape(turnOn)}</button>`
    + `<button type="button" class="text-button plan-see-example" ${exampleAttr} aria-expanded="false">${escape(seeExample)}<span class="plan-chevron" aria-hidden="true">›</span></button></div>`;
}
export function exampleActions(plan, useOwn, close) {
  const own = plan === 'tax' ? 'data-plan-tax-own' : `data-plan-own="${escape(plan)}"`;
  const closeAttr = plan === 'tax' ? 'data-plan-tax-example-close' : `data-plan-example-close="${escape(plan)}"`;
  return `<div class="plan-actions plan-example-actions"><button type="button" class="primary-button plan-use-own" ${own}>${escape(useOwn)} <span aria-hidden="true">›</span></button>`
    + `<button type="button" class="text-button" ${closeAttr}>${escape(close)}</button></div>`;
}

function splitBar(label, part, locale) {
  if (!part || !(part.paid_cents > 0)) return '';
  const interest = Math.round(part.interest_cents / part.paid_cents * 1000) / 10;
  const t = key => mortgageText(locale, key);
  return `<div class="mg-split-row"><div class="mg-split-head"><span>${escape(label)}</span><span>${escape(wholeEuros(part.paid_cents, locale))}</span></div>`
    + `<div class="mg-split-bar" aria-hidden="true"><span class="mg-seg-principal" style="width:${(100 - interest).toFixed(1)}%"></span><span class="mg-seg-interest" style="width:${interest.toFixed(1)}%"></span></div>`
    + `<div class="mg-split-values"><span><i class="mg-key mg-key-plan"></i>${escape(t('v5.mg.principalPart'))} ${escape(wholeEuros(part.principal_cents, locale))}</span><span><i class="mg-key mg-key-interest"></i>${escape(t('v5.mg.interestPart'))} ${escape(wholeEuros(part.interest_cents, locale))}</span></div></div>`;
}

function yearTable(p, h) {
  const t = key => mortgageText(h.locale, key);
  const years = p.yearly || [];
  if (!years.length) return '';
  return `<details class="mg-years"><summary>${escape(t('v5.mg.yearTable'))}</summary><div class="mg-table-wrap"><table><thead><tr><th scope="col">${escape(t('v5.mg.colYear'))}</th><th scope="col" class="mg-col-paid">${escape(t('v5.mg.colPaid'))}</th><th scope="col">${escape(t('v5.mg.colInterest'))}</th><th scope="col">${escape(t('v5.mg.colLeft'))}</th></tr></thead><tbody>`
    + years.map(item => `<tr><th scope="row">${item.year}</th><td class="mg-col-paid">${escape(wholeEuros(item.interest_cents + item.principal_cents, h.locale))}</td><td>${escape(wholeEuros(item.interest_cents, h.locale))}</td><td>${escape(wholeEuros(item.end_balance_cents, h.locale))}</td></tr>`).join('')
    + '</tbody></table></div></details>';
}

/**
 * The rich result shared by the example and the saved plan: hero payment, four facts, a plain summary,
 * the balance chart, the principal-vs-interest split, what-ifs (extra a month; rate ±1 %-point) and the year table.
 * ui: {extra (cents chosen), rate (legacy chip)}; opts: {example: bool}.
 */
export function renderMortgageResult(p, ui, h, {example = false} = {}) {
  const {locale, money, monthLabel} = h;
  const t = (key, values) => mortgageText(locale, key, values);
  const months = p.months_left;
  const term = formatTerm(months, locale);
  const totalPaid = p.total_paid_cents ?? ((p.inputs?.principal_cents || 0) + (p.total_interest_cents || 0));
  const summary = t(example ? 'v5.mg.summaryExample' : 'v5.mg.summaryOwn', {payment: money(p.monthly_payment_cents), time: term,
    month: monthLabel(p.payoff_month), total: wholeEuros(totalPaid, locale), interest: wholeEuros(p.total_interest_cents, locale)});
  const facts = `<dl class="mg-facts">`
    + `<div><dt>${escape(t('v5.mg.payoff'))}</dt><dd>${escape(monthLabel(p.payoff_month))}</dd></div>`
    + (Number.isInteger(months) ? `<div><dt>${escape(t('v5.mg.timeLeft'))}</dt><dd>${escape(term)}</dd></div>` : '')
    + `<div><dt>${escape(t('v5.mg.interestLeft'))}</dt><dd>${escape(wholeEuros(p.total_interest_cents, locale))}</dd></div>`
    + `<div><dt>${escape(t('v5.mg.totalLeft'))}</dt><dd>${escape(wholeEuros(totalPaid, locale))}</dd></div></dl>`;
  const options = Array.isArray(p.extra_options) ? p.extra_options : null;
  const advice = p.extra_advice || {};
  const chosen = ui.extra || 0;
  const chosenOption = options ? options.find(o => o.extra_cents === chosen) : null;
  const chart = Array.isArray(p.balance_curve) && p.balance_curve.length > 1
    ? `<section class="mg-block"><h4>${escape(t('v5.mg.chartTitle'))}</h4>${balanceChartSVG(p.balance_curve, chosenOption?.balance_curve, h, {extraCents: chosenOption ? chosen : 0})}</section>` : '';
  const s = p.split;
  const split = s?.first_year ? `<section class="mg-block"><h4>${escape(t('v5.mg.splitTitle'))}</h4>${splitBar(t('v5.mg.firstYear'), s.first_year, locale)}${splitBar(t('v5.mg.lastYear'), s.last_year, locale)}`
    + (s.last_year ? `<p class="mg-sentence">${escape(t('v5.mg.splitSentence', {first: percent(s.first_year.interest_cents, s.first_year.paid_cents, locale), last: percent(s.last_year.interest_cents, s.last_year.paid_cents, locale)}))}</p>` : '') + '</section>' : '';
  let extra;
  if (advice.reason === 'steady') extra = `<p class="plan-note">${escape(t('m.steady'))}</p>`;
  else if (options && options.length) {
    extra = `<section class="mg-block plan-whatif"><h4>${escape(t('m.extraTitle'))}</h4>${advice.reason === 'buffer_thin' ? `<p class="plan-note">${escape(t('m.thin'))}</p>` : ''}<div class="mg-options" role="group">`
      + options.map(o => `<button type="button" class="mg-option" data-plan-extra="${o.extra_cents}" aria-pressed="${chosen === o.extra_cents}"><span class="mg-option-amount">${escape(t('v5.mg.extraAmount', {amount: wholeEuros(o.extra_cents, locale)}))}</span><span class="mg-option-result">${escape(t('v5.mg.extraOption', {time: formatTerm(o.months_saved, locale), saved: wholeEuros(o.interest_saved_cents, locale)}))}</span><span class="mg-option-when">${escape(t('v5.mg.extraPaid', {month: monthLabel(o.payoff_month)}))}</span></button>`).join('')
      + `</div>${chosenOption
        ? `<p class="mg-extra-note" role="status">${escape(t('v5.mg.extraNote', {extra: wholeEuros(chosen, locale), month: monthLabel(chosenOption.payoff_month), time: formatTerm(chosenOption.months_saved, locale)}))} <button type="button" class="text-button mg-see-chart" data-plan-see-chart>${escape(t('v5.mg.seeChart'))} ↑</button></p>`
        : `<p class="mg-hint">${escape(t('v5.mg.extraHint'))}</p>`}</section>`;
  } else {
    // Older server shape: one what-if at a time, fetched per chip.
    const w = p.what_if;
    extra = `<div class="plan-whatif"><h4>${escape(t('m.extraTitle'))}</h4>${advice.reason === 'buffer_thin' ? `<p class="plan-note">${escape(t('m.thin'))}</p>` : ''}<div class="plan-chips" role="group">${EXTRA_STEPS.map(step => `<button type="button" class="plan-chip" data-plan-extra="${step}" aria-pressed="${chosen === step}">+${escape(money(step))}</button>`).join('')}</div>${w && w.extra_cents === chosen ? `<p class="plan-result" aria-live="polite">${escape(t('m.extraResult', {extra: money(w.extra_cents), month: monthLabel(w.payoff_month), months: w.months_saved, saved: money(w.interest_saved_cents)}))}</p>` : ''}</div>`;
  }
  const sign = cents => (cents > 0 ? '+' : cents < 0 ? '−' : '±') + money(Math.abs(cents));
  const fixedPayment = p.inputs?.remaining_months == null && p.inputs?.monthly_payment_cents != null;
  const rateTile = (key, item) => item ? `<div class="mg-rate"><p class="mg-rate-label">${escape(t(key))}</p>`
    + (fixedPayment && item.payment_change_cents === 0
      ? `<p class="mg-rate-value">${escape(money(item.monthly_payment_cents))}</p><p class="mg-rate-change">${escape(t('v5.mg.rateTerm', {time: formatTerm(item.months_left, locale)}))}</p>`
      : `<p class="mg-rate-value">${escape(money(item.monthly_payment_cents))} <span>${escape(t('perMonth'))}</span></p><p class="mg-rate-change">${escape(t('v5.mg.rateChange', {change: sign(item.payment_change_cents), rate: formatRate(item.rate_bp, locale).replace(' ', '\u00a0')}))}</p>`)
    + '</div>' : '';
  const rc = p.rate_change || {};
  const rates = (rc.up || rc.down) ? `<section class="mg-block"><h4>${escape(t('m.rateTitle'))}</h4><div class="mg-rates">${rateTile('v5.mg.rateUp', rc.up)}${rateTile('v5.mg.rateDown', rc.down)}</div></section>` : '';
  return `<div class="mg-result"><div class="mg-col"><p class="mg-label">${escape(t('v5.mg.monthly'))}</p><p class="plan-amount">${escape(money(p.monthly_payment_cents))} <span>${escape(t('perMonth'))}</span></p>`
    + (example ? '' : `<p class="plan-sub">${escape(t('heldBack'))} · ${escape(t('estimate'))}</p>`)
    + facts + `<p class="mg-summary">${escape(summary)}</p>` + chart + `</div><div class="mg-col">` + split + extra + rates + '</div></div>' + yearTable(p, h);
}

function exampleIntro(data, h) {
  const {locale, money} = h;
  const t = (key, values) => mortgageText(locale, key, values);
  const i = data.projection?.inputs || {};
  if (data.basis === 'detected_payment' && data.prefill?.monthly_payment_cents) {
    return t('v5.mg.exampleSized', {amount: money(data.prefill.monthly_payment_cents)}) + ' '
      + t('v5.mg.exampleIntro', {principal: wholeEuros(i.principal_cents, locale), ref: t('f.' + (i.reference_rate || 'euribor_12m')), refRate: formatRate(i.reference_rate_bp, locale).replace(' ', '\u00a0'), margin: formatRate(i.margin_bp, locale).replace(' ', '\u00a0'), years: Math.round((i.remaining_months || 0) / 12)});
  }
  return t('v5.mg.exampleIntro', {principal: wholeEuros(i.principal_cents, locale), ref: t('f.' + (i.reference_rate || 'euribor_12m')), refRate: formatRate(i.reference_rate_bp, locale).replace(' ', '\u00a0'), margin: formatRate(i.margin_bp, locale).replace(' ', '\u00a0'), years: Math.round((i.remaining_months || 0) / 12)});
}

/** The read-only example card body (inside the off card). example: {loading, error, data}. */
export function renderMortgageExample(example, ui, h) {
  const t = key => mortgageText(h.locale, key);
  const close = `<div class="plan-actions plan-example-actions"><button type="button" class="text-button" data-plan-example-close="mortgage">${escape(t('v5.mg.closeExample'))}</button></div>`;
  if (!example || example.loading) return `<p class="mg-status" role="status">${escape(t('v5.mg.exampleLoading'))}</p>`;
  if (example.error || !example.data?.projection) return `<p class="mg-status" role="status">${escape(t('v5.mg.exampleError'))}</p>${close}`;
  return `<div class="mg-example" data-mg-example><p class="mg-intro">${escape(exampleIntro(example.data, h))}</p>`
    + renderMortgageResult(example.data.projection, ui, h, {example: true})
    + `<p class="small-text">${escape(t('v5.mg.exampleFooter'))}</p>${exampleActions('mortgage', t('v5.mg.useOwn'), t('v5.mg.closeExample'))}</div>`;
}

export function renderMortgageCard(data, ui, h) {
  const {locale, money, monthLabel} = h;
  const t = (key, values) => mortgageText(locale, key, values);
  if (!data?.on) {
    const pre = data?.prefill;
    const detected = pre?.found && pre.source !== 'profile' && Number.isInteger(pre.monthly_payment_cents) && pre.payment_day
      ? `<p class="plan-detected">${escape(t('m.detected', {amount: money(pre.monthly_payment_cents), day: pre.payment_day}))}</p>` : '';
    if (ui?.example) {
      return `<article class="plan-card plan-card--example plan-card--wide" data-plan="mortgage">${planHead(t('m.title'), t('off'), false, t('v5.mg.exampleBadge'))}${renderMortgageExample(ui.example, ui, h)}</article>`;
    }
    return `<article class="plan-card plan-card--off" data-plan="mortgage">${planHead(t('m.title'), t('off'), false)}<p class="plan-benefit">${escape(t('m.benefit'))}</p>${detected}`
      + `${offActions('mortgage', t('turnOn'), t('v5.mg.seeExample'), 'data-plan-example="mortgage"')}</article>`;
  }
  const p = data.projection;
  const actions = `<div class="plan-actions"><button type="button" class="text-button" data-plan-edit="mortgage">${escape(t('change'))}</button><button type="button" class="text-button" data-plan-off="mortgage">${escape(t('turnOff'))}</button></div>`;
  if (!p) return `<article class="plan-card plan-card--on plan-card--wide" data-plan="mortgage">${planHead(t('m.title'), t('on'), true)}<p>${escape(t('m.error'))}</p>${actions}</article>`;
  const inputs = p.inputs || {};
  const rateDetail = inputs.reference_rate === 'fixed' ? t('m.rateFixed')
    : t('m.rateParts', {ref: t('f.' + inputs.reference_rate), refRate: formatRate(inputs.reference_rate_bp, locale), margin: formatRate(inputs.margin_bp, locale)});
  const notes = [];
  if ((p.notes || []).includes('payment_falls')) notes.push(t('m.falls'));
  if ((p.notes || []).includes('payment_differs')) notes.push(t('m.differs', {amount: money(p.calculated_payment_cents)}));
  const details = `<dl class="plan-rows">${row(t('m.rate'), formatRate(p.rate_bp, locale))}${p.next_rate_check ? row(t('m.rateCheck'), monthLabel(p.next_rate_check)) : ''}</dl><p class="small-text plan-rate-detail">${escape(rateDetail)}</p>`;
  return `<article class="plan-card plan-card--on plan-card--wide" data-plan="mortgage">${planHead(t('m.title'), t('on'), true)}`
    + renderMortgageResult(p, ui || {}, h) + details + notes.map(note => `<p class="plan-note">${escape(note)}</p>`).join('')
    + `<p class="small-text">${escape(t('m.footer'))}</p>${actions}</article>`;
}

/** Live form preview line for the draft form (annuity only). */
export function mortgageFormPreview(values, locale, {money, monthLabel, referenceDate}) {
  const converted = mortgageValue(values);
  if (!(converted.value && converted.value.remaining_months && converted.value.loan_type === 'annuity')) return '';
  const pay = annuityPayment(converted.value.principal_cents, converted.value.reference_rate_bp + converted.value.margin_bp, converted.value.remaining_months);
  const end = referenceDate ? addMonths(referenceDate.slice(0, 7), converted.value.remaining_months) : null;
  return pay && end ? mortgageText(locale, 'f.preview', {amount: money(pay), month: monthLabel(end)}) : '';
}

/** Read-only example loader: GET /api/plans/mortgage/preview with no loan numbers (computes, never saves). */
export async function loadMortgageExample(request, context, params = {}) {
  return request(context, 'get', '/api/plans/mortgage/preview', params);
}

export function addMonths(month, count) {
  const [y, m] = month.split('-').map(Number);
  const d = new Date(Date.UTC(y, m - 1 + count, 1));
  return d.getUTCFullYear() + '-' + String(d.getUTCMonth() + 1).padStart(2, '0');
}
