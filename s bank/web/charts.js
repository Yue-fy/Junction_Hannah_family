const esc = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
let chartLocale='en-IE', chartTranslate=null;
export function configureCharts({locale,translate}){chartLocale=locale;chartTranslate=translate;}
const ct=(key,values,fallback)=>{const translated=chartTranslate?.(key,values);return translated&&translated!==key?translated:String(fallback).replace(/\{(\w+)\}/g,(_,key)=>values?.[key]??'{'+key+'}');};
const euro = value => new Intl.NumberFormat(chartLocale,{style:'currency',currency:'EUR'}).format(Number(value)/100);
let sequence = 0;
const svg = (title, description, body, height, interactive=null) => {
  const id = 'chart-' + (++sequence);
  // Interactive charts use role="group": children of role="img" are presentational and their buttons would be hidden.
  const head = interactive ? `class="chart-interactive${interactive.selected?' has-selection':''}" style="--chart-columns:${interactive.columns}" role="group"` : 'role="img"';
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 330 ${height}" ${head} aria-labelledby="${id}-title ${id}-desc"><title id="${id}-title">${esc(title)}</title><desc id="${id}-desc">${esc(description)}</desc>${body}</svg>`;
};
const validIndex = (value, length) => Number.isInteger(value) && value >= 0 && value < length ? value : null;
/** Wrap one bar's marks in a focusable hit target covering the whole column (x, y, width, height in viewBox units). */
const hitTarget = (index, label, selected, rect, marks) => `<g class="chart-bar${selected===index?' is-selected':selected===null?'':' is-dimmed'}" role="button" tabindex="0" data-index="${index}" aria-label="${esc(label)}" aria-pressed="${selected===index}"><rect class="chart-hit" x="${rect.x}" y="${rect.y}" width="${rect.width}" height="${rect.height}" fill="transparent"/>${marks}</g>`;
const SELECTED_FILL = '#2c5230', SELECTED_STROKE = '#163e30', DIMMED_OPACITY = '0.6';
const empty = message => `<p class="empty-state">${esc(message)}</p>`;
export const palette = ['#466d48','#c2d7a3','#e1bd91','#92a88b','#c7c8bd','#eadac2'];
export const categoryPalette = Object.freeze({
  'Housing':'#367d62', 'Utilities':'#8fac75', 'Groceries':'#b7cb63',
  'Transportation':'#79b4b9', 'Restaurants':'#e7a274', 'Health':'#b5a0c7',
  'Home & Tech':'#cfba84', 'Entertainment':'#d78eab', 'Lifestyle':'#8b9dc2',
  'Travel':'#81b7a0'
});

const iconPaths = Object.freeze({
  'Housing':'M3 10 12 3l9 7M5 9v11h14V9M9 20v-7h6v7',
  'Utilities':'m13 2-8 12h6l-1 8 9-12h-6z',
  'Groceries':'M3 5h2l2 12h11l3-9H6M9 21h.01M17 21h.01M10 4v7M7 7h6',
  'Transportation':'M5 16H3V9l3-5h12l3 5v7h-2M5 16h14M5 9h14M6 16v4M18 16v4M7 12h.01M17 12h.01',
  'Restaurants':'M5 3v7M9 3v7M5 7h4M7 10v11M17 21V3c-4 2-4 10 0 10',
  'Health':'M10 3h4v7h7v4h-7v7h-4v-7H3v-4h7z',
  'Home & Tech':'M3 4h18v12H3zM9 21h6M12 16v5',
  'Entertainment':'m9 4 12-2v15M9 4v15M9 8l12-2M9 19c0 2-2 3-4 3s-3-1-3-2 2-3 4-3 3 1 3 2M21 17c0 2-2 3-4 3s-3-1-3-2 2-3 4-3 3 1 3 2',
  'Lifestyle':'M5 7h14l2 14H3L5 7ZM8 8V6a4 4 0 0 1 8 0v2',
  'Travel':'m3 10 8 2 4 9 2-1-1-9 6-6-1-2-7 5-9-2z'
});

export function categoryIcon(category) {
  const path=iconPaths[category]||'M5 5h5v5H5zM14 5h5v5h-5zM5 14h5v5H5zM14 14h5v5h-5z';
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="${path}"/></svg>`;
}

/** Render a category-only consumption ring; source totals and category labels are supplied by the caller. */
export function spendingRing(categories, selected=null) {
  const rows=(Array.isArray(categories)?categories:[]).map(row=>({
    ...row,
    category:String(row.category??row.name??''),
    label:String(row.label??row.category??row.name??''),
    value:Number(row.total_cents??row.amount_cents??row.consumption_cents)
  })).filter(row=>row.category&&Number.isSafeInteger(row.value)&&row.value>0);
  const total=rows.reduce((sum,row)=>sum+row.value,0);
  if(!total)return empty(ct('chart.noSpending',{},'No recorded spending in this selection.'));
  const id='spending-ring-'+(++sequence),radius=110,circumference=2*Math.PI*radius;
  const selectedCategory=typeof selected==='object'?selected?.category:selected;
  const hasSelection=rows.some(row=>row.category===selectedCategory);
  let offset=0;
  const segments=rows.map(row=>{
    const length=row.value/total*circumference;
    const gap=Math.min(4,length*.2);
    const percent=new Intl.NumberFormat(chartLocale,{style:'percent',maximumFractionDigits:1}).format(row.value/total);
    const color=categoryPalette[row.category]||'#92ac87';
    const label=`${row.label}: ${euro(row.value)} · ${percent}`;
    const circle=`<circle class="ring-segment" cx="150" cy="150" r="${radius}" fill="none" stroke="${color}" stroke-width="32" stroke-dasharray="${(length-gap).toFixed(4)} ${(circumference-length+gap).toFixed(4)}" stroke-dashoffset="${(-offset-gap/2).toFixed(4)}" role="button" tabindex="0" aria-label="${esc(label)}" aria-pressed="${row.category===selectedCategory}" data-spending-category="${esc(row.category)}"><title>${esc(label)}</title></circle>`;
    offset+=length;
    return circle;
  }).join('');
  const description=rows.map(row=>`${row.label}: ${euro(row.value)}`).join('. ');
  // Track and arcs share one SVG transform; CSS must not add a second rotation origin.
  return `<svg xmlns="http://www.w3.org/2000/svg" class="spending-ring${hasSelection?' has-selection':''}" viewBox="0 0 300 300" role="group" aria-labelledby="${id}-title ${id}-desc"><title id="${id}-title">${esc(ct('chart.spendingCategories',{},'Spending by category'))}</title><desc id="${id}-desc">${esc(description)}. ${esc(ct('chart.selectCategory',{},'Select a segment or use the category list to explore its transactions.'))}</desc><g transform="rotate(-90 150 150)"><circle class="ring-track" cx="150" cy="150" r="${radius}" fill="none" stroke-width="32"/>${segments}</g></svg>`;
}
export function flowChart(flows) {
  const income = flows.find(row => row.role === 'income');
  const rows = flows.map((row,index)=>({...row,index})).filter(row => row.role !== 'income' && Number.isFinite(Number(row.total_cents)) && Math.abs(Number(row.total_cents)) > 0);
  const total = rows.reduce((sum, row) => sum + Math.abs(row.total_cents), 0);
  if (!total) return empty('No money flow for this selection.');
  let x = 0;
  const bars = rows.map((row,index) => {
    const width = Math.abs(row.total_cents) / total * 330;
    const part = `<rect x="${x.toFixed(2)}" y="${income?26:0}" width="${width.toFixed(2)}" height="29" fill="${palette[row.index%palette.length]}"/><text x="${(x+width/2).toFixed(2)}" y="${income?45:19}" text-anchor="middle" fill="${row.index===0?'#fff':'#263825'}" font-size="10">${width>24?row.index+1:''}</text>`;
    x += width; return part;
  }).join('');
  const heading = income ? `<text x="0" y="11" class="chart-note">Income: ${euro(Math.abs(income.total_cents))}</text><text x="330" y="11" text-anchor="end" class="chart-note">Outflows: ${euro(total)}</text>` : '';
  return svg('Monthly money flow', (income?`Income: ${euro(Math.abs(income.total_cents))}. Outflows: ${euro(total)}. `:'') + rows.map(row => `${row.index+1}. ${row.label}: ${euro(Math.abs(row.total_cents))}`).join('. '), heading + bars, income?55:29);
}
export function comparisonChart(data) {
  const before=data.before, after=data.after;
  if (!before || !after) return empty(ct('chart.noComparison',{},'No complete comparison periods available.'));
  const max=Math.max(before.total_cents,after.total_cents,1);
  const rows=[before,after];
  const labels=[before.label || 'Previous period',after.label || 'Current period'];
  const bars=rows.map((row,i)=>{
    const y=i*70;
    return `<text x="0" y="${y+12}" class="chart-label">${esc(labels[i])}</text><text x="330" y="${y+12}" text-anchor="end" class="chart-value">${euro(row.total_cents)}</text><rect x="0" y="${y+25}" width="330" height="23" rx="5" fill="#e8ecdf"/><rect x="0" y="${y+25}" width="${Math.max(0,row.total_cents/max*330)}" height="23" rx="5" fill="${i?'#466d48':'#b8cd98'}"/><text x="0" y="${y+62}" class="chart-note">${esc(ct('chart.purchases',{count:row.count},'{count} purchases'))} · ${esc(row.average_cents===null||row.average_cents===undefined?ct('chart.noAverage',{},'Average unavailable'):ct('chart.average',{amount:euro(row.average_cents)},'{amount} average'))}</text>`;
  }).join('');
  return svg(ct('chart.comparison',{},'Restaurant spending comparison'), rows.map((row,i)=>`${labels[i]}: ${euro(row.total_cents)}, ${ct('chart.purchases',{count:row.count},'{count} purchases')}`).join('. '), bars, 135);
}
/**
 * Horizontal amount bars.
 * @param {Array<{label:string,value_cents:number}>} series Rows with integer cents; non-integer rows are skipped.
 * @param {{interactive?:boolean,selectedIndex?:number|null}} [options] When interactive, every row becomes a
 *   focusable `<g role="button" data-index>` (index into the filtered rows) covering the full row; the row at
 *   `selectedIndex` is highlighted with aria-pressed="true" and the others dimmed. Omitted options give the original output.
 * @returns {string} SVG markup (viewBox width 330), or '' when there are no rows.
 */
export function barChart(series, options={}) {
  const rows=(series||[]).filter(row=>Number.isSafeInteger(row.value_cents));
  if(!rows.length)return '';
  const interactive=Boolean(options?.interactive), selected=interactive?validIndex(options?.selectedIndex,rows.length):null;
  const min=Math.min(0,...rows.map(row=>row.value_cents)),max=Math.max(0,...rows.map(row=>row.value_cents)),range=max-min||1,zero=-min/range*330;
  const body=rows.map((row,index)=>{
    const y=index*65,position=(row.value_cents-min)/range*330,label=String(row.label??'');
    if(!interactive)return `<text x="0" y="${y+12}" class="chart-label"><title>${esc(label)}</title>${esc(label.length>44?label.slice(0,41)+'…':label)}</text><text x="330" y="${y+30}" text-anchor="end" class="chart-value">${esc(euro(row.value_cents))}</text><rect x="0" y="${y+39}" width="330" height="16" rx="4" fill="#e8ecdf"/><rect x="${Math.min(zero,position)}" y="${y+39}" width="${Math.abs(position-zero)}" height="16" rx="4" fill="#466d48"/>`;
    const isSelected=selected===index, dim=selected!==null&&!isSelected?` opacity="${DIMMED_OPACITY}"`:'';
    const marks=`<text x="0" y="${y+12}" class="chart-label"${dim}>${esc(label.length>44?label.slice(0,41)+'…':label)}</text><text x="330" y="${y+30}" text-anchor="end" class="chart-value"${dim}>${esc(euro(row.value_cents))}</text><rect x="0" y="${y+39}" width="330" height="16" rx="4" fill="#e8ecdf"/><rect class="chart-bar-mark" x="${Math.min(zero,position)}" y="${y+39}" width="${Math.abs(position-zero)}" height="16" rx="4" fill="${isSelected?SELECTED_FILL:'#466d48'}"${isSelected?` stroke="${SELECTED_STROKE}" stroke-width="1.5"`:dim}/>`;
    return hitTarget(index,`${label}: ${euro(row.value_cents)}`,selected,{x:0,y,width:330,height:65},marks);
  }).join('');
  return svg(ct('agent.chart',{},'Recorded amounts'),rows.map(row=>`${row.label}: ${euro(row.value_cents)}`).join('. '),body,rows.length*65,interactive?{columns:1,selected:selected!==null}:null);
}
/**
 * Vertical period bars (monthly spending trend).
 * @param {Array<{period?:string,month?:string,label?:string,total_cents?:number,consumption_cents?:number,value_cents?:number}>} rows
 * @param {{interactive?:boolean,selectedIndex?:number|null}} [options] When interactive, each column is a focusable
 *   `<g role="button" tabindex="0" data-index="i" aria-label="<period>: <amount>" aria-pressed>` covering the full
 *   column height; the SVG gets class "chart-interactive" and `--chart-columns` so CSS can keep each column >= 32px wide.
 *   Omitted options give the original output (last bar dark, others light).
 * @returns {string} SVG markup (viewBox 330x151) or an empty-state paragraph.
 */
export function trendChart(rows, options={}) {
  if (!rows?.length) return empty(ct('chart.noTrend',{},'No complete periods available for this trend.'));
  const values=rows.map(row=>Number(row.total_cents ?? row.consumption_cents ?? row.value_cents ?? 0));
  const max=Math.max(...values,1); const step=330/rows.length;
  const interactive=Boolean(options?.interactive), selected=interactive?validIndex(options?.selectedIndex,rows.length):null;
  const bars=rows.map((row,i)=>{const height=Math.max(1,values[i]/max*100),show=i===rows.length-1||i%Math.ceil(rows.length/6)===0;
    const tick=show?`<text transform="translate(${i*step+step/2},127) rotate(-35)" text-anchor="end" class="chart-note">${esc((row.period || row.month || row.label || '').slice(-5))}</text>`:'';
    if(!interactive)return `<rect x="${i*step+3}" y="${110-height}" width="${Math.max(2,step-6)}" height="${height}" rx="3" fill="${i===rows.length-1?'#466d48':'#b9cba3'}"/>${tick}`;
    const isSelected=selected===i, fill=isSelected?SELECTED_FILL:(selected===null&&i===rows.length-1?'#466d48':'#b9cba3');
    const marks=`<rect class="chart-bar-mark" x="${i*step+3}" y="${110-height}" width="${Math.max(2,step-6)}" height="${height}" rx="3" fill="${fill}"${isSelected?` stroke="${SELECTED_STROKE}" stroke-width="1.5"`:selected!==null?` opacity="${DIMMED_OPACITY}"`:''}/>`;
    return hitTarget(i,`${row.period||row.month||row.label||''}: ${euro(values[i])}`,selected,{x:i*step,y:0,width:step,height:131},marks)+tick;}).join('');
  return svg(ct('chart.trend',{},'Complete-month spending trend'), rows.map((row,i)=>`${row.period||row.month||row.label}: ${euro(values[i])}`).join('. '),bars,151,interactive?{columns:rows.length,selected:selected!==null}:null);
}
export function runwayChart(rows) {
  if (!rows?.length) return empty(ct('chart.noRunway',{},'A cash-flow estimate is not available for this account yet.'));
  const values=rows.map(row=>Number(row.balance_cents));
  const bounds=rows.flatMap(row=>row.historical_flexible_scenarios?Object.values(row.historical_flexible_scenarios):[row.balance_cents]);
  const min=Math.min(...values,...bounds), max=Math.max(...values,...bounds), span=Math.max(max-min,1);
  const xy=(row,i)=>[8+i/Math.max(rows.length-1,1)*314,93-(Number(row.balance_cents)-min)/span*75];
  const pointList=rows.map(xy); const observed=rows.filter(row=>row.status!=='scenario' && row.kind!=='scenario' && !row.projected);
  const split=Math.max(0,observed.length-1);
  const solid=pointList.slice(0,split+1).map(point=>point.join(',')).join(' ');
  const dashed=pointList.slice(split).map(point=>point.join(',')).join(' ');
  const start=pointList[0];
  const scenarioRows=rows.map((row,index)=>({row,index})).filter(({row})=>row.historical_flexible_scenarios);
  const bandPoints=key=>scenarioRows.map(({row,index})=>xy({balance_cents:row.historical_flexible_scenarios[key]},index).join(','));
  const band=scenarioRows.length?`<polygon points="${[...bandPoints('p25'),...bandPoints('p75').reverse()].join(' ')}" fill="#d5e2bd" opacity="0.7"/>`:'';
  return svg(ct('chart.runway',{},'Pattern-based cash-flow preview'), ct('chart.runwayDescription',{start:euro(values[0]),end:euro(values.at(-1))},'Observed starting balance {start}. Scenario ending balance {end}. Historical variation, not a probability interval.'), `<line x1="0" y1="103" x2="330" y2="103" stroke="#e2e6d9"/>${band}<polyline points="${solid}" fill="none" stroke="#466d48" stroke-width="2.5"/><polyline points="${dashed}" fill="none" stroke="#466d48" stroke-width="2.5" stroke-dasharray="5 5"/><circle cx="${start[0]}" cy="${start[1]}" r="4" fill="#466d48"/><text x="0" y="121" class="chart-note">${esc(ct('chart.recent',{},'Recent observed activity'))}</text><text x="330" y="121" text-anchor="end" class="chart-note">${esc(ct('chart.next30',{},'30-day estimate'))}</text><text x="0" y="10" class="chart-note">${euro(max)}</text>`,130);
}
export function goalChart(current,target) {
  if (!Number.isFinite(target) || target<=0) return empty(ct('chart.noGoal',{},'Choose a target to see your progress.'));
  const ratio=Math.min(1,Math.max(0,current/target));
  return svg(ct('chart.goal',{},'Goal progress'),ct('chart.goalDescription',{current:euro(current),target:euro(target),percent:Math.round(ratio*100)},'{current} saved toward {target}. {percent}% complete.'),`<rect width="330" height="10" rx="5" fill="#d5dfc5"/><rect width="${ratio*330}" height="10" rx="5" fill="#466d48"/><text x="0" y="29" class="chart-note">${esc(ct('chart.saved',{percent:Math.round(ratio*100)},'{percent}% saved'))}</text><text x="330" y="29" text-anchor="end" class="chart-note">${esc(ct('chart.target',{amount:euro(target)},'{amount} target'))}</text>`,34);
}

/* ---------- V3: selection wiring, detail panel, cash-flow chart ---------- */

/**
 * Pure helper: the bar index an event selects, or null.
 * @param {{type:string,key?:string,target?:{closest?:Function}}} event A click or keydown event.
 * @param {{contains?:Function}} [container] When given, the matched element must be inside it.
 * @returns {number|null} Integer index from the nearest `[data-index]` ancestor; null for other keys/targets.
 */
export function chartSelectionIndex(event, container=null) {
  if (!event) return null;
  if (event.type === 'keydown' && !['Enter',' ','Spacebar'].includes(event.key)) return null;
  if (event.type !== 'click' && event.type !== 'keydown') return null;
  const element = event.target?.closest?.('[data-index]');
  if (!element || (container?.contains && !container.contains(element))) return null;
  const index = Number(element.getAttribute?.('data-index') ?? element.dataset?.index);
  return Number.isInteger(index) && index >= 0 ? index : null;
}
const selectionBindings = new WeakMap();
/**
 * Wire click and Enter/Space on `[data-index]` elements inside container (event delegation, so re-rendering
 * the chart with innerHTML needs no re-wiring). Idempotent: a second call on the same container only swaps
 * the callback and returns the same detach function.
 * @param {Element} container Element holding chart markup from trendChart/barChart/cashflowChart with interactive:true.
 * @param {(index:number)=>void} onSelect Called with the selected bar index.
 * @returns {()=>void} Detach function that removes the listeners.
 */
export function attachChartSelection(container, onSelect) {
  if (!container?.addEventListener) return () => {};
  const existing = selectionBindings.get(container);
  if (existing) { existing.onSelect = onSelect; return existing.detach; }
  const binding = { onSelect };
  const handler = event => {
    const index = chartSelectionIndex(event, container);
    if (index === null) return;
    if (event.type === 'keydown') event.preventDefault?.();
    binding.onSelect?.(index);
  };
  container.addEventListener('click', handler);
  container.addEventListener('keydown', handler);
  binding.detach = () => {
    container.removeEventListener('click', handler);
    container.removeEventListener('keydown', handler);
    if (selectionBindings.get(container) === binding) selectionBindings.delete(container);
  };
  selectionBindings.set(container, binding);
  return binding.detach;
}

const fill = (text, values) => String(text ?? '').replace(/\{(\w+)\}/g, (_, key) => values?.[key] ?? '{' + key + '}');
const translator = t => (key, values, fallback) => {
  const translated = typeof t === 'function' ? t(key, values, fallback) : ct(key, values, fallback);
  return translated && translated !== key ? String(translated) : fill(fallback, values);
};
const cents = value => Number.isSafeInteger(value) ? value : null;

/**
 * HTML for the detail panel shown below a selected bar.
 * @param {{month:string,label?:string,total_cents:number,previous_total_cents?:number|null,
 *   categories?:Array<{category?:string,label?:string,total_cents:number}>}} detail
 *   month is YYYY-MM (used in the button data attributes); label is the display title (defaults to month);
 *   previous_total_cents enables the change line (amount and percent; percent only when previous > 0);
 *   the first three categories are shown in the given order (caller sorts).
 * @param {{money?:(cents:number)=>string,t?:(key:string,values:object,fallback:string)=>string}} [helpers]
 * @returns {string} `<section class="chart-detail">` markup with buttons `data-chart-transactions="<month>"` and
 *   `data-chart-ask="<month>"`, or '' when detail has no valid total.
 */
export function chartDetailPanel(detail, {money=euro, t=null}={}) {
  const total = cents(detail?.total_cents);
  if (total === null) return '';
  const tr = translator(t), format = value => String(money(value));
  const month = String(detail.month ?? ''), title = String(detail.label ?? month);
  const previous = cents(detail.previous_total_cents);
  let change = `<p class="chart-detail-change is-none">${esc(tr('chart.detail.noPrevious', {}, 'No previous month to compare'))}</p>`;
  if (previous !== null) {
    const delta = total - previous;
    const direction = delta > 0 ? 'up' : delta < 0 ? 'down' : 'same';
    const percent = previous > 0 ? new Intl.NumberFormat(chartLocale, {style:'percent', maximumFractionDigits:1, signDisplay:'exceptZero'}).format(delta / previous) : '';
    const arrow = {up:'↑', down:'↓', same:'→'}[direction];
    const values = {amount: format(Math.abs(delta)), percent};
    const fallback = {up: percent ? 'Up {amount} ({percent}) vs previous month' : 'Up {amount} vs previous month',
      down: percent ? 'Down {amount} ({percent}) vs previous month' : 'Down {amount} vs previous month',
      same: 'Same as previous month'}[direction];
    change = `<p class="chart-detail-change is-${direction}"><span aria-hidden="true">${arrow}</span> ${esc(tr('chart.detail.change.' + direction + (percent || direction === 'same' ? '' : 'NoPercent'), values, fallback))}</p>`;
  }
  const categories = (Array.isArray(detail.categories) ? detail.categories : []).filter(row => cents(row?.total_cents) !== null).slice(0, 3);
  const list = categories.length
    ? `<h4 class="chart-detail-subtitle">${esc(tr('chart.detail.topCategories', {}, 'Top categories'))}</h4><ul class="chart-detail-categories">${categories.map(row => `<li><span>${esc(row.label ?? row.category ?? '')}</span><span>${esc(format(row.total_cents))}</span></li>`).join('')}</ul>`
    : `<p class="chart-detail-empty">${esc(tr('chart.detail.noCategories', {}, 'No category breakdown for this month'))}</p>`;
  return `<section class="chart-detail" aria-label="${esc(tr('chart.detail.label', {month:title}, 'Details for {month}'))}"><h3 class="chart-detail-title">${esc(title)}</h3><p class="chart-detail-total"><span>${esc(tr('chart.detail.total', {}, 'Total'))}</span> <strong>${esc(format(total))}</strong></p>${change}${list}<div class="chart-detail-actions"><button type="button" class="secondary-button" data-chart-transactions="${esc(month)}">${esc(tr('chart.detail.transactions', {}, 'See transactions'))}</button><button type="button" class="secondary-button" data-chart-ask="${esc(month)}">${esc(tr('chart.detail.ask', {}, 'Ask coach about this month'))}</button></div></section>`;
}

/**
 * Money in vs money out per period: paired bars (income, spending), a net line with dots, a dashed zero
 * baseline when any net is negative, hatched + labelled partial periods and a text legend.
 * @param {Array<{label:string,income_cents:number,consumption_cents:number,savings_transfers_cents?:number,
 *   net_cents?:number,complete?:boolean}>} rows Periods in time order; rows without integer income and
 *   consumption cents are skipped (indices refer to the remaining rows). net_cents is drawn as given
 *   (income − consumption − savings transfers, computed by the backend); missing net leaves a gap.
 * @param {{interactive?:boolean,selectedIndex?:number|null}} [options] Same selection markup as trendChart.
 * @returns {string} SVG markup (viewBox 330x180) or an empty-state paragraph.
 */
export function cashflowChart(rows, options={}) {
  const data = (Array.isArray(rows) ? rows : []).filter(row => cents(row?.income_cents) !== null && cents(row?.consumption_cents) !== null);
  if (!data.length) return empty(ct('chart.cashflow.empty', {}, 'No income or spending recorded for this range.'));
  const interactive = Boolean(options?.interactive), selected = interactive ? validIndex(options?.selectedIndex, data.length) : null;
  const id = 'cashflow-' + (++sequence);
  const nets = data.map(row => cents(row.net_cents));
  const all = [0, ...data.flatMap(row => [row.income_cents, row.consumption_cents]), ...nets.filter(value => value !== null)];
  const min = Math.min(...all), max = Math.max(...all, 1), span = max - min || 1;
  const top = 24, plot = 96, y = value => top + (max - value) / span * plot, zero = y(0);
  const step = 330 / data.length, barWidth = Math.max(1.5, Math.min(22, (step - 6) / 2));
  const label = row => String(row.label ?? row.period ?? row.month ?? '');
  const anyPartial = data.some(row => row.complete === false);
  const partialText = ct('chart.cashflow.partial', {}, 'Partial');
  const bar = (x, value, color, pattern, cls, extra) => {
    const yy = Math.min(zero, y(value)), height = Math.max(1, Math.abs(y(value) - zero));
    return `<rect class="${cls}" x="${x.toFixed(2)}" y="${yy.toFixed(2)}" width="${barWidth.toFixed(2)}" height="${height.toFixed(2)}" rx="2" fill="${color}"${extra}/>` + (pattern ? `<rect x="${x.toFixed(2)}" y="${yy.toFixed(2)}" width="${barWidth.toFixed(2)}" height="${height.toFixed(2)}" rx="2" fill="url(#${id}-hatch)" pointer-events="none"/>` : '');
  };
  const columns = data.map((row, i) => {
    const centre = i * step + step / 2, partial = row.complete === false, isSelected = selected === i;
    const extra = isSelected ? ` stroke="${SELECTED_STROKE}" stroke-width="1.5"` : selected !== null ? ` opacity="${DIMMED_OPACITY}"` : '';
    const marks = bar(centre - barWidth - 1, row.income_cents, isSelected ? SELECTED_FILL : '#466d48', partial, 'chart-bar-mark cashflow-income', extra)
      + bar(centre + 1, row.consumption_cents, isSelected ? '#c98f55' : '#e1bd91', partial, 'chart-bar-mark cashflow-spending', extra)
      + (partial ? `<text x="${centre.toFixed(2)}" y="${(Math.min(y(row.income_cents), y(row.consumption_cents), zero) - 3).toFixed(2)}" text-anchor="middle" class="chart-note cashflow-partial-label" font-size="9">${esc(step >= 30 ? partialText : '*')}</text>` : '');
    const show = i === data.length - 1 || i % Math.ceil(data.length / 6) === 0;
    const tick = show ? `<text transform="translate(${centre.toFixed(2)},${top + plot + 16}) rotate(-35)" text-anchor="end" class="chart-note">${esc(label(row).slice(-7))}</text>` : '';
    if (!interactive) return marks + tick;
    const aria = ct('chart.cashflow.bar', {label:label(row), income:euro(row.income_cents), spending:euro(row.consumption_cents), net:nets[i] === null ? '—' : euro(nets[i])}, '{label}: money in {income}, money out {spending}, net {net}') + (partial ? ' (' + ct('chart.cashflow.partialPeriod', {}, 'partial period') + ')' : '');
    return hitTarget(i, aria, selected, {x:(i * step).toFixed(2), y:0, width:step.toFixed(2), height:top + plot + 20}, marks) + tick;
  }).join('');
  const points = data.map((row, i) => nets[i] === null ? null : [(i * step + step / 2).toFixed(2), y(nets[i]).toFixed(2)]);
  const segments = []; let current = [];
  points.forEach(point => { if (point) current.push(point.join(',')); else { if (current.length) segments.push(current); current = []; } });
  if (current.length) segments.push(current);
  const netLine = segments.filter(segment => segment.length > 1).map(segment => `<polyline class="cashflow-net" points="${segment.join(' ')}" fill="none" stroke="#163e30" stroke-width="2" pointer-events="none"/>`).join('')
    + points.map(point => point ? `<circle class="cashflow-net-dot" cx="${point[0]}" cy="${point[1]}" r="3" fill="#fff" stroke="#163e30" stroke-width="2" pointer-events="none"/>` : '').join('');
  const baseline = min < 0
    ? `<line class="cashflow-zero" x1="0" y1="${zero.toFixed(2)}" x2="330" y2="${zero.toFixed(2)}" stroke="#586e62" stroke-dasharray="3 3"/><text x="330" y="${(zero - 3).toFixed(2)}" text-anchor="end" class="chart-note" font-size="9">0</text>`
    : `<line x1="0" y1="${zero.toFixed(2)}" x2="330" y2="${zero.toFixed(2)}" stroke="#e2e6d9"/>`;
  const legendItems = [
    `<rect x="0" y="3" width="10" height="10" rx="2" fill="#466d48"/><text x="14" y="12" class="chart-note">${esc(ct('chart.cashflow.income', {}, 'Money in'))}</text>`,
    `<rect x="76" y="3" width="10" height="10" rx="2" fill="#e1bd91"/><text x="90" y="12" class="chart-note">${esc(ct('chart.cashflow.spending', {}, 'Money out'))}</text>`,
    `<line x1="158" y1="8" x2="174" y2="8" stroke="#163e30" stroke-width="2"/><circle cx="166" cy="8" r="3" fill="#fff" stroke="#163e30" stroke-width="2"/><text x="178" y="12" class="chart-note">${esc(ct('chart.cashflow.net', {}, 'Net'))}</text>`,
    anyPartial ? `<rect x="214" y="3" width="10" height="10" rx="2" fill="#c7c8bd"/><rect x="214" y="3" width="10" height="10" rx="2" fill="url(#${id}-hatch)"/><text x="228" y="12" class="chart-note">${esc(ct('chart.cashflow.partialLegend', {}, 'Partial period'))}</text>` : ''
  ];
  const defs = `<defs><pattern id="${id}-hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="5" height="5" fill="#ffffff" fill-opacity="0.35"/><line x1="0" y1="0" x2="0" y2="5" stroke="#ffffff" stroke-width="2.2"/></pattern></defs>`;
  const description = data.map((row, i) => {
    const parts = [`${label(row)}: ${ct('chart.cashflow.income', {}, 'Money in')} ${euro(row.income_cents)}`, `${ct('chart.cashflow.spending', {}, 'Money out')} ${euro(row.consumption_cents)}`];
    if (cents(row.savings_transfers_cents) !== null) parts.push(`${ct('chart.cashflow.savings', {}, 'Savings transfers')} ${euro(row.savings_transfers_cents)}`);
    if (nets[i] !== null) parts.push(`${ct('chart.cashflow.net', {}, 'Net')} ${euro(nets[i])}`);
    return parts.join(', ') + (row.complete === false ? ` (${ct('chart.cashflow.partialPeriod', {}, 'partial period')})` : '');
  }).join('. ') + '. ' + ct('chart.cashflow.netNote', {}, 'Net is money in minus money out minus savings transfers.');
  return svg(ct('chart.cashflow.title', {}, 'Money in vs money out'), description, defs + legendItems.join('') + baseline + columns + netLine, 180, interactive ? {columns:data.length, selected:selected !== null} : null);
}
