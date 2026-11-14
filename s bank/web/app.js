import { createAPI } from './api.js';
import { createState, selectPersona, money, escapeHTML as esc, dateLabel, eurosToCents, forecastRows } from './state.js';
import { flowChart, comparisonChart, trendChart, runwayChart, goalChart, palette } from './charts.js';

const state = createState();
let api = createAPI(state.customerId);
const $ = id => document.getElementById(id);
const text = (id, value) => { $(id).textContent = value; };
const month = '2026-09';
const comparisonQuery = {month, comparison_month:'2026-08', category:'Restaurants'};
const flowNames = {income:'Income',fixed_obligation:'Regular essentials',flexible_essential:'Irregular essentials',discretionary:'Everyday discretionary',saving_or_transfer:'Saving & transfers',needs_review:'Needs review'};
const personaNames = {CUST00001:'Everyday clarity',CUST00676:'Payday timing',CUST05097:'A big trip',CUST00756:'A salary step up',CUST00296:'A home in mind'};
class StaleResponse extends Error {}
const captureContext = () => ({customerId:state.customerId,api,generation:state.generation});
const isCurrent = context => context.customerId===state.customerId && context.api===api && context.generation===state.generation;
function assertCurrent(context){if(!isCurrent(context))throw new StaleResponse();}
async function request(context, method, path, values){
  assertCurrent(context);
  const result=await context.api[method](path,values);
  assertCurrent(context);
  return result;
}
const explainError = error => notify(error.message || 'Something went wrong. Please try again.', true);
function notify(message, retry=false) {
  let container=$('status-message');
  const active=Array.from(document.querySelectorAll('dialog[open]')).at(-1);
  if(active){
    container=active.querySelector('.dialog-notice');
    if(!container){container=document.createElement('p');container.className='status-message dialog-notice';container.setAttribute('role','status');container.setAttribute('aria-live','polite');active.querySelector('.sheet-content').prepend(container);}
  }
  container.replaceChildren(document.createTextNode(message));
  if(retry){const button=document.createElement('button');button.className='text-button';button.textContent='Try again';button.addEventListener('click',()=>load());container.append(button);}
}
async function perform(button, action) {
  if(state.busy) return;
  const context=captureContext();
  state.busy=true;
  const original=button?.textContent;
  if(button){button.dataset.loadingLabel=original;button.disabled=true;button.textContent='One moment…';}
  try { await action(context); }
  catch(error){if(isCurrent(context)&&!(error instanceof StaleResponse))explainError(error);}
  finally {if(isCurrent(context)){state.busy=false;if(button){button.disabled=false;if(button.textContent==='One moment…')button.textContent=original;delete button.dataset.loadingLabel;}}}
}
function openDialog(id) { const dialog=$(id); if(!dialog.open) dialog.showModal(); }
function closeDialogs(){document.querySelectorAll('dialog[open]').forEach(dialog=>dialog.close());}
function clearFilter(){state.filter=null;document.querySelectorAll('[data-role]').forEach(button=>button.setAttribute('aria-pressed','false'));}
function clearHandoff(){
  state.pendingHandoff=null;
  for(const id of ['goal-name','goal-template','goal-target','goal-saved','goal-date','goal-reserve'])$(id).disabled=false;
  text('goal-handoff','A trip, a buffer, something just for you.');
  text('goal-submit','Create my plan ↗');
}
function renderHandoffProgress(pending){
  if(state.pendingHandoff!==pending)return;
  const saved=Boolean(pending.createdGoalId);
  for(const id of ['goal-name','goal-template','goal-target','goal-saved','goal-date','goal-reserve'])$(id).disabled=saved;
  if(pending.linkComplete){
    text('goal-handoff',`Your goal and ${money(pending.contributionCents)} / month contribution are saved. Finish the S-mobiili handoff; no transfer is created.`);
    text('goal-submit','Finish goal handoff ↗');
  }else if(saved){
    text('goal-handoff',`Your goal is saved. Finish linking the ${money(pending.contributionCents)} / month modeled contribution to it.`);
    text('goal-submit',`Finish linking ${money(pending.contributionCents)} / month ↗`);
  }
}
function clearScopedViews({preserveLoading=false}={}){
  closeDialogs();clearFilter();clearHandoff();state.transactionEvidence=null;
  if(!preserveLoading)for(const button of document.querySelectorAll('[data-loading-label]')){button.disabled=false;button.textContent=button.dataset.loadingLabel;delete button.dataset.loadingLabel;}
  text('scenario-amount','—');text('scenario-detail','');text('coach-response','');text('transaction-summary','');
  $('transaction-list').replaceChildren();$('calculation-content').replaceChildren();
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
function normalizeComparison(data) {
  return {...data,before:{...data.previous,label:'August'},after:{...data.current,label:'September'}};
}
function renderComparison() {
  if(!state.comparison)return;
  const c=state.comparison;
  $('comparison-chart').innerHTML=comparisonChart(c);
  $('trend-comparison').innerHTML=comparisonChart(c);
  const countText=c.count_delta===0?'The same number of purchases.':`${c.count_delta>0?'+':''}${c.count_delta} purchases compared with August.`;
  const delta=c.delta_cents;
  text('story-description',`September ${delta>=0?'rose':'fell'} by ${money(Math.abs(delta))}. ${countText} The difference is in the average purchase size.`);
  $('comparison-decomposition').innerHTML=`<div class="decomposition"><div><p>Purchase count</p><strong>${esc(c.before.count)} → ${esc(c.after.count)}</strong><small>${c.count_delta===0?'Unchanged frequency':'Changed frequency'}</small></div><div><p>Average purchase</p><strong>${money(c.before.average_cents)} → ${money(c.after.average_cents)}</strong><small>Observed, per purchase</small></div></div>`;
  text('show-transactions',`See the ${c.after.count} September purchases ↗`);
  if(state.customerId==='CUST00001'){
    text('insight-headline',`Restaurant spending rose ${money(c.delta_cents)} in September.`);
    text('insight-description',`You went out the same number of times. A closer look can help you find a comfortable next step.`);
  }
}
function renderOverview() {
  const o=state.overview;
  text('current-balance',money(o.latest_balance_cents));$('current-balance').classList.remove('skeleton');
  text('account-caption',`${o.account_id || 'Demo account'} · Observed ${dateLabel(o.latest_balance_date || '2026-09-30')}`);
  const flows=(o.flows || []).map(row=>({...row,label:flowNames[row.role]||row.label||row.role,total_cents:Math.abs(row.amount_cents??row.total_cents??0)}));
  $('money-flow').innerHTML=flowChart(flows);$('money-flow').setAttribute('aria-busy','false');
  $('flow-legend').innerHTML=flows.map((row,i)=>`<button class="flow-filter" data-role="${esc(row.role)}" aria-pressed="false"><span class="flow-symbol" style="background:${palette[i%palette.length]};color:${i===0?'#fff':'#263825'}">${i+1}</span><span class="flow-text">${esc(row.label)}<strong>${money(row.total_cents)}</strong></span></button>`).join('');
  const candidate=o.priority || o.candidates?.[0];
  if(state.customerId!=='CUST00001'){
    text('insight-headline',candidate?.title || candidate?.headline || personaNames[state.customerId] || 'Your next useful insight');
    text('insight-description',candidate?.text || candidate?.description || candidate?.explanation || 'Explore the verified transactions behind your pattern, and choose the next step that fits your life.');
    text('open-story','Explore this pattern ↗');
  }else text('open-story','Take a closer look ↗');
  $('open-story').disabled=false;
  if(o.forecast){state.forecast=o.forecast;renderForecast();}
}
function renderScenario() {
  const result=state.scenario;
  if(!result)return;
  const contribution=result.contribution_cents ?? result.monthly_contribution_cents ?? result.savings_cents ?? result.modeled_savings_cents;
  $('scenario-amount').innerHTML=`${money(contribution)}<span>/ month</span>`;
  text('scenario-detail',`20% × ${money(result.adjustable_base_cents ?? result.base_cents)} repeatable spending. ${state.exclusion?'One-off purchase excluded from this scenario.':'All September restaurant purchases included.'}`);
  $('link-goal').disabled=!Number.isFinite(contribution);
  $('mark-one-off').hidden=Boolean(state.exclusion);
  $('exclusion-label').hidden=!state.exclusion;
  $('undo-action').disabled=!state.exclusion;
}
async function ensureScenario(context=captureContext()) {
  assertCurrent(context);
  if(state.scenario)return state.scenario;
  const result=await request(context,'post','/api/scenarios',{month,category:'Restaurants',percent:20,confirmed:true});
  state.scenario=result.scenario ?? result;
  renderScenario();
  return state.scenario;
}
async function showStory(context=captureContext()) {
  assertCurrent(context);clearFilter();
  if(state.customerId!=='CUST00001' && state.overview?.priority?.kind!=='category_change'){
    openDialog('coach-dialog');
    await askCoach('Explain my highest priority insight',context);
    return;
  }
  openDialog('story-dialog');
  if(!state.comparison){state.comparison=normalizeComparison(await request(context,'get','/api/comparison',comparisonQuery));renderComparison();}
  await ensureScenario(context);
}
async function fetchRows(filters={},context=captureContext()) {
  const result=await request(context,'get','/api/transactions',{month,...filters});
  return result.transactions || result.rows || [];
}
function renderRows(rows, title='September restaurant purchases') {
  state.rows=rows;
  text('transaction-summary',`${title} · ${rows.length} rows · Observed history`);
  $('transaction-list').innerHTML=rows.length?rows.map(row=>`<article class="transaction-row"><div><h3>${esc(row.merchant_name || row.merchant || 'Unknown merchant')}</h3><p>${dateLabel(row.date || row.timestamp)} · ${esc(row.category || 'Unknown category')}</p><p>${esc(row.literacy_label || flowNames[row.role] || 'Needs review')}</p>${row.transaction_ref===state.exclusion?'<span class="row-badge">You added this · scenario one-off</span>':''}<button class="text-button" data-transaction="${esc(row.transaction_ref)}">Open transaction detail ↗</button></div><strong>${money(Math.abs(row.amount_cents))}</strong></article>`).join(''):'<p class="empty-state">No transactions match this selection. Choose a different part of your Money Map.</p>';
}
async function showTransactions(filters={category:'Restaurants'},context=captureContext()) {
  assertCurrent(context);
  if(!filters.role)clearFilter();
  state.transactionEvidence=null;
  openDialog('transactions-dialog');
  $('transaction-list').innerHTML='<p class="empty-state" role="status">Loading the source rows…</p>';
  const rows=await fetchRows(filters,context);assertCurrent(context);
  state.transactionEvidence=filters.role?moneyMapEvidence(filters.role):restaurantEvidence();
  renderRows(rows,filters.role?flowNames[filters.role]:'September restaurant purchases');
}
async function markOneOff(context=captureContext()) {
  await ensureScenario(context);assertCurrent(context);
  const rows=await fetchRows({category:'Restaurants'},context);assertCurrent(context);
  const row=rows.find(row=>Math.abs(row.amount_cents)===3647);
  if(!row)throw new Error('The €36.47 row is not present in this account and period. No change was made.');
  const scenarioId=state.scenario.scenario_id || state.scenario.id;
  const result=await request(context,'post','/api/scenarios/exclude',{scenario_id:scenarioId,transaction_ref:row.transaction_ref,confirmed:true});
  state.scenario=result.scenario || result;
  state.exclusion=row.transaction_ref;
  renderScenario();
  notify('You added this: the one-off stays in actual spending and is excluded only from the 20% scenario.');
}
function renderForecast() {
  const f=state.forecast;
  const normalized=forecastRows(f);
  $('runway-chart').innerHTML=runwayChart(normalized);
  const assumptions=f?.assumptions || [];
  $('forecast-assumptions').innerHTML=`<p>Scenario only · Qualified recurring items, median amounts and dates. Flexible-spending variation reflects history, not confidence.</p>${(Array.isArray(assumptions)?assumptions:Object.entries(assumptions).map(([k,v])=>`${k}: ${v}`)).map(value=>`<p>• ${esc(typeof value==='string'?value:JSON.stringify(value))}</p>`).join('')}${(f?.recurring_items || []).map((item,i)=>`<fieldset class="assumption-inputs" data-assumption="${esc(item.id)}"><legend>${esc(item.category || item.transaction_type || item.role)}</legend><label for="assumption-enabled-${i}"><input id="assumption-enabled-${i}" type="checkbox" data-field="enabled" ${state.forecastAssumptions[item.id]?.enabled===false?'':'checked'}> Include in this preview</label><div class="form-grid"><div><label for="assumption-amount-${i}">Amount (€)</label><input id="assumption-amount-${i}" data-field="amount" type="number" step="0.01" value="${Number(state.forecastAssumptions[item.id]?.amount_cents ?? item.amount_cents ?? item.median_amount_cents ?? 0)/100}"></div><div><label for="assumption-day-${i}">Day of month</label><input id="assumption-day-${i}" data-field="day" type="number" min="1" max="31" value="${state.forecastAssumptions[item.id]?.median_day ?? item.median_day ?? 1}"></div></div></fieldset>`).join('')}<button class="secondary-button" id="apply-preview">Recalculate preview ↗</button><p>Edits apply only to this preview. They do not change your ledger or save a recurring rule.</p>`;
}
function renderTrends() {
  const t=state.trends;
  const rows=(t?.series || t?.months || t?.periods || []).filter(row=>row.available!==false && row.total_cents!==null);
  $('trend-chart').innerHTML=trendChart(rows);
  text('trend-description',rows.length?'Trailing complete months · Observed restaurant spending.':'There are not enough complete periods for this view yet.');
  $('trends-view').querySelector('.trend-facts')?.remove();
  if(t){
    const annual=t.annual_comparison;
    const evidence=`<section class="trend-facts"><h3>Same month, last year</h3><p>September change: ${money(t.year_over_year_delta_cents)}. Both periods are complete.</p><h3>Salary, on its own</h3><p>Recent three-month median: ${money(t.recent_three_salary_median_cents)}.<br>Prior six-month median: ${money(t.prior_six_salary_median_cents)}.</p><p>Other income stays separate from salary.</p>${annual?.available?`<details><summary>Compare two complete 12-month windows</summary>${comparisonChart({before:{...annual.previous,label:'Preceding 12 months'},after:{...annual.current,label:'Latest 12 months'}})}<p>${esc(annual.previous.start)}–${esc(annual.previous.end)} versus ${esc(annual.current.start)}–${esc(annual.current.end)}. Observed restaurants; no partial calendar years.</p></details>`:'<p>Two complete 12-month windows are not available yet.</p>'}<details><summary>Source & calculation</summary><p>Account: ${esc(t.account_id)}. Fact: <code>${esc(t.fact_id)}</code>. Totals sum the same selected restaurant rows; salary medians use salary only.</p><ul>${(t.transaction_refs||[]).map(ref=>`<li><code>${esc(ref)}</code></li>`).join('')}</ul></details></section>`;
    $('trend-chart').insertAdjacentHTML('afterend',evidence);
  }
}
function renderGoals() {
  $('goals-list').innerHTML=state.goals.length?state.goals.map(goal=>{
    const plan=goal.plan || goal;
    return `<article class="goal-card"><span class="status-pill scenario-pill">Planning scenario</span><h2>${esc(goal.name)}</h2><p class="subtle">By ${dateLabel(goal.target_date)} · Your chosen goal</p><p class="goal-amount">${money(plan.required_monthly_cents ?? plan.required_monthly_contribution_cents)}<span> required / month</span></p>${goalChart(goal.current_saved_cents??0,goal.target_cents)}<p class="small-text">Cautious monthly capacity: ${money(plan.conservative_monthly_contribution_cents)}. Based on six complete months of free cash flow.</p><p class="small-text">Protected reserve: ${money(goal.reserve_floor_cents)}. Available above that reserve: ${money(plan.upfront_available_cents)}, kept separate from monthly capacity.</p>${goal.modeled_scenario_contribution_cents>0?`<p class="small-text">${money(goal.modeled_scenario_contribution_cents)} modeled monthly contribution linked. No transfer created.</p>`:''}${plan.monthly_gap_cents>0?`<p class="small-text">Planning gap: ${money(plan.monthly_gap_cents)} / month. Try a later date or a smaller target.</p>`:''}<button class="text-button" data-goal-evidence="${esc(goal.goal_id || goal.id)}">See this plan's assumptions ↗</button></article>`;
  }).join(''):'<div class="goal-card"><span class="eyebrow">SOMETHING TO LOOK FORWARD TO</span><h2>What matters to you?</h2><p class="subtle">You choose the destination. We will help you explore a manageable pace.</p></div>';
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
  notify(linked?'Your modeled contribution is attached to your goal. No money has been moved.':'Your goal is saved. This is a planning scenario, with your reserve protected.');
}
async function loadGoals(context=captureContext()){const response=await request(context,'get','/api/goals');state.goals=response.goals || (Array.isArray(response)?response:[]);renderGoals();}
function moneyMapEvidence(role=null) {
  const overview=state.overview;
  if(!overview)return null;
  const selected=role?(overview.flows||[]).find(flow=>flow.role===role):null;
  return {kind:'money_map',customerId:state.customerId,accountId:overview.account_id,month:overview.month||month,start:overview.start||month+'-01',end:overview.end||month+'-30',label:selected?flowNames[role]:'All monthly money flows',amount_cents:selected?.amount_cents,fact_ids:[selected?.fact_id||overview.fact_id].filter(Boolean),transaction_refs:[...(selected?.transaction_refs||overview.transaction_refs||[])],flows:selected?null:overview.flows,latest_balance_cents:overview.latest_balance_cents};
}
function restaurantEvidence() {
  return {kind:'restaurant',customerId:state.customerId,accountId:state.comparison?.account_id||state.overview?.account_id,comparison:state.comparison,scenario:state.scenario,exclusion:state.exclusion};
}
function calculationHTML(context) {
  if(!context)return '<p class="empty-state">Choose a money flow or comparison to inspect its evidence.</p>';
  const scope=`Customer: ${esc(context.customerId)}<br>Account: ${esc(context.accountId||'Unavailable')}`;
  const sources=(refs,facts)=>`<section class="evidence-group"><h3>Same rows. Same numbers.</h3><p>Fact IDs: ${facts.map(esc).join(', ')||'Unavailable'}</p><details><summary>${refs.length} included source references</summary><ul>${refs.map(ref=>`<li><code>${esc(ref)}</code></li>`).join('')}</ul></details></section>`;
  if(context.kind==='money_map'){
    const flows=context.flows||[];
    return `<div class="evidence-status"><strong>Observed money flow</strong><p>Only the selected account, month and role are included in this evidence.</p></div><section class="evidence-group"><h3>Scope & period</h3><p>${scope}<br>Period: ${esc(context.start)}–${esc(context.end)}<br>Filter: ${esc(context.label)}<br>Status: Observed</p></section><section class="evidence-group"><h3>${esc(context.label)}</h3>${context.amount_cents!==undefined?`<p>Observed net flow: ${money(context.amount_cents)}. Negative amounts leave the account; positive amounts enter it.</p>`:flows.map(flow=>`<p>${esc(flowNames[flow.role]||flow.role)}: ${money(flow.amount_cents)}</p>`).join('')}<p>Formula: sum the signed source amounts matching this period and role. Income and saving/transfers remain separate from consumption. No restaurant scenario is applied to these rows.</p></section>${sources(context.transaction_refs||[],context.fact_ids||[])}`;
  }
  if(context.kind==='restaurant'){
    const comparison=context.comparison,scenario=context.scenario;
    const current=comparison?.current||comparison?.after,previous=comparison?.previous||comparison?.before;
    const refs=comparison?.transaction_refs||[...(previous?.transaction_refs||[]),...(current?.transaction_refs||[])];
    const contribution=scenario?.monthly_contribution_cents??scenario?.modeled_monthly_contribution_cents;
    return `<div class="evidence-status"><strong>Observed facts ≠ modeled scenarios</strong><p>Actual September restaurant spending: ${money(current?.total_cents)}. An exclusion never changes this history.</p></div><section class="evidence-group"><h3>Scope & periods</h3><p>${scope}<br>Current: ${esc(current?.start||'2026-09-01')}–${esc(current?.end||'2026-09-30')}<br>Comparison: ${esc(previous?.start||'2026-08-01')}–${esc(previous?.end||'2026-08-31')}<br>Filter: Restaurants<br>Status: Observed · Complete periods</p></section><section class="evidence-group"><h3>Comparison formula</h3><p>Totals sum the restaurant source rows in each period. Average purchase = period total / purchase count, rounded half up to the nearest cent. August: ${money(previous?.total_cents)}; September: ${money(current?.total_cents)}.</p></section>${sources(refs,[comparison?.fact_id].filter(Boolean))}<section class="evidence-group"><h3>20% planning scenario</h3><p>${money(scenario?.adjustable_base_cents)} × 20% = ${money(contribution)} / month, rounded half up to the nearest cent. This is a modeled contribution, never promised savings.</p><p>Excluded row: <code>${esc(context.exclusion||'None')}</code><br>Reason: ${context.exclusion?'One-off restaurant purchase':'No exclusion'}<br>Source: ${context.exclusion?'You added this · user-confirmed':'Deterministic scenario'}<br>Actuals remain unchanged.</p></section><section class="evidence-group"><h3>Coach memory & undo</h3><p>Confirmed changes are saved with an audit event. Undo appends a reversing event; reset restores seeded coach state.</p><p>Transaction detail and any real transfer belong to S-mobiili. This prototype has no private bank API access.</p></section>`;
  }
  if(context.kind==='transaction'){
    const row=context.row;
    return `<section class="evidence-group"><h3>Source transaction · Observed</h3><p>${scope}<br>${money(row.amount_cents)} · ${dateLabel(row.date)}<br>Original category: ${esc(row.category)}<br>Merchant: ${esc(row.merchant_name||row.merchant||'Unknown merchant')}<br>MCC: ${esc(row.mcc||'Unknown')}<br>Reference: <code>${esc(row.transaction_ref)}</code></p><p>In S-mobiili this opens the bank-owned transaction detail.</p></section>`;
  }
  if(context.kind==='goal'){
    const goal=context.goal;
    return `<section class="evidence-group"><h3>${esc(goal.name)} · Planning scenario</h3><p>${scope}</p><p>Remaining = max(target − already saved, 0). Required monthly contribution = remaining / months remaining, rounded upward to the next cent.</p><p>Conservative capacity is the lower quartile of six complete months of free cash flow. Investment transfers do not count as consumption or fresh goal capacity.</p><p>Target: ${money(goal.target_cents)}<br>Already saved: ${money(goal.current_saved_cents)}<br>Reserve: ${money(goal.reserve_floor_cents)}</p><p>Changing a goal creates no transfer and predicts no credit approval.</p></section>`;
  }
  return '<p class="empty-state">Evidence is unavailable for this selection.</p>';
}
function showCalculation(context){
  if(!context||context.customerId!==state.customerId)return;
  $('calculation-content').innerHTML=calculationHTML(context);openDialog('calculation-dialog');
}
async function askCoach(message,context=captureContext()) {
  assertCurrent(context);
  text('coach-response','Looking at your verified facts…');
  try {
    const response=await request(context,'post','/api/coach',{message,month});
    const blocks=response.explanation_blocks || response.explanations || [];
    const content=response.explanation || response.message || response.answer || blocks.map(block=>block.text || block.content || '').join(' ');
    text('coach-response',typeof content==='string'?content:'Your verified facts are ready. Open the comparison to explore the purchases behind the change.');
    if(response.clarification_question) $('coach-response').append(document.createTextNode(' '+response.clarification_question));
    const action=document.createElement('button');action.className='text-button';
    if(response.intent==='preview_cashflow') {action.textContent='Open your cash-flow preview ↗';action.onclick=()=>{closeDialogs();navigate('home');$('preview-title').scrollIntoView();};}
    else if(response.intent==='plan_goal'){action.textContent='Create your goal ↗';action.onclick=()=>{closeDialogs();navigate('goals');};}
    else {action.textContent='Explore the verified comparison ↗';action.onclick=()=>perform(action,showStory);}
    $('coach-response').append(action);
    text('coach-mode',`${response.source==='gemini'?'Gemini-assisted wording':'Deterministic offline coach'} · Numbers from verified facts · Changes require your confirmation`);
  }catch(error){if(isCurrent(context)&&!(error instanceof StaleResponse))text('coach-response',error.message+' You can still use the comparison, scenario controls and goals directly.');}
}
async function load(context=captureContext()) {
  assertCurrent(context);
  const loadSequence=++state.loadSequence;
  notify('Loading your verified account…');
  $('open-story').disabled=true;
  const results=await Promise.allSettled([
    request(context,'get','/api/overview',{month}),request(context,'get','/api/comparison',comparisonQuery),request(context,'get','/api/trends',{category:'Restaurants'}),request(context,'get','/api/forecast'),request(context,'get','/api/goals')
  ]);
  if(!isCurrent(context)||loadSequence!==state.loadSequence)return;
  const [overview,comparison,trends,forecast,goals]=results;
  if(overview.status==='fulfilled') {state.overview=overview.value;renderOverview();notify('');}
  else {explainError(overview.reason);text('current-balance','—');text('account-caption','Account unavailable');$('current-balance').classList.remove('skeleton');$('money-flow').innerHTML='<p class="empty-state">We cannot load this account yet. Retry when the demo database is ready.</p>';text('insight-headline','Your account needs a connection.');}
  if(comparison.status==='fulfilled'){state.comparison=normalizeComparison(comparison.value);renderComparison();}
  if(trends.status==='fulfilled')state.trends=trends.value;renderTrends();
  if(forecast.status==='fulfilled')state.forecast=forecast.value;renderForecast();
  if(goals.status==='fulfilled')state.goals=goals.value.goals || [];renderGoals();
  const persisted=state.overview?.scenario || state.overview?.scenarios?.filter(item=>item.category==='Restaurants').at(-1);
  if(persisted){state.scenario=persisted;state.exclusion=persisted.exclusions?.[0]?.transaction_ref || persisted.excluded_transaction_refs?.[0] || null;renderScenario();}
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
  text('goal-handoff',`${money(cents)} / month modeled from your restaurant scenario. Creating this plan will link that contribution. No transfer is created.`);
  text('goal-submit',`Create plan & link ${money(cents)} / month ↗`);
  $('goal-name').focus();
});
$('goal-form').addEventListener('submit',event=>{event.preventDefault();perform(event.submitter,createGoal);});
$('goal-template').addEventListener('change',()=>{const names={buffer:'My emergency buffer',trip:'My next adventure',vehicle:'My next vehicle',home:'My future home',purchase:'Something worth saving for',custom:''};$('goal-name').value=names[$('goal-template').value];});
$('ask-coach').addEventListener('click',()=>openDialog('coach-dialog'));
$('coach-form').addEventListener('submit',event=>{event.preventDefault();const message=$('coach-input').value.trim();if(message)perform(event.submitter,()=>askCoach(message));});
$('undo-action').addEventListener('click',event=>perform(event.currentTarget,async context=>{await request(context,'post','/api/undo',{confirmed:true});state.scenario=null;state.exclusion=null;clearHandoff();await load(context);assertCurrent(context);if(!state.scenario)await ensureScenario(context);assertCurrent(context);renderScenario();notify('Last change undone. Your actual history is unchanged.');}));
$('reset-demo').addEventListener('click',event=>perform(event.currentTarget,async context=>{
  // Advance the reset owner's token; every overlapping request retains its old epoch.
  state.generation+=1;context.generation=state.generation;state.loadSequence+=1;
  await request(context,'post','/api/reset',{confirmed:true});
  const generation=state.generation+1,loadSequence=state.loadSequence+1;
  Object.assign(state,createState(),{customerId:context.customerId,generation,loadSequence,busy:true});
  context.generation=generation;
  clearScopedViews({preserveLoading:true});
  await load(context);assertCurrent(context);
  notify('Demo reset. Seeded account history is ready to explore again.');
}));
$('forecast-details').addEventListener('click',()=>{const panel=$('forecast-assumptions');panel.hidden=!panel.hidden;$('forecast-details').setAttribute('aria-expanded',String(!panel.hidden));});

document.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;
  if(button.dataset.view)navigate(button.dataset.view);
  if(button.id==='apply-preview')return perform(button,async context=>{const assumptions={};for(const fieldset of document.querySelectorAll('[data-assumption]')){const amountInput=fieldset.querySelector('[data-field=amount]').value;const amount=eurosToCents(amountInput.replace(/^-/,''))*(amountInput.startsWith('-')?-1:1);const day=Number(fieldset.querySelector('[data-field=day]').value);if(!Number.isFinite(amount)||!Number.isInteger(day)||day<1||day>31)throw new Error('Use a valid amount and a day from 1 to 31.');assumptions[fieldset.dataset.assumption]={enabled:fieldset.querySelector('[data-field=enabled]').checked,amount_cents:amount,median_day:day};}state.forecast=await request(context,'get','/api/forecast',{assumptions:JSON.stringify(assumptions)});state.forecastAssumptions=assumptions;renderForecast();notify('Cash-flow preview recalculated. These edits are temporary scenario assumptions.');});
  if(button.hasAttribute('data-close'))button.closest('dialog').close();
  if(button.dataset.action==='comparison')perform(button,showStory);
  if(button.dataset.action==='calculation')showCalculation(button.dataset.evidence==='money-map'?moneyMapEvidence(state.filter):button.dataset.evidence==='transactions'?state.transactionEvidence:restaurantEvidence());
  if(button.dataset.prompt)perform(button,()=>askCoach(button.dataset.prompt));
  if(button.dataset.role){const role=button.dataset.role;state.filter=role;document.querySelectorAll('[data-role]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));perform(button,context=>showTransactions({role},context));}
  if(button.dataset.transaction){
    if(window.SCoachHost?.open_transaction)window.SCoachHost.open_transaction(button.dataset.transaction);
    else {const row=state.rows.find(row=>row.transaction_ref===button.dataset.transaction);if(row)showCalculation({kind:'transaction',customerId:state.customerId,accountId:state.overview?.account_id,row});}
  }
  if(button.dataset.goalEvidence){const goal=state.goals.find(goal=>(goal.goal_id||goal.id)===button.dataset.goalEvidence);if(goal)showCalculation({kind:'goal',customerId:state.customerId,accountId:state.overview?.account_id,goal});}
});
// Native dialogs provide Escape, focus trapping and restoration to the opener.
for(const dialog of document.querySelectorAll('dialog')) dialog.addEventListener('click',event=>{if(event.target===dialog){const box=dialog.getBoundingClientRect();if(event.clientY<box.top||event.clientY>box.bottom||event.clientX<box.left||event.clientX>box.right)dialog.close();}});
const targetDate=new Date('2027-03-31T12:00:00');$('goal-date').value=targetDate.toISOString().slice(0,10);$('goal-date').min='2026-10-01';
load();
