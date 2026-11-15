/**
 * Year in review story viewer (WP-L, F2). Dependency-free ES module, no fetch, no global state.
 *
 * Input contract (from scoach/year_review.py `year_review`):
 *   review = {year, complete, available, cards:[{id, kind, facts:{...}, caption_template}], captions?, closing_message?}
 * Money facts are integer `*_cents`; shares/rates are `*_percent` strings such as "23.4" (a trailing "%" is kept as-is).
 *
 * Facts read per card kind (missing optional facts simply hide the line that needs them):
 *   intro                    year, purchase_count?
 *   money_in_out             money_in_cents, money_out_cents, net_cents?
 *   saved                    saved_cents, saving_rate_percent?, previous_saved_cents?, left_over_cents?, stayed_in_account_cents?
 *   top_category             category | category_label, amount_cents, share_percent?
 *   baskets                  must_pays_cents, surprise_must_pays_cents, little_leaks_cents, matching *_percent?
 *                            (fixed_obligation_cents / flexible_essential_cents / discretionary_cents also accepted)
 *   little_leaks             little_leaks_cents | amount_cents, rent_months? (string or number)
 *   peak_month               month ("YYYY-MM"), amount_cents, calmest_month?, calmest_amount_cents?
 *   busiest_day              date ("YYYY-MM-DD"), amount_cents, purchase_count?
 *   favourite_weekday_or_mcc weekday (0=Monday..6, or English name) | weekday_label, mcc_label?, mcc_count?
 *   archetype                archetype_label | archetype, previous_archetype_label?
 *   closing                  year
 */

const LOCALES = ['en', 'fi', 'sv'];
const INTL = {en: 'en-GB', fi: 'fi-FI', sv: 'sv-SE'};
export const STORY_KINDS = Object.freeze(['intro', 'money_in_out', 'saved', 'top_category', 'baskets', 'little_leaks', 'peak_month', 'busiest_day', 'favourite_weekday_or_mcc', 'archetype', 'closing']);

const COPY = {
  'ui.dialog': ['Your year in money', 'Rahavuotesi', 'Ditt år i pengar'],
  'ui.close': ['Close', 'Sulje', 'Stäng'],
  'ui.prev': ['Previous card', 'Edellinen kortti', 'Föregående kort'],
  'ui.next': ['Next card', 'Seuraava kortti', 'Nästa kort'],
  'ui.pause': ['Pause', 'Pysäytä', 'Pausa'],
  'ui.play': ['Play', 'Jatka', 'Fortsätt'],
  'ui.progress': ['Card {current} of {total}', 'Kortti {current}/{total}', 'Kort {current} av {total}'],
  'ui.save': ['Save to my profile', 'Tallenna profiiliini', 'Spara i min profil'],
  'ui.ask': ['Ask coach about my year', 'Kysy valmentajalta vuodestani', 'Fråga coachen om mitt år'],
  'ui.unavailable': ["There isn't enough account history for {year} yet.", 'Vuodelta {year} ei ole vielä tarpeeksi tilitapahtumia.', 'Det finns inte tillräckligt med kontohistorik för {year} än.'],
  'ui.partial': ['{year} is still in progress, so these numbers cover the year so far.', 'Vuosi {year} on vielä kesken, joten luvut kattavat vuoden tähän asti.', '{year} pågår fortfarande, så siffrorna gäller året hittills.'],
  'banner.eyebrow': ['Year in review', 'Vuosikatsaus', 'Årsöversikt'],
  'banner.title': ['Your {year} in money is ready', 'Rahavuotesi {year} on valmis', 'Ditt {year} i pengar är klart'],
  'banner.help': ['A few quick cards about where your money went.', 'Muutama nopea kortti siitä, mihin rahasi menivät.', 'Några snabba kort om vart dina pengar tog vägen.'],
  'banner.open': ['See my year', 'Katso vuoteni', 'Se mitt år'],
  'banner.dismiss': ['Not now', 'Ei nyt', 'Inte nu'],
  'basket.must': ['Must-pays', 'Pakolliset kuukausimenot', 'Fasta måsten'],
  'basket.surprise': ['Surprise must-pays', 'Yllättävät pakolliset menot', 'Oväntade måsten'],
  'basket.leaks': ['Little leaks', 'Arjen pikkumenot', 'Vardagens småutgifter'],
  'bar.in': ['Money in', 'Tulot', 'Pengar in'],
  'bar.out': ['Money out', 'Menot', 'Pengar ut'],

  'eyebrow.intro': ['Your year in money', 'Rahavuotesi', 'Ditt år i pengar'],
  'eyebrow.money_in_out': ['In and out', 'Tulot ja menot', 'In och ut'],
  'eyebrow.saved': ['Saved', 'Säästöön', 'Sparat'],
  'eyebrow.top_category': ['Top category', 'Suurin menoluokka', 'Största kategorin'],
  'eyebrow.baskets': ['Your three baskets', 'Kolme koriasi', 'Dina tre korgar'],
  'eyebrow.little_leaks': ['Little leaks', 'Arjen pikkumenot', 'Vardagens småutgifter'],
  'eyebrow.peak_month': ['Biggest month', 'Kallein kuukausi', 'Dyraste månaden'],
  'eyebrow.busiest_day': ['Busiest day', 'Vilkkain päivä', 'Livligaste dagen'],
  'eyebrow.favourite_weekday_or_mcc': ['Your rhythm', 'Rytmisi', 'Din rytm'],
  'eyebrow.archetype': ['Your spending style', 'Kulutustyylisi', 'Din utgiftsstil'],
  'eyebrow.closing': ['That was {year}', 'Tällainen oli {year}', 'Så var {year}'],

  'label.intro': ['in money', 'rahan silmin', 'i pengar'],
  'label.money_in_out': ['came in', 'tuli tilillesi', 'kom in'],
  'label.saved': ['moved to savings', 'siirsit säästöön', 'flyttat till sparande'],
  'label.baskets': ['went to your three baskets', 'meni kolmeen koriisi', 'gick till dina tre korgar'],
  'label.little_leaks': ['on small everyday buys', 'pieniin arjen ostoksiin', 'på små vardagsköp'],
  'label.favourite_weekday': ['is the day you pay most often', 'on päivä, jona maksat useimmin', 'är dagen då du oftast betalar'],
  'label.favourite_mcc': ['is where you pay most often', 'on yleisin maksukohteesi', 'är där du oftast betalar'],
  'label.closing': ['Thanks for looking back', 'Kiitos, että katsoit taaksepäin', 'Tack för att du blickade tillbaka'],

  'caption.generic': ['A look back at your year.', 'Katsaus vuoteesi.', 'En tillbakablick på ditt år.'],
  'caption.intro': ['Here is how {year} looked for your money, straight from your own account.', 'Tältä vuosi {year} näytti rahojesi osalta – suoraan omalta tililtäsi.', 'Så här såg {year} ut för dina pengar, direkt från ditt eget konto.'],
  'caption.money_in_out': ['{money_in} came in and {money_out} went out.', 'Tilillesi tuli {money_in} ja sieltä lähti {money_out}.', '{money_in} kom in och {money_out} gick ut.'],
  'caption.saved': ['You moved {saved} to savings, {rate} of what came in.', 'Siirsit säästöön {saved} eli {rate} tuloistasi.', 'Du flyttade {saved} till sparande, {rate} av det som kom in.'],
  'caption.saved.short': ['You moved {saved} to savings this year.', 'Siirsit tänä vuonna säästöön {saved}.', 'Du flyttade {saved} till sparande i år.'],
  'caption.top_category': ['{category} took the biggest share: {share} of your spending.', 'Eniten rahaa meni luokkaan {category}: {share} kaikista menoistasi.', '{category} tog den största delen: {share} av dina utgifter.'],
  'caption.top_category.short': ['{category} was where most of your money went.', 'Eniten rahaa meni luokkaan {category}.', 'Mest pengar gick till {category}.'],
  'caption.baskets': ['Must-pays took {must}, surprise must-pays {surprise} and little leaks {leaks}.', 'Pakollisiin kuukausimenoihin meni {must}, yllättäviin pakollisiin menoihin {surprise} ja arjen pikkumenoihin {leaks}.', 'Fasta måsten tog {must}, oväntade måsten {surprise} och vardagens småutgifter {leaks}.'],
  'caption.little_leaks': ['Small everyday buys added up to {amount} over the year.', 'Pienistä arjen ostoksista kertyi vuoden aikana {amount}.', 'Små vardagsköp blev sammanlagt {amount} under året.'],
  'caption.peak_month': ['{month} was your biggest spending month at {amount}.', '{month} oli vuoden kallein kuukausi: {amount}.', '{month} var årets dyraste månad med {amount}.'],
  'caption.busiest_day': ['On {date} you spent {amount}, more than on any other day.', '{date} käytit {amount}, enemmän kuin minään muuna päivänä.', 'Den {date} spenderade du {amount}, mer än någon annan dag.'],
  'caption.favourite_weekday': ['{weekday} is the day you reach for your card most often.', 'Kortti on useimmin käytössä, kun on {weekday}.', 'Kortet åker oftast fram på en {weekday}.'],
  'caption.favourite_mcc': ['Your most frequent kind of purchase: {mcc}.', 'Useimmin maksoit kohteessa: {mcc}.', 'Ditt vanligaste slags köp: {mcc}.'],
  'caption.archetype': ['Your spending style this year: {archetype}.', 'Kulutustyylisi tänä vuonna: {archetype}.', 'Din utgiftsstil i år: {archetype}.'],
  'caption.closing': ['Every number here came from your own account. Want to talk about what comes next?', 'Jokainen luku tuli omalta tililtäsi. Jutellaanko siitä, mitä seuraavaksi?', 'Varje siffra kom från ditt eget konto. Ska vi prata om vad som händer härnäst?'],

  'support.intro': ['{count} purchases and payments in total.', 'Yhteensä {count} ostosta ja maksua.', 'Totalt {count} köp och betalningar.'],
  'support.money_in_out': ['Left over: {net}.', 'Jäi yli: {net}.', 'Över blev: {net}.'],
  'support.money_in_out.negative': ['Money out was {net} more than money in.', 'Menoja oli {net} enemmän kuin tuloja.', 'Utgifterna var {net} större än inkomsterna.'],
  'support.saved': ['Previous year: {previous}.', 'Edellisenä vuonna: {previous}.', 'Föregående år: {previous}.'],
  'support.saved.split': ['Of the {left} left over, {saved} went to savings and {stayed} stayed in your account.', 'Yli jääneestä {left} summasta {saved} meni säästöön ja {stayed} jäi tilillesi.', 'Av de {left} som blev över gick {saved} till sparande och {stayed} blev kvar på kontot.'],
  'support.saved.over': ['{saved} went to savings, more than the {left} left over; the difference came from your balance.', 'Säästöön meni {saved}, enemmän kuin yli jäi ({left}); erotus otettiin tililtäsi.', '{saved} gick till sparande, mer än de {left} som blev över; skillnaden togs från kontot.'],
  'support.top_category': ['{amount} in total.', 'Yhteensä {amount}.', 'Totalt {amount}.'],
  'support.little_leaks': ['That is about {rent_months} months of your own rent.', 'Se vastaa noin {rent_months} kuukauden vuokraasi.', 'Det motsvarar ungefär {rent_months} månader av din egen hyra.'],
  'support.peak_month': ['Calmest month: {calm_month}, {calm_amount}.', 'Rauhallisin kuukausi: {calm_month}, {calm_amount}.', 'Lugnaste månaden: {calm_month}, {calm_amount}.'],
  'support.busiest_day': ['{count} purchases that day.', 'Sinä päivänä ostoksia oli {count}.', '{count} köp den dagen.'],
  'support.favourite_weekday_or_mcc': ['Most frequent purchase type: {mcc}, {mcc_count} times.', 'Yleisin ostostyyppi: {mcc}, {mcc_count} kertaa.', 'Vanligaste köptypen: {mcc}, {mcc_count} gånger.'],
  'support.archetype': ['Last year: {previous}.', 'Viime vuonna: {previous}.', 'Förra året: {previous}.'],
  'support.closing': ['Save it to your profile to replay it any time.', 'Tallenna se profiiliisi, niin voit katsoa sen uudelleen milloin vain.', 'Spara den i din profil så kan du se den igen när du vill.'],
};

/** Frozen message maps: {en:{key:text}, fi:{...}, sv:{...}}; all three locales share identical keys. */
export const YEAR_REVIEW_MESSAGES = Object.freeze(Object.fromEntries(LOCALES.map((locale, index) => [locale, Object.freeze(Object.fromEntries(Object.entries(COPY).map(([key, values]) => [key, values[index]])))])));

const normLocale = locale => {
  const short = String(locale || 'en').toLowerCase().slice(0, 2);
  return LOCALES.includes(short) ? short : 'en';
};

/**
 * Localized message accessor.
 * @param {string} locale 'en' | 'fi' | 'sv' (anything else falls back to English)
 * @param {string} key message key from YEAR_REVIEW_MESSAGES
 * @param {object} values placeholder values; unknown placeholders stay as "{name}"
 * @returns {string}
 */
export function yr(locale, key, values = {}) {
  const text = YEAR_REVIEW_MESSAGES[normLocale(locale)][key] ?? YEAR_REVIEW_MESSAGES.en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, name) => values[name] === undefined || values[name] === null ? '{' + name + '}' : String(values[name]));
}

/** Fill a message, returning null when any placeholder has no value (so callers can fall back). */
function fill(locale, key, values) {
  const text = YEAR_REVIEW_MESSAGES[normLocale(locale)][key];
  if (text === undefined) return null;
  let missing = false;
  const out = text.replace(/\{(\w+)\}/g, (_, name) => {
    const value = values[name];
    if (value === undefined || value === null || value === '') { missing = true; return ''; }
    return String(value);
  });
  return missing ? null : capitalize(out);
}
function fillTemplate(template, values) {
  if (typeof template !== 'string' || !template.trim()) return null;
  let missing = false;
  const out = template.replace(/\{(\w+)\}/g, (_, name) => {
    const value = values[name];
    if (value === undefined || value === null || value === '') { missing = true; return ''; }
    return String(value);
  });
  return missing ? null : out;
}

const esc = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[x]));
const capitalize = text => text ? text.charAt(0).toLocaleUpperCase() + text.slice(1) : text;
const isCents = value => Number.isSafeInteger(value);
const WEEKDAYS_EN = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];

function formatters(locale, options = {}) {
  const intl = INTL[locale];
  const money = options.money || (cents => new Intl.NumberFormat(intl, {style: 'currency', currency: 'EUR'}).format(cents / 100));
  const monthLabel = options.monthLabel || (month => new Intl.DateTimeFormat(intl, {month: 'long', year: 'numeric', timeZone: 'UTC'}).format(new Date(month + '-01T12:00:00Z')));
  const dateLabel = options.dateLabel || (date => new Intl.DateTimeFormat(intl, {day: 'numeric', month: 'long', timeZone: 'UTC'}).format(new Date(String(date).slice(0, 10) + 'T12:00:00Z')));
  const count = value => Number.isFinite(Number(value)) && value !== null && value !== '' ? new Intl.NumberFormat(intl).format(Number(value)) : null;
  const percent = value => {
    if (value === null || value === undefined || value === '') return null;
    const raw = String(value).trim();
    if (raw.includes('%')) return raw;
    const number = Number(raw);
    if (!Number.isFinite(number)) return null;
    const text = new Intl.NumberFormat(intl, {maximumFractionDigits: 1}).format(number);
    return locale === 'en' ? text + '%' : text + ' %';
  };
  const decimal = value => {
    if (value === null || value === undefined || value === '') return null;
    const number = Number(value);
    return Number.isFinite(number) ? new Intl.NumberFormat(intl, {maximumFractionDigits: 1}).format(number) : null;
  };
  const weekday = value => {
    let index = Number.isInteger(value) ? value : WEEKDAYS_EN.indexOf(String(value ?? '').toLowerCase());
    if (index < 0 || index > 6) return value ? String(value) : null;
    return new Intl.DateTimeFormat(intl, {weekday: 'long', timeZone: 'UTC'}).format(new Date(Date.UTC(2024, 0, 1 + index)));
  };
  const m = value => isCents(value) ? money(value) : null;
  return {money: m, rawMoney: money, monthLabel: v => v ? monthLabel(v) : null, dateLabel: v => v ? dateLabel(v) : null, count, percent, decimal, weekday};
}

const pick = (facts, ...keys) => { for (const key of keys) if (facts[key] !== undefined && facts[key] !== null && facts[key] !== '') return facts[key]; return null; };

function basketFacts(facts) {
  return [
    {key: 'must', cents: pick(facts, 'must_pays_cents', 'fixed_obligation_cents'), percent: pick(facts, 'must_pays_percent', 'fixed_obligation_percent')},
    {key: 'surprise', cents: pick(facts, 'surprise_must_pays_cents', 'flexible_essential_cents'), percent: pick(facts, 'surprise_must_pays_percent', 'flexible_essential_percent')},
    {key: 'leaks', cents: pick(facts, 'little_leaks_cents', 'discretionary_cents'), percent: pick(facts, 'little_leaks_percent', 'discretionary_percent')},
  ];
}

/**
 * Build the view model for one card: everything renderStory shows, already formatted (not yet escaped).
 * @returns {{kind, eyebrow, big, bigCents, label, caption, support, visual}} big/label may be null
 */
function cardModel(card, review, locale, f, aiCaption) {
  const facts = card && typeof card.facts === 'object' && card.facts ? card.facts : {};
  const kind = STORY_KINDS.includes(card?.kind) ? card.kind : 'generic';
  const year = pick(facts, 'year') ?? review.year;
  const model = {kind, eyebrow: fill(locale, 'eyebrow.' + kind, {year}) || yr(locale, 'ui.dialog'), big: null, bigCents: null, label: null, caption: null, support: null, visual: null};
  const setMoney = cents => { if (isCents(cents)) { model.big = f.money(cents); model.bigCents = cents; } };
  let values = {year};
  let captionKeys = ['caption.' + kind];
  switch (kind) {
    case 'intro':
      model.big = year === null || year === undefined ? null : String(year);
      model.label = yr(locale, 'label.intro');
      model.support = fill(locale, 'support.intro', {count: f.count(pick(facts, 'purchase_count', 'transaction_count'))});
      if (review.complete === false) model.support = [model.support, fill(locale, 'ui.partial', {year})].filter(Boolean).join(' ');
      break;
    case 'money_in_out': {
      const inC = pick(facts, 'money_in_cents', 'income_cents'), outC = pick(facts, 'money_out_cents', 'spending_cents');
      setMoney(inC);
      model.label = yr(locale, 'label.money_in_out');
      values = {...values, money_in: f.money(inC), money_out: f.money(outC)};
      const net = isCents(pick(facts, 'net_cents')) ? facts.net_cents : (isCents(inC) && isCents(outC) ? inC - outC : null);
      if (isCents(net)) model.support = fill(locale, net < 0 ? 'support.money_in_out.negative' : 'support.money_in_out', {net: f.money(Math.abs(net))});
      if (isCents(inC) && isCents(outC)) model.visual = {type: 'inout', inCents: Math.abs(inC), outCents: Math.abs(outC), inText: f.money(inC), outText: f.money(outC)};
      break;
    }
    case 'saved': {
      const saved = pick(facts, 'saved_cents', 'savings_cents');
      setMoney(saved);
      model.label = yr(locale, 'label.saved');
      values = {...values, saved: f.money(saved), rate: f.percent(pick(facts, 'saving_rate_percent', 'savings_rate_percent'))};
      captionKeys = ['caption.saved', 'caption.saved.short'];
      // "Left over" (money in minus spending) already contains what was moved to savings: show the split, not a second total.
      const left = pick(facts, 'left_over_cents'), stayed = pick(facts, 'stayed_in_account_cents');
      model.support = isCents(left) && isCents(stayed) && isCents(saved)
        ? fill(locale, stayed < 0 ? 'support.saved.over' : 'support.saved.split', {left: f.money(left), saved: f.money(saved), stayed: f.money(stayed)})
        : fill(locale, 'support.saved', {previous: f.money(pick(facts, 'previous_saved_cents', 'previous_year_saved_cents'))});
      break;
    }
    case 'top_category': {
      const share = f.percent(pick(facts, 'share_percent'));
      const category = pick(facts, 'category_label', 'category');
      model.big = share || f.money(pick(facts, 'amount_cents'));
      if (!share) model.bigCents = isCents(facts.amount_cents) ? facts.amount_cents : null;
      model.label = category;
      values = {...values, category, share};
      captionKeys = ['caption.top_category', 'caption.top_category.short'];
      if (share) model.support = fill(locale, 'support.top_category', {amount: f.money(pick(facts, 'amount_cents'))});
      break;
    }
    case 'baskets': {
      const parts = basketFacts(facts);
      const total = parts.every(p => isCents(p.cents)) ? parts.reduce((sum, p) => sum + Math.abs(p.cents), 0) : null;
      setMoney(total);
      model.label = yr(locale, 'label.baskets');
      for (const p of parts) values[p.key] = f.percent(p.percent) || f.money(p.cents);
      if (total !== null) model.visual = {type: 'baskets', parts: parts.map(p => ({key: p.key, cents: Math.abs(p.cents), name: yr(locale, 'basket.' + p.key), text: f.money(p.cents), share: f.percent(p.percent)}))};
      break;
    }
    case 'little_leaks': {
      const amount = pick(facts, 'little_leaks_cents', 'amount_cents');
      setMoney(amount);
      model.label = yr(locale, 'label.little_leaks');
      values = {...values, amount: f.money(amount)};
      model.support = fill(locale, 'support.little_leaks', {rent_months: f.decimal(pick(facts, 'rent_months', 'rent_months_equivalent'))});
      break;
    }
    case 'peak_month': {
      const amount = pick(facts, 'amount_cents', 'spending_cents');
      setMoney(amount);
      const month = f.monthLabel(pick(facts, 'month'));
      model.label = month ? capitalize(month) : null;
      values = {...values, month, amount: f.money(amount)};
      model.support = fill(locale, 'support.peak_month', {calm_month: f.monthLabel(pick(facts, 'calmest_month')), calm_amount: f.money(pick(facts, 'calmest_amount_cents'))});
      break;
    }
    case 'busiest_day': {
      const amount = pick(facts, 'amount_cents', 'spending_cents');
      setMoney(amount);
      const date = f.dateLabel(pick(facts, 'date'));
      model.label = date;
      values = {...values, date, amount: f.money(amount)};
      model.support = fill(locale, 'support.busiest_day', {count: f.count(pick(facts, 'purchase_count', 'transaction_count'))});
      break;
    }
    case 'favourite_weekday_or_mcc': {
      const weekdayRaw = pick(facts, 'weekday_label') ?? (facts.weekday ?? null);
      const weekday = weekdayRaw === null ? null : (pick(facts, 'weekday_label') ? String(weekdayRaw) : f.weekday(weekdayRaw));
      const mcc = pick(facts, 'mcc_label', 'mcc_term');
      if (weekday) {
        model.big = capitalize(weekday);
        model.label = yr(locale, 'label.favourite_weekday');
        captionKeys = ['caption.favourite_weekday'];
        model.support = fill(locale, 'support.favourite_weekday_or_mcc', {mcc, mcc_count: f.count(pick(facts, 'mcc_count'))});
      } else if (mcc) {
        model.big = String(mcc);
        model.label = yr(locale, 'label.favourite_mcc');
        captionKeys = ['caption.favourite_mcc'];
      }
      values = {...values, weekday, mcc};
      break;
    }
    case 'archetype': {
      model.big = pick(facts, 'archetype_label', 'archetype');
      values = {...values, archetype: model.big};
      model.support = fill(locale, 'support.archetype', {previous: pick(facts, 'previous_archetype_label', 'previous_archetype')});
      break;
    }
    case 'closing':
      model.big = year === null || year === undefined ? null : String(year);
      model.label = yr(locale, 'label.closing');
      model.support = yr(locale, 'support.closing');
      break;
    default:
      break;
  }
  if (typeof aiCaption === 'string' && aiCaption.trim()) model.caption = aiCaption.trim();
  else {
    for (const key of captionKeys) { model.caption = fill(locale, key, values); if (model.caption) break; }
    if (!model.caption && kind === 'generic') model.caption = fillTemplate(card?.caption_template, {...facts, year});
    if (!model.caption) model.caption = yr(locale, 'caption.generic');
  }
  return model;
}

function visualHTML(visual, locale) {
  if (!visual) return '';
  if (visual.type === 'inout') {
    const max = Math.max(visual.inCents, visual.outCents, 1);
    const row = (label, cents, text, cls) => `<div class="yr-bar-row ${cls}"><span class="yr-bar-label">${esc(label)}</span><span class="yr-bar-track"><span class="yr-bar-fill" style="width:${(cents / max * 100).toFixed(2)}%"></span></span><span class="yr-bar-value">${esc(text)}</span></div>`;
    return `<div class="yr-visual yr-inout">${row(yr(locale, 'bar.in'), visual.inCents, visual.inText, 'yr-bar-in')}${row(yr(locale, 'bar.out'), visual.outCents, visual.outText, 'yr-bar-out')}</div>`;
  }
  if (visual.type === 'baskets') {
    const total = visual.parts.reduce((sum, p) => sum + p.cents, 0) || 1;
    const segments = visual.parts.map(p => `<span class="yr-seg yr-seg-${p.key}" style="flex-grow:${p.cents};width:${(p.cents / total * 100).toFixed(2)}%"></span>`).join('');
    const legend = visual.parts.map(p => `<li><i class="yr-dot yr-seg-${p.key}" aria-hidden="true"></i><span>${esc(p.name)}</span><b>${esc(p.share ? p.share + ' · ' + p.text : p.text)}</b></li>`).join('');
    return `<div class="yr-visual yr-baskets"><div class="yr-seg-bar" aria-hidden="true">${segments}</div><ul class="yr-legend">${legend}</ul></div>`;
  }
  return '';
}

/**
 * Render the full-screen story player for one card.
 * @param {object} review year_review result {year, complete, available, cards:[{id,kind,facts,caption_template}], captions?, closing_message?}
 * @param {object} options
 *   locale      'en'|'fi'|'sv'
 *   money       (cents:int) -> string, the app's formatter (default Intl EUR)
 *   monthLabel  ("YYYY-MM") -> string
 *   dateLabel   ("YYYY-MM-DD") -> string
 *   captions    {card_id: text} optional AI captions (may also carry closing_message); falls back to review.captions
 *   closingMessage optional AI closing text (else captions.closing_message / review.closing_message)
 *   index       current card index (clamped to the card range)
 *   paused      bool, renders the play button state
 *   autoAdvanceMs  current card progress animation duration in ms (CSS variable), default 6000
 * @returns {string} HTML: <div class="yr-story" role="dialog" aria-modal="true" aria-labelledby="yr-headline"> ... </div>
 *   Hooks: data-story-prev, data-story-next, data-story-close, data-story-toggle, data-story-save, data-story-ask,
 *   and data-count-cents on the headline number (for the count-up in attachStory).
 */
export function renderStory(review, options = {}) {
  const locale = normLocale(options.locale);
  const f = formatters(locale, options);
  const data = review && typeof review === 'object' ? review : {};
  const cards = Array.isArray(data.cards) ? data.cards.filter(card => card && typeof card === 'object') : [];
  const year = data.year ?? '';
  const closeBtn = `<button type="button" class="yr-close" data-story-close aria-label="${esc(yr(locale, 'ui.close'))}"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" fill="none"/></svg></button>`;
  if (data.available === false || !cards.length) {
    return `<div class="yr-story" role="dialog" aria-modal="true" aria-labelledby="yr-headline" data-story-root data-count="0" tabindex="-1"><div class="yr-frame"><div class="yr-top">${closeBtn}</div><section class="yr-card yr-kind-intro" data-kind="unavailable"><div class="yr-content"><p class="yr-eyebrow">${esc(yr(locale, 'ui.dialog'))}</p><h2 class="yr-headline" id="yr-headline"><span class="yr-label">${esc(yr(locale, 'ui.unavailable', {year}))}</span></h2></div></section></div></div>`;
  }
  const total = cards.length;
  const index = Math.min(Math.max(Number.isInteger(options.index) ? options.index : 0, 0), total - 1);
  const card = cards[index];
  const captions = options.captions && typeof options.captions === 'object' ? options.captions : (data.captions && typeof data.captions === 'object' ? data.captions : {});
  let ai = card.id !== undefined ? captions[card.id] : undefined;
  if (!ai && card.kind === 'closing') ai = options.closingMessage || captions.closing_message || data.closing_message;
  const model = cardModel(card, data, locale, f, ai);
  const last = index === total - 1;
  const duration = Number.isFinite(options.autoAdvanceMs) && options.autoAdvanceMs > 0 ? options.autoAdvanceMs : 6000;
  const bars = cards.map((_, i) => `<span class="yr-progress-bar" data-state="${i < index ? 'filled' : i === index ? 'current' : 'pending'}"><i></i></span>`).join('');
  const big = model.big === null || model.big === undefined ? '' : (model.bigCents !== null
    ? `<span class="yr-big"><span class="yr-big-value" aria-hidden="true" data-count-cents="${model.bigCents}">${esc(model.big)}</span><span class="yr-sr">${esc(model.big)}</span></span>`
    : `<span class="yr-big">${esc(model.big)}</span>`);
  const label = model.label ? `<span class="yr-label">${esc(model.label)}</span>` : '';
  const actions = last ? `<div class="yr-actions"><button type="button" class="yr-btn yr-btn-primary" data-story-save>${esc(yr(locale, 'ui.save'))}</button><button type="button" class="yr-btn yr-btn-secondary" data-story-ask>${esc(yr(locale, 'ui.ask'))}</button></div>` : '';
  const toggle = `<button type="button" class="yr-toggle" data-story-toggle aria-pressed="${options.paused ? 'true' : 'false'}" aria-label="${esc(yr(locale, options.paused ? 'ui.play' : 'ui.pause'))}"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${options.paused ? '<path d="M8 5l11 7-11 7z" fill="currentColor"/>' : '<path d="M8 5h3v14H8zM13 5h3v14h-3z" fill="currentColor"/>'}</svg></button>`;
  return `<div class="yr-story${options.paused ? ' yr-paused' : ''}" role="dialog" aria-modal="true" aria-labelledby="yr-headline" aria-describedby="yr-caption" data-story-root data-index="${index}" data-count="${total}" data-kind="${esc(model.kind)}" tabindex="-1" style="--yr-duration:${duration}ms">`
    + `<div class="yr-frame yr-kind-${esc(model.kind)}">`
    + `<div class="yr-top"><div class="yr-progress" role="progressbar" aria-label="${esc(yr(locale, 'ui.progress', {current: index + 1, total}))}" aria-valuemin="1" aria-valuemax="${total}" aria-valuenow="${index + 1}">${bars}</div><div class="yr-top-buttons">${toggle}${closeBtn}</div></div>`
    + `<button type="button" class="yr-tap yr-tap-prev" data-story-prev aria-label="${esc(yr(locale, 'ui.prev'))}"${index === 0 ? ' disabled' : ''}></button>`
    + `<button type="button" class="yr-tap yr-tap-next" data-story-next aria-label="${esc(yr(locale, 'ui.next'))}"${last ? ' disabled' : ''}></button>`
    + `<section class="yr-card" data-kind="${esc(model.kind)}" data-card-id="${esc(card.id ?? '')}" aria-roledescription="slide" aria-live="polite">`
    + `<div class="yr-content"><p class="yr-eyebrow">${esc(model.eyebrow)}</p><h2 class="yr-headline" id="yr-headline">${big}${label}</h2>${visualHTML(model.visual, locale)}<p class="yr-caption" id="yr-caption">${esc(model.caption)}</p>${model.support ? `<p class="yr-support">${esc(model.support)}</p>` : ''}${actions}</div>`
    + `</section></div></div>`;
}

/**
 * Story navigation controller (no DOM). Auto-advances one card every autoAdvanceMs; stops on the last card.
 * @param {object} options
 *   count          number of cards (>= 0)
 *   onIndex        (index:int, controller) -> void, called after every index change and on start()
 *   autoAdvanceMs  ms per card; 0/negative disables auto-advance (default 6000)
 *   index          initial index (default 0)
 *   scheduler      {setTimeout(fn, ms) -> id, clearTimeout(id), now() -> ms} injected for tests (default globals/Date.now)
 * @returns {{start, next, prev, goTo, pause, resume, toggle, destroy, readonly index, readonly paused, readonly isLast, readonly count}}
 *   next/prev/goTo return true when the index changed.
 */
export function createStoryController({count, onIndex, autoAdvanceMs = 6000, index = 0, scheduler} = {}) {
  const total = Math.max(0, Number.isInteger(count) ? count : 0);
  const sched = {
    setTimeout: scheduler?.setTimeout || ((fn, ms) => globalThis.setTimeout(fn, ms)),
    clearTimeout: scheduler?.clearTimeout || (id => globalThis.clearTimeout(id)),
    now: scheduler?.now || (() => Date.now()),
  };
  const auto = Number.isFinite(autoAdvanceMs) && autoAdvanceMs > 0;
  let current = Math.min(Math.max(Number.isInteger(index) ? index : 0, 0), Math.max(total - 1, 0));
  let paused = false, timer = null, startedAt = 0, remaining = autoAdvanceMs, destroyed = false;
  const clear = () => { if (timer !== null) { sched.clearTimeout(timer); timer = null; } };
  const schedule = ms => {
    clear();
    if (!auto || paused || destroyed || current >= total - 1) return;
    remaining = ms; startedAt = sched.now();
    timer = sched.setTimeout(() => { timer = null; api.next(); }, ms);
  };
  const emit = () => { if (typeof onIndex === 'function') onIndex(current, api); };
  const api = {
    start() { if (!total || destroyed) return; emit(); schedule(autoAdvanceMs); },
    goTo(target) {
      if (destroyed || !Number.isInteger(target) || target < 0 || target >= total || target === current) return false;
      current = target; remaining = autoAdvanceMs; emit(); schedule(autoAdvanceMs); return true;
    },
    next() { return api.goTo(current + 1); },
    prev() { return api.goTo(current - 1); },
    pause() {
      if (paused || destroyed) return;
      paused = true;
      if (timer !== null) { remaining = Math.max(0, remaining - (sched.now() - startedAt)); clear(); }
    },
    resume() { if (!paused || destroyed) return; paused = false; schedule(remaining > 0 ? remaining : autoAdvanceMs); },
    toggle() { if (paused) api.resume(); else api.pause(); return paused; },
    destroy() { clear(); destroyed = true; },
    get index() { return current; },
    get paused() { return paused; },
    get isLast() { return current === total - 1; },
    get count() { return total; },
  };
  return api;
}

/**
 * Wire a story into a container element and start it.
 * @param {HTMLElement} root container (e.g. a fixed overlay div); its innerHTML is replaced by render(index)
 * @param {object} options
 *   review         the year_review object (passed back to onSave/onAsk)
 *   render         (index:int, state:{paused:bool, autoAdvanceMs:int}) -> HTML string, usually
 *                  i => renderStory(review, {locale, money, monthLabel, dateLabel, captions, index: i, paused, autoAdvanceMs})
 *   count          number of cards (default review.cards.length)
 *   onClose        () -> void (close button, Escape, swipe down)
 *   onSave         (review) -> void (last card "Save to my profile")
 *   onAsk          (review) -> void (last card "Ask coach about my year")
 *   reducedMotion  bool; default matchMedia('(prefers-reduced-motion: reduce)'). Disables auto-advance and count-up.
 *   autoAdvanceMs  default 6000
 *   money          (cents) -> string; enables the headline count-up (final text is always the rendered exact value)
 *   scheduler, raf injection points for tests ({setTimeout, clearTimeout, now}; raf(fn) -> id)
 * @returns {function} detach(): stops timers, removes listeners, restores focus to the element focused before opening
 */
export function attachStory(root, options = {}) {
  const doc = root.ownerDocument || globalThis.document;
  const win = doc?.defaultView || globalThis;
  const review = options.review || {};
  const count = Number.isInteger(options.count) ? options.count : (Array.isArray(review.cards) ? review.cards.length : 0);
  const reduced = typeof options.reducedMotion === 'boolean' ? options.reducedMotion : !!win.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
  const autoAdvanceMs = reduced ? 0 : (Number.isFinite(options.autoAdvanceMs) ? options.autoAdvanceMs : 6000);
  const raf = options.raf || win.requestAnimationFrame?.bind(win);
  const caf = options.caf || win.cancelAnimationFrame?.bind(win) || (() => {});
  const previousFocus = doc?.activeElement || null;
  let frame = null, holdTimer = null, held = false, pointer = null, suppressClick = false, firstRender = true;

  const countUp = () => {
    if (frame !== null) { caf(frame); frame = null; }
    const node = root.querySelector('[data-count-cents]');
    // V4: no count-up. A half-counted headline next to the exact caption read as two different numbers.
    if (!node || reduced || !options.countUp || typeof options.money !== 'function' || typeof raf !== 'function') return;
    const target = Number(node.getAttribute('data-count-cents'));
    const finalText = node.textContent;
    if (!Number.isSafeInteger(target) || target === 0) return;
    const duration = 900;
    let start = null;
    const step = time => {
      if (start === null) start = time;
      const t = Math.min(1, (time - start) / duration);
      if (t >= 1) { node.textContent = finalText; frame = null; return; }
      node.textContent = options.money(Math.round(target * (1 - Math.pow(1 - t, 3))));
      frame = raf(step);
    };
    node.textContent = options.money(0);
    frame = raf(step);
  };
  const paint = index => {
    const focusInside = root.contains(doc?.activeElement);
    const focusedHook = focusInside ? ['data-story-next', 'data-story-prev', 'data-story-toggle'].find(attr => doc.activeElement.hasAttribute?.(attr)) : null;
    root.innerHTML = options.render(index, {paused: controller ? controller.paused : false, autoAdvanceMs});
    const dialog = root.querySelector('[role="dialog"]') || root;
    if (reduced) dialog.classList?.add('yr-reduced');
    let target = focusedHook ? root.querySelector('[' + focusedHook + ']:not([disabled])') : null;
    if (!target && (firstRender || focusInside)) target = dialog;
    target?.focus?.({preventScroll: true});
    firstRender = false;
    countUp();
  };
  let controller = null;
  controller = createStoryController({count, autoAdvanceMs, scheduler: options.scheduler, onIndex: index => paint(index)});
  const repaint = () => paint(controller.index);
  const setPaused = value => {
    if (value === controller.paused) return;
    if (value) controller.pause(); else controller.resume();
    const dialog = root.querySelector('.yr-story');
    dialog?.classList?.toggle('yr-paused', controller.paused);
  };

  const onClick = event => {
    if (suppressClick) { suppressClick = false; event.preventDefault(); return; }
    const el = event.target?.closest?.('[data-story-prev],[data-story-next],[data-story-close],[data-story-toggle],[data-story-save],[data-story-ask]');
    if (!el || !root.contains(el)) return;
    if (el.hasAttribute('data-story-prev')) controller.prev();
    else if (el.hasAttribute('data-story-next')) controller.next();
    else if (el.hasAttribute('data-story-close')) options.onClose?.();
    else if (el.hasAttribute('data-story-toggle')) { controller.toggle(); repaint(); }
    else if (el.hasAttribute('data-story-save')) { controller.pause(); options.onSave?.(review); }
    else if (el.hasAttribute('data-story-ask')) { controller.pause(); options.onAsk?.(review); }
  };
  const onKey = event => {
    if (event.key === 'ArrowRight') { event.preventDefault(); controller.next(); }
    else if (event.key === 'ArrowLeft') { event.preventDefault(); controller.prev(); }
    else if (event.key === 'Escape') { event.preventDefault(); options.onClose?.(); }
    else if (event.key === 'Tab') {
      const focusable = [...root.querySelectorAll('button:not([disabled]),[href],[tabindex]:not([tabindex="-1"])')];
      if (!focusable.length) return;
      const first = focusable[0], lastEl = focusable[focusable.length - 1];
      if (event.shiftKey && (doc.activeElement === first || !root.contains(doc.activeElement) || doc.activeElement === root.querySelector('[role="dialog"]'))) { event.preventDefault(); lastEl.focus(); }
      else if (!event.shiftKey && doc.activeElement === lastEl) { event.preventDefault(); first.focus(); }
    }
  };
  const isAction = target => !!target?.closest?.('[data-story-save],[data-story-ask],[data-story-close],[data-story-toggle]');
  const onDown = event => {
    if (isAction(event.target)) return;
    pointer = {x: event.clientX, y: event.clientY, id: event.pointerId};
    held = false;
    holdTimer = win.setTimeout(() => { held = true; setPaused(true); }, 220);
  };
  const onUp = event => {
    if (!pointer) return;
    win.clearTimeout(holdTimer);
    const dx = event.clientX - pointer.x, dy = event.clientY - pointer.y;
    pointer = null;
    if (held) { held = false; suppressClick = true; setPaused(false); return; }
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) { suppressClick = true; if (dx < 0) controller.next(); else controller.prev(); }
    else if (dy > 90 && Math.abs(dy) > Math.abs(dx)) { suppressClick = true; options.onClose?.(); }
  };
  const onCancel = () => { win.clearTimeout(holdTimer); pointer = null; if (held) { held = false; setPaused(false); } };
  const onContext = event => { if (pointer || held) event.preventDefault(); };

  root.addEventListener('click', onClick);
  root.addEventListener('keydown', onKey);
  root.addEventListener('pointerdown', onDown);
  root.addEventListener('pointerup', onUp);
  root.addEventListener('pointercancel', onCancel);
  root.addEventListener('contextmenu', onContext);
  controller.start();
  return function detach() {
    controller.destroy();
    win.clearTimeout(holdTimer);
    if (frame !== null) caf(frame);
    root.removeEventListener('click', onClick);
    root.removeEventListener('keydown', onKey);
    root.removeEventListener('pointerdown', onDown);
    root.removeEventListener('pointerup', onUp);
    root.removeEventListener('pointercancel', onCancel);
    root.removeEventListener('contextmenu', onContext);
    if (previousFocus && typeof previousFocus.focus === 'function' && doc?.contains?.(previousFocus)) previousFocus.focus();
  };
}

/**
 * Home banner announcing a ready year review.
 * @param {number|string} year e.g. 2025
 * @param {string} locale 'en'|'fi'|'sv'
 * @returns {string} HTML <aside class="yr-banner"> with an open button (data-story-open="{year}")
 *   and a dismiss button (data-story-dismiss="{year}")
 */
export function renderYearBanner(year, locale = 'en') {
  const lang = normLocale(locale);
  const y = esc(year);
  const title = yr(lang, 'banner.title', {year: String(year ?? '')});
  return `<aside class="yr-banner" aria-labelledby="yr-banner-title-${y}"><div class="yr-banner-art" aria-hidden="true"><span>${y}</span></div><div class="yr-banner-text"><p class="yr-banner-eyebrow">${esc(yr(lang, 'banner.eyebrow'))}</p><h3 id="yr-banner-title-${y}">${esc(title)}</h3><p>${esc(yr(lang, 'banner.help'))}</p><button type="button" class="yr-banner-open" data-story-open="${y}">${esc(yr(lang, 'banner.open'))}</button></div><button type="button" class="yr-banner-dismiss" data-story-dismiss="${y}" aria-label="${esc(yr(lang, 'banner.dismiss'))}"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" fill="none"/></svg></button></aside>`;
}
