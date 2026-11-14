"""Boundary contracts for the dependency-free, accessible mobile client."""
import json
import os
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

WEB = Path(__file__).resolve().parents[1] / 'web'

class Document(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.elements = []
        self.feed(source)
    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

class WebContractTests(unittest.TestCase):
    def read(self, name):
        self.assertTrue((WEB / name).is_file(), f'{name} is required')
        return (WEB / name).read_text()

    def test_keyboard_landmarks_and_labeled_dialogs(self):
        doc = Document(self.read('index.html'))
        ids = {attrs['id']: (tag, attrs) for tag, attrs in doc.elements if 'id' in attrs}
        self.assertIn('main', [tag for tag, _ in doc.elements])
        self.assertTrue(any(tag == 'nav' and attrs.get('aria-label') for tag, attrs in doc.elements))
        for identifier in ('home-view', 'trends-view', 'goals-view', 'ask-coach', 'persona', 'reset-demo', 'undo-action'):
            self.assertIn(identifier, ids)
        for identifier in ('coach-dialog', 'calculation-dialog', 'transactions-dialog'):
            tag, attrs = ids[identifier]
            self.assertEqual(tag, 'dialog')
            self.assertIn(attrs.get('aria-labelledby'), ids)
        self.assertTrue(any(attrs.get('aria-live') == 'polite' for _, attrs in doc.elements))
        self.assertTrue(any(tag == 'a' and attrs.get('href') == '#main-content' for tag, attrs in doc.elements))

    def test_assets_stay_local_and_forms_have_labels(self):
        doc = Document(self.read('index.html'))
        labels = {attrs.get('for') for tag, attrs in doc.elements if tag == 'label'}
        for tag, attrs in doc.elements:
            if tag in ('script', 'link', 'img'):
                self.assertFalse(attrs.get('src', attrs.get('href', '')).startswith(('http:', 'https:', '//')))
            if tag in ('input', 'select', 'textarea') and attrs.get('type') != 'hidden':
                self.assertTrue(attrs.get('id') in labels or attrs.get('aria-label'), attrs)
        self.assertNotIn('@import', self.read('styles.css'))

    def test_adaptive_controls_and_supporting_cards_are_semantic(self):
        doc = Document(self.read('index.html'))
        ids = {attrs.get('id'): (tag, attrs) for tag, attrs in doc.elements}
        for identifier in ('language', 'selected-month', 'trend-range', 'safe-card', 'investment-card', 'vat-card', 'vat-content'):
            self.assertIn(identifier, ids)
        self.assertTrue(ids['selected-month'][0] == 'select' or ids['selected-month'][1].get('type') == 'month')
        self.assertTrue(any(tag == 'svg' and attrs.get('data-brand') == 'coach-step' for tag, attrs in doc.elements), 'Use an original coach mark')

    def test_coach_directory_tax_planner_and_free_text_are_semantic(self):
        doc = Document(self.read('index.html'))
        ids = {attrs.get('id'): (tag, attrs) for tag, attrs in doc.elements}
        for identifier in (
            'coach-topics', 'coach-spending', 'coach-cashflow', 'coach-investing',
            'coach-goals', 'coach-home-vehicle', 'coach-tax', 'tax-plan-form',
            'tax-plan-amount', 'tax-plan-saved', 'tax-plan-date',
            'tax-plan-location', 'tax-plan-result', 'coach-form', 'coach-input',
        ):
            self.assertIn(identifier, ids)
        labels = {attrs.get('for') for tag, attrs in doc.elements if tag == 'label'}
        for identifier in ('tax-plan-amount', 'tax-plan-saved', 'tax-plan-date', 'tax-plan-location', 'coach-input'):
            self.assertIn(identifier, labels)
        self.assertEqual(ids['tax-plan-form'][0], 'form')
        self.assertEqual(ids['coach-form'][0], 'form')
        self.assertIn('hidden', ids['coach-home-history'][1], 'Mortgage history must stay hidden until availability is verified')
        self.assertTrue(any(tag == 'option' and attrs.get('value') == 'CUST01331' for tag, attrs in doc.elements))

    def test_vat_lens_is_data_backed_and_transaction_level(self):
        source = self.read('app.js')
        for token in ('/api/vat', 'estimated_vat_cents', 'rate_basis_points', 'rate_source', 'mapping_quality', 'mapping_note', 'limitations', 'comparison_transaction_refs'):
            self.assertIn(token, source)
        self.assertIn('vat', self.read('state.js'))

    def node_module(self, name, body):
        if not shutil.which('node'):
            self.skipTest('Node is not installed')
        source = self.read(name)
        script = 'const module = await import("data:text/javascript;base64," + Buffer.from(' + json.dumps(source) + ').toString("base64"));\n' + body
        result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def node_app(self, body):
        """Execute the real app with a small DOM boundary and scoped API fixtures."""
        sources = {name: self.read(name) for name in ('app.js', 'api.js', 'state.js', 'charts.js', 'i18n.js')}
        harness = r'''
import assert from 'node:assert/strict';
const elements = new Map(), documentListeners = {}, calls=[];
class Element {
 constructor(id=''){this.id=id;this.textContent='';this.innerHTML='';this.value='';this.hidden=false;this.disabled=false;this.open=false;this.dataset={};this.listeners={};this.attributes={};this.children=[];this.classList={remove(){}};}
 addEventListener(name,callback){this.listeners[name]=callback;}
 setAttribute(name,value){this.attributes[name]=value;}
 removeAttribute(name){delete this.attributes[name];}
 hasAttribute(name){return name in this.attributes;}
 replaceChildren(...children){this.children=[...children];this.textContent=children.map(x=>typeof x==='string'?x:x.textContent||'').join('');this.innerHTML='';}
 append(child){this.children.push(child);this.textContent+=typeof child==='string'?child:child.textContent||'';}
 prepend(){} focus(){this.focused=true;} scrollIntoView(){this.scrolled=true;} insertAdjacentHTML(_position,html){this.innerHTML+=html;} remove(){}
 querySelector(selector){if(selector==='.dialog-notice')return null;return this;}
 showModal(){this.open=true;} close(){this.open=false;}
 closest(){return this;}
}
const get=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
globalThis.document={documentElement:new Element('html'),getElementById:get,createElement:()=>new Element(),createTextNode:value=>({textContent:value}),addEventListener:(name,cb)=>documentListeners[name]=cb,querySelectorAll:selector=>selector==='dialog[open]'?[...elements.values()].filter(x=>x.open):[]};
globalThis.window={scrollTo(){}};
const comparison={customer_id:'CUST00001',account_id:'ACC000001',current:{start:'2026-09-01',end:'2026-09-30',total_cents:22570,count:10,average_cents:2257,transaction_refs:['restaurant-current']},previous:{start:'2026-08-01',end:'2026-08-31',total_cents:11543,count:10,average_cents:1154,transaction_refs:['restaurant-previous']},delta_cents:11027,count_delta:0,fact_id:'restaurant-fact'};
const scenario={id:'scenario-a',customer_id:'CUST00001',category:'Restaurants',adjustable_base_cents:18923,monthly_contribution_cents:3785,excluded_transaction_refs:['restaurant-one-off']};
let pending=null;
function fixture(path,customer){
 if(path==='/api/overview')return {customer_id:customer,account_id:customer==='CUST00001'?'ACC000001':'ACC000676',month:'2026-09',observed_start:'2024-10-03',observed_end:'2026-09-30',latest_balance_cents:10000,latest_balance_date:'2026-09-30',flows:[],scenarios:[]};
 if(path==='/api/comparison')return {...comparison,customer_id:customer};
 if(path==='/api/transactions')return {transactions:[{transaction_ref:'restaurant-one-off',category:'Restaurants',date:'2026-09-10',amount_cents:-3647}]};
 if(path==='/api/scenarios'||path==='/api/scenarios/exclude')return {scenario};
 if(path==='/api/goals/link')return {goal:{id:'goal-a'},host_action:{goal_ref:'goal-a',scenario_ref:'scenario-a',cents:3785}};
 if(path==='/api/goals')return {goals:[]};
 if(path==='/api/coach')return {intent:'explain_change',selected_candidate_id:'restaurant_change',explanation_blocks:[{text:'OLD CUSTOMER RESPONSE',fact_ids:['restaurant-fact']}],source:'deterministic'};
 if(path==='/api/forecast')return {customer_id:customer,observed:[],projected:[],recurring_items:[],assumptions:[]};
 if(path==='/api/safe-to-spend')return {customer_id:customer,available:true,horizon_days:7,horizon_end:'2026-10-07',safe_to_spend_cents:12345,reserve_floor_cents:50000,scheduled_outflows_cents:12000,historical_flexible_buffer_cents:3456,transaction_refs:[],fact_id:'safe-fact'};
 if(path==='/api/investments')return {customer_id:customer,total_contributions_cents:20000,withdrawals_cents:5000,contribution_months:4,period_months:12,months:[],transaction_refs:[],fact_id:'investment-fact'};
 if(path==='/api/vat')return {customer_id:customer,start:'2026-09-01',end:'2026-09-30',gross_spending_cents:187866,estimated_vat_cents:21238,coverage_basis_points:10000,transactions:[],by_rate:[],transaction_refs:[],fact_id:'vat-fact',limitations:['server limitation evidence']};
 if(path==='/api/tax-plan')return {amount_cents:90000,already_set_aside_cents:10000,remaining_cents:80000,due_date:'2027-03-31',reference_date:'2026-09-30',remaining_monthly_periods:6,required_monthly_set_aside_cents:13334,current_balance_cents:10000,reserve_floor_cents:50000,available_after_full_set_aside_cents:0,upfront_funding_gap_cents:90000,source:'user_declared',scenario:true,observed:false,not_tax_advice:true,persistence:'not_saved',scenario_id:'tax-plan'};
 return {};
}
globalThis.fetch=async(url,options)=>{
 const parsed=new URL(url,'http://local'), body=options.body?JSON.parse(options.body):{};
 const customer=body.customer_id||parsed.searchParams.get('customer_id');calls.push({path:parsed.pathname,customer,body,query:Object.fromEntries(parsed.searchParams)});
 let data=fixture(parsed.pathname,customer);
 if(parsed.pathname==='/api/goals'&&options.method==='POST')data={goal:{id:'goal-a',name:body.name}};
 if(pending&&pending.path===parsed.pathname&&!pending.used){const held=pending;held.used=true;held.startedResolve();await held.gate;}
 return {ok:true,json:async()=>({ok:true,data})};
};
const dataURL=source=>'data:text/javascript;base64,'+Buffer.from(source).toString('base64');
let source=sources['app.js'].replace(/from ['"]\.\/([^'"]+)['"]/g,(_,file)=>'from "'+dataURL(sources[file])+'"');
source=source.slice(0,source.lastIndexOf('\nload();'))+'\nexport {state,ensureScenario,showStory,showTransactions,markOneOff,createGoal,loadGoals,askCoach,calculationHTML,load,toolResultHTML,submitTaxPlan};';
const app=await import(dataURL(source));
const settle=async()=>{for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));};
async function select(customer){get('persona').value=customer;get('persona').listeners.change();await settle();}
function hold(path){let release,startedResolve;const gate=new Promise(resolve=>release=resolve),started=new Promise(resolve=>startedResolve=resolve);pending={path,gate,startedResolve,used:false};return {started,release};}
function goalInputs(){get('goal-name').value='Old customer goal';get('goal-target').value='3000';get('goal-saved').value='0';get('goal-reserve').value='500';get('goal-template').value='custom';}
await select('CUST00001');
'''
        script = 'const sources=' + json.dumps(sources) + ';\n' + harness + '\n' + body
        result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr[-6500:])

    def test_delayed_customer_responses_cannot_write_into_another_persona(self):
        self.node_app(r'''
const operations=[
 ['/api/scenarios',()=>app.ensureScenario()],
 ['/api/scenarios/exclude',()=>app.markOneOff()],
 ['/api/comparison',()=>{app.state.comparison=null;return app.showStory();}],
 ['/api/overview',()=>app.load()],
 ['/api/transactions',()=>app.showTransactions()],
 ['/api/goals',()=>app.createGoal()],
 ['/api/goals/link',()=>{get('link-goal').listeners.click();return app.createGoal();}],
 ['/api/goals',()=>app.loadGoals()],
 ['/api/coach',()=>app.askCoach('Explain my pattern')],
 ['/api/forecast',()=>{const button=get('apply-preview');return documentListeners.click({target:button});}],
 ['/api/undo',()=>get('undo-action').listeners.click({currentTarget:get('undo-action')})],
 ['/api/reset',()=>get('reset-demo').listeners.click({currentTarget:get('reset-demo')})]
];
for(const [path,run] of operations){
 await select('CUST00001');goalInputs();if(path!=='/api/scenarios')app.state.scenario={...scenario};
 const held=hold(path);const task=Promise.resolve(run()).catch(error=>assert.equal(error.constructor.name,'StaleResponse'));await held.started;
 await select('CUST00676');const oldNotice=get('status-message').textContent,oldCoach=get('coach-response').textContent;
 held.release();await task;await settle();pending=null;
 assert.equal(app.state.customerId,'CUST00676',path+' replaced the selected customer');
 assert.equal(app.state.scenario,null,path+' leaked an old scenario');assert.equal(app.state.exclusion,null,path+' leaked an exclusion');
 assert.deepEqual(app.state.rows,[],path+' leaked source rows');assert.deepEqual(app.state.goals,[],path+' leaked goals');
 assert.equal(app.state.comparison.customer_id,'CUST00676',path+' leaked a comparison');
 assert.equal(app.state.forecast.customer_id,'CUST00676',path+' leaked forecast');
 assert.equal(get('status-message').textContent,oldNotice,path+' leaked a notice');assert.equal(get('coach-response').textContent,oldCoach,path+' leaked coach copy');
}
''')

    def test_calculation_context_does_not_mix_money_map_and_restaurants(self):
        self.node_app(r'''
app.state.comparison={...comparison,before:comparison.previous,after:comparison.current};app.state.scenario=scenario;
app.state.filter='fixed_obligation';app.state.overview.flows=[{role:'fixed_obligation',amount_cents:-62031,transaction_refs:['housing-row'],fact_id:'housing-fact'}];
const mapContext={kind:'money_map',customerId:'CUST00001',accountId:'ACC000001',month:'2026-09',start:'2026-09-01',end:'2026-09-30',label:'Regular essentials',amount_cents:62031,fact_ids:['housing-fact'],transaction_refs:['housing-row']};
const map=app.calculationHTML(mapContext);assert.ok(map.includes('housing-row'));assert.ok(map.includes('housing-fact'));
assert.ok(!map.includes('restaurant-fact'),'Map evidence must not contain restaurant fact IDs');assert.ok(!map.includes('restaurant-current'));assert.ok(!map.includes('€225.70'));assert.ok(!map.includes('€37.85'));
const restaurant=app.calculationHTML({kind:'restaurant',customerId:'CUST00001',accountId:'ACC000001',comparison:app.state.comparison,scenario,exclusion:'restaurant-one-off'});
assert.ok(restaurant.includes('restaurant-current'));assert.ok(restaurant.includes('restaurant-fact'));assert.ok(!restaurant.includes('housing-row'));assert.ok(!restaurant.includes('housing-fact'));assert.ok(restaurant.includes('€37.85'));
await app.showStory();assert.equal(app.state.filter,null,'Restaurant transition must clear the Money Map filter');
''')

    def test_direct_goal_creation_requires_explicit_scenario_handoff(self):
        self.node_app(r'''
app.state.scenario={...scenario};goalInputs();calls.length=0;
await app.createGoal();assert.equal(calls.filter(call=>call.path==='/api/goals/link').length,0,'Direct goal creation must not silently link a restored scenario');
goalInputs();get('link-goal').listeners.click();
assert.equal(app.state.pendingHandoff.scenarioId,'scenario-a');assert.ok(get('goal-handoff').textContent.includes('€37.85'));
assert.ok(get('goal-submit').textContent.includes('€37.85'),'Final submit must explicitly confirm the modeled link');
get('goal-form').listeners.submit({preventDefault(){},submitter:get('goal-submit')});await settle();assert.equal(calls.filter(call=>call.path==='/api/goals/link').length,1);
assert.equal(app.state.pendingHandoff,null,'Confirmed handoff must be consumed');
assert.ok(!get('goal-submit').textContent.includes('€37.85'),'Consumed handoff must not leave a link confirmation on the next goal');
''')

    def test_reset_invalidates_overlapping_load_without_reusing_sequence_or_busy_state(self):
        self.node_app(r'''
await select('CUST00676');
const originalFetch=globalThis.fetch;let resetApplied=false,refreshStartedResolve,refreshRelease;
const refreshStarted=new Promise(resolve=>refreshStartedResolve=resolve),refreshGate=new Promise(resolve=>refreshRelease=resolve);
globalThis.fetch=async(url,options)=>{
 const path=new URL(url,'http://local').pathname,wasBeforeReset=!resetApplied;
 const response=await originalFetch(url,options);
 if(path==='/api/reset')resetApplied=true;
 if(path==='/api/overview'&&!wasBeforeReset){refreshStartedResolve();await refreshGate;}
 const result=await response.json();
 if(wasBeforeReset&&path==='/api/overview')result.data.scenarios=[scenario];
 if(wasBeforeReset&&path==='/api/goals'&&options.method==='GET')result.data.goals=[{id:'old-goal',name:'Before reset',target_cents:300000}];
 return {...response,json:async()=>result};
};
const held=hold('/api/overview');get('persona').value='CUST00001';get('persona').listeners.change();await held.started;
const oldSequence=app.state.loadSequence;
const resetting=get('reset-demo').listeners.click({currentTarget:get('reset-demo')});await refreshStarted;
const busyDuringRefresh=app.state.busy,sequenceDuringRefresh=app.state.loadSequence;
refreshRelease();await resetting;held.release();await settle();
assert.deepEqual(app.state.goals,[],'A pre-reset load restored removed goals');assert.equal(app.state.scenario,null,'A pre-reset load restored a removed scenario');
assert.ok(sequenceDuringRefresh>oldSequence,'Reset must preserve monotonic request sequencing');assert.equal(busyDuringRefresh,true,'Reset must remain busy through its refresh');assert.equal(app.state.busy,false);
''')

    def test_period_controls_scope_all_requests_and_discard_old_range_results(self):
        self.node_app(r'''
assert.equal(app.state.selectedMonth,'2026-09');assert.equal(get('selected-month').min,'2024-10');assert.equal(get('selected-month').max,'2026-09');
const held=hold('/api/trends');const old=app.load();await held.started;
get('selected-month').value='2026-08';get('selected-month').listeners.change();await settle();
get('trend-range').value='6';get('trend-range').listeners.change();await settle();
const currentTrend=app.state.trends;held.release();await old;await settle();
assert.equal(app.state.selectedMonth,'2026-08');assert.equal(app.state.trendMonths,6);assert.equal(app.state.trends,currentTrend,'Old range response replaced the selected period');
await app.showTransactions();await app.ensureScenario();await app.askCoach('Explain the change');
assert.equal(calls.filter(c=>c.path==='/api/comparison').at(-1).query.comparison_month,'2026-07');
for(const path of ['/api/overview','/api/comparison','/api/transactions','/api/trends','/api/investments'])assert.equal(calls.filter(c=>c.path===path).at(-1).query.month,'2026-08',path);
assert.equal(calls.filter(c=>c.path==='/api/trends').at(-1).query.months,'6');
assert.equal(calls.filter(c=>c.path==='/api/scenarios').at(-1).body.month,'2026-08');
assert.equal(calls.filter(c=>c.path==='/api/coach').at(-1).body.month,'2026-08');
const safe=calls.filter(c=>c.path==='/api/safe-to-spend').at(-1);assert.equal(safe.query.as_of,'2026-08-31');assert.equal(safe.query.reserve_floor_cents,'50000');
assert.ok(!get('story-description').textContent.includes('September'));
''')

    def test_language_controls_format_dynamic_ui_and_scope_offline_coach_locale(self):
        self.node_app(r'''
get('language').value='fi';get('language').listeners.change();await settle();
assert.equal(document.documentElement.lang,'fi');assert.ok(get('scenario-amount').innerHTML.includes('€')||!app.state.scenario);
assert.ok(get('selected-month').innerHTML.includes('syyskuu 2026'),'Month choices must follow product locale, independent of the OS');
await app.ensureScenario();assert.ok(get('scenario-amount').innerHTML.includes('37,85'));assert.ok(get('scenario-detail').textContent.includes('20'));
await app.askCoach('Mikä muuttui?');assert.equal(calls.filter(c=>c.path==='/api/coach').at(-1).body.locale,'fi');
assert.ok(get('coach-response').textContent.includes('RESPONSE\n'),'Coach explanation and action need a text boundary');
get('language').value='sv';get('language').listeners.change();await settle();assert.equal(document.documentElement.lang,'sv');
assert.ok(get('goal-submit').textContent.includes('Skapa'));
''')

    def test_supporting_cards_use_server_values_and_have_unavailable_states(self):
        self.node_app(r'''
assert.ok(get('safe-content').innerHTML.includes('€123.45'));assert.ok(get('safe-content').innerHTML.includes('€500.00'));
assert.ok(get('investment-content').innerHTML.includes('€200.00'));assert.ok(get('investment-content').innerHTML.includes('€50.00'));
assert.ok(get('vat-content').innerHTML.includes('mapping coverage'));assert.ok(get('vat-content').innerHTML.includes('Excise'));
const originalFetch=globalThis.fetch;globalThis.fetch=async(url,options)=>{const path=new URL(url,'http://local').pathname;if(path==='/api/safe-to-spend')return {ok:true,json:async()=>({ok:true,data:{available:false,needs_history:true}})};if(path==='/api/investments')return {ok:false,status:503,json:async()=>({ok:false,error:{message:'Unavailable'}})};return originalFetch(url,options);};
await app.load();assert.ok(get('safe-content').innerHTML.includes('history'));assert.ok(get('investment-content').innerHTML.includes('unavailable'));
''')

    def test_coach_tool_results_render_exact_server_values_without_generic_action(self):
        self.node_app(r'''
const stats=app.toolResultHTML({tool_kind:'transaction_statistics',tool_fact_id:'taxi-fact',parameters:{period:'2026-09',category:'Transportation'},tool_result:{start:'2026-09-01',end:'2026-09-30',filters:{category:'Transportation'},outflow_total_cents:26680,transaction_count:6,average_outflow_cents:4447,largest_outflow:{amount_cents:6216,date:'2026-09-20'},transaction_refs:['a','b']}});
assert.ok(stats.includes('€266.80'));assert.ok(stats.includes('6'));assert.ok(stats.includes('€44.47'));assert.ok(stats.includes('taxi-fact'));
const adjustment=app.toolResultHTML({tool_kind:'spending_adjustment_preview',tool_fact_id:'scenario-fact',tool_result:{category:'Restaurants',percent:'20',actual_total_cents:22570,adjustable_base_cents:22570,modeled_monthly_contribution_cents:4514,persistence:'not_saved',transaction_refs:['r1']}});
assert.ok(adjustment.includes('€45.14'));assert.ok(adjustment.includes('€225.70'));assert.ok(adjustment.includes('20'));
const profile=app.toolResultHTML({tool_kind:'three_basket_profile',tool_fact_id:'profile-fact',tool_result:{period:'2026-09',total_consumption_cents:187866,baskets:[{role:'fixed_obligation',amount_cents:126690},{role:'flexible_essential',amount_cents:0},{role:'discretionary',amount_cents:61176}],transaction_refs:['p1']}});
assert.ok(profile.includes('€1,266.90'));assert.ok(profile.includes('€0.00'));assert.ok(profile.includes('€611.76'));assert.ok(profile.includes('profile-fact'));
const safe=app.toolResultHTML({tool_kind:'safe_to_spend',tool_fact_id:'safe-fact',tool_result:{available:true,horizon_days:7,horizon_end:'2026-10-07',safe_to_spend_cents:328831,reserve_floor_cents:50000,scheduled_outflows_cents:52838,historical_flexible_buffer_cents:40689,assumptions:['server assumptions remain auditable'],transaction_refs:['s1'],comparison_transaction_refs:['h1']}});
assert.ok(safe.includes('€3,288.31'));assert.ok(safe.includes('€500.00'));assert.ok(safe.includes('€528.38'));assert.ok(safe.includes('€406.89'));assert.ok(safe.includes('safe-fact'));
const noTax=app.toolResultHTML({tool_kind:'observed_tax_evidence',tool_fact_id:'tax-fact',tool_result:{available:false,observed_tax_paid_cents:null,records:[],transaction_refs:[],limitations:[]}});
assert.ok(noTax.toLowerCase().includes('no explicit tax'));
assert.equal(app.toolResultHTML({intent:'explain_change'}),'');
''')

    def test_vat_transaction_evidence_explains_broad_mapping(self):
        self.node_app(r'''
app.state.vat={transactions:[{transaction_ref:'vat-row',estimated_vat_cents:2550,rate_basis_points:2550,rate_source:{kind:'mcc',value:'7999'},mapping_quality:'broad_mcc_estimate',mapping_note:'Ambiguous recreation MCC 7999 uses the documented broad estimate'}]};
const html=app.calculationHTML({kind:'transaction',customerId:'CUST00001',accountId:'ACC000001',row:{transaction_ref:'vat-row',date:'2026-09-01',amount_cents:-12550,category:'Entertainment',mcc_code:'7999'}});
assert.ok(html.includes('Broad MCC estimate'));assert.ok(html.includes('MCC 7999'));assert.ok(html.includes('Ambiguous recreation MCC 7999'));
''')

    def test_tax_plan_posts_user_inputs_as_unsaved_scenario(self):
        self.node_app(r'''
get('tax-plan-amount').value='900';get('tax-plan-saved').value='100';get('tax-plan-date').value='2027-03-31';get('tax-plan-location').value='inside_current_balance';calls.length=0;
app.state.overview.latest_balance_date='2026-08-31';
await app.submitTaxPlan();
const call=calls.find(item=>item.path==='/api/tax-plan');assert.ok(call);assert.equal(call.body.amount_cents,90000);assert.equal(call.body.already_set_aside_cents,10000);assert.equal(call.body.reference_date,'2026-08-31');assert.equal(call.body.current_balance_cents,10000);assert.equal(call.body.reserve_floor_cents,50000);assert.equal(call.body.set_aside_location,'inside_current_balance');assert.equal(call.body.confirmed,true);
assert.ok(get('tax-plan-result').innerHTML.includes('€133.34'));assert.ok(get('tax-plan-result').innerHTML.includes('Reference date'));assert.ok(get('tax-plan-result').innerHTML.includes('Observed balance'));assert.ok(get('tax-plan-result').innerHTML.includes('€100.00'));assert.ok(get('tax-plan-result').innerHTML.includes('Reserve'));assert.ok(get('tax-plan-result').innerHTML.includes('€500.00'));assert.ok(get('tax-plan-result').innerHTML.toLowerCase().includes('not tax advice'));
''')

    def test_coach_directory_routes_questions_goals_and_vat(self):
        self.node_app(r'''
calls.length=0;
const taxi=get('directory-taxi');taxi.dataset.coachQuestion='coach.question.taxi';
await documentListeners.click({target:taxi});await settle();
const coachCall=calls.filter(item=>item.path==='/api/coach').at(-1);assert.ok(coachCall);assert.equal(coachCall.body.message,'How much did I spend on taxis last month?');
get('language').value='sv';get('language').listeners.change();await settle();
const tax=get('directory-tax');tax.dataset.coachQuestion='coach.question.taxRecords';await documentListeners.click({target:tax});await settle();
assert.equal(calls.filter(item=>item.path==='/api/coach').at(-1).body.message,'Kontrollera uttryckliga skatteuppgifter den här månaden');
const vehicle=get('directory-vehicle');vehicle.dataset.goalTemplate='vehicle';documentListeners.click({target:vehicle});
assert.equal(app.state.view,'goals');assert.equal(get('goal-template').value,'vehicle');assert.ok(get('goal-name').value);assert.equal(get('goal-name').focused,true);
const vat=get('directory-vat');vat.setAttribute('data-open-vat','');documentListeners.click({target:vat});
assert.equal(app.state.view,'trends');assert.equal(get('vat-card').scrolled,true);
''')

    def test_persona_and_language_changes_clear_scoped_coach_evidence(self):
        self.node_app(r'''
get('coach-home-history').hidden=false;get('persona').value='CUST00676';get('persona').listeners.change();
assert.equal(get('coach-home-history').hidden,true,'A previously available mortgage-history action leaked into the next persona');
get('coach-debug').hidden=false;get('coach-debug-content').textContent='old diagnostics';get('tax-plan-result').innerHTML='<p>old tax scenario</p>';
get('language').value='fi';get('language').listeners.change();
assert.equal(get('coach-debug').hidden,true);assert.equal(get('coach-debug-content').textContent,'');assert.equal(get('tax-plan-result').innerHTML,'');
''')

    def test_ask_coach_mounts_exact_tool_result_and_collapsed_diagnostics(self):
        self.node_app(r'''
const originalFetch=globalThis.fetch;
globalThis.fetch=async(url,options)=>{
 const path=new URL(url,'http://local').pathname;
 if(path==='/api/coach'){
  const body=JSON.parse(options.body);
  if(body.message==='transport')return {ok:true,json:async()=>({ok:true,data:{intent:'spending_adjustment',source:'deterministic',tool_kind:'spending_adjustment_preview',explanation_blocks:[{text:'Transport preview.'}],tool_result:{category:'Transportation',percent:'20',actual_total_cents:20000,adjustable_base_cents:15000,modeled_monthly_contribution_cents:3000,transaction_refs:['transport-row']}}})};
  if(body.message==='tax')return {ok:true,json:async()=>({ok:true,data:{intent:'observed_tax_evidence',source:'deterministic',tool_kind:'observed_tax_evidence',explanation_blocks:[{text:'No explicit tax rows.'}],tool_result:{available:false,transaction_refs:[]}}})};
  return {ok:true,json:async()=>({ok:true,data:{intent:'transaction_statistics',source:'deterministic',fallback_reason:'gemini_unavailable',tool_source:'local_statistics',tool_kind:'transaction_statistics',tool_fact_id:'taxi-fact',parameters:{period:'2026-09'},explanation_blocks:[{text:'Verified taxi activity.'}],tool_result:{start:'2026-09-01',end:'2026-09-30',filters:{category:'Transportation'},outflow_total_cents:26680,transaction_count:6,average_outflow_cents:4447,largest_outflow:{amount_cents:6216,date:'2026-09-20'},transaction_refs:['taxi-row']}}})};
 }
 return originalFetch(url,options);
};
await app.askCoach('How much did I spend on taxis last month?');
assert.ok(get('coach-response').innerHTML.includes('€266.80'));assert.ok(get('coach-response').innerHTML.includes('€44.47'));assert.ok(get('coach-response').innerHTML.includes('taxi-fact'));
assert.equal(get('coach-debug').hidden,false);assert.ok(get('coach-debug-content').textContent.includes('gemini_unavailable'));assert.ok(get('coach-debug-content').textContent.includes('local_statistics'));
await app.askCoach('transport');let action=get('coach-response').children.filter(child=>child?.onclick).at(-1);assert.ok(action.textContent.includes('Create a goal'));action.onclick();assert.equal(app.state.view,'goals');assert.equal(get('story-dialog').open,false);
await app.askCoach('tax');action=get('coach-response').children.filter(child=>child?.onclick).at(-1);assert.ok(action.textContent.includes('Plan a user-declared tax amount'));action.onclick();assert.equal(get('coach-tax').open,true);assert.equal(get('tax-plan-amount').focused,true);
''')

    def test_handoff_retries_link_failure_without_creating_a_second_goal(self):
        self.node_app(r'''
app.state.scenario={...scenario};goalInputs();get('link-goal').listeners.click();calls.length=0;
const originalFetch=globalThis.fetch;let linkAttempts=0;
globalThis.fetch=async(url,options)=>{
 const response=await originalFetch(url,options);
 if(new URL(url,'http://local').pathname==='/api/goals/link'&&++linkAttempts===1)return {ok:false,status:503,json:async()=>({ok:false,error:{message:'Link unavailable'}})};
 return response;
};
await assert.rejects(()=>app.createGoal(),/Link unavailable/);
await app.createGoal();
assert.equal(calls.filter(call=>call.path==='/api/goals'&&call.body.confirmed).length,1,'Retry created a duplicate goal after acknowledged creation');
assert.equal(linkAttempts,2);assert.equal(app.state.pendingHandoff,null);
''')

    def test_handoff_retries_host_failure_without_recreating_or_relinking(self):
        self.node_app(r'''
app.state.scenario={...scenario};goalInputs();get('link-goal').listeners.click();calls.length=0;
let hostAttempts=0;window.SCoachHost={attach_modeled_contribution:async(goal,cents,scenarioId)=>{hostAttempts++;assert.equal(goal,'goal-a');assert.equal(cents,3785);assert.equal(scenarioId,'scenario-a');if(hostAttempts===1)throw new Error('Host not ready');}};
await assert.rejects(()=>app.createGoal(),/Host not ready/);await app.createGoal();
assert.equal(calls.filter(call=>call.path==='/api/goals'&&call.body.confirmed).length,1,'Host retry recreated the already saved goal');
assert.equal(calls.filter(call=>call.path==='/api/goals/link').length,1,'Host retry repeated an acknowledged link');assert.equal(hostAttempts,2);assert.equal(app.state.pendingHandoff,null);
''')

    def test_handoff_reconciles_a_committed_link_after_lost_response(self):
        self.node_app(r'''
app.state.scenario={...scenario};goalInputs();get('link-goal').listeners.click();calls.length=0;
const originalFetch=globalThis.fetch;let committed=false,hostCalls=0;
window.SCoachHost={attach_modeled_contribution:()=>hostCalls++};
globalThis.fetch=async(url,options)=>{
 const response=await originalFetch(url,options),path=new URL(url,'http://local').pathname;
 if(path==='/api/goals/link'){committed=true;throw new Error('Link response lost');}
 if(path==='/api/goals'&&options.method==='GET'&&committed)return {ok:true,json:async()=>({ok:true,data:{goals:[{id:'goal-a',name:'Saved',linked_scenarios:[scenario],modeled_scenario_contribution_cents:3785}]}})};
 return response;
};
await assert.rejects(()=>app.createGoal(),/Link response lost/);await app.createGoal();
assert.equal(calls.filter(call=>call.path==='/api/goals'&&call.body.confirmed).length,1);assert.equal(calls.filter(call=>call.path==='/api/goals/link').length,1,'A committed link must be recovered rather than posted again');assert.equal(hostCalls,1);assert.equal(app.state.pendingHandoff,null);
''')

    def test_state_switch_clears_previous_persona_evidence(self):
        self.node_module('state.js', '''
import assert from 'node:assert/strict';
const s = module.createState(); s.comparison = {old:true}; s.scenario={old:true};
module.selectPersona(s, 'CUST00676');
assert.equal(s.customerId, 'CUST00676'); assert.equal(s.comparison, null); assert.equal(s.scenario, null);
assert.equal(module.money(3785), '€37.85');
assert.equal(module.money(null), '—');
assert.equal(module.escapeHTML('<img src=x>'), '&lt;img src=x&gt;');
''')

    def test_api_sends_scoped_requests_and_surfaces_server_errors(self):
        self.node_module('api.js', '''
import assert from 'node:assert/strict';
const calls=[];
globalThis.fetch=async (url, options)=>{calls.push({url,options}); return {ok:true,json:async()=>({ok:true,data:{value:42}})}};
const api=module.createAPI('CUST00001');
const value=await api.get('/api/comparison',{category:'Restaurants'});
assert.equal(value.value,42); assert.ok(calls[0].url.includes('customer_id=CUST00001'));
assert.ok(calls[0].url.includes('category=Restaurants'));
await api.post('/api/undo',{});
assert.equal(JSON.parse(calls[1].options.body).customer_id,'CUST00001');
globalThis.fetch=async()=>({ok:false,status:400,json:async()=>({error:{message:'Invalid period'}})});
await assert.rejects(()=>api.get('/api/overview'),/Invalid period/);
''')

    def test_forecast_api_shape_keeps_scenario_visually_separate(self):
        self.node_module('state.js', """
import assert from 'node:assert/strict';
const rows=module.forecastRows({observed:[{date:'2026-09-30',balance_cents:10000,observed:true}],projected:[{date:'2026-10-01',balance_cents:9000,observed:false,historical_flexible_scenarios:{p25:100,p50:200,p75:300}}]});
assert.equal(rows.length,2);assert.equal(rows[0].status,'observed');assert.equal(rows[1].status,'scenario');
assert.equal(rows[1].historical_flexible_scenarios.p75,300);
assert.equal(module.eurosToCents('37.85'),3785);
assert.throws(()=>module.eurosToCents('2.005'));
""")

    def test_forecast_copy_describes_pattern_evidence_without_claiming_confirmation(self):
        source = self.read('i18n.js')
        self.assertNotIn('confirmed recurring items', source.lower())
        self.assertIn('qualified recurring patterns', source.lower())

    def test_story_has_bound_controls_and_local_module_imports(self):
        source = self.read('app.js')
        import re
        doc = Document(self.read('index.html'))
        ids = {attrs['id'] for _, attrs in doc.elements if 'id' in attrs}
        for identifier in ('open-story', 'mark-one-off', 'link-goal', 'show-transactions', 'goal-form', 'coach-form', 'reset-demo', 'undo-action'):
            self.assertIn(identifier, ids)
            self.assertIn(identifier, source)
        for relative in re.findall(r"from ['\"](\./[^'\"]+)['\"]", source):
            self.assertTrue((WEB / relative).is_file())
        for endpoint in ('/api/overview', '/api/comparison', '/api/transactions', '/api/scenarios', '/api/scenarios/exclude', '/api/goals/link', '/api/coach', '/api/undo', '/api/reset'):
            self.assertIn(endpoint, source)

    def test_accessible_charts_handle_empty_and_untrusted_labels(self):
        self.node_module('charts.js', '''
import assert from 'node:assert/strict';
assert.match(module.comparisonChart({before:{total_cents:11543,count:10},after:{total_cents:22570,count:10}}), /role="img"/);
assert.match(module.trendChart([]), /No complete periods/);
assert.ok(!module.flowChart([{label:'<img>',total_cents:100}]).includes('<img>'));
assert.match(module.runwayChart([{balance_cents:100,date:'2026-09-30'},{balance_cents:90,date:'2026-10-01',status:'scenario'}]),/stroke-dasharray/);
''')

    def test_runway_renders_historical_variation_as_a_labeled_band(self):
        self.node_module('charts.js', '''
import assert from 'node:assert/strict';
const chart=module.runwayChart([{balance_cents:10000,status:'observed'}, {balance_cents:9000,status:'scenario',historical_flexible_scenarios:{p25:8500,p50:9000,p75:9500}}]);
assert.match(chart, /<polygon/);assert.match(chart,/Historical variation/);assert.match(chart,/not a probability interval/);
''')

    def test_income_is_an_input_to_the_money_map_not_an_outflow(self):
        self.node_module('charts.js', '''
import assert from 'node:assert/strict';
const chart=module.flowChart([{role:'income',label:'Income',total_cents:10000},{role:'fixed_obligation',label:'Regular essentials',total_cents:6000},{role:'saving_or_transfer',label:'Saving',total_cents:1000}]);
assert.match(chart,/Income: €100.00/);assert.match(chart,/Outflows: €70.00/);
''')

    def test_chart_does_not_calculate_an_average_missing_from_api(self):
        self.node_module('charts.js', '''
import assert from 'node:assert/strict';
const chart=module.comparisonChart({before:{total_cents:100,count:3},after:{total_cents:100,count:3}});
assert.ok(!chart.includes('€0.33 average'),'Missing verified average must not be calculated in the client');
''')

    def test_twenty_four_month_trend_keeps_labels_readable_and_all_values_accessible(self):
        self.node_module('charts.js', '''
import assert from 'node:assert/strict';
const rows=Array.from({length:24},(_,index)=>({month:'period-'+index,total_cents:10000+index}));
const chart=module.trendChart(rows);assert.ok((chart.match(/class="chart-note"/g)||[]).length<=8,'Twenty-four labels overlap on a phone');assert.ok(chart.includes('period-23'));assert.ok(chart.includes('€100.23'),'Accessible description must retain each value');
''')

@unittest.skipUnless(os.environ.get('SCOACH_PLAYWRIGHT_PATH'), 'Set SCOACH_PLAYWRIGHT_PATH for optional browser integration')
class BrowserFlowTests(unittest.TestCase):
    def test_phone_primary_flow_refresh_goal_and_keyboard(self):
        from scoach.api import Application, create_server
        database = WEB.parent / 'var/scoach.sqlite3'
        if not database.is_file():
            self.skipTest('Build the demo database first')
        with tempfile.TemporaryDirectory() as directory:
            isolated = Path(directory) / 'test.sqlite3'
            shutil.copy2(database, isolated)
            server = create_server(Application(isolated), host='127.0.0.1', port=0)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            env = {**os.environ, 'SCOACH_TEST_URL': f'http://127.0.0.1:{server.server_port}'}
            script = r"""
const assert = require('node:assert/strict');
const {chromium} = require(process.env.SCOACH_PLAYWRIGHT_PATH);
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,chromiumSandbox:true});
 try {
 const page=await browser.newPage({viewport:{width:390,height:844}}), base=process.env.SCOACH_TEST_URL;
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.request.post(base+'/api/reset',{data:{customer_id:'CUST00001',confirmed:true}});
 await page.goto(base);await page.waitForFunction(()=>!document.querySelector('#open-story').disabled);
 const bounds=await page.locator('#open-story').boundingBox();assert.ok(bounds.y+bounds.height<710,'Primary action must appear above the dock');
 if(process.env.SCOACH_SCREENSHOT_DIR)await page.screenshot({path:process.env.SCOACH_SCREENSHOT_DIR+'/scoach-home.png',fullPage:true});
 await page.locator('#open-story').click();await page.waitForFunction(()=>document.querySelector('#scenario-amount').textContent.includes('45.14'));
 await page.locator('#mark-one-off').click();await page.waitForFunction(()=>document.querySelector('#scenario-amount').textContent.includes('37.85'));
 if(process.env.SCOACH_SCREENSHOT_DIR)await page.screenshot({path:process.env.SCOACH_SCREENSHOT_DIR+'/scoach-story.png',fullPage:true});
 await page.locator('#undo-action').click();await page.waitForFunction(()=>document.querySelector('#scenario-amount').textContent.includes('45.14'));
 await page.locator('#mark-one-off').click();await page.waitForFunction(()=>document.querySelector('#scenario-amount').textContent.includes('37.85'));
 assert.match(await page.locator('#comparison-chart').textContent(),/€225.70/);
 await page.locator('#show-transactions').click();await page.waitForFunction(()=>document.querySelectorAll('.transaction-row').length===10);
 await page.keyboard.press('Escape');assert.ok(await page.locator('#story-dialog').isVisible());
 await page.getByRole('button',{name:'How is this calculated?'}).click();
 assert.match(await page.locator('#calculation-content').innerText(),/€189.23/);assert.match(await page.locator('#calculation-content').innerText(),/€225.70/);
 await page.keyboard.press('Escape');await page.reload();await page.waitForFunction(()=>!document.querySelector('#open-story').disabled);
 await page.locator('#open-story').click();await page.waitForFunction(()=>document.querySelector('#scenario-amount').textContent.includes('37.85'));
 await page.locator('#link-goal').click();await page.locator('#goal-name').fill('A summer in Italy');await page.locator('#goal-target').fill('3000');
 await page.getByRole('button',{name:'Create plan & link €37.85 / month'}).click();await page.waitForFunction(()=>document.querySelector('#goals-list').textContent.includes('A summer in Italy'));
 assert.match(await page.locator('#goals-list').innerText(),/€37.85 modeled monthly contribution linked/);
 if(process.env.SCOACH_SCREENSHOT_DIR)await page.screenshot({path:process.env.SCOACH_SCREENSHOT_DIR+'/scoach-goal.png',fullPage:true});
 await page.getByRole('button',{name:'Trends',exact:true}).click();assert.ok(await page.getByRole('heading',{name:'Same month, last year'}).isVisible());
 assert.ok(await page.getByRole('heading',{name:'Salary, on its own'}).isVisible());
 await page.getByRole('button',{name:'Home',exact:true}).click();
 await page.locator('#ask-coach').click();await page.locator('#coach-spending>summary').click();await page.getByRole('button',{name:'What changed in restaurants?'}).click();
 await page.waitForFunction(()=>document.querySelector('#coach-response').textContent.includes('average'));await page.keyboard.press('Escape');
 await page.locator('#forecast-details').click();assert.ok(await page.locator('[data-assumption]').count()>0);
 await page.locator('#apply-preview').click();await page.waitForFunction(()=>document.querySelector('#status-message').textContent.includes('recalculated'));
 const dayField=page.locator('[data-field=day]').first();await dayField.fill('17');await page.locator('#apply-preview').click();await page.waitForFunction(()=>!document.querySelector('#apply-preview').disabled);
 assert.equal(await dayField.inputValue(),'17','Edited preview assumptions remain visible');
 for(const width of [320,390,768,1280,1440]){
  await page.setViewportSize({width,height:900});await page.reload();await page.waitForFunction(()=>!document.querySelector('#open-story').disabled);await page.getByRole('button',{name:'Home',exact:true}).click();assert.equal(await page.locator('#status-message').innerText(),'','A fresh load must not announce an edit');assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No horizontal overflow at '+width);
  const workspace=await page.locator('.phone-shell').boundingBox();if(width===768)assert.ok(workspace.width>=650,'Tablet must use the available width');
  if(width>=920){assert.ok(workspace.width>=1000,'Desktop must be a real workspace');const money=await page.locator('.money-card').boundingBox(),priority=await page.locator('.priority-section').boundingBox();assert.notEqual(Math.round(money.x),Math.round(priority.x),'Desktop Home must use two columns');assert.ok((await page.locator('nav').boundingBox()).y<160,'Desktop navigation must be visible near the top');assert.equal(await page.locator('.desktop-intro').count(),0);}
  if(process.env.SCOACH_SCREENSHOT_DIR)await page.screenshot({path:process.env.SCOACH_SCREENSHOT_DIR+'/scoach-7a-en-'+width+'.png'});
  if(width>=920){await page.locator('.skip-link').focus();await page.keyboard.press('Enter');const nav=await page.locator('nav').boundingBox(),main=await page.locator('#main-content').boundingBox();assert.ok(main.y>=nav.y+nav.height-1,'Sticky navigation must not cover the focused main target');}
  if(width===1280){
   await page.getByRole('button',{name:'Trends',exact:true}).click();const cards=page.locator('#trends-view>.white-card');assert.notEqual((await cards.nth(0).boundingBox()).x,(await cards.nth(1).boundingBox()).x);
   if(process.env.SCOACH_SCREENSHOT_DIR)await page.screenshot({path:process.env.SCOACH_SCREENSHOT_DIR+'/scoach-7a-trends-desktop.png'});
   await page.getByRole('button',{name:'Goals',exact:true}).click();assert.notEqual((await page.locator('#goals-list').boundingBox()).x,(await page.locator('#goal-form').boundingBox()).x);
   if(process.env.SCOACH_SCREENSHOT_DIR)await page.screenshot({path:process.env.SCOACH_SCREENSHOT_DIR+'/scoach-7a-goals-desktop.png'});
  }
  if(width===320){await page.getByRole('button',{name:'Goals',exact:true}).click();assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Goal form overflow on a small phone');await page.getByRole('button',{name:'Home',exact:true}).click();}
 }
 await page.locator('#persona-button').click();await page.locator('#persona').selectOption('CUST00676');await page.waitForFunction(()=>document.querySelector('#account-caption').textContent.includes('ACC000676'));
 assert.ok(!(await page.locator('#insight-headline').innerText()).includes('€110.27'));
 await page.locator('#persona').selectOption('CUST00001');await page.waitForFunction(()=>document.querySelector('#account-caption').textContent.includes('ACC000001'));
 await page.locator('#reset-demo').click();await page.waitForFunction(()=>document.querySelector('#status-message').textContent.includes('Demo reset'));
 await page.locator('#persona-button').click();
 await page.route('**/api/transactions?**',route=>route.fulfill({json:{ok:true,data:{transactions:[]}}}));
 await page.locator('#open-story').click();await page.locator('#show-transactions').click();await page.getByText('No transactions match this selection.',{exact:false}).waitFor();
 await page.keyboard.press('Escape');await page.keyboard.press('Escape');await page.unroute('**/api/transactions?**');
 await page.route('**/api/overview?**',route=>route.fulfill({status:503,json:{ok:false,error:{message:'Database unavailable for test'}}}));
 await page.reload();await page.getByText('Database unavailable for test',{exact:false}).waitFor();assert.equal(await page.locator('#current-balance').innerText(),'—');
 await page.unroute('**/api/overview?**');await page.getByRole('button',{name:'Try again',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#current-balance').textContent.includes('4,723.58'));
 if(process.env.SCOACH_SCREENSHOT_DIR)await page.screenshot({path:process.env.SCOACH_SCREENSHOT_DIR+'/scoach-desktop.png',fullPage:true});
 const localized=await browser.newPage({locale:'fi-FI',viewport:{width:390,height:844}});localized.on('pageerror',error=>errors.push(error.message));
 const coachLocales=[];localized.on('request',request=>{if(request.url().endsWith('/api/coach'))coachLocales.push(request.postDataJSON().locale);});
 await localized.goto(base);await localized.waitForFunction(()=>!document.querySelector('#open-story').disabled);assert.equal(await localized.locator('html').getAttribute('lang'),'fi','Browser language should be the initial choice');
 for(const locale of ['fi','sv']){
  if(locale==='sv'){await localized.locator('#language').selectOption('sv');await localized.reload();await localized.waitForFunction(()=>!document.querySelector('#open-story').disabled);}
  assert.equal(await localized.locator('html').getAttribute('lang'),locale);assert.ok((await localized.locator('#current-balance').innerText()).includes(',58'));
  assert.ok((await localized.locator('#selected-month option:checked').innerText()).includes(locale==='fi'?'syyskuu':'september'));
  assert.equal(await localized.locator('#home-title').innerText(),locale==='fi'?'Tuore näkymä raha-asioihisi':'En ny bild av din ekonomi');
  assert.ok(!(await localized.locator('#flow-legend').innerText()).includes('Regular essentials'));assert.ok(!(await localized.locator('body').innerText()).match(/\{[a-z]+\}/));
  if(process.env.SCOACH_SCREENSHOT_DIR)await localized.screenshot({path:process.env.SCOACH_SCREENSHOT_DIR+'/scoach-7a-'+locale+'-home.png'});
  for(const width of [320,768,1280]){await localized.setViewportSize({width,height:900});assert.ok(await localized.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),locale+' overflow at '+width);if(process.env.SCOACH_SCREENSHOT_DIR)await localized.screenshot({path:process.env.SCOACH_SCREENSHOT_DIR+'/scoach-7a-'+locale+'-'+width+'.png'});}
  await localized.setViewportSize({width:390,height:844});
  await localized.locator('#ask-coach').click();await localized.locator('#coach-spending>summary').click();await localized.locator('[data-coach-question="coach.promptRestaurants"]').click();await localized.waitForFunction(()=>document.querySelector('#coach-mode').textContent.includes('·'));
  await localized.waitForFunction(()=>!document.querySelector('#coach-response').textContent.includes('…'));
  assert.ok((await localized.locator('#coach-response').innerText()).includes(locale==='fi'?'havaittuihin':'observerade'));assert.equal(coachLocales.at(-1),locale);
  if(process.env.SCOACH_SCREENSHOT_DIR)await localized.screenshot({path:process.env.SCOACH_SCREENSHOT_DIR+'/scoach-7a-'+locale+'-coach.png'});
  await localized.keyboard.press('Escape');await localized.locator('#open-story').click();await localized.waitForFunction(()=>document.querySelector('#scenario-amount').textContent.includes(','));
  assert.ok((await localized.locator('#show-transactions').innerText()).includes('10'));assert.ok(!(await localized.locator('#story-dialog').innerText()).includes('Actual spending'));
  await localized.keyboard.press('Escape');
 }
 await localized.close();
 assert.deepEqual(errors,[]);
 console.log('PASS phone story, exact values, 10 rows, calculation, refresh, goal handoff, offline coach, forecast controls, three widths, persona isolation, reset, Escape');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
"""
            try:
                result = subprocess.run(['node', '-e', script], env=env, capture_output=True, text=True, timeout=90)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            finally:
                server.shutdown()
                server.server_close()

if __name__ == '__main__':
    unittest.main()
