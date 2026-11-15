import { createAPI } from './api.js';
import { createState, selectPersona, money, escapeHTML as esc, dateLabel, eurosToCents, forecastRows, setFormattingLocale, shiftMonth, monthEnd, monthLabel } from './state.js';
import { comparisonChart, trendChart, runwayChart, barChart, goalChart, configureCharts, spendingRing, categoryPalette, categoryIcon } from './charts.js';
import { createI18n } from './i18n.js';
import { createExperienceStore, suggestedMemory, ux, buildJournal } from './experience.js';
import { spendingCategories, forecastSummary, toolScope, milestoneFor } from './presentation.js';
import { coachNarrative } from './coach-narrative.js';
import { agentTurnHTML } from './coach-chat.js';
import { createMonthlyRecapCache, monthlyRecapPrompt, recapTiles } from './monthly-recap.js';
import { initV3 } from './v3.js';

const state = createState();
let api = createAPI(state.customerId);
const $ = id => document.getElementById(id);
const text = (id, value) => { $(id).textContent = value; };
const i18n=createI18n();
const t=(key,values)=>i18n.t(key,values);
const u=(key,values)=>ux(i18n.locale,key,values);
const copy=(en,fi,sv)=>({en,fi,sv}[i18n.locale]||en);
const names={CUST00001:'Alex',CUST00676:'Robin',CUST05097:'Sam',CUST00756:'Jules',CUST00296:'Taylor',CUST01331:'Kai'};
const categoryName=category=>{const label=u('category.'+category);return label==='category.'+category?category:label;};
const experienceStores=new Map();
let localStore=null;try{localStore=globalThis.localStorage||null;}catch{}
function experience(){if(!experienceStores.has(state.customerId))experienceStores.set(state.customerId,createExperienceStore(localStore,state.customerId));return experienceStores.get(state.customerId);}
const evidenceRegistry=new Map();let evidenceSequence=0;
let memoryProposal=null, noteEditing=null, tourStep=0, coachSequence=0;
let coachPending=null, coachTimer=null, agentProposal=null, actionSequence=0;
const monthlyRecaps=createMonthlyRecapCache(),recapPrevious=new Map();
let homeRecap=null,homeDataState='loading',v3=null;
function sourceButton(refs=[],scope={}){
  if(!refs.length)return '';
  const key='source-'+(++evidenceSequence);
  evidenceRegistry.set(key,{customerId:state.customerId,generation:state.generation,refs:[...refs],...scope});
  return `<button type="button" class="text-button" data-evidence-rows="${key}">${esc(u('spending.rows',{count:refs.length}))} ↗</button>`;
}
function personalStatus(){const store=experience();return u(store.load().consent?(store.isPersisted()?'personal.stored':'personal.storageUnavailable'):'personal.session');}
const flowKeys={income:'money.income',fixed_obligation:'basket.regular',flexible_essential:'basket.irregular',discretionary:'basket.everyday',saving_or_transfer:'basket.saving',needs_review:'basket.review'};
const flowHelp={income:'basket.income.help',fixed_obligation:'basket.regular.help',flexible_essential:'basket.irregular.help',discretionary:'basket.everyday.help',saving_or_transfer:'basket.saving.help',needs_review:'basket.review.help'};
const flowName=role=>t(flowKeys[role]||'basket.review');
function filterSummary(filters={},concept=null){
  const types={salary:copy('Salary','Palkka','Lön'),other_income:copy('Other income','Muut tulot','Övriga inkomster'),purchase:copy('Purchases','Ostokset','Köp'),housing_payment:copy('Housing payments','Asumismaksut','Boendebetalningar'),utilities_payment:copy('Bills','Laskut','Räkningar'),investment_deposit:copy('Investment deposits','Sijoitussiirrot','Insättningar till investeringar'),investment_withdrawal:copy('Investment withdrawals','Sijoitusnostot','Uttag från investeringar')};
  return Object.entries(filters).map(([key,value])=>key==='category'?categoryName(value):key==='role'?flowName(value):key==='consumption_only'?u('spending.all'):key==='transaction_type'?(types[value]||copy('Selected payment type','Valittu maksutyyppi','Vald betalningstyp')):key==='mcc_code'?(concept||copy('Selected merchant type','Valittu kauppiastyyppi','Vald handlartyp')):copy('Selected merchant','Valittu kauppias','Vald handlare')).join(' · ');
}
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
  const operation=++actionSequence;
  const context=captureContext();
  state.busy=true;
  const original=button?.textContent;
  if(button){button.dataset.loadingLabel=original;button.disabled=true;button.textContent=t('loading.action');}
  try { await action(context); }
  catch(error){if(isCurrent(context)&&!(error instanceof StaleResponse))explainError(error);}
  finally {if(isCurrent(context)&&operation===actionSequence){state.busy=false;if(button){button.disabled=false;if(button.dataset.loadingLabel&&button.textContent===t('loading.action'))button.textContent=original;delete button.dataset.loadingLabel;}}}
}
function openDialog(id) {
  if(id==='coach-dialog'){closeDialogs();navigate('coach');$('coach-input').focus();return;}
  const dialog=$(id); if(!dialog.open) dialog.showModal();
}
function closeDialogs(){document.querySelectorAll('dialog[open]').forEach(dialog=>dialog.close());}
function clearFilter(){state.filter=null;document.querySelectorAll('[data-role]').forEach(button=>button.setAttribute('aria-pressed','false'));}
function clearHandoff(){
  state.pendingHandoff=null;
  for(const id of ['goal-name','goal-template','goal-target','goal-saved','goal-date','goal-reserve'])$(id).disabled=false;
  text('goal-handoff',t('goal.intro'));
  text('goal-submit',t('goal.create')+' ↗');
}
function beginGoalHandoff(scenario,template=null){
  const cents=scenario?.monthly_contribution_cents??scenario?.modeled_monthly_contribution_cents;
  if(!Number.isFinite(cents))return;
  closeDialogs();navigate('goals');state.scenario=scenario;
  state.pendingHandoff={customerId:state.customerId,generation:state.generation,scenarioId:scenario.scenario_id||scenario.id,contributionCents:cents,createdGoalId:null,linkAttempted:false,linkComplete:false,hostComplete:false,hostAction:null};
  if(template){$('goal-template').value=template;$('goal-name').value=template==='custom'?'':t('goal.template.'+template);}
  $('goal-planner').open=true;
  text('goal-handoff',t('handoff.confirm',{amount:money(cents)}));text('goal-submit',t('handoff.submit',{amount:money(cents)})+' ↗');$('goal-name').focus();
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
  clearCoachPending(true);agentProposal=null;v3?.reset();
  homeRecap=null;homeDataState='loading';
  closeDialogs();clearFilter();clearHandoff();state.transactionEvidence=null;
  state.queryScope=null;state.conversation=[];memoryProposal=null;evidenceRegistry.clear();coachSequence++;
  if(!preserveLoading)for(const button of document.querySelectorAll('[data-loading-label]')){button.disabled=false;button.textContent=button.dataset.loadingLabel;delete button.dataset.loadingLabel;}
  text('scenario-amount','—');text('scenario-detail','');text('coach-response','');text('transaction-summary','');
  $('transaction-list').replaceChildren();$('calculation-content').replaceChildren();
  text('coach-debug-content','');$('coach-debug').hidden=true;$('tax-plan-result').replaceChildren();
  $('coach-home-history').hidden=true;
  text('coach-live-status','');$('coach-response').setAttribute('aria-busy','false');
  $('coach-input').value='';
  $('wish-title').value='';$('wish-title').dataset.template='custom';
  $('goal-name').value='';$('goal-target').value='';$('goal-date').value='';$('goal-saved').value='0';$('goal-reserve').value='500';
  $('tax-plan-amount').value='';$('tax-plan-saved').value='0';$('tax-plan-date').value='';$('tax-plan-location').value='inside_current_balance';
  $('mark-one-off').hidden=false;$('undo-action').disabled=true;$('link-goal').disabled=true;
  // Clear rendered account data before any request for the new scope can fail.
  text('current-balance','—');text('account-caption',t('loading.account'));text('balance-date-caption','');
  $('balance-month-summary').replaceChildren();$('flow-legend').replaceChildren();$('money-flow').replaceChildren();
  renderMonthlyRecap();
  renderComparison();renderForecast();renderTrends();renderGoals();renderSupport();renderVat();renderSpending();
}
function navigate(view) {
  if(!['home','trends','coach','goals','journal','profile'].includes(view))view='home';
  clearFilter();clearHandoff();
  state.view=view;
  document.documentElement.setAttribute('data-current-view',view);
  for(const name of ['home','trends','coach','goals','journal','profile']) $(name+'-view').hidden=name!==view;
  $('persona-panel').hidden=true;$('persona-button').setAttribute('aria-expanded','false');
  if(view==='journal')renderPersonalization();
  if(view==='goals')renderWishes();
  renderCoachContext();
  document.querySelectorAll('[data-view]').forEach(button=>{if(button.dataset.view===view)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});
  window.scrollTo({top:0,behavior:'instant'});
  $('main-content').focus({preventScroll:true});
  if(view==='home')refreshMonthlyRecap();
  v3?.onNavigate(view);
}
function renderMonthlyRecap(){
  const ready=homeDataState==='ready'&&state.overview;
  const active=ready&&homeRecap&&isCurrent(homeRecap.context)&&homeRecap.context.month===state.selectedMonth&&homeRecap.context.locale===i18n.locale?homeRecap.entry:null;
  const result=active?.result,overview=state.overview,facts=[];
  const period=state.selectedMonth?monthLabel(state.selectedMonth):t('loading.account');
  text('priority-title',t('home.recap.label'));text('insight-headline',t('home.recap.title',{period}));
  if(ready){
    if(Number.isSafeInteger(overview.salary_cents)&&Number.isSafeInteger(overview.other_income_cents))facts.push(t('home.recap.income',{amount:money(overview.salary_cents+overview.other_income_cents)}));
    if(Number.isSafeInteger(overview.consumption_cents))facts.push(t('home.recap.spending',{amount:money(overview.consumption_cents)}));
    if(Number.isSafeInteger(overview.committed_saving_transfers_cents))facts.push(t('home.recap.saving',{amount:money(overview.committed_saving_transfers_cents)}));
  }
  const lines=result?.lines;
  $('insight-description').innerHTML=lines?`<strong class="recap-lead">${esc(lines.headline)}</strong><span class="recap-line recap-good"><b>${esc(t('v3.recap.good'))}</b> ${esc(lines.good)}</span><span class="recap-line recap-watch"><b>${esc(t('v3.recap.watch'))}</b> ${esc(lines.watch)}</span>`:esc(result?.text||(ready?(facts.join(' ')||t('home.recap.noFacts')):t(homeDataState==='loading'?'loading.account':'home.recap.unavailable')));
  renderRecapTiles(ready?overview:null);
  text('home-recap-status',ready?t(active?.pending?'home.recap.pending':result?'home.recap.ai':'home.recap.recorded'):'');
  $('home-coach-card').setAttribute('aria-busy',String(Boolean(active?.pending)));
  text('open-story',t('home.recap.open')+' ↗');$('open-story').disabled=!ready;
  const profile=experience().load(),protectedCategory=profile.protected_category;
  const alternative=spendingCategories(state.categoryRows||[]).find(row=>['Restaurants','Lifestyle','Entertainment','Travel'].includes(row.category)&&row.category!==protectedCategory&&!(profile.focus==='travel'&&row.category==='Travel'));
  const question=protectedCategory==='Restaurants'&&alternative?`${copy('Show my spending on','Näytä menoni luokassa','Visa mina utgifter för')} ${alternative.category}`:profile.focus==='buffer'?t('coach.question.safe'):protectedCategory==='none'&&result?.question?result.question:t('home.recap.followup',{period});
  const starter=$('home-coach-question');starter.dataset.directQuestion=question;starter.textContent=question+' ↗';starter.disabled=!ready;
}
function renderRecapTiles(overview){
  const node=$('recap-tiles');if(!node)return;
  if(!overview){node.innerHTML='';return;}
  const previousMonth=state.selectedMonth?shiftMonth(state.selectedMonth,-1):null;
  const previous=recapPrevious.get(state.customerId+'|'+previousMonth)||null;
  node.innerHTML=recapTiles(overview,previous).map(tile=>{
    const delta=tile.delta_cents,direction=delta>0?'up':delta<0?'down':'same';
    const change=delta===null?'':`<small class="recap-delta recap-${direction}">${direction==='up'?'▲':direction==='down'?'▼':'＝'} ${esc(delta===0?t('v3.recap.same'):t('v3.recap.vs',{amount:money(Math.abs(delta)),month:monthLabel(previousMonth)}))}</small>`;
    return `<div class="recap-tile"><span>${esc(t('v3.recap.'+tile.key))}</span><strong>${money(tile.cents)}</strong>${change}</div>`;
  }).join('');
}
function loadPreviousOverview(context){
  if(!context.month||!state.observedStart)return;
  const previousMonth=shiftMonth(context.month,-1),key=context.customerId+'|'+previousMonth;
  if(recapPrevious.has(key)||previousMonth<state.observedStart.slice(0,7))return;
  recapPrevious.set(key,null);
  request(context,'get','/api/overview',{month:previousMonth}).then(data=>{recapPrevious.set(key,data);if(state.view==='home'&&isCurrent(context))renderRecapTiles(state.overview);}).catch(()=>{recapPrevious.delete(key);});
}
function refreshMonthlyRecap(){
  if(homeDataState!=='ready'||!state.overview||state.view!=='home'){renderMonthlyRecap();return;}
  const context=captureContext(),key=JSON.stringify([context.customerId,context.month,context.locale,state.overview]);
  loadPreviousOverview(context);
  const entry=monthlyRecaps.get(key,()=>context.api.agent(monthlyRecapPrompt(context.month,context.locale),{month:context.month,locale:context.locale,conversation:[]}));
  if(homeRecap?.entry===entry&&isCurrent(homeRecap.context)&&homeRecap.context.locale===context.locale){renderMonthlyRecap();return;}
  const current={context,entry};homeRecap=current;renderMonthlyRecap();
  entry.promise.then(()=>{if(homeRecap===current&&isCurrent(context)&&context.locale===i18n.locale)renderMonthlyRecap();});
}
function renderCoachContext(){
  const period=state.selectedMonth?monthLabel(state.selectedMonth):copy('Loading records','Ladataan tietoja','Läser in uppgifter');
  text('app-data-context',`${copy('Synthetic demo','Synteettinen demo','Syntetisk demo')} · ${names[state.customerId]} · ${period}`);
  text('coach-scope-button',`${names[state.customerId]} · ${period}`);
  $('coach-month').innerHTML=$('selected-month').innerHTML;$('coach-month').value=state.selectedMonth||'';
  $('coach-scope').innerHTML=`<strong>${esc(names[state.customerId]||'')} · ${esc(period)}</strong><p class="small-text">${esc(copy('One recorded account. Other accounts and household finances are not included.','Yksi kirjattu tili. Muut tilit ja kotitalouden talous eivät sisälly tietoihin.','Ett registrerat konto. Andra konton och hushållets ekonomi ingår inte.'))}</p>${state.overview?.latest_balance_date?`<p class="small-text">${esc(copy('Latest balance record','Viimeisin saldotieto','Senaste saldouppgift'))}: ${dateLabel(state.overview.latest_balance_date)}</p>`:''}`;
  $('coach-empty').hidden=state.conversation.length>0||Boolean(coachPending);
}
// The customer's own top two categories in a basket, so each basket is concrete.
function basketExamples(role){
  const totals=new Map();
  for(const row of state.categoryRows||[]){
    if(row.role!==role||!(row.amount_cents<0)||!['purchase','utilities_payment','housing_payment'].includes(row.transaction_type))continue;
    totals.set(row.category,(totals.get(row.category)||0)-row.amount_cents);
  }
  return [...totals].sort((a,b)=>b[1]-a[1]).slice(0,2).map(([category,cents])=>`${categoryName(category)} ${money(cents)}`).join(' · ');
}
function renderHomeSnapshot(){
  const rows=(state.overview?.flows||[]).filter(row=>['fixed_obligation','flexible_essential','discretionary','needs_review'].includes(row.role));
  const total=rows.reduce((sum,row)=>sum+Math.abs(row.amount_cents||0),0);
  $('home-baskets-content').innerHTML=total?`<p class="monthly-total">${money(total)} <span>${esc(copy('spent','käytetty','spenderat'))} · ${esc(monthLabel(state.selectedMonth))}</span></p><div class="basket-strip" aria-hidden="true">${rows.filter(row=>row.amount_cents).map((row,i)=>`<span style="flex:${Math.abs(row.amount_cents)};background:${['#286f56','#90a7a5','#d6b17d','#b2a8bc'][i]}"></span>`).join('')}</div>${rows.map((row,i)=>{const examples=basketExamples(row.role);return `<button class="basket-summary-row" type="button" data-role="${esc(row.role)}"><span><i style="background:${['#286f56','#90a7a5','#d6b17d','#b2a8bc'][i]}" aria-hidden="true"></i><span class="basket-text"><b>${esc(flowName(row.role))}</b>${flowHelp[row.role]?`<small class="basket-help">${esc(t(flowHelp[row.role]))}</small>`:''}${examples?`<small class="basket-examples">${esc(t('v3.basketExamples',{items:examples}))}</small>`:''}</span></span><strong>${money(Math.abs(row.amount_cents||0))}</strong></button>`;}).join('')}`:`<p class="empty-state">${esc(state.overview?t('empty.transactions'):t('loading.account'))}</p>`;
  const wishes=experience().load().wishes||[],goal=state.goals[0];
  $('home-goal-content').innerHTML=goal?`<p class="goal-summary-name">${esc(goal.name)}</p><p>${money(goal.current_saved_cents??0)} / ${money(goal.target_cents)}</p><p class="small-text">${esc(copy('Saved amount you entered','Itse ilmoittamasi säästö','Sparbeloppet du angett'))}</p>`:wishes.length?`<p class="goal-summary-name">${esc(wishes.at(-1).title)}</p><p class="small-text">${esc(copy('A direction to explore. No deadline needed yet.','Tutkittava suunta. Määräaikaa ei vielä tarvita.','En riktning att utforska. Inget datum behövs än.'))}</p>`:`<p class="subtle">${esc(t('v2.goals.help'))}</p>`;
  renderCoachContext();
}
function renderWishes(){
  const profile=experience().load(),wishes=profile.wishes||[];
  $('wish-remember').checked=profile.consent;$('wish-remember').disabled=profile.consent;text('wish-storage',personalStatus());
  $('wishes-list').innerHTML=wishes.length?wishes.map(wish=>`<article class="wish-card"><span class="eyebrow">${esc(copy('Exploring','Tutkitaan','Utforskar'))}</span><h2>${esc(wish.title)}</h2><p class="small-text">${esc(copy('No target or deadline set. Start whenever you are ready.','Ei tavoitesummaa tai määräaikaa. Aloita, kun olet valmis.','Inget belopp eller datum bestämt. Börja när du är redo.'))}</p>${Number.isSafeInteger(wish.contribution_cents)?`<p>${money(wish.contribution_cents)} / ${esc(t('common.perMonth'))} · ${esc(t('common.estimate'))}</p>`:''}<div class="personal-actions"><button class="text-button" type="button" data-wish-explore="${esc(wish.id)}">${esc(copy('Explore with coach','Tutki valmentajan kanssa','Utforska med coachen'))} ↗</button><button class="text-button" type="button" data-wish-plan="${esc(wish.id)}">${esc(t('v2.goal.calculate'))}</button><button class="text-button" type="button" data-wish-delete="${esc(wish.id)}">${esc(copy('Remove','Poista','Ta bort'))}</button></div></article>`).join(''):`<div class="wish-empty"><span aria-hidden="true">✦</span><p>${esc(copy('Your possibilities can start small.','Mahdollisuutesi voivat alkaa pienestä.','Dina möjligheter kan börja smått.'))}</p></div>`;
  renderHomeSnapshot();
}
async function openDemoStory(kind){
  const stories={kai:['CUST01331','coach.question.safe'],alex:['CUST00001','coach.promptRestaurants'],taylor:['CUST00296','coach.question.homeHistory']};
  const selected=stories[kind];if(!selected)return;
  closeDialogs();selectPersona(state,selected[0]);api=createAPI(state.customerId);clearScopedViews();$('persona').value=selected[0];state.selectedMonth='2026-09';
  const context=captureContext(),sequence=coachSequence;
  await load(context);
  if(!isCurrent(context)||context.locale!==i18n.locale||sequence!==coachSequence)return;
  navigate('coach');await askCoach(t(selected[1]),context);
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
  text('balance-title',copy('Last recorded balance','Viimeisin kirjattu saldo','Senaste registrerade saldo'));
  text('balance-date-caption',`${copy('Recorded','Kirjattu','Registrerat')} ${dateLabel(o.latest_balance_date)}`);
  $('balance-month-summary').innerHTML=`<div><span>${esc(t('money.income'))}</span><strong>${money((o.salary_cents||0)+(o.other_income_cents||0))}</strong></div><div><span>${esc(copy('To savings','Säästöihin','Till sparande'))}</span><strong>${money(o.committed_saving_transfers_cents||0)}</strong></div>`;
  text('account-caption',`${o.account_id||t('common.account')} · ${t('common.observed')} ${dateLabel(o.latest_balance_date)}`);
  $('money-flow').innerHTML='';$('money-flow').setAttribute('aria-busy','false');
  const flows=(o.flows||[]).filter(row=>row.role!=='needs_review'||row.transaction_refs?.length||row.amount_cents);
  $('flow-legend').innerHTML=flows.map(row=>`<button class="flow-filter" data-role="${esc(row.role)}" aria-pressed="${state.filter===row.role}"><span>${esc(flowName(row.role))}</span><strong>${money(row.role==='saving_or_transfer'?row.amount_cents:Math.abs(row.amount_cents))}<span class="flow-arrow" aria-hidden="true">↗</span></strong><span class="flow-help">${esc(t(flowHelp[row.role]||'basket.review.help'))}</span></button>`).join('');
  $('coach-home-history').hidden=!(o.candidates||[]).some(item=>item.kind==='home_financing_history');
  const taxReference=o.latest_balance_date||state.observedEnd;
  if(taxReference){$('tax-plan-date').min=shiftMonth(taxReference.slice(0,7),1)+'-01';if(!$('tax-plan-date').value)$('tax-plan-date').value=monthEnd(shiftMonth(taxReference.slice(0,7),6));}
  if(state.observedEnd)$('goal-date').min=shiftMonth(state.observedEnd.slice(0,7),1)+'-01';
  renderSpending();renderPersonalization();renderHomeSnapshot();
}

function renderSpending(){
  if(state.categoryRowsAvailable===false){
    $('spending-donut').innerHTML=`<p class="empty-state">${esc(state.overview?t('support.unavailable'):t('loading.account'))}</p>`;$('spending-donut').setAttribute('aria-busy',String(!state.overview));text('spending-total','—');$('spending-categories').innerHTML='';text('spending-selection','');return;
  }
  const categories=spendingCategories(state.categoryRows||[],state.spendingGroup).map(row=>({...row,label:categoryName(row.category)}));
  if(state.selectedCategory&&!categories.some(row=>row.category===state.selectedCategory))state.selectedCategory=null;
  const total=categories.reduce((sum,row)=>sum+row.total_cents,0),selected=categories.find(row=>row.category===state.selectedCategory);
  $('spending-donut').innerHTML=spendingRing(categories,state.selectedCategory);
  $('spending-donut').setAttribute('aria-busy','false');
  text('spending-total',money(selected?.total_cents??total));
  const basketKey={regular:'regular',irregular:'irregular',leaks:'everyday'}[state.spendingGroup],basketGroup=Boolean(basketKey);
  text('spending-center-label',selected?selected.label:basketGroup?t('basket.'+basketKey):u(state.spendingGroup==='all'?'spending.total':'spending.'+state.spendingGroup));
  if($('spending-group-help')){$('spending-group-help').hidden=!basketGroup;text('spending-group-help',basketGroup?t('basket.'+basketKey+'.help'):'');}
  const visible=state.categoryExpanded||categories.findIndex(row=>row.category===state.selectedCategory)>=5?categories:categories.slice(0,5);
  $('spending-categories').innerHTML=visible.map(row=>`<button type="button" class="category-row" data-spending-category="${esc(row.category)}" aria-pressed="${state.selectedCategory===row.category}"><span class="category-icon" style="--category-color:${categoryPalette[row.category]||'#668578'}">${categoryIcon(row.category)}</span><span class="category-copy"><strong>${esc(row.label)}</strong><small>${esc(u('spending.share',{percent:total?Math.round(row.total_cents*100/total):0}))}</small></span><span class="category-amount">${money(row.total_cents)}<span aria-hidden="true">›</span></span></button>`).join('')+(categories.length>5?`<button type="button" class="text-button category-expand" data-expand-categories>${esc(state.categoryExpanded?copy('Show less','Näytä vähemmän','Visa färre'):copy('Show all categories','Näytä kaikki luokat','Visa alla kategorier'))} ${state.categoryExpanded?'−':'+'}</button>`:'')||`<p class="empty-state">${esc(t('empty.transactions'))}</p>`;
  $('spending-selection').innerHTML=selected?`<div><strong>${esc(selected.label)}</strong><span>${money(selected.total_cents)}</span></div><div class="personal-actions"><button type="button" class="text-button" data-category-transactions="${esc(selected.category)}">${esc(u('spending.rows',{count:selected.count}))} ↗</button><button type="button" class="text-button" data-direct-question="${esc(copy(`How much did I spend on ${selected.category}?`,`Paljonko käytin ${selected.category}?`,`Hur mycket spenderade jag på ${selected.category}?`))}">${esc(copy('Ask about this category','Kysy tästä luokasta','Fråga om kategorin'))} ↗</button><button type="button" class="text-button" data-direct-question="${esc(copy(`How much could I save if I reduced ${selected.category} by 10%?`,`Kuinka paljon voisin säästää, jos vähennän ${selected.category} 10 %?`,`Hur mycket kan jag spara om jag minskar ${selected.category} med 10 %?`))}">${esc(copy('Try a 10% change','Kokeile 10 % muutosta','Prova en ändring på 10 %'))}</button></div>`:`<p>${esc(u('spending.tap'))}</p>`;
  for(const button of document.querySelectorAll('[data-spending-group]'))button.setAttribute('aria-pressed',String(button.dataset.spendingGroup===state.spendingGroup));
}

function selectSpending(category,source){
  const restore=source&&document.activeElement===source;
  state.selectedCategory=category;renderSpending();
  if(restore){const equivalent=[...document.querySelectorAll('[data-spending-category]')].find(node=>node.dataset.spendingCategory===category&&node.tagName===source.tagName);equivalent?.focus({preventScroll:true});}
}

function renderPersonalization(){
  const profile=experience().load(),name=names[state.customerId]||'';
  text('home-greeting',u('home.greeting',{name}));
  $('welcome-guide').hidden=profile.onboarding_complete;
  $('welcome-guide').innerHTML=`<div><strong>${esc(u('tour.title'))}</strong><p>${esc(u('tour.intro'))}</p></div><button type="button" class="text-button" data-open-tour>${esc(u('tour.replay'))} ↗</button><button type="button" class="text-button" data-tour-skip>${esc(u('tour.skip'))}</button>`;
  const goalTemplate=profile.focus==='flexibility'?'custom':profile.focus==='travel'?'trip':profile.focus;
  $('personalization-card').innerHTML=`<div><span class="eyebrow">${esc(u('personal.title'))}</span><h3 id="personalization-title">${esc(u('focus.'+profile.focus))}</h3><p>${esc(profile.onboarding_complete?personalStatus():u('personal.intro'))}</p></div><div class="personal-actions"><button type="button" class="text-button" data-open-notebook>${esc(u(profile.onboarding_complete?'personal.edit':'personal.setup'))} ↗</button><button type="button" class="text-button" data-open-tour>${esc(u('tour.replay'))}</button><button type="button" class="text-button" data-goal-template="${esc(goalTemplate)}">${esc(t('goal.form.title'))} ↗</button></div>`;
  const moments=buildJournal(state.overview,state.categoryRows||[],i18n.locale);
  $('journal-timeline').innerHTML=moments.length?moments.map(moment=>`<article class="journal-moment"><span class="journal-dot" aria-hidden="true">${moment.kind==='income'?'↙':moment.kind==='housing'?'⌂':'✦'}</span><div><time datetime="${esc(moment.date)}">${dateLabel(moment.date)}</time><h3>${esc(moment.title)}</h3><p>${esc(categoryName(moment.category))} · ${money(Math.abs(moment.amount_cents))}</p>${moment.transaction_ref?`<button type="button" class="text-button" data-journal-transaction="${esc(moment.transaction_ref)}">${esc(u('journal.view'))} ↗</button>`:''}</div></article>`).join(''):`<p class="empty-state">${esc(u('journal.empty'))}</p>`;
  $('notebook-content').innerHTML=`<p class="small-text">${esc(personalStatus())}</p>${profile.notes.length?profile.notes.map(note=>`<article class="notebook-note"><p>${esc(note.text)}</p><small>${esc(u(note.source==='confirmed_conversation'?'notebook.confirmed':'notebook.user'))}</small><div><button type="button" class="text-button" data-note-edit="${esc(note.id)}">${esc(u('notebook.edit'))}</button><button type="button" class="text-button" data-note-delete="${esc(note.id)}">${esc(u('notebook.delete'))}</button></div></article>`).join(''):`<p>${esc(u('notebook.empty'))}</p>`}<button type="button" class="secondary-button" data-open-notebook>${esc(u('notebook.add'))} +</button>`;
  const milestone=profile.milestones?milestoneFor(state.goals):null;
  $('goal-milestone').hidden=!milestone;
  if(milestone){const stage=milestone.percent>=100?'complete':milestone.percent>=75?'near':milestone.percent>=50?'half':milestone.percent>=25?'quarter':'start';$('goal-milestone').innerHTML=`<span class="milestone-symbol" aria-hidden="true">✦</span><div><span class="eyebrow">${esc(u('milestone.title'))}</span><h3>${esc(milestone.name)} · ${milestone.percent}%</h3><p>${esc(u('milestone.'+stage))}</p><p class="small-text">${esc(u('milestone.basis'))}</p></div>`;}
  // Only confirmed structured preferences affect suggestions; notes never act as instructions.
  const protectedCategory=profile.protected_category;
  const alternative=spendingCategories(state.categoryRows||[]).find(row=>['Restaurants','Lifestyle','Entertainment','Travel'].includes(row.category)&&row.category!==protectedCategory&&!(profile.focus==='travel'&&row.category==='Travel'));
  $('home-personal-plan').innerHTML='';
  const hasPersonalPlan=profile.onboarding_complete&&profile.focus!=='flexibility'&&alternative;
  text('home-coach-title',protectedCategory!=='none'?u('memory.protect',{category:categoryName(protectedCategory)}):hasPersonalPlan?u('focus.'+profile.focus):'');
  if(hasPersonalPlan){
    $('home-personal-plan').insertAdjacentHTML('beforeend',`<div class="personal-plan"><p>${esc(protectedCategory!=='none'?u('memory.protect',{category:categoryName(protectedCategory)}):u('focus.'+profile.focus))}</p><button type="button" class="secondary-button" data-personal-plan="${esc(alternative.category)}">${esc(copy(`Try 20% less on ${categoryName(alternative.category)}`,`Kokeile 20 % pienempiä menoja: ${categoryName(alternative.category)}`,`Prova 20 % mindre på ${categoryName(alternative.category)}`))} ↗</button><p class="small-text">${esc(copy('Preview a change, then choose whether to connect it to your goal.','Kokeile muutosta ja päätä sitten, liitätkö sen tavoitteeseesi.','Prova en förändring och välj sedan om du vill koppla den till ditt mål.'))}</p></div>`);
  }
  $('home-coach-question').hidden=Boolean(hasPersonalPlan);
  renderMonthlyRecap();
}

function experienceDialog(id,title){
  if(!$(id)&&document.body?.insertAdjacentHTML)document.body.insertAdjacentHTML('beforeend',`<dialog id="${id}" class="experience-dialog" aria-labelledby="${id}-title"><div class="sheet-header"><span class="wordmark">S-Coach</span><button type="button" class="close-button" data-close aria-label="${esc(u('personal.close'))}">×</button></div><div class="sheet-content"><h2 id="${id}-title">${esc(title)}</h2><div id="${id}-content"></div></div></dialog>`);
  if($(id+'-title'))text(id+'-title',title);
  return $(id);
}
function openNotebook(){
  closeDialogs();const dialog=experienceDialog('notebook-dialog',u('notebook.title'));if(!dialog)return;
  const profile=experience().load(),editing=profile.notes.find(note=>note.id===noteEditing);
  const selectOptions=(values,selected,prefix)=>values.map(value=>`<option value="${esc(value)}" ${value===selected?'selected':''}>${esc(prefix==='category.'?categoryName(value):u(prefix+value))}</option>`).join('');
  $('notebook-dialog-content').innerHTML=`<p class="subtle">${esc(u('notebook.intro'))}</p><form id="preferences-form" class="preferences-form"><label for="preference-focus">${esc(u('personal.focus'))}</label><select id="preference-focus">${selectOptions(['buffer','travel','home','vehicle','flexibility'],profile.focus,'focus.')}</select><label for="preference-style">${esc(u('personal.style'))}</label><select id="preference-style">${selectOptions(['gentle','direct'],profile.style,'style.')}</select><label for="preference-protect">${esc(u('personal.protect'))}</label><select id="preference-protect"><option value="none">${esc(u('protect.none'))}</option>${selectOptions(['Restaurants','Travel','Lifestyle'],profile.protected_category,'category.')}</select><p class="small-text">${esc(u('personal.protectHelp'))}</p><label class="check-row"><input id="preference-milestones" type="checkbox" ${profile.milestones?'checked':''}>${esc(u('personal.milestones'))}</label><p class="small-text">${esc(u('personal.milestonesHelp'))}</p><label class="check-row"><input id="preference-consent" type="checkbox" ${profile.consent?'checked':''}>${esc(u('personal.consent'))}</label><p class="small-text">${esc(u('personal.consentHelp'))}</p><button type="submit" class="primary-button">${esc(u('personal.save'))}</button><p id="preference-status" class="small-text" role="status">${esc(personalStatus())}</p></form><form id="note-form" class="note-form"><h3>${esc(u(editing?'notebook.edit':'notebook.add'))}</h3><label for="note-text">${esc(u('journal.reflection'))}</label><textarea id="note-text" rows="3" maxlength="500" required placeholder="${esc(u('notebook.placeholder'))}">${esc(editing?.text||'')}</textarea><p class="small-text">${esc(u('notebook.limit'))}</p><button type="submit" class="secondary-button">${esc(u('notebook.save'))}</button></form><button type="button" class="text-button danger-button" data-forget-profile>${esc(u('personal.forget'))}</button>`;
  $('preferences-form').addEventListener('submit',event=>{event.preventDefault();const store=experience();const fields={focus:$('preference-focus').value,style:$('preference-style').value,protected_category:$('preference-protect').value,milestones:$('preference-milestones').checked};const consent=$('preference-consent').checked,wasConsented=store.load().consent;if(consent!==wasConsented)store.setConsent(consent);store.save(fields);store.markOnboarded();renderPersonalization();renderWishes();text('preference-status',!consent&&wasConsented&&!store.isCleared()?u('personal.clearFailed'):personalStatus());});
  $('note-form').addEventListener('submit',event=>{event.preventDefault();const value=$('note-text').value.trim();if(!value)return;try{if(noteEditing)experience().updateNote(noteEditing,value);else experience().addNote({text:value,source:'user'});noteEditing=null;renderPersonalization();dialog.close();notify(personalStatus());}catch(error){text('preference-status',u('notebook.limit'));}});
  openDialog('notebook-dialog');
}
function showTour(step=0){
  tourStep=Math.max(0,Math.min(2,step));closeDialogs();const dialog=experienceDialog('tour-dialog',u('tour.title'));if(!dialog)return;
  const keys=['spending','coach','preferences'],key=keys[tourStep];
  $('tour-dialog-content').innerHTML=`<div class="tour-progress" aria-label="${esc(u('tour.step',{step:tourStep+1,total:3}))}">${keys.map((_,i)=>`<span class="${i<=tourStep?'is-active':''}"></span>`).join('')}</div><span class="tour-art" aria-hidden="true">${['◔','✳','✦'][tourStep]}</span><p class="eyebrow">${esc(u('tour.step',{step:tourStep+1,total:3}))}</p><h3>${esc(u('tour.'+key+'Title'))}</h3><p>${esc(u('tour.'+key))}</p><button type="button" class="secondary-button" data-tour-try="${key}">${esc(copy("Try it now","Kokeile nyt","Prova nu"))} ↗</button><div class="tour-actions">${tourStep?`<button type="button" class="text-button" data-tour-step="${tourStep-1}">${esc(u('tour.back'))}</button>`:''}<button type="button" class="primary-button" ${tourStep===2?'data-tour-done':`data-tour-step="${tourStep+1}"`}>${esc(u(tourStep===2?'tour.done':'tour.next'))} ↗</button></div><button type="button" class="text-button" data-tour-skip>${esc(u('tour.skip'))}</button>`;
  openDialog('tour-dialog');
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
  if(experience().load().protected_category==='Restaurants'&&state.overview?.priority?.id==='restaurant_change'){
    openDialog('coach-dialog');await askCoach(copy('How much did I spend on groceries?','Paljonko käytin ruokaostoksiin?','Hur mycket spenderade jag på matinköp?'),context);return;
  }
  if(!state.comparison){
    try{state.comparison=normalizeComparison(await request(context,'get','/api/comparison',comparisonQuery(context.month)),context.month);renderComparison();}
    catch(error){if(error instanceof StaleResponse)throw error;openDialog('coach-dialog');await askCoach(t('coach.promptMonth'),context);return;}
  }
  if(!isDemoStory()&&state.overview?.priority&&state.overview.priority.id!=='restaurant_change'){
    openDialog('coach-dialog');
    await askCoach(priorityCopy(state.overview.priority)?.question||t('coach.promptMonth'),context);
    return;
  }
  openDialog('coach-dialog');
  await askCoach(t('coach.promptRestaurants'),context);
}
async function fetchRows(filters={},context=captureContext()) {
  const result=await request(context,'get','/api/transactions',{month:context.month,...filters});
  return result.transactions || result.rows || [];
}
function renderRows(rows,label=monthLabel(state.selectedMonth)) {
  state.rows=rows;
  text('transaction-summary',t('transactions.summary',{label,count:rows.length}));
  $('transaction-list').innerHTML=rows.length?rows.map(row=>`<article class="transaction-row"><span class="category-icon" style="--category-color:${categoryPalette[row.category]||'#668578'}">${categoryIcon(row.category)}</span><div><h3>${esc(row.merchant_name||row.merchant||categoryName(row.category)||t('transactions.unknownMerchant'))}</h3><p>${dateLabel(row.date||row.timestamp)}</p>${row.transaction_ref===state.exclusion?`<span class="row-badge">${esc(t('story.userExclusion'))}</span>`:''}<button class="text-button" data-transaction="${esc(row.transaction_ref)}">${esc(t('transactions.open'))} ↗</button></div><strong>${row.amount_cents>0?'+':''}${money(Math.abs(row.amount_cents))}</strong></article>`).join(''):`<p class="empty-state">${esc(t('empty.transactions'))}</p>`;
}
async function showTransactions(filters={category:'Restaurants'},context=captureContext(),definition=null) {
  assertCurrent(context);if(!filters.role)clearFilter();state.transactionEvidence=null;
  openDialog('transactions-dialog');$('transaction-list').innerHTML=`<p class="empty-state" role="status">${esc(t('loading.rows'))}</p>`;
  let rows;
  try{
    rows=await fetchRows(filters,context);assertCurrent(context);
    if(Array.isArray(definition?.result?.transaction_refs)){
      const expected=new Set(definition.result.transaction_refs);rows=rows.filter(row=>expected.has(row.transaction_ref));
    }
  }catch(error){if(isCurrent(context))$('transaction-list').innerHTML=`<p class="empty-state">${esc(t('support.unavailable'))}</p>`;throw error;}
  const start=filters.start||(filters.month||context.month)+'-01',end=filters.end||monthEnd(filters.month||context.month);
  state.transactionEvidence=filters.role&&!filters.start&&!filters.end?moneyMapEvidence(filters.role):{kind:'statistics',customerId:state.customerId,accountId:state.overview?.account_id,start,end,metric:definition?.metric||(filters.role==='income'?'inflow_total':'outflow_total'),statistics:definition?.result,filters:Object.fromEntries(Object.entries(filters).filter(([key])=>!['start','end','month'].includes(key))),rows,transaction_refs:rows.map(row=>row.transaction_ref)};
  renderRows(rows,`${filters.role?flowName(filters.role)+' · ':filters.category?categoryName(filters.category)+' · ':''}${dateLabel(start)}–${dateLabel(end)}`);
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
  const summary=forecastSummary(f);
  $('forecast-summary').innerHTML=summary?`<strong>${esc(u('forecast.summary',{amount:money(summary.end_cents)}))}</strong><span>${esc(u('forecast.lowest',{amount:money(summary.low_cents)}))} · ${dateLabel(summary.low_date)}</span>`:'';
  $('forecast-assumptions').innerHTML=`<details class="forecast-method"><summary>${esc(t('evidence.formula'))}</summary><p>${esc(t('forecast.method'))}</p></details>${(f?.recurring_items||[]).map((item,i)=>`<fieldset class="assumption-inputs" data-assumption="${esc(item.id)}"><legend>${esc(flowName(item.role))}</legend><label for="assumption-enabled-${i}"><input id="assumption-enabled-${i}" type="checkbox" data-field="enabled" ${state.forecastAssumptions[item.id]?.enabled===false?'':'checked'}>${esc(t('forecast.include'))}</label><div class="form-grid"><div><label for="assumption-amount-${i}">${esc(t('forecast.amount'))}</label><input id="assumption-amount-${i}" data-field="amount" type="number" step="0.01" value="${Number(state.forecastAssumptions[item.id]?.amount_cents??item.amount_cents??0)/100}"></div><div><label for="assumption-day-${i}">${esc(t('forecast.day'))}</label><input id="assumption-day-${i}" data-field="day" type="number" min="1" max="31" value="${state.forecastAssumptions[item.id]?.median_day??item.median_day??1}"></div></div></fieldset>`).join('')}<button class="secondary-button" id="apply-preview">${esc(t('forecast.apply'))} ↗</button><p>${esc(t('forecast.temporary'))}</p>`;
}
function renderTrends() {
  const data=state.trends,rows=(data?.months||[]).filter(row=>row.available!==false&&row.total_cents!==null);
  if(v3)v3.renderTrendChart(rows);else $('trend-chart').innerHTML=trendChart(rows);text('trend-description',rows.length?t('trends.description',{count:rows.length}):t('empty.trends'));
  $('trends-view').querySelector('.trend-facts')?.remove();
  if(!data)return;
  const annual=data.annual_comparison;
  const evidence=`<section class="trend-facts"><h3>${esc(t('trends.sameMonth'))}</h3><p>${esc(data.year_over_year_delta_cents===null||data.year_over_year_delta_cents===undefined?t('empty.trends'):t('trends.yoy',{amount:money(data.year_over_year_delta_cents)}))}</p><h3>${esc(t('trends.salary'))}</h3><p>${esc(t('trends.salaryMedians',{recent:money(data.recent_three_salary_median_cents),prior:money(data.prior_six_salary_median_cents)}))}</p>${annual?.available?`<details><summary>${esc(t('trends.annual'))}</summary>${comparisonChart({before:{...annual.previous,label:t('trends.priorYear')},after:{...annual.current,label:t('trends.latestYear')}})}<p>${dateLabel(annual.previous.start)}–${dateLabel(annual.previous.end)} / ${dateLabel(annual.current.start)}–${dateLabel(annual.current.end)}</p></details>`:`<p>${esc(t('trends.noAnnual'))}</p>`}<details><summary>${esc(t('evidence.formula'))}</summary><p>${esc(u('spending.excludes'))}</p>${sourceButton(data.transaction_refs||[])}</details></section>`;
  $('trend-chart').insertAdjacentHTML('afterend',evidence);
}
function renderGoals() {
  $('goals-list').innerHTML=state.goals.length?state.goals.map(goal=>`<article class="goal-card"><span class="status-pill scenario-pill">${esc(t('common.estimate'))}</span><h2>${esc(goal.name)}</h2><p class="subtle">${esc(t('goal.by',{date:dateLabel(goal.target_date)}))}</p><p class="goal-amount">${money(goal.required_monthly_cents)} <span>${esc(t('goal.required'))}</span></p>${goalChart(goal.current_saved_cents??0,goal.target_cents)}<p class="small-text">${esc(t('goal.capacity',{amount:money(goal.conservative_monthly_contribution_cents)}))}</p><p class="small-text">${esc(t('goal.reserveDetail',{reserve:money(goal.reserve_floor_cents),upfront:money(goal.upfront_available_cents)}))}</p>${goal.modeled_scenario_contribution_cents>0?`<p class="small-text">${esc(t('goal.linked',{amount:money(goal.modeled_scenario_contribution_cents)}))}</p>`:''}${goal.monthly_gap_cents>0?`<p class="small-text">${esc(t('goal.gap',{amount:money(goal.monthly_gap_cents)}))}</p>`:''}<button class="text-button" data-goal-evidence="${esc(goal.goal_id||goal.id)}">${esc(t('goal.assumptions'))} ↗</button>${v3?v3.goalActionsHTML(goal):''}</article>`).join(''):`<div class="goal-card"><span class="eyebrow">${esc(t('goals.eyebrow'))}</span><h2>${esc(t('goals.empty'))}</h2><p class="subtle">${esc(t('goals.subtitle'))}</p></div>`;
  renderPersonalization();renderWishes();
}
function supportingEvidence(data){
  const calculationRefs=data.transaction_refs||[],historyRefs=data.comparison_transaction_refs||[];
  const assumptions=(data.assumptions||[]).map((item,index)=>t(`safe.assumption.${index}`)===`safe.assumption.${index}`?item:t(`safe.assumption.${index}`));
  return `<details><summary>${esc(t('safe.evidence'))}</summary>${assumptions.length?`<h3>${esc(t('evidence.assumptions'))}</h3><ul>${assumptions.map(item=>`<li>${esc(item)}</li>`).join('')}</ul>`:''}<h3>${esc(t('evidence.calculationSources'))}</h3>${sourceButton(calculationRefs)}${historyRefs.length?`<h3>${esc(t('evidence.historySources'))}</h3>${sourceButton(historyRefs)}`:''}</details>`;
}
// Until-payday view: everything due before payday and any planned saving are already set aside.
function safeUntilPaydayHTML(safe){
  const rows=[['v3.safe.balance',safe.starting_balance_cents],['v3.safe.bills',safe.committed_cents],['v3.safe.reserve',safe.reserve_floor_cents],['v3.safe.saving',safe.planned_saving_cents]].filter(([key,cents])=>Number.isSafeInteger(cents)&&!(key==='v3.safe.saving'&&cents===0));
  const values=rows.map(([key,cents])=>`<dt>${esc(t(key))}</dt><dd>${money(cents)}</dd>`).join('');
  const shortfall=Number.isSafeInteger(safe.shortfall_cents)&&safe.shortfall_cents>0?`<p class="safe-warning">${esc(t('v3.safe.shortfall',{amount:money(safe.shortfall_cents)}))}</p>`:'';
  const steady=safe.steady_mode?`<p class="small-text">${esc(t('v3.safe.steady'))}</p>`:'';
  const save=Number.isSafeInteger(safe.safe_to_save_cents)&&safe.safe_to_save_available!==false?`<p class="safe-save">${esc(t('v3.safe.save',{amount:money(safe.safe_to_save_cents)}))}</p>`:'';
  return `<p class="support-period">${esc(t('v3.safe.week'))}</p><p class="support-amount">${money(safe.this_week_cents)}</p><p class="small-text">${esc(t('v3.safe.perDay',{amount:money(safe.per_day_cents),date:dateLabel(safe.next_payday),days:safe.days_until_payday}))}</p>${shortfall}<dl class="support-values">${values}</dl>${save}${steady}<p class="small-text">${esc(t(safe.payday_source==='fallback_30_days'?'v3.safe.noPayday':'v3.safe.note'))}</p>${supportingEvidence(safe)}`;
}
function renderSupport(){
  const safe=state.safeToSpend;
  if(safe&&safe.next_payday){$('safe-content').innerHTML=safeUntilPaydayHTML(safe);}
  else $('safe-content').innerHTML=!safe?`<p class="empty-state">${esc(t('support.unavailable'))}</p>`:!safe.available?`<p class="empty-state">${esc(t(safe.needs_history?'support.needsHistory':'support.unavailable'))}</p>`:`<p class="support-period">${esc(t('safe.amount',{days:safe.horizon_days}))}</p><p class="support-amount">${money(safe.safe_to_spend_cents)}</p><p class="small-text">${esc(t('safe.horizon',{date:dateLabel(safe.horizon_end)}))}</p><dl class="support-values"><dt>${esc(t('safe.reserve'))}</dt><dd>${money(safe.reserve_floor_cents)}</dd><dt>${esc(t('safe.obligations'))}</dt><dd>${money(safe.scheduled_outflows_cents)}</dd><dt>${esc(t('safe.everydayAllowance'))}</dt><dd>${money(safe.historical_flexible_buffer_cents)}</dd></dl><p class="small-text">${esc(t('safe.demoReserve'))}</p>${supportingEvidence(safe)}`;
  const investment=state.investments;
  $('investment-content').innerHTML=!investment?`<p class="empty-state">${esc(t('support.unavailable'))}</p>`:`<p class="support-period">${monthLabel(investment.start_month||state.selectedMonth)} — ${monthLabel(investment.end_month||state.selectedMonth)}</p><dl class="support-values"><dt>${esc(t('investment.contributions'))}</dt><dd>${money(investment.total_contributions_cents)}</dd><dt>${esc(t('investment.withdrawals'))}</dt><dd>${money(investment.withdrawals_cents)}</dd><dt>${esc(t('investment.consistency'))}</dt><dd>${esc(t('investment.monthsCount',{count:investment.contribution_months,total:investment.period_months}))}</dd></dl>${investment.coverage_limited?`<p class="small-text">${esc(t('investment.coverageLimited',{count:investment.period_months}))}</p>`:''}${supportingEvidence(investment)}`;
}
function renderVat(){
  const vat=state.vat;
  if(!vat){$('vat-content').innerHTML=`<p class="empty-state">${esc(t('support.unavailable'))}</p>`;return;}
  const rates=(vat.by_rate||[]).map(row=>`<li>${esc(t('vat.rateRow',{rate:percentage(row.rate_basis_points),count:row.transaction_count,amount:money(row.estimated_vat_cents)}))}</li>`).join('');
  const limitations=(vat.limitations||[]).length?['vat.limitation.mixed','vat.limitation.ambiguous','vat.limitation.excise','vat.limitation.tax']:[];
  $('vat-content').innerHTML=`<p class="support-period">${dateLabel(vat.start)}–${dateLabel(vat.end)}</p><p class="support-amount">${esc(vat.gross_spending_cents>0&&vat.covered_spending_cents===0?copy('Estimate unavailable','Arvio ei ole saatavilla','Uppskattning saknas'):t('vat.amount',{amount:money(vat.estimated_vat_cents)}))}</p><dl class="support-values"><dt>${esc(t('vat.gross'))}</dt><dd>${money(vat.gross_spending_cents)}</dd><dt>${esc(t('vat.coverage'))}</dt><dd>${percentage(vat.coverage_basis_points)}</dd></dl><p class="small-text">${esc(t('vat.coverageNote'))}</p><details><summary>${esc(t('vat.breakdown'))}</summary><ul>${rates}</ul><p>${esc(t('vat.method'))}</p>${limitations.length?`<h3>${esc(t('vat.limitationsTitle'))}</h3><ul>${limitations.map(key=>`<li>${esc(t(key))}</li>`).join('')}</ul>`:''}</details>`;
}
async function createGoal(context=captureContext()) {
  assertCurrent(context);
  const candidate=state.pendingHandoff;
  const pending=candidate?.customerId===context.customerId&&candidate.generation===context.generation?candidate:null;
  const values={name:$('goal-name').value.trim(),template:$('goal-template').value,target_cents:eurosToCents($('goal-target').value),current_saved_cents:eurosToCents($('goal-saved').value),target_date:$('goal-date').value,reserve_floor_cents:eurosToCents($('goal-reserve').value),confirmed:true};
  const signature=JSON.stringify(values),acknowledged=state.pendingGoalCreation;
  let goalId=pending?.createdGoalId||(!pending&&acknowledged?.customerId===context.customerId&&acknowledged.generation===context.generation&&acknowledged.signature===signature?acknowledged.goalId:null);
  if(!goalId){
    const result=await request(context,'post','/api/goals',values);
    const goal=result.goal||result;goalId=goal.goal_id||goal.id;
    if(!goalId)throw new Error('The saved goal reference is unavailable.');
    if(pending&&state.pendingHandoff===pending){pending.createdGoalId=goalId;renderHandoffProgress(pending);}
  }
  if(!pending){
    state.pendingGoalCreation={customerId:context.customerId,generation:context.generation,signature,goalId};
    for(const id of ['goal-name','goal-template','goal-target','goal-saved','goal-date','goal-reserve'])$(id).disabled=true;
    text('goal-handoff',copy('Your plan is saved. Refresh to see it.','Suunnitelmasi on tallennettu. Näytä se päivittämällä.','Din plan är sparad. Uppdatera för att se den.'));
    text('goal-submit',copy('Refresh saved plan','Päivitä tallennettu suunnitelma','Uppdatera sparad plan')+' ↗');
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
  state.pendingGoalCreation=null;
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
  const scope=`${esc(names[context.customerId]||'')} · ${esc(copy('Demo account','Demotili','Demokonto'))}`;
  const sources=(refs,_facts)=>`<details class="evidence-group"><summary>${esc(t('evidence.refs',{count:refs.length}))}</summary><p>${esc(copy('Calculated from the matching account entries. You can inspect each payment below.','Laskettu vastaavista tilitapahtumista. Voit tarkastella jokaista maksua alta.','Beräknat från matchande kontoposter. Du kan granska varje betalning nedan.'))}</p>${sourceButton(refs,{start:context.start,end:context.end})}</details>`;
  if(context.kind==='statistics'){
    const incoming=context.metric==='inflow_total';
    const stats=context.statistics;
    const amount=stats?stats.metric_value_cents:(context.rows||[]).reduce((sum,row)=>sum+(incoming?Math.max(row.amount_cents,0):-Math.min(row.amount_cents,0)),0);
    const display=context.metric==='transaction_count'&&stats?String(stats.metric_value_count):money(amount);
    const filter=filterSummary(context.filters);
    let formula=incoming?copy('We add the positive amounts credited in this selection. This does not establish gross income before tax.','Laskemme yhteen tämän valinnan tilille saapuneet summat. Näistä ei voi päätellä bruttotuloja ennen veroja.','Vi summerar positiva belopp som kommit in i urvalet. De fastställer inte bruttoinkomst före skatt.'):copy('We add outgoing amounts in this selection. The spending chart excludes savings transfers.','Laskemme valinnan ulosmenevät summat. Menokaavio ei sisällä säästösiirtoja.','Vi summerar utgående belopp i urvalet. Utgiftsdiagrammet utesluter sparöverföringar.');
    if(context.metric==='average_outflow'&&stats)formula=stats.outflow_count?`${money(stats.outflow_total_cents)} ÷ ${stats.outflow_count} = ${money(stats.metric_value_cents)}. ${copy('Average per outgoing purchase, rounded to cents.','Keskiarvo lähtevää ostosta kohti, pyöristettynä senttiin.','Genomsnitt per utgående köp, avrundat till cent.')}`:copy('There are no matching outgoing payments, so an average is unavailable.','Vastaavia lähteviä maksuja ei ole, joten keskiarvoa ei voi laskea.','Det finns inga matchande utgående betalningar, så något genomsnitt finns inte.');
    if(context.metric==='transaction_count')formula=copy('We count the outgoing payments in this selection.','Laskemme tämän valinnan lähtevien maksujen määrän.','Vi räknar utgående betalningar i detta urval.');
    if(context.metric==='largest_outflow')formula=stats&&!stats.largest_outflow?copy('There is no matching outgoing payment in this selection.','Tässä valinnassa ei ole vastaavaa lähtevää maksua.','Det finns ingen matchande utgående betalning i urvalet.'):copy('This is the largest outgoing payment in the selection.','Tämä on valinnan suurin lähtevä maksu.','Detta är den största utgående betalningen i urvalet.');
    return `<section class="evidence-group"><h3>${esc(filter||u('spending.all'))}</h3><p class="coach-result-amount">${esc(display)}</p><p>${scope}<br>${dateLabel(context.start)}–${dateLabel(context.end)}</p><p>${esc(u('spending.rows',{count:context.rows?.length||0}))}</p><details><summary>${esc(t('evidence.formula'))}</summary><p>${esc(formula)}</p></details>${sources(context.transaction_refs||[],[])}</section>`;
  }
  if(context.kind==='money_map'){
    const label=context.role?flowName(context.role):context.label||t('evidence.allFlows');
    return `<div class="evidence-status"><strong>${esc(t('common.observed'))}</strong><p>${esc(t('evidence.mapIntro'))}</p></div><section class="evidence-group"><h3>${esc(t('evidence.scope'))}</h3><p>${scope}<br>${esc(t('common.period'))}: ${dateLabel(context.start)}–${dateLabel(context.end)}<br>${esc(t('evidence.filter'))}: ${esc(label)}</p></section><section class="evidence-group"><h3>${esc(label)}</h3>${context.amount_cents!==undefined?`<p>${esc(t('evidence.netFlow',{amount:money(context.amount_cents)}))}</p>`:(context.flows||[]).map(flow=>`<p>${esc(flowName(flow.role))}: ${money(flow.amount_cents)}</p>`).join('')}<details><summary>${esc(t('evidence.formula'))}</summary><p>${esc(t('evidence.mapFormula'))}</p></details></section>${sources(context.transaction_refs||[],context.fact_ids||[])}`;
  }
  if(context.kind==='restaurant'){
    const comparison=context.comparison,scenario=context.scenario,current=comparison?.current||comparison?.after,previous=comparison?.previous||comparison?.before;
    const refs=comparison?.transaction_refs||[...(previous?.transaction_refs||[]),...(current?.transaction_refs||[])];
    const contribution=scenario?.monthly_contribution_cents??scenario?.modeled_monthly_contribution_cents;
    const excluded=context.exclusionDetail?`${dateLabel(context.exclusionDetail.date)} · ${context.exclusionDetail.merchant_name||context.exclusionDetail.merchant||t('transactions.unknownMerchant')} · ${money(Math.abs(context.exclusionDetail.amount_cents))}`:context.exclusion?t('evidence.oneOffSaved'):t('evidence.none');
    return `<div class="evidence-status"><strong>${esc(t('common.observed'))}</strong><p>${esc(t('evidence.actual',{amount:money(current?.total_cents)}))}</p></div><section class="evidence-group"><h3>${esc(t('evidence.scope'))}</h3><p>${scope}<br>${esc(t('common.period'))}: ${dateLabel(current?.start)}–${dateLabel(current?.end)}<br>${esc(t('evidence.comparison'))}: ${dateLabel(previous?.start)}–${dateLabel(previous?.end)}<br>${esc(t('evidence.filter'))}: ${esc(t('category.restaurants'))}</p><p>${money(previous?.total_cents)} → ${money(current?.total_cents)}</p><details><summary>${esc(t('evidence.formula'))}</summary><p>${esc(t('evidence.averageFormula'))}</p></details></section>${sources(refs,[comparison?.fact_id].filter(Boolean))}<section class="evidence-group"><h3>${esc(t('common.estimate'))} · 20%</h3><p>${esc(t('evidence.scenarioFormula',{base:money(scenario?.adjustable_base_cents),amount:money(contribution)}))}</p><p>${esc(t('evidence.excluded'))}: <span>${esc(excluded)}</span><br>${esc(t('evidence.source'))}: ${esc(t(context.exclusion?'evidence.user':'evidence.deterministic'))}</p></section><details class="evidence-group"><summary>${esc(t('evidence.memory'))}</summary><p>${esc(t('evidence.memoryHelp'))}</p><p>${esc(t('evidence.host'))}</p></details>`;
  }
  if(context.kind==='transaction'){
    const row=context.row;
    const vat=vatEstimateFor(row.transaction_ref),vatLine=vat?`<br>${esc(vat.estimated_vat_cents===null?t('vat.unmapped'):t('vat.taxInside',{amount:money(vat.estimated_vat_cents),rate:percentage(vat.rate_basis_points)}))}<br>${esc(vatSourceLabel(vat))}<br><span title="${esc(vat.mapping_note||'')}">${esc(vatMappingLabel(vat))}</span>`:'';
    return `<section class="evidence-group"><h3>${esc(row.merchant_name||row.merchant||categoryName(row.category))}</h3><p class="coach-result-amount">${money(row.amount_cents)}</p><p>${dateLabel(row.date)} · ${esc(categoryName(row.category))}</p><p>${scope}</p>${vat?`<details><summary>${esc(t('vat.title'))}</summary><p>${vatLine}</p><p class="small-text">${esc(t('vat.disclaimer'))}</p></details>`:''}<p class="small-text">${esc(copy('Merchant names are not supplied in this synthetic dataset. Categories describe the payment, not what was bought.','Kauppiaiden nimiä ei ole tässä synteettisessä aineistossa. Luokka kuvaa maksua, ei ostettuja tuotteita.','Handlarnamn finns inte i detta syntetiska dataset. Kategorin beskriver betalningen, inte vad som köptes.'))}</p></section>`;
  }
  if(context.kind==='goal'){
    const goal=context.goal;
    return `<section class="evidence-group"><h3>${esc(goal.name)} · ${esc(t('common.estimate'))}</h3><p>${scope}</p><p>${esc(t('goal.target'))}: ${money(goal.target_cents)}<br>${esc(t('goal.saved'))}: ${money(goal.current_saved_cents)}<br>${esc(t('goal.reserve'))}: ${money(goal.reserve_floor_cents)}</p><details><summary>${esc(t('evidence.formula'))}</summary><p>${esc(t('evidence.goalFormula'))}</p></details><p>${esc(t('evidence.noApproval'))}</p></section>`;
  }
  return `<p class="empty-state">${esc(t('support.unavailable'))}</p>`;
}
function showCalculation(context){if(!context||context.customerId!==state.customerId)return;state.calculationEvidence=context;$('calculation-content').innerHTML=calculationHTML(context);openDialog('calculation-dialog');}
function toolEvidenceHTML(response,result){
  const refs=[...new Set([...(result.transaction_refs||[]),...(result.comparison_transaction_refs||[]),...(result.scenario_band?.comparison_transaction_refs||[]),...(response.source_refs?.transaction_refs||[]),...(result.current?.transaction_refs||[]),...(result.previous?.transaction_refs||[]),...(result.comparison?.transaction_refs||[])])];
  const events=response.source_refs?.mortgage_event_refs||[];
  const scope=toolScope(response,state.selectedMonth);
  if(!scope.start&&result.start_month)scope.start=result.start_month+'-01';
  if(!scope.end&&result.end_month)scope.end=monthEnd(result.end_month);
  if((result.as_of||result.reference_date)&&!scope.end){scope.start=result.observed_start||state.observedStart;scope.end=result.as_of||result.reference_date;}
  if(response.tool_kind==='transaction_statistics_comparison'||response.tool_kind==='spending_comparison'){
    const periods=[result.current,result.previous,result.comparison].filter(Boolean);
    scope.start=periods.map(period=>period.start).filter(Boolean).sort()[0]||scope.start;
    scope.end=periods.map(period=>period.end).filter(Boolean).sort().at(-1)||scope.end;
  }
  return `<details class="coach-tool-evidence"><summary>${esc(t('coach.result.evidence',{count:refs.length+events.length}))}</summary><p>${esc(copy('Based on the selected account records and the dates shown above.','Perustuu valittuihin tilitapahtumiin ja yllä oleviin päivämääriin.','Baserat på valda kontoposter och datumen ovan.'))}</p>${refs.length?sourceButton(refs,{start:scope.start,end:scope.end,metric:response.query_scope?.metric,statistics:response.tool_kind==='transaction_statistics'?result:null,filters:result.filters||{}}):''}${events.length?`<p>${esc(copy('Historical home-financing records','Historialliset asuntorahoitustiedot','Historiska bostadsfinansieringsposter'))}: ${events.length}</p>`:''}</details>`;
}
async function completeCoachAnswer(response,context){
  if(response.needs_clarification||response.tool_result)return response;
  const params=response.parameters||{};
  let kind,result;
  if(response.intent==='preview_cashflow'){
    kind='cashflow_forecast';
    result=await request(context,'get','/api/forecast',{as_of:params.as_of||params.reference_date||((state.observedEnd&&state.observedEnd<monthEnd(context.month))?state.observedEnd:monthEnd(context.month))});
  }else if(response.intent==='investment_cashflow'){
    if(params.start||params.end)return {...response,needs_clarification:true,clarification_question:copy('Investment transfers are available by complete month. Which ending month and how many months would you like to review?','Sijoitussiirrot ovat saatavilla kokonaisilta kuukausilta. Mikä loppukuukausi ja kuinka monta kuukautta valitaan?','Investeringsöverföringar finns per hel månad. Vilken slutmånad och hur många månader vill du granska?'),explanation_blocks:[]};
    kind='investment_cashflow';result=await request(context,'get','/api/investments',{month:params.period||params.month||context.month,months:params.months||context.trendMonths});
  }else if(response.intent==='home_financing_history'){
    kind='home_financing_history';result=await request(context,'get','/api/financing',{goal_type:'home'});
  }else if(response.selected_candidate_id==='restaurant_change'){
    kind='spending_comparison';result=await request(context,'get','/api/comparison',comparisonQuery(params.period||params.month||context.month));
  }
  if(kind)return {...response,tool_kind:kind,tool_result:result};
  if(!response.clarification_question&&!(response.explanation_blocks||[]).some(block=>block.text?.trim()))return {...response,needs_clarification:true,clarification_question:copy('Which category and dates should I use? You can ask for a spending total, a comparison, or a saving experiment.','Mitä luokkaa ja päivämääriä käytetään? Voit kysyä menojen summaa, vertailua tai säästökokeilua.','Vilken kategori och vilka datum ska jag använda? Du kan fråga om utgifter, en jämförelse eller ett sparexperiment.'),clarification_options:[copy('How much did I spend on groceries?','Paljonko käytin ruokaostoksiin?','Hur mycket spenderade jag på matinköp?'),t('coach.question.safe')]};
  return response;
}
function scenarioBars(result){
  const before=result.actual_total_cents, saving=result.modeled_monthly_contribution_cents;
  if(!Number.isSafeInteger(before)||!Number.isSafeInteger(saving)||before<0||saving<0||saving>before)return '';
  const after=before-saving;
  return `<div class="scenario-bars" aria-label="${esc(copy('Observed and simulated spending','Havaitut ja simuloidut menot','Observerade och simulerade utgifter'))}"><div class="scenario-bar-row"><span>${esc(copy('Observed','Havaittu','Observerat'))}</span><strong>${money(before)}</strong><i style="width:100%" aria-hidden="true"></i></div><div class="scenario-bar-row is-projected"><span>${esc(copy('If you make this change','Jos teet tämän muutoksen','Om du gör ändringen'))}</span><strong>${money(after)}</strong><i style="width:${before?after/before*100:0}%" aria-hidden="true"></i></div></div>`;
}
function toolResultHTML(response){
  const result=response?.tool_result;if(!result)return '';
  if(response.tool_kind==='cashflow_forecast'){
    const summary=forecastSummary(result);
    return `<section class="coach-tool-result"><span class="status-pill scenario-pill">${esc(t('common.estimate'))}</span><h3>${esc(t('forecast.title'))}</h3><p class="small-text">${esc(copy('Reference date','Viitepäivä','Referensdag'))}: ${dateLabel(result.as_of||monthEnd(state.selectedMonth))}</p>${summary?`<dl class="coach-result-values"><dt>${esc(copy('Estimated ending balance','Arvioitu loppusaldo','Uppskattat slutsaldo'))}</dt><dd>${money(summary.end_cents)} · ${dateLabel(summary.end_date)}</dd><dt>${esc(copy('Lowest estimated balance','Pienin arvioitu saldo','Lägsta uppskattade saldo'))}</dt><dd>${money(summary.low_cents)} · ${dateLabel(summary.low_date)}</dd></dl>${runwayChart(forecastRows(result))}`:`<p>${esc(t('support.needsHistory'))}</p>`}<p class="small-text">${esc(copy('Based on past income and spending patterns. New bills and costs can change the result. The shaded area shows past variation, not a probability.','Perustuu aiempiin tulo- ja menomalleihin. Uudet laskut ja kulut voivat muuttaa arviota. Varjostus kuvaa aiempaa vaihtelua, ei todennäköisyyttä.','Bygger på tidigare inkomster och utgifter. Nya räkningar och kostnader kan ändra resultatet. Skuggningen visar historisk variation, inte sannolikhet.'))}</p>${toolEvidenceHTML(response,result)}</section>`;
  }
  if(response.tool_kind==='investment_cashflow')return `<section class="coach-tool-result"><span class="status-pill">${esc(t('common.observed'))}</span><h3>${esc(t('investment.title'))}</h3><p class="small-text">${esc(monthLabel(result.start_month||state.selectedMonth))} – ${esc(monthLabel(result.end_month||state.selectedMonth))}</p><dl class="coach-result-values"><dt>${esc(t('investment.contributions'))}</dt><dd>${money(result.total_contributions_cents)}</dd><dt>${esc(t('investment.withdrawals'))}</dt><dd>${money(result.withdrawals_cents)}</dd><dt>${esc(t('investment.consistency'))}</dt><dd>${esc(t('investment.monthsCount',{count:result.contribution_months,total:result.period_months}))}</dd></dl><p class="small-text">${esc(t('investment.limitation'))}</p>${toolEvidenceHTML(response,result)}</section>`;
  if(response.tool_kind==='home_financing_history'){
    const label=copy('Historical home-financing records','Historialliset asuntorahoitustiedot','Historiska bostadsfinansieringsuppgifter');
    if(!result.available)return `<section class="coach-tool-result"><h3>${esc(label)}</h3><p>${esc(copy('No linked home-financing history is available for this account. You can still explore a home savings wish.','Tälle tilille ei ole yhdistettyä asuntorahoitushistoriaa. Voit silti pohtia kotisäästötoivetta.','Ingen kopplad bostadsfinansieringshistorik finns för kontot. Du kan ändå utforska en sparönskan för ett hem.'))}</p></section>`;
    const fields=[[copy('Property estimate','Asunnon hinta-arvio','Uppskattat bostadspris'),result.property_price_cents],[copy('Requested loan','Haettu laina','Ansökt lån'),result.requested_loan_cents],[copy('Equity recorded then','Tuolloin kirjattu omarahoitus','Då registrerad egen insats'),result.equity_cents],[copy('Recorded fees','Kirjatut kulut','Registrerade avgifter'),result.recorded_fees_total_cents]];
    const outcome=result.recorded_outcome?.decision==='rejected'?copy('Historical application declined','Historiallinen hakemus hylätty','Historisk ansökan avslagen'):result.recorded_outcome?.decision==='approved'?copy('Historical application approved','Historiallinen hakemus hyväksytty','Historisk ansökan godkänd'):copy('Historical outcome unavailable','Historiallinen päätös puuttuu','Historiskt beslut saknas');
    return `<section class="coach-tool-result"><span class="status-pill">${esc(copy('Historical record','Historiatieto','Historisk uppgift'))}</span><h3>${esc(label)}</h3><p>${esc(outcome)}</p><dl class="coach-result-values">${fields.filter(([,value])=>Number.isSafeInteger(value)).map(([label,value])=>`<dt>${esc(label)}</dt><dd>${money(value)}</dd>`).join('')}</dl><p class="small-text">${esc(copy('These records describe a past application. They do not establish a current mortgage, household finances, available savings, or a new lending decision.','Tiedot kuvaavat aiempaa hakemusta. Ne eivät osoita nykyistä asuntolainaa, kotitalouden taloutta, käytettävissä olevia säästöjä tai uutta lainapäätöstä.','Uppgifterna gäller en tidigare ansökan. De fastställer inte ett nuvarande bolån, hushållets ekonomi, tillgängligt sparande eller ett nytt lånebeslut.'))}</p><details class="coach-tool-evidence"><summary>${esc(copy('View the recorded timeline','Näytä kirjattu aikajana','Visa den registrerade tidslinjen'))} · ${result.events?.length||0}</summary><ol>${(result.events||[]).map(event=>`<li><time>${dateLabel(event.timestamp)}</time><p>${esc(event.description||copy('Recorded financing event','Kirjattu rahoitustapahtuma','Registrerad finansieringshändelse'))}</p>${Number.isSafeInteger(event.expense_amount_cents)?`<strong>${money(event.expense_amount_cents)}</strong>`:''}</li>`).join('')}</ol></details></section>`;
  }
  if(response.tool_kind==='spending_comparison')return `<section class="coach-tool-result"><span class="status-pill">${esc(t('common.observed'))}</span><h3>${esc(t('story.title'))}</h3>${comparisonChart(normalizeComparison(result,result.current?.start?.slice(0,7)||state.selectedMonth))}<p>${esc(t('coach.result.delta',{amount:money(result.delta_cents)}))}</p>${toolEvidenceHTML(response,{...result,start:result.previous?.start,end:result.current?.end,transaction_refs:[...(result.current?.transaction_refs||[]),...(result.previous?.transaction_refs||[])]})}</section>`;
  if(response.tool_kind==='transaction_statistics'){
    const filter=filterSummary(result.filters,response.query_scope?.concept)||t('coach.result.allActivity');
    const largest=result.largest_outflow;
    const metric=response.query_scope?.metric||'outflow_total',value=metric==='transaction_count'?String(result.metric_value_count??result.outflow_count??result.transaction_count):money(result.metric_value_cents??(metric==='average_outflow'?result.average_outflow_cents:metric==='largest_outflow'?largest?.amount_cents:result.outflow_total_cents));
    const heading=metric==='inflow_total'?copy('Money received','Saapunut raha','Mottagna pengar'):metric==='consumption_total'?u('spending.all'):metric==='average_outflow'?t('coach.result.average'):metric==='transaction_count'?t('coach.result.count'):metric==='largest_outflow'?t('coach.result.largest'):filter;
    if(metric==='inflow_total'){
      const definition=response.query_scope?.concept==='All inflows'?copy('Includes incoming saving and investment transfers. This is money received, not earned income.','Sisältää saapuvat säästö- ja sijoitussiirrot. Tämä on saapunutta rahaa, ei ansiotuloa.','Inkluderar inkommande spar- och investeringsöverföringar. Detta är mottagna pengar, inte arbetsinkomst.'):result.filters?.transaction_type==='investment_withdrawal'?copy('Investment withdrawals are transfers, not investment returns or earnings.','Sijoitusnostot ovat siirtoja, eivät sijoitustuottoa tai ansiotuloa.','Investeringsuttag är överföringar, inte avkastning eller arbetsinkomst.'):copy('This is money credited to the account, not gross pay before tax.','Tämä on tilille saapunut raha, ei bruttopalkka ennen veroja.','Detta är pengar som kommit in på kontot, inte bruttolön före skatt.');
      return `<section class="coach-tool-result"><span class="status-pill">${esc(t('common.observed'))}</span><h3>${esc(heading)}</h3><p class="coach-result-amount">${esc(value)}</p><p class="small-text">${esc(filter)} · ${dateLabel(result.start)}–${dateLabel(result.end)}</p><dl class="coach-result-values"><dt>${esc(t('coach.result.count'))}</dt><dd>${esc(result.inflow_count??result.transaction_count)}</dd></dl><p class="small-text">${esc(definition)}</p>${toolEvidenceHTML(response,result)}</section>`;
    }
    return `<section class="coach-tool-result"><span class="status-pill">${esc(t('common.observed'))}</span><h3>${esc(heading)}</h3><p class="coach-result-amount">${esc(value)}</p><p class="small-text">${esc(filter)} · ${dateLabel(result.start)}–${dateLabel(result.end)}</p><dl class="coach-result-values"><dt>${esc(t('coach.result.count'))}</dt><dd>${esc(result.outflow_count??result.transaction_count)}</dd><dt>${esc(t('coach.result.average'))}</dt><dd>${money(result.average_outflow_cents)}</dd>${largest?`<dt>${esc(t('coach.result.largest'))}</dt><dd>${money(largest.amount_cents)} · ${dateLabel(largest.date)}</dd>`:''}</dl>${toolEvidenceHTML(response,result)}</section>`;
  }
  if(response.tool_kind==='transaction_statistics_comparison'){
    const current=result.current||{},comparison=result.comparison||{};
    const metric=response.query_scope?.metric||'outflow_total';
    const fields={inflow_total:'inflow_total_cents',outflow_total:'outflow_total_cents',consumption_total:'consumption_cents',average_outflow:'average_outflow_cents',transaction_count:'outflow_count'};
    const value=item=>metric==='largest_outflow'?item.largest_outflow?.amount_cents:item[fields[metric]];
    const format=amount=>Number.isSafeInteger(amount)?metric==='transaction_count'?new Intl.NumberFormat(i18n.localeTag).format(amount):money(amount):'—';
    const before=value(comparison),after=value(current),delta=Number.isSafeInteger(before)&&Number.isSafeInteger(after)?after-before:null;
    return `<section class="coach-tool-result"><span class="status-pill">${esc(t('common.observed'))}</span><h3>${esc(t('coach.result.comparison'))}</h3><p class="coach-result-amount">${esc(format(before))} → ${esc(format(after))}</p><p class="small-text">${dateLabel(comparison.start)}–${dateLabel(comparison.end)} → ${dateLabel(current.start)}–${dateLabel(current.end)}</p>${delta!==null?`<p>${esc(t('coach.result.delta',{amount:format(delta)}))}</p>`:''}${toolEvidenceHTML(response,result)}</section>`;
  }
  if(response.tool_kind==='spending_adjustment_preview'){
    return `<section class="coach-tool-result"><span class="status-pill scenario-pill">${esc(t('coach.result.unsaved'))}</span><h3>${esc(t('coach.result.adjustment',{category:categoryName(result.category),percent:result.percent}))}</h3><p class="coach-result-amount">${money(result.modeled_monthly_contribution_cents)} <small>${esc(t('common.perMonth'))}</small></p><p class="small-text">${dateLabel(result.start)}–${dateLabel(result.end)}</p>${scenarioBars(result)}<dl class="coach-result-values"><dt>${esc(t('coach.result.actual'))}</dt><dd>${money(result.actual_total_cents)}</dd><dt>${esc(t('coach.result.base'))}</dt><dd>${money(result.adjustable_base_cents)}</dd></dl><p class="small-text">${esc(t('coach.result.noMutation'))}</p>${toolEvidenceHTML(response,result)}</section>`;
  }
  if(response.tool_kind==='three_basket_profile'){
    const baskets=(result.baskets||[]).map(row=>`<div><dt>${esc(flowName(row.role))}</dt><dd>${money(row.amount_cents)}</dd></div>`).join('');
    return `<section class="coach-tool-result"><span class="status-pill">${esc(t('common.observed'))}</span><h3>${esc(t('coach.result.profile'))}</h3><p class="small-text">${esc(monthLabel(result.period))} · ${esc(t('coach.result.noScore'))}</p><dl class="coach-baskets">${baskets}<div class="coach-total"><dt>${esc(t('coach.result.total'))}</dt><dd>${money(result.total_consumption_cents)}</dd></div></dl>${toolEvidenceHTML(response,result)}</section>`;
  }
  if(response.tool_kind==='safe_to_spend'){
    if(!result.available)return `<section class="coach-tool-result"><span class="status-pill scenario-pill">${esc(t('common.estimate'))}</span><h3>${esc(t('safe.title'))}</h3><p>${esc(t('support.needsHistory'))}</p>${toolEvidenceHTML(response,result)}</section>`;
    const assumptions=(result.assumptions||[]).slice(0,4).map((_item,index)=>`<li>${esc(t(`safe.assumption.${index}`))}</li>`).join('');
    return `<section class="coach-tool-result"><span class="status-pill scenario-pill">${esc(t('common.estimate'))}</span><h3>${esc(t('safe.title'))}</h3><p class="coach-result-amount">${money(result.safe_to_spend_cents)}</p><p class="small-text">${esc(t('safe.amount',{days:result.horizon_days}))} · ${esc(t('safe.horizon',{date:dateLabel(result.horizon_end)}))}</p><dl class="coach-result-values"><dt>${esc(t('safe.reserve'))}</dt><dd>${money(result.reserve_floor_cents)}</dd><dt>${esc(t('safe.obligations'))}</dt><dd>${money(result.scheduled_outflows_cents)}</dd><dt>${esc(t('safe.everydayAllowance'))}</dt><dd>${money(result.historical_flexible_buffer_cents)}</dd></dl><p class="small-text">${esc(t('safe.demoReserve'))} ${esc(copy('Goal allocations and unsaved tax plans are not deducted. Expected bills come from past patterns; this is not a guarantee.','Tavoitteiden varauksia ja tallentamattomia verosuunnitelmia ei ole vähennetty. Odotetut laskut perustuvat aiempiin tapahtumiin; arvio ei ole takuu.','Målavsättningar och osparade skatteplaner är inte avdragna. Väntade räkningar bygger på tidigare mönster; detta är ingen garanti.'))}</p>${assumptions?`<details class="coach-tool-evidence"><summary>${esc(t('evidence.assumptions'))}</summary><ul>${assumptions}</ul></details>`:''}${toolEvidenceHTML(response,result)}</section>`;
  }
  if(response.tool_kind==='vat_estimate'){
    const amount=result.gross_spending_cents>0&&result.covered_spending_cents===0?copy('VAT estimate unavailable','ALV-arvio ei ole saatavilla','Momsuppskattning saknas'):`≈ ${money(result.estimated_vat_cents)}`;
    const rates=(result.by_rate||[]).map(rate=>`<li>${esc(t('vat.rateRow',{rate:percentage(rate.rate_basis_points),count:rate.transaction_count,amount:money(rate.estimated_vat_cents)}))}</li>`).join('');
    const uncovered=result.uncovered_spending_cents>0?`<dt>${esc(copy('Spending without a rate estimate','Menot ilman verokanta-arviota','Utgifter utan momssatsuppskattning'))}</dt><dd>${money(result.uncovered_spending_cents)}</dd>`:'';
    return `<section class="coach-tool-result"><span class="status-pill scenario-pill">${esc(t('common.estimate'))}</span><h3>${esc(t('vat.title'))}</h3><p class="coach-result-amount">${esc(amount)}</p><p class="small-text">${dateLabel(result.start)}–${dateLabel(result.end)}</p><dl class="coach-result-values"><dt>${esc(t('vat.gross'))}</dt><dd>${money(result.gross_spending_cents)}</dd><dt>${esc(t('vat.coverage'))}</dt><dd>${percentage(result.coverage_basis_points)}</dd>${uncovered}</dl><p class="small-text">${esc(t('vat.disclaimer'))}</p><details class="coach-tool-evidence"><summary>${esc(t('vat.breakdown'))}</summary><ul>${rates}</ul><p>${esc(t('vat.method'))}</p><p>${esc(t('vat.coverageNote'))}</p><p>${esc(t('vat.limitation.mixed'))}</p><p>${esc(t('vat.limitation.excise'))}</p></details>${toolEvidenceHTML(response,result)}</section>`;
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
function clearCoachEvidence(turns=state.conversation){
  for(const turn of turns)for(const key of turn.evidenceKeys||[])evidenceRegistry.delete(key);
}
function agentTurn(id){
  return state.conversation.find(turn=>turn.id===id&&turn.response.source==='agent'&&isCurrent(turn.context)&&turn.context.locale===i18n.locale);
}
function reviewAgentAction(turn,index){
  const action=turn.response.actions?.[index],params=action?.params;
  if(!params)return;
  if(action.kind==='open_view'&&['home','trends','goals','coach','profile'].includes(params.view)){navigate(params.view);return;}
  if(!['create_goal','save_scenario'].includes(action.kind)){v3?.handleAgentAction(turn,action);return;}
  if(action.kind==='create_goal'){
    closeDialogs();navigate('goals');$('goal-planner').open=true;
    $('goal-template').value='custom';$('goal-name').value=params.name;
    $('goal-target').value=(params.target_cents/100).toFixed(2);$('goal-date').value=params.target_date;
    $('goal-saved').value='0';$('goal-reserve').value='500';$('goal-target').focus();return;
  }
  if(action.kind==='save_scenario'){
    const saved=turn.savedActions?.[index];if(saved){beginGoalHandoff(saved);return;}
    agentProposal={turn,index,params:{name:params.name,category:params.category,percent:params.percent,month:params.month},context:turn.context};
    text('agent-action-description',t('agent.scenarioReview',{category:categoryName(params.category),percent:params.percent,month:monthLabel(params.month)}));
    text('agent-action-status','');openDialog('agent-action-dialog');
  }
}
function configureCoachAction(turn,action){
  const {response,message,wish,declaredPreference}=turn;
  if(response.needs_clarification&&!['plan_tax','plan_goal'].includes(response.intent)&&!['affordability_context','inference_unavailable','exploratory_goal'].includes(response.clarification_code))return false;
  let hasAction=true;
    if(response.needs_clarification&&response.clarification_code==='affordability_context'){action.textContent=copy('Plan a purchase','Suunnittele hankinta','Planera ett köp')+' ↗';action.onclick=()=>{closeDialogs();navigate('goals');$('goal-planner').open=true;$('goal-template').value='purchase';$('goal-name').value=t('goal.template.purchase');$('goal-target').focus();};}
    else if(response.needs_clarification&&response.clarification_code==='inference_unavailable'){action.textContent=u('journal.reflection')+' ↗';action.onclick=()=>{noteEditing=null;openNotebook();};}
    else if(response.tool_kind==='transaction_statistics'){action.textContent=t('coach.result.rows')+' ↗';action.onclick=()=>{closeDialogs();perform(action,next=>showTransactions(toolScope(response,next.month),next,{metric:response.query_scope?.metric,result:response.tool_result}));};}
    else if(response.tool_kind==='spending_adjustment_preview'){
      const contribution=response.tool_result.modeled_monthly_contribution_cents;
      action.textContent=`${copy('Plan a goal with','Suunnittele tavoite summalla','Planera ett mål med')} ${money(contribution)} / ${copy('month','kk','månad')} ↗`;
      action.onclick=()=>perform(action,async next=>{const preview=response.tool_result;const saved=await request(next,'post','/api/scenarios',{month:preview.start?.slice(0,7)||next.month,category:preview.category,percent:preview.percent,name:copy('My personal goal plan','Oma tavoitesuunnitelmani','Min personliga målplan'),confirmed:true});const focus=experience().load().focus,template=focus==='travel'?'trip':focus==='flexibility'?'custom':focus;beginGoalHandoff(saved.scenario||saved,template);});
    }
    else if(response.tool_kind==='three_basket_profile'){action.textContent=t('money.title')+' ↗';action.onclick=()=>{closeDialogs();navigate('trends');$('money-title').scrollIntoView({block:'start'});};}
    else if(response.tool_kind==='observed_tax_evidence'||response.intent==='plan_tax'){action.textContent=t('taxPlan.title')+' ↗';action.onclick=()=>{openDialog('coach-context-dialog');$('coach-more').open=true;$('coach-tax').open=true;$('coach-tax').scrollIntoView({block:'start'});$('tax-plan-amount').focus();};}
    else if(response.intent==='preview_cashflow'||response.intent==='safe_to_spend'||response.intent==='investment_cashflow'){action.textContent=copy('See this calculation','Katso tämä laskelma','Visa denna beräkning')+' ↗';action.onclick=()=>{const details=$('coach-support-'+turn.id);details.open=true;details.scrollIntoView({block:'nearest'});};}
    else if(response.intent==='plan_goal'){action.textContent=(wish?t('v2.goal.explore'):t('v2.wish.save'))+' ↗';action.onclick=()=>{closeDialogs();navigate('goals');if(wish){$('wishes-list').scrollIntoView({block:'nearest'});return;}const focus=declaredPreference?.value,template=focus==='travel'?'trip':focus==='flexibility'?'custom':focus||'custom';$('wish-title').value=template==='custom'?message.slice(0,80):t('goal.template.'+template);$('wish-title').dataset.template=template;$('wish-title').focus();};}
    else if(response.intent==='home_financing_history'){action.textContent=t('v2.wish.home')+' ↗';action.onclick=()=>{closeDialogs();navigate('goals');$('wish-title').dataset.template='home';$('wish-title').value=t('goal.template.home');$('wish-title').focus();};}
    else if(response.selected_candidate_id==='restaurant_change'){action.textContent=t('coach.result.rows')+' ↗';action.onclick=()=>perform(action,next=>showTransactions({category:'Restaurants'},next));}
    else hasAction=false;
  if(hasAction){const invoke=action.onclick;action.onclick=(...args)=>{if(!isCurrent(turn.context)||turn.context.locale!==i18n.locale||!state.conversation.includes(turn))return;return invoke(...args);};}
  return hasAction;
}
function resizeCoachInput(){
  const input=$('coach-input');input.style.height='auto';input.style.height=Math.min(112,Math.max(48,input.scrollHeight))+'px';
}
function scrollCoach(){ $('coach-end').scrollIntoView({block:'end'}); }
function clearCoachPending(cancel=false){
  if(coachTimer!==null){clearInterval(coachTimer);coachTimer=null;}
  if(cancel&&coachPending){actionSequence++;state.busy=false;}
  coachPending=null;text('coach-pending','');text('coach-live-status','');
  $('coach-send').disabled=false;
  if($('coach-send').dataset.loadingLabel){$('coach-send').textContent=$('coach-send').dataset.loadingLabel;delete $('coach-send').dataset.loadingLabel;}
  $('coach-response').setAttribute('aria-busy','false');
}
async function askCoach(message,context=captureContext(),wish=null){
  assertCurrent(context);if(coachPending)return;
  closeDialogs();
  if(state.view!=='coach')navigate('coach');
  const sequence=++coachSequence;coachPending={sequence,context};memoryProposal=null;
  $('coach-send').disabled=true;$('coach-response').setAttribute('aria-busy','true');
  $('coach-pending').innerHTML=`<p class="coach-turn-user">${esc(message)}</p><div class="coach-typing" aria-hidden="true"><i></i><i></i><i></i></div>`;
  let phase=0;text('coach-live-status',t('agent.looking'));
  coachTimer=setInterval(()=>{phase++;text('coach-live-status',t(phase%2?'agent.calculating':'agent.looking'));},4500);
  renderCoachContext();scrollCoach();
  try{
    const previousTurn=state.conversation.at(-1);
    const priceReply=message.trim().match(/^(?:(?:EUR|€)\s*)?(\d{1,6}(?:[.,]\d{1,2})?)(?:\s*(?:EUR|€|euros?))?[.!]?$/i);
    const continuingPurchase=priceReply&&previousTurn?.response?.clarification_code==='planned_purchase_cost'&&previousTurn.context&&isCurrent(previousTurn.context)&&previousTurn.context.locale===context.locale;
    const requestMessage=continuingPurchase?`${previousTurn.requestMessage||previousTurn.message}\nMy total budget is EUR ${priceReply[1].replace(',','.')}.`:message;
    // Explicit preference declarations retain their local consent flow.
    const declaredPreference=suggestedMemory(message,context.locale);
    const envelope=declaredPreference?{source:'deterministic'}:await context.api.agent(message,{month:context.month,locale:context.locale,conversation:state.conversation});
    assertCurrent(context);if(context.locale!==i18n.locale||sequence!==coachSequence)return;
    let response=envelope.source==='agent'?envelope:declaredPreference?{
      intent:declaredPreference.field==='focus'?'plan_goal':'preference_proposal',source:'local_preferences',needs_clarification:false,
      explanation_blocks:[{text:declaredPreference.field==='focus'?copy('A direction is enough to start. You can keep this as a wish without choosing an amount or deadline. Would you like to explore your spending first, or keep the wish for later?','Suunta riittää alkuun. Voit säilyttää tämän toiveena ilman summaa tai määräaikaa. Haluatko ensin tutkia menojasi vai säilyttää toiveen myöhemmäksi?','En riktning räcker för att börja. Du kan spara önskan utan belopp eller datum. Vill du utforska dina utgifter först eller spara önskan till senare?'):copy('You choose how your coach helps. Confirm the preference below to use it; nothing has been remembered yet.','Sinä päätät, miten valmentajasi auttaa. Vahvista toive alta, jos haluat käyttää sitä. Mitään ei ole vielä tallennettu.','Du väljer hur din coach hjälper. Bekräfta önskemålet nedan om du vill använda det. Inget har sparats ännu.')}],
    }:(continuingPurchase||state.queryScope)?await request(context,'post','/api/coach',{message:requestMessage,month:context.month,locale:context.locale,...(state.queryScope&&!continuingPurchase?{previous_query:state.queryScope}:{})}):envelope.legacy;
    if(!response)throw new Error(t('error.generic'));
    // Mark answers that fell back from the AI coach so testers can tell them apart.
    if(response.source!=='agent'&&envelope.fallback_reason&&envelope.fallback_reason!=='not_configured')response={...response,agent_fallback:envelope.fallback_reason};
    if(response.source!=='agent')response=await completeCoachAnswer(response,context);
    assertCurrent(context);
    if(context.locale!==i18n.locale||sequence!==coachSequence)return;
    state.queryScope=response.query_scope||null;
    const paragraphs=response.source==='agent'?response.answer:coachNarrative(response,{locale:i18n.locale,money,dateLabel,monthLabel,categoryName,flowName,selectedMonth:context.month});
    const content=paragraphs.join(' ');
    state.conversation.push({id:String(sequence),context,requestMessage,wish,declaredPreference,message:wish?copy(`Explore my wish: ${wish.title}`,`Tutkitaan toivettani: ${wish.title}`,`Utforska min önskan: ${wish.title}`):message,response,paragraphs,content});clearCoachEvidence(state.conversation.splice(0,Math.max(0,state.conversation.length-20)));
    const coachingStyle=experience().load().style;
    clearCoachEvidence();
    $('coach-response').innerHTML=state.conversation.map((turn,index)=>{
      if(turn.response.source==='agent')return agentTurnHTML(turn,{esc,t,charts:{barChart,trendChart,runwayChart},flowName,latest:index===state.conversation.length-1});
      const keysBefore=new Set(evidenceRegistry.keys());
      const result=turn.response.needs_clarification?'':toolResultHTML(turn.response);
      turn.evidenceKeys=[...evidenceRegistry.keys()].filter(key=>!keysBefore.has(key));
      const explanation=`<div class="coach-prose">${(turn.paragraphs||[turn.content]).filter(Boolean).map(paragraph=>`<p>${esc(paragraph)}</p>`).join('')}</div>`;
      const requestedVisual=/\b(?:chart|graph|plot|visuali[sz]\w*|kaavio\w*|diagram\w*)\b/i.test(turn.message);
      const support=result?`<details class="coach-support" id="coach-support-${turn.id}"${requestedVisual?' open':''}><summary>${esc(copy('See calculation and sources','Katso laskelma ja lähteet','Visa beräkning och källor'))}</summary>${result}</details>`:'';
      const turnAction=document.createElement('button');
      const retainedAction=index<state.conversation.length-1&&configureCoachAction(turn,turnAction)?`<button type="button" class="text-button coach-turn-action" data-coach-turn-action="${turn.id}">${esc(turnAction.textContent)}</button>`:'';
      const options=turn.response.clarification_options?.length?`<div class="clarification-options">${turn.response.clarification_options.map(option=>`<button type="button" data-direct-question="${esc(option)}">${esc(option)}</button>`).join('')}</div>`:'';
      const offline=turn.response.agent_fallback?`<span class="offline-tag" title="${esc(turn.response.agent_fallback)}">${esc(t('v3.offlineAnswer'))}</span>`:'';
      return `<article class="coach-turn"><p class="coach-turn-user">${esc(turn.message)}</p><div class="coach-turn-answer" data-coaching-style="${coachingStyle}">${offline}${explanation}${support}${retainedAction}${options}</div></article>`;
    }).join('');
    const scope=response.query_scope;
    if(scope)$('coach-response').insertAdjacentHTML('beforeend',`<p class="query-scope-caption">${esc(copy('Using','Käytössä','Använder'))}: ${dateLabel(scope.start)}–${dateLabel(scope.end)} · ${esc(scope.filters?.category?categoryName(scope.filters.category):scope.concept||u('spending.all'))}</p>`);
    const action=document.createElement('button');action.className='text-button';
    if(response.source!=='agent'&&configureCoachAction(state.conversation.at(-1),action)){$('coach-response').append(action);}
    const proposal=declaredPreference;
    if(proposal){memoryProposal={...proposal,customerId:context.customerId,generation:context.generation};$('coach-response').insertAdjacentHTML('beforeend',`<section class="memory-proposal"><h3>${esc(u('notebook.remember'))}</h3><p>${esc(proposal.text)}</p>${!experience().load().consent?`<label class="check-row"><input id="remember-consent" type="checkbox">${esc(u('personal.consent'))}</label><p class="small-text">${esc(u('personal.session'))}</p>`:''}<button type="button" class="secondary-button" data-confirm-memory>${esc(u('notebook.confirm'))}</button><button type="button" class="text-button" data-dismiss-memory>${esc(u('notebook.dismiss'))}</button></section>`);}
    if(response.source!=='agent')$('coach-response').insertAdjacentHTML('beforeend',`<div class="response-feedback"><span>${esc(copy('Did this help?','Oliko tästä apua?','Var detta till hjälp?'))}</span><button type="button" class="text-button" data-response-feedback="yes">${esc(copy('Yes','Kyllä','Ja'))}</button><button type="button" class="text-button" data-response-feedback="no">${esc(copy('Help me refine it','Tarkenna kysymystä','Hjälp mig precisera'))}</button><span id="response-feedback-message" role="status"></span></div>`);
    clearCoachPending();renderCoachContext();scrollCoach();
    text('coach-mode',t(response.source==='agent'?'agent.mode':response.source==='gemini'?'coach.aiMode':'coach.offlineMode'));
    $('coach-debug').hidden=!new URLSearchParams(globalThis.location?.search||'').has('debug');text('coach-debug-content',`${t('coach.debug.source')}: ${response.source||'—'} · ${t('coach.debug.fallback')}: ${response.fallback_reason||t('coach.debug.none')} · ${t('coach.debug.tool')}: ${response.tool_source||response.tool_kind||'—'}`);
  }catch(error){if(isCurrent(context)&&context.locale===i18n.locale&&sequence===coachSequence&&!(error instanceof StaleResponse)){clearCoachPending();renderCoachContext();text('coach-live-status',errorText(error)+' '+t('coach.fallback'));const retry=document.createElement('button');retry.className='text-button';retry.textContent=t('action.retry');retry.onclick=()=>perform(retry,next=>askCoach(message,next,wish));$('coach-live-status').append(retry);scrollCoach();}}
}
function unavailableAccount(error){explainError(error);text('current-balance','—');text('account-caption',t('error.account'));$('current-balance').classList.remove('skeleton');$('money-flow').innerHTML=`<p class="empty-state">${esc(t('error.database'))}</p>`;text('insight-headline',t('error.account'));if(!state.overview){$('home-baskets-content').innerHTML=`<p class="empty-state">${esc(t('support.unavailable'))}</p>`;$('spending-donut').innerHTML=`<p class="empty-state">${esc(t('support.unavailable'))}</p>`;$('spending-donut').setAttribute('aria-busy','false');}}
async function load(context=captureContext()){
  assertCurrent(context);const loadSequence=++state.loadSequence;notify(t('loading.account'));homeRecap=null;homeDataState='loading';renderMonthlyRecap();
  let initialOverview=null;
  if(!context.month){
    const [initial]=await Promise.allSettled([request(context,'get','/api/overview')]);
    if(!isCurrent(context)||loadSequence!==state.loadSequence)return;
    if(initial.status==='rejected'){homeDataState='unavailable';unavailableAccount(initial.reason);renderMonthlyRecap();renderSupport();return;}
    initialOverview=initial.value;context.month=initialOverview.month||initialOverview.latest_balance_date?.slice(0,7);
    state.selectedMonth=context.month;state.observedStart=initialOverview.observed_start;state.observedEnd=initialOverview.observed_end;
  }
  if(!context.month)return;
  const asOf=state.observedEnd&&monthEnd(context.month)>state.observedEnd?state.observedEnd:monthEnd(context.month);
  const results=await Promise.allSettled([
    initialOverview?Promise.resolve(initialOverview):request(context,'get','/api/overview',{month:context.month}),
    request(context,'get','/api/comparison',comparisonQuery(context.month)),
    request(context,'get','/api/trends',{month:context.month,months:context.trendMonths}),
    request(context,'get','/api/forecast',{as_of:asOf}),request(context,'get','/api/goals'),
    request(context,'get','/api/safe-to-spend',{as_of:asOf,horizon:'until_payday',reserve_floor_cents:50000}),
    request(context,'get','/api/investments',{month:context.month,months:context.trendMonths}),
    request(context,'get','/api/vat',{month:context.month}),
    request(context,'get','/api/transactions',{month:context.month})
  ]);
  if(!isCurrent(context)||loadSequence!==state.loadSequence)return;
  const [overview,comparison,trends,forecast,goals,safe,investments,vat,categoryRows]=results;
  state.categoryRowsAvailable=categoryRows.status==='fulfilled';
  state.categoryRows=state.categoryRowsAvailable?(categoryRows.value.transactions||[]):[];
  state.comparison=comparison.status==='fulfilled'?normalizeComparison(comparison.value,context.month):null;
  if(overview.status==='fulfilled'){state.overview=overview.value;homeDataState='ready';renderOverview();notify('');}else{homeDataState='unavailable';unavailableAccount(overview.reason);}
  renderComparison();
  state.trends=trends.status==='fulfilled'?trends.value:null;renderTrends();
  state.forecast=forecast.status==='fulfilled'?forecast.value:null;state.forecastAssumptions={};renderForecast();
  state.goals=goals.status==='fulfilled'?(goals.value.goals||[]):[];renderGoals();
  state.safeToSpend=safe.status==='fulfilled'?safe.value:null;state.investments=investments.status==='fulfilled'?investments.value:null;state.vat=vat.status==='fulfilled'?vat.value:null;renderSupport();renderVat();
  const persisted=state.overview?.scenarios?.filter(item=>item.category==='Restaurants'&&(!item.start||item.start.slice(0,7)===context.month)).at(-1);
  state.scenario=persisted||null;state.exclusion=persisted?.excluded_transaction_refs?.[0]||null;renderScenario();
  renderSpending();renderPersonalization();
  refreshMonthlyRecap();
  v3?.onLoad(context);
}
function changePeriod(selectedMonth,trendMonths=state.trendMonths){
  if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(selectedMonth)||!/^(?:[1-9]|1\d|2[0-4])$/.test(String(trendMonths)))return explainError(new Error(t('error.period')));
  if((state.observedStart&&selectedMonth<state.observedStart.slice(0,7))||(state.observedEnd&&selectedMonth>state.observedEnd.slice(0,7)))return explainError(new Error(t('error.period')));
  const keep={customerId:state.customerId,selectedMonth,trendMonths:Number(trendMonths),observedStart:state.observedStart,observedEnd:state.observedEnd,generation:state.generation+1,loadSequence:state.loadSequence+1,view:state.view};
  Object.assign(state,createState(),keep);clearScopedViews();navigate(keep.view);load();
}
function applyLanguage(){
  document.documentElement.lang=i18n.locale;setFormattingLocale(i18n.localeTag);configureCharts({locale:i18n.localeTag,translate:t});$('language').value=i18n.locale;
  for(const node of document.querySelectorAll('[data-i18n]'))node.textContent=t(node.dataset.i18n);
  for(const node of document.querySelectorAll('[data-i18n-aria]'))node.setAttribute('aria-label',t(node.dataset.i18nAria));
  for(const node of document.querySelectorAll('[data-i18n-placeholder]'))node.setAttribute('placeholder',t(node.dataset.i18nPlaceholder));
  for(const node of document.querySelectorAll('[data-ux]'))node.textContent=u(node.dataset.ux);
  for(const node of document.querySelectorAll('[data-ux-aria]'))node.setAttribute('aria-label',u(node.dataset.uxAria));
  for(const node of document.querySelectorAll('[data-v2]'))node.textContent=t('v2.'+node.dataset.v2);
  for(const node of document.querySelectorAll('[data-v2-placeholder]'))node.setAttribute('placeholder',t('v2.'+node.dataset.v2Placeholder));
  renderOverview();renderComparison();renderScenario();renderForecast();renderTrends();renderGoals();renderSupport();renderVat();
  const pending=state.pendingHandoff;
  if(pending){if(pending.createdGoalId)renderHandoffProgress(pending);else{text('goal-handoff',t('handoff.confirm',{amount:money(pending.contributionCents)}));text('goal-submit',t('handoff.submit',{amount:money(pending.contributionCents)})+' ↗');}}
  else clearHandoff();
  if(state.rows.length)renderRows(state.rows,state.transactionEvidence?.role?flowName(state.transactionEvidence.role):monthLabel(state.selectedMonth));
  if($('calculation-dialog').open&&state.calculationEvidence)$('calculation-content').innerHTML=calculationHTML(state.calculationEvidence);
  renderSpending();renderPersonalization();
}
v3=initV3({state,$,esc,t,money,dateLabel,monthLabel,shiftMonth,monthEnd,request,captureContext,isCurrent,perform,navigate,changePeriod,askCoach,showTransactions,openDialog,closeDialogs,explainError,notify,
  locale:()=>i18n.locale,categoryName,storage:localStore,localProfile:()=>experience().load(),
  refreshGoals:async context=>{await loadGoals(context);},
  refreshSupport:async context=>{try{const asOf=state.overview?.latest_balance_date||monthEnd(state.selectedMonth);const safe=await request(context,'get','/api/safe-to-spend',{as_of:asOf,horizon:'until_payday',reserve_floor_cents:50000});state.safeToSpend=safe;renderSupport();}catch{}}});
$('persona-button').addEventListener('click',()=>{const panel=$('persona-panel');panel.hidden=!panel.hidden;$('persona-button').setAttribute('aria-expanded',String(!panel.hidden));if(!panel.hidden)$('persona').focus();});
$('persona').addEventListener('change',()=>{selectPersona(state,$('persona').value);api=createAPI(state.customerId);clearScopedViews();navigate('home');load();});
$('open-story').addEventListener('click',event=>perform(event.currentTarget,context=>askCoach(t('home.recap.question',{period:monthLabel(context.month)}),context)));
$('show-transactions').addEventListener('click',event=>perform(event.currentTarget,context=>showTransactions({category:'Restaurants'},context)));
$('mark-one-off').addEventListener('click',event=>perform(event.currentTarget,markOneOff));
$('link-goal').addEventListener('click',()=>{if(state.scenario)beginGoalHandoff(state.scenario);});
$('goal-form').addEventListener('submit',event=>{event.preventDefault();perform(event.submitter,createGoal);});
$('wish-form').addEventListener('submit',event=>{
  event.preventDefault();
  try{
    const store=experience();if($('wish-remember').checked&&!store.load().consent)store.setConsent(true);
    store.addWish({title:$('wish-title').value,template:$('wish-title').dataset.template||'custom'});
    $('wish-title').value='';$('wish-title').dataset.template='custom';renderWishes();
    notify(copy('Your wish is here. You can explore the numbers when you are ready.','Toiveesi on tallessa. Voit tutkia summia, kun olet valmis.','Din önskan finns här. Utforska beloppen när du är redo.'));
  }catch(error){explainError(error);}
});
$('wish-title').addEventListener('input',()=>{$('wish-title').dataset.template='custom';});
$('demo-button').addEventListener('click',()=>openDialog('demo-dialog'));
for(const link of document.querySelectorAll('a.wordmark'))link.addEventListener('click',event=>{event.preventDefault();navigate('home');});
$('goal-template').addEventListener('change',()=>{$('goal-name').value=$('goal-template').value==='custom'?'':t('goal.template.'+$('goal-template').value);});
$('ask-coach').addEventListener('click',()=>openDialog('coach-dialog'));
$('coach-form').addEventListener('submit',event=>{event.preventDefault();const message=$('coach-input').value.trim();if(message&&!coachPending){return perform(event.submitter,context=>{$('coach-input').value='';resizeCoachInput();return askCoach(message,context);});}});
$('coach-input').addEventListener('input',resizeCoachInput);
$('coach-input').addEventListener('keydown',event=>{
  if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();if(!$('coach-send').disabled&&$('coach-input').value.trim())$('coach-form').requestSubmit($('coach-send'));}
});
$('coach-scope-button').addEventListener('click',()=>{renderCoachContext();openDialog('coach-context-dialog');});
$('coach-month').addEventListener('change',()=>changePeriod($('coach-month').value));
$('agent-action-form').addEventListener('submit',event=>{
  event.preventDefault();const proposal=agentProposal;
  if(!proposal||!agentTurn(proposal.turn.id))return;
  return perform(event.submitter,async context=>{
    const saved=await request(context,'post','/api/scenarios',{...proposal.params,confirmed:true});
    const scenario=saved.scenario||saved;
    proposal.turn.savedActions={...proposal.turn.savedActions,[proposal.index]:scenario};
    if(agentProposal!==proposal)return;
    agentProposal=null;closeDialogs();beginGoalHandoff(scenario);
  });
});
$('tax-plan-form').addEventListener('submit',event=>{event.preventDefault();perform(event.submitter,submitTaxPlan);});
$('undo-action').addEventListener('click',event=>perform(event.currentTarget,async context=>{await request(context,'post','/api/undo',{confirmed:true});state.scenario=null;state.exclusion=null;clearHandoff();await load(context);assertCurrent(context);if(!state.scenario)await ensureScenario(context);assertCurrent(context);renderScenario();notify(t('feedback.undo'));}));
$('reset-demo').addEventListener('click',event=>perform(event.currentTarget,async context=>{
  // Advance the reset owner's token; every overlapping request retains its old epoch.
  state.generation+=1;context.generation=state.generation;state.loadSequence+=1;
  await request(context,'post','/api/reset',{confirmed:true});
  const generation=state.generation+1,loadSequence=state.loadSequence+1;
  Object.assign(state,createState(),{customerId:context.customerId,generation,loadSequence,busy:true,view:state.view,selectedMonth:context.month,trendMonths:context.trendMonths,observedStart:state.observedStart,observedEnd:state.observedEnd});
  context.generation=generation;
  clearScopedViews({preserveLoading:true});
  await load(context);assertCurrent(context);
  notify(t('feedback.reset'));
}));
$('forecast-details').addEventListener('click',()=>{const panel=$('forecast-assumptions');panel.hidden=!panel.hidden;$('forecast-details').setAttribute('aria-expanded',String(!panel.hidden));});

document.addEventListener('click',event=>{
  if(v3?.handleClick(event))return;
  const categoryTarget=event.target.closest('[data-spending-category]');
  if(categoryTarget?.dataset?.spendingCategory){selectSpending(categoryTarget.dataset.spendingCategory,categoryTarget);return;}
  const button=event.target.closest('button');if(!button)return;
  if(button.dataset.coachTurnAction){
    const turn=state.conversation.find(item=>item.id===button.dataset.coachTurnAction);
    if(turn&&configureCoachAction(turn,button))return button.onclick();
    return;
  }
  if(button.hasAttribute('data-open-demos')){openDialog('demo-dialog');return;}
  if(button.dataset.demoStory){openDemoStory(button.dataset.demoStory).catch(explainError);return;}
  if(button.dataset.wishTemplate){$('wish-title').value=t('goal.template.'+button.dataset.wishTemplate);$('wish-title').dataset.template=button.dataset.wishTemplate;$('wish-title').focus();return;}
  if(button.dataset.wishDelete){experience().deleteWish(button.dataset.wishDelete);renderWishes();return;}
  if(button.dataset.wishExplore){
    const wish=experience().load().wishes.find(item=>item.id===button.dataset.wishExplore);if(!wish)return;
    return perform(button,context=>askCoach(copy('I want to save but I do not know how much','Haluan säästää, mutta en tiedä kuinka paljon','Jag vill spara men vet inte hur mycket'),context,wish));
  }
  if(button.dataset.wishPlan){
    const wish=experience().load().wishes.find(item=>item.id===button.dataset.wishPlan);if(!wish)return;
    $('goal-planner').open=true;$('goal-name').value=wish.title;$('goal-template').value=wish.template;$('goal-target').focus();return;
  }
  if(button.hasAttribute('data-open-coach')){closeDialogs();openDialog('coach-dialog');$('coach-input').focus();return;}
  if(button.dataset.agentEvidence){const turn=agentTurn(button.dataset.agentEvidence),item=turn?.response.evidence?.[Number(button.dataset.index)];if(item?.query)return perform(button,context=>showTransactions(item.query,context));return;}
  if(button.dataset.agentAction){const turn=agentTurn(button.dataset.agentAction);if(turn)reviewAgentAction(turn,Number(button.dataset.index));return;}
  if(button.dataset.agentSuggestion){const turn=agentTurn(button.dataset.agentSuggestion),message=turn?.response.suggestions?.[Number(button.dataset.index)];if(turn===state.conversation.at(-1)&&typeof message==='string')return perform(button,context=>askCoach(message,context));return;}
  if(button.dataset.directQuestion)return perform(button,context=>{openDialog('coach-dialog');return askCoach(button.dataset.directQuestion,context);});
  if(button.dataset.personalPlan)return perform(button,context=>{openDialog('coach-dialog');const category=categoryName(button.dataset.personalPlan);return askCoach(copy(`How much could I save if I reduced ${category} spending by 20%?`,`Kuinka paljon voisin säästää, jos vähennän ${category} 20 %?`,`Hur mycket kan jag spara om jag minskar ${category} med 20 %?`),context);});
  if(button.hasAttribute('data-open-notebook')){noteEditing=null;openNotebook();return;}
  if(button.hasAttribute('data-open-tour'))return showTour();
  if(button.dataset.tourTry){experience().markOnboarded();closeDialogs();renderPersonalization();if(button.dataset.tourTry==='spending'){navigate('trends');state.spendingGroup='everyday';const category=spendingCategories(state.categoryRows,'everyday')[0]?.category;selectSpending(category);$('money-title').scrollIntoView({block:'start'});}else if(button.dataset.tourTry==='coach'){openDialog('coach-dialog');$('coach-input').focus();}else openNotebook();return;}
  if(button.dataset.tourStep!==undefined)return showTour(Number(button.dataset.tourStep));
  if(button.hasAttribute('data-tour-done')||button.hasAttribute('data-tour-skip')){experience().markOnboarded();closeDialogs();renderPersonalization();if(button.hasAttribute('data-tour-done')){navigate('trends');$('spending-donut').scrollIntoView({block:'center',behavior:'smooth'});}return;}
  if(button.dataset.spendingGroup){state.spendingGroup=button.dataset.spendingGroup;state.selectedCategory=null;renderSpending();return;}
  if(button.hasAttribute('data-expand-categories')){state.categoryExpanded=!state.categoryExpanded;renderSpending();return;}
  if(button.dataset.categoryTransactions)return perform(button,context=>showTransactions({category:button.dataset.categoryTransactions,consumption_only:'true'},context));
  if(button.dataset.evidenceRows)return perform(button,async context=>{
    const evidence=evidenceRegistry.get(button.dataset.evidenceRows);if(!evidence||evidence.customerId!==context.customerId||evidence.generation!==context.generation)return;
    const filters={start:evidence.start||state.observedStart,end:evidence.end||state.observedEnd};
    const all=await fetchRows(filters,context),allowed=new Set(evidence.refs),rows=all.filter(row=>allowed.has(row.transaction_ref));
    assertCurrent(context);state.transactionEvidence={kind:'statistics',customerId:context.customerId,accountId:state.overview?.account_id,start:filters.start,end:filters.end,metric:evidence.metric,statistics:evidence.statistics,filters:evidence.filters||{},rows,transaction_refs:rows.map(row=>row.transaction_ref)};renderRows(rows,`${dateLabel(filters.start)}–${dateLabel(filters.end)}`);openDialog('transactions-dialog');
  });
  if(button.dataset.journalTransaction){const row=(state.categoryRows||[]).find(item=>item.transaction_ref===button.dataset.journalTransaction);if(row)showCalculation({kind:'transaction',customerId:state.customerId,accountId:state.overview?.account_id,row});return;}
  if(button.dataset.noteEdit){noteEditing=button.dataset.noteEdit;openNotebook();return;}
  if(button.dataset.noteDelete){experience().deleteNote(button.dataset.noteDelete);renderPersonalization();return;}
  if(button.hasAttribute('data-forget-profile')){experience().forget();noteEditing=null;memoryProposal=null;closeDialogs();renderPersonalization();renderWishes();notify(u(experience().isCleared()?'personal.forgotten':'personal.clearFailed'));return;}
  if(button.hasAttribute('data-confirm-memory')){
    const proposal=memoryProposal;if(!proposal||proposal.customerId!==state.customerId||proposal.generation!==state.generation)return;
    if($('remember-consent')?.checked)experience().setConsent(true);
    experience().save({[proposal.field]:proposal.value});experience().addNote({text:proposal.text,source:'confirmed_conversation'});memoryProposal=null;
    button.closest('.memory-proposal')?.remove();renderPersonalization();renderWishes();notify(personalStatus());return;
  }
  if(button.hasAttribute('data-dismiss-memory')){memoryProposal=null;button.closest('.memory-proposal')?.remove();return;}
  if(button.dataset.responseFeedback){text('response-feedback-message',button.dataset.responseFeedback==='yes'?copy('Good. You choose the next step.','Hyvä. Sinä päätät seuraavan askeleen.','Bra. Du väljer nästa steg.'):copy('Tell me the category, dates, or meaning you want to change.','Kerro, mitä luokkaa, päivämääriä tai määritelmää haluat muuttaa.','Berätta vilken kategori, vilka datum eller vilken definition du vill ändra.'));if(button.dataset.responseFeedback==='no')$('coach-input').focus();return;}
  if(button.hasAttribute('data-new-conversation')){clearCoachPending(true);agentProposal=null;clearCoachEvidence();state.queryScope=null;state.conversation=[];memoryProposal=null;coachSequence++;text('coach-response','');$('coach-input').value='';resizeCoachInput();text('coach-mode',t('coach.verified'));renderCoachContext();$('coach-input').focus();return;}
  if(button.dataset.view)navigate(button.dataset.view);
  if(button.dataset.coachQuestion)return perform(button,context=>askCoach(t(button.dataset.coachQuestion),context));
  if(button.dataset.coachGoalTemplate!==undefined){const target=button.dataset.coachGoalTemplate,concept={buffer:'an emergency buffer',home:'a home',vehicle:'a car',purchase:'a large purchase',custom:''}[target]||'';return perform(button,context=>askCoach(concept?copy(`I want to save for ${concept}.`,`Haluan säästää ${target==='buffer'?'hätävaraan':target==='home'?'kotiin':target==='vehicle'?'autoon':'hankintaan'}.`,`Jag vill spara till ${target==='buffer'?'en buffert':target==='home'?'ett hem':target==='vehicle'?'en bil':'ett stort köp'}.`):copy('I want to save but I do not know how much','Haluan säästää, mutta en tiedä kuinka paljon','Jag vill spara men vet inte hur mycket'),context));}
  if(button.dataset.goalTemplate!==undefined){closeDialogs();navigate('goals');const template=button.dataset.goalTemplate;$('goal-planner').open=true;$('goal-template').value=template;$('goal-name').value=template==='custom'?'':t('goal.template.'+template);$('goal-name').focus();return;}
  if(button.hasAttribute('data-open-vat'))return perform(button,context=>askCoach(copy('How much VAT is inside my purchases?','Paljonko arvonlisäveroa ostoksissani on?','Hur mycket moms ingår i mina köp?'),context));
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
document.addEventListener('keydown',event=>{const segment=event.target.closest?.('[data-spending-category]');if(segment?.dataset?.spendingCategory&&segment.tagName?.toLowerCase()!=='button'&&['Enter',' '].includes(event.key)){event.preventDefault();selectSpending(segment.dataset.spendingCategory,segment);}});
// Native dialogs provide Escape, focus trapping and restoration to the opener.
for(const dialog of document.querySelectorAll('dialog')) dialog.addEventListener('click',event=>{if(event.target===dialog){const box=dialog.getBoundingClientRect();if(event.clientY<box.top||event.clientY>box.bottom||event.clientX<box.left||event.clientX>box.right)dialog.close();}});
$('language').addEventListener('change',()=>{clearCoachPending(true);agentProposal=null;const retry=Boolean($('status-message').querySelector('button'));i18n.setLocale($('language').value);clearCoachEvidence();state.queryScope=null;state.conversation=[];memoryProposal=null;coachSequence++;text('coach-response','');text('coach-live-status','');$('coach-response').setAttribute('aria-busy','false');$('coach-input').value='';resizeCoachInput();text('coach-debug-content','');$('coach-debug').hidden=true;$('tax-plan-result').replaceChildren();notify(retry?t('error.generic'):'',retry);applyLanguage();refreshMonthlyRecap();v3?.onLanguage();});
$('selected-month').addEventListener('change',()=>changePeriod($('selected-month').value));
$('trend-range').addEventListener('change',()=>changePeriod(state.selectedMonth,Number($('trend-range').value)));
document.addEventListener('invalid',event=>event.target.setCustomValidity?.(t('error.validation')),true);
document.addEventListener('input',event=>event.target.setCustomValidity?.(''));
applyLanguage();
load();
