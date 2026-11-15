/* V5 lane FC: the 30-day balance chart — events, plain summary and the touch-friendly day readout.
 * No imports on purpose: pure helpers are testable on their own and app.js passes in t/money. */

const DAY_MS = 86400000;
const isoDay = value => /^\d{4}-\d{2}-\d{2}$/.test(String(value || '')) ? Date.parse(value + 'T00:00:00Z') : NaN;
const addDays = (iso, days) => new Date(isoDay(iso) + days * DAY_MS).toISOString().slice(0, 10);

/** Bills smaller than this (or 10 % of pay) stay off the chart; they still move the line. */
export const BIG_BILL_CENTS = 15000;

function eventKind(item) {
  const type = String(item?.transaction_type || '').toLowerCase();
  if (item?.role === 'income') return type === 'salary' || item?.category === 'Salary' ? 'payday' : 'income';
  if (type === 'housing_payment' || item?.category === 'Housing') return 'rent';
  if (type.includes('loan') || item?.role === 'loan' || item?.category === 'Financing') return 'loan';
  if (type === 'utilities_payment' || item?.category === 'Utilities') return 'homeBills';
  return 'bill';
}
const KIND_ORDER = ['payday', 'income', 'rent', 'loan', 'homeBills', 'bill'];

/**
 * Days worth marking on the chart: salary arriving, rent/housing, loan payments and big bills.
 * Uses the forecast's own scheduled items so the marks always sit on the drawn line.
 * @returns {{date:string, kind:string, amount_cents:number, items:{kind:string, amount_cents:number}[]}[]}
 */
export function forecastEvents(forecast) {
  const items = new Map((forecast?.scheduled_items || forecast?.recurring_items || []).map(item => [item.id, item]));
  const pay = [...items.values()].filter(item => eventKind(item) === 'payday').reduce((sum, item) => sum + Math.max(0, Number(item.amount_cents) || 0), 0);
  const threshold = Math.max(BIG_BILL_CENTS, Math.round(pay * 0.1));
  const events = [];
  for (const row of forecast?.projected || []) {
    const marked = (row.scheduled_item_ids || []).map(id => items.get(id)).filter(Boolean)
      .map(item => ({kind: eventKind(item), amount_cents: Number(item.amount_cents) || 0}))
      .filter(item => ['payday', 'rent', 'loan'].includes(item.kind) || Math.abs(item.amount_cents) >= threshold);
    if (!marked.length) continue;
    marked.sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind));
    events.push({date: row.date, kind: marked[0].kind, amount_cents: marked.reduce((sum, item) => sum + item.amount_cents, 0), items: marked});
  }
  return events;
}

/**
 * The plain-language read of the next 30 days.
 * status: 'clear' (never below the cushion), 'cushion' (dips under the cushion but stays above zero), 'negative'.
 */
export function forecastOutlook(forecast, {events = forecastEvents(forecast), cushionCents = null} = {}) {
  const points = (forecast?.projected || []).filter(row => Number.isSafeInteger(row.balance_cents) && isoDay(row.date) === isoDay(row.date));
  if (!points.length) return null;
  const lowest = points.reduce((a, b) => (b.balance_cents < a.balance_cents ? b : a));
  const end = points.at(-1);
  const cushion = Number.isSafeInteger(cushionCents) && cushionCents > 0 ? cushionCents : null;
  const firstNegative = points.find(row => row.balance_cents < 0)?.date || null;
  const firstBelowCushion = cushion === null ? null : points.find(row => row.balance_cents < cushion)?.date || null;
  const paydays = events.filter(event => event.items?.some(item => item.kind === 'payday') || event.kind === 'payday').map(event => event.date);
  const beforePayday = paydays.includes(addDays(lowest.date, 1));
  const nextPayday = paydays.find(date => date > lowest.date) || null;
  const status = firstNegative ? 'negative' : firstBelowCushion ? 'cushion' : 'clear';
  return {lowest: {date: lowest.date, balance_cents: lowest.balance_cents}, end: {date: end.date, balance_cents: end.balance_cents},
    start: {date: points[0].date}, beforePayday, nextPayday, status, cushion_cents: cushion, firstNegativeDate: firstNegative, firstBelowCushionDate: firstBelowCushion};
}

/** Whole-euro money for headlines and chart labels ("€3,541", "3 541 €"). */
export function wholeEuros(cents, localeTag = 'en-FI') {
  return new Intl.NumberFormat(localeTag, {style: 'currency', currency: 'EUR', maximumFractionDigits: 0, minimumFractionDigits: 0}).format(Math.round(Number(cents) / 100));
}
export function dayName(iso, localeTag = 'en-FI') {
  const time = isoDay(iso);
  if (!Number.isFinite(time)) return String(iso || '');
  return new Intl.DateTimeFormat(localeTag, {weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC'}).format(new Date(time)).replace(/^([A-Za-z]{3}), /, '$1 ');
}

/** One or two plain sentences under the title. t is the app translator; keys live in i18n.js (v5.fc.*). */
export function forecastSentence(outlook, {t, localeTag = 'en-FI'}) {
  if (!outlook) return '';
  const amount = wholeEuros(outlook.lowest.balance_cents, localeTag), date = dayName(outlook.lowest.date, localeTag);
  const lead = t(outlook.beforePayday ? 'v5.fc.tightestBeforePayday' : 'v5.fc.tightest', {amount, date});
  let follow;
  if (outlook.status === 'negative') follow = t('v5.fc.belowZero', {date: dayName(outlook.firstNegativeDate, localeTag)});
  else if (outlook.status === 'cushion') follow = t('v5.fc.belowCushion', {cushion: wholeEuros(outlook.cushion_cents, localeTag)});
  else follow = t(outlook.cushion_cents ? 'v5.fc.aboveCushion' : 'v5.fc.aboveZero');
  return lead + ' ' + follow;
}

/* ---------- interaction: crosshair + readout for pointer, touch and keyboard ---------- */

const bound = new WeakSet();
/**
 * Wire the day readout on a container that holds runwayChart(..., {interactive:true}) markup.
 * Delegated, so re-rendering the chart with innerHTML needs no re-wiring. Idempotent.
 */
export function attachForecastChart(container) {
  if (!container?.addEventListener || bound.has(container)) return;
  bound.add(container);
  let active = null;
  const parts = () => {
    const svg = container.querySelector('svg[data-fc-points]');
    if (!svg) return null;
    let points = [];
    try { points = JSON.parse(svg.getAttribute('data-fc-points')) || []; } catch { points = []; }
    return {svg, points, tip: container.querySelector('.fc-tip'), cursor: svg.querySelector('.fc-cursor'), width: Number(svg.getAttribute('data-fc-width')) || 330};
  };
  const idle = p => {
    const hint = document.createElement('span'); hint.className = 'fc-tip-hint'; hint.textContent = p.svg.getAttribute('data-fc-hint') || '';
    p.tip.replaceChildren(hint); p.tip.classList?.add('is-idle'); p.tip.style.left = ''; p.tip.style.top = '';
  };
  const hide = () => {
    const p = parts(); active = null;
    if (!p) return;
    if (p.tip) idle(p);
    p.cursor?.setAttribute('visibility', 'hidden');
  };
  const show = index => {
    const p = parts();
    if (!p || !p.points.length) return;
    index = Math.max(0, Math.min(p.points.length - 1, index));
    active = index;
    const point = p.points[index];
    if (p.cursor) {
      p.cursor.setAttribute('visibility', 'visible');
      p.cursor.querySelector('line')?.setAttribute('x1', point.x);
      p.cursor.querySelector('line')?.setAttribute('x2', point.x);
      const dot = p.cursor.querySelector('circle');
      dot?.setAttribute('cx', point.x); dot?.setAttribute('cy', point.y);
    }
    if (!p.tip) return;
    const rows = [['fc-tip-date', [point.d, point.k].filter(Boolean).join(' · ')], ['fc-tip-value', point.v], ['fc-tip-range', point.r], ['fc-tip-event', point.e]].filter(([, text]) => text);
    p.tip.replaceChildren(...rows.map(([name, text]) => { const line = document.createElement('span'); line.className = name; line.textContent = text; return line; }));
    p.tip.classList?.remove('is-idle');
    // Phones: the readout is a fixed row above the chart (CSS), so it never covers the line.
    if (globalThis.getComputedStyle?.(p.tip).position !== 'absolute') return;
    const svgBox = p.svg.getBoundingClientRect(), hostBox = container.getBoundingClientRect();
    const scale = svgBox.width / p.width || 1;
    const px = svgBox.left - hostBox.left + point.x * scale, py = svgBox.top - hostBox.top + point.y * scale;
    const tipWidth = p.tip.offsetWidth || 150, tipHeight = p.tip.offsetHeight || 60;
    // Beside the crosshair (never on top of the day being read), on the side with more room.
    const right = px + 14, leftSide = px - 14 - tipWidth;
    let left = px < hostBox.width / 2 ? right : leftSide;
    if (left + tipWidth > hostBox.width) left = leftSide;
    if (left < 0) left = right + tipWidth <= hostBox.width ? right : Math.max(0, Math.min(hostBox.width - tipWidth, px - tipWidth / 2));
    const plotTop = svgBox.top - hostBox.top;
    let topPx = Math.max(plotTop, Math.min(py - tipHeight / 2, plotTop + (Number(p.svg.getAttribute('data-fc-plot-bottom')) || 180) * scale - tipHeight));
    p.tip.style.left = left + 'px';
    p.tip.style.top = topPx + 'px';
  };
  const indexAt = event => {
    const p = parts();
    if (!p || !p.points.length) return null;
    const box = p.svg.getBoundingClientRect();
    const x = (event.clientX - box.left) * (p.width / (box.width || p.width));
    let best = 0;
    p.points.forEach((point, i) => { if (Math.abs(point.x - x) < Math.abs(p.points[best].x - x)) best = i; });
    return best;
  };
  const onPointer = event => {
    if (!event.target?.closest?.('svg[data-fc-points]')) return;
    if (event.type === 'pointermove' && event.pointerType !== 'mouse' && !event.buttons && !event.pressure) return;
    const index = indexAt(event);
    if (index !== null) show(index);
  };
  container.addEventListener('pointerdown', onPointer);
  container.addEventListener('pointermove', onPointer);
  container.addEventListener('pointerleave', event => { if (event.pointerType === 'mouse') hide(); });
  container.addEventListener('focusin', event => {
    if (!event.target?.matches?.('svg[data-fc-points]')) return;
    const p = parts(); if (!p) return;
    show(active ?? Math.max(0, p.points.findIndex(point => point.low)));
  });
  container.addEventListener('focusout', hide);
  container.addEventListener('keydown', event => {
    if (!event.target?.matches?.('svg[data-fc-points]')) return;
    const p = parts(); if (!p) return;
    const moves = {ArrowLeft: -1, ArrowRight: 1, ArrowDown: -1, ArrowUp: 1};
    if (event.key in moves) show((active ?? 0) + moves[event.key]);
    else if (event.key === 'Home') show(0);
    else if (event.key === 'End') show(p.points.length - 1);
    else if (event.key === 'Escape') hide();
    else return;
    event.preventDefault();
  });
  globalThis.document?.addEventListener?.('pointerdown', event => { if (active !== null && !container.contains(event.target)) hide(); });
}

/** Re-render when the column width no longer matches the width the chart was drawn at
 * (opening the accordion, rotating a phone, switching persona while it was closed). */
export function watchWidth(element, onChange) {
  if (!element || typeof ResizeObserver !== 'function' || element.__fcObserver) return;
  element.__fcObserver = new ResizeObserver(() => {
    const width = element.clientWidth, drawn = Number(element.dataset?.fcDrawnWidth) || 0;
    if (width && Math.abs(width - drawn) > 6) onChange(width);
  });
  element.__fcObserver.observe(element);
}
