export function createState() {
  return { customerId: 'CUST00001', view: 'home', overview: null, comparison: null, scenario: null, rows: [], goals: [], forecast: null, forecastAssumptions: {}, trends: null, exclusion: null, filter: null, transactionEvidence: null, pendingHandoff: null, busy: false, generation: 0, loadSequence: 0 };
}
export function selectPersona(state, customerId) {
  Object.assign(state, createState(), { customerId, generation: state.generation + 1 });
}
export function money(cents) {
  if (cents === null || cents === undefined || !Number.isFinite(Number(cents))) return '—';
  return new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR' }).format(Number(cents) / 100);
}
export function escapeHTML(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}
export function dateLabel(value) {
  const parsed = new Date(String(value).slice(0, 10) + 'T12:00:00');
  return Number.isNaN(parsed.valueOf()) ? String(value ?? '') : parsed.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
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
