// Answer cards (V4 lane U): one renderer for catalogue answers and for cards attached to AI answers.
// Card contract (docs/V4_SPEC.md, lane C): {question_id, title, headline:{label, value_text, value_cents|null},
// lines:[str] (<=4), chart:{kind:'bars'|'trend'|'ring'|'progress', data}|null, caveat, evidence:[{label, query}],
// followups:[{id,text}], pickers:[{name, kind, value, options?}], params_used:{}}. Every text is localized by the
// server; this module only adds a few UI labels. It formats money only where the contract gives cents without text
// (chart rows, an amount picker's input) and never computes amounts.
import { barChart, trendChart, spendingRing, goalChart } from './charts.js';

const LOCALES = ['en', 'fi', 'sv'];
const COPY = {
  quickMode: ['Quick answers mode – the AI coach isn’t available right now, so I can’t read typed questions.',
    'Pikavastaukset käytössä – tekoälyvalmentaja ei ole juuri nyt käytettävissä, joten en ymmärrä vapaasti kirjoitettuja kysymyksiä.',
    'Snabbsvar används – AI-coachen är inte tillgänglig just nu, så jag kan inte läsa skrivna frågor.'],
  closest: ['Closest questions I can answer exactly:', 'Lähimmät kysymykset, joihin osaan vastata tarkasti:', 'Närmaste frågor som jag kan svara exakt på:'],
  noSuggestions: ['Pick a question from Browse topics, or try the AI coach again.', 'Valitse kysymys aiheista tai kokeile tekoälyvalmentajaa uudelleen.', 'Välj en fråga bland ämnena eller försök med AI-coachen igen.'],
  usingProfile: ['Using what you told me: {text}', 'Käytän sitä, mitä kerroit: {text}', 'Jag använder det du berättade: {text}'],
  introChip: ['Tell me about you (1 min)', 'Kerro itsestäsi (1 min)', 'Berätta om dig (1 min)'],
  introHide: ['Hide this suggestion', 'Piilota tämä ehdotus', 'Dölj förslaget'],
  followups: ['Next questions', 'Seuraavat kysymykset', 'Nästa frågor'],
  evidence: ['See the transactions', 'Katso tapahtumat', 'Visa transaktionerna'],
  mode: ['Quick answers · Numbers come from your account', 'Pikavastaukset · Luvut tulevat tililtäsi', 'Snabbsvar · Siffrorna kommer från ditt konto'],
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
  if (kind === 'ring') return charts.spendingRing(rows.filter(row => row.value_cents > 0).map(row => ({category: row.category || row.label, label: row.label, total_cents: row.value_cents})));
  return '';
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
  const headline = card.headline && typeof card.headline === 'object' ? card.headline : {};
  const pickers = (Array.isArray(card.pickers) ? card.pickers : []).map((picker, i) => pickerHTML(picker, i, {locale, esc, turnId, cardIndex: index, monthLabel})).filter(Boolean).join('');
  const lines = (Array.isArray(card.lines) ? card.lines : []).map(str).filter(Boolean).slice(0, 4);
  const profile = [card.profile_note, card.using_profile, card.personalization].map(value => Array.isArray(value) ? value.map(str).filter(Boolean).join(' · ') : str(value)).find(Boolean);
  const chart = chartHTML(card.chart, options.charts, esc, locale);
  const evidence = (Array.isArray(card.evidence) ? card.evidence : []).map((item, i) => item && item.query && typeof item.query === 'object'
    ? `<button type="button" class="answer-card__link" data-card-evidence="${esc(turnId)}" data-card-index="${index}" data-index="${i}">${plain(item.label) || esc(cardText(locale, 'evidence'))} <span aria-hidden="true">›</span></button>` : '').filter(Boolean).slice(0, 2).join('');
  const followups = latest ? (Array.isArray(card.followups) ? card.followups : []).filter(item => str(item?.id) && str(item?.text)).slice(0, 3)
    .map(item => `<button type="button" class="answer-chip" data-catalogue-question="${esc(item.id)}" data-catalogue-text="${plain(item.text)}">${plain(item.text)}</button>`).join('') : '';
  const value = str(headline.value_text);
  return `<article class="answer-card${busy ? ' is-busy' : ''}" data-card-question="${plain(card.question_id)}" aria-busy="${busy}">`
    + `<h3 class="answer-card__title">${plain(card.title)}</h3>`
    + (pickers ? `<div class="answer-card__pickers">${pickers}</div>` : '')
    + (value || str(headline.label) ? `<p class="answer-card__headline">${value ? `<strong class="answer-card__value">${esc(value)}</strong>` : ''}${str(headline.label) ? `<span class="answer-card__label">${plain(headline.label)}</span>` : ''}</p>` : '')
    + (lines.length ? `<ul class="answer-card__lines">${lines.map(line => `<li>${esc(line)}</li>`).join('')}</ul>` : '')
    + (chart ? `<figure class="answer-card__chart">${chart}</figure>` : '')
    + (profile ? `<p class="answer-card__profile">${esc(cardText(locale, 'usingProfile', {text: profile}))}</p>` : '')
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
    const suggestions = latest ? questionChips(response.suggestions, {esc, max: 3}) : '';
    const supportive = str(response.supportive);
    // A warm line first when the customer sounds worried, then the honest mode notice.
    notice = `<section class="quick-notice" role="note">`
      + (supportive ? `<p class="quick-notice__supportive">${esc(supportive)}</p>` : '')
      + `<p class="quick-notice__mode">${esc(cardText(locale, 'quickMode'))}</p>`
      + (suggestions ? `<p class="quick-notice__lead">${esc(cardText(locale, 'closest'))}</p><div class="answer-chips">${suggestions}</div>`
        : cards ? '' : `<p class="quick-notice__lead">${esc(cardText(locale, 'noSuggestions'))}</p>`)
      + (latest && retryLabel ? `<button type="button" class="text-button coach-retry" data-retry-agent="${esc(turn.id)}">${esc(retryLabel)} ↻</button>` : '')
      + `</section>`;
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
