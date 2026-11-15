// Goals page (V5 fix lane GL): the goal card and its "does this fit?" line.
// The server works out every number (scoach/goals.py goal_plan); this module only decides which sentence fits and
// renders the card. Goal amounts are whole euros (targets, monthly amounts, "about" figures), as on Home.
import { wholeEuros, addMonths } from './plans-mortgage.js';

const LOCALES = ['en', 'fi', 'sv'];
const COPY = {
  'mine.title': ['Your goals and wishes', 'Tavoitteesi ja toiveesi', 'Dina mål och önskningar'],
  'add.title': ['Add a goal or a wish', 'Lisää tavoite tai toive', 'Lägg till ett mål eller en önskan'],
  'perMonth': ['a month', 'kuukaudessa', 'i månaden'],
  'savedOf': ['{saved} of {target} saved', '{saved} / {target} säästetty', '{saved} av {target} sparat'],
  'fit.ok': ['Fits what you usually have left: about {left} a month.', 'Mahtuu siihen, mitä sinulle yleensä jää: noin {left} kuukaudessa.', 'Ryms i det du brukar ha kvar: cirka {left} i månaden.'],
  'fit.now': ['That is more than you usually have left each month (about {left}). If {now} from your account goes to this goal now, about {after} a month is enough.', 'Se on enemmän kuin sinulle yleensä jää kuukaudessa (noin {left}). Jos laitat tililtäsi nyt {now} tähän tavoitteeseen, noin {after} kuukaudessa riittää.', 'Det är mer än du brukar ha kvar i månaden (cirka {left}). Om {now} från kontot går till målet nu räcker cirka {after} i månaden.'],
  'fit.over': ['{need} a month is {gap} more than you usually have left (about {left}). A later date or a smaller target would fit better.', '{need} kuukaudessa on {gap} enemmän kuin sinulle yleensä jää (noin {left}). Myöhempi päivä tai pienempi tavoite sopisi paremmin.', '{need} i månaden är {gap} mer än du brukar ha kvar (cirka {left}). Ett senare datum eller ett mindre mål passar bättre.'],
  'fit.later': ['At about {left} a month you would get there in {month}.', 'Noin {left} kuukaudessa pääsisit tavoitteeseen {month:in}.', 'Med cirka {left} i månaden når du målet i {month}.'],
  'fit.none': ['Nothing is usually left over after bills and spending, so this goal would need a change somewhere else first.', 'Laskujen ja menojen jälkeen sinulle ei yleensä jää mitään, joten tavoite vaatisi ensin muutosta jossain muualla.', 'Efter räkningar och utgifter brukar inget bli kvar, så målet kräver först en ändring någon annanstans.'],
  'fit.unknown': ['We need six full months of your account to say whether this fits.', 'Tarvitsemme tililtäsi kuusi täyttä kuukautta, jotta voimme sanoa, sopiiko tämä.', 'Vi behöver sex hela månader från ditt konto för att säga om det här passar.'],
  'fit.done': ['You have already saved the whole target.', 'Olet jo säästänyt koko tavoitesumman.', 'Du har redan sparat hela målbeloppet.'],
  'reserve': ['Your safety cushion of {reserve} stays untouched.', 'Turvatyyny {reserve} pysyy koskemattomana.', 'Säkerhetsmarginalen på {reserve} lämnas orörd.'],
  'linked': ['{amount} a month from your spending change goes towards this goal. No money is moved.', '{amount} kuukaudessa menomuutoksestasi on merkitty tähän tavoitteeseen. Rahaa ei siirretä.', '{amount} i månaden från din ändrade konsumtion går till målet. Inga pengar flyttas.'],
};
export const GOALS_COPY = COPY;
export const GOALS_COPY_KEYS = Object.freeze(Object.keys(COPY));

const lang = locale => (LOCALES.includes(String(locale).slice(0, 2)) ? String(locale).slice(0, 2) : 'en');
// Finnish months and years after "in" take the inessive ("kesäkuussa 2028").
function inessive(text, locale) {
  if (lang(locale) !== 'fi') return text;
  const month = /^(\S*kuu)(\s+\d{4})?$/i.exec(text);
  return month ? month[1] + 'ssa' + (month[2] || '') : text;
}
export function goalsText(locale, key, values = {}) {
  const row = COPY[key];
  const text = row ? row[LOCALES.indexOf(lang(locale))] || row[0] : key;
  return text.replace(/\{(\w+)(?::(in))?\}/g, (_, name, filter) => (values[name] === undefined ? '{' + name + '}'
    : filter === 'in' ? inessive(String(values[name]), locale) : String(values[name])));
}

const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const int = value => (Number.isFinite(Number(value)) && value !== null ? Number(value) : null);

/**
 * Does the monthly amount fit what is usually left? Pure.
 * Returns {kind: 'done'|'ok'|'now'|'over'|'none'|'unknown', need, left, gap, now, after, reachMonth}.
 *  - ok: the monthly amount fits the typical monthly left-over;
 *  - now: it does not, but putting the plan's "could be saved now" amount towards it makes it fit;
 *  - over: it does not fit even then (gap = what is still missing each month); reachMonth = when the usual left-over gets there;
 *  - none: nothing is usually left; unknown: not enough history.
 */
export function goalFit(goal) {
  const need = int(goal?.required_monthly_cents), left = int(goal?.conservative_monthly_contribution_cents);
  const remaining = int(goal?.remaining_cents) ?? Math.max(0, (int(goal?.target_cents) || 0) - (int(goal?.current_saved_cents) || 0));
  const now = Math.max(0, int(goal?.upfront_available_cents) || 0);
  const after = int(goal?.required_monthly_after_now_cents);
  if (remaining <= 0) return {kind: 'done'};
  if (goal?.capacity_available === false) return {kind: 'unknown', need};
  if (need === null || left === null) return {kind: 'unknown', need};
  if (left <= 0) return {kind: 'none', need, left: 0};
  if (need <= left) return {kind: 'ok', need, left};
  const serverGap = int(goal?.monthly_gap_cents);
  if (now > 0 && after !== null && after <= left && !(serverGap > 0)) return {kind: 'now', need, left, now, after};
  const gap = serverGap > 0 ? serverGap : need - left;
  const start = String(goal?.as_of || '').slice(0, 7);
  const reachMonth = /^\d{4}-\d{2}$/.test(start) ? addMonths(start, Math.ceil(remaining / left)) : null;
  return {kind: 'over', need, left, gap, reachMonth};
}

// Tone for the server's fit status: a gap is a warning; fitting only with money put in now is a note; else it fits.
function serverFitKind(fit, local) {
  const status = String(fit.status || '').toLowerCase();
  if (int(fit.gap_cents) > 0 || /over|short|gap|not|tight/.test(status)) return 'over';
  if (/upfront|now/.test(status)) return 'now';
  if (/unknown|history/.test(status)) return 'unknown';
  if (/fit|ok/.test(status)) return 'ok';
  return local.kind;
}

/**
 * One goal card. h: {locale, t (app i18n), dateLabel, monthLabel, actionsHTML(goal)}.
 * Header (name, date, target), the monthly amount, the HTML progress bar (charts.goalChart), one "does it fit" line
 * (calm note when it fits, amber when it does not), the cushion line, the explanation link and the actions.
 */
export function goalCardHTML(goal, h, goalChart) {
  const {locale, t} = h;
  const g = (key, values) => goalsText(locale, key, values);
  const euros = cents => wholeEuros(cents, locale);
  const id = goal.goal_id || goal.id;
  const local = goalFit(goal);
  // lane NB: /api/goals returns goal.fit with its own wording in en/fi/sv; it is the source when present.
  const server = goal.fit && typeof goal.fit === 'object' ? goal.fit : null;
  const serverText = server?.texts?.[lang(locale)] || server?.texts?.en || '';
  const fit = serverText ? {...local, kind: serverFitKind(server, local)} : local;
  const fitText = serverText ? serverText : fit.kind === 'ok' ? g('fit.ok', {left: euros(fit.left)})
    : fit.kind === 'now' ? g('fit.now', {left: euros(fit.left), now: euros(fit.now), after: euros(fit.after)})
      : fit.kind === 'over' ? g('fit.over', {need: euros(fit.need), gap: euros(fit.gap), left: euros(fit.left)})
        + (fit.reachMonth && h.monthLabel ? ' ' + g('fit.later', {left: euros(fit.left), month: h.monthLabel(fit.reachMonth)}) : '')
        : fit.kind === 'none' ? g('fit.none') : fit.kind === 'done' ? g('fit.done') : g('fit.unknown');
  const tone = fit.kind === 'ok' || fit.kind === 'done' ? 'ok' : fit.kind === 'unknown' ? 'info' : fit.kind === 'now' ? 'info' : 'warn';
  const icon = tone === 'warn' ? '!' : tone === 'ok' ? '✓' : 'i';
  const amount = int(goal.required_monthly_cents);
  const linked = goal.modeled_scenario_contribution_cents > 0 ? `<p class="goal-card__note">${escape(g('linked', {amount: euros(goal.modeled_scenario_contribution_cents)}))}</p>` : '';
  return `<article class="goal-card goal-card--v5" data-goal-id="${escape(id)}">`
    + `<div class="goal-card__head"><div class="goal-card__titles"><h3>${escape(goal.name)}</h3><p class="goal-card__date">${escape(t('goal.by', {date: h.dateLabel(goal.target_date)}))}</p></div><span class="status-pill scenario-pill">${escape(t('common.estimate'))}</span></div>`
    + `<div class="goal-card__body"><div class="goal-card__main">`
    + (amount !== null ? `<p class="goal-amount">${escape(euros(amount))} <span>${escape(g('perMonth'))}</span></p>` : '')
    + goalChart(goal.current_saved_cents ?? 0, goal.target_cents)
    + `</div><div class="goal-card__side"><p class="goal-fit goal-fit--${tone}" data-goal-fit="${fit.kind}"><span class="goal-fit__icon" aria-hidden="true">${icon}</span><span>${escape(fitText)}</span></p>`
    + (int(goal.reserve_floor_cents) > 0 ? `<p class="goal-card__note">${escape(g('reserve', {reserve: euros(goal.reserve_floor_cents)}))}</p>` : '')
    + linked
    + `<button class="text-button goal-card__how" type="button" data-goal-evidence="${escape(id)}">${escape(t('goal.assumptions'))} ›</button></div></div>`
    + (h.actionsHTML ? h.actionsHTML(goal) : '')
    + '</article>';
}
