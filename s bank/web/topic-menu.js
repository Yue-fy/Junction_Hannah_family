/**
 * Coach topic menu (COACH_V3_PLAN WP-F).
 *
 * A "Browse topics" pill beside the composer opens a sheet of topic groups with ready
 * starter questions. Tapping a question hands its text (in the current locale) to the
 * caller, who sends it through the normal agent path. Free typing is never blocked.
 *
 * Pure and dependency-free: no fetch, no storage, no global state.
 */

const LOCALES = ['en', 'fi', 'sv'];

const COPY = {
  'topic.browse': ['Browse topics', 'Selaa aiheita', 'Bläddra bland ämnen'],
  'topic.sheetTitle': ['What would you like to know?', 'Mitä haluaisit tietää?', 'Vad vill du veta?'],
  'topic.intro': ['Tap a question to ask it. You can always type your own, too.', 'Napauta kysymystä, niin kysyn sen puolestasi. Voit aina kirjoittaa myös oman kysymyksesi.', 'Tryck på en fråga för att ställa den. Du kan alltid skriva en egen också.'],
  'topic.close': ['Close', 'Sulje', 'Stäng'],
  'topic.count': ['{count} questions', '{count} kysymystä', '{count} frågor'],

  'topic.money': ['Where my money goes', 'Mihin rahani menevät', 'Vart mina pengar tar vägen'],
  'topic.money.month': ['Where did my money go this month?', 'Mihin rahani menivät tässä kuussa?', 'Vart tog mina pengar vägen den här månaden?'],
  'topic.money.leaks': ['What are my Little leaks?', 'Mitkä ovat arjen pikkumenoni?', 'Vilka är mina vardagens småutgifter?'],
  'topic.money.weekday': ['Which weekday do I spend the most?', 'Minä viikonpäivänä kulutan eniten?', 'Vilken veckodag spenderar jag mest?'],
  'topic.money.compare': ['Compare this month with last month', 'Vertaa tätä kuuta edelliseen kuuhun', 'Jämför den här månaden med förra månaden'],

  'topic.room': ['Spending room', 'Käyttövara', 'Utrymme att spendera'],
  'topic.room.week': ['What can I safely spend this week?', 'Paljonko voin käyttää turvallisesti tällä viikolla?', 'Hur mycket kan jag tryggt spendera den här veckan?'],
  'topic.room.save': ['How much can I save this month?', 'Paljonko voin säästää tässä kuussa?', 'Hur mycket kan jag spara den här månaden?'],
  'topic.room.payday': ['Will I make it to payday?', 'Riittävätkö rahani palkkapäivään asti?', 'Räcker pengarna till lönedagen?'],

  'topic.me': ['About me', 'Minusta', 'Om mig'],
  'topic.me.spender': ['What kind of spender am I?', 'Millainen rahankäyttäjä olen?', 'Vilken typ av spenderare är jag?'],
  'topic.me.profile': ['Update my money profile', 'Päivitä rahaprofiilini', 'Uppdatera min ekonomiska profil'],
  'topic.me.known': ['What do you know about me?', 'Mitä tiedät minusta?', 'Vad vet du om mig?'],

  'topic.goals': ['Goals', 'Tavoitteet', 'Mål'],
  'topic.goals.new': ['Help me save for something', 'Auta minua säästämään johonkin', 'Hjälp mig att spara till något'],
  'topic.goals.progress': ['How are my goals doing?', 'Miten tavoitteeni etenevät?', 'Hur går det med mina mål?'],
  'topic.goals.dining': ['What if I cut eating out by 20%?', 'Entä jos vähentäisin ravintolamenoja 20 %?', 'Vad händer om jag äter ute 20 % mindre?'],

  'topic.bills': ['Bills & debts', 'Laskut ja velat', 'Räkningar och skulder'],
  'topic.bills.recurring': ['What are my recurring payments?', 'Mitkä ovat toistuvat maksuni?', 'Vilka återkommande betalningar har jag?'],
  'topic.bills.loans': ['How much goes to my mortgage and loans?', 'Paljonko rahaa menee asuntolainaan ja muihin lainoihin?', 'Hur mycket går till mitt bolån och andra lån?'],

  'topic.taxes': ['Taxes', 'Verot', 'Skatter'],
  'topic.taxes.withheld': ['How much tax has been taken from my salary this year?', 'Paljonko palkastani on pidätetty veroa tänä vuonna?', 'Hur mycket skatt har dragits från min lön i år?'],
  'topic.taxes.refund': ['When do I get my tax refund?', 'Milloin saan veronpalautukseni?', 'När får jag min skatteåterbäring?'],
  'topic.taxes.backTax': ['Help me prepare for back taxes', 'Auta minua varautumaan jäännösveroon', 'Hjälp mig att förbereda mig på kvarskatt'],
  'topic.taxes.vat': ['How much VAT was in my groceries?', 'Paljonko ruokaostoksissani oli arvonlisäveroa?', 'Hur mycket moms ingick i mina matinköp?'],

  'topic.learn': ['Learn', 'Opi', 'Lär dig'],
  'topic.learn.baskets': ['What are the three baskets?', 'Mitkä ovat kolme koria?', 'Vilka är de tre korgarna?'],
  'topic.learn.emergency': ['What is an emergency fund?', 'Mikä on hätävara?', 'Vad är en nödbuffert?'],
  'topic.learn.taxCard': ['What is a tax card?', 'Mikä on verokortti?', 'Vad är ett skattekort?'],

  'topic.year': ['My year', 'Vuoteni', 'Mitt år'],
  'topic.year.review': ['Show my year in review', 'Näytä vuosikatsaukseni', 'Visa min årsöversikt'],
};

/** Frozen message maps: {en: {key: text}, fi: {...}, sv: {...}}; identical keys in every locale. */
export const TOPIC_MESSAGES = Object.freeze(Object.fromEntries(LOCALES.map((locale, index) => [
  locale, Object.freeze(Object.fromEntries(Object.entries(COPY).map(([key, values]) => [key, values[index]]))),
])));

const q = (topic, id, legacyKey) => Object.freeze({id: topic + '.' + id, key: 'topic.' + topic + '.' + id, ...(legacyKey ? {legacyKey} : {})});

/**
 * Topic groups in display order. Each: {id, key (title message key), questions: [{id, key, legacyKey?}]}.
 * legacyKey names an existing web/i18n.js `coach.question.*` key with the same meaning, if any.
 */
export const TOPICS = Object.freeze([
  Object.freeze({id: 'money', key: 'topic.money', questions: Object.freeze([q('money', 'month'), q('money', 'leaks'), q('money', 'weekday'), q('money', 'compare')])}),
  Object.freeze({id: 'room', key: 'topic.room', questions: Object.freeze([q('room', 'week', 'coach.question.safe'), q('room', 'save'), q('room', 'payday')])}),
  Object.freeze({id: 'me', key: 'topic.me', questions: Object.freeze([q('me', 'spender', 'coach.question.profile'), q('me', 'profile'), q('me', 'known')])}),
  Object.freeze({id: 'goals', key: 'topic.goals', questions: Object.freeze([q('goals', 'new', 'coach.question.goal'), q('goals', 'progress'), q('goals', 'dining', 'coach.question.dining')])}),
  Object.freeze({id: 'bills', key: 'topic.bills', questions: Object.freeze([q('bills', 'recurring'), q('bills', 'loans')])}),
  Object.freeze({id: 'taxes', key: 'topic.taxes', questions: Object.freeze([q('taxes', 'withheld'), q('taxes', 'refund'), q('taxes', 'backTax'), q('taxes', 'vat', 'coach.question.vat')])}),
  Object.freeze({id: 'learn', key: 'topic.learn', questions: Object.freeze([q('learn', 'baskets'), q('learn', 'emergency'), q('learn', 'taxCard')])}),
  Object.freeze({id: 'year', key: 'topic.year', questions: Object.freeze([q('year', 'review')])}),
]);

/** DOM id of the rendered sheet; the button's aria-controls points at it. */
export const TOPIC_SHEET_ID = 'coach-topic-sheet';

const handles = new WeakMap();

function normLocale(locale) {
  const value = String(locale || 'en').toLowerCase().slice(0, 2);
  return LOCALES.includes(value) ? value : 'en';
}

/**
 * Localized message lookup.
 * @param {string} locale 'en' | 'fi' | 'sv' (falls back to 'en').
 * @param {string} key a key of TOPIC_MESSAGES.en.
 * @param {object} [values] placeholder values, e.g. {count: 3}.
 * @returns {string}
 */
export function message(locale, key, values = {}) {
  const lang = normLocale(locale);
  const text = TOPIC_MESSAGES[lang][key] || TOPIC_MESSAGES.en[key] || key;
  return text.replace(/\{(\w+)\}/g, (_, name) => (values[name] === undefined ? '{' + name + '}' : String(values[name])));
}

/**
 * Escape text for HTML content and quoted attributes.
 * @param {*} value
 * @returns {string}
 */
export function escapeHtml(value) {
  return String(value === null || value === undefined ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/**
 * All starter questions as plain text in one locale.
 * @param {string} locale
 * @returns {Array<{topic: string, id: string, key: string, text: string}>} in display order.
 */
export function topicQuestions(locale) {
  return TOPICS.flatMap(topic => topic.questions.map(question => ({topic: topic.id, id: question.id, key: question.key, text: message(locale, question.key)})));
}

/**
 * The 'Browse topics' pill for beside the composer.
 * @param {string} [locale]
 * @returns {string} <button data-topic-open aria-controls="coach-topic-sheet" aria-expanded="false">.
 */
export function renderTopicButton(locale = 'en') {
  const label = escapeHtml(message(locale, 'topic.browse'));
  return '<button type="button" class="topic-button" data-topic-open aria-haspopup="dialog" aria-expanded="false" aria-controls="' + TOPIC_SHEET_ID + '">'
    + '<svg class="topic-button__icon" viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" focusable="false">'
    + '<path d="M3 5h14M3 10h14M3 15h9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'
    + '<span class="topic-button__label">' + label + '</span></button>';
}

/**
 * The topic sheet (bottom sheet on phones, side panel at >= 1024px via cards-v3.css).
 * @param {string} [locale]
 * @param {object} [options]
 * @param {string} [options.openTopic] id of the group expanded initially (default: the first group).
 * @param {boolean} [options.open=false] render visible instead of hidden.
 * @returns {string} markup rooted at <div class="topic-sheet" id="coach-topic-sheet" data-topic-sheet>.
 *   Each question is <button data-topic-question="<text in that locale>">. Wire with attachTopicMenu.
 */
export function renderTopicSheet(locale = 'en', options = {}) {
  const lang = normLocale(locale);
  const opts = options && typeof options === 'object' ? options : {};
  const openTopic = TOPICS.some(topic => topic.id === opts.openTopic) ? opts.openTopic : TOPICS[0].id;
  const groups = TOPICS.map(topic => {
    const questions = topic.questions.map(question => {
      const text = message(lang, question.key);
      return '<li><button type="button" class="topic-question" data-topic-question="' + escapeHtml(text) + '" data-topic-question-id="' + escapeHtml(question.id) + '" data-topic-focusable>'
        + escapeHtml(text) + '</button></li>';
    }).join('');
    return '<details class="topic-group" data-topic="' + escapeHtml(topic.id) + '"' + (topic.id === openTopic ? ' open' : '') + '>'
      + '<summary class="topic-group__summary" data-topic-focusable><span class="topic-group__title">' + escapeHtml(message(lang, topic.key)) + '</span>'
      + '<span class="topic-group__count">' + escapeHtml(message(lang, 'topic.count', {count: topic.questions.length})) + '</span></summary>'
      + '<ul class="topic-group__questions">' + questions + '</ul></details>';
  }).join('');
  return '<div class="topic-sheet" id="' + TOPIC_SHEET_ID + '" data-topic-sheet' + (opts.open ? ' data-open="true"' : ' hidden') + '>'
    + '<div class="topic-sheet__backdrop" data-topic-close data-topic-backdrop></div>'
    + '<section class="topic-sheet__panel" role="dialog" aria-modal="true" aria-labelledby="' + TOPIC_SHEET_ID + '-title">'
    + '<header class="topic-sheet__header"><span class="topic-sheet__grip" aria-hidden="true"></span>'
    + '<h2 class="topic-sheet__title" id="' + TOPIC_SHEET_ID + '-title">' + escapeHtml(message(lang, 'topic.sheetTitle')) + '</h2>'
    + '<button type="button" class="topic-sheet__close" data-topic-close data-topic-focusable aria-label="' + escapeHtml(message(lang, 'topic.close')) + '">'
    + '<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" focusable="false"><path d="M5 5l10 10M15 5L5 15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button>'
    + '</header>'
    + '<p class="topic-sheet__intro">' + escapeHtml(message(lang, 'topic.intro')) + '</p>'
    + '<div class="topic-sheet__groups">' + groups + '</div>'
    + '</section></div>';
}

/**
 * Map a click target to a topic-menu action (pure routing helper).
 * @param {Element|null} target
 * @returns {{action: 'ask', text: string}|{action: 'open'}|{action: 'close'}|null}
 */
export function topicAction(target) {
  if (!target || typeof target.closest !== 'function') return null;
  const question = target.closest('[data-topic-question]');
  if (question) return {action: 'ask', text: question.getAttribute('data-topic-question') || ''};
  if (target.closest('[data-topic-open]')) return {action: 'open'};
  if (target.closest('[data-topic-close]')) return {action: 'close'};
  return null;
}

/**
 * Map a keydown event to a topic-menu key action (pure helper).
 * @param {{key: string, shiftKey?: boolean}} event
 * @returns {'close'|'tab'|'shiftTab'|null}
 */
export function topicKeyAction(event) {
  if (!event) return null;
  if (event.key === 'Escape' || event.key === 'Esc') return 'close';
  if (event.key === 'Tab') return event.shiftKey ? 'shiftTab' : 'tab';
  return null;
}

/**
 * Wire the button and sheet found inside root. Idempotent: attaching the same root again only
 * replaces the callbacks and returns the same controller.
 * Behaviour: the button opens the sheet and focuses the first item; a question calls onAsk(text) and
 * closes; the close button, backdrop and Escape close; Tab wraps inside the sheet; closing returns
 * focus to the element that opened it.
 * @param {Element} root a container holding [data-topic-open] and [data-topic-sheet] (e.g. the Coach page).
 * @param {object} [callbacks]
 * @param {function(string):void} [callbacks.onAsk] receives the question text in the rendered locale.
 * @param {function(string):void} [callbacks.onClose] receives the reason: 'ask' | 'close' | 'escape' | 'api'.
 * @returns {function():void|null} detach function with extra properties open() and close(); null if no sheet.
 */
export function attachTopicMenu(root, callbacks = {}) {
  if (!root || typeof root.querySelector !== 'function') return null;
  const existing = handles.get(root);
  if (existing) { existing.callbacks = callbacks || {}; return existing.detach; }
  const sheet = root.querySelector('[data-topic-sheet]');
  if (!sheet) return null;
  const state = {callbacks: callbacks || {}, opener: null, isOpen: sheet.getAttribute('data-open') === 'true' && !sheet.hidden};
  const buttons = () => Array.from(root.querySelectorAll('[data-topic-open]'));
  const focusables = () => Array.from(sheet.querySelectorAll('[data-topic-focusable]')).filter(el => {
    if (el.hidden) return false;
    const details = typeof el.closest === 'function' ? el.closest('details') : null;
    if (!details || el.matches('summary')) return true;
    return details.open === true || details.hasAttribute('open');
  });
  const firstItem = () => sheet.querySelector('details[open] [data-topic-question]') || sheet.querySelector('summary[data-topic-focusable]') || focusables()[0];
  const open = opener => {
    state.opener = opener || null;
    sheet.hidden = false;
    sheet.setAttribute('data-open', 'true');
    buttons().forEach(button => button.setAttribute('aria-expanded', 'true'));
    state.isOpen = true;
    const target = firstItem();
    if (target && typeof target.focus === 'function') target.focus();
  };
  const close = reason => {
    if (!state.isOpen) return;
    state.isOpen = false;
    sheet.hidden = true;
    sheet.removeAttribute('data-open');
    buttons().forEach(button => button.setAttribute('aria-expanded', 'false'));
    const back = state.opener || buttons()[0];
    state.opener = null;
    if (back && typeof back.focus === 'function') back.focus();
    const handler = state.callbacks.onClose;
    if (typeof handler === 'function') handler(reason || 'close');
  };
  const onClick = event => {
    const routed = topicAction(event.target);
    if (!routed) return;
    if (routed.action === 'open') {
      if (event.preventDefault) event.preventDefault();
      open(event.target.closest('[data-topic-open]'));
    } else if (routed.action === 'close') {
      if (event.preventDefault) event.preventDefault();
      close('close');
    } else if (routed.action === 'ask') {
      if (event.preventDefault) event.preventDefault();
      const handler = state.callbacks.onAsk;
      close('ask');
      if (typeof handler === 'function' && routed.text) handler(routed.text);
    }
  };
  const onKeydown = event => {
    if (!state.isOpen) return;
    const action = topicKeyAction(event);
    if (action === 'close') {
      if (event.preventDefault) event.preventDefault();
      close('escape');
      return;
    }
    if (action === 'tab' || action === 'shiftTab') {
      const items = focusables();
      if (!items.length) return;
      const active = event.target;
      const first = items[0];
      const last = items[items.length - 1];
      const inside = items.includes(active);
      if (action === 'tab' && (active === last || !inside)) {
        if (event.preventDefault) event.preventDefault();
        first.focus();
      } else if (action === 'shiftTab' && (active === first || !inside)) {
        if (event.preventDefault) event.preventDefault();
        last.focus();
      }
    }
  };
  root.addEventListener('click', onClick);
  root.addEventListener('keydown', onKeydown);
  const detach = () => {
    root.removeEventListener('click', onClick);
    root.removeEventListener('keydown', onKeydown);
    handles.delete(root);
  };
  detach.open = () => open(null);
  detach.close = () => close('api');
  detach.isOpen = () => state.isOpen;
  handles.set(root, {get callbacks() { return state.callbacks; }, set callbacks(value) { state.callbacks = value; }, detach});
  return detach;
}
