// V5 lane SP: the Spending tab as one calm column of cards.
//
// Order (top to bottom): period control → "Where it went" (ring + categories, basket chips under them)
// → "How spending changes over time" → "Your balance over the next 30 days" → "More about your money"
// (folded: money in vs out, money by type, savings transfers, VAT).
//
// The chart lanes own their own markup and render code, so this module never rewrites it: it only moves
// whole blocks into place by id, gives them the shared card class, and hides the blocks that repeat what
// Home already shows. Every step is a no-op when a node is missing, so it is safe to run more than once.

export const SPENDING_ORDER = Object.freeze(['spending-card', 'history-details', 'spending-forecast', 'spending-more']);
// Blocks that move into the folded "More" card, in this order.
export const MORE_ORDER = Object.freeze(['cashflow-analysis', 'basket-explanation', 'investment-analysis', 'vat-analysis']);

const STYLESHEET = 'spending-v5.css';

function ensureStylesheet(doc) {
  if (!doc?.head?.appendChild || !doc.createElement) return;
  if (doc.querySelector?.(`link[href$="${STYLESHEET}"]`)) return;
  const link = doc.createElement('link');
  link.rel = 'stylesheet';
  link.href = STYLESHEET;
  doc.head.appendChild(link);
}

function byId(doc, id) {
  if (id === 'basket-explanation') return doc.querySelector?.('#trends-view .basket-explanation') || null;
  return doc.getElementById?.(id) || null;
}

// The 30-day card is the section that holds #runway-chart (lane FC may change its classes).
function forecastCard(doc) {
  const chart = doc.getElementById?.('runway-chart');
  return chart?.closest?.('section') || null;
}

/**
 * Put the Spending blocks in order and give them one card system. Returns the ids it placed, in order.
 * @param {Document} doc
 */
export function arrangeSpending(doc = globalThis.document) {
  if (!doc?.getElementById) return [];
  const view = doc.getElementById('trends-view');
  const more = doc.getElementById('spending-more');
  const list = doc.getElementById('spending-more-list');
  if (!view?.insertBefore || !more) return [];
  ensureStylesheet(doc);

  // 30-day balance: lift the card out of the old "Explore the coming days" fold so it is a card of its own.
  const forecastFold = doc.getElementById('forecast-analysis');
  const forecast = forecastCard(doc);
  if (forecast) {
    if (!forecast.id) forecast.id = 'spending-forecast';
    forecast.classList?.add?.('sp5-card', 'sp5-forecast-card');
  }
  // The fold also holds "Room to spend this week", which repeats the plan on Home: keep it out of sight
  // (its render code still runs, so nothing else changes).
  if (forecastFold) forecastFold.hidden = true;

  const history = doc.getElementById('history-details');
  if (history) {
    history.classList?.add?.('sp5-card', 'sp5-fold');
    if (!history.dataset?.sp5Opened) { history.open = true; if (history.dataset) history.dataset.sp5Opened = '1'; }
  }

  // Main order: everything goes in front of "More", which stays last.
  const placed = [];
  for (const id of SPENDING_ORDER) {
    const node = id === 'spending-forecast' ? forecast : doc.getElementById(id);
    if (!node) continue;
    if (node !== more) view.insertBefore(node, more);
    placed.push(node.id || id);
  }
  // "More" starts folded and so does everything inside it (only the first time: later the customer decides).
  if (list) {
    for (const id of MORE_ORDER) {
      const node = byId(doc, id);
      if (!node) continue;
      if (node.dataset && !node.dataset.sp5Folded) { node.open = false; node.dataset.sp5Folded = '1'; }
      node.classList?.add?.('sp5-sub');
      list.appendChild(node);
    }
  }
  return placed;
}

/** After a basket chip changes the ring, bring the ring back into view when it has scrolled away. */
export function revealRing(doc = globalThis.document) {
  const card = doc?.getElementById?.('spending-card');
  const ring = doc?.getElementById?.('spending-donut');
  if (!card?.scrollIntoView || !ring?.getBoundingClientRect) return false;
  const box = ring.getBoundingClientRect();
  if (box.top >= 0 && box.bottom <= (globalThis.innerHeight || 0)) return false;
  const reduce = globalThis.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
  card.scrollIntoView({block: 'start', behavior: reduce ? 'auto' : 'smooth'});
  return true;
}

// ---------- V5 fix wave (lane SP2): pure helpers for the transactions sheet and the assumptions form ----------

const escapeText = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[x]));
const isoDate = value => /^\d{4}-\d{2}-\d{2}$/.test(String(value || '')) ? new Date(String(value) + 'T00:00:00Z') : null;
const lastDayOf = iso => { const d = isoDate(iso); return d ? new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).toISOString().slice(0, 10) : ''; };

/** `{key}.one` for exactly 1, `{key}.other` otherwise (EN/FI/SV all use the singular only for 1). */
export function pluralKey(key, count) { return key + (Number(count) === 1 ? '.one' : '.other'); }

/** "September 2026" when start..end is one whole month, otherwise a compact range ("1–14 Sept 2026", "1.–14.9.2026"). */
export function periodText(start, end, {localeTag = 'en-FI', monthLabel = null} = {}) {
  const a = isoDate(start), b = isoDate(end);
  if (!a || !b) return '';
  if (start.slice(8) === '01' && end === lastDayOf(start) && monthLabel) return monthLabel(start.slice(0, 7));
  const format = new Intl.DateTimeFormat(localeTag, {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'});
  try { return start === end ? format.format(a) : format.formatRange(a, b); } catch { return format.format(a) + '–' + format.format(b); }
}

/** "Wed 2 Sept" / "ke 2.9." / "ons 2 sep." for a row title. */
export function rowDay(iso, localeTag = 'en-FI') {
  const d = isoDate(iso);
  if (!d) return String(iso || '');
  return new Intl.DateTimeFormat(localeTag, {weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC'}).format(d).replace(/^([A-Za-z]{3}), /, '$1 ');
}

/** "16:51" from the dataset timestamp ("02SEP26:16:51:38") or an ISO time; '' when there is none. */
export function rowTime(row) {
  const match = /(\d{2}):(\d{2})(?::\d{2})?$/.exec(String(row?.timestamp || ''));
  return match && !(match[1] === '00' && match[2] === '00') ? `${match[1]}:${match[2]}` : '';
}

/**
 * The category drill-down sheet ("Groceries · September 2026", "5 purchases · €361.38", one compact tappable row each).
 * @param {Array<object>} rows Transactions from /api/transactions.
 * @param {{scope:{category?:string,role?:string,start:string,end:string,title?:string}, t:Function, money:Function,
 *   categoryName:Function, monthLabel?:Function, localeTag?:string, icon?:Function, color?:Function, esc?:Function,
 *   badgeFor?:Function}} o
 * @returns {{title:string, summary:string, list:string, footnote:string}}
 */
export function transactionSheet(rows, o) {
  const esc = o.esc || escapeText, list = Array.isArray(rows) ? rows : [], scope = o.scope || {};
  const name = scope.title || (scope.category ? o.categoryName(scope.category) : scope.role ? o.roleName?.(scope.role) : '') || o.t('v5.sp.tx.all');
  const period = periodText(scope.start, scope.end, {localeTag: o.localeTag, monthLabel: o.monthLabel});
  const title = period ? `${name} · ${period}` : name;
  const outs = list.filter(row => Number(row.amount_cents) < 0), ins = list.filter(row => Number(row.amount_cents) > 0);
  const purchases = list.length && outs.length === list.length && list.every(row => !row.transaction_type || row.transaction_type === 'purchase');
  const count = o.t(pluralKey(purchases ? 'v5.sp.tx.purchases' : 'v5.sp.tx.rows', list.length), {count: list.length});
  const total = outs.length === list.length ? outs.reduce((sum, row) => sum - Number(row.amount_cents), 0)
    : ins.length === list.length ? ins.reduce((sum, row) => sum + Number(row.amount_cents), 0) : null;
  const summary = list.length && total !== null ? `${count} · ${o.money(total)}` : count;
  // One category in the sheet: the category is already in the title, so each row leads with its day instead.
  const oneCategory = Boolean(scope.category) || (list.length > 0 && list.every(row => row.category === list[0].category));
  const missingMerchant = list.some(row => !(row.merchant_name || row.merchant));
  const html = list.map(row => {
    const merchant = row.merchant_name || row.merchant || '';
    const day = rowDay(row.date || String(row.timestamp || '').slice(0, 10), o.localeTag), time = rowTime(row);
    const head = merchant || (oneCategory ? day : o.categoryName(row.category) || o.t('transactions.unknownMerchant'));
    const meta = merchant || !oneCategory ? [day, time].filter(Boolean).join(' · ') : time;
    const amount = Number(row.amount_cents) || 0;
    const badge = o.badgeFor?.(row) || '';
    return `<button type="button" class="transaction-row tx5-row" data-transaction="${esc(row.transaction_ref)}">`
      + `<span class="category-icon" style="--category-color:${esc(o.color ? o.color(row.category) : '#668578')}">${o.icon ? o.icon(row.category) : ''}</span>`
      + `<span class="tx5-copy"><span class="tx5-name">${esc(head)}</span>${meta ? `<span class="tx5-meta">${esc(meta)}</span>` : ''}${badge}</span>`
      + `<span class="tx5-amount${amount > 0 ? ' is-in' : ''}">${amount > 0 ? '+' : ''}${esc(o.money(Math.abs(amount)))}<span class="tx5-chevron" aria-hidden="true">›</span></span></button>`;
  }).join('');
  return {title, summary, list: html, footnote: list.length && missingMerchant ? o.t('v5.sp.tx.footnote') : ''};
}

const ITEM_KIND = item => {
  const type = String(item?.transaction_type || '').toLowerCase();
  if (item?.role === 'income') return type === 'salary' || item?.category === 'Salary' ? 'payday' : 'income';
  if (type === 'housing_payment' || item?.category === 'Housing') return 'rent';
  if (type.includes('loan') || item?.category === 'Financing') return 'loan';
  if (type === 'utilities_payment' || item?.category === 'Utilities') return 'homeBills';
  return null;
};

/** The plain name of a repeating forecast item: "Salary", "Rent", "Home bills", else its category name. */
export function assumptionName(item, {t, categoryName}) {
  const kind = ITEM_KIND(item);
  return kind ? t('v5.sp.fa.name.' + kind) : categoryName(item?.category) || t('v5.sp.fa.out');
}

/**
 * "Adjust the assumptions": one flat row per repeating item (name, in/out, a switch, a positive amount and a day),
 * one "Update the chart" button and one plain note. The sign lives in data-sign so the customer never types a minus.
 * @param {Array<object>} items forecast.recurring_items
 * @param {{saved?:object, t:Function, categoryName:Function, esc?:Function, localeTag?:string}} o
 * @returns {string}
 */
export function assumptionsFormHTML(items, o) {
  const esc = o.esc || escapeText, saved = o.saved || {};
  const decimals = new Intl.NumberFormat(String(o.localeTag || 'en').startsWith('en') ? 'en-GB' : o.localeTag, {minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: false});
  const rows = (items || []).map((item, i) => {
    const mine = saved[item.id] || {}, original = Number(item.amount_cents) || 0;
    const sign = original < 0 ? -1 : 1, cents = Math.abs(Number(mine.amount_cents ?? original) || 0);
    const name = assumptionName(item, o), day = mine.median_day ?? item.median_day ?? 1, on = mine.enabled !== false;
    return `<fieldset class="assumption-inputs fa5-row${on ? '' : ' is-off'}" data-assumption="${esc(item.id)}" data-sign="${sign}">`
      + `<legend class="visually-hidden">${esc(name)}</legend>`
      + `<label class="fa5-head" for="assumption-enabled-${i}"><input id="assumption-enabled-${i}" type="checkbox" class="fa5-switch" data-field="enabled" ${on ? 'checked' : ''} aria-label="${esc(o.t('v5.sp.fa.include', {name}))}">`
      + `<span class="fa5-name">${esc(name)}</span><span class="fa5-dir fa5-dir--${sign < 0 ? 'out' : 'in'}">${esc(o.t(sign < 0 ? 'v5.sp.fa.out' : 'v5.sp.fa.in'))}</span></label>`
      + `<div class="fa5-fields"><label class="fa5-field fa5-field--amount" for="assumption-amount-${i}"><span>${esc(o.t('v5.sp.fa.amount'))}</span><span class="fa5-euro"><input id="assumption-amount-${i}" data-field="amount" type="text" inputmode="decimal" autocomplete="off" value="${esc(decimals.format(cents / 100))}"><span aria-hidden="true">€</span></span></label>`
      + `<label class="fa5-field fa5-field--day" for="assumption-day-${i}"><span>${esc(o.t('v5.sp.fa.day'))}</span><input id="assumption-day-${i}" data-field="day" type="number" inputmode="numeric" min="1" max="31" value="${esc(day)}"></label></div></fieldset>`;
  }).join('');
  return `<p class="fa5-intro">${esc(o.t('v5.sp.fa.intro'))}</p><div class="fa5-list">${rows}</div>`
    + `<div class="fa5-actions"><button class="secondary-button fa5-apply" id="apply-preview" type="button">${esc(o.t('v5.sp.fa.apply'))}</button><p class="fa5-note">${esc(o.t('v5.sp.fa.note'))}</p></div>`;
}
