const esc = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
let chartLocale='en-IE', chartTranslate=null;
export function configureCharts({locale,translate}){chartLocale=locale;chartTranslate=translate;}
const ct=(key,values,fallback)=>chartTranslate?chartTranslate(key,values):String(fallback).replace(/\{(\w+)\}/g,(_,key)=>values?.[key]??'{'+key+'}');
const euro = value => new Intl.NumberFormat(chartLocale,{style:'currency',currency:'EUR'}).format(Number(value)/100);
let sequence = 0;
const svg = (title, description, body, height) => {
  const id = 'chart-' + (++sequence);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 330 ${height}" role="img" aria-labelledby="${id}-title ${id}-desc"><title id="${id}-title">${esc(title)}</title><desc id="${id}-desc">${esc(description)}</desc>${body}</svg>`;
};
const empty = message => `<p class="empty-state">${esc(message)}</p>`;
export const palette = ['#466d48','#c2d7a3','#e1bd91','#92a88b','#c7c8bd','#eadac2'];
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
