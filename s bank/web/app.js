import { createAPI } from './api.js';
import { createState, selectPersona, money, escapeHTML as esc, dateLabel, eurosToCents, forecastRows, setFormattingLocale, shiftMonth, monthEnd, monthLabel } from './state.js';
import { comparisonChart, trendChart, runwayChart, goalChart, configureCharts } from './charts.js';
import { createI18n } from './i18n.js';

const state = createState();
let api = createAPI(state.customerId);
const $ = id => document.getElementById(id);
const text = (id, value) => { $(id).textContent = value; };
const i18n=createI18n();
const t=(key,values)=>i18n.t(key,values);
const flowKeys={income:'money.income',fixed_obligation:'basket.regular',flexible_essential:'basket.irregular',discretionary:'basket.everyday',saving_or_transfer:'basket.saving',needs_review:'basket.review'};
const flowHelp={income:'basket.income.help',fixed_obligation:'basket.regular.help',flexible_essential:'basket.irregular.help',discretionary:'basket.everyday.help',saving_or_transfer:'basket.saving.help',needs_review:'basket.review.help'};
const flowName=role=>t(flowKeys[role]||'basket.review');
function priorityCopy(candidate){
  if(!candidate)return null;
  if(candidate.kind==='payday_timing')return {title:t('home.priority.payday.title'),description:t('home.priority.payday.description'),question:t('home.priority.payday.question')};
  if(candidate.kind==='salary_change')return {title:t('home.priority.salary.title'),description:t('home.priority.salary.description'),question:t('home.priority.salary.question')};
  if(candidate.kind==='home_financing_history')return {title:t('home.priority.home.title'),description:t('home.priority.home.description'),question:t('home.priority.home.question')};
  if(candidate.kind==='explain_change'&&candidate.id!=='restaurant_change')return {title:t('home.priority.unusual.title'),description:t('home.priority.unusual.description'),question:t('home.priority.unusual.question')};
  return null;
}
const percentage=bp=>`${new Intl.NumberFormat(i18n.localeTag,{maximumFractionDigits:1}).format(Number(bp||0)/100)} %`;
const vatEstimateFor=ref=>(state.vat?.transactions||[]).find(item=>item.transaction_ref===ref);
const vatMappingLabel=vat=>t(`vat.mapping.${vat?.mapping_quality||'unmapped'}`);
const vatSourceLabel=vat=>vat?.rate_source?.kind==='mcc'?`MCC ${vat.rate_source.value}`:vat?.rate_source?.kind==='category'?`${t('vat.source.category')}: ${vat.rate_source.value}`:t('vat.source.unmapped');
const isDemoStory=()=>state.customerId==='CUST00001'&&state.selectedMonth==='2026-09';
const comparisonQuery=month=>({month,comparison_month:shiftMonth(month,-1),category:'Restaurants'});
class StaleResponse extends Error {}
const captureContext = () => ({customerId:state.customerId,api,generation:state.generation,month:state.selectedMonth,trendMonths:state.trendMonths,locale:i18n.locale});
const isCurrent = context => context.customerId===state.customerId && context.api===api && context.generation===state.generation;
function assertCurrent(context){if(!isCurrent(context))throw new StaleResponse();}
async function request(context, method, path, values){
  assertCurrent(context);
  const result=await context.api[method](path,values);
  assertCurrent(context);
  return result;
}
function errorText(error){
  if(i18n.locale==='en')return error.message||t('error.generic');
  const message=String(error.message||'').toLowerCase();
  return t(message.includes('database')?'error.database':message.includes('period')||message.includes('month')?'error.period':message.includes('customer')?'error.customer':message.includes('connect')||message.includes('reach')?'error.network':'error.validation');
}
const explainError = error => notify(errorText(error), true);
function notify(message, retry=false) {
  let container=$('status-message');
  const active=Array.from(document.querySelectorAll('dialog[open]')).at(-1);
  if(active){
    container=active.querySelector('.dialog-notice');
    if(!container){container=document.createElement('p');container.className='status-message dialog-notice';container.setAttribute('role','status');container.setAttribute('aria-live','polite');active.querySelector('.sheet-content').prepend(container);}
  }
  container.replaceChildren(document.createTextNode(message));
  if(retry){const button=document.createElement('button');button.className='text-button';button.textContent=t('action.retry');button.addEventListener('click',()=>load());container.append(button);}
}
async function perform(button, action) {
  if(state.busy) return;
  const context=captureContext();
  state.busy=true;
  const original=button?.textContent;
  if(button){button.dataset.loadingLabel=original;button.disabled=true;button.textContent=t('loading.action');}
  try { await action(context); }
  catch(error){if(isCurrent(context)&&!(error instanceof StaleResponse))explainError(error);}
  finally {if(isCurrent(context)){state.busy=false;if(button){button.disabled=false;if(button.dataset.loadingLabel&&button.textContent===t('loading.action'))button.textContent=original;delete button.dataset.loadingLabel;}}}
}
function openDialog(id) { const dialog=$(id); if(!dialog.open) dialog.showModal(); }
function closeDialogs(){document.querySelectorAll('dialog[open]').forEach(dialog=>dialog.close());}
function clearFilter(){state.filter=null;document.querySelectorAll('[data-role]').forEach(button=>button.setAttribute('aria-pressed','false'));}
function clearHandoff(){
  state.pendingHandoff=null;
  for(const id of ['goal-name','goal-template','goal-target','goal-saved','goal-date','goal-reserve'])$(id).disabled=false;
  text('goal-handoff',t('goal.intro'));
  text('goal-submit',t('goal.create')+' ↗');
}
function renderHandoffProgress(pending){
  if(state.pendingHandoff!==pending)return;
  const saved=Boolean(pending.createdGoalId);
  for(const id of ['goal-name','goal-template','goal-target','goal-saved','goal-date','goal-reserve'])$(id).disabled=saved;
  if(pending.linkComplete){
    text('goal-handoff',t('handoff.host'));
    text('goal-submit',t('handoff.finishHost')+' ↗');
  }else if(saved){
    text('goal-handoff',t('handoff.saved',{amount:money(pending.contributionCents)}));
    text('goal-submit',t('handoff.finishLink',{amount:money(pending.contributionCents)})+' ↗');
  }
}
function clearScopedViews({preserveLoading=false}={}){
  closeDialogs();clearFilter();clearHandoff();state.transactionEvidence=null;
  if(!preserveLoading)for(const button of document.querySelectorAll('[data-loading-label]')){button.disabled=false;button.textContent=button.dataset.loadingLabel;delete button.dataset.loadingLabel;}
  text('scenario-amount','—');text('scenario-detail','');text('coach-response','');text('transaction-summary','');
  $('transaction-list').replaceChildren();$('calculation-content').replaceChildren();
  text('coach-debug-content','');$('coach-debug').hidden=true;$('tax-plan-result').replaceChildren();
  $('coach-home-history').hidden=true;
  $('tax-plan-amount').value='';$('tax-plan-saved').value='0';$('tax-plan-date').value='';$('tax-plan-location').value='inside_current_balance';
  $('mark-one-off').hidden=false;$('undo-action').disabled=true;$('link-goal').disabled=true;
}
function navigate(view) {
  clearFilter();clearHandoff();
  state.view=view;
  for(const name of ['home','trends','goals']) $(name+'-view').hidden=name!==view;
  document.querySelectorAll('[data-view]').forEach(button=>{if(button.dataset.view===view)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});
  window.scrollTo({top:0,behavior:'instant'});
  $('main-content').focus({preventScroll:true});
}
function normalizeComparison(data,period=state.selectedMonth) {
  return {...data,scopeMonth:period,before:{...data.previous,label:monthLabel(shiftMonth(period,-1))},after:{...data.current,label:monthLabel(period)}};
}
function renderComparison() {
  const c=state.comparison;
  if(!c){$('comparison-chart').innerHTML='';$('trend-comparison').innerHTML='';return;}
  const period=c.scopeMonth||state.selectedMonth;
  const labels={current:monthLabel(period),previous:monthLabel(shiftMonth(period,-1))};
  $('comparison-chart').innerHTML=comparisonChart(c);$('trend-comparison').innerHTML=comparisonChart(c);
  text('story-title',t(c.count_delta===0?'story.sameTitle':'story.title'));
  text('story-description',t('story.change',{...labels,amount:money(c.delta_cents)})+' '+t(c.count_delta===0?'story.sameCount':'story.changedCount',{count:c.count_delta}));
  $('comparison-decomposition').innerHTML=`<div class="decomposition"><div><p>${esc(t('story.count'))}</p><strong>${esc(c.before.count)} → ${esc(c.after.count)}</strong><small>${esc(t(c.count_delta===0?'story.sameCount':'story.changedCount',{count:c.count_delta}))}</small></div><div><p>${esc(t('story.average'))}</p><strong>${money(c.before.average_cents)} → ${money(c.after.average_cents)}</strong><small>${esc(t('story.averageObserved'))}</small></div></div>`;
  text('show-transactions',t('story.transactions',{count:c.after.count,period:labels.current})+' ↗');
  $('clarification-card').hidden=!isDemoStory();
  text('clarification-question',t('story.oneOffQuestion',{amount:money(3647)}));
  if(isDemoStory()){
    text('insight-headline',t('home.demoHeadline',{amount:money(c.delta_cents)}));text('insight-description',t('home.demoDescription'));
  }else if(!state.overview?.priority||state.overview.priority.id==='restaurant_change'){
    text('insight-headline',t('home.genericHeadline',{amount:money(c.delta_cents),period:labels.current}));text('insight-description',t('home.genericDescription'));
  }
}
function renderOverview() {
  const o=state.overview;if(!o)return;
  state.observedStart=o.observed_start||state.observedStart;state.observedEnd=o.observed_end||state.observedEnd;
  const first=state.observedStart?.slice(0,7),last=state.observedEnd?.slice(0,7),choices=[];
  if(first&&last)for(let period=first;period<=last;period=shiftMonth(period,1))choices.push(period);
  $('selected-month').innerHTML=choices.reverse().map(period=>`<option value="${period}">${esc(monthLabel(period))}</option>`).join('');
  $('selected-month').min=first||'';$('selected-month').max=last||'';$('selected-month').value=state.selectedMonth||'';
  $('trend-range').value=String(state.trendMonths);
  text('map-period',monthLabel(state.selectedMonth));text('trend-period',monthLabel(state.selectedMonth));
  text('current-balance',money(o.latest_balance_cents));$('current-balance').classList.remove('skeleton');
  text('account-caption',`${o.account_id||t('common.account')} · ${t('common.observed')} ${dateLabel(o.latest_balance_date)}`);
  $('money-flow').innerHTML='';$('money-flow').setAttribute('aria-busy','false');
  const flows=(o.flows||[]).filter(row=>row.role!=='needs_review'||row.transaction_refs?.length||row.amount_cents);
  $('flow-legend').innerHTML=flows.map(row=>`<button class="flow-filter" data-role="${esc(row.role)}" aria-pressed="${state.filter===row.role}"><span>${esc(flowName(row.role))}</span><strong>${money(row.role==='saving_or_transfer'?row.amount_cents:Math.abs(row.amount_cents))}<span class="flow-arrow" aria-hidden="true">↗</span></strong><span class="flow-help">${esc(t(flowHelp[row.role]||'basket.review.help'))}</span></button>`).join('');
  text('open-story',t('home.priority.open')+' ↗');$('open-story').disabled=false;
  if(!state.comparison){text('insight-headline',t('home.noComparison'));text('insight-description',t('home.noComparisonHelp'));}
  const candidate=o.priority;
  if(candidate&&candidate.id!=='restaurant_change'&&!isDemoStory()){
    const copy=priorityCopy(candidate);
    text('insight-headline',copy?.title||t('home.priority.title'));
    text('insight-description',copy?.description||t('home.priority.description'));
  }
  $('coach-home-history').hidden=!(o.candidates||[]).some(item=>item.kind==='home_financing_history');
  const taxReference=o.latest_balance_date||state.observedEnd;
  if(taxReference){$('tax-plan-date').min=shiftMonth(taxReference.slice(0,7),1)+'-01';if(!$('tax-plan-date').value)$('tax-plan-date').value=monthEnd(shiftMonth(taxReference.slice(0,7),6));}
  if(!$('goal-date').value&&state.observedEnd)$('goal-date').value=monthEnd(shiftMonth(state.observedEnd.slice(0,7),6));
  if(state.observedEnd)$('goal-date').min=shiftMonth(state.observedEnd.slice(0,7),1)+'-01';
}
function renderScenario() {
  const result=state.scenario;if(!result){text('scenario-amount','—');return;}
  const contribution=result.monthly_contribution_cents??result.modeled_monthly_contribution_cents;
  $('scenario-amount').innerHTML=`${money(contribution)}<span>${esc(t('common.perMonth'))}</span>`;
  text('scenario-detail',t('scenario.base',{base:money(result.adjustable_base_cents)})+' '+t(state.exclusion?'scenario.excluded':'scenario.included'));
  $('link-goal').disabled=!Number.isFinite(contribution);$('mark-one-off').hidden=Boolean(state.exclusion);$('exclusion-label').hidden=!state.exclusion;$('undo-action').disabled=!state.exclusion;
}
async function ensureScenario(context=captureContext()) {
  assertCurrent(context);
  if(state.scenario)return state.scenario;
  const result=await request(context,'post','/api/scenarios',{month:context.month,category:'Restaurants',percent:20,confirmed:true});
  state.scenario=result.scenario ?? result;
  renderScenario();
  return state.scenario;
}
async function showStory(context=captureContext()) {
  assertCurrent(context);clearFilter();
  if(!state.comparison){
    try{state.comparison=normalizeComparison(await request(context,'get','/api/comparison',comparisonQuery(context.month)),context.month);renderComparison();}
    catch(error){if(error instanceof StaleResponse)throw error;openDialog('coach-dialog');await askCoach(t('coach.promptMonth'),context);return;}
  }
  if(!isDemoStory()&&state.overview?.priority&&state.overview.priority.id!=='restaurant_change'){
    openDialog('coach-dialog');
    await askCoach(priorityCopy(state.overview.priority)?.question||t('coach.promptMonth'),context);
    return;
  }
  openDialog('story-dialog');
  await ensureScenario(context);
}
async function fetchRows(filters={},context=captureContext()) {
  const result=await request(context,'get','/api/transactions',{month:context.month,...filters});
  return result.transactions || result.rows || [];
}
function renderRows(rows,label=monthLabel(state.selectedMonth)) {
  state.rows=rows;
  text('transaction-summary',t('transactions.summary',{label,count:rows.length}));
  $('transaction-list').innerHTML=rows.length?rows.map(row=>{const vat=vatEstimateFor(row.transaction_ref);const vatTitle=vat?[vatSourceLabel(vat),vatMappingLabel(vat),vat.mapping_note].filter(Boolean).join(' · '):'';const taxLine=vat?`<p class="tax-inside" title="${esc(vatTitle)}">${esc(vat.estimated_vat_cents===null?t('vat.unmapped'):t('vat.taxInside',{amount:money(vat.estimated_vat_cents),rate:percentage(vat.rate_basis_points)}))}</p>`:'';return `<article class="transaction-row"><div><h3>${esc(row.merchant_name||row.merchant||t('transactions.unknownMerchant'))}</h3><p>${dateLabel(row.date||row.timestamp)} · ${esc(row.category==='Restaurants'?t('category.restaurants'):row.category||t('transactions.unknownCategory'))}</p><p>${esc(flowName(row.role))}</p>${taxLine}${row.transaction_ref===state.exclusion?`<span class="row-badge">${esc(t('story.userExclusion'))}</span>`:''}<button class="text-button" data-transaction="${esc(row.transaction_ref)}">${esc(t('transactions.open'))} ↗</button></div><strong>${money(Math.abs(row.amount_cents))}</strong></article>`;}).join(''):`<p class="empty-state">${esc(t('empty.transactions'))}</p>`;
}
async function showTransactions(filters={category:'Restaurants'},context=captureContext()) {
  assertCurrent(context);if(!filters.role)clearFilter();state.transactionEvidence=null;
  openDialog('transactions-dialog');$('transaction-list').innerHTML=`<p class="empty-state" role="status">${esc(t('loading.rows'))}</p>`;
  const rows=await fetchRows(filters,context);assertCurrent(context);
  state.transactionEvidence=filters.role?moneyMapEvidence(filters.role):restaurantEvidence();
  renderRows(rows,filters.role?flowName(filters.role):monthLabel(context.month));
}
async function markOneOff(context=captureContext()) {
  await ensureScenario(context);assertCurrent(context);
  const rows=await fetchRows({category:'Restaurants'},context);assertCurrent(context);
  const row=rows.find(row=>Math.abs(row.amount_cents)===3647);
  if(!row)throw new Error(t('error.oneOffMissing'));
  const scenarioId=state.scenario.scenario_id || state.scenario.id;
  const result=await request(context,'post','/api/scenarios/exclude',{scenario_id:scenarioId,transaction_ref:row.transaction_ref,confirmed:true});
  state.scenario=result.scenario || result;
  state.exclusion=row.transaction_ref;
  state.exclusionDetail=row;
  renderScenario();
  notify(t('feedback.excluded'));
}
function renderForecast() {
  const f=state.forecast;$('runway-chart').innerHTML=runwayChart(forecastRows(f));
  $('forecast-assumptions').innerHTML=`<details class="forecast-method"><summary>${esc(t('evidence.formula'))}</summary><p>${esc(t('forecast.method'))}</p></details>${(f?.recurring_items||[]).map((item,i)=>`<fieldset class="assumption-inputs" data-assumption="${esc(item.id)}"><legend>${esc(flowName(item.role))}</legend><label for="assumption-enabled-${i}"><input id="assumption-enabled-${i}" type="checkbox" data-field="enabled" ${state.forecastAssumptions[item.id]?.enabled===false?'':'checked'}>${esc(t('forecast.include'))}</label><div class="form-grid"><div><label for="assumption-amount-${i}">${esc(t('forecast.amount'))}</label><input id="assumption-amount-${i}" data-field="amount" type="number" step="0.01" value="${Number(state.forecastAssumptions[item.id]?.amount_cents??item.amount_cents??0)/100}"></div><div><label for="assumption-day-${i}">${esc(t('forecast.day'))}</label><input id="assumption-day-${i}" data-field="day" type="number" min="1" max="31" value="${state.forecastAssumptions[item.id]?.median_day??item.median_day??1}"></div></div></fieldset>`).join('')}<button class="secondary-button" id="apply-preview">${esc(t('forecast.apply'))} ↗</button><p>${esc(t('forecast.temporary'))}</p>`;
}
function renderTrends() {
  const data=state.trends,rows=(data?.months||[]).filter(row=>row.available!==false&&row.total_cents!==null);
  $('trend-chart').innerHTML=trendChart(rows);text('trend-description',rows.length?t('trends.description',{count:rows.length}):t('empty.trends'));
  $('trends-view').querySelector('.trend-facts')?.remove();
  if(!data)return;
  const annual=data.annual_comparison;
  const evidence=`<section class="trend-facts"><h3>${esc(t('trends.sameMonth'))}</h3><p>${esc(data.year_over_year_delta_cents===null||data.year_over_year_delta_cents===undefined?t('empty.trends'):t('trends.yoy',{amount:money(data.year_over_year_delta_cents)}))}</p><h3>${esc(t('trends.salary'))}</h3><p>${esc(t('trends.salaryMedians',{recent:money(data.recent_three_salary_median_cents),prior:money(data.prior_six_salary_median_cents)}))}</p>${annual?.available?`<details><summary>${esc(t('trends.annual'))}</summary>${comparisonChart({before:{...annual.previous,label:t('trends.priorYear')},after:{...annual.current,label:t('trends.latestYear')}})}<p>${dateLabel(annual.previous.start)}–${dateLabel(annual.previous.end)} / ${dateLabel(annual.current.start)}–${dateLabel(annual.current.end)}</p></details>`:`<p>${esc(t('trends.noAnnual'))}</p>`}<details><summary>${esc(t('evidence.formula'))}</summary><p>${esc(t('common.account'))}: ${esc(data.account_id)} · ${esc(t('evidence.facts'))}: <code>${esc(data.fact_id)}</code></p><ul>${(data.transaction_refs||[]).map(ref=>`<li><code>${esc(ref)}</code></li>`).join('')}</ul></details></section>`;
  $('trend-chart').insertAdjacentHTML('afterend',evidence);
}
function renderGoals() {
  $('goals-list').innerHTML=state.goals.length?state.goals.map(goal=>`<article class="goal-card"><span class="status-pill scenario-pill">${esc(t('common.estimate'))}</span><h2>${esc(goal.name)}</h2><p class="subtle">${esc(t('goal.by',{date:dateLabel(goal.target_date)}))}</p><p class="goal-amount">${money(goal.required_monthly_cents)} <span>${esc(t('goal.required'))}</span></p>${goalChart(goal.current_saved_cents??0,goal.target_cents)}<p class="small-text">${esc(t('goal.capacity',{amount:money(goal.conservative_monthly_contribution_cents)}))}</p><p class="small-text">${esc(t('goal.reserveDetail',{reserve:money(goal.reserve_floor_cents),upfront:money(goal.upfront_available_cents)}))}</p>${goal.modeled_scenario_contribution_cents>0?`<p class="small-text">${esc(t('goal.linked',{amount:money(goal.modeled_scenario_contribution_cents)}))}</p>`:''}${goal.monthly_gap_cents>0?`<p class="small-text">${esc(t('goal.gap',{amount:money(goal.monthly_gap_cents)}))}</p>`:''}<button class="text-button" data-goal-evidence="${esc(goal.goal_id||goal.id)}">${esc(t('goal.assumptions'))} ↗</button></article>`).join(''):`<div class="goal-card"><span class="eyebrow">${esc(t('goals.eyebrow'))}</span><h2>${esc(t('goals.empty'))}</h2><p class="subtle">${esc(t('goals.subtitle'))}</p></div>`;
}
function supportingEvidence(data){
  const calculationRefs=data.transaction_refs||[],historyRefs=data.comparison_transaction_refs||[];
  const assumptions=(data.assumptions||[]).map((item,index)=>t(`safe.assumption.${index}`)===`safe.assumption.${index}`?item:t(`safe.assumption.${index}`));
  return `<details><summary>${esc(t('safe.evidence'))}</summary><p>${esc(t('evidence.facts'))}: <code>${esc(data.fact_id||'—')}</code></p>${assumptions.length?`<h3>${esc(t('evidence.assumptions'))}</h3><ul>${assumptions.map(item=>`<li>${esc(item)}</li>`).join('')}</ul>`:''}<h3>${esc(t('evidence.calculationSources'))}</h3><ul>${calculationRefs.map(ref=>`<li><code>${esc(ref)}</code></li>`).join('')}</ul>${historyRefs.length?`<h3>${esc(t('evidence.historySources'))}</h3><ul>${historyRefs.map(ref=>`<li><code>${esc(ref)}</code></li>`).join('')}</ul>`:''}</details>`;
}
function renderSupport(){
  const safe=state.safeToSpend;
  $('safe-content').innerHTML=!safe?`<p class="empty-state">${esc(t('support.unavailable'))}</p>`:!safe.available?`<p class="empty-state">${esc(t(safe.needs_history?'support.needsHistory':'support.unavailable'))}</p>`:`<p class="support-period">${esc(t('safe.amount',{days:safe.horizon_days}))}</p><p class="support-amount">${money(safe.safe_to_spend_cents)}</p><p class="small-text">${esc(t('safe.horizon',{date:dateLabel(safe.horizon_end)}))}</p><dl class="support-values"><dt>${esc(t('safe.reserve'))}</dt><dd>${money(safe.reserve_floor_cents)}</dd><dt>${esc(t('safe.obligations'))}</dt><dd>${money(safe.scheduled_outflows_cents)}</dd><dt>${esc(t('safe.everydayAllowance'))}</dt><dd>${money(safe.historical_flexible_buffer_cents)}</dd></dl><p class="small-text">${esc(t('safe.demoReserve'))}</p>${supportingEvidence(safe)}`;
  const investment=state.investments;
  $('investment-content').innerHTML=!investment?`<p class="empty-state">${esc(t('support.unavailable'))}</p>`:`<p class="support-period">${monthLabel(investment.start_month||state.selectedMonth)} — ${monthLabel(investment.end_month||state.selectedMonth)}</p><dl class="support-values"><dt>${esc(t('investment.contributions'))}</dt><dd>${money(investment.total_contributions_cents)}</dd><dt>${esc(t('investment.withdrawals'))}</dt><dd>${money(investment.withdrawals_cents)}</dd><dt>${esc(t('investment.consistency'))}</dt><dd>${esc(t('investment.monthsCount',{count:investment.contribution_months,total:investment.period_months}))}</dd></dl>${investment.coverage_limited?`<p class="small-text">${esc(t('investment.coverageLimited',{count:investment.period_months}))}</p>`:''}${supportingEvidence(investment)}`;
}
function renderVat(){
  const vat=state.vat;
  if(!vat){$('vat-content').innerHTML=`<p class="empty-state">${esc(t('support.unavailable'))}</p>`;return;}
  const rates=(vat.by_rate||[]).map(row=>`<li>${esc(t('vat.rateRow',{rate:percentage(row.rate_basis_points),count:row.transaction_count,amount:money(row.estimated_vat_cents)}))}</li>`).join('');
  const limitations=(vat.limitations||[]).length?['vat.limitation.mixed','vat.limitation.ambiguous','vat.limitation.excise','vat.limitation.tax']:[];
  $('vat-content').innerHTML=`<p class="support-period">${dateLabel(vat.start)}–${dateLabel(vat.end)}</p><p class="support-amount">${esc(t('vat.amount',{amount:money(vat.estimated_vat_cents)}))}</p><dl class="support-values"><dt>${esc(t('vat.gross'))}</dt><dd>${money(vat.gross_spending_cents)}</dd><dt>${esc(t('vat.coverage'))}</dt><dd>${percentage(vat.coverage_basis_points)}</dd></dl><p class="small-text">${esc(t('vat.coverageNote'))}</p><details><summary>${esc(t('vat.breakdown'))}</summary><ul>${rates}</ul><p>${esc(t('vat.method'))}</p>${limitations.length?`<h3>${esc(t('vat.limitationsTitle'))}</h3><ul>${limitations.map(key=>`<li>${esc(t(key))}</li>`).join('')}</ul>`:''}</details>`;
}
async function createGoal(context=captureContext()) {
  assertCurrent(context);
  const candidate=state.pendingHandoff;
  const pending=candidate?.customerId===context.customerId&&candidate.generation===context.generation?candidate:null;
  let goalId=pending?.createdGoalId;
  if(!goalId){
    const result=await request(context,'post','/api/goals',{name:$('goal-name').value.trim(),template:$('goal-template').value,target_cents:eurosToCents($('goal-target').value),current_saved_cents:eurosToCents($('goal-saved').value),target_date:$('goal-date').value,reserve_floor_cents:eurosToCents($('goal-reserve').value),confirmed:true});
    const goal=result.goal||result;goalId=goal.goal_id||goal.id;
    if(!goalId)throw new Error('The saved goal reference is unavailable.');
    if(pending&&state.pendingHandoff===pending){pending.createdGoalId=goalId;renderHandoffProgress(pending);}
  }
  if(pending&&state.pendingHandoff===pending){
    if(!pending.linkComplete){
      // An interrupted response may hide a committed link. Read its state before retrying.
      if(pending.linkAttempted){
        const result=await request(context,'get','/api/goals');
        const goal=(result.goals||[]).find(item=>(item.goal_id||item.id)===goalId);
        if(goal&&(goal.linked_scenarios||[]).some(item=>(item.scenario_id||item.id)===pending.scenarioId)){
          pending.linkComplete=true;
          pending.hostAction={goal_ref:goalId,scenario_ref:pending.scenarioId,cents:goal.modeled_scenario_contribution_cents};
        }
      }
      if(!pending.linkComplete){
        pending.linkAttempted=true;
        const result=await request(context,'post','/api/goals/link',{goal_id:goalId,scenario_id:pending.scenarioId,confirmed:true});
        pending.linkComplete=true;pending.hostAction=result.host_action||null;
      }
      renderHandoffProgress(pending);
    }
    if(!pending.hostComplete){
      if(window.SCoachHost?.attach_modeled_contribution&&pending.hostAction){
        const action=pending.hostAction;
        await window.SCoachHost.attach_modeled_contribution(action.goal_ref,action.cents,action.scenario_ref);
        assertCurrent(context);
      }
      pending.hostComplete=true;
    }
  }
  // Keep acknowledged progress until the final refresh also succeeds.
  await loadGoals(context);assertCurrent(context);
  const linked=pending&&state.pendingHandoff===pending&&pending.linkComplete;
  clearHandoff();$('goal-name').value='';
  notify(t(linked?'feedback.linked':'feedback.goal'));
}
async function loadGoals(context=captureContext()){const response=await request(context,'get','/api/goals');state.goals=response.goals || (Array.isArray(response)?response:[]);renderGoals();}
function moneyMapEvidence(role=null) {
  const overview=state.overview;if(!overview)return null;
  const selected=role?(overview.flows||[]).find(flow=>flow.role===role):null,period=state.selectedMonth;
  return {kind:'money_map',customerId:state.customerId,accountId:overview.account_id,month:period,start:overview.start||period+'-01',end:overview.end||monthEnd(period),role,label:selected?flowName(role):t('evidence.allFlows'),amount_cents:selected?.amount_cents,fact_ids:[selected?.fact_id||overview.fact_id].filter(Boolean),transaction_refs:[...(selected?.transaction_refs||overview.transaction_refs||[])],flows:selected?null:overview.flows};
}
function restaurantEvidence(){return {kind:'restaurant',customerId:state.customerId,accountId:state.comparison?.account_id||state.overview?.account_id,month:state.selectedMonth,comparison:state.comparison,scenario:state.scenario,exclusion:state.exclusion,exclusionDetail:state.exclusionDetail||state.rows.find(row=>row.transaction_ref===state.exclusion)||null};}
function calculationHTML(context){
  if(!context)return `<p class="empty-state">${esc(t('support.unavailable'))}</p>`;
  const scope=`${esc(t('evidence.customer'))}: ${esc(context.customerId)}<br>${esc(t('common.account'))}: ${esc(context.accountId||'—')}`;
  const sources=(refs,facts)=>`<details class="evidence-group"><summary>${esc(t('evidence.refs',{count:refs.length}))}</summary><p>${esc(t('evidence.facts'))}: ${facts.map(esc).join(', ')||'—'}</p><ul>${refs.map(ref=>`<li><code>${esc(ref)}</code></li>`).join('')}</ul></details>`;
  if(context.kind==='money_map'){
    const label=context.role?flowName(context.role):context.label||t('evidence.allFlows');
    return `<div class="evidence-status"><strong>${esc(t('common.observed'))}</strong><p>${esc(t('evidence.mapIntro'))}</p></div><section class="evidence-group"><h3>${esc(t('evidence.scope'))}</h3><p>${scope}<br>${esc(t('common.period'))}: ${dateLabel(context.start)}–${dateLabel(context.end)}<br>${esc(t('evidence.filter'))}: ${esc(label)}</p></section><section class="evidence-group"><h3>${esc(label)}</h3>${context.amount_cents!==undefined?`<p>${esc(t('evidence.netFlow',{amount:money(context.amount_cents)}))}</p>`:(context.flows||[]).map(flow=>`<p>${esc(flowName(flow.role))}: ${money(flow.amount_cents)}</p>`).join('')}<details><summary>${esc(t('evidence.formula'))}</summary><p>${esc(t('evidence.mapFormula'))}</p></details></section>${sources(context.transaction_refs||[],context.fact_ids||[])}`;
  }
  if(context.kind==='restaurant'){
    const comparison=context.comparison,scenario=context.scenario,current=comparison?.current||comparison?.after,previous=comparison?.previous||comparison?.before;
    const refs=comparison?.transaction_refs||[...(previous?.transaction_refs||[]),...(current?.transaction_refs||[])];
    const contribution=scenario?.monthly_contribution_cents??scenario?.modeled_monthly_contribution_cents;
    const excluded=context.exclusionDetail?`${dateLabel(context.exclusionDetail.date)} · ${context.exclusionDetail.merchant_name||context.exclusionDetail.merchant||t('transactions.unknownMerchant')} · ${money(Math.abs(context.exclusionDetail.amount_cents))}`:context.exclusion?t('evidence.oneOffSaved'):t('evidence.none');
    return `<div class="evidence-status"><strong>${esc(t('common.observed'))}</strong><p>${esc(t('evidence.actual',{amount:money(current?.total_cents)}))}</p></div><section class="evidence-group"><h3>${esc(t('evidence.scope'))}</h3><p>${scope}<br>${esc(t('common.period'))}: ${dateLabel(current?.start)}–${dateLabel(current?.end)}<br>${esc(t('evidence.comparison'))}: ${dateLabel(previous?.start)}–${dateLabel(previous?.end)}<br>${esc(t('evidence.filter'))}: ${esc(t('category.restaurants'))}</p><p>${money(previous?.total_cents)} → ${money(current?.total_cents)}</p><details><summary>${esc(t('evidence.formula'))}</summary><p>${esc(t('evidence.averageFormula'))}</p></details></section>${sources(refs,[comparison?.fact_id].filter(Boolean))}<section class="evidence-group"><h3>${esc(t('common.estimate'))} · 20%</h3><p>${esc(t('evidence.scenarioFormula',{base:money(scenario?.adjustable_base_cents),amount:money(contribution)}))}</p><p>${esc(t('evidence.excluded'))}: <span title="${esc(context.exclusion||'')}">${esc(excluded)}</span><br>${esc(t('evidence.source'))}: ${esc(t(context.exclusion?'evidence.user':'evidence.deterministic'))}</p></section><details class="evidence-group"><summary>${esc(t('evidence.memory'))}</summary><p>${esc(t('evidence.memoryHelp'))}</p><p>${esc(t('evidence.host'))}</p></details>`;
  }
  if(context.kind==='transaction'){
    const row=context.row;
    const vat=vatEstimateFor(row.transaction_ref),vatLine=vat?`<br>${esc(vat.estimated_vat_cents===null?t('vat.unmapped'):t('vat.taxInside',{amount:money(vat.estimated_vat_cents),rate:percentage(vat.rate_basis_points)}))}<br>${esc(vatSourceLabel(vat))}<br><span title="${esc(vat.mapping_note||'')}">${esc(vatMappingLabel(vat))}</span>`:'';
    return `<section class="evidence-group"><h3>${esc(t('common.observed'))}</h3><p>${scope}<br>${money(row.amount_cents)} · ${dateLabel(row.date)}<br>${esc(row.category)}<br>${esc(row.merchant_name||row.merchant||t('transactions.unknownMerchant'))}<br>MCC: ${esc(row.mcc_code||t('transactions.unknown'))}${vatLine}<br><code>${esc(row.transaction_ref)}</code></p><p>${esc(t('evidence.host'))}</p></section>`;
  }
  if(context.kind==='goal'){
    const goal=context.goal;
    return `<section class="evidence-group"><h3>${esc(goal.name)} · ${esc(t('common.estimate'))}</h3><p>${scope}</p><p>${esc(t('goal.target'))}: ${money(goal.target_cents)}<br>${esc(t('goal.saved'))}: ${money(goal.current_saved_cents)}<br>${esc(t('goal.reserve'))}: ${money(goal.reserve_floor_cents)}</p><details><summary>${esc(t('evidence.formula'))}</summary><p>${esc(t('evidence.goalFormula'))}</p></details><p>${esc(t('evidence.noApproval'))}</p></section>`;
  }
  return `<p class="empty-state">${esc(t('support.unavailable'))}</p>`;
}
function showCalculation(context){if(!context||context.customerId!==state.customerId)return;state.calculationEvidence=context;$('calculation-content').innerHTML=calculationHTML(context);openDialog('calculation-dialog');}
function toolEvidenceHTML(response,result){
  const refs=result.transaction_refs||response.source_refs?.transaction_refs||[];
  const events=response.source_refs?.mortgage_event_refs||[];
  return `<details class="coach-tool-evidence"><summary>${esc(t('coach.result.evidence',{count:refs.length+events.length}))}</summary><p>${esc(t('evidence.facts'))}: <code>${esc(response.tool_fact_id||'—')}</code></p>${refs.length?`<ul>${refs.map(ref=>`<li><code>${esc(ref)}</code></li>`).join('')}</ul>`:''}${events.length?`<ul>${events.map(ref=>`<li><code>${esc(ref)}</code></li>`).join('')}</ul>`:''}</details>`;
}
function toolResultHTML(response){
  const result=response?.tool_result;if(!result)return '';
  if(response.tool_kind==='transaction_statistics'){
    const filter=Object.entries(result.filters||{}).map(([key,value])=>`${t(`coach.filter.${key}`)}: ${value}`).join(' · ')||t('coach.result.allActivity');
    const largest=result.largest_outflow;
    return `<section class="coach-tool-result"><span class="status-pill">${esc(t('common.observed'))}</span><h3>${esc(t('coach.result.statistics'))}</h3><p class="coach-result-amount">${money(result.outflow_total_cents)}</p><p class="small-text">${esc(filter)} · ${dateLabel(result.start)}–${dateLabel(result.end)}</p><dl class="coach-result-values"><dt>${esc(t('coach.result.count'))}</dt><dd>${esc(result.transaction_count)}</dd><dt>${esc(t('coach.result.average'))}</dt><dd>${money(result.average_outflow_cents)}</dd>${largest?`<dt>${esc(t('coach.result.largest'))}</dt><dd>${money(largest.amount_cents)} · ${dateLabel(largest.date)}</dd>`:''}</dl>${toolEvidenceHTML(response,result)}</section>`;
  }
  if(response.tool_kind==='transaction_statistics_comparison'){
    const current=result.current||{},comparison=result.comparison||{};
    return `<section class="coach-tool-result"><span class="status-pill">${esc(t('common.observed'))}</span><h3>${esc(t('coach.result.comparison'))}</h3><p class="coach-result-amount">${money(comparison.outflow_total_cents)} → ${money(current.outflow_total_cents)}</p><p>${esc(t('coach.result.delta',{amount:money(result.outflow_delta_cents)}))}</p>${toolEvidenceHTML(response,result)}</section>`;
  }
  if(response.tool_kind==='spending_adjustment_preview'){
    return `<section class="coach-tool-result"><span class="status-pill scenario-pill">${esc(t('coach.result.unsaved'))}</span><h3>${esc(t('coach.result.adjustment',{category:result.category,percent:result.percent}))}</h3><p class="coach-result-amount">${money(result.modeled_monthly_contribution_cents)} <small>${esc(t('common.perMonth'))}</small></p><dl class="coach-result-values"><dt>${esc(t('coach.result.actual'))}</dt><dd>${money(result.actual_total_cents)}</dd><dt>${esc(t('coach.result.base'))}</dt><dd>${money(result.adjustable_base_cents)}</dd></dl><p class="small-text">${esc(t('coach.result.noMutation'))}</p>${toolEvidenceHTML(response,result)}</section>`;
  }
  if(response.tool_kind==='three_basket_profile'){
    const baskets=(result.baskets||[]).map(row=>`<div><dt>${esc(flowName(row.role))}</dt><dd>${money(row.amount_cents)}</dd></div>`).join('');
    return `<section class="coach-tool-result"><span class="status-pill">${esc(t('common.observed'))}</span><h3>${esc(t('coach.result.profile'))}</h3><p class="small-text">${esc(monthLabel(result.period))} · ${esc(t('coach.result.noScore'))}</p><dl class="coach-baskets">${baskets}<div class="coach-total"><dt>${esc(t('coach.result.total'))}</dt><dd>${money(result.total_consumption_cents)}</dd></div></dl>${toolEvidenceHTML(response,result)}</section>`;
  }
  if(response.tool_kind==='safe_to_spend'){
    if(!result.available)return `<section class="coach-tool-result"><span class="status-pill scenario-pill">${esc(t('common.estimate'))}</span><h3>${esc(t('safe.title'))}</h3><p>${esc(t('support.needsHistory'))}</p>${toolEvidenceHTML(response,result)}</section>`;
    const assumptions=(result.assumptions||[]).slice(0,4).map((_item,index)=>`<li>${esc(t(`safe.assumption.${index}`))}</li>`).join('');
    return `<section class="coach-tool-result"><span class="status-pill scenario-pill">${esc(t('common.estimate'))}</span><h3>${esc(t('safe.title'))}</h3><p class="coach-result-amount">${money(result.safe_to_spend_cents)}</p><p class="small-text">${esc(t('safe.amount',{days:result.horizon_days}))} · ${esc(t('safe.horizon',{date:dateLabel(result.horizon_end)}))}</p><dl class="coach-result-values"><dt>${esc(t('safe.reserve'))}</dt><dd>${money(result.reserve_floor_cents)}</dd><dt>${esc(t('safe.obligations'))}</dt><dd>${money(result.scheduled_outflows_cents)}</dd><dt>${esc(t('safe.everydayAllowance'))}</dt><dd>${money(result.historical_flexible_buffer_cents)}</dd></dl>${assumptions?`<details class="coach-tool-evidence"><summary>${esc(t('evidence.assumptions'))}</summary><ul>${assumptions}</ul></details>`:''}${toolEvidenceHTML(response,result)}</section>`;
  }
  if(response.tool_kind==='observed_tax_evidence'){
    if(!result.available)return `<section class="coach-tool-result"><span class="status-pill">${esc(t('common.observed'))}</span><h3>${esc(t('coach.result.tax'))}</h3><p>${esc(t('coach.result.noExplicitTax'))}</p><p class="small-text">${esc(t('coach.result.missingTaxWarning'))}</p>${toolEvidenceHTML(response,result)}</section>`;
    return `<section class="coach-tool-result"><span class="status-pill">${esc(t('common.observed'))}</span><h3>${esc(t('coach.result.tax'))}</h3><p class="coach-result-amount">${money(result.observed_net_tax_cents)}</p><dl class="coach-result-values"><dt>${esc(t('coach.result.paid'))}</dt><dd>${money(result.observed_tax_paid_cents)}</dd><dt>${esc(t('coach.result.refunds'))}</dt><dd>${money(result.observed_tax_refund_cents)}</dd></dl>${toolEvidenceHTML(response,result)}</section>`;
  }
  return '';
}
function taxPlanHTML(result){
  return `<section class="coach-tool-result tax-plan-output"><span class="status-pill scenario-pill">${esc(t('coach.result.unsaved'))}</span><h4>${esc(t('taxPlan.resultTitle'))}</h4><p class="coach-result-amount">${money(result.required_monthly_set_aside_cents)} <small>${esc(t('common.perMonth'))}</small></p><dl class="coach-result-values"><dt>${esc(t('taxPlan.remaining'))}</dt><dd>${money(result.remaining_cents)}</dd><dt>${esc(t('taxPlan.due'))}</dt><dd>${dateLabel(result.due_date)}</dd><dt>${esc(t('taxPlan.reference'))}</dt><dd>${dateLabel(result.reference_date)}</dd><dt>${esc(t('taxPlan.balance'))}</dt><dd>${money(result.current_balance_cents)}</dd><dt>${esc(t('taxPlan.reserve'))}</dt><dd>${money(result.reserve_floor_cents)}</dd><dt>${esc(t('taxPlan.afterSetAside'))}</dt><dd>${money(result.available_after_full_set_aside_cents)}</dd></dl><p class="small-text">${esc(t('taxPlan.notAdvice'))}</p></section>`;
}
async function submitTaxPlan(context=captureContext()){
  assertCurrent(context);
  const result=await request(context,'post','/api/tax-plan',{amount_cents:eurosToCents($('tax-plan-amount').value),already_set_aside_cents:eurosToCents($('tax-plan-saved').value),set_aside_location:$('tax-plan-location').value,due_date:$('tax-plan-date').value,reference_date:state.overview?.latest_balance_date||state.observedEnd||monthEnd(context.month),current_balance_cents:state.overview?.latest_balance_cents,reserve_floor_cents:state.safeToSpend?.reserve_floor_cents??50000,confirmed:true});
  $('tax-plan-result').innerHTML=taxPlanHTML(result);
  return result;
}
async function askCoach(message,context=captureContext()){
  assertCurrent(context);text('coach-response',t('loading.coach'));
  try{
    const response=await request(context,'post','/api/coach',{message,month:context.month,locale:context.locale});
    if(context.locale!==i18n.locale)return;
    const content=response.explanation_blocks?.map(block=>block.text||'').join(' ')||t('home.genericDescription');
    text('coach-response',content);
    if(response.clarification_question)$('coach-response').append(document.createTextNode(' '+response.clarification_question));
    const toolHTML=toolResultHTML(response);if(toolHTML)$('coach-response').insertAdjacentHTML('beforeend',toolHTML);
    const action=document.createElement('button');action.className='text-button';let hasAction=true;
    if(response.tool_kind==='transaction_statistics'){action.textContent=t('coach.result.rows')+' ↗';action.onclick=()=>{closeDialogs();perform(action,next=>showTransactions(response.tool_result?.filters||{},next));};}
    else if(response.tool_kind==='spending_adjustment_preview'&&response.tool_result?.category==='Restaurants'){action.textContent=t('coach.result.exploreScenario')+' ↗';action.onclick=()=>{closeDialogs();perform(action,showStory);};}
    else if(response.tool_kind==='spending_adjustment_preview'){action.textContent=t('goal.form.title')+' ↗';action.onclick=()=>{closeDialogs();navigate('goals');$('goal-name').focus();};}
    else if(response.tool_kind==='three_basket_profile'){action.textContent=t('money.title')+' ↗';action.onclick=()=>{closeDialogs();navigate('home');$('money-title').scrollIntoView({block:'start'});};}
    else if(response.tool_kind==='observed_tax_evidence'){action.textContent=t('taxPlan.title')+' ↗';action.onclick=()=>{$('coach-tax').open=true;$('coach-tax').scrollIntoView({block:'start'});$('tax-plan-amount').focus();};}
    else if(response.intent==='preview_cashflow'||response.intent==='safe_to_spend'){action.textContent=t(response.intent==='safe_to_spend'?'safe.title':'forecast.title')+' ↗';action.onclick=()=>{closeDialogs();navigate('home');$(response.intent==='safe_to_spend'?'safe-title':'preview-title').scrollIntoView({block:'start'});};}
    else if(response.intent==='investment_cashflow'){action.textContent=t('investment.title')+' ↗';action.onclick=()=>{closeDialogs();navigate('trends');$('investment-title').scrollIntoView({block:'start'});};}
    else if(response.intent==='plan_goal'){action.textContent=t('goal.form.title')+' ↗';action.onclick=()=>{closeDialogs();navigate('goals');$('goal-name').focus();};}
    else if(response.intent==='home_financing_history'){action.textContent=t('coach.question.homeGoal')+' ↗';action.onclick=()=>{closeDialogs();navigate('goals');$('goal-template').value='home';$('goal-name').value=t('goal.template.home');$('goal-name').focus();};}
    else if(response.selected_candidate_id==='restaurant_change'){action.textContent=t('home.priority.open')+' ↗';action.onclick=()=>{closeDialogs();perform(action,showStory);};}
    else hasAction=false;
    if(hasAction){$('coach-response').append(document.createTextNode('\n'));$('coach-response').append(action);}
    text('coach-mode',t(response.source==='gemini'?'coach.aiMode':'coach.offlineMode'));
    $('coach-debug').hidden=false;text('coach-debug-content',`${t('coach.debug.source')}: ${response.source||'—'} · ${t('coach.debug.fallback')}: ${response.fallback_reason||t('coach.debug.none')} · ${t('coach.debug.tool')}: ${response.tool_source||response.tool_kind||'—'}`);
  }catch(error){if(isCurrent(context)&&context.locale===i18n.locale&&!(error instanceof StaleResponse))text('coach-response',errorText(error)+' '+t('coach.fallback'));}
}
function unavailableAccount(error){explainError(error);text('current-balance','—');text('account-caption',t('error.account'));$('current-balance').classList.remove('skeleton');$('money-flow').innerHTML=`<p class="empty-state">${esc(t('error.database'))}</p>`;text('insight-headline',t('error.account'));}
async function load(context=captureContext()){
  assertCurrent(context);const loadSequence=++state.loadSequence;notify(t('loading.account'));$('open-story').disabled=true;
  let initialOverview=null;
  if(!context.month){
    const [initial]=await Promise.allSettled([request(context,'get','/api/overview')]);
    if(!isCurrent(context)||loadSequence!==state.loadSequence)return;
    if(initial.status==='rejected'){unavailableAccount(initial.reason);renderSupport();return;}
    initialOverview=initial.value;context.month=initialOverview.month||initialOverview.latest_balance_date?.slice(0,7);
    state.selectedMonth=context.month;state.observedStart=initialOverview.observed_start;state.observedEnd=initialOverview.observed_end;
  }
  if(!context.month)return;
  const asOf=state.observedEnd&&monthEnd(context.month)>state.observedEnd?state.observedEnd:monthEnd(context.month);
  const results=await Promise.allSettled([
    initialOverview?Promise.resolve(initialOverview):request(context,'get','/api/overview',{month:context.month}),
    request(context,'get','/api/comparison',comparisonQuery(context.month)),
    request(context,'get','/api/trends',{month:context.month,months:context.trendMonths,category:'Restaurants'}),
    request(context,'get','/api/forecast',{as_of:asOf}),request(context,'get','/api/goals'),
    request(context,'get','/api/safe-to-spend',{as_of:asOf,days:7,reserve_floor_cents:50000}),
    request(context,'get','/api/investments',{month:context.month,months:context.trendMonths}),
    request(context,'get','/api/vat',{month:context.month})
  ]);
  if(!isCurrent(context)||loadSequence!==state.loadSequence)return;
  const [overview,comparison,trends,forecast,goals,safe,investments,vat]=results;
  state.comparison=comparison.status==='fulfilled'?normalizeComparison(comparison.value,context.month):null;
  if(overview.status==='fulfilled'){state.overview=overview.value;renderOverview();notify('');}else unavailableAccount(overview.reason);
  renderComparison();
  state.trends=trends.status==='fulfilled'?trends.value:null;renderTrends();
  state.forecast=forecast.status==='fulfilled'?forecast.value:null;state.forecastAssumptions={};renderForecast();
  state.goals=goals.status==='fulfilled'?(goals.value.goals||[]):[];renderGoals();
  state.safeToSpend=safe.status==='fulfilled'?safe.value:null;state.investments=investments.status==='fulfilled'?investments.value:null;state.vat=vat.status==='fulfilled'?vat.value:null;renderSupport();renderVat();
  const persisted=state.overview?.scenarios?.filter(item=>item.category==='Restaurants'&&(!item.start||item.start.slice(0,7)===context.month)).at(-1);
  state.scenario=persisted||null;state.exclusion=persisted?.excluded_transaction_refs?.[0]||null;renderScenario();
}
function changePeriod(selectedMonth,trendMonths=state.trendMonths){
  if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(selectedMonth)||!['3','6','12','24'].includes(String(trendMonths)))return explainError(new Error(t('error.period')));
  if((state.observedStart&&selectedMonth<state.observedStart.slice(0,7))||(state.observedEnd&&selectedMonth>state.observedEnd.slice(0,7)))return explainError(new Error(t('error.period')));
  const keep={customerId:state.customerId,selectedMonth,trendMonths:Number(trendMonths),observedStart:state.observedStart,observedEnd:state.observedEnd,generation:state.generation+1,loadSequence:state.loadSequence+1,view:state.view};
  Object.assign(state,createState(),keep);clearScopedViews();navigate(keep.view);load();
}
function applyLanguage(){
  document.documentElement.lang=i18n.locale;setFormattingLocale(i18n.localeTag);configureCharts({locale:i18n.localeTag,translate:t});$('language').value=i18n.locale;
  for(const node of document.querySelectorAll('[data-i18n]'))node.textContent=t(node.dataset.i18n);
  for(const node of document.querySelectorAll('[data-i18n-aria]'))node.setAttribute('aria-label',t(node.dataset.i18nAria));
  for(const node of document.querySelectorAll('[data-i18n-placeholder]'))node.setAttribute('placeholder',t(node.dataset.i18nPlaceholder));
  renderOverview();renderComparison();renderScenario();renderForecast();renderTrends();renderGoals();renderSupport();renderVat();
  const pending=state.pendingHandoff;
  if(pending){if(pending.createdGoalId)renderHandoffProgress(pending);else{text('goal-handoff',t('handoff.confirm',{amount:money(pending.contributionCents)}));text('goal-submit',t('handoff.submit',{amount:money(pending.contributionCents)})+' ↗');}}
  else clearHandoff();
  if(state.rows.length)renderRows(state.rows,state.transactionEvidence?.role?flowName(state.transactionEvidence.role):monthLabel(state.selectedMonth));
  if($('calculation-dialog').open&&state.calculationEvidence)$('calculation-content').innerHTML=calculationHTML(state.calculationEvidence);
}
$('persona-button').addEventListener('click',()=>{const panel=$('persona-panel');panel.hidden=!panel.hidden;$('persona-button').setAttribute('aria-expanded',String(!panel.hidden));if(!panel.hidden)$('persona').focus();});
$('persona').addEventListener('change',()=>{selectPersona(state,$('persona').value);api=createAPI(state.customerId);clearScopedViews();navigate('home');load();});
$('open-story').addEventListener('click',event=>perform(event.currentTarget,showStory));
$('show-transactions').addEventListener('click',event=>perform(event.currentTarget,context=>showTransactions({category:'Restaurants'},context)));
$('mark-one-off').addEventListener('click',event=>perform(event.currentTarget,markOneOff));
$('link-goal').addEventListener('click',()=>{
  const scenario=state.scenario;if(!scenario)return;
  const cents=scenario.monthly_contribution_cents??scenario.modeled_monthly_contribution_cents;
  if(!Number.isFinite(cents))return;
  closeDialogs();navigate('goals');
  state.pendingHandoff={customerId:state.customerId,generation:state.generation,scenarioId:scenario.scenario_id||scenario.id,contributionCents:cents,createdGoalId:null,linkAttempted:false,linkComplete:false,hostComplete:false,hostAction:null};
  text('goal-handoff',t('handoff.confirm',{amount:money(cents)}));
  text('goal-submit',t('handoff.submit',{amount:money(cents)})+' ↗');
  $('goal-name').focus();
});
$('goal-form').addEventListener('submit',event=>{event.preventDefault();perform(event.submitter,createGoal);});
$('goal-template').addEventListener('change',()=>{$('goal-name').value=$('goal-template').value==='custom'?'':t('goal.template.'+$('goal-template').value);});
$('ask-coach').addEventListener('click',()=>openDialog('coach-dialog'));
$('coach-form').addEventListener('submit',event=>{event.preventDefault();const message=$('coach-input').value.trim();if(message)perform(event.submitter,()=>askCoach(message));});
$('tax-plan-form').addEventListener('submit',event=>{event.preventDefault();perform(event.submitter,submitTaxPlan);});
$('undo-action').addEventListener('click',event=>perform(event.currentTarget,async context=>{await request(context,'post','/api/undo',{confirmed:true});state.scenario=null;state.exclusion=null;clearHandoff();await load(context);assertCurrent(context);if(!state.scenario)await ensureScenario(context);assertCurrent(context);renderScenario();notify(t('feedback.undo'));}));
$('reset-demo').addEventListener('click',event=>perform(event.currentTarget,async context=>{
  // Advance the reset owner's token; every overlapping request retains its old epoch.
  state.generation+=1;context.generation=state.generation;state.loadSequence+=1;
  await request(context,'post','/api/reset',{confirmed:true});
  const generation=state.generation+1,loadSequence=state.loadSequence+1;
  Object.assign(state,createState(),{customerId:context.customerId,generation,loadSequence,busy:true,selectedMonth:context.month,trendMonths:context.trendMonths,observedStart:state.observedStart,observedEnd:state.observedEnd});
  context.generation=generation;
  clearScopedViews({preserveLoading:true});
  await load(context);assertCurrent(context);
  notify(t('feedback.reset'));
}));
$('forecast-details').addEventListener('click',()=>{const panel=$('forecast-assumptions');panel.hidden=!panel.hidden;$('forecast-details').setAttribute('aria-expanded',String(!panel.hidden));});

document.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;
  if(button.dataset.view)navigate(button.dataset.view);
  if(button.dataset.coachQuestion)return perform(button,context=>askCoach(t(button.dataset.coachQuestion),context));
  if(button.dataset.goalTemplate!==undefined){closeDialogs();navigate('goals');const template=button.dataset.goalTemplate;$('goal-template').value=template;$('goal-name').value=template==='custom'?'':t('goal.template.'+template);$('goal-name').focus();return;}
  if(button.hasAttribute('data-open-vat')){closeDialogs();navigate('trends');$('vat-card').scrollIntoView({block:'start'});return;}
  if(button.id==='apply-preview')return perform(button,async context=>{const assumptions={};for(const fieldset of document.querySelectorAll('[data-assumption]')){const amountInput=fieldset.querySelector('[data-field=amount]').value;const amount=eurosToCents(amountInput.replace(/^-/,''))*(amountInput.startsWith('-')?-1:1);const day=Number(fieldset.querySelector('[data-field=day]').value);if(!Number.isFinite(amount)||!Number.isInteger(day)||day<1||day>31)throw new Error(t('error.assumption'));assumptions[fieldset.dataset.assumption]={enabled:fieldset.querySelector('[data-field=enabled]').checked,amount_cents:amount,median_day:day};}state.forecast=await request(context,'get','/api/forecast',{as_of:state.forecast?.as_of||monthEnd(context.month),assumptions:JSON.stringify(assumptions)});state.forecastAssumptions=assumptions;renderForecast();notify(t('feedback.preview'));});
  if(button.hasAttribute('data-close'))button.closest('dialog').close();
  if(button.dataset.action==='comparison')perform(button,showStory);
  if(button.dataset.action==='calculation')showCalculation(button.dataset.evidence==='money-map'?moneyMapEvidence(state.filter):button.dataset.evidence==='transactions'?state.transactionEvidence:restaurantEvidence());
  if(button.dataset.prompt)perform(button,context=>askCoach(t(button.dataset.prompt==='restaurants'?'coach.promptRestaurants':button.dataset.prompt==='future'?'coach.requestFuture':'coach.promptMonth'),context));
  if(button.dataset.role){const role=button.dataset.role;state.filter=role;document.querySelectorAll('[data-role]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));perform(button,context=>showTransactions({role},context));}
  if(button.dataset.transaction){
    if(window.SCoachHost?.open_transaction)window.SCoachHost.open_transaction(button.dataset.transaction);
    else {const row=state.rows.find(row=>row.transaction_ref===button.dataset.transaction);if(row)showCalculation({kind:'transaction',customerId:state.customerId,accountId:state.overview?.account_id,row});}
  }
  if(button.dataset.goalEvidence){const goal=state.goals.find(goal=>(goal.goal_id||goal.id)===button.dataset.goalEvidence);if(goal)showCalculation({kind:'goal',customerId:state.customerId,accountId:state.overview?.account_id,goal});}
});
// Native dialogs provide Escape, focus trapping and restoration to the opener.
for(const dialog of document.querySelectorAll('dialog')) dialog.addEventListener('click',event=>{if(event.target===dialog){const box=dialog.getBoundingClientRect();if(event.clientY<box.top||event.clientY>box.bottom||event.clientX<box.left||event.clientX>box.right)dialog.close();}});
$('language').addEventListener('change',()=>{const retry=Boolean($('status-message').querySelector('button'));i18n.setLocale($('language').value);text('coach-response','');text('coach-debug-content','');$('coach-debug').hidden=true;$('tax-plan-result').replaceChildren();notify(retry?t('error.generic'):'',retry);applyLanguage();});
$('selected-month').addEventListener('change',()=>changePeriod($('selected-month').value));
$('trend-range').addEventListener('change',()=>changePeriod(state.selectedMonth,Number($('trend-range').value)));
document.addEventListener('invalid',event=>event.target.setCustomValidity?.(t('error.validation')),true);
document.addEventListener('input',event=>event.target.setCustomValidity?.(''));
applyLanguage();
load();
