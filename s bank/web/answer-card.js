// Answer cards (V4 lane U): one renderer for catalogue answers and for cards attached to AI answers.
// Card contract (docs/V4_SPEC.md, lane C): {question_id, title, headline:{label, value_text, value_cents|null},
// lines:[str] (<=4), chart:{kind:'bars'|'trend'|'ring'|'progress', data}|null, caveat, evidence:[{label, query}],
// followups:[{id,text}], pickers:[{name, kind, value, options?}], params_used:{}}. Every text is localized by the
// server; this module only adds a few UI labels. It formats money only where the contract gives cents without text
// (chart rows, an amount picker's input) and never computes amounts.
import { barChart, trendChart, spendingRing, goalChart } from './charts.js';
import { emptyStateHTML, emptyText } from './empty-states.js';

const LOCALES = ['en', 'fi', 'sv'];
const COPY = {
  // V5 fix (lane CO): one calm grey line, shown only when no exact answer card could be given.
  quickMode: ['Quick answers – here are the closest questions I can answer exactly.',
    'Pikavastaukset – tässä lähimmät kysymykset, joihin osaan vastata tarkasti.',
    'Snabbsvar – här är de närmaste frågorna som jag kan svara exakt på.'],
  noSuggestions: ['Pick a question from Browse topics, or try the AI coach again.', 'Valitse kysymys aiheista tai kokeile tekoälyvalmentajaa uudelleen.', 'Välj en fråga bland ämnena eller försök med AI-coachen igen.'],
  usingProfile: ['Using what you told me: {text}', 'Käytän sitä, mitä kerroit: {text}', 'Jag använder det du berättade: {text}'],
  introChip: ['Tell me about you (1 min)', 'Kerro itsestäsi (1 min)', 'Berätta om dig (1 min)'],
  introHide: ['Hide this suggestion', 'Piilota tämä ehdotus', 'Dölj förslaget'],
  followups: ['Next questions', 'Seuraavat kysymykset', 'Nästa frågor'],
  evidence: ['See the transactions', 'Katso tapahtumat', 'Visa transaktionerna'],
  // The composer footer never changes with the answer source (V5 fix, lane CO).
  footer: ['Numbers come from your account. Nothing changes without your OK.', 'Luvut tulevat tililtäsi. Mitään ei muuteta ilman lupaasi.', 'Siffrorna kommer från ditt konto. Inget ändras utan ditt ok.'],
  updating: ['Updating…', 'Päivitetään…', 'Uppdaterar…'],
  cardError: ['I couldn’t update this answer. Please try again.', 'En saanut päivitettyä vastausta. Yritä uudelleen.', 'Jag kunde inte uppdatera svaret. Försök igen.'],
  'picker.category': ['Category', 'Luokka', 'Kategori'],
  'picker.month': ['Month', 'Kuukausi', 'Månad'],
  'picker.percent': ['Change', 'Muutos', 'Ändring'],
  'picker.amount': ['Amount (€)', 'Summa (€)', 'Belopp (€)'],
  'picker.date': ['Date', 'Päivä', 'Datum'],
};

const lang = locale => { const value = String(locale || 'en').slice(0, 2).toLowerCase(); return LOCALES.includes(value) ? value : 'en'; };
/** Localized UI label owned by this module. */
export function cardText(locale, key, values = {}) {
  const row = COPY[key];
  const text = row ? row[LOCALES.indexOf(lang(locale))] || row[0] : key;
  return text.replace(/\{(\w+)\}/g, (_, name) => values[name] === undefined ? '{' + name + '}' : String(values[name]));
}

const TAGS = {en: 'en-IE', fi: 'fi-FI', sv: 'sv-FI'};
const euroFormatter = locale => { const format = new Intl.NumberFormat(TAGS[lang(locale)], {style: 'currency', currency: 'EUR'}); return value => format.format(value / 100); };
const defaultEsc = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[x]));
const str = value => typeof value === 'string' ? value : (typeof value === 'number' && Number.isFinite(value) ? String(value) : '');
const cents = value => Number.isSafeInteger(value) ? value : null;
// Short hyphenated words ("must-pays") never break at the hyphen on narrow screens (U+2011 non-breaking hyphen).
const keepHyphen = text => text.replace(/(?<![\p{L}\d-])(\p{L}{1,6})-(\p{L}{1,6})(?![\p{L}\d-])/gu, '$1\u2011$2');

/** True when the value looks like a card the renderer can show (headline or title required). */
export function isCard(card) {
  return Boolean(card && typeof card === 'object' && !Array.isArray(card) && (str(card.title) || str(card.headline?.value_text)));
}
/** Cards stored on a conversation turn (catalogue answers, AI answers with cards, fallback with one card). */
export function cardsOf(response) {
  if (!response || typeof response !== 'object') return [];
  const list = Array.isArray(response.cards) ? response.cards : response.card ? [response.card] : [];
  return list.filter(isCard);
}
/** Plain text of a card, used as the coach side of conversation history. */
export function cardSummary(card) {
  if (!isCard(card)) return [];
  const headline = [str(card.headline?.value_text), str(card.headline?.label)].filter(Boolean).join(' ');
  return [str(card.title), headline, ...(Array.isArray(card.lines) ? card.lines.map(str) : [])].filter(Boolean).slice(0, 6);
}

// Accepts the shapes a builder is likely to send: an array, or {series|rows|items:[...]}.
function rowsOf(data) {
  const list = Array.isArray(data) ? data : Array.isArray(data?.series) ? data.series : Array.isArray(data?.rows) ? data.rows : Array.isArray(data?.items) ? data.items : [];
  return list.map(row => ({
    label: str(row?.label ?? row?.name ?? row?.category ?? row?.month ?? row?.period),
    category: str(row?.category ?? row?.label ?? row?.name),
    value_cents: cents(row?.value_cents ?? row?.amount_cents ?? row?.total_cents ?? row?.cents),
    value_text: str(row?.value_text),
  })).filter(row => row.label && row.value_cents !== null);
}
/** Chart markup via charts.js, or '' when the data is missing or malformed. */
export function chartHTML(chart, charts = {barChart, trendChart, spendingRing, goalChart}, esc = defaultEsc, locale = 'en') {
  if (!chart || typeof chart !== 'object') return '';
  const kind = chart.kind, data = chart.data;
  if (kind === 'progress') {
    const current = cents(data?.current_cents ?? data?.value_cents ?? data?.saved_cents), target = cents(data?.target_cents);
    return current !== null && target !== null && target > 0 ? charts.goalChart(current, target) : '';
  }
  const rows = rowsOf(data);
  if (!rows.length) return '';
  if (kind === 'bars') return compactBars(rows.slice(0, 5), esc, euroFormatter(locale));
  if (kind === 'trend') return rows.length > 1 ? charts.trendChart(rows.map(row => ({label: row.label, value_cents: row.value_cents}))) : '';
  if (kind === 'ring') return splitBar(rows, esc, euroFormatter(locale));
  return '';
}

// V5 fix (lane CO): a 'ring' (parts of one whole, e.g. held back / daily life / could be saved) is drawn as one
// labelled horizontal bar with a legend: every part is named with its amount. With fewer than two parts above €0
// the bar would be a single colour that says nothing, so the card shows no chart (the headline and lines explain).
const SPLIT_COLOURS = ['#04432b', '#5fae86', '#f6cf86', '#c9ec7a', '#9fb5a5'];
function splitBar(rows, esc, format) {
  const parts = rows.filter(row => row.value_cents > 0).slice(0, SPLIT_COLOURS.length);
  if (parts.length < 2) return '';
  const total = parts.reduce((sum, row) => sum + row.value_cents, 0);
  const colour = index => SPLIT_COLOURS[index % SPLIT_COLOURS.length];
  const text = row => row.value_text || format(row.value_cents);
  const description = parts.map(row => `${row.label}: ${text(row)}`).join(', ');
  return `<div class="card-split" role="img" aria-label="${esc(description)}">`
    + `<div class="card-split__bar" aria-hidden="true">${parts.map((row, i) => `<span style="flex-grow:${(row.value_cents / total * 1000).toFixed(0)};background:${colour(i)}"></span>`).join('')}</div>`
    + `<ul class="card-split__legend" aria-hidden="true">${parts.map((row, i) => `<li><i style="background:${colour(i)}"></i><span class="card-split__label">${esc(row.label)}</span><span class="card-split__value">${esc(text(row))}</span></li>`).join('')}</ul>`
    + `</div>`;
}

// Bars inside a card are a compact list (label, server-formatted value, thin bar) so a card stays one screen tall.
// The value is the row's value_text when the server sends one, otherwise the cents formatted for the locale.
function compactBars(rows, esc, format) {
  const max = Math.max(...rows.map(row => Math.abs(row.value_cents)), 1);
  return `<ul class="card-bars">${rows.map(row => {
    const width = Math.max(2, Math.round(Math.abs(row.value_cents) / max * 100));
    return `<li><span class="card-bars__label">${esc(row.label)}</span><span class="card-bars__value">${esc(row.value_text || format(row.value_cents))}</span><span class="card-bars__track" aria-hidden="true"><span style="width:${width}%"></span></span></li>`;
  }).join('')}</ul>`;
}

function optionList(picker) {
  const options = Array.isArray(picker.options) ? picker.options : [];
  const list = options.map(option => option && typeof option === 'object'
    ? {value: str(option.value ?? option.id), label: str(option.label ?? option.text ?? option.value)}
    : {value: str(option), label: str(option)}).filter(option => option.value !== '');
  if (!list.length && picker.kind === 'percent') for (const value of [10, 20, 30]) list.push({value: String(value), label: String(value)});
  const current = str(picker.value);
  if (current && !list.some(option => option.value === current)) list.unshift({value: current, label: current});
  return list;
}
const percentLabel = (locale, value) => /^-?\d+(?:[.,]\d+)?$/.test(value) ? (lang(locale) === 'en' ? value + '%' : value.replace('.', ',') + ' %') : value;

function pickerHTML(picker, index, {locale, esc, turnId, cardIndex, monthLabel}) {
  const name = str(picker?.name);
  if (!name || !['category', 'month', 'percent', 'amount', 'date'].includes(picker.kind)) return '';
  const id = `card-${esc(turnId)}-${cardIndex}-${esc(name)}`;
  const attrs = `id="${id}" data-card-picker="${esc(name)}" data-card-kind="${esc(picker.kind)}" data-card-turn="${esc(turnId)}" data-card-index="${cardIndex}"`;
  const label = `<label class="visually-hidden" for="${id}">${esc(cardText(locale, 'picker.' + picker.kind))}</label>`;
  if (picker.kind === 'amount') {
    const value = cents(picker.value);
    return `<span class="answer-card__picker answer-card__picker--input">${label}<span aria-hidden="true">€</span><input ${attrs} type="number" inputmode="decimal" min="0" step="1" value="${value === null ? '' : esc(String(value / 100))}"></span>`;
  }
  if (picker.kind === 'date') return `<span class="answer-card__picker answer-card__picker--input">${label}<input ${attrs} type="date" value="${esc(str(picker.value))}"></span>`;
  const options = optionList(picker).map(option => {
    const text = picker.kind === 'percent' && option.label === option.value ? percentLabel(locale, option.label)
      : picker.kind === 'month' && option.label === option.value && monthLabel ? monthLabel(option.value) : option.label;
    return `<option value="${esc(option.value)}"${option.value === str(picker.value) ? ' selected' : ''}>${esc(text)}</option>`;
  }).join('');
  if (!options) return '';
  return `<span class="answer-card__picker">${label}<select ${attrs}>${options}</select></span>`;
}

// Questions where €0 means "nothing recorded" (a calm empty state), not a warning such as "€0 safe to spend".
const ZERO_IS_EMPTY = new Set(['money.where', 'money.category', 'spend.leaks', 'spend.biggest', 'spend.recent', 'extra.vat']);
const chartHasValues = chart => rowsOf(chart?.data).some(row => row.value_cents !== 0)
  || (chart?.kind === 'progress' && Boolean(chart.data));
/**
 * 'unavailable' when the server could not answer, 'zero' when a spending question found nothing; otherwise null.
 * An all-zero chart counts as no chart (nothing to draw).
 */
export function emptyCardKind(card) {
  if (!isCard(card)) return null;
  const headline = card.headline && typeof card.headline === 'object' ? card.headline : {};
  if (str(headline.value_text) === '—') return 'unavailable';
  if (headline.value_cents === 0 && ZERO_IS_EMPTY.has(str(card.question_id)) && !(card.chart && chartHasValues(card.chart))) return 'zero';
  return null;
}

/**
 * Render one answer card.
 * @param {object} card the server card (see contract above)
 * @param {object} options {locale, esc, turnId, index, charts, monthLabel, latest, busy, error}
 * @returns {string} HTML; '' for an invalid card.
 */
export function renderCard(card, options = {}) {
  if (!isCard(card)) return '';
  const {locale = 'en', esc = defaultEsc, turnId = '', index = 0, monthLabel = null, latest = true, busy = false, error = false} = options;
  const plain = value => esc(str(value));
  const shown = value => esc(keepHyphen(str(value)));
  const headline = card.headline && typeof card.headline === 'object' ? card.headline : {};
  const pickers = (Array.isArray(card.pickers) ? card.pickers : []).map((picker, i) => pickerHTML(picker, i, {locale, esc, turnId, cardIndex: index, monthLabel})).filter(Boolean).join('');
  const lines = (Array.isArray(card.lines) ? card.lines : []).map(str).filter(Boolean).slice(0, 4);
  // The server's profile_note is already a full localized sentence ("Using what you told me: …"), so it is shown as
  // sent. Only a bare list of facts (using_profile / personalization) gets this module's prefix: never both.
  const facts = [card.using_profile, card.personalization].map(value => Array.isArray(value) ? value.map(str).filter(Boolean).join(' · ') : str(value)).find(Boolean);
  const profile = str(card.profile_note) || (facts ? cardText(locale, 'usingProfile', {text: facts}) : '');
  const emptyKind = emptyCardKind(card);
  const chart = emptyKind ? '' : chartHTML(card.chart, options.charts, esc, locale);
  // V5 lane EM: no data → one designed empty state in place of the headline, lines and chart; pickers and next questions stay.
  const empty = !emptyKind ? '' : emptyKind === 'unavailable'
    ? emptyStateHTML({kind: 'chart', compact: true, title: str(headline.label), body: lines.join(' ') || emptyText(locale, 'v5.em.card.unavailable.body'), esc, id: 'card-unavailable'})
    : emptyStateHTML({kind: 'calm', compact: true, eyebrow: [str(headline.label), str(headline.value_text)].filter(Boolean).join(' · '), title: lines[0] || str(headline.label), body: lines.slice(1).join(' '), esc, id: 'card-zero'});
  const evidence = (Array.isArray(card.evidence) ? card.evidence : []).map((item, i) => item && item.query && typeof item.query === 'object'
    ? `<button type="button" class="answer-card__link" data-card-evidence="${esc(turnId)}" data-card-index="${index}" data-index="${i}">${shown(item.label) || esc(cardText(locale, 'evidence'))} <span aria-hidden="true">›</span></button>` : '').filter(Boolean).slice(0, 2).join('');
  const followups = latest ? (Array.isArray(card.followups) ? card.followups : []).filter(item => str(item?.id) && str(item?.text)).slice(0, 3)
    .map(item => `<button type="button" class="answer-chip" data-catalogue-question="${esc(item.id)}" data-catalogue-text="${plain(item.text)}">${shown(item.text)}</button>`).join('') : '';
  const value = str(headline.value_text);
  return `<article class="answer-card${busy ? ' is-busy' : ''}" data-card-question="${plain(card.question_id)}" aria-busy="${busy}">`
    + `<h3 class="answer-card__title">${shown(card.title)}</h3>`
    + (pickers ? `<div class="answer-card__pickers">${pickers}</div>` : '')
    + (empty || (value || str(headline.label) ? `<p class="answer-card__headline">${value ? `<strong class="answer-card__value">${esc(value)}</strong>` : ''}${str(headline.label) ? `<span class="answer-card__label">${shown(headline.label)}</span>` : ''}</p>` : ''))
    + (lines.length && !empty ? `<ul class="answer-card__lines">${lines.map(line => `<li>${esc(keepHyphen(line))}</li>`).join('')}</ul>` : '')
    + (chart ? `<figure class="answer-card__chart">${chart}</figure>` : '')
    + (profile ? `<p class="answer-card__profile">${esc(profile)}</p>` : '')
    + (str(card.caveat) ? `<p class="answer-card__caveat">${plain(card.caveat)}</p>` : '')
    + (busy ? `<p class="answer-card__status" role="status">${esc(cardText(locale, 'updating'))}</p>` : error ? `<p class="answer-card__status answer-card__status--error" role="status">${esc(cardText(locale, 'cardError'))}</p>` : '')
    + (evidence ? `<div class="answer-card__evidence">${evidence}</div>` : '')
    + `</article>`
    + (followups ? `<div class="answer-chips" aria-label="${esc(cardText(locale, 'followups'))}">${followups}</div>` : '');
}

/** Suggestion chips for catalogue questions ({id, text}); used by the empty state and the quick-answers notice. */
export function questionChips(questions, {esc = defaultEsc, className = 'answer-chip', max = 6} = {}) {
  return (Array.isArray(questions) ? questions : []).filter(item => str(item?.id) && str(item?.text)).slice(0, max)
    .map(item => `<button type="button" class="${className}" data-catalogue-question="${esc(item.id)}" data-catalogue-text="${esc(item.text)}">${esc(item.text)}</button>`).join('');
}

/**
 * A coach turn answered from the catalogue: either a tapped question ({source:'catalogue_card', cards}) or a typed
 * question while the AI is unavailable ({source:'catalogue', supportive, suggestions, cards}).
 */
export function catalogueTurnHTML(turn, {locale = 'en', esc = defaultEsc, latest = false, monthLabel = null, charts, retryLabel = '', cardState = {}} = {}) {
  const response = turn?.response || {};
  const cards = cardsOf(response).map((card, index) => renderCard(card, {locale, esc, turnId: turn.id, index, monthLabel, charts, latest,
    busy: cardState[index] === 'busy', error: cardState[index] === 'error'})).join('');
  let notice = '';
  if (response.source === 'catalogue') {
    // V5 fix (lane CO): a typed question that matched one catalogue question exactly or confidently gets its card and
    // nothing else, as if it had been tapped. Only when there is no card does one grey line introduce the closest
    // questions. A warm line comes first when the customer sounds worried.
    const suggestions = latest && !cards ? questionChips(response.suggestions, {esc, max: 3}) : '';
    const supportive = str(response.supportive);
    const retry = latest && retryLabel && !cards && response.fallback_reason && response.fallback_reason !== 'not_configured';
    if (supportive || !cards) {
      notice = `<section class="quick-notice" role="note">`
        + (supportive ? `<p class="quick-notice__supportive">${esc(supportive)}</p>` : '')
        + (cards ? '' : `<p class="quick-notice__mode">${esc(cardText(locale, suggestions ? 'quickMode' : 'noSuggestions'))}</p>`)
        + (suggestions ? `<div class="answer-chips">${suggestions}</div>` : '')
        + (retry ? `<button type="button" class="text-button coach-retry" data-retry-agent="${esc(turn.id)}">${esc(retryLabel)} ↻</button>` : '')
        + `</section>`;
    }
  }
  return `<article class="coach-turn card-turn"><p class="coach-turn-user">${esc(str(turn?.message))}</p><div class="coach-turn-cards">${notice}${cards}</div></article>`;
}

/** Dismissible empty-state chip that opens the optional "tell me about you" intro. */
export function introChipHTML(locale, esc = defaultEsc) {
  return `<div class="intro-chip"><button type="button" class="intro-chip__open" data-open-intro><span aria-hidden="true">✦</span> ${esc(cardText(locale, 'introChip'))}</button>`
    + `<button type="button" class="intro-chip__hide" data-dismiss-intro aria-label="${esc(cardText(locale, 'introHide'))}">×</button></div>`;
}

/** Validate GET /api/catalogue data; returns {groups, starters:[{id,text}]} or null. */
export function normalizeCatalogue(data) {
  const groups = (Array.isArray(data?.groups) ? data.groups : []).map(group => ({
    id: str(group?.id), title: str(group?.title),
    questions: (Array.isArray(group?.questions) ? group.questions : []).filter(q => str(q?.id) && str(q?.text)).map(q => ({id: str(q.id), text: str(q.text)})),
  })).filter(group => group.id && group.title && group.questions.length);
  if (!groups.length) return null;
  const byId = new Map(groups.flatMap(group => group.questions.map(q => [q.id, q])));
  const starters = (Array.isArray(data.starters) ? data.starters : []).map(id => byId.get(str(id))).filter(Boolean).slice(0, 6);
  return {groups, starters: starters.length ? starters : groups.map(group => group.questions[0]).slice(0, 6)};
}
