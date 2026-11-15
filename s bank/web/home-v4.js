/**
 * Home as the Payday Plan (V4 lane H).
 *
 * Top to bottom: plan hero ("€X a day until payday" + why), one coach insight with up to two
 * actions, this month (in / spent / left over), the surprise buffer, goals and plans, a small
 * personalise row, and seasonal extras. Pure helpers are exported for tests; createHome() wires
 * them to the app. All amounts are integer cents. All text exists in EN, FI and SV.
 */

import { updateDraftPreview } from './draft-card.js';

const LOCALES = ['en', 'fi', 'sv'];

const COPY = {
  'title': ['Your payday plan', 'Palkkapäivän suunnitelma', 'Din lönedagsplan'],
  'eyebrow': ['Payday plan', 'Palkkapäivän suunnitelma', 'Lönedagsplan'],
  'canUse': ['You can use about', 'Voit käyttää noin', 'Du kan använda ungefär'],
  'perDay': ['a day for food, getting around and fun', 'päivässä ruokaan, liikkumiseen ja muuhun', 'om dagen för mat, resor och nöjen'],
  'perDayFallback': ['a day for the next {days} days', 'päivässä seuraavat {days} päivää', 'om dagen de kommande {days} dagarna'],
  'paydayIn': ['Payday in {days} days · {date}', 'Palkkapäivään {days} päivää · {date}', 'Lönedag om {days} dagar · {date}'],
  'paydayTomorrow': ['Payday tomorrow · {date}', 'Palkkapäivä huomenna · {date}', 'Lönedag i morgon · {date}'],
  'noPayday': ['No regular salary found yet, so this plan covers {days} days.', 'Säännöllistä palkkaa ei vielä löytynyt, joten suunnitelma kattaa {days} päivää.', 'Ingen regelbunden lön hittades än, så planen gäller {days} dagar.'],
  'balance': ['In your account', 'Tililläsi', 'På ditt konto'],
  'seg.held': ['Held back', 'Varattu', 'Avsatt'],
  'seg.buffer': ['Buffer', 'Puskuri', 'Buffert'],
  'seg.everyday': ['Everyday basics', 'Arjen perusmenot', 'Vardagsutgifter'],
  'seg.free': ['Free to spend', 'Käytettävissä', 'Fritt att använda'],
  'seg.extra': ['Could be saved', 'Voisi säästää', 'Kan sparas'],
  'why': ['Why this number?', 'Miksi tämä summa?', 'Varför det här beloppet?'],
  'why.balance': ['In your account now', 'Tililläsi nyt', 'På ditt konto nu'],
  'why.reserve': ['Safety cushion, kept untouched', 'Turvatyyny, johon ei kosketa', 'Säkerhetsbuffert som lämnas orörd'],
  'why.buffer': ['Surprise buffer, this payday', 'Yllätyspuskuri tältä palkkakaudelta', 'Överraskningsbuffert den här perioden'],
  'why.everyday': ['Everyday basics until payday', 'Arjen perusmenot palkkapäivään asti', 'Vardagsutgifter fram till lönedagen'],
  'why.extra': ['More than you usually need: could be saved', 'Enemmän kuin yleensä tarvitset: voisi säästää', 'Mer än du brukar behöva: kan sparas'],
  'why.free': ['Free to spend until payday', 'Käytettävissä palkkapäivään asti', 'Fritt att använda fram till lönedagen'],
  'why.perDay': ['{amount} over {days} days is about {perDay} a day.', '{amount} jaettuna {days} päivälle on noin {perDay} päivässä.', '{amount} på {days} dagar blir ungefär {perDay} om dagen.'],
  'why.note': ['Your next salary is counted only when it arrives. Nothing moves from your account.', 'Seuraava palkka lasketaan mukaan vasta, kun se on tilillä. Tililtäsi ei siirry rahaa.', 'Nästa lön räknas först när den har kommit. Inga pengar flyttas från ditt konto.'],
  'why.held': ['Held back for what is due before payday', 'Varattu ennen palkkapäivää erääntyviin', 'Avsatt för det som förfaller före lönedagen'],
  'kind.saving': ['Your planned saving', 'Suunnittelemasi säästö', 'Ditt planerade sparande'],
  'kind.savingPct': ['Your planned saving, {pct} of salary', 'Suunnittelemasi säästö, {pct} palkasta', 'Ditt planerade sparande, {pct} av lönen'],
  'kind.tax': ['Tax set-aside', 'Verovaraus', 'Skatteavsättning'],
  'kind.loan': ['Loan payment', 'Lainanlyhennys', 'Låneamortering'],
  'told': ['You told me', 'Kerroit minulle', 'Du berättade'],
  'shortfall': ['Bills before payday are {amount} more than you have free.', 'Ennen palkkapäivää erääntyvät laskut ovat {amount} enemmän kuin sinulla on vapaana.', 'Räkningarna före lönedagen är {amount} mer än du har fritt.'],
  'steady': ['Careful mode is on because you told me about {event}. A month of must-pays is kept aside.', 'Varovainen tila on päällä, koska kerroit tilanteestasi ({event}). Kuukauden välttämättömät menot on pidetty sivussa.', 'Försiktigt läge är på eftersom du berättade om {event}. En månads nödvändiga utgifter hålls undan.'],
  'event.job_loss': ['losing your job', 'työpaikan menetys', 'att du har förlorat jobbet'],
  'event.income_drop': ['a drop in income', 'tulojen lasku', 'att inkomsten har minskat'],
  'event.large_loss': ['a large unexpected cost', 'suuri yllättävä meno', 'en stor oväntad kostnad'],
  'event.other': ['a change in your life', 'elämänmuutos', 'en förändring i ditt liv'],
  'loading': ['Working out your plan…', 'Lasketaan suunnitelmaasi…', 'Räknar ut din plan…'],
  'unavailable': ['Your plan is not available right now. Please try again in a moment.', 'Suunnitelmasi ei ole juuri nyt saatavilla. Yritä hetken päästä uudelleen.', 'Din plan är inte tillgänglig just nu. Försök igen om en stund.'],
  'insight.eyebrow': ['From your coach', 'Valmentajaltasi', 'Från din coach'],
  'insight.buffer': ['Surprise costs like the dentist or a repair came to about {amount} a month for you last year. A little set aside each payday means the next one won’t hurt.', 'Yllättäviä menoja, kuten hammaslääkäri tai korjaus, oli sinulla viime vuonna noin {amount} kuukaudessa. Pieni summa sivuun joka palkkapäivä, niin seuraava ei satu.', 'Oväntade kostnader som tandläkare eller reparationer blev ungefär {amount} i månaden för dig förra året. Lite undan varje lönedag gör att nästa inte svider.'],
  'insight.extra': ['You have {amount} more than you usually need before payday. Moving it to savings keeps it from slipping into everyday spending.', 'Sinulla on {amount} enemmän kuin tavallisesti tarvitset ennen palkkapäivää. Säästöön siirrettynä se ei huku arkeen.', 'Du har {amount} mer än du brukar behöva före lönedagen. Flyttar du det till sparande försvinner det inte i vardagen.'],
  'insight.shortfall': ['Money is tight before payday. Let’s look together at which bills could wait or be split, and what to do first.', 'Rahaa on niukasti ennen palkkapäivää. Katsotaan yhdessä, mitkä laskut voisivat odottaa tai jakautua osiin ja mitä tehdä ensin.', 'Pengarna är knappa före lönedagen. Vi tittar tillsammans på vilka räkningar som kan vänta eller delas upp, och vad du gör först.'],
  'insight.steady': ['Your safety cushion comes first right now: a month of must-pays is kept aside before anything else. I won’t push saving goals until things settle.', 'Turvatyyny on nyt etusijalla: kuukauden välttämättömät menot pidetään sivussa ennen kaikkea muuta. En ehdota säästötavoitteita, ennen kuin tilanne tasaantuu.', 'Din säkerhetsbuffert kommer först just nu: en månads nödvändiga utgifter hålls undan före allt annat. Jag föreslår inga sparmål förrän läget har lugnat sig.'],
  'insight.topCategory': ['{category} was your biggest everyday extra this month, {amount}.', '{category} oli tämän kuun suurin arjen lisämeno, {amount}.', '{category} var månadens största vardagsextra, {amount}.'],
  'chip.category': ['Look at {category}', 'Tarkastele: {category}', 'Titta på {category}'],
  'q.category': ['How much did I spend on {category} this month, and how could I spend less?', 'Paljonko käytin tässä kuussa kohteeseen {category}, ja miten voisin käyttää vähemmän?', 'Hur mycket spenderade jag på {category} den här månaden, och hur kan jag spendera mindre?'],
  'insight.spentLess': ['You spent {amount} less than in {month}. That is room for your plan.', 'Käytit {amount} vähemmän kuin {month}. Se on tilaa suunnitelmallesi.', 'Du spenderade {amount} mindre än i {month}. Det ger utrymme för din plan.'],
  'insight.spentMore': ['You spent {amount} more than in {month}. Want to see where it went?', 'Käytit {amount} enemmän kuin {month}. Haluatko nähdä, mihin rahat menivät?', 'Du spenderade {amount} mer än i {month}. Vill du se vart pengarna gick?'],
  'insight.calm': ['Your bills before payday are covered. Spending about {amount} a day keeps you on plan.', 'Ennen palkkapäivää erääntyvät laskut on katettu. Noin {amount} päivässä pitää sinut suunnitelmassa.', 'Räkningarna före lönedagen är täckta. Ungefär {amount} om dagen håller dig på plan.'],
  'insight.savingTold': ['You told me you want to save {pct} of your salary, so that is held back first.', 'Kerroit haluavasi säästää {pct} palkastasi, joten se varataan ensin.', 'Du berättade att du vill spara {pct} av lönen, så det avsätts först.'],
  'chip.buffer': ['Put {amount} in your surprise buffer', 'Laita {amount} yllätyspuskuriin', 'Lägg {amount} i överraskningsbufferten'],
  'chip.where': ['See where it goes', 'Katso, mihin rahat menevät', 'Se vart pengarna går'],
  'chip.goal': ['Make it a goal', 'Tee siitä tavoite', 'Gör det till ett mål'],
  'chip.ask': ['Ask the coach', 'Kysy valmentajalta', 'Fråga coachen'],
  'chip.due': ['See what is due', 'Katso, mitä erääntyy', 'Se vad som förfaller'],
  'chip.situation': ['Update my situation', 'Päivitä tilanteeni', 'Uppdatera min situation'],
  'q.shortfall': ['My bills before payday are more than I have. What can I do?', 'Laskuni ennen palkkapäivää ovat enemmän kuin minulla on rahaa. Mitä voin tehdä?', 'Mina räkningar före lönedagen är mer än jag har. Vad kan jag göra?'],
  'q.steady': ['What should I focus on while money is tight?', 'Mihin minun kannattaa keskittyä, kun rahaa on vähän?', 'Vad ska jag fokusera på när pengarna är knappa?'],
  'q.save': ['How could I save more?', 'Miten voisin säästää enemmän?', 'Hur kan jag spara mer?'],
  'q.safe': ['What can I safely spend until payday?', 'Paljonko voin turvallisesti käyttää palkkapäivään asti?', 'Hur mycket kan jag tryggt spendera fram till lönedagen?'],
  'month.title': ['This month', 'Tämä kuukausi', 'Den här månaden'],
  'month.choose': ['Choose month', 'Valitse kuukausi', 'Välj månad'],
  'month.in': ['Money in', 'Tulot', 'Pengar in'],
  'month.out': ['Spent', 'Menot', 'Utgifter'],
  'month.left': ['Left over', 'Jäi yli', 'Blev över'],
  'month.vs': ['{amount} vs {month}', '{amount} vrt. {month}', '{amount} jmf. {month}'],
  'month.same': ['Same as {month}', 'Sama kuin {month}', 'Samma som {month}'],
  'month.empty': ['No activity recorded for this month.', 'Tälle kuukaudelle ei ole kirjattu tapahtumia.', 'Ingen aktivitet registrerad för den här månaden.'],
  'buffer.title': ['Surprise buffer', 'Yllätyspuskuri', 'Överraskningsbuffert'],
  'buffer.help': ['For costs that always come, just not on schedule: the dentist, the car, a broken washing machine.', 'Menoihin, jotka tulevat aina, mutta eivät aikataulussa: hammaslääkäri, auto, rikkoutunut pesukone.', 'För kostnader som alltid kommer, bara inte enligt schema: tandläkaren, bilen, en trasig tvättmaskin.'],
  'buffer.basis': ['Last 12 months: {total} in surprises, the biggest {largest}.', 'Viimeiset 12 kk: yllätysmenoja {total}, suurin {largest}.', 'Senaste 12 månaderna: {total} i överraskningar, den största {largest}.'],
  'buffer.none': ['No surprise costs in the last year. A small buffer still helps when one comes.', 'Viime vuonna ei ollut yllätysmenoja. Pieni puskuri auttaa silti, kun sellainen tulee.', 'Inga överraskningar det senaste året. En liten buffert hjälper ändå när en kommer.'],
  'buffer.suggest': ['Suggested buffer', 'Ehdotettu puskuri', 'Föreslagen buffert'],
  'buffer.pace': ['{amount} a month, ready by {date}', '{amount} kuukaudessa, valmis {date}', '{amount} i månaden, klar {date}'],
  'buffer.action': ['Set aside {amount} monthly', 'Varaa {amount} kuukausittain', 'Avsätt {amount} i månaden'],
  'buffer.progress': ['{saved} of {target}', '{saved} / {target}', '{saved} av {target}'],
  'buffer.planned': ['Plan saved: about {amount} each payday until {date}.', 'Suunnitelma tallennettu: noin {amount} joka palkkapäivä {date} asti.', 'Plan sparad: ungefär {amount} varje lönedag till {date}.'],
  'buffer.later': ['Start setting money aside once the bills before payday are covered. Your coach will remind you.', 'Aloita säästäminen, kun palkkapäivää edeltävät laskut on katettu. Valmentaja muistuttaa sinua.', 'Börja lägga undan när räkningarna före lönedagen är täckta. Coachen påminner dig.'],
  'buffer.change': ['Change', 'Muuta', 'Ändra'],
  'draft.title': ['Start your surprise buffer', 'Aloita yllätyspuskuri', 'Starta din överraskningsbuffert'],
  'draft.intro': ['This saves a plan: about {amount} set aside on each payday. No money moves from your account.', 'Tämä tallentaa suunnitelman: noin {amount} sivuun joka palkkapäivä. Tililtäsi ei siirry rahaa.', 'Det här sparar en plan: ungefär {amount} undan varje lönedag. Inga pengar flyttas från ditt konto.'],
  'draft.name': ['Name', 'Nimi', 'Namn'],
  'draft.target': ['Buffer target', 'Puskurin tavoite', 'Buffertmål'],
  'draft.date': ['Ready by', 'Valmis viimeistään', 'Klar senast'],
  'draft.saved': ['Already set aside', 'Jo sivussa', 'Redan undanlagt'],
  'draft.save': ['Save my plan', 'Tallenna suunnitelma', 'Spara planen'],
  'draft.preview': ['About {amount} a month for {months} months.', 'Noin {amount} kuukaudessa {months} kuukauden ajan.', 'Ungefär {amount} i månaden i {months} månader.'],
  'draft.defaultName': ['Surprise buffer', 'Yllätyspuskuri', 'Överraskningsbuffert'],
  'draft.saved.notice': ['Your surprise buffer plan is saved. No money was moved.', 'Yllätyspuskurin suunnitelma on tallennettu. Rahaa ei siirretty.', 'Planen för överraskningsbufferten är sparad. Inga pengar flyttades.'],
  'goals.title': ['Goals and plans', 'Tavoitteet ja suunnitelmat', 'Mål och planer'],
  'goals.all': ['All goals', 'Kaikki tavoitteet', 'Alla mål'],
  'goals.line': ['{saved} of {target} · by {date}', '{saved} / {target} · {date} mennessä', '{saved} av {target} · senast {date}'],
  'goals.monthly': ['{amount} a month', '{amount} kk', '{amount}/mån'],
  'goals.wish': ['A wish to explore', 'Tutkittava toive', 'En önskan att utforska'],
  'goals.empty': ['Nothing planned yet. A wish is enough to start.', 'Ei vielä suunnitelmia. Toive riittää alkuun.', 'Inget planerat än. En önskan räcker för att börja.'],
  'goals.start': ['Start a goal', 'Aloita tavoite', 'Starta ett mål'],
  'personal.title': ['Make the plan yours', 'Tee suunnitelmasta omasi', 'Gör planen till din'],
  'personal.help': ['Tell the coach a little about you, and the plan fits your life.', 'Kerro valmentajalle vähän itsestäsi, niin suunnitelma sopii elämääsi.', 'Berätta lite om dig för coachen, så passar planen ditt liv.'],
  'personal.start': ['Tell the coach about you', 'Kerro itsestäsi valmentajalle', 'Berätta om dig för coachen'],
  'personal.known1': ['Your coach knows 1 thing you told it', 'Valmentajasi tietää yhden asian, jonka kerroit', 'Din coach vet 1 sak du har berättat'],
  'personal.known': ['Your coach knows {count} things you told it', 'Valmentajasi tietää {count} asiaa, jotka kerroit', 'Din coach vet {count} saker du har berättat'],
  'personal.review': ['Review', 'Tarkista', 'Granska'],
  'personal.prefs': ['Preferences', 'Asetukset', 'Inställningar'],
  'seasonal': ['Also this season', 'Myös nyt ajankohtaista', 'Också aktuellt nu'],
};

export const HOME_MESSAGES = Object.freeze(Object.fromEntries(LOCALES.map((locale, index) => [
  locale, Object.freeze(Object.fromEntries(Object.entries(COPY).map(([key, values]) => [key, values[index]])))])));

const lang = locale => (LOCALES.includes(locale) ? locale : 'en');
/** Localized Home copy with {name} placeholders. */
export function hm(locale, key, values = {}) {
  const template = HOME_MESSAGES[lang(locale)][key] ?? HOME_MESSAGES.en[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_, name) => (values[name] ?? '{' + name + '}'));
}
const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
const int = value => (Number.isSafeInteger(value) ? value : null);
const pos = value => Math.max(0, int(value) ?? 0);
const TAG = {en: 'en-IE', fi: 'fi-FI', sv: 'sv-FI'};

/** Default formatters for a locale (used by tests and as a fallback). */
export function formatters(locale = 'en') {
  const tag = TAG[lang(locale)];
  const currency = digits => new Intl.NumberFormat(tag, {style: 'currency', currency: 'EUR', minimumFractionDigits: digits, maximumFractionDigits: digits});
  const day = value => new Date(String(value).slice(0, 10) + 'T12:00:00Z');
  const safe = format => value => { const parsed = day(value); return value && !Number.isNaN(parsed.valueOf()) ? format.format(parsed) : ''; };
  return {
    money: cents => (int(cents) === null ? '—' : currency(2).format(cents / 100)),
    whole: cents => (int(cents) === null ? '—' : currency(0).format(Math.round(cents / 100))),
    floor: cents => (int(cents) === null ? '—' : currency(0).format(Math.floor(cents / 100))),
    shortDate: safe(new Intl.DateTimeFormat(tag, {weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC'})),
    date: safe(new Intl.DateTimeFormat(tag, {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'})),
    dayMonth: safe(new Intl.DateTimeFormat(tag, {day: 'numeric', month: 'short', timeZone: 'UTC'})),
    month: month => new Intl.DateTimeFormat(tag, {month: 'long', timeZone: 'UTC'}).format(day(month + '-01')),
    monthYearShort: month => new Intl.DateTimeFormat(tag, {month: 'short', year: 'numeric', timeZone: 'UTC'}).format(day(month + '-01')),
    monthShort: month => new Intl.DateTimeFormat(tag, {month: 'short', timeZone: 'UTC'}).format(day(month + '-01')),
    monthYear: month => new Intl.DateTimeFormat(tag, {month: 'long', year: 'numeric', timeZone: 'UTC'}).format(day(month + '-01')),
    percent: value => new Intl.NumberFormat(tag, {style: 'percent', maximumFractionDigits: 1}).format(Number(value) / 100),
  };
}

const LOAN_TYPES = new Set(['loan_payment', 'loan_repayment', 'mortgage_payment', 'debt_payment']);
const TOLD_SOURCES = new Set(['declared', 'profile', 'you_told_me', 'money_profile']);

/**
 * One plan shape from either API shape.
 * - Lane N `spending_plan`: {balance_cents, next_payday, days_to_payday, held_back[], everyday_cents, buffer_cents,
 *   reserve_floor_cents, free_cents, per_day_cents, extra_cents, ...}
 * - Current `safe_until_payday`: {starting_balance_cents, next_payday, days_until_payday, committed_items[],
 *   planned_saving_cents, reserve_floor_cents, free_cents, safe_to_save_cents, ...}. Its own split is used:
 *   what could move to savings is "could be saved"; the rest of the free money is spendable.
 * Returns null when the input has neither shape. Every amount is nonnegative integer cents, except
 * shortfall (the uncovered gap when bills exceed what is free).
 */
export function normalizePlan(raw) {
  if (!raw || typeof raw !== 'object') return null;
  if (Array.isArray(raw.held_back) && int(raw.balance_cents) !== null) {
    const items = [], cushion = {reserve: 0, buffer: 0};
    for (const item of raw.held_back) {
      const amount = pos(item?.amount_cents);
      if (!amount) continue;
      const kind = ['bill', 'loan', 'tax', 'goal', 'buffer', 'reserve'].includes(item.kind) ? item.kind : 'bill';
      if (kind === 'reserve' || kind === 'buffer') { cushion[kind] += amount; continue; }
      items.push({kind, label: String(item.label || ''), amount, date: item.date || null, told: TOLD_SOURCES.has(item.source) || item.told === true});
    }
    const reserve = Math.max(cushion.reserve, raw.held_back.some(item => item?.kind === 'reserve') ? 0 : pos(raw.reserve_floor_cents));
    const buffer = Math.max(cushion.buffer, raw.held_back.some(item => item?.kind === 'buffer') ? 0 : pos(raw.buffer_cents));
    const free = int(raw.free_cents) ?? 0, extra = Math.min(pos(raw.extra_cents), Math.max(free, 0));
    const spendable = int(raw.spendable_cents) !== null ? pos(raw.spendable_cents) : Math.max(free - extra, 0);
    const days = Math.max(1, int(raw.days_to_payday) ?? int(raw.days_until_payday) ?? 1);
    const heldTotal = items.reduce((sum, item) => sum + item.amount, 0);
    const everyday = pos(raw.everyday_cents);
    const shortfall = int(raw.shortfall_cents) !== null ? pos(raw.shortfall_cents) : Math.max(0, heldTotal + reserve + buffer + everyday - pos(raw.balance_cents));
    return {shape: 'plan', asOf: raw.as_of || null, balance: int(raw.balance_cents), nextPayday: raw.next_payday || null, days,
      paydayKnown: (raw.basis?.payday_source || raw.payday_source || 'detected') !== 'fallback_30_days', items, heldTotal, reserve, buffer,
      everyday, spendable, extra, perDay: int(raw.per_day_cents) ?? Math.floor((spendable + everyday) / days), shortfall,
      steady: Boolean(raw.steady_mode || raw.basis?.steady_mode || raw.basis?.coaching_mode === 'steady')};
  }
  if (int(raw.starting_balance_cents) !== null && raw.next_payday) {
    const items = (raw.committed_items || []).map(item => ({
      kind: LOAN_TYPES.has(item.transaction_type) || (item.source === 'declared' && /loan|debt|mortgage/i.test(String(item.label))) ? 'loan' : 'bill',
      label: String(item.label || ''), amount: pos(item.amount_cents), date: item.date || null, told: TOLD_SOURCES.has(item.source),
    })).filter(item => item.amount);
    if (pos(raw.planned_saving_cents)) items.push({kind: 'goal', label: '', amount: pos(raw.planned_saving_cents), date: null, told: true, saving: true});
    const heldTotal = items.reduce((sum, item) => sum + item.amount, 0);
    const days = Math.max(1, int(raw.days_until_payday) ?? 1);
    const free = int(raw.free_cents) ?? 0;
    const extra = raw.safe_to_save_available === false ? 0 : Math.min(pos(raw.safe_to_save_cents), Math.max(free, 0));
    const spendable = Math.max(free, 0) - extra;
    return {shape: 'legacy', asOf: raw.reference_date || null, balance: int(raw.starting_balance_cents), nextPayday: raw.next_payday, days,
      paydayKnown: raw.payday_source !== 'fallback_30_days', items, heldTotal, reserve: pos(raw.reserve_floor_cents), buffer: 0,
      everyday: 0, spendable, extra, perDay: Math.floor(spendable / days), shortfall: Math.max(pos(raw.shortfall_cents), free < 0 ? -free : 0),
      steady: Boolean(raw.steady_mode)};
  }
  return null;
}

/** Bar segments (key, cents, share 0..1) for a normalized plan; shares sum to 1 when anything is shown. */
export function planSegments(plan) {
  if (!plan) return [];
  const rows = [['held', plan.heldTotal], ['buffer', plan.reserve + plan.buffer], ['everyday', plan.everyday], ['free', plan.spendable], ['extra', plan.extra]]
    .filter(([, cents]) => cents > 0);
  const total = rows.reduce((sum, [, cents]) => sum + cents, 0);
  return rows.map(([key, cents]) => ({key, cents, share: total ? cents / total : 0}));
}

/** The active life event that put the profile into careful (steady) mode, or null. */
export function steadyEvent(profile) {
  const entries = (profile?.entries || []).filter(entry => entry.key === 'life_event' && entry.active !== false && entry.value && !entry.value.ended);
  const careful = entries.filter(entry => ['job_loss', 'income_drop', 'large_loss'].includes(entry.value.type));
  const list = careful.length ? careful : entries;
  if (!list.length) return null;
  return [...list].sort((a, b) => String(b.value.since || '').localeCompare(String(a.value.since || '')))[0].value.type;
}
const profileValue = (profile, key) => {
  const entry = (profile?.entries || []).find(item => item.key === key && item.active !== false);
  return entry ? entry.value : null;
};

/** Monthly set-aside, target and months for a surprise buffer from irregular_buffer data. */
export function bufferPlan(buffer) {
  if (!buffer || buffer.available === false) return null;
  const average = pos(buffer.suggested_monthly_set_aside_cents ?? buffer.monthly_average_cents);
  const monthly = Math.max(1000, Math.ceil(average / 1000) * 1000);
  const largest = pos(buffer.largest?.amount_cents);
  const target = Math.max(5000, Math.ceil(Math.max(largest, average * 3) / 5000) * 5000);
  return {monthly, target, months: Math.max(1, Math.ceil(target / monthly)), average, total: pos(buffer.total_cents), largest: buffer.largest || null, count: pos(buffer.count)};
}

/** Categories the customer asked the coach never to suggest cutting: server profile, plus the local preference. */
export function protectedCategories(profile, localPreference = null) {
  const list = profileValue(profile, 'protected_categories');
  const names = new Set((Array.isArray(list) ? list : []).map(name => String(name).toLowerCase()));
  if (localPreference && localPreference !== 'none') names.add(String(localPreference).toLowerCase());
  return names;
}

/** The biggest discretionary (everyday extra) category this month that is not protected, or null. */
export function topFlexibleCategory(rows = [], protectedNames = new Set()) {
  const totals = new Map();
  for (const row of rows || []) {
    if (row.role !== 'discretionary' || !(row.amount_cents < 0) || !row.category) continue;
    if (protectedNames.has(String(row.category).toLowerCase())) continue;
    totals.set(row.category, (totals.get(row.category) || 0) - row.amount_cents);
  }
  const [best] = [...totals].sort((a, b) => b[1] - a[1]);
  return best && best[1] >= 2000 ? {category: best[0], cents: best[1]} : null;
}

/** The month tiles: in / spent / left over, with change versus the previous month. */
export function monthTiles(overview, previous) {
  const values = data => {
    if (!data) return null;
    const income = int(data.salary_cents) !== null && int(data.other_income_cents) !== null ? data.salary_cents + data.other_income_cents : null;
    const spent = int(data.consumption_cents);
    return {in: income, out: spent, left: income !== null && spent !== null ? income - spent : null};
  };
  const now = values(overview), before = values(previous);
  if (!now) return [];
  return ['in', 'out', 'left'].filter(key => now[key] !== null).map(key => ({
    key, cents: now[key], delta: before && before[key] !== null ? now[key] - before[key] : null,
    good: key === 'out' ? -1 : 1,
  }));
}

/**
 * The one coach insight for Home: {kind, text, chips:[{label, attrs}]} (chips ≤ 2).
 * Priority: shortfall, careful mode, surprise buffer not yet planned, money beyond the usual need,
 * spending change versus last month, calm default.
 */
export function pickInsight({plan, profile, bufferInfo, hasBufferGoal, tiles = [], previousMonth = null, topCategory = null, categoryLabel = name => name, locale = 'en', fmt = formatters(locale)}) {
  const t = (key, values) => hm(locale, key, values);
  const ask = question => ({'data-direct-question': t(question)});
  const savingPct = profileValue(profile, 'saving_rate_target_pct');
  const told = Number.isFinite(Number(savingPct)) && Number(savingPct) > 0 ? ' ' + t('insight.savingTold', {pct: fmt.percent(savingPct)}) : '';
  if (plan?.steady || profile?.mode === 'steady')
    return {kind: 'steady', text: t('insight.steady'), chips: [{label: t('chip.ask'), attrs: ask('q.steady')}, plan && plan.shortfall > 0 ? {label: t('chip.due'), attrs: {'data-home-why': ''}} : {label: t('chip.situation'), attrs: {'data-view': 'profile'}}]};
  if (plan && plan.shortfall > 0)
    return {kind: 'shortfall', text: t('insight.shortfall'), chips: [{label: t('chip.ask'), attrs: ask('q.shortfall')}, {label: t('chip.due'), attrs: {'data-home-why': ''}}]};
  const idle = plan && plan.extra >= 10000 && plan.extra > Math.max(plan.spendable * 3, 500000);
  if (idle)
    return {kind: 'extra', text: t('insight.extra', {amount: fmt.whole(plan.extra)}) + told, chips: [{label: t('chip.goal'), attrs: {'data-view': 'goals'}, primary: true}, {label: t('chip.ask'), attrs: ask('q.save')}]};
  if (bufferInfo && bufferInfo.average > 0 && !hasBufferGoal)
    return {kind: 'buffer', text: t('insight.buffer', {amount: fmt.whole(bufferInfo.average)}) + told, chips: [{label: t('chip.buffer', {amount: fmt.whole(bufferInfo.monthly)}), attrs: {'data-home-buffer': ''}, primary: true}, {label: t('chip.where'), attrs: {'data-view': 'trends'}}]};
  if (plan && plan.extra >= 10000)
    return {kind: 'extra', text: t('insight.extra', {amount: fmt.whole(plan.extra)}) + told, chips: [{label: t('chip.goal'), attrs: {'data-view': 'goals'}, primary: true}, {label: t('chip.ask'), attrs: ask('q.save')}]};
  const out = tiles.find(tile => tile.key === 'out');
  if (out && out.delta && previousMonth && Math.abs(out.delta) >= 2000) {
    const key = out.delta < 0 ? 'insight.spentLess' : 'insight.spentMore';
    const text = t(key, {amount: fmt.whole(Math.abs(out.delta)), month: fmt.month(previousMonth)});
    if (out.delta > 0 && topCategory) {
      const category = categoryLabel(topCategory.category);
      return {kind: 'spentMore', text: text.replace(/\s*[^.!?]*\?$/, '') + ' ' + t('insight.topCategory', {category, amount: fmt.whole(topCategory.cents)}) + told,
        chips: [{label: t('chip.category', {category}), attrs: {'data-direct-question': t('q.category', {category})}}, {label: t('chip.where'), attrs: {'data-view': 'trends'}}]};
    }
    return {kind: out.delta < 0 ? 'spentLess' : 'spentMore', text: text + told, chips: [{label: t('chip.where'), attrs: {'data-view': 'trends'}}, {label: t('chip.ask'), attrs: ask('q.save')}]};
  }
  return {kind: 'calm', text: t('insight.calm', {amount: (fmt.floor || fmt.whole)(plan?.perDay ?? 0)}) + told, chips: [{label: t('chip.ask'), attrs: ask('q.safe')}, {label: t('chip.where'), attrs: {'data-view': 'trends'}}]};
}

const attrs = map => Object.entries(map || {}).map(([key, value]) => ` ${key}="${escape(value)}"`).join('');

/** The plan hero card HTML. options: {locale, fmt, label(item) -> text, profile, state:'loading'|'unavailable'|'ready'}. */
export function planCardHTML(plan, {locale = 'en', fmt = formatters(locale), label = item => item.label, profile = null, state = 'ready'} = {}) {
  const t = (key, values) => hm(locale, key, values);
  const head = `<p class="hv4-eyebrow">${escape(t('eyebrow'))}</p>`;
  if (!plan) return `<section class="hv4-plan" aria-labelledby="home-v4-title" aria-busy="${state === 'loading'}">${head}<h2 id="home-v4-title" class="hv4-visually-hidden">${escape(t('title'))}</h2><p class="hv4-plan-empty">${escape(t(state === 'loading' ? 'loading' : 'unavailable'))}</p></section>`;
  const segments = planSegments(plan);
  const payday = !plan.paydayKnown ? t('noPayday', {days: plan.days}) : plan.days === 1 ? t('paydayTomorrow', {date: fmt.shortDate(plan.nextPayday)}) : t('paydayIn', {days: plan.days, date: fmt.shortDate(plan.nextPayday)});
  const event = plan.steady ? steadyEvent(profile) : null;
  const steady = plan.steady ? `<p class="hv4-steady" role="note">${escape(t('steady', {event: t('event.' + (event && ['job_loss', 'income_drop', 'large_loss'].includes(event) ? event : 'other'))}))}</p>` : '';
  const warning = plan.shortfall > 0 ? `<p class="hv4-warning" role="note">${escape(t('shortfall', {amount: fmt.money(plan.shortfall)}))}</p>` : '';
  const bar = segments.length ? `<div class="hv4-bar" role="img" aria-label="${escape(segments.map(s => t('seg.' + s.key) + ' ' + fmt.money(s.cents)).join(', '))}">${segments.map(s => `<span class="hv4-seg hv4-seg-${s.key}" style="flex-grow:${Math.max(s.share, 0.015).toFixed(4)}"></span>`).join('')}</div>` : '';
  const legend = segments.length ? `<ul class="hv4-legend">${segments.map(s => `<li><i class="hv4-dot hv4-seg-${s.key}" aria-hidden="true"></i><span>${escape(t('seg.' + s.key))}</span><b>${escape(fmt.whole(s.cents))}</b></li>`).join('')}</ul>` : '';
  const savingPct = profileValue(profile, 'saving_rate_target_pct');
  const itemLabel = item => item.saving ? (Number(savingPct) > 0 ? t('kind.savingPct', {pct: fmt.percent(savingPct)}) : t('kind.saving'))
    : item.kind === 'tax' && !item.label ? t('kind.tax') : item.kind === 'loan' && !item.label ? t('kind.loan') : label(item);
  const row = (text, cents, {sign = '−', date = null, told = false, strong = false} = {}) => `<li class="${strong ? 'hv4-why-total' : ''}"><span>${escape(text)}${date ? `<small>${escape(fmt.dayMonth(date))}</small>` : ''}${told ? `<small class="hv4-told">${escape(t('told'))}</small>` : ''}</span><b>${sign ? sign + ' ' : ''}${escape(fmt.money(cents))}</b></li>`;
  const lines = [row(t('why.balance'), plan.balance, {sign: ''})];
  for (const item of plan.items) lines.push(row(itemLabel(item), item.amount, {date: item.date, told: item.told}));
  if (plan.reserve) lines.push(row(t('why.reserve'), plan.reserve));
  if (plan.buffer) lines.push(row(t('why.buffer'), plan.buffer));
  if (plan.everyday) lines.push(row(t('why.everyday'), plan.everyday));
  if (plan.extra) lines.push(row(t('why.extra'), plan.extra));
  lines.push(row(t('why.free'), plan.spendable, {sign: '=', strong: true}));
  const why = `<details class="hv4-why" id="home-v4-why"><summary>${escape(t('why'))}</summary><ul class="hv4-why-list">${lines.join('')}</ul><p class="hv4-why-perday">${escape(t('why.perDay', {amount: fmt.money(plan.spendable + plan.everyday), days: plan.days, perDay: fmt.money(plan.perDay)}))}</p><p class="hv4-why-note">${escape(t('why.note'))}</p></details>`;
  return `<section class="hv4-plan${plan.steady ? ' hv4-plan-steady' : ''}" aria-labelledby="home-v4-title">${head}<h2 id="home-v4-title" class="hv4-hero"><span class="hv4-hero-lead">${escape(t('canUse'))}</span><span class="hv4-hero-amount">${escape((fmt.floor || fmt.whole)(plan.perDay))}</span><span class="hv4-hero-unit">${escape(plan.paydayKnown ? t('perDay') : t('perDayFallback', {days: plan.days}))}</span></h2><p class="hv4-payday">${escape(payday)}</p>${steady}${warning}<div class="hv4-split"><p class="hv4-balance"><span>${escape(t('balance'))}</span><b>${escape(fmt.money(plan.balance))}</b></p>${bar}${legend}</div>${why}</section>`;
}

/** The insight card HTML. */
export function insightHTML(insight, {locale = 'en'} = {}) {
  if (!insight) return '';
  const chips = insight.chips.slice(0, 2).map(chip => `<button type="button" class="hv4-chip${chip.primary ? ' hv4-chip-primary' : ''}"${attrs(chip.attrs)}>${escape(chip.label)}</button>`).join('');
  return `<section class="hv4-card hv4-insight" data-insight="${escape(insight.kind)}" aria-label="${escape(hm(locale, 'insight.eyebrow'))}"><p class="hv4-insight-head"><span class="hv4-coach-mark" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M6 15v-4h5V7h6m-4 0h4v4" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></span>${escape(hm(locale, 'insight.eyebrow'))}</p><p class="hv4-insight-text">${escape(insight.text)}</p><div class="hv4-chips">${chips}</div></section>`;
}

/** This month card HTML. monthOptions is the <option> list for the month picker. */
export function monthHTML(tiles, {locale = 'en', fmt = formatters(locale), month = null, previousMonth = null, monthOptions = ''} = {}) {
  const t = (key, values) => hm(locale, key, values);
  const picker = monthOptions ? `<label class="hv4-month-pick"><span class="hv4-visually-hidden">${escape(t('month.choose'))}</span><select id="home-v4-month-select">${monthOptions}</select></label>` : `<span class="hv4-month-label">${escape(month ? fmt.monthYear(month) : '')}</span>`;
  const body = tiles.length ? `<dl class="hv4-tiles">${tiles.map(tile => {
    const delta = tile.delta;
    const tone = delta === null || delta === 0 ? 'same' : (delta * tile.good > 0 ? 'good' : 'watch');
    const change = delta === null || !previousMonth ? '' : `<small class="hv4-delta hv4-delta-${tone}">${delta === 0 ? escape(t('month.same', {month: (fmt.monthShort || fmt.month)(previousMonth)})) : `<span aria-hidden="true">${delta > 0 ? '▲' : '▼'}</span> ${escape(t('month.vs', {amount: fmt.whole(Math.abs(delta)), month: (fmt.monthShort || fmt.month)(previousMonth)}))}`}</small>`;
    return `<div class="hv4-tile hv4-tile-${tile.key}"><dt>${escape(t('month.' + tile.key))}</dt><dd><b>${escape(fmt.whole(tile.cents))}</b>${change}</dd></div>`;
  }).join('')}</dl>` : `<p class="hv4-muted">${escape(t('month.empty'))}</p>`;
  return `<section class="hv4-card hv4-month" aria-labelledby="home-v4-month-title"><div class="hv4-card-head"><h2 id="home-v4-month-title">${escape(t('month.title'))}</h2>${picker}</div>${body}</section>`;
}

/** Surprise buffer card HTML. goal: an existing goal with template 'buffer', or null. */
export function bufferHTML(info, goal, {locale = 'en', fmt = formatters(locale), readyBy = null, tight = false} = {}) {
  const t = (key, values) => hm(locale, key, values);
  const head = `<div class="hv4-card-head"><h2 id="home-v4-buffer-title">${escape(t('buffer.title'))}</h2>${goal ? `<button type="button" class="hv4-link" data-goal-edit="${escape(goal.id || goal.goal_id)}">${escape(t('buffer.change'))}</button>` : ''}</div>`;
  if (goal) {
    const saved = pos(goal.current_saved_cents), target = pos(goal.target_cents), share = target ? Math.min(1, saved / target) : 0;
    return `<section class="hv4-card hv4-buffer" aria-labelledby="home-v4-buffer-title">${head}<p class="hv4-buffer-amount">${escape(t('buffer.progress', {saved: fmt.whole(saved), target: fmt.whole(target)}))}</p><div class="hv4-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(share * 100)}" aria-label="${escape(t('buffer.progress', {saved: fmt.money(saved), target: fmt.money(target)}))}"><span style="width:${(share * 100).toFixed(1)}%"></span></div><p class="hv4-muted">${escape(t('buffer.planned', {amount: fmt.whole(pos(goal.required_monthly_cents)), date: fmt.date(goal.target_date)}))}</p></section>`;
  }
  if (!info) return '';
  const basis = info.total && info.largest ? t('buffer.basis', {total: fmt.whole(info.total), largest: fmt.whole(pos(info.largest.amount_cents))}) : t('buffer.none');
  return `<section class="hv4-card hv4-buffer" aria-labelledby="home-v4-buffer-title">${head}<p class="hv4-muted">${escape(t('buffer.help'))}</p><div class="hv4-buffer-suggest"><span>${escape(t('buffer.suggest'))}</span><b>${escape(fmt.whole(info.target))}</b><small>${escape(readyBy ? t('buffer.pace', {amount: fmt.whole(info.monthly), date: fmt.date(readyBy)}) : '')}</small></div><p class="hv4-basis">${escape(basis)}</p>${tight ? `<p class="hv4-later">${escape(t('buffer.later'))}</p>` : `<button type="button" class="hv4-button" data-home-buffer>${escape(t('buffer.action', {amount: fmt.whole(info.monthly)}))}</button>`}</section>`;
}

/** Goals and plans summary HTML: one line per goal (buffer goal shown in its own card), wishes after. */
export function goalsHTML(goals = [], wishes = [], {locale = 'en', fmt = formatters(locale)} = {}) {
  const t = (key, values) => hm(locale, key, values);
  const list = goals.filter(goal => goal.template !== 'buffer').slice(0, 3);
  const rows = list.map(goal => {
    const saved = pos(goal.current_saved_cents), target = pos(goal.target_cents), share = target ? Math.min(1, saved / target) : 0;
    return `<li><button type="button" class="hv4-goal" data-view="goals"><span class="hv4-goal-name">${escape(goal.name)}</span><span class="hv4-goal-meta">${escape(goal.target_date ? t('goals.line', {saved: fmt.whole(saved), target: fmt.whole(target), date: fmt.date(goal.target_date)}) : t('buffer.progress', {saved: fmt.whole(saved), target: fmt.whole(target)}))}${int(goal.required_monthly_cents) ? ' · ' + escape(t('goals.monthly', {amount: fmt.whole(goal.required_monthly_cents)})) : ''}</span><span class="hv4-mini" aria-hidden="true"><span style="width:${(share * 100).toFixed(1)}%"></span></span></button></li>`;
  });
  for (const wish of wishes.slice(-2).reverse()) if (rows.length < 4) rows.push(`<li><button type="button" class="hv4-goal" data-view="goals"><span class="hv4-goal-name">${escape(wish.title)}</span><span class="hv4-goal-meta">${escape(t('goals.wish'))}</span></button></li>`);
  const body = rows.length ? `<ul class="hv4-goals">${rows.join('')}</ul>` : `<p class="hv4-muted">${escape(t('goals.empty'))}</p><button type="button" class="hv4-chip" data-view="goals">${escape(t('goals.start'))}</button>`;
  return `<section class="hv4-card hv4-goals-card" aria-labelledby="home-v4-goals-title"><div class="hv4-card-head"><h2 id="home-v4-goals-title">${escape(t('goals.title'))}</h2><button type="button" class="hv4-link" data-view="goals">${escape(t('goals.all'))} <span aria-hidden="true">›</span></button></div>${body}</section>`;
}

/** Personalise row: a clear entry when the profile is empty, otherwise what the coach knows. */
export function personalHTML(profile, {locale = 'en'} = {}) {
  const t = (key, values) => hm(locale, key, values);
  const count = (profile?.entries || []).filter(entry => entry.active !== false && entry.key !== 'year_review').length;
  if (!profile || profile.empty || !count)
    return `<section class="hv4-personal hv4-personal-empty" aria-labelledby="home-v4-personal-title"><div><h2 id="home-v4-personal-title">${escape(t('personal.title'))}</h2><p>${escape(t('personal.help'))}</p></div><div class="hv4-personal-actions"><button type="button" class="hv4-button" data-home-intro>${escape(t('personal.start'))}</button><button type="button" class="hv4-link" data-open-notebook>${escape(t('personal.prefs'))}</button></div></section>`;
  return `<section class="hv4-personal" aria-labelledby="home-v4-personal-title"><h2 id="home-v4-personal-title" class="hv4-personal-known">${escape(count === 1 ? t('personal.known1') : t('personal.known', {count}))}</h2><div class="hv4-personal-actions"><button type="button" class="hv4-link" data-view="profile">${escape(t('personal.review'))} <span aria-hidden="true">›</span></button><button type="button" class="hv4-link" data-open-notebook>${escape(t('personal.prefs'))}</button></div></section>`;
}

function addMonths(isoDate, months) {
  const [y, m] = isoDate.slice(0, 7).split('-').map(Number);
  const end = new Date(Date.UTC(y, m - 1 + months + 1, 0));
  return end.toISOString().slice(0, 10);
}

/**
 * Wire Home to the app. deps: {state, $, request, captureContext, isCurrent, navigate, changePeriod, perform,
 * locale(), money, monthLabel, shiftMonth, categoryName, localProfile(), v3(), refreshGoals(context), notify}.
 */
export function createHome(deps) {
  const {state, $} = deps;
  let data = {key: null, profile: null, buffer: null};
  let planSettled = null;
  const locale = () => lang(deps.locale?.() || 'en');
  const fmt = () => {
    const base = formatters(locale());
    return deps.money ? {...base, money: deps.money} : base;
  };
  const keyOf = context => [context.customerId, context.month, context.generation].join('|');
  const bufferGoal = () => (state.goals || []).find(goal => goal.template === 'buffer') || null;
  const label = item => (item.kind === 'bill' || item.kind === 'loan') && deps.categoryName ? deps.categoryName(item.label) : item.label;
  const referenceDate = () => state.safeToSpend?.reference_date || state.safeToSpend?.as_of || state.overview?.latest_balance_date || null;

  function render({settled = false} = {}) {
    const root = $('home-v4');
    if (!root) return;
    if (settled) planSettled = state.generation + '|' + state.selectedMonth;
    const done = planSettled === state.generation + '|' + state.selectedMonth;
    const l = locale(), f = fmt();
    const plan = normalizePlan(state.safeToSpend);
    const fresh = data.key === keyOf({customerId: state.customerId, month: state.selectedMonth, generation: state.generation});
    const profile = fresh ? data.profile : null;
    const bufferInfo = fresh ? bufferPlan(data.buffer) : null;
    const previous = deps.previousOverview?.() || null;
    const previousMonth = previous && state.selectedMonth && deps.shiftMonth ? deps.shiftMonth(state.selectedMonth, -1) : null;
    const tiles = monthTiles(state.overview, previous);
    const local = (() => { try { return deps.localProfile?.() || {}; } catch { return {}; } })();
    const topCategory = topFlexibleCategory(state.categoryRows, protectedCategories(profile, local.protected_category));
    const insight = state.overview || plan ? pickInsight({plan, profile, bufferInfo, hasBufferGoal: Boolean(bufferGoal()), tiles, previousMonth, topCategory, categoryLabel: name => (deps.categoryName ? deps.categoryName(name) : name), locale: l, fmt: f}) : null;
    const reference = referenceDate();
    const wishes = local.wishes || [];
    $('home-v4-plan').innerHTML = planCardHTML(plan, {locale: l, fmt: f, label, profile, state: plan ? 'ready' : done ? 'unavailable' : 'loading'});
    $('home-v4-insight').innerHTML = insightHTML(insight, {locale: l});
    const months = [...String($('selected-month')?.innerHTML || '').matchAll(/value="(\d{4}-\d{2})"/g)].map(match => match[1]);
    const options = months.map(month => `<option value="${month}"${month === state.selectedMonth ? ' selected' : ''}>${escape(f.monthYearShort(month))}</option>`).join('');
    $('home-v4-month').innerHTML = state.overview ? monthHTML(tiles, {locale: l, fmt: f, month: state.selectedMonth, previousMonth, monthOptions: options}) : '';
    const select = $('home-v4-month-select');
    if (select && typeof select.addEventListener === 'function') {
      select.value = state.selectedMonth || '';
      select.addEventListener('change', () => { if (select.value && select.value !== state.selectedMonth) deps.changePeriod?.(select.value); });
    }
    $('home-v4-buffer').innerHTML = bufferHTML(bufferInfo, bufferGoal(), {locale: l, fmt: f, readyBy: bufferInfo && reference ? addMonths(reference, bufferInfo.months) : null, tight: Boolean(plan && (plan.shortfall > 0 || plan.steady))});
    $('home-v4-goals').innerHTML = state.overview ? goalsHTML(state.goals || [], wishes, {locale: l, fmt: f}) : '';
    $('home-v4-personal').innerHTML = fresh ? personalHTML(profile, {locale: l}) : '';
  }

  async function onLoad(context = deps.captureContext()) {
    if (!context?.month) { render(); return; }
    const key = keyOf(context);
    // The previous month's overview is shared with the monthly recap cache (deps.previousOverview), not fetched twice.
    const [profile, spender] = await Promise.allSettled([
      deps.request(context, 'get', '/api/profile', {month: context.month}),
      deps.request(context, 'get', '/api/spender-profile', {month: context.month}),
    ]);
    if (!deps.isCurrent(context) || context.month !== state.selectedMonth) return;
    data = {key,
      profile: profile.status === 'fulfilled' ? (profile.value?.profile || null) : null,
      buffer: spender.status === 'fulfilled' ? (spender.value?.buffer || null) : null};
    render();
  }

  function openBufferDraft() {
    const info = bufferPlan(data.buffer) || {monthly: 5000, target: 50000, months: 10};
    const v3 = deps.v3?.();
    const reference = referenceDate() || new Date().toISOString().slice(0, 10);
    const l = locale(), f = fmt(), t = (key, values) => hm(l, key, values);
    const preview = values => {
      const target = pos(values.target_cents) - pos(values.current_saved_cents);
      if (!values.target_date || !(target > 0)) return '';
      const [fy, fm] = reference.split('-').map(Number), [ty, tm] = String(values.target_date).split('-').map(Number);
      const months = (ty - fy) * 12 + (tm - fm);
      return months >= 1 ? t('draft.preview', {amount: f.whole(Math.ceil(target / months)), months}) : '';
    };
    const spec = {id: 'home-buffer', kind: 'goal', title: t('draft.title'), intro: t('draft.intro', {amount: f.whole(info.monthly)}), saveLabel: t('draft.save'), fields: [
      {name: 'name', label: t('draft.name'), type: 'text', value: t('draft.defaultName'), required: true, max: 120},
      {name: 'target_cents', label: t('draft.target'), type: 'amount', value: info.target, required: true, min: 100},
      {name: 'target_date', label: t('draft.date'), type: 'date', value: addMonths(reference, info.months), required: true},
      {name: 'current_saved_cents', label: t('draft.saved'), type: 'amount', value: 0},
    ]};
    spec.preview = preview({target_cents: info.target, target_date: spec.fields[2].value, current_saved_cents: 0});
    const context = deps.captureContext();
    const save = async values => {
      await deps.request(context, 'post', '/api/goals', {name: values.name, target_cents: values.target_cents, target_date: values.target_date,
        current_saved_cents: values.current_saved_cents || 0, reserve_floor_cents: 50000, template: 'buffer', confirmed: true});
      await deps.refreshGoals?.(context);
      deps.notify?.(t('draft.saved.notice'));
    };
    if (v3?.openDraft) v3.openDraft(spec, {onSave: save, onChange: (values, card) => updateDraftPreview(card, preview(values))});
    else return deps.perform?.(null, () => save({name: t('draft.defaultName'), target_cents: info.target, target_date: spec.fields[2].value, current_saved_cents: 0}));
  }

  function handleClick(event) {
    const target = event?.target?.closest?.('[data-home-buffer],[data-home-why],[data-home-intro]');
    if (!target || !target.dataset) return false;
    if (target.dataset.homeBuffer !== undefined) { openBufferDraft(); return true; }
    if (target.dataset.homeWhy !== undefined) {
      const why = $('home-v4-why');
      if (why) { why.open = true; why.scrollIntoView?.({block: 'center', behavior: 'smooth'}); }
      return true;
    }
    if (target.dataset.homeIntro !== undefined) {
      const v3 = deps.v3?.();
      if (v3?.startIntro) v3.startIntro(); else deps.navigate?.('profile');
      return true;
    }
    return false;
  }

  function reset() { data = {key: null, profile: null, buffer: null}; planSettled = null; }

  // A Home error must never break the rest of the app.
  const guard = (fn, fallback) => (...args) => { try { const out = fn(...args); return out?.catch ? out.catch(error => { globalThis.console?.warn?.('[home]', error); }) : out; } catch (error) { globalThis.console?.warn?.('[home]', error); return fallback; } };
  return {render: guard(render), onLoad: guard(onLoad), handleClick: guard(handleClick, false), reset: guard(reset), openBufferDraft: guard(openBufferDraft)};
}
