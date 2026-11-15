// V3 page wiring (docs/COACH_V3_PLAN.md). app.js passes its helpers in; this module owns no global state
// beyond what it keeps for the active customer, and every async result is checked against the context
// that started it so a persona, month or language change can never show stale figures.
import { renderDraftCard, attachDraftCard, updateDraftPreview } from './draft-card.js';
import { renderTopicButton, renderTopicSheet, attachTopicMenu } from './topic-menu.js';
import { renderProfilePage, attachProfilePage, renderAddMenu, pm, draftSpecForEntry, draftValueToEntry, describeEntry,
  createOnboardingState, attachOnboarding } from './money-profile.js';
import { renderStory, attachStory, renderYearBanner } from './year-review.js';
import { trendChart, attachChartSelection, chartDetailPanel, cashflowChart } from './charts.js';
import { initPlans } from './plans.js';

const ONBOARDING_KEY = 'scoach.v3.onboarding.';
const BANNER_KEY = 'scoach.v3.yearBannerDismissed.';

export function initV3(deps) {
  const {state, $, esc, t, money, dateLabel, monthLabel, shiftMonth, monthEnd, request, captureContext, isCurrent,
    perform, navigate, changePeriod, askCoach, showTransactions, openDialog, closeDialogs, explainError, refreshGoals,
    locale, storage} = deps;
  const v3 = {};
  let profileData = null, profilePending = null, trendSelected = null, cashflowGranularity = 'month', cashflowData = null,
    cashflowSelected = null, onboardingState = null, onboardingHandle = null, topicHandle = null, yearOptions = null,
    taxOverview = null;

  // A translate function with a fallback, for components that pass one.
  const tr = (key, values = {}, fallback = key) => {
    const value = t(key, values);
    return value === key ? String(fallback).replace(/\{(\w+)\}/g, (_, name) => values?.[name] ?? '{' + name + '}') : value;
  };
  const helpers = () => ({money, dateLabel, monthLabel});
  const stored = key => { try { return storage?.getItem(key); } catch { return null; } };
  const store = (key, value) => { try { storage?.setItem(key, value); } catch { /* storage is optional */ } };
  const current = context => isCurrent(context) && context.locale === locale();

  // ---------- Generic review dialog for draft cards ----------
  let panelDetach = null;
  function openDraft(specs, {onSave, onChange} = {}) {
    panelDetach?.(); panelDetach = null;
    const blank = value => value === undefined || value === null || value === '' || (Array.isArray(value) && !value.length);
    // Nothing to review yet (a manual add): open straight into the editable form.
    const list = (Array.isArray(specs) ? specs : [specs]).map(spec => spec && !spec.mode && (spec.fields || []).length && (spec.fields || []).every(field => blank(field.value)) ? {...spec, mode: 'edit'} : spec);
    const container = $('v3-dialog-content');
    container.innerHTML = list.map(spec => renderDraftCard(spec, locale())).join('');
    setSheetTitle(list.length === 1 ? list[0]?.title : '');
    let remaining = list.length;
    list.forEach((spec, index) => {
      const card = container.querySelectorAll('[data-draft-card]')[index];
      if (!card) return;
      attachDraftCard(card, {spec, locale: locale(),
        onChange: onChange ? values => onChange(values, card, spec) : undefined,
        onSave: values => Promise.resolve(onSave(values, spec, index)).then(result => {
          remaining -= 1;
          if (remaining <= 0) setTimeout(() => { if ($('v3-dialog').open) closeDialogs(); }, 600);
          return result;
        }),
        onDismiss: () => { remaining -= 1; card.hidden = true; if (remaining <= 0) closeDialogs(); }});
    });
    openDialog('v3-dialog');
  }
  // One title, in the sheet header. A single card's own title is then hidden (styles.css: .v3-dialog.has-title).
  function setSheetTitle(title) {
    const heading = $('v3-dialog-title'), dialog = $('v3-dialog');
    if (heading) heading.textContent = title || '';
    if (dialog?.classList) dialog.classList.toggle?.('has-title', Boolean(title));
    if (title) dialog?.setAttribute?.('aria-labelledby', 'v3-dialog-title'); else dialog?.removeAttribute?.('aria-labelledby');
  }
  function openPanel(html, {onAction, title = ''} = {}) {
    panelDetach?.(); panelDetach = null;
    const node = $('v3-dialog-content');
    node.innerHTML = html;
    setSheetTitle(title);
    // The Me tab's "Add something" menu lives in this dialog, outside #profile-content, so it needs its own handler.
    if (onAction) panelDetach = attachProfilePage(node, {onAction: action => { panelDetach?.(); panelDetach = null; onAction(action); }});
    openDialog('v3-dialog');
  }

  // ---------- Optional plans (mortgage, tax) above the goals: web/plans.js ----------
  const plans = initPlans({$, request, captureContext, isCurrent: current, openDraft, closeDialogs, money, dateLabel, monthLabel,
    locale, notify: deps.notify, explainError, updatePreview: updateDraftPreview, openTax: () => { closeDialogs(); openTax(); },
    confirmDanger: (title, intro, action) => confirmDanger(title, intro, action),
    referenceDate: () => referenceDate(), planEntry: key => profileData?.profile?.by_key?.[key],
    onChanged: context => afterProfileChange(context)});
  const openPlan = (plan, provenance) => plans.render().then(() => plans.openSetup(plan, provenance));

  // ---------- Goals: draft cards for create, update, delete ----------
  const referenceDate = () => state.overview?.latest_balance_date || (state.selectedMonth ? monthEnd(state.selectedMonth) : null);
  function monthsUntil(target) {
    const from = referenceDate();
    if (!from || !target) return null;
    const [fy, fm] = from.split('-').map(Number), [ty, tm] = target.split('-').map(Number);
    const months = (ty - fy) * 12 + (tm - fm);
    return months >= 1 ? months : null;
  }
  function goalPreview(values) {
    const months = monthsUntil(values.target_date);
    const remaining = (values.target_cents || 0) - (values.current_saved_cents || 0);
    if (!months || !(remaining > 0)) return '';
    return t('v3.goal.preview', {amount: money(Math.ceil(remaining / months)), months, date: dateLabel(values.target_date)});
  }
  function goalSpec({id, title, name = '', target_cents = null, target_date = '', current_saved_cents = 0}) {
    return {id, kind: 'goal', title, intro: t('v3.goal.intro'), saveLabel: t('v3.goal.save'), fields: [
      {name: 'name', label: t('v3.goal.name'), type: 'text', value: name, required: true, max: 120},
      {name: 'target_cents', label: t('v3.goal.target'), type: 'amount', value: target_cents, required: true, min: 100},
      {name: 'target_date', label: t('v3.goal.date'), type: 'date', value: target_date, required: true},
      {name: 'current_saved_cents', label: t('v3.goal.saved'), type: 'amount', value: current_saved_cents || 0},
    ], preview: goalPreview({target_cents, target_date, current_saved_cents})};
  }
  const draftChange = (values, card) => updateDraftPreview(card, goalPreview(values));

  function createGoalDraft(params = {}, provenance = 'user') {
    const context = captureContext();
    openDraft(goalSpec({id: 'goal-new', title: t('v3.goal.newTitle'), ...params}), {onChange: draftChange, onSave: async values => {
      await request(context, 'post', '/api/goals', {name: values.name, target_cents: values.target_cents, target_date: values.target_date,
        current_saved_cents: values.current_saved_cents || 0, reserve_floor_cents: 50000, template: 'custom', confirmed: true, provenance});
      await refreshGoals(context);
    }});
  }
  function editGoalDraft(goal, fields = {}, provenance = 'user') {
    const context = captureContext();
    const spec = goalSpec({id: 'goal-' + goal.id, title: t('v3.goal.editTitle'), name: goal.name, target_cents: goal.target_cents,
      target_date: goal.target_date, current_saved_cents: goal.current_saved_cents ?? 0, ...fields});
    // Tapping Edit opens straight into the form; a coach proposal is reviewed first.
    if (provenance === 'user') spec.mode = 'edit';
    openDraft(spec, {onChange: draftChange, onSave: async values => {
      const changed = {};
      for (const key of ['name', 'target_cents', 'target_date', 'current_saved_cents'])
        if (values[key] !== null && values[key] !== undefined && values[key] !== goal[key]) changed[key] = values[key];
      if (Object.keys(changed).length) await request(context, 'post', '/api/goals/update', {goal_id: goal.id, fields: changed, confirmed: true, provenance});
      await refreshGoals(context);
    }});
  }
  function deleteGoalDraft(goal, provenance = 'user') {
    const context = captureContext();
    openDraft({id: 'goal-delete-' + goal.id, kind: 'goal', danger: true, title: t('v3.goal.deleteTitle', {name: goal.name}),
      intro: t('v3.goal.deleteIntro'), fields: [], saveLabel: t('v3.goal.delete')}, {onSave: async () => {
      await request(context, 'post', '/api/goals/delete', {goal_id: goal.id, confirmed: true, provenance});
      await refreshGoals(context);
    }});
  }
  const findGoal = params => (state.goals || []).find(goal => goal.id === params?.goal_id) ||
    (state.goals || []).find(goal => params?.goal_name && goal.name.toLowerCase() === String(params.goal_name).toLowerCase());
  v3.goalActionsHTML = goal => `<div class="goal-actions"><button type="button" class="text-button" data-goal-edit="${esc(goal.id)}">${esc(t('v3.goal.edit'))}</button><button type="button" class="text-button goal-delete" data-goal-delete="${esc(goal.id)}">${esc(t('v3.goal.delete'))}</button></div>`;

  // ---------- Money profile ----------
  function toUiValue(key, value) {
    if (key !== 'tax' || !value) return value;
    const ui = {...value};
    if (typeof ui.assessment_end_month === 'string') ui.assessment_end_month = Number(ui.assessment_end_month.slice(5, 7));
    return ui;
  }
  function toApiValue(key, value) {
    if (key !== 'tax' || !value) return value;
    const api = {...value};
    if (!api.tax_year) api.tax_year = Number((referenceDate() || '2026').slice(0, 4));
    if (Number.isInteger(api.assessment_end_month)) api.assessment_end_month = `${api.tax_year + 1}-${String(api.assessment_end_month).padStart(2, '0')}`;
    return api;
  }
  async function loadProfile(context = captureContext(), force = false) {
    const lang = locale();
    if (profileData && profileData.customerId === context.customerId && profileData.locale === lang && !force) return profileData;
    if (profilePending && profilePending.customerId === context.customerId && profilePending.locale === lang && !force) return profilePending.promise;
    const promise = request(context, 'get', '/api/profile', {as_of: referenceDate() || undefined, locale: lang}).then(data => {
      if (!isCurrent(context)) return null;
      profileData = {customerId: context.customerId, locale: lang, profile: data.profile, suggestions: data.suggestions || []};
      return profileData;
    }).finally(() => { if (profilePending?.promise === promise) profilePending = null; });
    profilePending = {customerId: context.customerId, locale: lang, promise};
    return promise;
  }
  function entryById(id) { return profileData?.profile?.entries?.find(entry => entry.id === id); }
  function profileEntryDraft(entryOrKey, {source = 'you_told_me', provenance = 'user', note} = {}) {
    const context = captureContext();
    const entry = typeof entryOrKey === 'string' ? null : entryOrKey;
    const key = entry ? entry.key : entryOrKey;
    const spec = draftSpecForEntry(entry ? {...entry, value: toUiValue(key, entry.value)} : key, locale());
    if (provenance === 'user') spec.mode = 'edit';
    openDraft(spec, {onSave: async values => {
      const converted = draftValueToEntry(key, values, entry ? toUiValue(key, entry.value) : undefined);
      if (converted.errors && Object.keys(converted.errors).length) throw new Error(t('error.validation'));
      const value = toApiValue(key, converted.value);
      if (entry?.id) await request(context, 'post', '/api/profile/entries/update', {entry_id: entry.id, value, confirmed: true, provenance});
      else await request(context, 'post', '/api/profile/entries', {key, value, source, ...(note ? {note} : {}), confirmed: true, provenance});
      await afterProfileChange(context);
    }});
  }
  async function afterProfileChange(context) {
    await loadProfile(context, true);
    if (state.view === 'profile') renderProfile(context);
    deps.refreshSupport?.(context);
  }
  function confirmDanger(title, intro, action) {
    openDraft({id: 'danger', kind: 'profile', danger: true, title, intro, fields: [], saveLabel: t('v3.delete')}, {onSave: action});
  }
  async function renderProfile(context = captureContext()) {
    const node = $('profile-content');
    node.setAttribute('aria-busy', 'true');
    let data;
    try { data = await loadProfile(context); } catch (error) {
      if (current(context)) { node.innerHTML = `<p class="empty-state">${esc(t('support.unavailable'))}</p>`; node.setAttribute('aria-busy', 'false'); }
      return;
    }
    if (!data || !current(context)) return;
    const local = deps.localProfile?.();
    const migrate = data.profile?.empty && local && (local.notes?.length || local.onboarding_complete)
      ? `<section class="white-card"><p>${esc(t('v3.profile.migrate'))}</p><button type="button" class="secondary-button" data-v3-migrate>${esc(t('v3.profile.migrateAction'))}</button></section>` : '';
    node.innerHTML = migrate + renderProfilePage(data.profile, data.suggestions, locale(), helpers());
    node.setAttribute('aria-busy', 'false');
    attachProfilePage(node, {onAction: action => handleProfileAction(action, context)});
  }
  function handleProfileAction(action, context) {
    if (!isCurrent(context)) return;
    const entry = action.id ? entryById(action.id) : null;
    const post = (path, body) => perform(null, async next => { await request(next, 'post', path, {...body, confirmed: true}); await afterProfileChange(next); });
    switch (action.type) {
      case 'edit': if (entry?.key?.startsWith('plan_')) loadProfile(context).then(() => openPlan(entry.key.slice(5))); else if (entry) profileEntryDraft(entry); break;
      case 'delete': if (entry) confirmDanger(t('v3.profile.deleteTitle'), describeEntry({...entry, value: toUiValue(entry.key, entry.value)}, locale(), helpers()),
        async () => { await request(context, 'post', '/api/profile/entries/delete', {entry_id: entry.id, confirmed: true}); await afterProfileChange(context); }); break;
      case 'mode_off': if (action.id) post('/api/profile/entries/update', {entry_id: action.id, active: false}); break;
      case 'suggestion_keep': post('/api/profile/suggestions/confirm', {suggestion_id: action.id, locale: locale()}); break;
      case 'suggestion_dismiss': post('/api/profile/suggestions/dismiss', {suggestion_id: action.id}); break;
      case 'add': openPanel(renderAddMenu(locale()), {title: pm(locale(), 'actions.addTitle'), onAction: next => handleProfileAction(next, context)}); break;
      case 'add_key': profileEntryDraft(action.key); break;
      case 'open_tax': openTax(context); break;
      case 'open_review': if (entry?.value?.year) openYearReview(entry.value.year); break;
      case 'onboarding': store(ONBOARDING_KEY + state.customerId, ''); navigate('coach'); startOnboarding(captureContext(), true); break;
      case 'forget': confirmDanger(t('v3.profile.forgetTitle'), t('v3.profile.forgetIntro'),
        async () => { await request(context, 'post', '/api/profile/forget', {confirmed: true}); await afterProfileChange(context); }); break;
      default: break;
    }
  }

  // ---------- Onboarding on the first Coach visit ----------
  async function startOnboarding(context = captureContext(), force = false) {
    const root = $('onboarding-root');
    if (!root) return;
    if (!force && (stored(ONBOARDING_KEY + context.customerId) || state.conversation.length)) { root.innerHTML = ''; return; }
    let data;
    try { data = await loadProfile(context); } catch { return; }
    if (!data || !current(context) || state.view !== 'coach' || (!force && state.conversation.length)) return;
    if (!force && !data.profile.empty) { root.innerHTML = ''; return; }
    onboardingState = createOnboardingState({suggestions: data.suggestions});
    $('coach-empty').hidden = true;
    root.scrollIntoView?.({block: 'start'});
    onboardingHandle?.detach?.();
    onboardingHandle = attachOnboarding(root, {state: onboardingState, locale: locale(), helpers: helpers(),
      onState: next => { onboardingState = next; },
      onSkipAll: () => { store(ONBOARDING_KEY + context.customerId, 'skipped'); closeOnboarding(); },
      onFinish: result => perform(null, async next => {
        for (const entry of result.entries) await request(next, 'post', '/api/profile/entries', {key: entry.key, value: toApiValue(entry.key, entry.value), source: 'you_told_me', confirmed: true});
        for (const id of result.acceptedSuggestions) await request(next, 'post', '/api/profile/suggestions/confirm', {suggestion_id: id, locale: locale(), confirmed: true});
        for (const id of result.dismissedSuggestions) await request(next, 'post', '/api/profile/suggestions/dismiss', {suggestion_id: id, confirmed: true});
        store(ONBOARDING_KEY + next.customerId, 'done');
        closeOnboarding();
        await loadProfile(next, true);
        deps.notify?.(t('v3.onboarding.saved'));
        deps.refreshSupport?.(next);
      })});
  }
  function closeOnboarding() {
    onboardingHandle?.detach?.(); onboardingHandle = null;
    $('onboarding-root').innerHTML = '';
    $('coach-empty').hidden = state.conversation.length > 0;
    deps.onIntroClosed?.();
  }
  // V4: the intro no longer opens by itself; the Coach empty-state chip and Me open it on request.
  v3.openIntro = () => startOnboarding(captureContext(), true);

  // ---------- Coach topic menu ----------
  function renderTopics() {
    const root = $('topic-menu-root');
    if (!root) return;
    topicHandle?.();
    const catalogue = deps.coachCatalogue?.() || null;
    root.innerHTML = renderTopicButton(locale()) + renderTopicSheet(locale(), {catalogue});
    topicHandle = attachTopicMenu(root, {onAsk: (text, id) => {
      if (!text) return;
      if (onboardingHandle) closeOnboarding();
      if (id && deps.askCatalogue) perform(null, context => deps.askCatalogue(id, text, context));
      else perform(null, context => askCoach(text, context));
    }});
  }
  v3.renderTopics = () => renderTopics();

  // ---------- Spending: month range, selectable bars, cash flow, VAT tile ----------
  v3.renderTrendChart = rows => {
    const end = state.selectedMonth, months = Number(state.trendMonths) || 12;
    const min = state.observedStart?.slice(0, 7), max = state.observedEnd?.slice(0, 7);
    if (end && min && max) renderSpendingPeriod($('trend-range-control'), {end, months, min, max});
    if (trendSelected !== null && trendSelected >= rows.length) trendSelected = null;
    $('trend-chart').innerHTML = trendChart(rows, {interactive: rows.length > 0, selectedIndex: trendSelected});
    if (trendSelected === null || trendSelected === undefined) scrollToLatest($('trend-chart'));
    attachChartSelection($('trend-chart'), index => { trendSelected = index; v3.renderTrendChart(rows); showTrendDetail(rows, index); });
    if (trendSelected === null) $('trend-detail').innerHTML = '';
  };
  // Spending's only period control: ‹ month › for the whole tab, and 3/6/12 months for the charts over time.
  function renderSpendingPeriod(control, {end, months, min, max}) {
    if (!control) return;
    const options = [];
    for (let month = max; month >= min; month = shiftMonth(month, -1)) options.push(`<option value="${esc(month)}"${month === end ? ' selected' : ''}>${esc(monthLabel(month))}</option>`);
    control.innerHTML = `<div class="spending-period"><div class="period-stepper"><button type="button" data-period-step="-1" aria-label="${esc(t('month.previous'))}"${end <= min ? ' disabled' : ''}>‹</button>`
      + `<label class="visually-hidden" for="spending-month">${esc(t('period.month.label'))}</label><select id="spending-month">${options.join('')}</select>`
      + `<button type="button" data-period-step="1" aria-label="${esc(t('month.next'))}"${end >= max ? ' disabled' : ''}>›</button></div>`
      + `<div class="period-segments" role="group" aria-label="${esc(t('range.label'))}">${[3, 6, 12].map(count => `<button type="button" data-period-months="${count}" aria-pressed="${count === months}">${esc(t('spending.period.' + count))}</button>`).join('')}</div></div>`;
    control.onchange = event => { if (event.target?.id === 'spending-month' && event.target.value !== state.selectedMonth) changePeriod(event.target.value); };
    control.onclick = event => {
      const button = event.target?.closest?.('[data-period-step],[data-period-months]');
      if (!button || button.disabled) return;
      if (button.dataset.periodStep) { const next = shiftMonth(state.selectedMonth, Number(button.dataset.periodStep)); if (next >= min && next <= max) changePeriod(next); }
      else if (Number(button.dataset.periodMonths) !== Number(state.trendMonths)) changePeriod(state.selectedMonth, Number(button.dataset.periodMonths));
    };
  }
  async function showTrendDetail(rows, index, context = captureContext()) {
    const row = rows[index];
    if (!row) return;
    const month = row.month || row.period;
    const render = categories => {
      $('trend-detail').innerHTML = chartDetailPanel({month, label: monthLabel(month), total_cents: row.total_cents,
        previous_total_cents: rows[index - 1]?.total_cents, categories}, {money, t: tr});
    };
    render(undefined);
    try {
      const data = await request(context, 'get', '/api/explore', {start: month + '-01', end: monthEnd(month), group_by: 'category', top: 3});
      if (current(context) && trendSelected === index) render((data.rows || []).map(item => ({label: deps.categoryName(item.key), total_cents: item.value_cents})));
    } catch { /* the panel already shows the total */ }
  }

  async function loadCashflow(context = captureContext()) {
    const node = $('cashflow-chart');
    if (!node || !state.observedStart || !state.selectedMonth) return;
    const min = state.observedStart.slice(0, 7), max = state.observedEnd.slice(0, 7);
    const months = Number(state.trendMonths) || 12;
    const start = cashflowGranularity === 'year' ? min : (shiftMonth(state.selectedMonth, 1 - months) < min ? min : shiftMonth(state.selectedMonth, 1 - months));
    const end = cashflowGranularity === 'year' ? max : state.selectedMonth;
    node.setAttribute('aria-busy', 'true');
    try {
      const data = await request(context, 'get', '/api/cashflow/summary', {start_month: start, end_month: end, granularity: cashflowGranularity});
      if (!current(context)) return;
      cashflowData = data; cashflowSelected = null; renderCashflow();
    } catch {
      if (current(context)) { node.innerHTML = `<p class="empty-state">${esc(t('support.unavailable'))}</p>`; node.setAttribute('aria-busy', 'false'); }
    }
  }
  function renderCashflow() {
    const node = $('cashflow-chart');
    const periods = cashflowData?.periods || [];
    const rows = periods.map(row => ({label: cashflowGranularity === 'year' ? String(row.period) : shortMonth(row.period),
      income_cents: row.income_cents, consumption_cents: row.consumption_cents, savings_transfers_cents: row.savings_transfers_cents,
      net_cents: row.net_cents, complete: row.complete}));
    node.innerHTML = cashflowChart(rows, {interactive: rows.length > 0, selectedIndex: cashflowSelected});
    node.setAttribute('aria-busy', 'false');
    attachChartSelection(node, index => { cashflowSelected = index; renderCashflow(); });
    if (cashflowSelected === null) scrollToLatest(node);
    const row = periods[cashflowSelected];
    $('cashflow-detail').innerHTML = row ? `<section class="chart-detail"><h3>${esc(cashflowGranularity === 'year' ? String(row.period) : monthLabel(row.period))}${row.complete ? '' : ' · ' + esc(t('v3.cashflow.partial'))}</h3><dl class="support-values"><dt>${esc(t('v3.recap.income'))}</dt><dd>${money(row.income_cents)}</dd><dt>${esc(t('v3.recap.spent'))}</dt><dd>${money(row.consumption_cents)}</dd>${Number.isSafeInteger(row.left_over_cents) ? `<dt>${esc(t('v3.cashflow.leftOver'))}</dt><dd>${money(row.left_over_cents)}</dd>` : ''}${row.saving_rate_percent !== null && row.saving_rate_percent !== undefined ? `<dt>${esc(t('v3.cashflow.rate'))}</dt><dd>${esc(cashflowPercent(row.saving_rate_percent))}</dd>` : ''}<dt>${esc(t('v3.recap.saved'))}</dt><dd>${money(row.savings_transfers_cents)}</dd><dt>${esc(t('v3.cashflow.net'))}</dt><dd>${money(row.net_cents)}</dd></dl><button type="button" class="text-button" data-direct-question="${esc(t('v3.cashflow.ask', {period: cashflowGranularity === 'year' ? String(row.period) : monthLabel(row.period)}))}">${esc(t('v3.cashflow.askLabel'))} ›</button></section>` : '';
    const change = cashflowData?.comparisons?.saving_rate_change;
    $('cashflow-summary').textContent = change && change.from_percent !== null && change.to_percent !== null && change.from_period !== change.to_period
      ? t(change.direction === 'same' ? 'v3.cashflow.rateSame' : 'v3.cashflow.rateChange', {from: cashflowPercent(change.from_percent), to: cashflowPercent(change.to_percent), start: periodLabel(change.from_period), end: periodLabel(change.to_period)}) : '';
    for (const button of document.querySelectorAll('[data-cashflow-granularity]')) button.setAttribute('aria-pressed', String(button.dataset.cashflowGranularity === cashflowGranularity));
  }
  // '9.6' -> '9.6%' (en) or '9,6 %' (fi/sv).
  function cashflowPercent(value) {
    const lang = globalThis.document?.documentElement?.lang || 'en';
    return lang.startsWith('en') ? String(value) + '%' : String(value).replace('.', ',').replace('-', '−') + '\u00a0%';
  }
  // Long ranges scroll sideways; start at the newest period.
  function scrollToLatest(node) { try { if (node && node.scrollWidth > node.clientWidth) node.scrollLeft = node.scrollWidth; } catch { /* fake DOM */ } }
  function shortMonth(value) {
    const match = /^(\d{4})-(\d{2})$/.exec(String(value));
    if (!match) return String(value);
    try {
      const lang = globalThis.document?.documentElement?.lang || 'en';
      return new Date(Date.UTC(+match[1], +match[2] - 1, 15)).toLocaleDateString(lang, {month: 'short', year: '2-digit', timeZone: 'UTC'});
    } catch { return String(value); }
  }
  const periodLabel = value => /^\d{4}-\d{2}$/.test(String(value)) ? monthLabel(value) : String(value);

  async function loadVatTile(context = captureContext()) {
    const node = $('vat-tile');
    if (!node || !state.selectedMonth) return;
    try {
      const card = await request(context, 'get', '/api/vat/card', {month: state.selectedMonth, locale: locale()});
      if (!current(context) || !card || !Number.isSafeInteger(card.estimated_vat_cents) || !card.estimated_vat_cents) { if (current(context)) node.innerHTML = ''; return; }
      node.innerHTML = `<aside class="vat-tile"><p class="eyebrow">${esc(t('v3.vat.eyebrow'))}</p><p>${esc(t('v3.vat.line', {vat: money(card.estimated_vat_cents), spent: money(card.spending_cents ?? card.gross_spending_cents), category: deps.categoryName(card.category), rate: card.rate_label || ''}))}</p><p class="small-text">${esc(t('v3.vat.note'))}</p></aside>`;
    } catch { if (current(context)) node.innerHTML = ''; }
  }

  // ---------- Taxes ----------
  async function openTax(context = captureContext()) {
    openPanel(`<p class="empty-state" role="status">${esc(t('loading.account'))}</p>`, {title: t('v3.tax.title')});
    let data;
    try { data = await request(context, 'get', '/api/tax', {locale: locale()}); } catch (error) {
      if (current(context)) $('v3-dialog-content').innerHTML = `<p class="empty-state">${esc(t('support.unavailable'))}</p>`;
      return;
    }
    if (!current(context)) return;
    taxOverview = data;
    $('v3-dialog-content').innerHTML = taxHTML(data);
    $('v3-dialog-content').querySelector('[data-v3-tax-edit]')?.addEventListener('click', () => {
      const entry = data.tax_entry_id ? entryById(data.tax_entry_id) : null;
      closeDialogs();
      loadProfile(context).then(() => profileEntryDraft(entry || entryById(data.tax_entry_id) || 'tax'));
    });
  }
  function taxHTML(data) {
    const w = data.withholding || {}, plan = data.back_tax_plan, refund = data.refund_seen;
    // The server sends every tax sentence in EN/FI/SV (locale money format); use the current language.
    const lc = (en, texts) => (texts && typeof texts[locale()] !== 'undefined' ? texts[locale()] : en);
    const rawCycle = data.cycle || {};
    const cycle = {...rawCycle, label: lc(rawCycle.label, rawCycle.stage_label_texts), tasks: lc(rawCycle.tasks, rawCycle.task_texts), check_mytax_note: lc(rawCycle.check_mytax_note, rawCycle.check_mytax_note_texts)};
    const flowText = w.flow ? lc(w.flow.text, w.flow.texts) : null;
    const flow = w.available && flowText ? `<p class="support-amount tax-flow">${esc(flowText)}</p>` : `<p>${esc(w.why || lc(w.reason, w.reason_texts) || t('v3.tax.missing'))}</p>`;
    const stage = cycle.label ? `<section class="tax-stage"><h3>${esc(cycle.label)}</h3>${cycle.next_date ? `<p>${esc(t('v3.tax.next', {date: dateLabel(cycle.next_date), days: cycle.days_until ?? ''}))}</p>` : ''}${(cycle.tasks || []).length ? `<ul>${cycle.tasks.map(task => `<li>${esc(typeof task === 'string' ? task : task.text || task.label || '')}</li>`).join('')}</ul>` : ''}${cycle.check_mytax_note ? `<p class="small-text">${esc(cycle.check_mytax_note)}</p>` : ''}</section>` : '';
    const setAside = plan && Number.isSafeInteger(plan.monthly_set_aside_now_cents) ? `<p class="safe-save">${esc(t('v3.tax.setAside', {amount: money(plan.monthly_set_aside_now_cents)}))}</p>` : '';
    const seen = refund?.seen && refund.match ? `<p class="safe-save">${esc(t('v3.tax.refundSeen', {amount: money(refund.match.amount_cents), date: dateLabel(refund.match.date)}))}</p>` : '';
    return `<section class="tax-card"><p class="eyebrow">${esc(t('v3.tax.eyebrow'))}</p><h2>${esc(t('v3.tax.title'))}</h2>${w.available ? `<p class="small-text">${esc(t('v3.tax.explainer'))}</p>` : ''}${flow}${stage}${setAside}${seen}<button type="button" class="primary-button" data-v3-tax-edit>${esc(t(data.tax_entry_id ? 'v3.tax.edit' : 'v3.tax.add'))}</button><p class="small-text">${esc(lc(data.footer, data.footer_texts) || t('v3.tax.footer'))}</p></section>`;
  }
  async function loadTaxChip(context = captureContext()) {
    const node = $('home-tax-chip');
    if (!node) return;
    try {
      const data = await request(context, 'get', '/api/tax', {locale: locale()});
      if (!current(context)) return;
      const cycle = data.cycle || {};
      const near = ['check_return', 'refund_expected', 'back_tax_due'].includes(cycle.stage) && Number.isInteger(cycle.days_until) && cycle.days_until >= 0 && cycle.days_until <= 30;
      node.innerHTML = near ? `<button type="button" class="tax-chip" data-v3-open-tax>${esc(cycle.label || t('v3.tax.title'))} · ${esc(dateLabel(cycle.next_date))} ›</button>` : '';
    } catch { if (current(context)) node.innerHTML = ''; }
  }

  // ---------- Year in review ----------
  async function loadYearBanner(context = captureContext()) {
    const node = $('year-banner');
    if (!node) return;
    try {
      yearOptions = await request(context, 'get', '/api/year-review/options', {});
      if (!current(context)) return;
      const options = Array.isArray(yearOptions) ? yearOptions : (yearOptions.options || yearOptions.years || []);
      const year = options.find(option => option.complete && option.available !== false)?.year;
      const profile = await loadProfile(context).catch(() => null);
      const saved = (profile?.profile?.by_key?.year_review || []).some?.(entry => entry.value?.year === year);
      node.innerHTML = year && !saved && stored(BANNER_KEY + context.customerId + '.' + year) !== '1' ? renderYearBanner(year, locale()) : '';
    } catch { if (current(context)) node.innerHTML = ''; }
  }
  async function openYearReview(year, context = captureContext()) {
    let review;
    try { review = await request(context, 'get', '/api/year-review', {year, locale: locale()}); } catch (error) { explainError(error); return; }
    if (!current(context)) return;
    const story = review.story_cards || review;
    let captions = {}, closingMessage = null;
    const overlay = document.createElement('div');
    overlay.className = 'year-story-overlay';
    document.body.append(overlay);
    const options = index => ({locale: locale(), money, monthLabel, dateLabel, captions, closingMessage, index});
    let detach = null;
    const close = () => { detach?.(); overlay.remove(); };
    detach = attachStory(overlay, {review: story, money,
      render: (index, extra = {}) => renderStory(story, {...options(index), ...extra}),
      onClose: close,
      onSave: () => perform(null, async next => {
        await request(next, 'post', '/api/year-review/save', {year: Number(year), captions, closing_message: closingMessage, confirmed: true});
        store(BANNER_KEY + next.customerId + '.' + year, '1');
        await loadProfile(next, true);
        if ($('year-banner')) $('year-banner').innerHTML = '';
        deps.notify?.(t('v3.year.saved'));
      }),
      onAsk: () => { close(); perform(null, next => askCoach(t('v3.year.ask', {year}), next)); }});
    // Captions are optional; the viewer starts with its own localized captions.
    request(context, 'post', '/api/year-review/captions', {year: Number(year)}).then(result => {
      if (!result || !current(context)) return;
      captions = result.captions || {}; closingMessage = result.closing_message || null;
    }).catch(() => {});
  }

  // ---------- Agent actions ----------
  v3.handleAgentAction = (turn, action) => {
    const params = action?.params || {};
    const provenance = 'gemini_proposed_user_confirmed';
    switch (action?.kind) {
      case 'create_goal': createGoalDraft({name: params.name, target_cents: params.target_cents, target_date: params.target_date}, provenance); return true;
      case 'update_goal': { const goal = findGoal(params); if (!goal) return false; editGoalDraft(goal, params.fields || {}, provenance); return true; }
      case 'delete_goal': { const goal = findGoal(params); if (!goal) return false; deleteGoalDraft(goal, provenance); return true; }
      case 'update_profile': {
        const entries = Array.isArray(params.entries) ? params.entries : [];
        if (!entries.length) return false;
        const context = captureContext();
        const specs = entries.map((entry, index) => ({...draftSpecForEntry({key: entry.key, value: toUiValue(entry.key, entry.value)}, locale()),
          id: 'profile-chat-' + index, title: t('v3.profile.noteTitle'), intro: entry.note || undefined}));
        openDraft(specs, {onSave: async (values, spec, index) => {
          const entry = entries[index];
          const converted = draftValueToEntry(entry.key, values, toUiValue(entry.key, entry.value));
          if (converted.errors && Object.keys(converted.errors).length) throw new Error(t('error.validation'));
          await request(context, 'post', '/api/profile/entries', {key: entry.key, value: toApiValue(entry.key, converted.value),
            source: 'from_our_chat', ...(entry.note ? {note: entry.note} : {}), confirmed: true, provenance});
          await afterProfileChange(context);
        }});
        return true;
      }
      case 'open_year_review': if (params.year) { openYearReview(params.year); return true; } return false;
      case 'enable_plan': if (!['mortgage', 'tax'].includes(params.plan)) return false; loadProfile().catch(() => null).then(() => openPlan(params.plan, provenance)); return true;
      default: return false;
    }
  };

  // ---------- Lifecycle hooks ----------
  v3.onNavigate = view => {
    if (view === 'profile') renderProfile();
    if (view === 'coach') renderTopics();
    if (view === 'goals') { loadProfile().catch(() => null); plans.render(); }
  };
  v3.onLoad = (context = captureContext()) => {
    loadCashflow(context); loadVatTile(context); loadYearBanner(context); loadTaxChip(context);
    if (state.view === 'profile') renderProfile(context);
    if (state.view === 'coach') renderTopics();
    if (state.view === 'goals') plans.render(context);
  };
  v3.reset = () => {
    profileData = null; profilePending = null; trendSelected = null; cashflowData = null; cashflowSelected = null; taxOverview = null;
    onboardingHandle?.detach?.(); onboardingHandle = null; plans.reset();
    for (const id of ['trend-detail', 'cashflow-detail', 'vat-tile', 'year-banner', 'home-tax-chip', 'onboarding-root']) if ($(id)) $(id).innerHTML = '';
  };
  v3.onLanguage = () => {
    renderTopics();
    if (state.view === 'profile') renderProfile();
    if (cashflowData) renderCashflow();
    plans.repaint();
    const context = captureContext();
    loadVatTile(context); loadYearBanner(context); loadTaxChip(context);
  };
  v3.profileForPlanning = () => profileData?.profile;
  // Home (lane H): review-before-saving cards and the 'Tell the coach about you' intro.
  v3.openDraft = openDraft;
  v3.startIntro = () => handleProfileAction({type: 'onboarding'}, captureContext());

  // ---------- Delegated clicks (called from app.js's document click handler) ----------
  v3.handleClick = event => {
    if (plans.handleClick(event)) return true;
    const target = event.target?.closest?.('[data-goal-edit],[data-goal-delete],[data-cashflow-granularity],[data-chart-transactions],[data-chart-ask],[data-story-open],[data-story-dismiss],[data-v3-open-tax],[data-v3-migrate]');
    if (!target || !target.dataset) return false;
    const handled = route(target);
    return handled !== false;
  };
  function route(target) {
    if (target.dataset.goalEdit) { const goal = findGoal({goal_id: target.dataset.goalEdit}); if (goal) editGoalDraft(goal); return; }
    if (target.dataset.goalDelete) { const goal = findGoal({goal_id: target.dataset.goalDelete}); if (goal) deleteGoalDraft(goal); return; }
    if (target.dataset.cashflowGranularity) { cashflowGranularity = target.dataset.cashflowGranularity; loadCashflow(); return; }
    if (target.dataset.chartTransactions) { perform(target, context => showTransactions({month: target.dataset.chartTransactions}, context)); return; }
    if (target.dataset.chartAsk) { perform(target, context => askCoach(t('v3.trend.ask', {month: monthLabel(target.dataset.chartAsk)}), context)); return; }
    if (target.dataset.storyOpen) { openYearReview(Number(target.dataset.storyOpen)); return; }
    if (target.dataset.storyDismiss) { store(BANNER_KEY + state.customerId + '.' + target.dataset.storyDismiss, '1'); $('year-banner').innerHTML = ''; return; }
    if (target.hasAttribute?.('data-v3-open-tax')) { openTax(); return; }
    if (target.hasAttribute?.('data-v3-migrate')) {
      const local = deps.localProfile?.();
      perform(target, async context => { await request(context, 'post', '/api/profile/migrate-local', {local, confirmed: true}); await afterProfileChange(context); });
      return true;
    }
    return false;
  }
  // Every hook fails safe: a component error must never break the rest of the app.
  const guard = (name, fallback) => {
    const fn = v3[name];
    v3[name] = (...args) => {
      try { return fn(...args); } catch (error) { globalThis.console?.warn?.('[v3] ' + name, error); return fallback?.(...args); }
    };
  };
  guard('renderTrendChart', rows => { $('trend-chart').innerHTML = trendChart(rows); });
  guard('onNavigate'); guard('onLoad'); guard('openIntro'); guard('renderTopics'); guard('reset'); guard('onLanguage');
  guard('handleAgentAction', () => false); guard('handleClick', () => false); guard('goalActionsHTML', () => '');
  return v3;
}
