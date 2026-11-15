/**
 * Review-before-saving draft card (COACH_V3_PLAN WP-E).
 *
 * A generic card used for goals, money-profile entries and tax details. The caller
 * supplies a spec; the card shows the values for review, lets the customer change them
 * inline, validates them and hands normalized values back through callbacks.
 *
 * Pure and dependency-free: no fetch, no storage, no global state. Every piece of text
 * from the spec is HTML-escaped. Amounts are integer cents.
 */

const LOCALES = ['en', 'fi', 'sv'];

const COPY = {
  'draft.title.default': ['Check before saving', 'Tarkista ennen tallennusta', 'Kontrollera innan du sparar'],
  'draft.title.goal': ['I can save this goal for you', 'Voin tallentaa tämän tavoitteen sinulle', 'Jag kan spara det här målet åt dig'],
  'draft.title.profile': ['Shall I note this down?', 'Kirjaanko tämän muistiin?', 'Ska jag anteckna det här?'],
  'draft.title.tax': ['Check your tax details', 'Tarkista verotietosi', 'Kontrollera dina skatteuppgifter'],
  'draft.save': ['Save', 'Tallenna', 'Spara'],
  'draft.delete': ['Delete', 'Poista', 'Ta bort'],
  'draft.change': ['Change', 'Muuta', 'Ändra'],
  'draft.notNow': ['Not now', 'Ei nyt', 'Inte nu'],
  'draft.reviewHint': ['Nothing is saved until you tap {save}.', 'Mitään ei tallenneta ennen kuin napautat {save}.', 'Inget sparas förrän du trycker på {save}.'],
  'draft.empty': ['Not set', 'Ei asetettu', 'Inte angivet'],
  'draft.optional': ['optional', 'valinnainen', 'valfritt'],
  'draft.danger.title': ['Are you sure?', 'Oletko varma?', 'Är du säker?'],
  'draft.danger.body': ['Please confirm once more before I go ahead.', 'Vahvista vielä kerran ennen kuin jatkan.', 'Bekräfta en gång till innan jag fortsätter.'],
  'draft.danger.yes': ['Yes, delete', 'Kyllä, poista', 'Ja, ta bort'],
  'draft.danger.no': ['Go back', 'Takaisin', 'Tillbaka'],
  'draft.saving': ['Saving…', 'Tallennetaan…', 'Sparar…'],
  'draft.saved': ['Saved', 'Tallennettu', 'Sparat'],
  'draft.saveFailed': ['Could not save. Please try again.', 'Tallennus epäonnistui. Yritä uudelleen.', 'Det gick inte att spara. Försök igen.'],
  'draft.fixErrors': ['Please check the highlighted fields.', 'Tarkista merkityt kentät.', 'Kontrollera de markerade fälten.'],
  'draft.error.required': ['Please fill this in.', 'Täytä tämä kenttä.', 'Fyll i det här fältet.'],
  'draft.error.amount': ['Enter an amount in euros, like 1,200.50.', 'Anna summa euroina, esimerkiksi 1 200,50.', 'Ange ett belopp i euro, till exempel 1 200,50.'],
  'draft.error.percent': ['Enter a percentage, like 21.5.', 'Anna prosentti, esimerkiksi 21,5.', 'Ange en procentsats, till exempel 21,5.'],
  'draft.error.number': ['Enter a number.', 'Anna luku.', 'Ange ett tal.'],
  'draft.error.date': ['Enter a date as YYYY-MM-DD.', 'Anna päivämäärä muodossa VVVV-KK-PP.', 'Ange ett datum som ÅÅÅÅ-MM-DD.'],
  'draft.error.month': ['Choose a month as YYYY-MM.', 'Valitse kuukausi muodossa VVVV-KK.', 'Välj en månad som ÅÅÅÅ-MM.'],
  'draft.error.select': ['Choose one of the options.', 'Valitse jokin vaihtoehdoista.', 'Välj ett av alternativen.'],
  'draft.error.min': ['This must be at least {min}.', 'Arvon on oltava vähintään {min}.', 'Värdet måste vara minst {min}.'],
  'draft.error.max': ['This can be at most {max}.', 'Arvo voi olla enintään {max}.', 'Värdet får vara högst {max}.'],
  'draft.error.minDate': ['Choose {min} or later.', 'Valitse {min} tai myöhemmin.', 'Välj {min} eller senare.'],
  'draft.error.maxDate': ['Choose {max} or earlier.', 'Valitse {max} tai aiemmin.', 'Välj {max} eller tidigare.'],
  'draft.error.tooLong': ['Please keep this under {max} characters.', 'Käytä enintään {max} merkkiä.', 'Använd högst {max} tecken.'],
};

const MONTHS = {
  en: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
  fi: ['tammikuu', 'helmikuu', 'maaliskuu', 'huhtikuu', 'toukokuu', 'kesäkuu', 'heinäkuu', 'elokuu', 'syyskuu', 'lokakuu', 'marraskuu', 'joulukuu'],
  sv: ['januari', 'februari', 'mars', 'april', 'maj', 'juni', 'juli', 'augusti', 'september', 'oktober', 'november', 'december'],
};

/** Frozen message maps: {en: {key: text}, fi: {...}, sv: {...}}; identical keys in every locale. */
export const DRAFT_CARD_MESSAGES = Object.freeze(Object.fromEntries(LOCALES.map((locale, index) => [
  locale, Object.freeze(Object.fromEntries(Object.entries(COPY).map(([key, values]) => [key, values[index]]))),
])));

/** Field types the card understands. Unknown types render as 'text'. */
export const FIELD_TYPES = Object.freeze(['text', 'amount', 'date', 'month', 'percent', 'select', 'number']);

const TEXT_MAX = 200;
const handles = new WeakMap();

function normLocale(locale) {
  const value = String(locale || 'en').toLowerCase().slice(0, 2);
  return LOCALES.includes(value) ? value : 'en';
}

/**
 * Localized message lookup.
 * @param {string} locale 'en' | 'fi' | 'sv' (anything else falls back to 'en').
 * @param {string} key a key of DRAFT_CARD_MESSAGES.en.
 * @param {object} [values] placeholder values, e.g. {min: '€10.00'}.
 * @returns {string} text with {placeholders} replaced; the key itself when unknown.
 */
export function message(locale, key, values = {}) {
  const lang = normLocale(locale);
  const text = DRAFT_CARD_MESSAGES[lang][key] || DRAFT_CARD_MESSAGES.en[key] || key;
  return text.replace(/\{(\w+)\}/g, (_, name) => (values[name] === undefined ? '{' + name + '}' : String(values[name])));
}

/**
 * Escape text for HTML element content and quoted attribute values.
 * @param {*} value any value; null/undefined become ''.
 * @returns {string}
 */
export function escapeHtml(value) {
  return String(value === null || value === undefined ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

const SPACES = /[\s    ']/g;

/**
 * Parse a euro amount typed by a customer into integer cents.
 * Accepts '1 200,50', '1,200.50', '1.200,50', '1200', '1200.5', '€1 200', '1 200 €', '12 EUR', '-5'.
 * A single ',' or '.' followed by exactly three digits is a thousands separator ('1,200' = 1200 €);
 * followed by one or two digits it is the decimal mark. More than two decimals is rejected.
 * @param {string|number} text the typed text (a finite number is read as euros).
 * @returns {number|null} integer cents, or null when the text is empty or not an amount.
 */
export function parseAmount(text) {
  if (typeof text === 'number') return Number.isFinite(text) ? Math.round(text * 100) : null;
  if (typeof text !== 'string') return null;
  let s = text.trim().replace(/^(€|eur\b)/i, '').replace(/(€|eur)$/i, '').trim();
  let sign = 1;
  if (/^[-−]/.test(s)) { sign = -1; s = s.slice(1).trim(); }
  s = s.replace(/^(€|eur\b)/i, '').trim();
  if (!s) return null;
  // Space-like thousands separators: every group after the first must have three digits.
  if (/[\s    ']/.test(s)) {
    const parts = s.split(/[\s    ']+/);
    for (let i = 1; i < parts.length; i += 1) {
      const head = parts[i].split(/[.,]/)[0];
      if (head.length !== 3 && !(i === parts.length - 1 && /^\d{3}[.,]\d{1,2}$/.test(parts[i]))) return null;
    }
    s = s.replace(SPACES, '');
  }
  if (!/^\d[\d.,]*$/.test(s) && !/^[.,]\d{1,2}$/.test(s)) return null;
  const lastComma = s.lastIndexOf(',');
  const lastDot = s.lastIndexOf('.');
  let intPart = s;
  let decPart = '';
  if (lastComma >= 0 && lastDot >= 0) {
    const decimalMark = lastComma > lastDot ? ',' : '.';
    const thousandsMark = decimalMark === ',' ? '.' : ',';
    const idx = s.lastIndexOf(decimalMark);
    intPart = s.slice(0, idx);
    decPart = s.slice(idx + 1);
    if (intPart.includes(decimalMark)) return null;
    if (!validGroups(intPart, thousandsMark)) return null;
    intPart = intPart.split(thousandsMark).join('');
  } else if (lastComma >= 0 || lastDot >= 0) {
    const mark = lastComma >= 0 ? ',' : '.';
    const pieces = s.split(mark);
    if (pieces.length > 2) {
      if (!validGroups(s, mark)) return null;
      intPart = pieces.join('');
    } else if (pieces[1].length === 3 && pieces[0].length >= 1 && pieces[0].length <= 3 && pieces[0] !== '0') {
      intPart = pieces.join('');
    } else {
      intPart = pieces[0];
      decPart = pieces[1];
    }
  }
  if (intPart === '') intPart = '0';
  if (!/^\d+$/.test(intPart) || !/^\d{0,2}$/.test(decPart)) return null;
  const cents = Number(intPart) * 100 + Number((decPart + '00').slice(0, 2));
  return Number.isSafeInteger(cents) ? sign * cents : null;
}

function validGroups(text, mark) {
  const groups = text.split(mark);
  if (!/^\d{1,3}$/.test(groups[0])) return false;
  return groups.slice(1).every(group => /^\d{3}$/.test(group));
}

/**
 * Parse a percentage typed by a customer. Accepts '21,5', '21.5', '21,5 %', '21.5%'.
 * @param {string|number} text the typed text.
 * @returns {number|null} the percentage as a number (21.5 means 21.5 %), rounded to 2 decimals; null if invalid.
 */
export function parsePercent(text) {
  if (typeof text === 'number') return Number.isFinite(text) ? Math.round(text * 100) / 100 : null;
  if (typeof text !== 'string') return null;
  const s = text.trim().replace(/\s*%$/, '').replace(SPACES, '').replace('−', '-');
  if (!/^-?(\d+([.,]\d+)?|[.,]\d+)$/.test(s)) return null;
  const value = Number(s.replace(',', '.'));
  return Number.isFinite(value) ? Math.round(value * 100) / 100 : null;
}

/**
 * Parse a plain number ('3', '2,5', '2.5').
 * @param {string|number} text
 * @returns {number|null}
 */
export function parseNumber(text) {
  if (typeof text === 'number') return Number.isFinite(text) ? text : null;
  if (typeof text !== 'string') return null;
  const s = text.trim().replace(SPACES, '').replace('−', '-');
  if (!/^-?(\d+([.,]\d+)?|[.,]\d+)$/.test(s)) return null;
  const value = Number(s.replace(',', '.'));
  return Number.isFinite(value) ? value : null;
}

function group(intText, sep) {
  return intText.replace(/\B(?=(\d{3})+(?!\d))/g, sep);
}

/**
 * Format integer cents for an editable input, in a form parseAmount reads back.
 * en: '1,200.50' / '1,200'; fi, sv: '1 200,50' / '1 200' (plain spaces).
 * @param {number} cents integer cents.
 * @param {string} locale 'en' | 'fi' | 'sv'.
 * @returns {string} '' when cents is not an integer.
 */
export function formatAmountInput(cents, locale) {
  if (!Number.isSafeInteger(cents)) return '';
  const lang = normLocale(locale);
  const negative = cents < 0;
  const abs = Math.abs(cents);
  const euros = String(Math.floor(abs / 100));
  const rest = abs % 100;
  const sep = lang === 'en' ? ',' : ' ';
  const dec = lang === 'en' ? '.' : ',';
  return (negative ? '-' : '') + group(euros, sep) + (rest ? dec + String(rest).padStart(2, '0') : '');
}

/**
 * Format integer cents for display: en '€1,200.50', fi/sv '1 200,50 €'. Whole euros omit decimals.
 * @param {number} cents
 * @param {string} locale
 * @returns {string}
 */
export function formatAmountDisplay(cents, locale) {
  if (!Number.isSafeInteger(cents)) return '';
  const lang = normLocale(locale);
  const text = formatAmountInput(Math.abs(cents), lang).replace(/ /g, ' ');
  const sign = cents < 0 ? '-' : '';
  return lang === 'en' ? sign + '€' + text : sign + text + ' €';
}

function formatPlainNumber(value, locale) {
  const lang = normLocale(locale);
  const text = String(value);
  return lang === 'en' ? text : text.replace('.', ',');
}

/**
 * Format a percentage for display: en '21.5%', fi/sv '21,5 %'.
 * @param {number} value percentage number.
 * @param {string} locale
 * @returns {string}
 */
export function formatPercent(value, locale) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '';
  const lang = normLocale(locale);
  return lang === 'en' ? formatPlainNumber(value, lang) + '%' : formatPlainNumber(value, lang) + ' %';
}

function realDate(text) {
  if (typeof text !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(text)) return false;
  const [y, m, d] = text.split('-').map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d;
}

function realMonth(text) {
  if (typeof text !== 'string' || !/^\d{4}-\d{2}$/.test(text)) return false;
  const m = Number(text.slice(5));
  return m >= 1 && m <= 12;
}

/**
 * Format an ISO date ('2027-06-14') or month ('2027-06') for display.
 * en: '14 June 2027' / 'June 2027'; fi: '14.6.2027' / 'kesäkuu 2027'; sv: '14 juni 2027' / 'juni 2027'.
 * @param {string} value
 * @param {string} locale
 * @returns {string} the input unchanged when it is not a valid date or month.
 */
export function formatDateDisplay(value, locale) {
  const lang = normLocale(locale);
  if (realMonth(value)) {
    const [y, m] = value.split('-').map(Number);
    return MONTHS[lang][m - 1] + ' ' + y;
  }
  if (realDate(value)) {
    const [y, m, d] = value.split('-').map(Number);
    if (lang === 'fi') return d + '.' + m + '.' + y;
    return d + ' ' + MONTHS[lang][m - 1] + ' ' + y;
  }
  return typeof value === 'string' ? value : '';
}

/**
 * Text shown in a date input, in the customer's own format: fi '31.3.2027', sv '2027-03-31', en '31/03/2027'.
 * @param {string} value ISO date
 * @param {string} locale
 * @returns {string} the input unchanged when it is not a valid ISO date.
 */
export function formatDateInput(value, locale) {
  if (!realDate(value)) return typeof value === 'string' ? value : '';
  const lang = normLocale(locale);
  const [y, m, d] = value.split('-');
  if (lang === 'fi') return Number(d) + '.' + Number(m) + '.' + y;
  if (lang === 'sv') return value;
  return d + '/' + m + '/' + y;
}

/** Placeholder for a date input: fi 'pp.kk.vvvv', sv 'åååå-mm-dd', en 'dd/mm/yyyy'. */
export function datePlaceholder(locale) {
  return {fi: 'pp.kk.vvvv', sv: 'åååå-mm-dd', en: 'dd/mm/yyyy'}[normLocale(locale)];
}

/**
 * Parse a date typed as d.m.yyyy, d/m/yyyy or yyyy-mm-dd (any locale) into an ISO date.
 * @param {string} text
 * @returns {string|null} ISO 'YYYY-MM-DD', or null when it is not a real date.
 */
export function parseDateInput(text) {
  const raw = String(text ?? '').trim();
  let y, m, d;
  let match = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(raw);
  if (match) [, y, m, d] = match;
  else if ((match = /^(\d{1,2})[./\s-](\d{1,2})[./\s-](\d{4})$/.exec(raw))) [, d, m, y] = match;
  else return null;
  const iso = y + '-' + String(m).padStart(2, '0') + '-' + String(d).padStart(2, '0');
  return realDate(iso) ? iso : null;
}

function optionList(field) {
  return (Array.isArray(field.options) ? field.options : []).map(option => (
    option && typeof option === 'object'
      ? {value: String(option.value), label: String(option.label === undefined ? option.value : option.label)}
      : {value: String(option), label: String(option)}
  ));
}

function fieldType(field) {
  return FIELD_TYPES.includes(field.type) ? field.type : 'text';
}

function boundText(field, bound, locale) {
  const type = fieldType(field);
  if (type === 'amount') return formatAmountDisplay(bound, locale);
  if (type === 'percent') return formatPercent(bound, locale);
  if (type === 'date' || type === 'month') return formatDateDisplay(bound, locale);
  return formatPlainNumber(bound, locale);
}

/**
 * Validate and normalize one field value.
 * @param {object} field a spec field.
 * @param {*} raw input text, or an already-typed value (cents integer for amounts).
 * @param {string} [locale]
 * @returns {{value: *, error: null|{code: string, message: string}}}
 *   value: amount -> integer cents, percent/number -> number, date/month -> ISO string,
 *   select -> option value string, text -> trimmed string; null when empty or invalid.
 */
export function validateField(field, raw, locale = 'en') {
  const type = fieldType(field);
  const fail = (code, values) => ({value: null, error: {code, message: message(locale, 'draft.error.' + code, values)}});
  const empty = raw === null || raw === undefined || (typeof raw === 'string' && raw.trim() === '');
  if (empty) return field.required ? fail('required') : {value: null, error: null};
  let value;
  if (type === 'amount') {
    value = Number.isSafeInteger(raw) ? raw : parseAmount(String(raw));
    if (value === null) return fail('amount');
  } else if (type === 'percent') {
    value = parsePercent(typeof raw === 'number' ? raw : String(raw));
    if (value === null) return fail('percent');
  } else if (type === 'number') {
    value = parseNumber(typeof raw === 'number' ? raw : String(raw));
    if (value === null) return fail('number');
  } else if (type === 'date' || type === 'month') {
    value = type === 'date' ? (parseDateInput(raw) || String(raw).trim()) : String(raw).trim();
    if (type === 'date' ? !realDate(value) : !realMonth(value)) return fail(type);
    if (field.min !== undefined && field.min !== null && value < String(field.min)) return fail('minDate', {min: boundText(field, String(field.min), locale)});
    if (field.max !== undefined && field.max !== null && value > String(field.max)) return fail('maxDate', {max: boundText(field, String(field.max), locale)});
    return {value, error: null};
  } else if (type === 'select') {
    value = String(raw);
    if (!optionList(field).some(option => option.value === value)) return fail('select');
    return {value, error: null};
  } else {
    value = String(raw).trim();
    const max = Number.isInteger(field.max) && field.max > 0 ? field.max : TEXT_MAX;
    if (value.length > max) return fail('tooLong', {max});
    return {value, error: null};
  }
  if (typeof field.min === 'number' && value < field.min) return fail('min', {min: boundText(field, field.min, locale)});
  if (typeof field.max === 'number' && value > field.max) return fail('max', {max: boundText(field, field.max, locale)});
  return {value, error: null};
}

/**
 * Validate a whole draft.
 * Bounds: amount min/max are integer cents; percent/number min/max are numbers;
 * date/month min/max are ISO strings; text max is a character limit (default 200).
 * @param {object} spec the card spec (uses spec.fields).
 * @param {object} [values] {fieldName: raw text or typed value}; a missing name falls back to field.value.
 * @param {string} [locale] for error messages.
 * @returns {{valid: boolean, values: object, errors: object}}
 *   values: {fieldName: normalized value or null}; errors: {fieldName: {code, message}} for invalid fields only.
 */
export function validateDraft(spec, values = {}, locale = 'en') {
  const out = {valid: true, values: {}, errors: {}};
  const fields = spec && Array.isArray(spec.fields) ? spec.fields : [];
  const given = values && typeof values === 'object' ? values : {};
  for (const field of fields) {
    if (!field || typeof field.name !== 'string') continue;
    const raw = Object.prototype.hasOwnProperty.call(given, field.name) ? given[field.name] : field.value;
    const result = validateField(field, raw, locale);
    out.values[field.name] = result.value;
    if (result.error) { out.valid = false; out.errors[field.name] = result.error; }
  }
  return out;
}

function slug(text) {
  return String(text || '').replace(/[^a-zA-Z0-9_-]/g, '-').slice(0, 60) || 'x';
}

function inputValue(field, locale) {
  const type = fieldType(field);
  const value = field.value;
  if (value === null || value === undefined) return '';
  if (type === 'amount' && Number.isSafeInteger(value)) return formatAmountInput(value, locale);
  if ((type === 'percent' || type === 'number') && typeof value === 'number') return formatPlainNumber(value, locale);
  if (type === 'date') return formatDateInput(String(value), locale);
  return String(value);
}

/**
 * Display text for a field value in review mode.
 * @param {object} field spec field.
 * @param {*} value raw or normalized value.
 * @param {string} locale
 * @returns {string} plain (unescaped) text; the localized 'Not set' when empty or invalid.
 */
export function displayValue(field, value, locale) {
  const result = validateField({...field, required: false, min: undefined, max: undefined}, value, locale);
  const v = result.value;
  if (v === null || v === undefined || v === '') return message(locale, 'draft.empty');
  const type = fieldType(field);
  if (type === 'amount') return formatAmountDisplay(v, locale);
  if (type === 'percent') return formatPercent(v, locale);
  if (type === 'number') return formatPlainNumber(v, locale);
  if (type === 'date' || type === 'month') return formatDateDisplay(v, locale);
  if (type === 'select') return (optionList(field).find(option => option.value === v) || {label: v}).label;
  return v;
}

function renderInput(field, id, describedBy, locale) {
  const type = fieldType(field);
  const common = 'id="' + id + '" name="' + escapeHtml(field.name) + '" data-draft-input="' + escapeHtml(field.name) + '"'
    + (describedBy ? ' aria-describedby="' + describedBy + '"' : '') + (field.required ? ' required aria-required="true"' : '');
  if (type === 'select') {
    const current = field.value === null || field.value === undefined ? '' : String(field.value);
    const options = optionList(field);
    const blank = options.some(option => option.value === current) ? '' : '<option value=""></option>';
    return '<select class="draft-field__input" ' + common + '>' + blank + options.map(option => (
      '<option value="' + escapeHtml(option.value) + '"' + (option.value === current ? ' selected' : '') + '>' + escapeHtml(option.label) + '</option>'
    )).join('') + '</select>';
  }
  const value = ' value="' + escapeHtml(inputValue(field, locale)) + '"';
  if (type === 'date' || type === 'month') {
    const bounds = (field.min ? ' min="' + escapeHtml(field.min) + '"' : '') + (field.max ? ' max="' + escapeHtml(field.max) + '"' : '');
    if (type === 'date') {
      return '<input class="draft-field__input" type="text" inputmode="numeric" autocomplete="off" spellcheck="false" placeholder="'
        + escapeHtml(datePlaceholder(locale)) + '" data-draft-date ' + common + value + '>';
    }
    const pattern = ' pattern="\\d{4}-\\d{2}" placeholder="YYYY-MM"';
    return '<input class="draft-field__input" type="' + type + '" ' + common + value + bounds + pattern + '>';
  }
  if (type === 'amount' || type === 'percent' || type === 'number') {
    const unit = type === 'amount' ? '€' : type === 'percent' ? '%' : '';
    const input = '<input class="draft-field__input" type="text" inputmode="decimal" autocomplete="off" spellcheck="false" ' + common + value + '>';
    return unit ? '<span class="draft-field__affix draft-field__affix--' + type + '">' + input + '<span class="draft-field__unit" aria-hidden="true">' + unit + '</span></span>' : input;
  }
  const max = Number.isInteger(field.max) && field.max > 0 ? field.max : TEXT_MAX;
  return '<input class="draft-field__input" type="text" autocomplete="off" maxlength="' + max + '" ' + common + value + '>';
}

/**
 * Render the draft card as an HTML string.
 * @param {object} spec {id, kind: 'goal'|'profile'|'tax'|string, title?, intro?, fields: [{name, label,
 *   type: 'text'|'amount'|'date'|'month'|'percent'|'select'|'number', value, options?: [{value,label}|string],
 *   required?, min?, max?, help?}], preview?: string, saveLabel?, confirmLabel?, mode?: 'review'|'edit', danger?: boolean}.
 *   Amount values and bounds are integer cents; date values 'YYYY-MM-DD'; month values 'YYYY-MM'.
 * @param {string} [locale] 'en' | 'fi' | 'sv'.
 * @returns {string} markup rooted at <section class="draft-card" data-draft-card="<id>">. Wire it with attachDraftCard.
 */
export function renderDraftCard(spec, locale = 'en') {
  const lang = normLocale(locale);
  const s = spec && typeof spec === 'object' ? spec : {};
  const base = 'dc-' + slug(s.id);
  const mode = s.mode === 'edit' ? 'edit' : 'review';
  const editing = mode === 'edit';
  const kind = typeof s.kind === 'string' ? s.kind : 'other';
  const titleKey = ['goal', 'profile', 'tax'].includes(kind) ? 'draft.title.' + kind : 'draft.title.default';
  const title = s.title ? String(s.title) : message(lang, titleKey);
  const saveLabel = s.saveLabel ? String(s.saveLabel) : message(lang, s.danger ? 'draft.delete' : 'draft.save');
  const fields = (Array.isArray(s.fields) ? s.fields : []).filter(field => field && typeof field.name === 'string');
  const rows = fields.map(field => {
    const fid = base + '-' + slug(field.name);
    const helpId = field.help ? fid + '-help' : '';
    const errId = fid + '-error';
    const describedBy = [helpId, errId].filter(Boolean).join(' ');
    // Some labels already say "(optional)"; never print it twice.
    const optionalWord = message(lang, 'draft.optional');
    const saysOptional = String(field.label || '').toLowerCase().includes('(' + optionalWord.toLowerCase() + ')');
    const optional = field.required || saysOptional ? '' : ' <span class="draft-field__optional">(' + escapeHtml(optionalWord) + ')</span>';
    return '<div class="draft-field draft-field--' + fieldType(field) + '" data-draft-field="' + escapeHtml(field.name) + '">'
      + '<label class="draft-field__label" for="' + fid + '">' + escapeHtml(field.label || field.name) + optional + '</label>'
      + '<p class="draft-field__value" data-draft-view="' + escapeHtml(field.name) + '"' + (editing ? ' hidden' : '') + '>' + escapeHtml(displayValue(field, field.value, lang)) + '</p>'
      + '<div class="draft-field__control" data-draft-edit' + (editing ? '' : ' hidden') + '>' + renderInput(field, fid, describedBy, lang) + '</div>'
      + (field.help ? '<p class="draft-field__help" id="' + helpId + '">' + escapeHtml(field.help) + '</p>' : '')
      + '<p class="draft-field__error" id="' + errId + '" data-draft-error="' + escapeHtml(field.name) + '" hidden></p>'
      + '</div>';
  }).join('');
  const preview = s.preview ? String(s.preview) : '';
  const confirm = s.danger
    ? '<div class="draft-card__confirm" data-draft-confirm hidden role="group" aria-labelledby="' + base + '-confirm-title">'
      + '<p class="draft-card__confirm-title" id="' + base + '-confirm-title"><strong>' + escapeHtml(message(lang, 'draft.danger.title')) + '</strong></p>'
      + '<p class="draft-card__confirm-body">' + escapeHtml(message(lang, 'draft.danger.body')) + '</p>'
      + '<div class="draft-card__actions">'
      + '<button type="button" class="draft-btn draft-btn--danger" data-draft-confirm-yes>' + escapeHtml(s.confirmLabel ? String(s.confirmLabel) : message(lang, 'draft.danger.yes')) + '</button>'
      + '<button type="button" class="draft-btn draft-btn--quiet" data-draft-confirm-no>' + escapeHtml(message(lang, 'draft.danger.no')) + '</button>'
      + '</div></div>'
    : '';
  return '<section class="draft-card draft-card--' + escapeHtml(slug(kind)) + (s.danger ? ' draft-card--danger' : '') + '" data-draft-card="' + escapeHtml(s.id === undefined ? '' : s.id) + '"'
    + ' data-draft-kind="' + escapeHtml(kind) + '" data-mode="' + mode + '"' + (s.danger ? ' data-danger="true"' : '') + ' aria-labelledby="' + base + '-title">'
    + '<form class="draft-card__form" data-draft-form novalidate>'
    + '<h3 class="draft-card__title" id="' + base + '-title">' + escapeHtml(title) + '</h3>'
    + (s.intro ? '<p class="draft-card__intro">' + escapeHtml(s.intro) + '</p>' : '')
    + '<div class="draft-card__fields">' + rows + '</div>'
    + '<p class="draft-card__preview" data-draft-preview aria-live="polite"' + (preview ? '' : ' hidden') + '>' + escapeHtml(preview) + '</p>'
    + '<p class="draft-card__hint">' + escapeHtml(message(lang, 'draft.reviewHint', {save: saveLabel})) + '</p>'
    + '<p class="draft-card__status" data-draft-status role="status" aria-live="polite" hidden></p>'
    + '<div class="draft-card__actions" data-draft-actions>'
    + '<button type="submit" class="draft-btn ' + (s.danger ? 'draft-btn--danger' : 'draft-btn--primary') + '" data-draft-save>' + escapeHtml(saveLabel) + '</button>'
    + '<button type="button" class="draft-btn draft-btn--secondary" data-draft-change' + (editing ? ' hidden' : '') + '>' + escapeHtml(message(lang, 'draft.change')) + '</button>'
    + '<button type="button" class="draft-btn draft-btn--quiet" data-draft-dismiss>' + escapeHtml(message(lang, 'draft.notNow')) + '</button>'
    + '</div>' + confirm + '</form></section>';
}

/**
 * Map an event target to a draft-card action name (pure routing helper).
 * @param {Element|null} target the clicked element (or a descendant of a button).
 * @returns {'change'|'dismiss'|'save'|'confirm'|'cancelConfirm'|null}
 */
export function draftAction(target) {
  if (!target || typeof target.closest !== 'function') return null;
  if (target.closest('[data-draft-confirm-yes]')) return 'confirm';
  if (target.closest('[data-draft-confirm-no]')) return 'cancelConfirm';
  if (target.closest('[data-draft-change]')) return 'change';
  if (target.closest('[data-draft-dismiss]')) return 'dismiss';
  if (target.closest('[data-draft-save]')) return 'save';
  return null;
}

function findCard(root) {
  if (!root) return null;
  if (typeof root.matches === 'function' && root.matches('[data-draft-card]')) return root;
  return typeof root.querySelector === 'function' ? root.querySelector('[data-draft-card]') : null;
}

/**
 * Replace the caller-computed preview line (e.g. after recomputing goal_plan on change).
 * @param {Element} root the card element or a container holding it.
 * @param {string} text plain text; empty hides the line. Set via textContent (no HTML).
 * @returns {boolean} true when a preview element was found.
 */
export function updateDraftPreview(root, text) {
  const card = findCard(root);
  const el = card && card.querySelector('[data-draft-preview]');
  if (!el) return false;
  const value = text === null || text === undefined ? '' : String(text);
  el.textContent = value;
  el.hidden = !value;
  return true;
}

/**
 * Show a save status on the card and toggle its busy state.
 * @param {Element} root the card or a container holding it.
 * @param {'idle'|'saving'|'saved'|'error'} status
 * @param {string} [text] override text; defaults to the localized message for the status.
 * @param {string} [locale]
 * @returns {boolean} true when the card was found.
 */
export function setDraftStatus(root, status, text, locale) {
  const card = findCard(root);
  if (!card) return false;
  const lang = normLocale(locale || card.getAttribute('data-locale') || 'en');
  const el = card.querySelector('[data-draft-status]');
  const defaults = {saving: 'draft.saving', saved: 'draft.saved', error: 'draft.saveFailed'};
  const value = text !== undefined && text !== null ? String(text) : defaults[status] ? message(lang, defaults[status]) : '';
  if (el) { el.textContent = value; el.hidden = !value; el.setAttribute('data-status', status); }
  const busy = status === 'saving';
  card.setAttribute('data-status', status);
  if (busy) card.setAttribute('aria-busy', 'true'); else card.removeAttribute('aria-busy');
  card.querySelectorAll('[data-draft-save],[data-draft-confirm-yes]').forEach(button => { button.disabled = busy || status === 'saved'; });
  return true;
}

/**
 * Read the raw text values currently in the card's inputs.
 * @param {Element} root the card or a container holding it.
 * @returns {object} {fieldName: string}
 */
export function readDraftValues(root) {
  const card = findCard(root);
  const out = {};
  if (!card) return out;
  card.querySelectorAll('[data-draft-input]').forEach(input => { out[input.getAttribute('data-draft-input')] = input.value; });
  return out;
}

/**
 * Wire a rendered draft card. Idempotent: attaching the same card again only replaces the
 * handlers and returns the same detach function.
 * @param {Element} root the card element or a container holding it.
 * @param {object} options
 * @param {object} options.spec the spec used to render (required for validation).
 * @param {string} [options.locale] 'en' | 'fi' | 'sv'.
 * @param {function(object, object):*} [options.onSave] called with (normalizedValues, rawValues) after
 *   validation passes (and after the second confirm tap when spec.danger). Amounts are integer cents.
 *   If it returns a promise, the card shows saving / saved / error automatically.
 * @param {function(object, object):void} [options.onChange] called (debounced) with (normalizedValues, result)
 *   where result is validateDraft's output, so the caller can recompute the preview.
 * @param {function():void} [options.onDismiss] called when 'Not now' is tapped.
 * @param {number} [options.debounceMs=250] onChange debounce.
 * @returns {function():void|null} detach (removes listeners and pending timers); null when no card was found.
 */
export function attachDraftCard(root, options = {}) {
  const card = findCard(root);
  if (!card) return null;
  const existing = handles.get(card);
  if (existing) { existing.options = options; return existing.detach; }
  const state = {options, timer: null};
  const opts = () => state.options || {};
  const lang = () => normLocale(opts().locale || 'en');
  if (opts().locale) card.setAttribute('data-locale', lang());
  const spec = () => opts().spec || {fields: []};
  const fieldEls = name => ({
    input: card.querySelector('[data-draft-input="' + name + '"]'),
    error: card.querySelector('[data-draft-error="' + name + '"]'),
    view: card.querySelector('[data-draft-view="' + name + '"]'),
  });
  const setMode = mode => {
    card.setAttribute('data-mode', mode);
    card.querySelectorAll('[data-draft-view]').forEach(el => { el.hidden = mode === 'edit'; });
    card.querySelectorAll('[data-draft-edit]').forEach(el => { el.hidden = mode !== 'edit'; });
    const change = card.querySelector('[data-draft-change]');
    if (change) change.hidden = mode === 'edit';
  };
  const showErrors = result => {
    for (const field of spec().fields || []) {
      const els = fieldEls(field.name);
      const err = result.errors[field.name];
      if (els.error) { els.error.textContent = err ? err.message : ''; els.error.hidden = !err; }
      if (els.input) { if (err) els.input.setAttribute('aria-invalid', 'true'); else els.input.removeAttribute('aria-invalid'); }
    }
  };
  const refreshViews = () => {
    const raw = readDraftValues(card);
    for (const field of spec().fields || []) {
      const els = fieldEls(field.name);
      if (els.view && Object.prototype.hasOwnProperty.call(raw, field.name)) els.view.textContent = displayValue(field, raw[field.name], lang());
    }
  };
  const confirmBox = () => card.querySelector('[data-draft-confirm]');
  const setConfirm = open => {
    const box = confirmBox();
    if (!box) return;
    box.hidden = !open;
    const actions = card.querySelector('[data-draft-actions]');
    if (actions) actions.hidden = open;
    const target = card.querySelector(open ? '[data-draft-confirm-yes]' : '[data-draft-save]');
    if (target && typeof target.focus === 'function') target.focus();
  };
  const doSave = () => {
    const raw = readDraftValues(card);
    const result = validateDraft(spec(), raw, lang());
    if (!result.valid) {
      showErrors(result);
      setMode('edit');
      setConfirm(false);
      const first = (spec().fields || []).find(field => result.errors[field.name]);
      const input = first && fieldEls(first.name).input;
      if (input && typeof input.focus === 'function') input.focus();
      return;
    }
    showErrors(result);
    const handler = opts().onSave;
    if (typeof handler !== 'function') return;
    setDraftStatus(card, 'saving', undefined, lang());
    let outcome;
    try { outcome = handler(result.values, raw); } catch (error) { setDraftStatus(card, 'error', undefined, lang()); throw error; }
    if (outcome && typeof outcome.then === 'function') {
      outcome.then(() => setDraftStatus(card, 'saved', undefined, lang()), () => setDraftStatus(card, 'error', undefined, lang()));
    }
  };
  const onClick = event => {
    const action = draftAction(event.target);
    if (!action) return;
    if (action === 'save') return; // handled by the form submit event
    if (event.preventDefault) event.preventDefault();
    if (action === 'change') {
      setMode('edit');
      const input = card.querySelector('[data-draft-input]');
      if (input && typeof input.focus === 'function') input.focus();
    } else if (action === 'dismiss') {
      const handler = opts().onDismiss;
      if (typeof handler === 'function') handler();
    } else if (action === 'confirm') {
      doSave();
    } else if (action === 'cancelConfirm') {
      setConfirm(false);
    }
  };
  const onSubmit = event => {
    if (event.preventDefault) event.preventDefault();
    if (card.getAttribute('aria-busy') === 'true') return;
    if (card.getAttribute('data-danger') === 'true') {
      const result = validateDraft(spec(), readDraftValues(card), lang());
      showErrors(result);
      if (!result.valid) { doSave(); return; }
      setConfirm(true);
      return;
    }
    doSave();
  };
  const onInput = event => {
    const target = event.target;
    if (!target || typeof target.getAttribute !== 'function') return;
    const name = target.getAttribute('data-draft-input');
    if (!name) return;
    const field = (spec().fields || []).find(item => item.name === name);
    if (field && target.getAttribute('aria-invalid') === 'true') {
      const check = validateField(field, target.value, lang());
      if (!check.error) {
        target.removeAttribute('aria-invalid');
        const els = fieldEls(name);
        if (els.error) { els.error.textContent = ''; els.error.hidden = true; }
      }
    }
    if (card.getAttribute('data-status') === 'saved' || card.getAttribute('data-status') === 'error') setDraftStatus(card, 'idle', undefined, lang());
    if (state.timer) clearTimeout(state.timer);
    const delay = Number.isFinite(opts().debounceMs) ? opts().debounceMs : 250;
    state.timer = setTimeout(() => {
      state.timer = null;
      refreshViews();
      const handler = opts().onChange;
      if (typeof handler !== 'function') return;
      const result = validateDraft(spec(), readDraftValues(card), lang());
      handler(result.values, result);
    }, delay);
  };
  card.addEventListener('click', onClick);
  card.addEventListener('submit', onSubmit);
  card.addEventListener('input', onInput);
  card.addEventListener('change', onInput);
  const detach = () => {
    if (state.timer) clearTimeout(state.timer);
    state.timer = null;
    card.removeEventListener('click', onClick);
    card.removeEventListener('submit', onSubmit);
    card.removeEventListener('input', onInput);
    card.removeEventListener('change', onInput);
    handles.delete(card);
  };
  handles.set(card, {get options() { return state.options; }, set options(value) { state.options = value; }, detach});
  return detach;
}
