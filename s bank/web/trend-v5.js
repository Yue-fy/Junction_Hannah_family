// S-Coach V5 (lane TR): "How spending changes over time" as a line chart with a tooltip.
// The tooltip opens on mouse hover, on tap (phones) and on keyboard focus (arrow keys move between months,
// Escape closes). It shows the month, what was spent and the two biggest categories; a tapped/clicked
// month also offers "See transactions".
import { lineChart, roundEuro } from './charts.js';

const defaultEsc = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const totalOf = row => Number(row?.total_cents ?? row?.consumption_cents ?? row?.value_cents);
const monthOf = row => String(row?.month || row?.period || '');
const mean = list => list.reduce((sum, value) => sum + value, 0) / (list.length || 1);

/**
 * One plain sentence about the months shown.
 * @param {Array<{month:string,total_cents:number}>} rows Months in time order.
 * @param {{t:Function, monthLabel?:Function, format?:Function}} helpers t(key, values) translates `v5.tr.summary.*`;
 *   format(cents) gives the rounded euro amount (defaults to charts.roundEuro).
 * @returns {{kind:'none'|'one'|'up'|'down'|'steady'|'varied', text:string}}
 */
export function trendSummary(rows, {t, monthLabel = month => month, format = roundEuro} = {}) {
  const list = (rows || []).filter(row => Number.isFinite(totalOf(row)));
  if (!list.length) return {kind: 'none', text: ''};
  const values = list.map(totalOf);
  if (list.length === 1) return {kind: 'one', text: t('v5.tr.summary.one', {amount: format(values[0]), month: monthLabel(monthOf(list[0]))})};
  const low = Math.min(...values), high = Math.max(...values), average = mean(values);
  const half = Math.floor(values.length / 2), before = mean(values.slice(0, half)), after = mean(values.slice(values.length - half));
  const change = before > 0 ? (after - before) / before : 0;
  if (Math.abs(change) > 0.12 && values.length >= 4) {
    const kind = change > 0 ? 'up' : 'down';
    return {kind, text: t('v5.tr.summary.' + kind, {from: format(before), to: format(after)})};
  }
  if (average <= 0 || (high - low) / average <= 0.35) return {kind: 'steady', text: t('v5.tr.summary.steady', {low: format(low), high: format(high)})};
  const peak = list[values.indexOf(high)];
  return {kind: 'varied', text: t('v5.tr.summary.varied', {low: format(low), high: format(high), month: monthLabel(monthOf(peak))})};
}

/** "Your salary has been about €2,410 a month lately." or '' when there is no salary median. */
export function salarySentence(cents, {t, format = roundEuro} = {}) {
  return Number.isSafeInteger(cents) && cents > 0 ? t('v5.tr.salary', {amount: format(cents)}) : '';
}

/**
 * Tooltip HTML for one month.
 * @param {{month:string,total_cents:number}} row
 * @param {{esc?:Function,t:Function,money:Function,monthLabel:Function,categories?:Array<{label:string,total_cents:number}>|null,pinned?:boolean}} o
 *   categories: undefined = still loading, null/[] = no breakdown, otherwise the biggest first (two are shown).
 */
export function trendTooltipHTML(row, {esc = defaultEsc, t, money, monthLabel, categories, pinned = false}) {
  const month = monthOf(row);
  const cats = categories === undefined
    ? `<p class="trend5-tip-note">${esc(t('v5.tr.tip.loading'))}</p>`
    : categories?.length
      ? `<ul class="trend5-tip-cats">${categories.slice(0, 2).map(item => `<li><span class="trend5-tip-cat">${esc(item.label)}</span><span class="trend5-tip-amount">${esc(money(item.total_cents))}</span></li>`).join('')}</ul>`
      : `<p class="trend5-tip-note">${esc(t('v5.tr.tip.none'))}</p>`;
  const action = pinned ? `<button type="button" class="trend5-tip-action" data-chart-transactions="${esc(month)}">${esc(t('v5.tr.tip.transactions'))} ›</button>` : '';
  return `<p class="trend5-tip-month">${esc(monthLabel(month))}</p><p class="trend5-tip-total"><strong>${esc(money(totalOf(row)))}</strong> <span>${esc(t('v5.tr.tip.spent'))}</span></p>${cats}${action}`;
}

/** Accessible name of a point: month, amount and (when known) the two biggest categories. */
export function pointLabel(row, {t, money, monthLabel, categories}) {
  const base = t('v5.tr.point', {month: monthLabel(monthOf(row)), amount: money(totalOf(row))});
  return categories?.length ? base + '. ' + categories.slice(0, 2).map(item => `${item.label} ${money(item.total_cents)}`).join(', ') : base;
}

const mounts = new WeakMap();
/** Below this chart width (px) the readout sits under the chart instead of floating over it. */
export const DOCK_BELOW = 560;
let tipSequence = 0;

/**
 * Draw the line chart into container and wire the tooltip.
 * @param {Element} container
 * @param {Array<{month:string,total_cents:number}>} rows
 * @param {{esc?:Function,t:Function,money:Function,monthLabel:Function,
 *   categoriesFor?:(month:string)=>Array|null|undefined, loadCategories?:(months:string[])=>Promise<unknown>,
 *   doc?:Document}} o categoriesFor returns cached categories (undefined = not loaded yet); loadCategories loads them.
 * @returns {{show:(index:number|null, pinned?:boolean)=>void, state:object, destroy:()=>void}}
 */
export function mountTrendChart(container, rows, o) {
  // A redraw with new data (late loads, a basket change) keeps the month the customer had open.
  const previous = mounts.get(container);
  const keepMonth = previous && previous.state.pinned !== null ? previous.state.month?.(previous.state.pinned) : null;
  previous?.destroy();
  const esc = o.esc || defaultEsc, doc = o.doc || globalThis.document;
  const list = (rows || []).filter(row => Number.isFinite(totalOf(row)));
  const tipId = 'trend5-tip-' + (++tipSequence);
  const st = {hover: null, pinned: null, focus: list.length - 1, width: 0, pointerFocus: false, redrawing: false, loading: null};
  container.innerHTML = list.length
    ? `<div class="trend5"><div class="trend5-plot"></div><div class="trend5-tip" id="${tipId}" hidden></div></div>`
      + `<p class="trend5-hint"><span class="trend5-hint-touch">${esc(o.t('v5.tr.hint.tap'))}</span><span class="trend5-hint-hover">${esc(o.t('v5.tr.hint.hover'))}</span></p>`
    : lineChart([]);
  const wrap = container.querySelector('.trend5'), plot = container.querySelector('.trend5-plot'), tip = container.querySelector('.trend5-tip');
  const noop = {show() {}, state: st, destroy() { mounts.delete(container); }};
  if (!wrap) { mounts.set(container, noop); return noop; }
  const categoriesFor = month => o.categoriesFor ? o.categoriesFor(month) : null;
  const labels = () => list.map(row => pointLabel(row, {...o, categories: categoriesFor(monthOf(row))}));
  const points = () => [...plot.querySelectorAll('.lc-pt')];
  const shown = () => st.hover ?? st.pinned;

  function draw() {
    const width = Math.round(plot.clientWidth || 0) || 330;
    st.width = width;
    const focused = points().findIndex(node => node === doc?.activeElement);
    plot.innerHTML = lineChart(list, {width, height: width < 420 ? 210 : width < 640 ? 230 : 250, focusIndex: st.focus, describedBy: tipId, labels: labels()});
    if (focused >= 0) { st.redrawing = true; points()[focused]?.focus?.(); st.redrawing = false; }
  }
  // V5 fix (lane SP2): narrow charts and touch screens get the readout docked under the chart, so it never covers
  // a neighbouring month and one tap on another month moves it. Wide mouse screens keep a floating card pinned to
  // the top of the plot, on the side away from the active month.
  const docked = () => (st.width || 0) < DOCK_BELOW || Boolean(globalThis.matchMedia?.('(hover: none)')?.matches);
  // V5 fix (lane SP2): the readout never floats over the line. Narrow and touch screens: docked under the chart
  // (one tap on another month moves it). Wide mouse screens: a fixed readout row under the chart that shows a hint
  // until a month is pointed at, so nothing covers neighbouring months and the chart never moves.
  function position() {
    const dock = docked();
    tip.classList.toggle('is-docked', dock);
    tip.classList.toggle('is-bar', !dock);
    tip.style.left = ''; tip.style.top = '';
    wrap.classList.toggle('has-bar', !dock);
  }
  function show() {
    const index = shown(), pinned = index !== null && index === st.pinned && st.hover === null;
    const svg = plot.querySelector('svg');
    svg?.classList.toggle('has-active', index !== null);
    points().forEach((node, i) => { node.classList.toggle('is-active', i === index); node.setAttribute('aria-expanded', String(i === index && pinned)); });
    const cross = plot.querySelector('.lc-cross'), dot = index === null ? null : points()[index]?.querySelector('.lc-dot');
    if (cross && dot) { cross.setAttribute('x1', dot.getAttribute('cx')); cross.setAttribute('x2', dot.getAttribute('cx')); }
    if (index === null) {
      position();
      tip.classList.remove('is-pinned');
      if (docked()) { tip.hidden = true; tip.innerHTML = ''; tip.classList.remove('is-idle'); return; }
      tip.innerHTML = `<p class="trend5-tip-hint">${esc(o.t('v5.tr.hint.hover'))}</p>`;
      tip.classList.add('is-idle'); tip.hidden = false; return;
    }
    tip.classList.remove('is-idle');
    const row = list[index], categories = categoriesFor(monthOf(row));
    tip.innerHTML = trendTooltipHTML(row, {esc, t: o.t, money: o.money, monthLabel: o.monthLabel, categories, pinned});
    tip.classList.toggle('is-pinned', pinned);
    tip.hidden = false;
    position();
    if (categories === undefined && o.loadCategories && !st.loading) {
      st.loading = Promise.resolve(o.loadCategories(list.map(monthOf))).catch(() => null).then(() => {
        if (!mounts.has(container) || mounts.get(container) !== api) return;
        points().forEach((node, i) => node.setAttribute('aria-label', labels()[i]));
        if (shown() !== null) show();
      });
    }
  }
  const indexAt = clientX => {
    const nodes = points();
    let best = null, distance = Infinity;
    nodes.forEach((node, i) => {
      const rect = node.querySelector('.lc-dot')?.getBoundingClientRect?.();
      if (!rect) return;
      const d = Math.abs(rect.left + rect.width / 2 - clientX);
      if (d < distance) { distance = d; best = i; }
    });
    return best;
  };
  const indexOf = target => {
    const node = target?.closest?.('.lc-pt');
    const index = node ? Number(node.getAttribute('data-index')) : NaN;
    return Number.isInteger(index) ? index : null;
  };
  const focusPoint = index => {
    st.focus = index;
    points().forEach((node, i) => node.setAttribute('tabindex', i === index ? '0' : '-1'));
    points()[index]?.focus?.();
  };
  const onMove = event => {
    if (event.pointerType && event.pointerType !== 'mouse') return;
    if (st.pinned !== null) return; // a clicked month stays put until closed
    const index = indexAt(event.clientX);
    if (index !== st.hover) { st.hover = index; show(); }
  };
  const onLeave = event => {
    if (event.pointerType && event.pointerType !== 'mouse') return;
    if (st.hover !== null) { st.hover = null; show(); }
  };
  const onDown = () => { st.pointerFocus = true; };
  // Click follows pointerup in the same turn; a drag or scroll that never clicks must not block keyboard focus later.
  const onUp = () => { setTimeout(() => { st.pointerFocus = false; }, 0); };
  const onClick = event => {
    st.pointerFocus = false;
    const index = indexOf(event.target) ?? indexAt(event.clientX);
    if (index === null) return;
    st.hover = null;
    // A tap can focus the month just before its click (touch timing); that same tap must open it, not close it.
    const justFocused = st.focusPinned === index && Date.now() - (st.focusPinnedAt || 0) < 600;
    st.focusPinned = null;
    st.pinned = st.pinned === index && !justFocused ? null : index;
    st.focus = index;
    points().forEach((node, i) => node.setAttribute('tabindex', i === index ? '0' : '-1'));
    show();
  };
  const onFocus = event => {
    const index = indexOf(event.target);
    if (index === null || st.redrawing || st.pointerFocus) return;
    st.focus = index; st.hover = null; st.pinned = index; st.focusPinned = index; st.focusPinnedAt = Date.now();
    points().forEach((node, i) => node.setAttribute('tabindex', i === index ? '0' : '-1'));
    show();
  };
  const onKey = event => {
    const index = indexOf(event.target);
    if (index === null) { if (event.key === 'Escape' && st.pinned !== null) { const back = st.pinned; st.pinned = null; show(); points()[back]?.focus?.(); } return; }
    const moves = {ArrowRight: index + 1, ArrowDown: index + 1, ArrowLeft: index - 1, ArrowUp: index - 1, Home: 0, End: list.length - 1};
    if (event.key in moves) { event.preventDefault?.(); focusPoint(Math.max(0, Math.min(list.length - 1, moves[event.key]))); return; }
    if (event.key === 'Escape') { if (st.pinned !== null || st.hover !== null) { event.preventDefault?.(); st.pinned = null; st.hover = null; show(); } return; }
    if (event.key === 'Enter' || event.key === ' ' || event.key === 'Spacebar') { event.preventDefault?.(); st.pinned = st.pinned === index ? null : index; show(); }
  };
  const onFocusOut = event => {
    if (event.relatedTarget && wrap.contains(event.relatedTarget)) return;
    if (st.pointerFocus) return;
    if (event.relatedTarget && st.pinned !== null) { st.pinned = null; show(); }
  };
  const onOutside = event => {
    if (st.pinned === null || wrap.contains(event.target)) return;
    st.pinned = null; show();
  };
  plot.addEventListener('pointermove', onMove);
  plot.addEventListener('pointerleave', onLeave);
  plot.addEventListener('pointerdown', onDown);
  plot.addEventListener('click', onClick);
  plot.addEventListener('pointerup', onUp);
  plot.addEventListener('pointercancel', onUp);
  wrap.addEventListener('focusin', onFocus);
  wrap.addEventListener('keydown', onKey);
  wrap.addEventListener('focusout', onFocusOut);
  doc?.addEventListener?.('pointerdown', onOutside);
  let observer = null, frame = null;
  if (typeof globalThis.ResizeObserver === 'function') {
    observer = new globalThis.ResizeObserver(() => {
      const width = Math.round(plot.clientWidth || 0);
      if (!width || width === st.width || frame) return;
      frame = (globalThis.requestAnimationFrame || (fn => setTimeout(fn, 16)))(() => { frame = null; draw(); show(); });
    });
    observer.observe(plot);
  }
  const api = {
    state: st,
    show(index, pinned = true) { st.hover = null; st.pinned = pinned ? index : null; if (!pinned) st.hover = index; show(); },
    destroy() {
      observer?.disconnect?.();
      plot.removeEventListener('pointermove', onMove); plot.removeEventListener('pointerleave', onLeave);
      plot.removeEventListener('pointerdown', onDown); plot.removeEventListener('click', onClick);
      plot.removeEventListener('pointerup', onUp); plot.removeEventListener('pointercancel', onUp);
      wrap.removeEventListener('focusin', onFocus); wrap.removeEventListener('keydown', onKey); wrap.removeEventListener('focusout', onFocusOut);
      doc?.removeEventListener?.('pointerdown', onOutside);
      if (mounts.get(container) === api) mounts.delete(container);
    },
  };
  st.month = index => monthOf(list[index]);
  mounts.set(container, api);
  if (keepMonth) { const index = list.findIndex(row => monthOf(row) === keepMonth); if (index >= 0) { st.pinned = index; st.focus = index; } }
  draw();
  show();
  return api;
}
