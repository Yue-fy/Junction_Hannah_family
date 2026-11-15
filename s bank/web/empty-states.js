// Designed empty states (V5 lane EM). The wrapper keeps the legacy `empty-state` class as a marker for older code/tests. One small component used everywhere a list, chart or card can be empty:
// a calm line-art illustration, a short title, one helpful line and, when it helps, one next step.
// Copy lives here (keys `v5.em.*`, EN/FI/SV) so call sites only pick a key and pass real data when it is cheap.

const LOCALES = ['en', 'fi', 'sv'];
const defaultEsc = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[x]));
const lang = locale => { const value = String(locale || 'en').slice(0, 2).toLowerCase(); return LOCALES.includes(value) ? value : 'en'; };

/** Every customer-facing string of the empty states, [EN, FI, SV]. */
export const EMPTY_COPY = Object.freeze({
  // Spending ring + category list, per filter.
  'v5.em.spending.irregular.title': ['No surprise costs', 'Ei yllätysmenoja', 'Inga oväntade utgifter'],
  'v5.em.spending.irregular.last': ['Nice and calm. Last one: {what}, {amount} on {date}.', 'Rauhallista. Edellinen: {what}, {amount} ({date}).', 'Lugnt och fint. Senaste: {what}, {amount} den {date}.'],
  'v5.em.spending.irregular.none': ['Nothing unexpected in the past year either. A small buffer still helps for when one comes.', 'Ei mitään odottamatonta koko viime vuonna. Pieni yllätyspuskuri auttaa silti, kun sellainen tulee.', 'Inget oväntat det senaste året heller. En liten buffert för oväntat hjälper ändå när något dyker upp.'],
  'v5.em.spending.irregular.generic': ['Nice and calm. Costs like the dentist or a broken washing machine show up here when they happen.', 'Rauhallista. Hammaslääkärin tai rikkoutuneen pesukoneen kaltaiset menot näkyvät täällä, kun niitä tulee.', 'Lugnt och fint. Kostnader som tandläkaren eller en trasig tvättmaskin syns här när de kommer.'],
  'v5.em.spending.regular.title': ['No must-pays recorded', 'Pakollisia menoja ei ole kirjattu', 'Inga måsten registrerade'],
  'v5.em.spending.regular.body': ['Rent and bills may have been paid from another account, or they fall in a different month.', 'Vuokra ja laskut on ehkä maksettu toiselta tililtä, tai ne osuvat toiseen kuukauteen.', 'Hyra och räkningar kan ha betalats från ett annat konto, eller så hamnar de i en annan månad.'],
  'v5.em.spending.leaks.title': ['No little leaks', 'Ei arjen pikkumenoja', 'Inga småutgifter'],
  'v5.em.spending.leaks.body': ['No small extras this month. Your everyday choices were all bigger buys or none at all.', 'Ei pieniä lisäostoksia tässä kuussa. Arjen valinnat olivat isompia ostoksia tai niitä ei ollut lainkaan.', 'Inga små extraköp den här månaden. Vardagsvalen var större köp eller inga alls.'],
  'v5.em.spending.all.title': ['No spending recorded', 'Kulutusta ei ole kirjattu', 'Inga utgifter registrerade'],
  'v5.em.spending.all.body': ['This month has no purchases or bills yet. Pick another month to explore.', 'Tälle kuukaudelle ei ole vielä ostoksia eikä laskuja. Valitse toinen kuukausi.', 'Den här månaden har inga köp eller räkningar än. Välj en annan månad.'],
  'v5.em.spending.group.title': ['Nothing in this group', 'Tässä ryhmässä ei ole menoja', 'Inget i den här gruppen'],
  'v5.em.spending.group.body': ['No purchases fall into this group this month.', 'Tämän kuun ostoksia ei osu tähän ryhmään.', 'Inga köp hamnar i den här gruppen den här månaden.'],
  'v5.em.action.allSpending': ['See all spending', 'Näytä kaikki menot', 'Visa alla utgifter'],
  // Transactions sheet.
  'v5.em.transactions.title': ['No transactions here', 'Ei tapahtumia', 'Inga transaktioner här'],
  'v5.em.transactions.body': ['Nothing matches this selection. Try another month or category.', 'Mikään ei osu tähän valintaan. Kokeile toista kuukautta tai luokkaa.', 'Inget matchar valet. Prova en annan månad eller kategori.'],
  // Charts (charts.js empty()).
  'v5.em.chart.noFlow': ['No money flow for this selection.', 'Tälle valinnalle ei ole rahavirtoja.', 'Inga penningflöden för det här valet.'],
  'v5.em.chart.body': ['It fills in as more months are recorded.', 'Kuva täydentyy, kun kuukausia kertyy lisää.', 'Bilden fylls i när fler månader registreras.'],
  // Goals and wishes.
  'v5.em.goals.title': ['Your goals will live here', 'Tavoitteesi näkyvät täällä', 'Dina mål visas här'],
  'v5.em.goals.body': ['Keep a wish below, even without an amount. When you know the amount and date, make a detailed plan.', 'Tallenna toive alla, vaikka ilman summaa. Kun summa ja päivä ovat tiedossa, tee tarkempi suunnitelma.', 'Spara en önskan nedan, även utan belopp. När du vet belopp och datum kan du göra en detaljerad plan.'],
  'v5.em.goals.action': ['Plan with an amount and a date', 'Suunnittele summalla ja päivällä', 'Planera med belopp och datum'],
  // Me / money profile.
  'v5.em.profile.title': ['Your coach doesn’t know you yet', 'Valmentajasi ei vielä tunne sinua', 'Din coach känner dig inte än'],
  // Plans.
  'v5.em.plans.error.title': ['Plans are taking a break', 'Suunnitelmat eivät juuri nyt lataudu', 'Planerna laddas inte just nu'],
  'v5.em.plans.error.body': ['Your saved plans are safe. Try again in a moment.', 'Tallennetut suunnitelmasi ovat tallessa. Yritä hetken päästä uudelleen.', 'Dina sparade planer är kvar. Försök igen om en stund.'],
  'v5.em.plans.taxNothing.title': ['Nothing to set aside', 'Ei mitään varattavaa', 'Inget att lägga undan'],
  'v5.em.plans.taxNothing.body': ['Your tax withholding looks enough for now. We’ll tell you if that changes.', 'Ennakonpidätyksesi näyttää nyt riittävältä. Kerromme, jos tilanne muuttuu.', 'Din förskottsinnehållning ser ut att räcka just nu. Vi säger till om det ändras.'],
  // Coach answer cards.
  'v5.em.card.unavailable.body': ['Try another month with the picker above, or one of the next questions.', 'Kokeile toista kuukautta yllä olevasta valinnasta tai jotakin seuraavista kysymyksistä.', 'Prova en annan månad med väljaren ovan, eller en av nästa frågor.'],
  // Year review.
  'v5.em.year.body': ['Your year in review appears once a few months are recorded. Meanwhile, your monthly view has the story so far.', 'Vuosikatsaus näkyy, kun kuukausia on kertynyt muutama. Sillä välin kuukausinäkymä kertoo tähänastisen tarinan.', 'Årsöversikten visas när några månader har registrerats. Under tiden visar månadsvyn hur det har gått hittills.'],
  'v5.em.year.action': ['Back to my month', 'Takaisin kuukauteen', 'Tillbaka till min månad'],
  // Supporting cards on Spending.
  'v5.em.investment.title': ['No savings transfers yet', 'Ei vielä säästösiirtoja', 'Inga sparöverföringar än'],
  'v5.em.investment.body': ['Nothing moved to savings or investments in this period. Even a small monthly amount adds up.', 'Tällä jaksolla ei siirretty rahaa säästöön tai sijoituksiin. Pienikin kuukausisumma kasvaa.', 'Inget flyttades till sparande eller investeringar under perioden. Även ett litet månadsbelopp växer.'],
  'v5.em.investment.action': ['How could I save more?', 'Miten voisin säästää enemmän?', 'Hur kan jag spara mer?'],
  'v5.em.history.title': ['A little more history needed', 'Tarvitaan vähän lisää historiaa', 'Lite mer historik behövs'],
  'v5.em.unavailable.title': ['Not available right now', 'Ei saatavilla juuri nyt', 'Inte tillgängligt just nu'],
  'v5.em.unavailable.body': ['Your data is safe. Try again in a moment.', 'Tietosi ovat tallessa. Yritä hetken päästä uudelleen.', 'Dina uppgifter är kvar. Försök igen om en stund.'],
  // Journal / notebook.
  'v5.em.journal.title': ['A quiet month', 'Hiljainen kuukausi', 'En lugn månad'],
  // Home.
  'v5.em.home.month.title': ['Nothing recorded yet', 'Ei vielä kirjauksia', 'Inget registrerat än'],
});

/** Localized empty-state copy. Unknown keys return the key (so missing copy is visible in tests, never blank). */
export function emptyText(locale, key, values = {}) {
  const row = EMPTY_COPY[key];
  const text = row ? row[LOCALES.indexOf(lang(locale))] || row[0] : key;
  return text.replace(/\{(\w+)\}/g, (_, name) => values[name] === undefined ? '{' + name + '}' : String(values[name]));
}

// Calm line art on a soft disc: 64x64, stroke = currentColor, accents use CSS custom properties.
const ART = Object.freeze({
  ring: '<circle cx="32" cy="32" r="15" fill="none" stroke-dasharray="4 5"/><circle cx="32" cy="32" r="6" fill="none"/>',
  chart: '<path d="M14 46h36M14 46V18"/><path d="M19 38c5 0 7-6 12-6s7 4 12 4 5-3 7-3" stroke-dasharray="3 4"/>',
  list: '<rect x="16" y="17" width="32" height="30" rx="5" fill="none"/><path d="M22 26h20M22 32h14M22 38h17"/>',
  coin: '<ellipse cx="32" cy="23" rx="12" ry="5" fill="none"/><path d="M20 23v9c0 3 5 5 12 5s12-2 12-5v-9M20 32v8c0 3 5 5 12 5s12-2 12-5v-8"/>',
  document: '<path d="M21 15h15l8 8v26H21z" fill="none"/><path d="M36 15v8h8M26 31h13M26 37h13M26 43h8"/>',
  goal: '<path d="M22 48V16"/><path d="M22 17h19l-4 7 4 7H22" fill="none"/>',
  person: '<circle cx="32" cy="25" r="7" fill="none"/><path d="M19 47a13 13 0 0 1 26 0"/>',
  calm: '<circle cx="32" cy="33" r="13" fill="none"/><path d="m26 33 4 4 8-9"/>',
});
const SPARKLES = '<path class="es-spark" d="M49 14v6M46 17h6M14 44v4M12 46h4M51 42l1 2 2 1-2 1-1 2-1-2-2-1 2-1z"/>';
export const EMPTY_KINDS = Object.freeze(Object.keys(ART));

/** The illustration alone (decorative; hidden from screen readers). */
export function emptyArt(kind, {celebrate = false} = {}) {
  const art = ART[kind] || ART.list;
  return `<svg class="es-art" viewBox="0 0 64 64" aria-hidden="true" focusable="false"><circle class="es-disc" cx="32" cy="32" r="28"/><g fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${art}${celebrate ? SPARKLES : ''}</g></svg>`;
}

const SAFE_ATTR = /^(data-[a-z0-9-]+|aria-[a-z]+)$/;
function actionHTML(action, esc, primary) {
  if (!action || !action.label) return '';
  const attrs = Object.entries(action.attrs || {}).filter(([name]) => SAFE_ATTR.test(name))
    .map(([name, value]) => ` ${name}="${esc(value === true ? '' : value)}"`).join('');
  return `<button type="button" class="es-action${primary ? '' : ' es-action--quiet'}"${attrs}>${esc(action.label)} <span aria-hidden="true">›</span></button>`;
}

/**
 * Render one designed empty state.
 * @param {object} options
 * @param {string} options.kind ring|chart|list|coin|document|goal|person|calm (illustration)
 * @param {string} options.title short, positive headline (plain text)
 * @param {string} [options.body] one helpful line (plain text)
 * @param {string} [options.eyebrow] small context line above the title, e.g. the month
 * @param {{label:string, attrs:object}} [options.action] next step; attrs are data-* / aria-* only (wired by existing handlers)
 * @param {{label:string, attrs:object}} [options.secondary] optional quieter second step
 * @param {Function} [options.esc] HTML escaper (defaults to a local one)
 * @param {boolean} [options.compact] smaller, side-by-side layout for cards and tiles
 * @param {boolean} [options.celebrate] adds sparkles: for good news like "no surprise costs"
 * @param {string} [options.id] optional data-empty identifier for tests and styling
 * @returns {string} HTML
 */
export function emptyStateHTML({kind = 'list', title = '', body = '', eyebrow = '', action = null, secondary = null, esc = defaultEsc, compact = false, celebrate = false, id = ''} = {}) {
  const art = ART[kind] ? kind : 'list';
  const actions = actionHTML(action, esc, true) + actionHTML(secondary, esc, false);
  return `<div class="es empty-state es--${art}${compact ? ' es--compact' : ''}${celebrate ? ' es--celebrate' : ''}" data-empty="${esc(id || art)}">`
    + emptyArt(art, {celebrate})
    + `<div class="es-copy">${eyebrow ? `<p class="es-eyebrow">${esc(eyebrow)}</p>` : ''}${title ? `<p class="es-title">${esc(title)}</p>` : ''}${body ? `<p class="es-body">${esc(body)}</p>` : ''}`
    + (actions ? `<div class="es-actions">${actions}</div>` : '') + `</div></div>`;
}

/**
 * Empty state for the spending ring when the chosen filter/month has no spending.
 * @param {object} o {group, locale, esc, monthLabel, last:{what, amount, date}|null|undefined}
 *   last === undefined → still looking (generic line), null → none in the past year.
 */
export function spendingEmptyHTML({group = 'all', locale = 'en', esc = defaultEsc, monthLabel = '', last} = {}) {
  const t = (key, values) => emptyText(locale, key, values);
  const allAction = {label: t('v5.em.action.allSpending'), attrs: {'data-spending-group': 'all'}};
  if (group === 'irregular') {
    const body = last ? t('v5.em.spending.irregular.last', last) : last === null ? t('v5.em.spending.irregular.none') : t('v5.em.spending.irregular.generic');
    return emptyStateHTML({kind: 'calm', celebrate: true, eyebrow: monthLabel, title: t('v5.em.spending.irregular.title'), body, action: allAction, esc, id: 'spending-irregular'});
  }
  if (group === 'regular' || group === 'leaks')
    return emptyStateHTML({kind: group === 'leaks' ? 'calm' : 'document', celebrate: group === 'leaks', eyebrow: monthLabel, title: t(`v5.em.spending.${group}.title`), body: t(`v5.em.spending.${group}.body`), action: allAction, esc, id: 'spending-' + group});
  if (group === 'all')
    return emptyStateHTML({kind: 'ring', eyebrow: monthLabel, title: t('v5.em.spending.all.title'), body: t('v5.em.spending.all.body'), esc, id: 'spending-all'});
  return emptyStateHTML({kind: 'ring', eyebrow: monthLabel, title: t('v5.em.spending.group.title'), body: t('v5.em.spending.group.body'), action: allAction, esc, id: 'spending-group'});
}
