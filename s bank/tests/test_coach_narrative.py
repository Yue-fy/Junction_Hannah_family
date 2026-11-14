"""Coach answers must explain the requested result before supporting visuals."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


MODULE = Path(__file__).resolve().parents[1] / "web" / "coach-narrative.js"


@unittest.skipUnless(shutil.which("node"), "Node is required for narrative checks")
class CoachNarrativeTests(unittest.TestCase):
    def check(self, assertions):
        self.assertTrue(MODULE.is_file(), "The prose-first narrative module is missing")
        script = (
            'import assert from "node:assert/strict";\n'
            'const {coachNarrative}=await import("data:text/javascript;base64,"+'
            'Buffer.from(' + json.dumps(MODULE.read_text()) + ').toString("base64"));\n'
            + r"""
const format = {
 locale:'en',
 money:value=>new Intl.NumberFormat('en-IE',{style:'currency',currency:'EUR'}).format(value/100),
 dateLabel:value=>value.slice(0,10),
 monthLabel:value=>value,
 categoryName:value=>value,
 flowName:value=>({income:'Income',fixed_obligation:'Regular essentials',flexible_essential:'Irregular essentials',discretionary:'Everyday choices'}[value]||value),
 selectedMonth:'2026-09',
};
const narrate=(response,options={})=>coachNarrative(response,{...format,...options});
const statistics=(metric='outflow_total',changes={},scope={})=>({
 tool_kind:'transaction_statistics',source:'deterministic',
 explanation_blocks:[{text:'Here are the exact observed results for the selected category and period.'}],
 query_scope:{concept:'Restaurants',metric,start:'2026-08-01',end:'2026-08-31',filters:{category:'Restaurants'},...scope},
 tool_result:{start:'2026-08-01',end:'2026-08-31',filters:{category:'Restaurants'},has_transactions:true,
  outflow_total_cents:11543,inflow_total_cents:0,outflow_count:10,inflow_count:0,transaction_count:10,
  average_outflow_cents:1154,largest_outflow:{amount_cents:2240,date:'2026-08-17'},
  ...changes},
});
function valid(paragraphs){
 assert.ok(Array.isArray(paragraphs));
 assert.ok(paragraphs.length>=1&&paragraphs.length<=3);
 assert.ok(paragraphs.every(value=>typeof value==='string'&&value.trim()));
 assert.doesNotMatch(paragraphs.join(' '),/<\/?[a-z][^>]*>/i);
 assert.doesNotMatch(paragraphs.join(' '),/undefined|null|NaN/);
}
"""
            + assertions
        )
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_requested_statistic_and_returned_period_lead_instead_of_generic_intro(self):
        self.check(r"""
const cases=[
 ['outflow_total',{},'€115.43',/spent|spending/i],
 ['average_outflow',{metric_value_cents:1154},'€11.54',/average.*(?:purchase|payment)/i],
 ['transaction_count',{metric_value_count:10},'10',/(?:payments|purchases)/i],
 ['largest_outflow',{metric_value_cents:2240},'€22.40',/largest/i],
];
for(const [metric,changes,amount,meaning] of cases){
 const answer=narrate(statistics(metric,changes));valid(answer);
 assert.ok(answer[0].includes(amount));assert.match(answer[0],meaning);
 assert.ok(answer[0].includes('Restaurants'));assert.ok(answer[0].includes('2026-08-01'));
 assert.ok(answer[0].includes('2026-08-31'));assert.ok(!answer[0].includes('2026-09'));
 assert.ok(!answer.join(' ').includes('Here are the exact observed results'));
 if(metric!=='outflow_total')assert.ok(!answer[0].includes('€115.43'));
 if(metric==='largest_outflow')assert.ok(answer[0].includes('2026-08-17'));
}
""")

    def test_unknown_values_and_empty_narrow_results_do_not_claim_zero_spending(self):
        self.check(r"""
for(const metric of ['outflow_total','average_outflow','largest_outflow']){
 const response=statistics(metric,{metric_value_cents:null,outflow_total_cents:null,average_outflow_cents:null,largest_outflow:null});
 const answer=narrate(response);valid(answer);assert.ok(!answer.join(' ').includes('€0.00'));
 assert.match(answer.join(' '),/unavailable|cannot|could not|no .*available|not available/i);
}
const answer=narrate(statistics('outflow_total',{has_transactions:false,outflow_count:0,transaction_count:0,metric_value_cents:0},
 {concept:'Taxi',filters:{mcc_code:'4121'}}));valid(answer);
assert.match(answer[0],/no .*identified|no .*found|no .*recorded/i);
assert.match(answer.join(' '),/Taxi/i);assert.match(answer.join(' '),/missing|different codes/i);
assert.ok(!answer[0].includes('€0.00'));
""")

    def test_income_keeps_credits_separate_from_outflows_transfers_and_gross_pay(self):
        self.check(r"""
const income=statistics('inflow_total',{metric_value_cents:244781,inflow_total_cents:244781,inflow_count:1,outflow_count:0,outflow_total_cents:0},
 {concept:'Income received',filters:{role:'income'}});
let answer=narrate(income);valid(answer);
assert.ok(answer[0].includes('€2,447.81'));assert.ok(!answer[0].includes('€0.00'));
assert.match(answer[0],/received|credited/i);assert.match(answer.join(' '),/salary/i);
assert.match(answer.join(' '),/transfers.*separate|excludes.*transfers/i);
assert.match(answer.join(' '),/gross/i);
answer=narrate({...income,query_scope:{...income.query_scope,concept:'All inflows',filters:{}}});
assert.match(answer.join(' '),/includes.*transfers/i);assert.match(answer.join(' '),/not.*(?:earned income|earnings)/i);
answer=narrate({...income,query_scope:{...income.query_scope,concept:'Investment withdrawals',filters:{transaction_type:'investment_withdrawal'}}});
assert.match(answer.join(' '),/withdrawals/i);assert.match(answer.join(' '),/not.*(?:returns|earnings)/i);
""")

    def test_scenario_leads_with_modeled_amount_and_keeps_adjustable_base(self):
        self.check(r"""
const response={tool_kind:'spending_adjustment_preview',tool_result:{
 category:'Restaurants',percent:'12.5',start:'2026-08-01',end:'2026-08-31',
 actual_total_cents:22570,adjustable_base_cents:18923,modeled_monthly_contribution_cents:2365,persistence:'not_saved',
}};
const before=JSON.stringify(response),answer=narrate(response);valid(answer);
assert.ok(answer[0].includes('€23.65'));assert.ok(answer[0].includes('12.5'));
assert.ok(answer.join(' ').includes('€189.23'));assert.ok(answer.join(' ').includes('2026-08-01'));
assert.match(answer.join(' '),/unsaved|not saved/i);assert.match(answer.join(' '),/nothing.*(?:moved|saved)|no money/i);
assert.equal(JSON.stringify(response),before);
""")

    def test_all_outflows_and_investment_deposits_are_not_called_consumption(self):
        self.check(r"""
for(const scope of [
 {concept:'All outflows',filters:{}},
 {concept:'Investment deposits',filters:{transaction_type:'investment_deposit'}},
 {concept:'Saving and transfers',filters:{role:'saving_or_transfer'}},
]){
 const answer=narrate(statistics('outflow_total',{metric_value_cents:10000,outflow_count:1},scope));
 valid(answer);assert.ok(answer[0].includes('€100.00'));
 assert.match(answer[0],/outgoing|left the account|transferred/i);
 assert.doesNotMatch(answer[0],/you spent|consumer spending/i);
 assert.doesNotMatch(answer[0],/1 (?:outgoing )?payments/);
}
""")

    def test_comparison_retains_both_periods_and_requested_metric(self):
        self.check(r"""
let answer=narrate({tool_kind:'spending_comparison',tool_result:{
 current:{start:'2026-09-01',end:'2026-09-30',total_cents:22570,count:10,average_cents:2257},
 previous:{start:'2026-08-01',end:'2026-08-31',total_cents:11543,count:10,average_cents:1154},delta_cents:11027,
}});valid(answer);
for(const value of ['€225.70','€115.43','2026-09-01','2026-08-01'])assert.ok(answer[0].includes(value));
assert.ok(answer.join(' ').includes('€110.27'));assert.match(answer.join(' '),/higher|increase/i);
answer=narrate({tool_kind:'transaction_statistics_comparison',query_scope:{metric:'inflow_total',filters:{role:'income'},concept:'Income received'},
 tool_result:{current:{start:'2026-09-01',end:'2026-09-30',inflow_total_cents:200000,outflow_total_cents:0},
 comparison:{start:'2026-08-01',end:'2026-08-31',inflow_total_cents:190000,outflow_total_cents:0},outflow_delta_cents:0}});
valid(answer);assert.ok(answer[0].includes('€2,000.00'));assert.ok(answer[0].includes('€1,900.00'));
assert.ok(!answer.join(' ').includes('€0.00'));assert.match(answer[0],/received|credited|incoming/i);
""")

    def test_safe_estimate_keeps_historical_clock_reserve_and_limits_visible(self):
        self.check(r"""
let answer=narrate({tool_kind:'safe_to_spend',tool_result:{available:true,reference_date:'2026-09-30',horizon_days:7,horizon_end:'2026-10-07',
 safe_to_spend_cents:328831,reserve_floor_cents:50000,reserve_floor_source:'demo_default',scheduled_outflows_cents:52838,historical_flexible_buffer_cents:40689}});
valid(answer);
for(const value of ['€3,288.31','2026-09-30','2026-10-07'])assert.ok(answer[0].includes(value));
assert.match(answer[0],/estimate/i);assert.ok(answer.join(' ').includes('€500.00'));
assert.match(answer.join(' '),/demo/i);assert.match(answer.join(' '),/goal/i);assert.match(answer.join(' '),/tax/i);
answer=narrate({tool_kind:'safe_to_spend',tool_result:{available:false,safe_to_spend_cents:null}});
valid(answer);assert.match(answer.join(' '),/history|records/i);assert.ok(!answer.join(' ').includes('€0.00'));
""")

    def test_forecast_uses_valid_returned_points_for_ending_and_lowest_balances(self):
        self.check(r"""
const response={tool_kind:'cashflow_forecast',tool_result:{as_of:'2026-08-31',projected:[
 {date:'2026-09-01',balance_cents:400000},
 {date:'2026-09-02',balance_cents:null},
 {date:'2026-09-21',balance_cents:296609},
 {date:'2026-09-30',balance_cents:473436},
]}};
const answer=narrate(response);valid(answer);
for(const value of ['€4,734.36','€2,966.09','2026-08-31','2026-09-21','2026-09-30'])assert.ok(answer[0].includes(value));
assert.match(answer.join(' '),/estimate|preview/i);assert.match(answer.join(' '),/not.*probability/i);
const missing=narrate({tool_kind:'cashflow_forecast',tool_result:{projected:[{date:'2026-09-30',balance_cents:null}]}});
valid(missing);assert.ok(!missing.join(' ').includes('€0.00'));
""")

    def test_zero_allowance_does_not_claim_reserve_or_expected_costs_are_funded(self):
        self.check(r"""
const response={tool_kind:'safe_to_spend',tool_result:{available:true,
 reference_date:'2026-09-30',horizon_days:7,horizon_end:'2026-10-07',
 starting_balance_cents:31214,safe_to_spend_cents:0,reserve_floor_cents:50000,
 reserve_floor_source:'demo_default',scheduled_outflows_cents:10000,historical_flexible_buffer_cents:10000}};
for(const [locale,noRoom,method] of [
 ['en',/no estimated room for (?:extra|additional) spending/i,/calculation deducts/i],
 ['fi',/ei .*arvioitua.*(?:lisäkulutus|ylimääräis)/i,/laskelma vähentää/i],
 ['sv',/inget uppskattat utrymme för (?:extra|ytterligare) utgifter/i,/beräkningen drar av/i],
]){
 const answer=narrate(response,{locale});valid(answer);
 assert.match(answer[0],noRoom);assert.match(answer.join(' '),method);
 assert.doesNotMatch(answer.join(' '),/leaves room for|jättää tilaa|lämnar utrymme/i);
 assert.ok(answer[0].includes('2026-09-30'));assert.ok(answer[0].includes('2026-10-07'));
 assert.ok(answer.join(' ').includes('€500.00'));
 const positive=narrate({...response,tool_result:{...response.tool_result,safe_to_spend_cents:10000,starting_balance_cents:80000}},{locale});
 assert.match(positive.join(' '),method);assert.doesNotMatch(positive.join(' '),noRoom);
}
""")

    def test_investment_prose_reports_transfers_and_coverage_without_returns(self):
        self.check(r"""
const answer=narrate({tool_kind:'investment_cashflow',tool_result:{start_month:'2025-10',end_month:'2026-09',
 total_contributions_cents:277585,withdrawals_cents:0,contribution_months:12,period_months:12,coverage_limited:false}});
valid(answer);
for(const value of ['€2,775.85','€0.00','2025-10','2026-09'])assert.ok(answer[0].includes(value));
assert.match(answer.join(' '),/12.*12/);assert.match(answer.join(' '),/not.*(?:returns|performance)/i);
const missing=narrate({tool_kind:'investment_cashflow',tool_result:{total_contributions_cents:null,withdrawals_cents:null}});
valid(missing);assert.ok(!missing.join(' ').includes('€0.00'));
""")

    def test_vat_and_explicit_tax_do_not_confuse_estimate_coverage_or_absence(self):
        self.check(r"""
let answer=narrate({tool_kind:'vat_estimate',tool_result:{start:'2026-09-01',end:'2026-09-30',estimated_vat_cents:21238,
 gross_spending_cents:187866,covered_spending_cents:187866,coverage_basis_points:10000}});
valid(answer);assert.ok(answer[0].includes('€212.38'));assert.ok(answer[0].includes('€1,878.66'));
assert.match(answer[0],/included/i);assert.match(answer.join(' '),/not.*accuracy/i);assert.match(answer.join(' '),/not.*(?:extra|additional|liability)/i);
answer=narrate({tool_kind:'vat_estimate',tool_result:{estimated_vat_cents:0,gross_spending_cents:1234,covered_spending_cents:0,coverage_basis_points:0}});
valid(answer);assert.match(answer.join(' '),/unavailable|cannot|not available/i);assert.ok(!answer[0].includes('€0.00'));
answer=narrate({tool_kind:'observed_tax_evidence',tool_result:{available:false,observed_tax_paid_cents:null,observed_tax_refund_cents:null}});
valid(answer);assert.match(answer.join(' '),/does not mean.*no tax|does not establish.*no tax/i);assert.ok(!answer.join(' ').includes('€0.00'));
answer=narrate({tool_kind:'observed_tax_evidence',tool_result:{available:true,start:'2026-08-01',end:'2026-08-31',
 observed_tax_paid_cents:60000,observed_tax_refund_cents:10000,observed_net_tax_cents:50000}});
valid(answer);assert.ok(answer[0].includes('€600.00'));assert.ok(answer[0].includes('€100.00'));
assert.match(answer[0],/payments|paid/i);assert.match(answer[0],/refund/i);assert.ok(answer[0].includes('2026-08-01'));
""")

    def test_baskets_and_mortgage_describe_records_without_a_personality_or_current_approval(self):
        self.check(r"""
let answer=narrate({tool_kind:'three_basket_profile',tool_result:{period:'2026-09',total_consumption_cents:187866,baskets:[
 {role:'fixed_obligation',amount_cents:126690},{role:'flexible_essential',amount_cents:0},{role:'discretionary',amount_cents:61176},
]}});
valid(answer);assert.ok(answer[0].includes('€1,878.66'));assert.ok(answer.join(' ').includes('€1,266.90'));
assert.match(answer.join(' '),/not.*score|no.*score/i);
answer=narrate({tool_kind:'home_financing_history',tool_result:{available:true,recorded_outcome:{decision:'approved'},
 requested_loan_cents:18000000,equity_cents:2000000,property_price_cents:null}});
valid(answer);assert.match(answer[0],/historical|past/i);assert.match(answer[0],/approved/i);
assert.ok(answer[0].includes('€180,000.00'));assert.ok(!answer.join(' ').includes('€0.00'));
assert.match(answer.join(' '),/not.*current|do not.*current/i);
answer=narrate({tool_kind:'home_financing_history',tool_result:{available:false,recorded_fees_total_cents:0}});
valid(answer);assert.match(answer.join(' '),/no.*history|history.*unavailable/i);assert.ok(!answer.join(' ').includes('€0.00'));
""")

    def test_supplied_clarifications_purchase_answers_and_meaningful_gemini_copy_are_preserved(self):
        self.check(r"""
assert.deepEqual(narrate({needs_clarification:true,explanation_blocks:[{text:'A wish is enough.'},{text:'A wish is enough.'}],
 clarification_question:'What would you like to explore?'}),['A wish is enough.','What would you like to explore?']);
const purchase={tool_kind:'planned_purchase_preview',tool_result:{},source:'deterministic',
 explanation_blocks:[{text:'The €20 plan fits the historical estimate.'},{text:'This uses 30 September, not today.'}]};
assert.deepEqual(narrate(purchase),purchase.explanation_blocks.map(block=>block.text));
assert.deepEqual(narrate({...purchase,tool_kind:'safe_to_spend',clarification_code:'planned_purchase_preview',
 tool_result:{available:true,safe_to_spend_cents:328831}}),purchase.explanation_blocks.map(block=>block.text));
const answer=narrate({...statistics(),source:'gemini',explanation_blocks:[
 {text:'Your purchase sizes varied.'},{text:'Your purchase sizes varied.'},
 {text:'Here are the exact observed results for the selected category and period.'},
]});
valid(answer);assert.ok(answer[0].includes('€115.43'));
assert.equal(answer.join(' ').split('Your purchase sizes varied.').length-1,1);
assert.ok(!answer.join(' ').includes('Here are the exact observed results'));
const plain=narrate({explanation_blocks:[{text:'Useful <strong>context</strong>.'}],clarification_question:'Which period?'});
valid(plain);assert.ok(plain.join(' ').includes('Useful context.'));
""")

    def test_supported_locales_keep_financial_facts_and_missing_values(self):
        self.check(r"""
for(const locale of ['en','fi','sv']){
 for(const response of [
  statistics('average_outflow',{metric_value_cents:1154}),
  {tool_kind:'safe_to_spend',tool_result:{available:true,reference_date:'2026-09-30',horizon_end:'2026-10-07',safe_to_spend_cents:12345}},
  {tool_kind:'vat_estimate',tool_result:{estimated_vat_cents:1234,gross_spending_cents:10000,covered_spending_cents:10000,coverage_basis_points:10000}},
  {tool_kind:'observed_tax_evidence',tool_result:{available:false}},
 ]){
  const answer=narrate(response,{locale});valid(answer);
  if(locale!=='en')assert.notEqual(answer[0],narrate(response)[0]);
 }
 const average=narrate(statistics('average_outflow',{metric_value_cents:1154}),{locale});
 assert.ok(average[0].includes('€11.54'));assert.ok(average[0].includes('2026-08-01'));
 const missing=narrate(statistics('average_outflow',{metric_value_cents:null,average_outflow_cents:null}),{locale});
 valid(missing);assert.ok(!missing.join(' ').includes('€0.00'));
}
""")
