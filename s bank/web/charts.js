const esc = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
let chartLocale='en-IE', chartTranslate=null;
let chartEmptyState=null;
/** emptyState (optional, V5 lane EM): ({kind,title,body,compact})=>HTML, normally empty-states.js emptyStateHTML. */
export function configureCharts({locale,translate,emptyState}){chartLocale=locale;chartTranslate=translate;if(emptyState!==undefined)chartEmptyState=emptyState;}
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
// V5 lane EM: a designed empty state (illustration + title + helpful line) when one is configured; plain text otherwise.
const empty = (message, kind='chart', body='') => chartEmptyState ? chartEmptyState({kind, title:message, body, compact:true, esc, id:'chart-'+kind}) : `<p class="empty-state">${esc(message)}</p>`;
const moreMonths = () => ct('v5.em.chart.body',{},'It fills in as more months are recorded.');
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
  if(!total)return empty(ct('chart.noSpending',{},'No recorded spending in this selection.'),'ring');
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
  if (!total) return empty(ct('v5.em.chart.noFlow',{},'No money flow for this selection.'),'coin');
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
  if (!before || !after) return empty(ct('chart.noComparison',{},'No complete comparison periods available.'),'chart',moreMonths());
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
const isoMonth=value=>{const match=/^(\d{4})-(\d{2})$/.exec(String(value??''));return match?new Date(Date.UTC(+match[1],+match[2]-1,15)):null;};
const monthFormat=(date,options)=>{try{return date.toLocaleDateString(chartLocale,{...options,timeZone:'UTC'});}catch{return date.toISOString().slice(0,7);}};
/** Full period name for screen readers and tooltips: "October 2025"; non-month labels are kept as given. */
function periodName(row){const raw=row.period||row.month||row.label||'',date=isoMonth(raw);return date?monthFormat(date,{month:'long',year:'numeric'}):String(raw);}
/** Short axis label: "Oct"; the first label and every January also show the year ("Jan 26"). */
function periodTick(row,first){const raw=row.period||row.month||row.label||'',date=isoMonth(raw);if(!date)return String(raw).slice(-5);return monthFormat(date,first||date.getUTCMonth()===0?{month:'short',year:'2-digit'}:{month:'short'});}
export function trendChart(rows, options={}) {
  if (!rows?.length) return empty(ct('chart.noTrend',{},'No complete periods available for this trend.'),'chart',moreMonths());
  const values=rows.map(row=>Number(row.total_cents ?? row.consumption_cents ?? row.value_cents ?? 0));
  const max=Math.max(...values,1); const step=330/rows.length;
  const interactive=Boolean(options?.interactive), selected=interactive?validIndex(options?.selectedIndex,rows.length):null;
  // Long month names (Finnish "marras 25") get fewer labels so they never touch.
  const longNames=rows.some((row,i)=>periodTick(row,i===0).length>6),every=Math.ceil(rows.length/(longNames?4:6)),last=rows.length-1;
  const bars=rows.map((row,i)=>{const height=Math.max(1,values[i]/max*100),show=(last-i)%every===0;
    // Horizontal month names ("Oct", "Jan 26"), counted back from the newest bar so it is always labelled.
    const anchor=rows.length>1&&i===0?'start':rows.length>1&&i===last?'end':'middle',tickX=anchor==='start'?i*step+2:anchor==='end'?(i+1)*step-2:i*step+step/2;
    const tick=show?`<text x="${tickX}" y="127" text-anchor="${anchor}" class="chart-note">${esc(periodTick(rows[i],i===last-every*Math.floor(last/every)))}</text>`:'';
    if(!interactive)return `<rect x="${i*step+3}" y="${110-height}" width="${Math.max(2,step-6)}" height="${height}" rx="3" fill="${i===rows.length-1?'#466d48':'#b9cba3'}"/>${tick}`;
    const isSelected=selected===i, fill=isSelected?SELECTED_FILL:(selected===null&&i===rows.length-1?'#466d48':'#b9cba3');
    const value=isSelected?`<text x="${Math.min(Math.max(i*step+step/2,24),306)}" y="${Math.max(9,106-height)}" text-anchor="middle" class="chart-value trend-selected-value">${esc(euro(values[i]))}</text>`:'';
    const marks=`<rect class="chart-bar-mark" x="${i*step+3}" y="${110-height}" width="${Math.max(2,step-6)}" height="${height}" rx="3" fill="${fill}"${isSelected?` stroke="${SELECTED_STROKE}" stroke-width="1.5"`:selected!==null?` opacity="${DIMMED_OPACITY}"`:''}/>${value}`;
    return hitTarget(i,`${periodName(row)}: ${euro(values[i])}`,selected,{x:i*step,y:0,width:step,height:131},marks)+tick;}).join('');
  return svg(ct('chart.trend',{},'Complete-month spending trend'), rows.map((row,i)=>`${periodName(row)}: ${euro(values[i])}`).join('. '),bars,151,interactive?{columns:rows.length,selected:selected!==null}:null);
}
/* V5 lane FC: the 30-day balance chart. Drawn at the real column width (options.width) so text stays
 * 11–12px on every screen; marks payday, rent and big bills (options.events) and the lowest day.
 * Legacy callers (coach answers) pass only rows and get the same chart in a 330-wide viewBox. */
const fcDay=value=>/^\d{4}-\d{2}-\d{2}$/.test(String(value||''))?Date.parse(value+'T00:00:00Z'):NaN;
const fcWhole=cents=>new Intl.NumberFormat(chartLocale,{style:'currency',currency:'EUR',maximumFractionDigits:0,minimumFractionDigits:0}).format(Math.round(Number(cents)/100));
// Axis labels share one formatter with the other charts: "€6k" in English, "6 000 €" in Finnish and Swedish.
const fcShort=cents=>axisEuro(cents);
// "Wed 14 Oct" rather than "Wed, 14 Oct" in English; FI/SV keep their own formats.
const fcDate=(iso,opts)=>Number.isFinite(fcDay(iso))?new Intl.DateTimeFormat(chartLocale,{...opts,timeZone:'UTC'}).format(new Date(fcDay(iso))).replace(/^([A-Za-z]{3}), /,'$1 '):String(iso??'');
const fcNiceStep=span=>{const raw=span/3,power=10**Math.floor(Math.log10(Math.max(raw,1)));return [1,2,2.5,5,10].map(x=>x*power).find(x=>x>=raw)||10*power;};
const FC_EVENT_LABEL={payday:['v5.fc.event.payday','Payday'],income:['v5.fc.event.income','Money in'],rent:['v5.fc.event.rent','Rent'],loan:['v5.fc.event.loan','Loan'],homeBills:['v5.fc.event.homeBills','Home bills'],bill:['v5.fc.event.bill','Bill']};
const fcEventName=kind=>ct(...(FC_EVENT_LABEL[kind]||FC_EVENT_LABEL.bill),{});
const fcSigned=cents=>(cents>0?'+':cents<0?'−':'')+fcWhole(Math.abs(cents));
export function runwayChart(rows, options={}) {
  if (!rows?.length) return empty(ct('chart.noRunway',{},'A cash-flow estimate is not available for this account yet.'),'chart',moreMonths());
  const points=rows.map(row=>{const band=row.historical_flexible_scenarios,values=band?[band.p25,band.p75].map(Number).filter(Number.isFinite):[];
    return {date:row.date??row.label,balance:Number(row.balance_cents),lo:values.length===2?Math.min(...values):null,hi:values.length===2?Math.max(...values):null,observed:!(row.status==='scenario'||row.kind==='scenario'||row.projected)};})
    .filter(point=>Number.isFinite(point.balance));
  if(!points.length)return empty(ct('chart.noRunway',{},'A cash-flow estimate is not available for this account yet.'));
  const interactive=Boolean(options.interactive), W=Math.max(260,Math.round(Number(options.width)||330)), wide=W>=520;
  const events=(options.events||[]).filter(event=>points.some(point=>point.date===event.date));
  const cushion=Number.isSafeInteger(options.cushionCents)&&options.cushionCents>0?options.cushionCents:null;
  const H=Math.round(Number(options.height)||(W>=820?300:wide?268:236)), padX=wide?10:7, top=24, plotBottom=H-(events.length?56:30), dataBottom=plotBottom-26;
  // x follows the calendar (observed rows only exist on days with transactions).
  const days=points.map(point=>fcDay(point.date)),byDate=days.every(Number.isFinite)&&days.at(-1)>days[0];
  const xAt=i=>padX+(byDate?(days[i]-days[0])/(days.at(-1)-days[0]):i/Math.max(points.length-1,1))*(W-2*padX);
  // y: the line, the usual range, and the cushion/zero when they are close enough to matter.
  const values=points.flatMap(point=>[point.balance,point.lo,point.hi]).filter(Number.isFinite);
  let low=Math.min(...values),high=Math.max(...values);const span0=Math.max(high-low,1);
  if(cushion!==null&&cushion<high&&cushion>=low-span0*.2)low=Math.min(low,cushion);
  if(low<0&&high>0){/* zero is inside the range already */}
  else if(low>0&&low<span0*.15)low=0;
  const pad=Math.max((high-low)*.06,500);high+=pad;low-=pad*.4;
  const yAt=value=>top+(high-value)/Math.max(high-low,1)*(dataBottom-top);
  const xy=points.map((point,i)=>[+xAt(i).toFixed(1),+yAt(point.balance).toFixed(1)]);
  const firstExpected=points.findIndex(point=>!point.observed),split=firstExpected<=0?0:firstExpected-1;
  const path=list=>list.map(([x,y],i)=>(i?'L':'M')+x+' '+y).join('');
  // Gridlines: 2–3 short labels (€3k, €4k), never the misleading max.
  // Pick the round step that gives 2–3 lines; skip any that would sit on the cushion line.
  const tickSet=step=>{const list=[];for(let k=Math.ceil(low/step);k*step<=high;k++)list.push(Math.round(k*step)||0);return list;};
  const scale=10**Math.floor(Math.log10(Math.max(high-low,100)));let ticks=[];
  for(const factor of [5,2.5,2,1,.5,.25,.2,.1]){const list=tickSet(scale*factor);if(list.length>=2&&list.length<=3){ticks=list;break;}}
  if(!ticks.length)ticks=tickSet(fcNiceStep((high-low)/100)*100).slice(0,3);
  if(cushion!==null)ticks=ticks.filter(v=>Math.abs(yAt(v)-yAt(cushion))>14);
  // When the balance may go below zero, zero always gets its own line.
  if(low<0&&high>0&&!ticks.includes(0))ticks=[...ticks.filter(v=>Math.abs(yAt(v)-yAt(0))>14),0].sort((a,b)=>a-b);
  const grid=ticks.map(v=>{const y=yAt(v).toFixed(1);return `<line class="fc-grid${v===0?' fc-grid--zero':''}" x1="0" x2="${W}" y1="${y}" y2="${y}"/>`;}).join('');
  // Axis text is painted after the line (with a white halo) so the line never hides it.
  const axisText=ticks.map(v=>`<text class="fc-axis" x="0" y="${(yAt(v)-4).toFixed(1)}">${esc(fcShort(v))}</text>`).join('');
  const showCushion=cushion!==null&&cushion>=low&&cushion<=high;
  const cushionLine=showCushion?`<line class="fc-cushion" x1="0" x2="${W}" y1="${yAt(cushion).toFixed(1)}" y2="${yAt(cushion).toFixed(1)}"/>`:'';
  const bandIdx=points.map((point,i)=>i).filter(i=>points[i].lo!==null);
  const band=bandIdx.length>1?`<path class="fc-band" d="${path(bandIdx.map(i=>[xAt(i).toFixed(1),yAt(points[i].hi).toFixed(1)]))}${bandIdx.slice().reverse().map(i=>'L'+xAt(i).toFixed(1)+' '+yAt(points[i].lo).toFixed(1)).join('')}Z"/>`:'';
  const solid=split>0?`<path class="fc-line fc-line--observed" d="${path(xy.slice(0,split+1))}"/>`:'';
  const dashed=`<path class="fc-line fc-line--expected" d="${path(xy.slice(split))}" stroke-dasharray="6 5"/>`;
  const todayText=ct('v5.fc.today',{},'Today'),todayW=todayText.length*6.4,todayX=split>0?Math.min(Math.max(xy[split][0],todayW/2+2),W-todayW/2-2):0;
  const today=split>0?`<line class="fc-today" x1="${xy[split][0]}" x2="${xy[split][0]}" y1="${top-4}" y2="${plotBottom}"/><text class="fc-today-label" x="${todayX.toFixed(1)}" y="${top-8}" text-anchor="middle">${esc(todayText)}</text>`:'';
  // Lowest expected day: dot + label under it.
  const expectedIdx=points.map((p,i)=>i).filter(i=>!points[i].observed),pool=expectedIdx.length?expectedIdx:points.map((p,i)=>i);
  const lowIndex=pool.reduce((a,b)=>points[b].balance<points[a].balance?b:a,pool[0]),lowPoint=xy[lowIndex],lowValue=points[lowIndex].balance;
  const tone=lowValue<0?'alert':cushion!==null&&lowValue<cushion?'watch':'ok';
  const lowText=ct('v5.fc.lowest',{amount:fcWhole(lowValue)},'Lowest {amount}'),lowWidth=lowText.length*6.6;
  // Centred under the dot unless an event ring (usually payday, the next day) would sit inside the text.
  const lowY=lowPoint[1]+20,clash=dir=>events.some(event=>{const i=points.findIndex(point=>point.date===event.date);if(i<0||i===lowIndex)return false;const dx=(xy[i][0]-lowPoint[0])*dir;return dx>0&&dx<lowWidth/2+8&&xy[i][1]>lowY-18&&xy[i][1]<lowY+8;});
  let lowAnchor=lowPoint[0]-lowWidth/2<2?'start':lowPoint[0]+lowWidth/2>W-2?'end':'middle';
  if(lowAnchor==='middle'&&clash(1)&&lowPoint[0]-lowWidth>2)lowAnchor='end';else if(lowAnchor==='middle'&&clash(-1)&&lowPoint[0]+lowWidth<W-2)lowAnchor='start';
  const lowX=lowAnchor==='start'?Math.max(2,lowPoint[0]-8):lowAnchor==='end'?Math.min(W-2,lowPoint[0]+8):lowPoint[0];
  const lowMark=`<circle class="fc-low fc-low--${tone}" cx="${lowPoint[0]}" cy="${lowPoint[1]}" r="5.5"/><text class="fc-low-label" x="${lowX}" y="${lowY.toFixed(1)}" text-anchor="${lowAnchor}">${esc(lowText)}</text>`;
  // End value as a direct label (skipped if the lowest day is the last day).
  // Sits above whatever the line or band does under the label's width, so it never sits on the line.
  const endText=fcWhole(points.at(-1).balance),endWidth=endText.length*7+6;
  const under=points.map((point,i)=>i).filter(i=>xy[i][0]>=W-endWidth-padX);
  const ceiling=Math.min(...under.map(i=>Math.min(xy[i][1],points[i].hi!==null?yAt(points[i].hi):Infinity)));
  const floor=Math.max(...under.map(i=>Math.max(xy[i][1],points[i].lo!==null?yAt(points[i].lo):-Infinity)));
  const endY=ceiling-8-top>=4?ceiling-8:floor+17;
  const endMark=lowIndex===points.length-1?'':`<text class="fc-end-label" x="${W}" y="${endY.toFixed(1)}" text-anchor="end">${esc(endText)}</text>`;
  // Events: a ring on the line + a two-line label in a lane under the plot; labels never overlap.
  const placed=[],lane=[],eventByDate=new Map(events.map(event=>[event.date,event]));
  const fits=(x0,x1)=>placed.every(([a,b])=>x1<a-6||x0>b+6);
  const placeLabel=(x,lines,cls)=>{const width=Math.max(...lines.map(line=>line.length))*6.4;
    let anchor='middle',x0=x-width/2;if(x0<0){anchor='start';x0=Math.max(0,x-4);}else if(x+width/2>W){anchor='end';x0=Math.min(W,x+4)-width;}
    if(!fits(x0,x0+width))return false;placed.push([x0,x0+width]);
    const tx=anchor==='middle'?x:anchor==='start'?x0:x0+width;
    lane.push(`<text class="${cls}" x="${tx.toFixed(1)}" y="${plotBottom+19}" text-anchor="${anchor}">${esc(lines[0])}</text>${lines[1]?`<text class="fc-lane-date" x="${tx.toFixed(1)}" y="${plotBottom+33}" text-anchor="${anchor}">${esc(lines[1])}</text>`:''}`);return true;};
  const order=['payday','income','rent','loan','homeBills','bill'];
  const eventMarks=events.map(event=>({event,i:points.findIndex(point=>point.date===event.date)})).sort((a,b)=>order.indexOf(a.event.kind)-order.indexOf(b.event.kind)).map(({event,i})=>{
    const [x,y]=xy[i],kindClass=event.kind==='payday'||event.kind==='income'?'in':'out';
    placeLabel(x,[fcEventName(event.kind),fcDate(event.date,{day:'numeric',month:'short'})],'fc-lane-name fc-lane-name--'+kindClass);
    return `<line class="fc-tick" x1="${x}" x2="${x}" y1="${plotBottom}" y2="${plotBottom+5}"/><circle class="fc-event fc-event--${kindClass}" cx="${x}" cy="${y}" r="4.5"/>`;}).join('');
  const baseline=`<line class="fc-base" x1="0" x2="${W}" y1="${plotBottom}" y2="${plotBottom}"/>`;
  // Start/end dates frame the lane when there is room.
  const startDate=fcDate(points[0].date,{day:'numeric',month:'short'}),endDate=fcDate(points.at(-1).date,{day:'numeric',month:'short'});
  const frame=events.length?'':`<text class="fc-lane-date" x="0" y="${plotBottom+18}">${esc(startDate)}</text><text class="fc-lane-date" x="${W}" y="${plotBottom+18}" text-anchor="end">${esc(endDate)}</text>`;
  const soFar=ct('v5.fc.soFar',{},'So far').toLowerCase(),expectedKind=ct('v5.fc.expected',{},'Expected').toLowerCase();
  const description=!byDate?ct('v5.fc.chartDescriptionPlain',{amount:fcWhole(points.at(-1).balance),lowest:fcWhole(lowValue)},'Ending around {amount}. Lowest {lowest}. The shaded area is your usual range.'):ct('v5.fc.chartDescription',{start:fcDate(points[0].date,{day:'numeric',month:'long'}),end:fcDate(points.at(-1).date,{day:'numeric',month:'long'}),amount:fcWhole(points.at(-1).balance),lowest:fcWhole(lowValue),date:fcDate(points[lowIndex].date,{day:'numeric',month:'long'})},'Balance from {start} to {end}, ending around {amount}. Lowest {lowest} on {date}. The shaded area is your usual range.');
  // Cushion label on the right unless the end value sits there; then on the left.
  const cushionText=showCushion?(()=>{const y=yAt(cushion)-4,right=!endMark||Math.abs(endY-y)>16;return `<text class="fc-axis fc-axis--cushion" x="${right?W:0}" y="${y.toFixed(1)}"${right?' text-anchor="end"':''}>${esc(ct('v5.fc.cushionLabel',{},'Safety cushion'))}</text>`;})():'';
  const body=`${grid}${cushionLine}${band}${today}${baseline}${solid}${dashed}${axisText}${cushionText}${eventMarks}${lowMark}${endMark}${lane.join('')}${frame}`;
  const title=ct('v5.fc.title',{},'Your balance over the next 30 days');
  if(!interactive)return svg(title,description,body,H);
  const data=points.map((point,i)=>{const event=eventByDate.get(point.date);return {x:xy[i][0],y:xy[i][1],d:fcDate(point.date,{weekday:'short',day:'numeric',month:'short'}),v:fcWhole(point.balance),
    k:point.observed?soFar:expectedKind,r:point.lo!==null&&!point.observed?ct('v5.fc.tipRange',{low:fcWhole(point.lo),high:fcWhole(point.hi)},'Usually {low}–{high}'):'',
    e:event?event.items.map(item=>fcEventName(item.kind)+' '+fcSigned(item.amount_cents)).join(' · '):'',low:i===lowIndex||undefined};});
  const id='chart-'+(++sequence),hint=ct('v5.fc.tapHint',{},'Tap or hover the line to see any day.');
  const cursor=`<g class="fc-cursor" visibility="hidden" pointer-events="none"><line x1="0" x2="0" y1="${top-6}" y2="${plotBottom}"/><circle cx="0" cy="0" r="6"/></g>`;
  const hit=`<rect class="fc-hit" x="0" y="0" width="${W}" height="${H}" fill="transparent"/>`;
  return `<div class="fc-chart"><svg xmlns="http://www.w3.org/2000/svg" class="fc-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" tabindex="0" role="img" aria-labelledby="${id}-title ${id}-desc" data-fc-width="${W}" data-fc-plot-bottom="${plotBottom}" data-fc-hint="${esc(hint)}" data-fc-points="${esc(JSON.stringify(data))}"><title id="${id}-title">${esc(title)}</title><desc id="${id}-desc">${esc(description+' '+ct('v5.fc.keyboard',{},'Use the arrow keys to read each day.'))}</desc>${body}${cursor}${hit}</svg><div class="fc-tip is-idle" role="status" aria-live="polite"><span class="fc-tip-hint">${esc(hint)}</span></div></div>`;
}
// V5 fix lane GL: the goal bar is HTML (a track, a fill and a row of labels) so its text keeps the body size at every
// card width; the old fixed-viewBox SVG scaled the labels from ~10px to ~22px. Goal amounts are whole euros.
const wholeEuro = value => new Intl.NumberFormat(chartLocale,{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(Math.round(Number(value)/100));
export function goalChart(current,target) {
  if (!Number.isFinite(target) || target<=0) return empty(ct('chart.noGoal',{},'Choose a target to see your progress.'),'goal');
  const ratio=Math.min(1,Math.max(0,current/target)),percent=Math.round(ratio*100);
  const label=ct('chart.goalDescription',{current:wholeEuro(current),target:wholeEuro(target),percent},'{current} saved toward {target}. {percent}% complete.');
  return `<div class="goal-progress" role="img" aria-label="${esc(label)}"><div class="goal-progress__track" aria-hidden="true"><span class="goal-progress__fill" style="width:${(ratio*100).toFixed(1)}%"></span></div>`
    +`<div class="goal-progress__labels" aria-hidden="true"><span>${esc(ct('chart.saved',{percent},'{percent}% saved'))}</span><span>${esc(ct('chart.target',{amount:wholeEuro(target)},'{amount} target'))}</span></div></div>`;
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
    // A bare signed number: the catalogue strings add the % sign in each language's own style ("+8%", "+8 %").
    const percent = previous > 0 ? new Intl.NumberFormat(chartLocale, {maximumFractionDigits:1, signDisplay:'exceptZero'}).format(Math.round(delta / previous * 1000) / 10) : '';
    const arrow = {up:'↑', down:'↓', same:'→'}[direction];
    const values = {amount: format(Math.abs(delta)), percent};
    const fallback = {up: percent ? 'Up {amount} ({percent}%) vs previous month' : 'Up {amount} vs previous month',
      down: percent ? 'Down {amount} ({percent}%) vs previous month' : 'Down {amount} vs previous month',
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
 * Axis and chart-label money: whole euros, short. EN "€800", "€1k", "€2.5k"; FI/SV "800 €", "1 000 €" (no "t." / "tn").
 * @param {number} cents
 * @returns {string}
 */
export function axisEuro(cents) {
  const euros = Math.round(Number(cents) / 100);
  if (!Number.isFinite(euros)) return '';
  if (String(chartLocale).toLowerCase().startsWith('en')) {
    const abs = Math.abs(euros), sign = euros < 0 ? '−' : '';
    if (abs < 1000) return sign + '€' + abs;
    const k = abs / 1000, text = k >= 10 ? String(Math.round(k)) : String(Math.round(k * 10) / 10);
    return sign + '€' + text + 'k';
  }
  try { return new Intl.NumberFormat(chartLocale, {style:'currency', currency:'EUR', maximumFractionDigits:0, minimumFractionDigits:0}).format(euros); }
  catch { return euros + ' €'; }
}

/**
 * Money in vs money out per period, drawn like the trend line chart: at the real column width (options.width,
 * viewBox = pixels) so text stays 11–12px, light y gridlines with short labels, paired bars (money in, spent),
 * and under them a small "left over" strip on its own scale (left_over_cents, or net_cents when missing) with a
 * zero line when any period is negative. Partial periods are hatched. The legend is HTML above the SVG so it wraps.
 * @param {Array<{label?:string,period?:string,income_cents:number,consumption_cents:number,savings_transfers_cents?:number,
 *   left_over_cents?:number,net_cents?:number,complete?:boolean}>} rows Periods in time order; rows without integer
 *   income and consumption cents are skipped (indices refer to the remaining rows).
 * @param {{interactive?:boolean,selectedIndex?:number|null,width?:number}} [options] interactive: one focusable
 *   `<g role="button" data-index>` per column (whole column, plot only); selectedIndex highlights a column.
 * @returns {string} `<div class="cf5">` (HTML legend + SVG) or an empty state.
 */
export function cashflowChart(rows, options={}) {
  const data = (Array.isArray(rows) ? rows : []).filter(row => cents(row?.income_cents) !== null && cents(row?.consumption_cents) !== null);
  if (!data.length) return empty(ct('chart.cashflow.empty', {}, 'No income or spending recorded for this range.'),'coin',moreMonths());
  const interactive = Boolean(options?.interactive), selected = interactive ? validIndex(options?.selectedIndex, data.length) : null;
  const id = 'cashflow-' + (++sequence), n = data.length, last = n - 1;
  const W = Math.max(260, Math.round(Number(options?.width) || 330)), narrow = W < 420;
  const r = value => Math.round(value * 10) / 10;
  const label = row => String(row.label ?? row.period ?? row.month ?? '');
  const lefts = data.map(row => cents(row.left_over_cents) ?? cents(row.net_cents));
  const nets = data.map(row => cents(row.net_cents));
  // Main scale: money in and spent, from zero, 3–4 light gridlines.
  const maxValue = Math.max(1, ...data.flatMap(row => [row.income_cents, row.consumption_cents]));
  const step = niceStep(maxValue, narrow ? 3 : 4), top = Math.max(step, Math.ceil(maxValue / step) * step);
  const ticks = []; for (let value = 0; value <= top + 1; value += step) ticks.push(value);
  const tickLabels = ticks.map(value => value === 0 ? '' : axisEuro(value));
  const gutter = Math.max(...tickLabels.map(text => text.length)) * 6.6 + 8;
  const left = gutter + 6, right = W - 2, span = right - left, colW = span / n;
  const plotTop = 10, plotBottom = plotTop + (narrow ? 150 : W < 640 ? 170 : 190);
  const y = value => plotBottom - Math.max(0, value) / top * (plotBottom - plotTop);
  const groupW = Math.min(colW * 0.74, 46), barW = Math.max(1.5, (groupW - 2) / 2);
  // Left-over strip: its own small scale, a caption line, and a zero line.
  const stripLabelY = plotBottom + 22, stripTop = stripLabelY + 8, stripH = 30, stripBottom = stripTop + stripH;
  const leftValues = lefts.filter(value => value !== null);
  const posMax = Math.max(0, ...leftValues), negMax = Math.max(0, ...leftValues.map(value => -value)), stripSpan = posMax + negMax || 1;
  const stripZero = stripTop + posMax / stripSpan * stripH;
  const sy = value => stripZero - value / stripSpan * stripH;
  const xLabelY = stripBottom + 17, H = xLabelY + 6;
  const anyPartial = data.some(row => row.complete === false), anyNegative = negMax > 0;
  const centre = i => left + colW * i + colW / 2;
  const hatch = (x, yy, w, h) => `<rect x="${r(x)}" y="${r(yy)}" width="${r(w)}" height="${r(h)}" rx="2" fill="url(#${id}-hatch)" pointer-events="none"/>`;
  const bar = (x, value, cls, partial) => {
    const yy = y(value), h = Math.max(1, plotBottom - yy);
    return `<rect class="${cls}" x="${r(x)}" y="${r(yy)}" width="${r(barW)}" height="${r(h)}" rx="2"/>` + (partial ? hatch(x, yy, barW, h) : '');
  };
  const grid = ticks.map((value, i) => `<line class="cf5-grid${value === 0 ? ' cf5-base' : ''}" x1="${r(left - 4)}" x2="${r(right)}" y1="${r(y(value))}" y2="${r(y(value))}"/>`
    + (tickLabels[i] ? `<text class="cf5-ylabel" x="${r(gutter)}" y="${r(y(value) + 4)}" text-anchor="end">${esc(tickLabels[i])}</text>` : '')).join('');
  // Month names: as many as fit (≥ 50px apart), counted back from the newest so it is always named.
  const ticksText = data.map((row, i) => periodTick(row, false));
  const longNames = ticksText.some(text => text.length > 6);
  const every = Math.max(1, Math.ceil(n / Math.max(1, Math.floor(span / (longNames ? 62 : 50)))));
  const firstShown = last % every;
  const xLabels = data.map((row, i) => {
    if ((last - i) % every) return '';
    const anchor = n > 1 && i === 0 && colW < 44 ? 'start' : n > 1 && i === last && colW < 44 ? 'end' : 'middle';
    const tx = anchor === 'start' ? left + colW * i : anchor === 'end' ? right : centre(i);
    return `<text class="cf5-xlabel${i === selected ? ' is-active' : ''}" x="${r(tx)}" y="${xLabelY}" text-anchor="${anchor}">${esc(periodTick(row, i === firstShown))}</text>`;
  }).join('');
  const leftText = ct('v3.cashflow.leftOver', {}, 'Left over after spending');
  const stripCaption = `<text class="cf5-strip-label" x="${r(left)}" y="${r(stripLabelY)}">${esc(leftText)}</text>`;
  const stripZeroLine = `<line class="${anyNegative ? 'cashflow-zero cf5-strip-zero' : 'cf5-strip-zero'}" x1="${r(left - 4)}" x2="${r(right)}" y1="${r(stripZero)}" y2="${r(stripZero)}"/>`
    + (anyNegative ? `<text class="cf5-ylabel" x="${r(gutter)}" y="${r(stripZero + 4)}" text-anchor="end">0</text>` : '');
  const partialText = ct('chart.cashflow.partial', {}, 'Partial');
  const columns = data.map((row, i) => {
    const cx = centre(i), partial = row.complete === false, isSelected = selected === i;
    const value = lefts[i];
    const stripBar = value === null ? '' : `<rect class="cashflow-net cf5-left${value < 0 ? ' is-negative' : ''}" x="${r(cx - barW)}" y="${r(Math.min(sy(value), stripZero))}" width="${r(barW * 2 + 2)}" height="${r(Math.max(1, Math.abs(sy(value) - stripZero)))}" rx="1.5"/>`;
    const partialMark = partial && colW >= 56 ? `<text class="cf5-partial" x="${r(cx)}" y="${r(Math.min(y(row.income_cents), y(row.consumption_cents)) - 4)}" text-anchor="middle">${esc(partialText)}</text>` : '';
    const marks = bar(cx - barW - 1, row.income_cents, 'chart-bar-mark cashflow-income', partial)
      + bar(cx + 1, row.consumption_cents, 'chart-bar-mark cashflow-spending', partial) + stripBar + partialMark
      + (isSelected && value !== null ? `<text class="cf5-left-value" x="${r(Math.min(Math.max(cx, left + 24), right - 24))}" y="${r(value < 0 ? stripZero - 4 : Math.min(sy(value), stripZero) - 4)}" text-anchor="middle">${esc(axisEuro(value))}</text>` : '');
    if (!interactive) return marks;
    const aria = ct('chart.cashflow.bar', {label:label(row), income:euro(row.income_cents), spending:euro(row.consumption_cents), net:value === null ? '—' : euro(value)}, '{label}: money in {income}, money out {spending}, net {net}') + (partial ? ' (' + ct('chart.cashflow.partialPeriod', {}, 'partial period') + ')' : '');
    const band = `<rect class="cf5-band" x="${r(left + colW * i + 1)}" y="${plotTop - 4}" width="${r(Math.max(2, colW - 2))}" height="${r(stripBottom + 4 - plotTop + 4)}" rx="6"/>`;
    return `<g class="chart-bar cf5-col${isSelected ? ' is-selected' : selected === null ? '' : ' is-dimmed'}" role="button" tabindex="0" data-index="${i}" aria-label="${esc(aria)}" aria-pressed="${isSelected}"><rect class="chart-hit" x="${r(left + colW * i)}" y="0" width="${r(colW)}" height="${r(stripBottom + 4)}" fill="transparent"/>${band}${marks}</g>`;
  }).join('');
  const defs = `<defs><pattern id="${id}-hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="5" height="5" fill="#ffffff" fill-opacity="0.35"/><line x1="0" y1="0" x2="0" y2="5" stroke="#ffffff" stroke-width="2.2"/></pattern></defs>`;
  const description = data.map((row, i) => {
    const parts = [`${label(row)}: ${ct('chart.cashflow.income', {}, 'Money in')} ${euro(row.income_cents)}`, `${ct('chart.cashflow.spending', {}, 'Money out')} ${euro(row.consumption_cents)}`];
    if (cents(row.savings_transfers_cents) !== null) parts.push(`${ct('chart.cashflow.savings', {}, 'Savings transfers')} ${euro(row.savings_transfers_cents)}`);
    if (lefts[i] !== null) parts.push(`${leftText} ${euro(lefts[i])}`);
    if (nets[i] !== null && nets[i] !== lefts[i]) parts.push(`${ct('chart.cashflow.net', {}, 'Net')} ${euro(nets[i])}`);
    return parts.join(', ') + (row.complete === false ? ` (${ct('chart.cashflow.partialPeriod', {}, 'partial period')})` : '');
  }).join('. ');
  const key = (cls, text) => `<li class="cf5-key ${cls}">${esc(text)}</li>`;
  const legend = `<ul class="cf5-legend" aria-hidden="true">${key('cf5-key--in', ct('chart.cashflow.income', {}, 'Money in'))}${key('cf5-key--out', ct('chart.cashflow.spending', {}, 'Money out'))}${key('cf5-key--left', ct('chart.cashflow.leftShort', {}, 'Left over'))}${anyPartial ? key('cf5-key--partial', ct('chart.cashflow.partialLegend', {}, 'Partial period')) : ''}</ul>`;
  const svgId = 'chart-' + (++sequence);
  const head = interactive ? `role="group"` : `role="img"`;
  const body = defs + grid + stripZeroLine + columns + stripCaption + xLabels;
  return `<div class="cf5${selected !== null ? ' has-selection' : ''}">${legend}<svg xmlns="http://www.w3.org/2000/svg" class="cf5-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" ${head} data-cf-width="${W}" aria-labelledby="${svgId}-title ${svgId}-desc"><title id="${svgId}-title">${esc(ct('chart.cashflow.title', {}, 'Money in vs money out'))}</title><desc id="${svgId}-desc">${esc(description)}</desc>${body}</svg></div>`;
}

// ---------- V5 lane TR: monthly spending as a line chart ----------
/** Short money label for axes and summaries: "€1.8K" in English, whole euros "1 800 €" in FI/SV (no "t." / "tn"). */
export function compactEuro(cents) {
  try {
    if (!/^en\b/i.test(chartLocale)) return new Intl.NumberFormat(chartLocale, {style:'currency', currency:'EUR', minimumFractionDigits:0, maximumFractionDigits:0}).format(Math.round(Number(cents) / 100));
    return new Intl.NumberFormat(chartLocale, {style:'currency', currency:'EUR', notation:'compact', minimumFractionDigits:0, maximumFractionDigits:1}).format(Number(cents) / 100); }
  catch { return euro(cents); }
}
/** A "nice" gridline step in cents (1, 2, 2.5 or 5 × 10^k euros) giving about `count` lines up to max. */
function niceStep(maxCents, count=3) {
  const raw = Math.max(maxCents, 100) / count, power = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 2.5, 5, 10].map(f => f * power).find(step => step >= raw) || 10 * power;
}
/**
 * Monthly spending as one clean line with a light area, 2–4 light gridlines with short labels and month names.
 * Drawn in pixel units (viewBox = width × height) so text keeps its real size at every screen width.
 * @param {Array<{month?:string,period?:string,label?:string,total_cents?:number,value_cents?:number}>} rows Months in time order.
 * @param {{width?:number,height?:number,activeIndex?:number|null,focusIndex?:number|null,describedBy?:string,labels?:string[]}} [options]
 *   activeIndex draws the crosshair and enlarged dot; focusIndex is the point in the tab order (roving tabindex,
 *   defaults to the newest month); labels optionally replace each point's accessible name.
 * @returns {string} SVG markup with one focusable `<g class="lc-pt" role="button" data-index>` per month, or an empty state.
 */
export function lineChart(rows, options={}) {
  const values = (rows || []).map(row => Number(row.total_cents ?? row.consumption_cents ?? row.value_cents));
  if (!values.length || values.some(value => !Number.isFinite(value))) return empty(ct('chart.noTrend', {}, 'No complete periods available for this trend.'));
  const n = values.length, last = n - 1;
  const width = Math.max(240, Math.round(Number(options.width) || 330)), height = Math.max(150, Math.round(Number(options.height) || 200));
  const active = validIndex(options.activeIndex, n), focus = validIndex(options.focusIndex, n) ?? active ?? last;
  const step = niceStep(Math.max(...values, 0)), top = Math.max(step, Math.ceil(Math.max(...values, 0) / step) * step);
  const ticks = []; for (let value = 0; value <= top + 1; value += step) ticks.push(value);
  const tickLabels = ticks.map(value => value === 0 ? '' : axisEuro(value));
  const gutter = Math.max(...tickLabels.map(label => label.length)) * 6.6 + 10;
  const padTop = 22, padBottom = 30, plotBottom = height - padBottom, plotTop = padTop;
  const left = gutter + 8, right = width - 14, span = right - left;
  const x = i => n === 1 ? left + span / 2 : left + i * span / last;
  const y = value => plotBottom - Math.max(0, value) / top * (plotBottom - plotTop);
  const r = value => Math.round(value * 10) / 10;
  const grid = ticks.map((value, i) => `<line class="lc-grid${value === 0 ? ' lc-base' : ''}" x1="${r(gutter)}" x2="${width}" y1="${r(y(value))}" y2="${r(y(value))}"/>`
    + (tickLabels[i] ? `<text class="lc-ylabel" x="${r(gutter - 6)}" y="${r(y(value) + 4)}" text-anchor="end">${esc(tickLabels[i])}</text>` : '')).join('');
  const points = values.map((value, i) => [r(x(i)), r(y(value))]);
  const line = points.map(([px, py], i) => (i ? 'L' : 'M') + px + ' ' + py).join(' ');
  const area = n > 1 ? `<path class="lc-area" d="${line} L${points[last][0]} ${plotBottom} L${points[0][0]} ${plotBottom} Z"/>` : '';
  // Month names: as many as fit (≥ 52px apart), counted back from the newest so it is always named.
  const longNames = rows.some((row, i) => periodTick(row, i === 0).length > 6);
  const every = Math.max(1, Math.ceil(n / Math.max(1, Math.floor(span / (longNames ? 64 : 56)))));
  const firstShown = last % every;
  const monthTicks = rows.map((row, i) => {
    if ((last - i) % every) return '';
    const anchor = n > 1 && i === 0 ? 'start' : n > 1 && i === last ? 'end' : 'middle';
    const tx = anchor === 'start' ? points[i][0] - 6 : anchor === 'end' ? points[i][0] + 6 : points[i][0];
    return `<text class="lc-xlabel${i === active ? ' is-active' : ''}" x="${r(tx)}" y="${height - 8}" text-anchor="${anchor}">${esc(periodTick(row, i === firstShown))}</text>`;
  }).join('');
  // Always present (hidden until a month is active) so the interactive layer can move it without redrawing.
  const crossX = points[active ?? last][0];
  const cross = `<line class="lc-cross" x1="${crossX}" x2="${crossX}" y1="${plotTop - 6}" y2="${plotBottom}"/>`;
  const describedBy = options.describedBy ? ` aria-describedby="${esc(options.describedBy)}"` : '';
  const half = n > 1 ? span / last / 2 : span / 2;
  const marks = values.map((value, i) => {
    const [px, py] = points[i], x0 = i === 0 ? 0 : px - half, x1 = i === last ? width : px + half;
    const label = options.labels?.[i] || `${periodName(rows[i])}: ${euro(value)}`;
    const cls = 'lc-pt' + (i === active ? ' is-active' : '') + (i === last ? ' is-latest' : '');
    return `<g class="${cls}" role="button" tabindex="${i === focus ? 0 : -1}" data-index="${i}" aria-label="${esc(label)}"${describedBy}>`
      + `<rect class="lc-hit" x="${r(x0)}" y="0" width="${r(x1 - x0)}" height="${plotBottom}"/>`
      + `<circle class="lc-dot" cx="${px}" cy="${py}" r="${i === active ? 6 : i === last ? 4.5 : 3.5}"/></g>`;
  }).join('');
  // One direct label: the newest month's amount (CSS hides it while a month is active so it never meets the tooltip).
  // Put it on the side away from the incoming segment: below the dot when the line falls into it, else above.
  const falling = n > 1 && values[last - 1] > values[last];
  const labelY = falling ? Math.min(plotBottom - 6, points[last][1] + 22) : Math.max(12, points[last][1] - 12);
  const latest = `<text class="lc-value" x="${r(n > 1 ? points[last][0] - 4 : points[last][0])}" y="${r(labelY)}" text-anchor="${n > 1 ? 'end' : 'middle'}">${esc(axisEuro(values[last]))}</text>`;
  const id = 'chart-' + (++sequence);
  const description = rows.map((row, i) => `${periodName(row)}: ${euro(values[i])}`).join('. ');
  return `<svg xmlns="http://www.w3.org/2000/svg" class="line-chart${active === null ? '' : ' has-active'}" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="group" aria-labelledby="${id}-title ${id}-desc"><title id="${id}-title">${esc(ct('v5.tr.chartTitle', {}, 'Monthly spending'))}</title><desc id="${id}-desc">${esc(description)}</desc>${grid}${area}<path class="lc-line" d="${line}"/>${cross}${monthTicks}${latest}${marks}</svg>`;
}
/** Money in whole euros, rounded to the nearest `nearest` euros, for plain sentences: "€2,410", "2 410 €". */
export function roundEuro(cents, nearest=10) {
  const euros = Math.round(Number(cents) / 100 / nearest) * nearest;
  try { return new Intl.NumberFormat(chartLocale, {style:'currency', currency:'EUR', maximumFractionDigits:0}).format(euros); }
  catch { return euro(euros * 100); }
}
