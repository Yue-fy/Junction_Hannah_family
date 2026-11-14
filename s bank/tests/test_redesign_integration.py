"""Integrated customer journeys at the actual client/API boundary, without a browser.

These tests reuse the shared minimal DOM harness. They assert observable UI values,
request scopes and state isolation; they do not replace viewport/browser checks.
"""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import unittest
from urllib.parse import urlencode
import test_web_contract as contracts


class RedesignIntegrationTests(unittest.TestCase):
    read = contracts.WebContractTests.read
    node_app = contracts.WebContractTests.node_app

    def test_vat_chat_mounts_the_real_estimate_with_period_and_readable_evidence(self):
        from scoach.api import Application
        bank = Application(Path(__file__).resolve().parents[1] / 'var' / 'scoach.sqlite3')
        status, envelope = bank.handle('POST', '/api/coach', {
            'customer_id': 'CUST00001', 'month': '2026-09', 'locale': 'en',
            'message': 'How much VAT is inside my purchases?',
        })
        self.assertEqual(status, 200, envelope)
        self.assertEqual(envelope['data'].get('tool_kind'), 'vat_estimate')
        self.node_app('const vatAnswer=' + json.dumps(envelope['data']) + ';\n' + r'''
const originalFixture=fixture;
fixture=(path,customer)=>path==='/api/coach'?vatAnswer:originalFixture(path,customer);
get('ask-coach').listeners.click();
const vat=new Element('vat-question');vat.setAttribute('data-open-vat','');calls.length=0;
await documentListeners.click({target:vat});await settle();
const requests=calls.filter(call=>call.path==='/api/coach');assert.equal(requests.length,1);
assert.equal(requests[0].body.message,'How much VAT is inside my purchases?');
assert.equal(requests[0].body.month,'2026-09');assert.equal(requests[0].customer,'CUST00001');
assert.equal(app.state.view,'coach');assert.equal(get('coach-view').hidden,false);assert.equal(get('trends-view').hidden,true);
const html=get('coach-response').innerHTML,visible=html.replace(/<[^>]*>/g,'');
assert.ok(visible.includes('≈')&&visible.includes('€212.38'));
assert.ok(visible.includes('VAT inside your spending'));
assert.ok(visible.includes('2026'));
assert.ok(visible.includes('not a personal tax calculation'));
assert.ok(html.includes('data-evidence-rows'));
assert.ok(!visible.includes('no explicit tax records'));
assert.ok(!/tx:\d+:[a-f0-9]{32}/.test(visible));
assert.equal(app.state.selectedMonth,'2026-09');
''')

    def test_investment_question_hydrates_transfers_inline_and_keeps_returned_period_evidence(self):
        self.node_app(r'''
const originalFixture=fixture;
fixture=(path,customer)=>{
 if(path==='/api/coach')return {intent:'investment_cashflow',source:'deterministic',parameters:{period:'2026-08',months:6},explanation_blocks:[]};
 if(path==='/api/investments')return {customer_id:customer,start_month:'2026-03',end_month:'2026-08',total_contributions_cents:121000,withdrawals_cents:13700,contribution_months:4,period_months:6,months:[],transaction_refs:['investment-scope-row']};
 if(path==='/api/transactions')return {transactions:[{transaction_ref:'investment-scope-row',date:'2026-08-01',amount_cents:-121000,category:'Investment',transaction_type:'investment_deposit'}]};
 return originalFixture(path,customer);
};
calls.length=0;get('coach-input').value='Show investment transfers for the six months ending August 2026';
get('coach-form').listeners.submit({preventDefault(){},submitter:new Element('send')});await settle();
const request=calls.find(call=>call.path==='/api/investments');assert.ok(request);
assert.equal(request.query.month,'2026-08');assert.equal(request.query.months,'6');assert.equal(request.customer,'CUST00001');
assert.equal(app.state.view,'coach');assert.equal(get('trends-view').hidden,true);
const html=get('coach-response').innerHTML,visible=get('coach-response').textContent;
assert.ok(html.includes('coach-tool-result'));assert.ok(visible.includes('€1,210.00'));assert.ok(visible.includes('€137.00'));
assert.ok(visible.includes('March 2026')&&visible.includes('August 2026'));
assert.ok(visible.includes('account transfers only'));
assert.ok(visible.includes('cannot show holdings, returns, risk or investment advice'));
assert.ok(!visible.includes('investment-scope-row'));
const evidenceKey=html.match(/data-evidence-rows="([^"]+)"/)?.[1];assert.ok(evidenceKey);
const evidence=new Element('investment-evidence');evidence.dataset.evidenceRows=evidenceKey;
await documentListeners.click({target:evidence});await settle();
const rowsRequest=calls.filter(call=>call.path==='/api/transactions').at(-1);
assert.equal(rowsRequest.query.start,'2026-03-01');assert.equal(rowsRequest.query.end,'2026-08-31');
assert.deepEqual(app.state.rows.map(row=>row.transaction_ref),['investment-scope-row']);
assert.equal(calls.filter(call=>call.method==='POST'&&call.path!=='/api/coach').length,0);
''')

    def test_home_financing_question_hydrates_historical_records_without_current_mortgage_claims(self):
        self.node_app(r'''
await select('CUST00296');
const originalFixture=fixture;
fixture=(path,customer)=>{
 if(path==='/api/coach')return {intent:'home_financing_history',source:'deterministic',parameters:{goal_type:'home'},explanation_blocks:[]};
 if(path==='/api/financing')return {customer_id:customer,available:true,property_price_cents:31200000,requested_loan_cents:24800000,equity_cents:6400000,recorded_fees_total_cents:75000,recorded_outcome:{decision:'rejected'},events:[{timestamp:'2025-06-11',description:'Application review recorded',expense_amount_cents:75000,event_ref:'mortgage:internal-id'}]};
 return originalFixture(path,customer);
};
calls.length=0;get('coach-input').value='Explain linked home-financing history';
get('coach-form').listeners.submit({preventDefault(){},submitter:new Element('send')});await settle();
const request=calls.find(call=>call.path==='/api/financing');assert.ok(request);
assert.equal(request.query.goal_type,'home');assert.equal(request.customer,'CUST00296');
assert.equal(app.state.view,'coach');assert.equal(get('goals-view').hidden,true);
const visible=get('coach-response').textContent;
assert.ok(visible.includes('Historical home-financing records'));
assert.ok(visible.includes('Historical application declined'));
for(const amount of ['€312,000.00','€248,000.00','€64,000.00','€750.00'])assert.ok(visible.includes(amount),amount);
assert.ok(visible.includes('a past application'));
assert.ok(visible.includes('do not establish a current mortgage, household finances, available savings, or a new lending decision'));
assert.ok(visible.includes('Application review recorded'));
assert.ok(!visible.includes('mortgage:internal-id'));
assert.equal(calls.filter(call=>call.method==='POST'&&call.path!=='/api/coach').length,0);
const next=get('coach-response').children.find(child=>child?.onclick);assert.ok(next);next.onclick();
assert.equal(app.state.view,'goals');assert.equal(get('wish-title').dataset.template,'home');
assert.equal(get('goal-planner').open,false);
assert.equal(calls.filter(call=>call.path.startsWith('/api/goals')&&call.method==='POST').length,0);
''')

    def test_partial_vat_coverage_is_visible_in_the_answer_not_hidden_as_accuracy(self):
        self.node_app(r'''
const html=app.toolResultHTML({tool_kind:'vat_estimate',tool_result:{start:'2026-08-15',end:'2026-09-15',estimated_vat_cents:1200,gross_spending_cents:20000,covered_spending_cents:10000,uncovered_spending_cents:10000,coverage_basis_points:5000,by_rate:[],transactions:[],transaction_refs:[],value_status:'estimated'}});
const visible=html.replace(/<[^>]*>/g,'');
assert.ok(visible.includes('≈')&&visible.includes('€12.00'));
assert.match(visible,/50\s*%/);
assert.ok(visible.includes('Spending without a rate estimate')&&visible.includes('€100.00'));
assert.ok(visible.includes('mapping coverage')&&visible.includes('not an accuracy or confidence score'));
''')

    def test_fully_unmapped_vat_is_not_presented_as_zero_tax(self):
        self.node_app(r'''
const html=app.toolResultHTML({tool_kind:'vat_estimate',tool_result:{start:'2026-09-01',end:'2026-09-30',estimated_vat_cents:0,gross_spending_cents:10000,covered_spending_cents:0,uncovered_spending_cents:10000,coverage_basis_points:0,by_rate:[],transactions:[],transaction_refs:[]}});
const visible=html.replace(/<[^>]*>/g,'');
assert.ok(visible.includes('VAT estimate unavailable'));
assert.ok(!visible.includes('≈ €0.00'));
''')

    def test_internal_filter_flags_are_not_customer_labels(self):
        self.node_app(r'''
const html=app.toolResultHTML({tool_kind:'transaction_statistics',query_scope:{metric:'consumption_total',concept:'All spending'},tool_result:{start:'2026-09-01',end:'2026-09-30',filters:{consumption_only:'true'},metric_value_cents:187866,outflow_total_cents:187866,transaction_count:30,outflow_count:30,average_outflow_cents:6262,transaction_refs:[]}});
const visible=html.replace(/<[^>]*>/g,'');assert.ok(visible.includes('All spending'));
assert.ok(!/\btrue\b/.test(visible));assert.ok(!visible.includes('consumption_only'));
const received=app.toolResultHTML({tool_kind:'transaction_statistics',query_scope:{metric:'inflow_total',concept:'All inflows'},tool_result:{start:'2026-09-01',end:'2026-09-30',filters:{},metric_value_cents:212000,inflow_count:3,transaction_count:3,transaction_refs:[]}});
assert.ok(received.includes('not earned income'));
''')

    def test_real_bank_responses_preserve_average_and_income_in_calculation_drawers(self):
        from scoach.api import Application
        database=Path(__file__).resolve().parents[1]/'var'/'scoach.sqlite3'
        if not database.is_file():
            self.skipTest('Build the synthetic demo database first')
        bank=Application(database)
        fixtures={}
        previous=None
        for name,message in (
            ('average','What was my average restaurant purchase in August 2026?'),
            ('income','How much salary was credited in August 2026?'),
        ):
            body={'customer_id':'CUST00001','month':'2026-09','locale':'en','message':message}
            if previous:
                body['previous_query']=previous
            status,envelope=bank.handle('POST','/api/coach',body)
            self.assertEqual(status,200,envelope)
            answer=envelope['data'];scope=answer['query_scope'];previous=scope
            status,rows=bank.handle('GET','/api/transactions?'+urlencode({'customer_id':'CUST00001','start':scope['start'],'end':scope['end'],**scope['filters']}))
            self.assertEqual(status,200,rows)
            fixtures[name]={'message':message,'answer':answer,'rows':rows['data']}
        with closing(sqlite3.connect(f'file:{database}?mode=ro',uri=True)) as conn:
            income=conn.execute("SELECT sum(amount_cents) FROM transactions WHERE customer_id=? AND transaction_type='salary' AND date BETWEEN ? AND ? AND amount_cents>0",('CUST00001','2026-08-01','2026-08-31')).fetchone()[0]
        self.assertEqual(fixtures['income']['answer']['tool_result']['metric_value_cents'],income)
        self.assertEqual(fixtures['average']['answer']['tool_result']['metric_value_cents'],1154)
        body='const bank='+json.dumps(fixtures)+';\n'+r'''
const originalFetch=globalThis.fetch;
globalThis.fetch=async(url,options)=>{
 const parsed=new URL(url,'http://local');
 if(parsed.pathname==='/api/coach'){const body=JSON.parse(options.body),fixture=Object.values(bank).find(item=>item.message===body.message);assert.ok(fixture);return {ok:true,json:async()=>({ok:true,data:fixture.answer})};}
 if(parsed.pathname==='/api/transactions'){assert.equal(parsed.searchParams.get('start'),'2026-08-01');assert.equal(parsed.searchParams.get('end'),'2026-08-31');const fixture=parsed.searchParams.get('category')==='Restaurants'?bank.average:bank.income;return {ok:true,json:async()=>({ok:true,data:fixture.rows})};}
 return originalFetch(url,options);
};
for(const name of ['average','income']){
 await app.askCoach(bank[name].message);
 const action=get('coach-response').children.filter(child=>child?.onclick).at(-1);action.onclick();await settle();
 const context=app.state.transactionEvidence;
 assert.equal(context.kind,'statistics');assert.equal(context.start,'2026-08-01');
 assert.equal(context.metric,bank[name].answer.query_scope.metric);
 assert.deepEqual(app.state.rows.map(row=>row.transaction_ref),bank[name].answer.tool_result.transaction_refs);
 const html=app.calculationHTML(context),cents=bank[name].answer.tool_result.metric_value_cents;
 const amount=new Intl.NumberFormat('en-FI',{style:'currency',currency:'EUR'}).format(cents/100);
 assert.ok(html.includes(amount));
 if(name==='average')assert.ok(html.includes('÷ 10 ='));
 if(name==='income'){assert.ok(html.includes('positive amounts'));assert.ok(!html.includes('€0.00'));}
}
'''
        self.node_app(body)

    def test_missing_purchase_context_offers_a_supported_planning_form(self):
        self.node_app(r'''
const originalFetch=globalThis.fetch;
globalThis.fetch=async(url,options)=>new URL(url,'http://local').pathname==='/api/coach'?{ok:true,json:async()=>({ok:true,data:{intent:'explain_change',source:'deterministic',needs_clarification:true,clarification_code:'affordability_context',clarification_question:'What would you like to buy, how much will it cost, and when?'}})}:originalFetch(url,options);
await app.askCoach('Can I afford it?');
assert.ok(get('coach-response').innerHTML.includes('how much will it cost'));
const action=get('coach-response').children.filter(child=>child?.onclick).at(-1);
assert.ok(action.textContent.includes('Plan a purchase'));action.onclick();
assert.equal(app.state.view,'goals');assert.equal(get('goal-template').value,'purchase');
assert.equal(get('goal-planner').open,true,'The purchase planner must be visible before focusing its required amount');
assert.equal(get('goal-target').focused,true);
assert.equal(calls.filter(call=>call.path==='/api/goals'&&call.body.confirmed).length,0,'Asking for context must not create a plan or move money');
''')

    def test_income_answer_does_not_render_outflow_metrics(self):
        self.node_app(r'''
const html=app.toolResultHTML({tool_kind:'transaction_statistics',query_scope:{metric:'inflow_total',concept:'Income'},tool_result:{start:'2026-09-01',end:'2026-09-30',filters:{role:'income'},metric_value_cents:244781,inflow_total_cents:244781,inflow_count:2,outflow_count:0,transaction_count:2,outflow_total_cents:0,average_outflow_cents:null,transaction_refs:[]}});
assert.match(html,/<p class="coach-result-amount">€2,447\.81<\/p>/);
assert.ok(html.includes('Money received'));assert.ok(html.includes('not gross pay'));
assert.ok(!html.includes('Average purchase'),'Income must not be framed as an outgoing purchase');
''')

    def test_coaching_styles_keep_prose_before_the_same_financial_details(self):
        self.node_app(r'''
const exp=await import('data:text/javascript;base64,'+Buffer.from(sources['experience.js']).toString('base64'));
const store=exp.createExperienceStore(null,'CUST00001'),originalFetch=globalThis.fetch;
globalThis.fetch=async(url,options)=>new URL(url,'http://local').pathname==='/api/coach'?{ok:true,json:async()=>({ok:true,data:{intent:'transaction_statistics',source:'deterministic',explanation_blocks:[{text:'A plain explanation of the selected records.'}],tool_kind:'transaction_statistics',tool_result:{start:'2026-09-01',end:'2026-09-30',filters:{category:'Restaurants'},outflow_total_cents:22570,transaction_count:10,outflow_count:10,average_outflow_cents:2257,transaction_refs:[]}}})}:originalFetch(url,options);
store.save({style:'gentle'});await app.askCoach('How much did I spend on restaurants?');
const gentle=get('coach-response').innerHTML;
assert.ok(gentle.includes('data-coaching-style="gentle"'));
assert.ok(gentle.indexOf('coach-prose')<gentle.indexOf('coach-tool-result'));
assert.ok(gentle.slice(gentle.indexOf('coach-prose'),gentle.indexOf('coach-support')).includes('€225.70'));
app.state.conversation=[];store.save({style:'direct'});await app.askCoach('How much did I spend on restaurants?');
const direct=get('coach-response').innerHTML;
assert.ok(direct.includes('data-coaching-style="direct"'));
assert.ok(direct.indexOf('coach-prose')<direct.indexOf('coach-tool-result'));
assert.ok(direct.slice(direct.indexOf('coach-prose'),direct.indexOf('coach-support')).includes('€225.70'));
assert.ok(gentle.includes('€22.57')&&direct.includes('€22.57'));
assert.equal(store.load().consent,false,'Style changes must not enable remembered storage');
''')

    def test_explicit_preference_is_confirmed_without_an_irrelevant_bank_query(self):
        self.node_app(r'''
const exp=await import('data:text/javascript;base64,'+Buffer.from(sources['experience.js']).toString('base64'));
const store=exp.createExperienceStore(null,'CUST00001');store.forget();calls.length=0;
await app.askCoach('I want to save for a car.');
assert.equal(calls.filter(call=>call.path==='/api/coach').length,0,'A bounded preference declaration needs no banking query or model call');
assert.equal(store.load().focus,'flexibility','The preference must remain a proposal');
assert.ok(get('coach-response').innerHTML.includes('without choosing an amount or deadline'));
assert.ok(get('coach-response').innerHTML.includes('data-confirm-memory'));
const action=get('coach-response').children.filter(child=>child?.onclick).at(-1);action.onclick();
assert.equal(app.state.view,'goals');assert.equal(get('wish-title').dataset.template,'vehicle');
assert.ok(get('wish-title').value);assert.equal(get('wish-title').focused,true);
assert.equal(get('goal-planner').open,false,'An unpriced wish must not open the numeric planner');
assert.equal(store.load().wishes.length,0,'Prefilling a wish is not confirmation to save it');
assert.equal(store.load().focus,'flexibility','Opening a wish form does not grant memory consent');
const confirm=new Element('confirm-memory');confirm.setAttribute('data-confirm-memory','');get('remember-consent').checked=false;
documentListeners.click({target:confirm});
assert.equal(store.load().focus,'vehicle');assert.equal(store.load().notes.length,1);assert.equal(store.load().consent,false);
''')

    def test_alternative_scenario_connects_to_the_users_trip_goal(self):
        self.node_app(r'''
const exp=await import('data:text/javascript;base64,'+Buffer.from(sources['experience.js']).toString('base64'));
const store=exp.createExperienceStore(null,'CUST00001');store.save({focus:'travel',protected_category:'Restaurants'});store.markOnboarded();
const originalFetch=globalThis.fetch;
globalThis.fetch=async(url,options)=>{
 const path=new URL(url,'http://local').pathname;
 if(path==='/api/coach')return {ok:true,json:async()=>({ok:true,data:{intent:'spending_adjustment',source:'deterministic',tool_kind:'spending_adjustment_preview',explanation_blocks:[{text:'An optional shopping scenario.'}],tool_result:{start:'2026-09-01',end:'2026-09-30',category:'Lifestyle',percent:'20',actual_total_cents:20000,adjustable_base_cents:20000,modeled_monthly_contribution_cents:4000,transaction_refs:['shopping-row']}}})};
 if(path==='/api/scenarios'){const body=JSON.parse(options.body);assert.equal(body.category,'Lifestyle');assert.equal(body.confirmed,true);return {ok:true,json:async()=>({ok:true,data:{scenario:{id:'personal-scenario',category:'Lifestyle',modeled_monthly_contribution_cents:4000}}})};}
 return originalFetch(url,options);
};
await app.askCoach('How much could I save if I reduced shopping by 20%?');
const action=get('coach-response').children.filter(child=>child?.onclick).at(-1);
assert.ok(action.textContent.includes('€40.00'));
await action.onclick();await settle();
assert.equal(app.state.view,'goals');assert.equal(get('goal-template').value,'trip');
assert.equal(app.state.pendingHandoff.scenarioId,'personal-scenario');
assert.equal(app.state.pendingHandoff.contributionCents,4000);
assert.equal(app.state.scenario.category,'Lifestyle');
assert.ok(get('goal-name').value);
''')

    def test_ring_groups_and_category_selection_use_consumption_only(self):
        self.node_app(r'''
const originalFixture=fixture;
const rows=[
 {transaction_ref:'rent',category:'Housing',transaction_type:'housing_payment',date:'2026-09-05',amount_cents:-10000},
 {transaction_ref:'bill',category:'Utilities',transaction_type:'utilities_payment',date:'2026-09-06',amount_cents:-2000},
 {transaction_ref:'food',category:'Groceries',transaction_type:'purchase',date:'2026-09-07',amount_cents:-3000},
 {transaction_ref:'bus',category:'Transportation',transaction_type:'purchase',date:'2026-09-08',amount_cents:-1200},
 {transaction_ref:'meal',category:'Restaurants',transaction_type:'purchase',date:'2026-09-09',amount_cents:-4000},
 {transaction_ref:'transfer',category:'Investment',transaction_type:'investment_deposit',date:'2026-09-10',amount_cents:-99900},
 {transaction_ref:'refund',category:'Restaurants',transaction_type:'refund',date:'2026-09-11',amount_cents:200},
 {transaction_ref:'salary',category:'Salary',transaction_type:'salary',date:'2026-09-28',amount_cents:200000}
];
fixture=(path,customer)=>path==='/api/transactions'?{transactions:rows}:originalFixture(path,customer);
await app.load();
assert.equal(get('spending-total').textContent,'€202.00');
assert.equal(app.state.categoryRowsAvailable,true);
assert.equal(get('spending-donut').attributes['aria-busy'],'false');
assert.ok(!get('spending-categories').innerHTML.includes('Investment'));
assert.ok(!get('spending-categories').innerHTML.includes('Salary'));
const group=new Element('home-group');group.dataset.spendingGroup='home';
documentListeners.click({target:group});
assert.equal(app.state.spendingGroup,'home');
assert.equal(get('spending-total').textContent,'€120.00');
assert.equal(get('spending-center-label').textContent,'Home & essentials');
assert.ok(!get('spending-categories').innerHTML.includes('Eating out'));
const category=new Element('housing-category');category.dataset.spendingCategory='Housing';
documentListeners.click({target:category});
assert.equal(app.state.selectedCategory,'Housing');
assert.equal(get('spending-total').textContent,'€100.00');
assert.equal(get('spending-center-label').textContent,'Housing');
assert.match(get('spending-selection').innerHTML,/View 1 transactions/);
assert.match(get('spending-selection').innerHTML,/data-category-transactions="Housing"/);
assert.ok(get('spending-donut').innerHTML.includes('aria-pressed="true" data-spending-category="Housing"'));
''')

    def test_failed_transaction_load_is_unavailable_instead_of_zero_spending(self):
        self.node_app(r'''
const originalFetch=globalThis.fetch;
globalThis.fetch=async(url,options)=>{
 if(new URL(url,'http://local').pathname==='/api/transactions')throw new Error('Transactions unavailable');
 return originalFetch(url,options);
};
await app.load();
assert.equal(app.state.categoryRowsAvailable,false);
assert.deepEqual(app.state.categoryRows,[]);
assert.equal(get('spending-total').textContent,'—');
assert.equal(get('spending-categories').innerHTML,'');
assert.equal(get('spending-donut').attributes['aria-busy'],'false');
assert.ok(get('spending-donut').innerHTML.includes('empty-state'));
assert.ok(!get('spending-donut').innerHTML.includes('€0.00'));
assert.ok(!get('spending-donut').innerHTML.includes('No recorded spending'));
''')

    def test_august_answer_drills_into_august_rows_and_scopes_the_follow_up(self):
        self.node_app(r'''
const queryScope={customer_id:'CUST00001',account_id:'ACC000001',start:'2026-08-01',end:'2026-08-31',filters:{category:'Restaurants'},metric:'outflow_total',concept:'Restaurants',reference_date:'2026-09-30'};
const originalFetch=globalThis.fetch;
globalThis.fetch=async(url,options)=>{
 const response=await originalFetch(url,options);
 if(new URL(url,'http://local').pathname!=='/api/coach')return response;
 return {...response,json:async()=>({ok:true,data:{intent:'transaction_statistics',source:'deterministic',query_scope:queryScope,explanation_blocks:[{text:'Restaurant spending in August.'}],tool_kind:'transaction_statistics',tool_result:{start:'2026-08-01',end:'2026-08-31',filters:{category:'Restaurants'},outflow_total_cents:11543,metric_value_cents:11543,transaction_count:10,outflow_count:10,average_outflow_cents:1154,transaction_refs:['august-row']}}})};
};
assert.equal(app.state.selectedMonth,'2026-09');
await app.askCoach('How much did I spend on restaurants in August 2026?');
assert.deepEqual(app.state.queryScope,queryScope);
const action=get('coach-response').children.find(child=>typeof child.onclick==='function');
assert.ok(action,'The answer must offer a matching-row action');
action.onclick();await settle();
const matching=calls.filter(call=>call.path==='/api/transactions').at(-1);
assert.equal(matching.query.start,'2026-08-01');
assert.equal(matching.query.end,'2026-08-31');
assert.equal(matching.query.month,'2026-08');
assert.equal(matching.query.category,'Restaurants');
assert.equal(app.state.selectedMonth,'2026-09','Drill-down must not silently mutate the selected Home month');
await app.askCoach('And groceries?');
const followup=calls.filter(call=>call.path==='/api/coach').at(-1);
assert.deepEqual(followup.body.previous_query,queryScope);
assert.equal(followup.body.message,'And groceries?');
''')

    def test_average_answer_uses_the_verified_average_as_the_primary_amount(self):
        self.node_app(r'''
const html=app.toolResultHTML({tool_kind:'transaction_statistics',query_scope:{metric:'average_outflow',concept:'Restaurants'},tool_result:{start:'2026-08-01',end:'2026-08-31',filters:{category:'Restaurants'},outflow_total_cents:11543,metric_value_cents:1154,transaction_count:10,outflow_count:10,average_outflow_cents:1154,transaction_refs:[]}});
assert.match(html,/<p class="coach-result-amount">€11\.54<\/p>/);
assert.ok(!html.includes('€115.43'),'The total must not masquerade as the requested single-purchase average');
''')

    def test_customer_visible_evidence_uses_rows_without_hash_text(self):
        self.node_app(r'''
const ref='tx:582:'+'9'.repeat(64),originalFixture=fixture;
const row={transaction_ref:ref,category:'Restaurants',transaction_type:'purchase',date:'2026-09-10',amount_cents:-3647};
fixture=(path,customer)=>path==='/api/transactions'?{transactions:[row]}:originalFixture(path,customer);
await app.showTransactions({category:'Restaurants'});
const stats=app.calculationHTML({kind:'statistics',customerId:'CUST00001',accountId:'ACC000001',start:'2026-09-01',end:'2026-09-30',filters:{category:'Restaurants'},rows:[row],transaction_refs:[ref]});
const result=app.toolResultHTML({tool_kind:'transaction_statistics',query_scope:{metric:'outflow_total'},tool_result:{start:'2026-09-01',end:'2026-09-30',filters:{category:'Restaurants'},outflow_total_cents:3647,transaction_count:1,average_outflow_cents:3647,transaction_refs:[ref]}});
const visible=html=>html.replace(/<[^>]*>/g,'');
for(const html of [stats,result,get('transaction-list').innerHTML]){
 assert.ok(!visible(html).includes(ref),'Raw references belong to metadata, not customer copy');
 assert.ok(!visible(html).includes('9999999999999999'));
}
assert.ok(stats.includes('data-evidence-rows'));
assert.ok(get('transaction-list').innerHTML.includes('data-transaction="'+ref+'"'),'Stable references must remain available internally');
''')

    def test_first_visit_tour_offers_a_real_category_action_and_can_be_skipped(self):
        self.node_app(r'''
const originalFixture=fixture;
fixture=(path,customer)=>path==='/api/transactions'?{transactions:[{transaction_ref:'food',category:'Groceries',transaction_type:'purchase',date:'2026-09-10',amount_cents:-3200}]}:originalFixture(path,customer);
await app.load();
assert.equal(get('welcome-guide').hidden,false);
assert.ok(get('welcome-guide').innerHTML.includes('data-open-tour'));
assert.ok(get('welcome-guide').innerHTML.includes('data-tour-skip'));
const skip=new Element('skip-tour');skip.setAttribute('data-tour-skip','');documentListeners.click({target:skip});
assert.equal(get('welcome-guide').hidden,true,'Skipping first-use guidance must remain a complete path');
const open=new Element('open-tour');open.setAttribute('data-open-tour','');documentListeners.click({target:open});
assert.equal(get('tour-dialog').open,true);
assert.ok(get('tour-dialog-content').innerHTML.includes('data-tour-try="spending"'));
const tryIt=new Element('try-spending');tryIt.dataset.tourTry='spending';documentListeners.click({target:tryIt});
assert.equal(get('tour-dialog').open,false);
assert.equal(app.state.spendingGroup,'everyday');
assert.equal(app.state.selectedCategory,'Groceries');
assert.equal(get('spending-total').textContent,'€32.00');
assert.equal(get('welcome-guide').hidden,true);
assert.equal(get('money-title').scrolled,true);
''')

    def test_protecting_dining_changes_suggestions_without_rewriting_account_facts(self):
        self.node_app(r'''
const originalFixture=fixture;
fixture=(path,customer)=>{
 const data=originalFixture(path,customer);
 if(path==='/api/overview')return {...data,priority:{id:'restaurant_change',kind:'explain_change'}};
 if(path==='/api/transactions')return {transactions:[
  {transaction_ref:'meal',category:'Restaurants',transaction_type:'purchase',date:'2026-09-10',amount_cents:-7000},
  {transaction_ref:'shop',category:'Lifestyle',transaction_type:'purchase',date:'2026-09-12',amount_cents:-4000}
 ]};
 return data;
};
await app.load();const before=JSON.stringify(app.state.overview),rowsBefore=JSON.stringify(app.state.categoryRows);
const open=new Element('open-preferences');open.setAttribute('data-open-notebook','');documentListeners.click({target:open});
get('preference-focus').value='buffer';get('preference-style').value='direct';get('preference-protect').value='Restaurants';get('preference-consent').checked=false;get('preference-milestones').checked=false;
calls.length=0;get('preferences-form').listeners.submit({preventDefault(){}});
assert.equal(calls.length,0,'Browser preferences must not rewrite banking data or silently call the server');
assert.equal(JSON.stringify(app.state.overview),before);
assert.equal(JSON.stringify(app.state.categoryRows),rowsBefore);
assert.equal(get('home-coach-question').textContent,get('home-coach-question').dataset.directQuestion+' ↗');
assert.ok(get('home-coach-question').dataset.directQuestion.includes('Lifestyle'));
assert.ok(!get('home-coach-question').dataset.directQuestion.includes('Restaurants'));
assert.ok(get('insight-headline').textContent.toLowerCase().includes('eating out'));
assert.ok(get('personalization-card').innerHTML.includes('id="personalization-title"'));
assert.ok(get('personalization-card').innerHTML.includes('this visit only'));
const question=get('home-coach-question').dataset.directQuestion;
await documentListeners.click({target:get('home-coach-question')});await settle();
assert.equal(calls.filter(call=>call.path==='/api/coach').at(-1).body.message,question);
assert.equal(app.state.view,'coach');
''')


if __name__ == '__main__':
    unittest.main()
