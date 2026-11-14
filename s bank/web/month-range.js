/* Compact from-month -> to-month range control (WP-G). Dependency-free; months are 'YYYY-MM' strings, inclusive. */
const esc = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const fill = (text, values) => String(text ?? '').replace(/\{(\w+)\}/g, (_, key) => values?.[key] ?? '{' + key + '}');
const MONTH = /^(\d{4})-(0[1-9]|1[0-2])$/;

/** 'YYYY-MM' -> integer month index (year*12 + month-1), or null when malformed. */
export function monthIndex(month) {
  const match = MONTH.exec(String(month ?? ''));
  return match ? Number(match[1]) * 12 + Number(match[2]) - 1 : null;
}
/** Integer month index -> 'YYYY-MM'. */
export function monthFromIndex(index) {
  const year = Math.floor(index / 12), month = index - year * 12 + 1;
  return String(year).padStart(4, '0') + '-' + String(month).padStart(2, '0');
}
/** Inclusive number of months from start to end ('YYYY-MM'); 0 when malformed or reversed. */
export function monthSpan(start, end) {
  const a = monthIndex(start), b = monthIndex(end);
  return a === null || b === null || b < a ? 0 : b - a + 1;
}

/**
 * Pure: normalise a month range.
 * @param {{start:string,end:string,min:string,max:string,maxSpan?:number,anchor?:'start'|'end'}} range
 *   YYYY-MM strings; maxSpan in months (default 24, at least 1). anchor names the end the user just changed.
 * @returns {{start:string,end:string,min:string,max:string,maxSpan:number,months:number}}
 *   Both ends clamped into [min,max] (min/max swapped if reversed; a missing/malformed end falls back to the
 *   bound). If start > end: with anchor 'start' end moves to start, with anchor 'end' start moves to end, with no
 *   anchor the two are swapped. If the span exceeds maxSpan the end opposite the anchor moves (default: start
 *   moves, keeping end). months is the inclusive month count, as /api/trends `months` expects.
 */
export function clampRange({start, end, min, max, maxSpan = 24, anchor = null} = {}) {
  let low = monthIndex(min), high = monthIndex(max);
  if (low === null && high === null) throw new TypeError('clampRange needs a valid min or max month (YYYY-MM)');
  if (low === null) low = high; if (high === null) high = low;
  if (low > high) [low, high] = [high, low];
  const span = Math.max(1, Math.floor(Number(maxSpan)) || 24);
  const clamp = value => Math.min(high, Math.max(low, value));
  let a = monthIndex(start), b = monthIndex(end);
  b = b === null ? high : clamp(b);
  a = a === null ? Math.max(low, b - Math.min(span, 12) + 1) : clamp(a);
  if (a > b) {
    if (anchor === 'start') b = a;
    else if (anchor === 'end') a = b;
    else [a, b] = [b, a];
  }
  if (b - a + 1 > span) {
    if (anchor === 'start') b = a + span - 1;
    else a = b - span + 1;
  }
  return {start: monthFromIndex(a), end: monthFromIndex(b), min: monthFromIndex(low), max: monthFromIndex(high), maxSpan: span, months: b - a + 1};
}

/**
 * Pure: move one end of a range by delta months, then clamp with that end as the anchor (so the other end moves
 * if needed to keep start <= end and span <= maxSpan).
 * @param {{start:string,end:string,min:string,max:string,maxSpan?:number}} range
 * @param {'start'|'end'} which End to move.
 * @param {number} delta Months (negative = earlier). "−1 month" on the start extends the range, "+1" shrinks it.
 * @returns Same shape as clampRange.
 */
export function stepRange(range, which, delta) {
  const key = which === 'end' ? 'end' : 'start';
  const current = clampRange(range);
  const moved = monthFromIndex(monthIndex(current[key]) + (Math.trunc(Number(delta)) || 0));
  return clampRange({...current, [key]: moved, anchor: key});
}

/**
 * Pure: the range "last N months" ending at `end` (default 12 months ending at max).
 * @returns Same shape as clampRange.
 */
export function lastMonthsRange({end, min, max, maxSpan = 24, months = 12}) {
  const last = clampRange({start: end ?? max, end: end ?? max, min, max, maxSpan, anchor: 'end'}).end;
  const count = Math.max(1, Math.min(Math.floor(Number(months)) || 12, Math.max(1, Math.floor(Number(maxSpan)) || 24)));
  return clampRange({start: monthFromIndex(monthIndex(last) - count + 1), end: last, min, max, maxSpan, anchor: 'end'});
}

/**
 * HTML for the range control.
 * @param {{start:string,end:string,min:string,max:string,maxSpan?:number,monthLabel?:(month:string)=>string,
 *   defaultEnd?:string,t?:(key:string,values:object,fallback:string)=>string,id?:string}} options
 *   min/max: observed_start/observed_end (YYYY-MM). defaultEnd: end month used by the reset button (default max;
 *   pass the selected month). monthLabel formats option text (default the YYYY-MM value). t localizes labels.
 * @returns {string} `<div class="month-range" data-month-range ...>` with two selects (data-month-range-from,
 *   data-month-range-to), step buttons (data-month-range-step="-1"|"1", acting on the start) and a reset button
 *   (data-month-range-reset). Options listed newest first. Wire with attachMonthRange.
 */
export function renderMonthRange({start, end, min, max, maxSpan = 24, monthLabel = null, defaultEnd = null, t = null, id = 'month-range'} = {}) {
  const range = clampRange({start, end, min, max, maxSpan});
  const label = typeof monthLabel === 'function' ? monthLabel : month => month;
  const tr = (key, values, fallback) => { const value = typeof t === 'function' ? t(key, values, fallback) : null; return value && value !== key ? String(value) : fill(fallback, values); };
  const low = monthIndex(range.min), high = monthIndex(range.max), from = monthIndex(range.start), to = monthIndex(range.end);
  const options = selected => { let html = ''; for (let index = high; index >= low; index--) { const month = monthFromIndex(index); html += `<option value="${month}"${index === selected ? ' selected' : ''}>${esc(label(month))}</option>`; } return html; };
  const resetEnd = clampRange({start: range.min, end: defaultEnd ?? range.max, min: range.min, max: range.max, maxSpan: range.maxSpan}).end;
  const reset = lastMonthsRange({end: resetEnd, min: range.min, max: range.max, maxSpan: range.maxSpan});
  const canExtend = from > low, canShrink = from < to || to < high;
  const safeId = esc(id);
  return `<div class="month-range" data-month-range data-min="${range.min}" data-max="${range.max}" data-max-span="${range.maxSpan}" data-default-end="${resetEnd}" role="group" aria-label="${esc(tr('range.label', {}, 'Month range'))}">`
    + `<div class="month-range-fields"><label class="month-range-field" for="${safeId}-from"><span>${esc(tr('range.from', {}, 'From'))}</span><select id="${safeId}-from" data-month-range-from>${options(from)}</select></label>`
    + `<span class="month-range-arrow" aria-hidden="true">→</span>`
    + `<label class="month-range-field" for="${safeId}-to"><span>${esc(tr('range.to', {}, 'To'))}</span><select id="${safeId}-to" data-month-range-to>${options(to)}</select></label></div>`
    + `<div class="month-range-actions"><button type="button" class="month-range-step" data-month-range-step="-1"${canExtend ? '' : ' disabled'}>${esc(tr('range.earlier', {}, '−1 month'))}</button>`
    + `<button type="button" class="month-range-step" data-month-range-step="1"${canShrink ? '' : ' disabled'}>${esc(tr('range.later', {}, '+1 month'))}</button>`
    + `<button type="button" class="month-range-reset" data-month-range-reset${reset.start === range.start && reset.end === range.end ? ' aria-pressed="true"' : ''}>${esc(tr('range.last12', {}, 'Last 12 months'))}</button></div>`
    + `<p class="month-range-summary" aria-live="polite">${esc(tr('range.summary', {count: range.months, start: label(range.start), end: label(range.end)}, '{count} months: {start} – {end}'))}</p></div>`;
}

const attr = (element, name) => element?.getAttribute?.(name) ?? null;
/**
 * Pure-ish helper: the new range implied by a change/click event inside a rendered control, or null.
 * Reads bounds from the closest [data-month-range] root and the current values of its two selects.
 * @param {{type:string,target:Element}} event
 * @returns Same shape as clampRange, or null when the event is not for the control.
 */
export function monthRangeFromEvent(event) {
  const target = event?.target;
  const root = target?.closest?.('[data-month-range]');
  if (!root) return null;
  const bounds = {min: attr(root, 'data-min'), max: attr(root, 'data-max'), maxSpan: Number(attr(root, 'data-max-span')) || 24};
  const current = {...bounds, start: root.querySelector?.('[data-month-range-from]')?.value, end: root.querySelector?.('[data-month-range-to]')?.value};
  if (event.type === 'change') {
    if (target.hasAttribute?.('data-month-range-from')) return clampRange({...current, anchor: 'start'});
    if (target.hasAttribute?.('data-month-range-to')) return clampRange({...current, anchor: 'end'});
    return null;
  }
  if (event.type !== 'click') return null;
  const button = target.closest?.('[data-month-range-step],[data-month-range-reset]');
  if (!button || button.disabled) return null;
  if (button.hasAttribute?.('data-month-range-reset')) return lastMonthsRange({...bounds, end: attr(root, 'data-default-end') || bounds.max});
  return stepRange(current, 'start', Number(attr(button, 'data-month-range-step')));
}

const bindings = new WeakMap();
/**
 * Wire a container holding renderMonthRange markup (event delegation; survives innerHTML re-renders).
 * Idempotent: calling again on the same container swaps the callback and returns the same detach function.
 * The control does not re-render itself: re-render with the range passed to onChange.
 * @param {Element} container
 * @param {(range:{start:string,end:string,min:string,max:string,maxSpan:number,months:number})=>void} onChange
 *   Called only when the range actually changes (or a select needed correcting). Use range.end as end_month and
 *   range.months as months for /api/trends.
 * @returns {()=>void} Detach function.
 */
export function attachMonthRange(container, onChange) {
  if (!container?.addEventListener) return () => {};
  const existing = bindings.get(container);
  if (existing) { existing.onChange = onChange; return existing.detach; }
  const binding = {onChange};
  const handler = event => {
    const range = monthRangeFromEvent(event);
    if (range) binding.onChange?.(range);
  };
  container.addEventListener('change', handler);
  container.addEventListener('click', handler);
  binding.detach = () => {
    container.removeEventListener('change', handler);
    container.removeEventListener('click', handler);
    if (bindings.get(container) === binding) bindings.delete(container);
  };
  bindings.set(container, binding);
  return binding.detach;
}
