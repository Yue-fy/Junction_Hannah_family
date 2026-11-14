"""Customer-facing conversation regressions, using the real client harness."""
import unittest
import test_web_contract as contracts


class ConversationUXTests(unittest.TestCase):
    read = contracts.WebContractTests.read
    node_app = contracts.WebContractTests.node_app

    def test_a_statistics_answer_leads_with_prose_and_collapses_calculations(self):
        self.node_app(r'''
const originalFixture=fixture;
fixture=(path,customer)=>path==='/api/coach'?{intent:'transaction_statistics',source:'deterministic',tool_kind:'transaction_statistics',explanation_blocks:[{text:'Here are the exact observed results for the selected category and period.'}],query_scope:{start:'2026-09-01',end:'2026-09-30',concept:'Restaurants',metric:'outflow_total',filters:{category:'Restaurants'}},tool_result:{start:'2026-09-01',end:'2026-09-30',filters:{category:'Restaurants'},metric_value_cents:22570,outflow_total_cents:22570,outflow_count:10,average_outflow_cents:2257,transaction_refs:['dining-row']}}:originalFixture(path,customer);
const exp=await import('data:text/javascript;base64,'+Buffer.from(sources['experience.js']).toString('base64'));
for(const style of ['gentle','direct']){
 exp.createExperienceStore(null,'CUST00001').save({style});app.state.conversation=[];
 await app.askCoach('How much did I spend on restaurants?');
 const html=get('coach-response').innerHTML;
 const prose=html.match(/<div class="coach-prose">([\s\S]*?)<\/div>/)?.[1];
 assert.ok(prose&&prose.includes('€225.70')&&prose.includes('10'),'The answer itself must contain the amount and matching payment count');
 assert.ok(html.indexOf('coach-prose')<html.indexOf('coach-tool-result'),'Prose leads in either coaching style');
 assert.match(html,/<details class="coach-support"[^>]*>/);
 assert.ok(!/<details class="coach-support"[^>]*\sopen(?:[\s=>])/.test(html),'Supporting calculations are initially collapsed');
 assert.ok(!html.includes('Here are the exact observed results'));
}
''')

    def test_safe_spending_evidence_includes_the_buffer_history(self):
        self.node_app(r'''
const originalFixture=fixture;
fixture=(path,customer)=>path==='/api/coach'?{intent:'safe_to_spend',source:'deterministic',tool_kind:'safe_to_spend',source_refs:{transaction_refs:['scheduled','history-buffer']},tool_result:{available:true,as_of:'2026-09-30',horizon_days:7,horizon_end:'2026-10-07',safe_to_spend_cents:7814,reserve_floor_cents:50000,scheduled_outflows_cents:97526,historical_flexible_buffer_cents:22754,transaction_refs:['scheduled'],comparison_transaction_refs:['history-buffer']}}:originalFixture(path,customer);
await app.askCoach('What can I spend this week?');
const html=get('coach-response').innerHTML;
assert.ok(html.includes('Source rows (2)'),'Both the scheduled and historical-buffer sources must be inspectable');
const key=html.match(/data-evidence-rows="([^"]+)"/)?.[1];assert.ok(key);
const evidence=new Element('safe-evidence');evidence.dataset.evidenceRows=key;calls.length=0;
await documentListeners.click({target:evidence});await settle();
const request=calls.find(call=>call.path==='/api/transactions');
assert.equal(request.query.start,'2024-10-03');assert.equal(request.query.end,'2026-09-30');
''')

    def test_an_older_scenario_keeps_its_action_and_original_percentage(self):
        self.node_app(r'''
const originalFixture=fixture;let answer=0;
fixture=(path,customer)=>path==='/api/coach'?(++answer===1?{intent:'spending_adjustment',source:'deterministic',tool_kind:'spending_adjustment_preview',tool_result:{category:'Restaurants',percent:'12.5',start:'2026-08-01',end:'2026-08-31',actual_total_cents:11543,adjustable_base_cents:11543,modeled_monthly_contribution_cents:1443,transaction_refs:[]}}:{intent:'safe_to_spend',source:'deterministic',tool_kind:'safe_to_spend',tool_result:originalFixture('/api/safe-to-spend',customer)}):originalFixture(path,customer);
await app.askCoach('What if dining out in August were 12.5% lower?');
await app.askCoach('What can I spend this week?');
const oldTurn=app.state.conversation[0];
assert.ok(get('coach-response').innerHTML.includes('data-coach-turn-action="'+oldTurn.id+'"'),'The older scenario action must remain reachable');
const action=new Element('old-scenario-action');action.dataset.coachTurnAction=oldTurn.id;calls.length=0;
await documentListeners.click({target:action});await settle();
const saved=calls.find(call=>call.path==='/api/scenarios'&&call.method==='POST');
assert.ok(saved);assert.equal(String(saved.body.percent),'12.5');assert.equal(saved.body.month,'2026-08');
''')

    def test_a_dated_forecast_action_stays_with_its_answer(self):
        self.node_app(r'''
const originalFixture=fixture;
fixture=(path,customer)=>path==='/api/coach'?{intent:'preview_cashflow',source:'deterministic',parameters:{reference_date:'2026-08-31'}}:path==='/api/forecast'?{as_of:'2026-08-31',projected:[{date:'2026-09-30',balance_cents:473436}],transaction_refs:[]}:originalFixture(path,customer);
await app.askCoach('Show cash flow as of 2026-08-31');
const action=get('coach-response').children.find(child=>typeof child.onclick==='function');assert.ok(action);action.onclick();
assert.equal(app.state.view,'coach','The dated answer must not open a different selected-month forecast');
assert.equal(get('coach-support-'+app.state.conversation.at(-1).id).open,true);
''')

    def test_price_clarification_continues_the_plan_without_a_previous_statistics_scope(self):
        self.node_app(r'''
const originalFixture=fixture;
fixture=(path,customer)=>path==='/api/coach'?{intent:'safe_to_spend',source:'deterministic',needs_clarification:true,clarification_code:'planned_purchase_cost',clarification_question:'What total cost should we check?'}:originalFixture(path,customer);
app.state.queryScope={concept:'Restaurants',start:'2026-08-01',end:'2026-08-31'};
await app.askCoach('I want to go see a movie this week');
assert.equal(app.state.queryScope,null,'The movie plan must replace an unrelated historical scope');
await app.askCoach('€20');
const request=calls.filter(call=>call.path==='/api/coach').at(-1);
assert.ok(request.body.message.includes('movie'));assert.ok(request.body.message.includes('20'));
assert.ok(!('previous_query' in request.body));
assert.equal(app.state.conversation.at(-1).message,'€20','The customer still sees the reply they typed');
await select('CUST00676');await app.askCoach('€30');
assert.equal(calls.filter(call=>call.path==='/api/agent').at(-1).body.message,'€30','A price must not continue another customer’s plan');
''')

    def test_spending_ring_rows_use_the_same_consumption_filter_as_the_chart(self):
        self.node_app(r'''
const button=new Element('category-rows');button.dataset.categoryTransactions='Restaurants';calls.length=0;
await documentListeners.click({target:button});await settle();
const request=calls.find(call=>call.path==='/api/transactions');
assert.equal(request.query.category,'Restaurants');
assert.equal(request.query.consumption_only,'true','Refunds and saving transfers must not appear as purchases represented by the ring');
''')

    def test_comparison_evidence_keeps_both_periods(self):
        self.node_app(r'''
const originalFixture=fixture;
fixture=(path,customer)=>path==='/api/coach'?{intent:'transaction_statistics',source:'deterministic',tool_kind:'transaction_statistics_comparison',query_scope:{start:'2026-09-01',end:'2026-09-30',metric:'outflow_total',filters:{category:'Restaurants'}},tool_result:{current:{start:'2026-09-01',end:'2026-09-30',outflow_total_cents:22570,transaction_refs:['september']},comparison:{start:'2026-08-01',end:'2026-08-31',outflow_total_cents:11543,transaction_refs:['august']},outflow_delta_cents:11027,transaction_refs:['august','september']}}:originalFixture(path,customer);
await app.askCoach('Compare restaurant spending in September and August');
const key=get('coach-response').innerHTML.match(/data-evidence-rows="([^"]+)"/)?.[1];assert.ok(key);
const evidence=new Element('comparison-evidence');evidence.dataset.evidenceRows=key;calls.length=0;
await documentListeners.click({target:evidence});await settle();
const request=calls.find(call=>call.path==='/api/transactions');
assert.equal(request.query.start,'2026-08-01');assert.equal(request.query.end,'2026-09-30');
''')

    def test_tax_planning_clarification_keeps_its_explicit_form_action(self):
        self.node_app(r'''
const originalFixture=fixture;
fixture=(path,customer)=>path==='/api/coach'?{intent:'plan_tax',source:'deterministic',needs_clarification:true,clarification_code:null,clarification_question:'What tax amount and due date do you want to plan for?'}:originalFixture(path,customer);
await app.askCoach('Help me plan for a tax payment');
const action=get('coach-response').children.find(child=>typeof child.onclick==='function');
assert.ok(action,'The user must be able to supply the requested amount and due date');
action.onclick();assert.equal(get('coach-more').open,true);assert.equal(get('coach-tax').open,true);assert.equal(get('tax-plan-amount').focused,true);
''')

    def test_forecast_evidence_includes_nested_variation_sources(self):
        self.node_app(r'''
const originalFixture=fixture;
fixture=(path,customer)=>path==='/api/coach'?{intent:'preview_cashflow',source:'deterministic',parameters:{reference_date:'2026-08-31'}}:path==='/api/forecast'?{as_of:'2026-08-31',projected:[{date:'2026-09-30',balance_cents:473436}],transaction_refs:['recurring'],scenario_band:{comparison_transaction_refs:['past-variation','recurring']}}:originalFixture(path,customer);
await app.askCoach('Show cash flow as of 2026-08-31');
assert.ok(get('coach-response').innerHTML.includes('Source rows (2)'),'The displayed historical variation needs its source records, with duplicates removed');
''')

    def test_comparison_details_honor_income_and_count_metrics(self):
        self.node_app(r'''
const base={tool_kind:'transaction_statistics_comparison',tool_result:{current:{start:'2026-09-01',end:'2026-09-30',inflow_total_cents:200000,outflow_total_cents:0,outflow_count:5},comparison:{start:'2026-08-01',end:'2026-08-31',inflow_total_cents:190000,outflow_total_cents:0,outflow_count:2},outflow_delta_cents:0,transaction_refs:[]}};
const income=app.toolResultHTML({...base,query_scope:{metric:'inflow_total'}});
assert.ok(income.includes('€1,900.00 → €2,000.00'),'Income comparison details must use income, not outgoing totals');
assert.ok(income.includes('€100.00'));
const count=app.toolResultHTML({...base,query_scope:{metric:'transaction_count'}});
assert.ok(count.includes('2 → 5'));assert.ok(!count.includes('€'),'Payment counts must not turn into money');
''')


if __name__ == '__main__':
    unittest.main()
