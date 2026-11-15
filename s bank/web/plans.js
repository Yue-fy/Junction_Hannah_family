// Optional planning modules (V4 lane P): a mortgage plan and a tax plan the customer can switch on.
// Both are money-profile entries (plan_mortgage, plan_tax); the server does every calculation and this
// module only renders them, opens the shared review form (openDraft) and saves after the customer confirms.
// Every number shown is an estimate from what the customer entered.

const LOCALES = ['en', 'fi', 'sv'];
const COPY = {
  'title': ['Plans', 'Suunnitelmat', 'Planer'],
  'intro': ['Optional extras. Switch on what fits your life, and switch off any time.', 'Valinnaisia lisiä. Ota käyttöön se, mikä sopii elämääsi, ja poista milloin tahansa.', 'Valfria tillägg. Slå på det som passar ditt liv och stäng av när du vill.'],
  'on': ['On', 'Käytössä', 'På'],
  'turnOn': ['Turn on', 'Ota käyttöön', 'Slå på'],
  'turnOff': ['Turn off', 'Poista käytöstä', 'Stäng av'],
  'change': ['Change numbers', 'Muuta lukuja', 'Ändra siffror'],
  'estimate': ['Estimate', 'Arvio', 'Uppskattning'],
  'loading': ['Loading your plans…', 'Ladataan suunnitelmia…', 'Läser in dina planer…'],
  'unavailable': ['Plans are not available right now.', 'Suunnitelmat eivät ole juuri nyt saatavilla.', 'Planerna är inte tillgängliga just nu.'],
  'saved': ['Plan saved. It is now held back on each payday.', 'Suunnitelma tallennettu. Se varataan nyt jokaisena palkkapäivänä.', 'Planen är sparad. Den hålls nu undan varje lönedag.'],
  'removed': ['Plan switched off.', 'Suunnitelma poistettu käytöstä.', 'Planen är avstängd.'],
  'perMonth': ['a month', 'kuukaudessa', 'i månaden'],
  'heldBack': ['held back on each payday', 'varataan jokaisena palkkapäivänä', 'hålls undan varje lönedag'],
  // Mortgage
  'm.title': ['Mortgage plan', 'Asuntolainasuunnitelma', 'Bolåneplan'],
  'm.benefit': ['If you have a home loan: see the payment held back each payday, when the loan ends, and what a little extra would do.', 'Jos sinulla on asuntolaina: näet jokaisena palkkapäivänä varattavan erän, milloin laina päättyy ja mitä pieni lisälyhennys tekisi.', 'Om du har ett bolån: se betalningen som hålls undan varje lönedag, när lånet är betalt och vad lite extra skulle göra.'],
  'm.detected': ['You pay about {amount} for housing each month, around the {day}. If that is your loan payment, we can start from it.', 'Maksat asumisesta noin {amount} kuukaudessa, yleensä noin {day}. päivä. Jos se on lainanlyhennyksesi, voimme aloittaa siitä.', 'Du betalar cirka {amount} för boendet varje månad, runt den {day}. Om det är din lånebetalning kan vi börja med den.'],
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
  'm.extraResult': ['With {extra} extra a month: paid off in {month}, {months} months sooner, about {saved} less interest.', 'Kun lyhennät {extra} enemmän kuukaudessa: laina maksettu {month}, {months} kuukautta aiemmin, noin {saved} vähemmän korkoa.', 'Med {extra} extra i månaden: betalt {month}, {months} månader tidigare, cirka {saved} mindre ränta.'],
  'm.steady': ['Right now it makes sense to keep your cushion first, so we are not suggesting extra payments.', 'Juuri nyt on järkevää pitää puskuri ensin, joten emme ehdota lisälyhennyksiä.', 'Just nu är det klokt att behålla bufferten först, så vi föreslår inga extra amorteringar.'],
  'm.thin': ['Your cushion looks thin. Before paying extra on the loan, it may help to keep a little more in your account for surprises.', 'Puskurisi näyttää ohuelta. Ennen lisälyhennyksiä voi olla hyvä pitää tilillä vähän enemmän yllätyksiä varten.', 'Din buffert ser tunn ut. Innan du amorterar extra kan det vara bra att ha lite mer på kontot för oväntade utgifter.'],
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
  'f.years': ['Years left', 'Laina-aikaa jäljellä (vuotta)', 'År kvar'],
  'f.payment': ['Monthly payment', 'Kuukausierä', 'Månadsbetalning'],
  'f.paymentHelp': ['Leave empty to calculate it from the years left.', 'Jätä tyhjäksi, niin erä lasketaan jäljellä olevasta laina-ajasta.', 'Lämna tomt för att räkna ut den från åren kvar.'],
  'f.day': ['Payment day of the month', 'Eräpäivä (kuukauden päivä)', 'Betalningsdag i månaden'],
  'f.check': ['Next rate check', 'Seuraava koron tarkistus', 'Nästa räntejustering'],
  'f.needTerm': ['Enter the years left or the monthly payment.', 'Anna jäljellä oleva laina-aika tai kuukausierä.', 'Ange år kvar eller månadsbetalningen.'],
  'f.preview': ['About {amount} a month, paid off in {month}.', 'Noin {amount} kuukaudessa, laina maksettu {month}.', 'Cirka {amount} i månaden, betalt {month}.'],
  'f.save': ['Save my plan', 'Tallenna suunnitelma', 'Spara min plan'],
  // Tax
  't.title': ['Tax plan', 'Verosuunnitelma', 'Skatteplan'],
  't.benefit': ['Put a little aside each month for back taxes, know when a refund is coming, and get a nudge if your tax card looks off.', 'Varaa joka kuukausi vähän jäännösveroa varten, tiedä milloin veronpalautus tulee ja saat vinkin, jos verokorttisi näyttää väärältä.', 'Lägg undan lite varje månad för kvarskatt, vet när en skatteåterbäring kommer och få en påminnelse om skattekortet verkar fel.'],
  't.setAside': ['for back taxes, until {date}', 'jäännösveroa varten {date} asti', 'för kvarskatt, fram till {date}'],
  't.nothing': ['Nothing to put aside for taxes right now.', 'Veroja varten ei tarvitse varata juuri nyt.', 'Inget att lägga undan för skatt just nu.'],
  't.estimateDate': ['The date is our estimate; your tax decision shows the exact one.', 'Päivä on arviomme; veropäätöksessäsi on tarkka päivä.', 'Datumet är vår uppskattning; ditt beskattningsbeslut visar det exakta.'],
  't.refund': ['Tax refund of about {amount} expected on {date}.', 'Veronpalautusta noin {amount} odotetaan {date}.', 'Skatteåterbäring på cirka {amount} väntas {date}.'],
  't.refundNoDate': ['You expect a tax refund of about {amount} after your tax decision.', 'Odotat noin {amount} veronpalautusta veropäätöksen jälkeen.', 'Du väntar en skatteåterbäring på cirka {amount} efter beskattningsbeslutet.'],
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
  't.expect': ['Add what I expect', 'Lisää odotukseni', 'Lägg till vad jag väntar mig'],
  't.card': ['Tax card details', 'Verokortin tiedot', 'Skattekortets uppgifter'],
  't.footer': ['Estimate from what you entered. Your tax decision in OmaVero is the official source.', 'Arvio antamistasi tiedoista. Virallinen lähde on veropäätöksesi OmaVerossa.', 'Uppskattning utifrån det du angett. Den officiella källan är ditt beskattningsbeslut i MinSkatt (OmaVero).'],
  'f.tTitle': ['Help me plan taxes', 'Auta minua suunnittelemaan verot', 'Hjälp mig planera skatten'],
  'f.tIntro': ['I will use your tax decision and tax card when you add them. If you already expect back taxes or a refund for this year, add the amount and I will spread it over the coming months.', 'Käytän veropäätöstäsi ja verokorttiasi, kun lisäät ne. Jos odotat jo jäännösveroa tai palautusta tältä vuodelta, lisää summa, niin jaan sen tuleville kuukausille.', 'Jag använder ditt beskattningsbeslut och skattekort när du lägger till dem. Om du redan väntar kvarskatt eller återbäring för i år, ange beloppet så fördelar jag det över de kommande månaderna.'],
  'f.backTax': ['Back taxes I expect for this year', 'Odotan jäännösveroa tältä vuodelta', 'Kvarskatt jag väntar mig för i år'],
  'f.refund': ['Refund I expect for this year', 'Odotan veronpalautusta tältä vuodelta', 'Återbäring jag väntar mig för i år'],
  't.save': ['Turn on my tax plan', 'Ota verosuunnitelma käyttöön', 'Slå på min skatteplan'],
  'off.title': ['Switch off this plan?', 'Poistetaanko suunnitelma käytöstä?', 'Stänga av den här planen?'],
  'off.intro': ['The plan is removed from your money profile and no longer held back on payday. You can undo this.', 'Suunnitelma poistetaan rahaprofiilistasi, eikä sitä enää varata palkkapäivänä. Voit perua tämän.', 'Planen tas bort från din pengaprofil och hålls inte längre undan på lönedagen. Du kan ångra det.'],
};

const lang = locale => (LOCALES.includes(String(locale).slice(0, 2)) ? String(locale).slice(0, 2) : 'en');
export function planText(locale, key, values = {}) {
  const row = COPY[key];
  const text = row ? row[LOCALES.indexOf(lang(locale))] || row[0] : key;
  return text.replace(/\{(\w+)\}/g, (_, name) => (values[name] === undefined ? '{' + name + '}' : String(values[name])));
}
export const PLAN_COPY_KEYS = Object.freeze(Object.keys(COPY));

/** Percentage from basis points in the customer's language: en '2.85%', fi/sv '2,85 %'. */
export function formatRate(bp, locale) {
  const value = (Number(bp) || 0) / 100;
  const text = value.toFixed(2).replace(/0$/, '').replace(/\.0$/, '');
  return lang(locale) === 'en' ? text + '%' : text.replace('.', ',') + ' %';
}

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
  const t = key => planText(locale, key);
  const v = value || {};
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

export function taxSpec(locale, {value = null} = {}) {
  const t = key => planText(locale, key);
  const v = value || {};
  return {id: 'plan-tax', kind: 'plan', title: t('f.tTitle'), intro: t('f.tIntro'), saveLabel: t('t.save'), mode: 'edit', fields: [
    {name: 'expected_back_tax_cents', label: t('f.backTax'), type: 'amount', value: v.expected_back_tax_cents ?? '', min: 0},
    {name: 'expected_refund_cents', label: t('f.refund'), type: 'amount', value: v.expected_refund_cents ?? '', min: 0},
  ]};
}
export function taxValue(values) {
  const value = {on: true};
  for (const key of ['expected_back_tax_cents', 'expected_refund_cents']) if (Number.isSafeInteger(values[key]) && values[key] > 0) value[key] = values[key];
  return {value};
}

/** Plain-language one-liner for the Me page entry (money-profile.js describeEntry). */
export function describePlan(entry, locale, money) {
  const v = entry?.value || {};
  if (entry?.key === 'plan_mortgage') {
    const parts = [planText(locale, 'm.left') + ' ' + money(v.principal_cents || 0), formatRate((v.reference_rate_bp || 0) + (v.margin_bp || 0), locale)];
    if (Number.isInteger(v.monthly_payment_cents)) parts.push(money(v.monthly_payment_cents) + ' ' + planText(locale, 'perMonth'));
    return parts.join(' · ');
  }
  const parts = [planText(locale, 'on')];
  if (v.expected_back_tax_cents) parts.push(planText(locale, 'f.backTax') + ': ' + money(v.expected_back_tax_cents));
  if (v.expected_refund_cents) parts.push(planText(locale, 'f.refund') + ': ' + money(v.expected_refund_cents));
  return parts.join(' · ');
}

// ---------------------------------------------------------------- rendering (pure)

function row(label, value) { return `<div class="plan-row"><dt>${escape(label)}</dt><dd>${escape(value)}</dd></div>`; }

export function renderMortgageCard(data, ui, h) {
  const {locale, money, monthLabel} = h;
  const t = (key, values) => planText(locale, key, values);
  if (!data?.on) {
    const pre = data?.prefill;
    const detected = pre?.found && pre.source !== 'profile' && Number.isInteger(pre.monthly_payment_cents) && pre.payment_day
      ? `<p class="plan-detected">${escape(t('m.detected', {amount: money(pre.monthly_payment_cents), day: pre.payment_day}))}</p>` : '';
    return `<article class="plan-card" data-plan="mortgage"><h3>${escape(t('m.title'))}</h3><p class="plan-benefit">${escape(t('m.benefit'))}</p>${detected}<div class="plan-actions"><button type="button" class="secondary-button" data-plan-on="mortgage">${escape(t('turnOn'))}</button></div></article>`;
  }
  const p = data.projection;
  const actions = `<div class="plan-actions"><button type="button" class="text-button" data-plan-edit="mortgage">${escape(t('change'))}</button><button type="button" class="text-button" data-plan-off="mortgage">${escape(t('turnOff'))}</button></div>`;
  if (!p) return `<article class="plan-card plan-card--on" data-plan="mortgage"><div class="plan-head"><h3>${escape(t('m.title'))}</h3><span class="plan-pill">${escape(t('on'))}</span></div><p>${escape(t('m.error'))}</p>${actions}</article>`;
  const inputs = p.inputs || {};
  const rateDetail = inputs.reference_rate === 'fixed' ? t('m.rateFixed')
    : t('m.rateParts', {ref: t('f.' + inputs.reference_rate), refRate: formatRate(inputs.reference_rate_bp, locale), margin: formatRate(inputs.margin_bp, locale)});
  const notes = [];
  if ((p.notes || []).includes('payment_falls')) notes.push(t('m.falls'));
  if ((p.notes || []).includes('payment_differs')) notes.push(t('m.differs', {amount: money(p.calculated_payment_cents)}));
  const advice = p.extra_advice || {};
  let extra;
  if (advice.reason === 'steady') extra = `<p class="plan-note">${escape(t('m.steady'))}</p>`;
  else {
    const chosen = ui.extra || 0;
    const w = p.what_if;
    extra = `<div class="plan-whatif"><h4>${escape(t('m.extraTitle'))}</h4>${advice.reason === 'buffer_thin' ? `<p class="plan-note">${escape(t('m.thin'))}</p>` : ''}<div class="plan-chips" role="group">${EXTRA_STEPS.map(step => `<button type="button" class="plan-chip" data-plan-extra="${step}" aria-pressed="${chosen === step}">+${escape(money(step))}</button>`).join('')}</div>${w && w.extra_cents === chosen ? `<p class="plan-result" aria-live="polite">${escape(t('m.extraResult', {extra: money(w.extra_cents), month: monthLabel(w.payoff_month), months: w.months_saved, saved: money(w.interest_saved_cents)}))}</p>` : ''}</div>`;
  }
  const selected = ui.rate ? (ui.rate > 0 ? p.rate_change?.up : p.rate_change?.down) : null;
  const sign = cents => (cents > 0 ? '+' : cents < 0 ? '−' : '±') + money(Math.abs(cents));
  const rateResult = selected ? `<p class="plan-result" aria-live="polite">${escape(selected.payment_change_cents === 0 && inputs.remaining_months == null
    ? t('m.rateResultTerm', {rate: formatRate(selected.rate_bp, locale), months: selected.months_left})
    : t('m.rateResult', {rate: formatRate(selected.rate_bp, locale), amount: money(selected.monthly_payment_cents), change: sign(selected.payment_change_cents)}))}</p>` : '';
  const rateBlock = `<div class="plan-whatif"><h4>${escape(t('m.rateTitle'))}</h4><div class="plan-chips" role="group"><button type="button" class="plan-chip" data-plan-rate="100" aria-pressed="${ui.rate === 100}">${escape(t('m.rateUp'))}</button><button type="button" class="plan-chip" data-plan-rate="-100" aria-pressed="${ui.rate === -100}">${escape(t('m.rateDown'))}</button></div>${rateResult}</div>`;
  return `<article class="plan-card plan-card--on" data-plan="mortgage"><div class="plan-head"><h3>${escape(t('m.title'))}</h3><span class="plan-pill">${escape(t('on'))}</span></div>`
    + `<p class="plan-amount">${escape(money(p.monthly_payment_cents))} <span>${escape(t('perMonth'))}</span></p><p class="plan-sub">${escape(t('heldBack'))} · ${escape(t('estimate'))}</p>`
    + `<dl class="plan-rows">${row(t('m.payoff'), monthLabel(p.payoff_month))}${row(t('m.interest'), money(p.total_interest_cents))}${row(t('m.rate'), formatRate(p.rate_bp, locale))}${p.next_rate_check ? row(t('m.rateCheck'), monthLabel(p.next_rate_check)) : ''}</dl><p class="small-text plan-rate-detail">${escape(rateDetail)}</p>`
    + notes.map(note => `<p class="plan-note">${escape(note)}</p>`).join('') + extra + rateBlock
    + `<p class="small-text">${escape(t('m.footer'))}</p>${actions}</article>`;
}

export function renderTaxCard(data, h) {
  const {locale, money, dateLabel} = h;
  const t = (key, values) => planText(locale, key, values);
  if (!data?.on) {
    return `<article class="plan-card" data-plan="tax"><h3>${escape(t('t.title'))}</h3><p class="plan-benefit">${escape(t('t.benefit'))}</p><div class="plan-actions"><button type="button" class="secondary-button" data-plan-on="tax">${escape(t('turnOn'))}</button></div></article>`;
  }
  const s = data.set_aside || {};
  const omavero = data.omavero_text || 'OmaVero';
  const head = s.monthly_cents > 0
    ? `<p class="plan-amount">${escape(money(s.monthly_cents))} <span>${escape(t('perMonth'))}</span></p><p class="plan-sub">${escape(t('t.setAside', {date: dateLabel(s.until)}))} · ${escape(t('estimate'))}</p>${(s.instalments || []).some(item => item.status === 'upcoming' && item.date_is_estimate) ? `<p class="small-text">${escape(t('t.estimateDate'))}</p>` : ''}`
    : `<p class="plan-sub">${escape(t('t.nothing'))}</p>`;
  const r = data.refund;
  const refund = r ? `<p class="plan-note">${escape(r.seen && r.seen_date ? t('t.refundSeen', {amount: money(r.amount_cents), date: dateLabel(r.seen_date)})
    : r.expected_date ? t('t.refund', {amount: money(r.amount_cents), date: dateLabel(r.expected_date)}) : t('t.refundNoDate', {amount: money(r.amount_cents)}))}</p>` : '';
  const cardKey = {looks_ok: 't.cardOk', income_above_limit: 't.cardAbove', income_below_limit: 't.cardBelow', pay_differs: 't.cardDiffers', missing: 't.cardMissing'}[data.tax_card?.status] || 't.cardMissing';
  const card = `<p class="plan-note">${escape(t(cardKey, {omavero}))}</p>`;
  const dates = (data.dates || []).slice(0, 3);
  const dateList = dates.length ? `<h4>${escape(t('t.dates'))}</h4><dl class="plan-rows">${dates.map(item => row(t('t.kind.' + item.kind), dateLabel(item.date))).join('')}</dl>` : '';
  return `<article class="plan-card plan-card--on" data-plan="tax"><div class="plan-head"><h3>${escape(t('t.title'))}</h3><span class="plan-pill">${escape(t('on'))}</span></div>${head}${refund}${card}${dateList}`
    + `<p class="small-text">${escape(t('t.footer'))}</p><div class="plan-actions"><button type="button" class="text-button" data-plan-edit="tax">${escape(t('t.expect'))}</button><button type="button" class="text-button" data-plan-tax-card>${escape(t('t.card'))}</button><button type="button" class="text-button" data-plan-off="tax">${escape(t('turnOff'))}</button></div></article>`;
}

export function renderPlansSection(state, h) {
  const t = key => planText(h.locale, key);
  const body = state.error ? `<p class="empty-state">${escape(t('unavailable'))}</p>`
    : state.loading ? `<p class="empty-state" role="status">${escape(t('loading'))}</p>`
      : renderMortgageCard(state.mortgage, state.ui || {}, h) + renderTaxCard(state.tax, h);
  return `<section class="plans-v4" aria-labelledby="plans-v4-title"><h2 id="plans-v4-title">${escape(t('title'))}</h2><p class="subtle">${escape(t('intro'))}</p><div class="plan-list">${body}</div></section>`;
}

// ---------------------------------------------------------------- wiring

/**
 * @param {object} deps {$, request, captureContext, isCurrent, openDraft, closeDialogs, money, dateLabel, monthLabel,
 *   locale: () => string, referenceDate: () => string|null, notify, explainError, onChanged(context), openTax(), confirmDanger}
 * @returns {{render(context?), reset(), openSetup(plan, provenance?), editEntry(entry), handleClick(event): boolean}}
 */
export function initPlans(deps) {
  const {$, request, captureContext, isCurrent, openDraft, money, dateLabel, monthLabel, locale, referenceDate, notify} = deps;
  let view = {loading: true, mortgage: null, tax: null, ui: {extra: 0, rate: 0}, error: false};
  let customer = null;
  const helpers = () => ({locale: locale(), money, dateLabel, monthLabel});
  const asOf = () => (referenceDate() ? {as_of: referenceDate()} : {});
  const paint = () => { const root = $('plans-root'); if (root) root.innerHTML = renderPlansSection(view, helpers()); };

  async function loadMortgage(context) {
    const params = {...asOf()};
    if (view.ui.extra) params.extra_cents = view.ui.extra;
    if (view.ui.rate) params.rate_delta_bp = view.ui.rate;
    return request(context, 'get', '/api/plans/mortgage/projection', params);
  }
  async function render(context = captureContext()) {
    if (!$('plans-root')) return;
    if (customer !== context.customerId) { view = {loading: true, mortgage: null, tax: null, ui: {extra: 0, rate: 0}, error: false}; customer = context.customerId; }
    if (!view.mortgage) paint();
    try {
      const [mortgageData, taxData] = await Promise.all([loadMortgage(context), request(context, 'get', '/api/plans/tax', asOf())]);
      if (!isCurrent(context)) return;
      view = {...view, loading: false, error: false, mortgage: mortgageData, tax: taxData};
    } catch {
      if (!isCurrent(context)) return;
      view = {...view, loading: false, error: true};
    }
    paint();
  }
  async function refreshMortgage(context = captureContext()) {
    try {
      const data = await loadMortgage(context);
      if (isCurrent(context)) { view.mortgage = data; paint(); }
    } catch (error) { deps.explainError?.(error); }
  }
  async function saved(context, message) {
    view.ui = {extra: 0, rate: 0};
    await deps.onChanged?.(context);
    await render(context);
    // The review dialog closes itself shortly after a save; tell the customer once it is gone.
    setTimeout(() => { try { notify?.(planText(locale(), message)); } catch { /* the notice is optional */ } }, 700);
  }
  function openSetup(plan, provenance = 'user') {
    const context = captureContext();
    const lang = locale();
    if (plan === 'mortgage') {
      const current = view.mortgage?.projection?.inputs && view.mortgage.on ? view.mortgage.projection.inputs : null;
      const spec = mortgageSpec(lang, {value: current, prefill: view.mortgage?.prefill});
      openDraft(spec, {
        onChange: (values, card) => {
          const converted = mortgageValue(values);
          let text = '';
          if (converted.value && converted.value.remaining_months && converted.value.loan_type === 'annuity') {
            const pay = annuityPayment(converted.value.principal_cents, converted.value.reference_rate_bp + converted.value.margin_bp, converted.value.remaining_months);
            const end = referenceDate() ? addMonths(referenceDate().slice(0, 7), converted.value.remaining_months) : null;
            if (pay && end) text = planText(lang, 'f.preview', {amount: money(pay), month: monthLabel(end)});
          }
          deps.updatePreview?.(card, text);
        },
        onSave: async values => {
          const converted = mortgageValue(values);
          if (converted.error) throw new Error(planText(lang, converted.error));
          await request(context, 'post', '/api/plans/mortgage', {plan: converted.value, confirmed: true, provenance,
            ...(provenance === 'user' ? {} : {source: 'from_our_chat'})});
          await saved(context, 'saved');
        }});
      return;
    }
    const current = view.tax?.on ? deps.planEntry?.('plan_tax')?.value : null;
    openDraft(taxSpec(lang, {value: current}), {onSave: async values => {
      await request(context, 'post', '/api/plans/tax', {plan: taxValue(values).value, confirmed: true, provenance,
        ...(provenance === 'user' ? {} : {source: 'from_our_chat'})});
      await saved(context, 'saved');
    }});
  }
  function turnOff(plan) {
    const data = plan === 'mortgage' ? view.mortgage : view.tax;
    if (!data?.entry_id) return;
    const context = captureContext();
    deps.confirmDanger(planText(locale(), 'off.title'), planText(locale(), 'off.intro'), async () => {
      await request(context, 'post', '/api/profile/entries/delete', {entry_id: data.entry_id, confirmed: true});
      await saved(context, 'removed');
    });
  }
  function handleClick(event) {
    const target = event.target?.closest?.('[data-plan-on],[data-plan-edit],[data-plan-off],[data-plan-extra],[data-plan-rate],[data-plan-tax-card]');
    const d = target?.dataset;
    if (!d || !(d.planOn || d.planEdit || d.planOff || d.planExtra || d.planRate || target.hasAttribute?.('data-plan-tax-card'))) return false;
    if (d.planOn) openSetup(d.planOn);
    else if (d.planEdit) openSetup(d.planEdit);
    else if (d.planOff) turnOff(d.planOff);
    else if (d.planExtra) { const value = Number(d.planExtra); view.ui.extra = view.ui.extra === value ? 0 : value; refreshMortgage(); }
    else if (d.planRate) { const value = Number(d.planRate); view.ui.rate = view.ui.rate === value ? 0 : value; refreshMortgage(); }
    else if (target.hasAttribute('data-plan-tax-card')) deps.openTax?.();
    return true;
  }
  return {
    render, openSetup, handleClick,
    reset() { view = {loading: true, mortgage: null, tax: null, ui: {extra: 0, rate: 0}, error: false}; customer = null; const root = $('plans-root'); if (root) root.innerHTML = ''; },
    repaint: paint,
  };
}

function addMonths(month, count) {
  const [y, m] = month.split('-').map(Number);
  const d = new Date(Date.UTC(y, m - 1 + count, 1));
  return d.getUTCFullYear() + '-' + String(d.getUTCMonth() + 1).padStart(2, '0');
}
