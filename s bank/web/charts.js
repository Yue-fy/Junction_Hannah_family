const esc = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
let chartLocale='en-IE', chartTranslate=null;
export function configureCharts({locale,translate}){chartLocale=locale;chartTranslate=translate;}
const ct=(key,values,fallback)=>{const translated=chartTranslate?.(key,values);return translated&&translated!==key?translated:String(fallback).replace(/\{(\w+)\}/g,(_,key)=>values?.[key]??'{'+key+'}');};
const euro = value => new Intl.NumberFormat(chartLocale,{style:'currency',currency:'EUR'}).format(Number(value)/100);
let sequence = 0;
const svg = (title, description, body, height) => {
  const id = 'chart-' + (++sequence);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 330 ${height}" role="img" aria-labelledby="${id}-title ${id}-desc"><title id="${id}-title">${esc(title)}</title><desc id="${id}-desc">${esc(description)}</desc>${body}</svg>`;
};
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
export function barChart(series) {
  const rows=(series||[]).filter(row=>Number.isSafeInteger(row.value_cents));
  if(!rows.length)return '';
  const min=Math.min(0,...rows.map(row=>row.value_cents)),max=Math.max(0,...rows.map(row=>row.value_cents)),range=max-min||1,zero=-min/range*330;
  const body=rows.map((row,index)=>{
    const y=index*65,position=(row.value_cents-min)/range*330,label=String(row.label??'');
    return `<text x="0" y="${y+12}" class="chart-label"><title>${esc(label)}</title>${esc(label.length>44?label.slice(0,41)+'…':label)}</text><text x="330" y="${y+30}" text-anchor="end" class="chart-value">${esc(euro(row.value_cents))}</text><rect x="0" y="${y+39}" width="330" height="16" rx="4" fill="#e8ecdf"/><rect x="${Math.min(zero,position)}" y="${y+39}" width="${Math.abs(position-zero)}" height="16" rx="4" fill="#466d48"/>`;
  }).join('');
  return svg(ct('agent.chart',{},'Recorded amounts'),rows.map(row=>`${row.label}: ${euro(row.value_cents)}`).join('. '),body,rows.length*65);
}
export function trendChart(rows) {
  if (!rows?.length) return empty(ct('chart.noTrend',{},'No complete periods available for this trend.'));
  const values=rows.map(row=>Number(row.total_cents ?? row.consumption_cents ?? row.value_cents ?? 0));
  const max=Math.max(...values,1); const step=330/rows.length;
  const bars=rows.map((row,i)=>{const height=Math.max(1,values[i]/max*100),show=i===rows.length-1||i%Math.ceil(rows.length/6)===0;return `<rect x="${i*step+3}" y="${110-height}" width="${Math.max(2,step-6)}" height="${height}" rx="3" fill="${i===rows.length-1?'#466d48':'#b9cba3'}"/>${show?`<text transform="translate(${i*step+step/2},127) rotate(-35)" text-anchor="end" class="chart-note">${esc((row.period || row.month || row.label || '').slice(-5))}</text>`:''}`;}).join('');
  return svg(ct('chart.trend',{},'Complete-month spending trend'), rows.map((row,i)=>`${row.period||row.month||row.label}: ${euro(values[i])}`).join('. '),bars,151);
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
