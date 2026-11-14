export function createState() {
  return { customerId: 'CUST00001', selectedMonth: null, trendMonths: 12, observedStart: null, observedEnd: null, safeToSpend: null, investments: null, vat: null, view: 'home', overview: null, comparison: null, scenario: null, rows: [], goals: [], forecast: null, forecastAssumptions: {}, trends: null, exclusion: null, exclusionDetail: null, filter: null, transactionEvidence: null, pendingHandoff: null, busy: false, generation: 0, loadSequence: 0 };
}
export function selectPersona(state, customerId) {
  Object.assign(state, createState(), { customerId, trendMonths: state.trendMonths, generation: state.generation + 1 });
}
let formattingLocale = 'en-IE';
export function setFormattingLocale(locale){ formattingLocale=locale; }
export function money(cents) {
  if (cents === null || cents === undefined || !Number.isFinite(Number(cents))) return '—';
  return new Intl.NumberFormat(formattingLocale, { style: 'currency', currency: 'EUR' }).format(Number(cents) / 100);
}
export function escapeHTML(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}
export function dateLabel(value) {
  const parsed = new Date(String(value).slice(0, 10) + 'T12:00:00');
  return Number.isNaN(parsed.valueOf()) ? String(value ?? '') : parsed.toLocaleDateString(formattingLocale, { day: 'numeric', month: 'short', year: 'numeric' });
}
export function eurosToCents(value) {
  const text = String(value).trim();
  if (!/^\d+(?:\.\d{1,2})?$/.test(text)) throw new Error('Enter a positive euro amount with at most two decimal places.');
  const [euros, fraction = ''] = text.split('.');
  const cents = Number(euros) * 100 + Number(fraction.padEnd(2, '0'));
  if (!Number.isSafeInteger(cents)) throw new Error('That amount is too large.');
  return cents;
}
export function forecastRows(forecast) {
  if (!forecast) return [];
  if (Array.isArray(forecast.observed) || Array.isArray(forecast.projected)) {
    return [...(forecast.observed || []).slice(-7).map(row => ({...row,status:'observed'})), ...(forecast.projected || []).map(row => ({...row,status:'scenario'}))];
  }
  return (forecast.timeline || forecast.points || []).map(row => ({...row,status:row.observed===true?'observed':'scenario'}));
}

export function shiftMonth(month, offset) {
  if(!/^\d{4}-\d{2}$/.test(month))throw new Error('Invalid month');
  const [year, number]=month.split('-').map(Number);
  if(number<1||number>12)throw new Error('Invalid month');
  const date=new Date(Date.UTC(year,number-1+offset,1));
  return date.toISOString().slice(0,7);
}
export function monthEnd(month){
  const next=shiftMonth(month,1);
  return new Date(Date.parse(next+'-01T12:00:00Z')-86400000).toISOString().slice(0,10);
}
export function monthLabel(month, locale=formattingLocale){
  if(!month)return '';
  return new Intl.DateTimeFormat(locale,{month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(month+'-01T12:00:00Z'));
}
