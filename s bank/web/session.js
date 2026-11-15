/**
 * Keep the chosen customer and month across a page reload (V5 fix wave, lane ME).
 *
 * Stored in sessionStorage, so a reload or Back/Forward keeps the persona and month, while a new tab starts
 * from the default demo customer. Pure helpers: pass the storage object (or null when it is unavailable).
 */
export const SESSION_KEY = 'scoach.v5.session';
const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;
const CUSTOMER = /^CUST\d{5}$/;

/**
 * Read the saved customer and month.
 * @param {Storage|null} storage  sessionStorage (or a stub)
 * @param {string[]} [known]      allowed customer ids; others are ignored
 * @returns {{customerId:string, month:string|null}|null}
 */
export function readSession(storage, known = null) {
  let raw = null;
  try { raw = storage?.getItem(SESSION_KEY); } catch { return null; }
  if (!raw) return null;
  let value;
  try { value = JSON.parse(raw); } catch { return null; }
  const customerId = typeof value?.customerId === 'string' && CUSTOMER.test(value.customerId) ? value.customerId : null;
  if (!customerId || (Array.isArray(known) && !known.includes(customerId))) return null;
  return {customerId, month: typeof value.month === 'string' && MONTH.test(value.month) ? value.month : null};
}

/**
 * Save (or, with null, clear) the customer and month.
 * @param {Storage|null} storage
 * @param {{customerId:string, month:string|null}|null} value
 */
export function writeSession(storage, value) {
  try {
    if (!value) storage?.removeItem(SESSION_KEY);
    else storage?.setItem(SESSION_KEY, JSON.stringify({customerId: value.customerId, month: MONTH.test(value.month || '') ? value.month : null}));
  } catch { /* storage is optional (private mode, embedded previews) */ }
}
