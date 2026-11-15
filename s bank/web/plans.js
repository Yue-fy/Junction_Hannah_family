// Optional planning modules (V4 lane P): a mortgage plan and a tax plan the customer can switch on.
// Both are money-profile entries (plan_mortgage, plan_tax); the server does every calculation and this
// module only renders them, opens the shared review form (openDraft) and saves after the customer confirms.
// Every number shown is an estimate from what the customer entered.
import { emptyStateHTML, emptyText } from './empty-states.js';

import { MORTGAGE_COPY, formatRate, renderMortgageCard, mortgageSpec, mortgageFormPreview, mortgageValue, loadMortgageExample,
  bindMortgageCharts } from './plans-mortgage.js';
// The mortgage UI lives in plans-mortgage.js (V5 lane MG); these names stay importable from here.
export { formatRate, annuityPayment, mortgageSpec, mortgageValue, renderMortgageCard } from './plans-mortgage.js';

import { createTaxPlan, describeTaxPlan, renderTaxCard } from './plans-tax.js';

// The tax plan UI lives in plans-tax.js (V5 lane TX); re-exported here for existing callers.
export { renderTaxCard, taxSpec, taxValue } from './plans-tax.js';

const LOCALES = ['en', 'fi', 'sv'];
const COPY = {
  'title': ['Plans (optional)', 'Suunnitelmat (valinnainen)', 'Planer (valfritt)'],
  'intro': ['Optional extras. Switch on what fits your life, and switch off any time.', 'Valinnaisia lisiä. Ota käyttöön se, mikä sopii elämääsi, ja poista milloin tahansa.', 'Valfria tillägg. Slå på det som passar ditt liv och stäng av när du vill.'],
  'on': ['On', 'Käytössä', 'På'],
  'turnOn': ['Turn on', 'Ota käyttöön', 'Slå på'],
  'turnOff': ['Turn off', 'Poista käytöstä', 'Stäng av'],
  'change': ['Change numbers', 'Muuta lukuja', 'Ändra siffror'],
  'estimate': ['Estimate', 'Arvio', 'Uppskattning'],
  'loading': ['Loading your plans…', 'Ladataan suunnitelmia…', 'Läser in dina planer…'],
  'unavailable': ['Plans are not available right now.', 'Suunnitelmat eivät ole juuri nyt saatavilla.', 'Planerna är inte tillgängliga just nu.'],
  'saved': ['Plan saved. It is now held back on each payday.', 'Suunnitelma tallennettu. Se varataan nyt jokaisena palkkapäivänä.', 'Planen är sparad. Den hålls nu undan varje lönedag.'],
  'removed': ['Plan switched off.', 'Suunnitelma poistettu käytöstä.', 'Planen är avstängd.'],
  'perMonth': ['a month', 'kuukaudessa', 'i månaden'],
  'heldBack': ['held back on each payday', 'varataan jokaisena palkkapäivänä', 'hålls undan varje lönedag'],
  'off.title': ['Switch off this plan?', 'Poistetaanko suunnitelma käytöstä?', 'Stänga av den här planen?'],
  'off.intro': ['The plan is removed from your money profile and no longer held back on payday. You can undo this.', 'Suunnitelma poistetaan rahaprofiilistasi, eikä sitä enää varata palkkapäivänä. Voit perua tämän.', 'Planen tas bort från din pengaprofil och hålls inte längre undan på lönedagen. Du kan ångra det.'],
};

const lang = locale => (LOCALES.includes(String(locale).slice(0, 2)) ? String(locale).slice(0, 2) : 'en');
export function planText(locale, key, values = {}) {
  const row = COPY[key] || MORTGAGE_COPY[key];
  const text = row ? row[LOCALES.indexOf(lang(locale))] || row[0] : key;
  return text.replace(/\{(\w+)\}/g, (_, name) => (values[name] === undefined ? '{' + name + '}' : String(values[name])));
}
export const PLAN_COPY_KEYS = Object.freeze(Object.keys(COPY));

const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

/** Plain-language one-liner for the Me page entry (money-profile.js describeEntry). */
export function describePlan(entry, locale, money) {
  const v = entry?.value || {};
  if (entry?.key === 'plan_mortgage') {
    const parts = [planText(locale, 'm.left') + ' ' + money(v.principal_cents || 0), formatRate((v.reference_rate_bp || 0) + (v.margin_bp || 0), locale)];
    if (Number.isInteger(v.monthly_payment_cents)) parts.push(money(v.monthly_payment_cents) + ' ' + planText(locale, 'perMonth'));
    return parts.join(' · ');
  }
  return describeTaxPlan(entry, locale, money);
}

// ---------------------------------------------------------------- rendering (pure)

function row(label, value) { return `<div class="plan-row"><dt>${escape(label)}</dt><dd>${escape(value)}</dd></div>`; }

export function renderPlansSection(state, h) {
  const t = key => planText(h.locale, key);
  const body = state.error ? emptyStateHTML({kind: 'document', compact: true, title: emptyText(h.locale, 'v5.em.plans.error.title'), body: emptyText(h.locale, 'v5.em.plans.error.body'), esc: escape, id: 'plans'})
    : state.loading ? `<p class="empty-state" role="status">${escape(t('loading'))}</p>`
      : renderMortgageCard(state.mortgage, state.ui || {}, h) + renderTaxCard(state.tax, h);
  // V5 fix lane GL: when one plan is open wide (an example or a saved mortgage plan), every plan card goes full width,
  // so the other card never sits alone in a half-empty row.
  const wide = !state.loading && !state.error && (Boolean(state.ui?.example) || Boolean(state.mortgage?.on) || Boolean(state.tax?.example?.open));
  return `<section class="plans-v4" aria-labelledby="plans-v4-title"><h2 id="plans-v4-title">${escape(t('title'))}</h2><p class="subtle">${escape(t('intro'))}</p><div class="plan-list${wide ? ' plan-list--wide' : ''}">${body}</div></section>`;
}

// ---------------------------------------------------------------- wiring

/**
 * @param {object} deps {$, request, captureContext, isCurrent, openDraft, closeDialogs, money, dateLabel, monthLabel,
 *   locale: () => string, referenceDate: () => string|null, notify, explainError, onChanged(context), openTax(), confirmDanger}
 * @returns {{render(context?), reset(), openSetup(plan, provenance?), editEntry(entry), handleClick(event): boolean}}
 */
export function initPlans(deps) {
  const {$, request, captureContext, isCurrent, openDraft, money, dateLabel, monthLabel, locale, referenceDate, notify} = deps;
  let view = {loading: true, mortgage: null, tax: null, ui: {extra: 0, rate: 0}, error: false};
  let customer = null;
  const helpers = () => ({locale: locale(), money, dateLabel, monthLabel});
  const asOf = () => (referenceDate() ? {as_of: referenceDate()} : {});
  const paint = () => { const root = $('plans-root'); if (root) { root.innerHTML = renderPlansSection(view, helpers()); bindMortgageCharts(root, helpers()); } };
  // Opening or closing an example changes the card height a lot: keep the card's top in view so nobody is left
  // looking at an unrelated part of the page (the close button sits at the bottom of a long example).
  const revealCard = plan => {
    const card = $('plans-root')?.querySelector?.(`[data-plan="${plan}"]`);
    const top = card?.getBoundingClientRect?.().top;
    if (Number.isFinite(top) && (top < 0 || top > (globalThis.innerHeight || 800) * 0.6)) card.scrollIntoView?.({block: 'start', behavior: 'smooth'});
  };
  const taxPlan = createTaxPlan({...deps, getData: () => view.tax, setData: data => { view.tax = data; paint(); }, saved: (context, message) => saved(context, message),
    reveal: () => revealCard('tax')});

  async function loadMortgage(context) {
    const params = {...asOf()};
    if (view.ui.extra) params.extra_cents = view.ui.extra;
    if (view.ui.rate) params.rate_delta_bp = view.ui.rate;
    return request(context, 'get', '/api/plans/mortgage/projection', params);
  }
  async function render(context = captureContext()) {
    if (!$('plans-root')) return;
    if (customer !== context.customerId) { view = {loading: true, mortgage: null, tax: null, ui: {extra: 0, rate: 0}, error: false}; customer = context.customerId; }
    if (!view.mortgage) paint();
    try {
      const [mortgageData, taxData] = await Promise.all([loadMortgage(context), taxPlan.load(context)]);
      if (!isCurrent(context)) return;
      view = {...view, loading: false, error: false, mortgage: mortgageData, tax: taxData};
    } catch {
      if (!isCurrent(context)) return;
      view = {...view, loading: false, error: true};
    }
    paint();
  }
  async function refreshMortgage(context = captureContext()) {
    try {
      const data = await loadMortgage(context);
      if (isCurrent(context)) { view.mortgage = data; paint(); }
    } catch (error) { deps.explainError?.(error); }
  }
  async function saved(context, message) {
    view.ui = {extra: 0, rate: 0};
    await deps.onChanged?.(context);
    await render(context);
    // The review dialog closes itself shortly after a save; tell the customer once it is gone.
    setTimeout(() => { try { notify?.(planText(locale(), message)); } catch { /* the notice is optional */ } }, 700);
  }
  function openSetup(plan, provenance = 'user') {
    const context = captureContext();
    const lang = locale();
    if (plan === 'mortgage') {
      const current = view.mortgage?.projection?.inputs && view.mortgage.on ? view.mortgage.projection.inputs : null;
      // Editing a saved plan starts from the saved numbers only; the detected housing payment is a prefill for a new plan.
      const spec = mortgageSpec(lang, current ? {value: current} : {prefill: view.mortgage?.prefill});
      openDraft(spec, {
        onChange: (values, card) => deps.updatePreview?.(card, mortgageFormPreview(values, lang, {money, monthLabel, referenceDate: referenceDate()})),
        onSave: async values => {
          const converted = mortgageValue(values);
          if (converted.error) throw new Error(planText(lang, converted.error));
          await request(context, 'post', '/api/plans/mortgage', {plan: converted.value, confirmed: true, provenance,
            ...(provenance === 'user' ? {} : {source: 'from_our_chat'})});
          await saved(context, 'saved');
        }});
      return;
    }
    taxPlan.openSetup(provenance);
  }
  function turnOff(plan) {
    const data = plan === 'mortgage' ? view.mortgage : view.tax;
    if (!data?.entry_id) return;
    const context = captureContext();
    deps.confirmDanger(planText(locale(), 'off.title'), planText(locale(), 'off.intro'), async () => {
      await request(context, 'post', '/api/profile/entries/delete', {entry_id: data.entry_id, confirmed: true});
      await saved(context, 'removed');
    });
  }
  // The read-only mortgage example (plans-mortgage.js): computed by /api/plans/mortgage/preview, never saved.
  async function openExample(context = captureContext()) {
    view.ui = {extra: 0, rate: 0, example: {loading: true}};
    paint();
    try {
      const data = await loadMortgageExample(request, context, asOf());
      if (isCurrent(context) && view.ui.example) { view.ui.example = {data}; paint(); }
    } catch {
      if (isCurrent(context) && view.ui.example) { view.ui.example = {error: true}; paint(); }
    }
  }
  const localWhatIfs = () => Array.isArray((view.ui.example?.data || view.mortgage)?.projection?.extra_options);
  function handleClick(event) {
    if (taxPlan.handleClick(event)) return true;
    const seeChart = event.target?.closest?.('[data-plan-see-chart]');
    if (seeChart?.hasAttribute?.('data-plan-see-chart')) {
      const chart = seeChart.closest('[data-plan]')?.querySelector('[data-mg-chart]');
      chart?.scrollIntoView?.({block: 'center', behavior: 'smooth'});
      chart?.focus?.({preventScroll: true});
      return true;
    }
    const target = event.target?.closest?.('[data-plan-on],[data-plan-edit],[data-plan-off],[data-plan-extra],[data-plan-rate],[data-plan-tax-card],[data-plan-example],[data-plan-example-close],[data-plan-own]');
    const d = target?.dataset;
    if (!d || !(d.planOn || d.planEdit || d.planOff || d.planExtra || d.planRate || d.planExample || d.planExampleClose || d.planOwn || target.hasAttribute?.('data-plan-tax-card'))) return false;
    if (d.planExample) { openExample(); revealCard('mortgage'); }
    else if (d.planExampleClose) { view.ui = {extra: 0, rate: 0}; paint(); revealCard('mortgage'); }
    else if (d.planOwn) { view.ui = {extra: 0, rate: 0}; paint(); openSetup(d.planOwn); }
    else if (d.planExtra && localWhatIfs()) { const value = Number(d.planExtra); view.ui.extra = view.ui.extra === value ? 0 : value; paint(); }
    else if (d.planOn) openSetup(d.planOn);
    else if (d.planEdit) openSetup(d.planEdit);
    else if (d.planOff) turnOff(d.planOff);
    else if (d.planExtra) { const value = Number(d.planExtra); view.ui.extra = view.ui.extra === value ? 0 : value; refreshMortgage(); }
    else if (d.planRate) { const value = Number(d.planRate); view.ui.rate = view.ui.rate === value ? 0 : value; refreshMortgage(); }
    else if (target.hasAttribute('data-plan-tax-card')) deps.openTax?.();
    return true;
  }
  return {
    render, openSetup, handleClick,
    reset() { view = {loading: true, mortgage: null, tax: null, ui: {extra: 0, rate: 0}, error: false}; customer = null; taxPlan.reset(); const root = $('plans-root'); if (root) root.innerHTML = ''; },
    repaint: paint,
  };
}

