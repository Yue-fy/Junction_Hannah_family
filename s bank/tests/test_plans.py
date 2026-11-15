"""V4 lane P: optional mortgage and tax plans (money-profile entries, arithmetic, API, agent tools, UI)."""
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from scoach import money_profile as mp, mortgage, plans
from scoach.agent_tools import DECLARATIONS, ToolContext, dispatch
from scoach.api import Application
from scoach.db import connect, initialize_schema
from scoach.state import undo_last
from tests.core_helper import demo_connection

WEB = pathlib.Path(__file__).resolve().parents[1] / 'web'
DEMO_DB = pathlib.Path(__file__).resolve().parents[1] / 'var/scoach.sqlite3'
TAYLOR, ALEX = 'CUST00296', 'CUST00001'
PLAN = {'principal_cents': 18_000_000, 'loan_type': 'annuity', 'reference_rate': 'euribor_12m',
        'reference_rate_bp': 225, 'margin_bp': 60, 'remaining_months': 240, 'payment_day': 4}


def synthetic(balance=100000, loan=True, decision=None):
    """One customer: salary on the 15th, groceries, rent-like housing payment on the 5th, optional loan row."""
    conn = connect(':memory:'); initialize_schema(conn)
    conn.execute("INSERT INTO customers VALUES('CUST09999','00100',40,'{}')")
    n = [0]
    def add(day, category, cents, kind):
        n[0] += 1
        conn.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                     ('tx:%s:s' % n[0], 'CUST09999', 'ACC009999', day, '01JAN25:10:00:%02d' % (n[0] % 60), category, cents,
                      balance, kind, None, None, n[0], 'h%s' % n[0], '{}'))
    for month in ['2026-%02d' % m for m in range(1, 10)]:
        add(month + '-05', 'Housing', -90000, 'housing_payment')
        add(month + '-15', 'Salary', 300000, 'salary')
        add(month + '-20', 'Groceries', -60000, 'purchase')
    add('2026-09-30', 'Groceries', -1000, 'purchase')
    if decision:
        conn.execute("INSERT INTO mortgage_final(customer_id,mortgage_customer_id,raw_json) VALUES('CUST09999','C9',?)",
                     (json.dumps({'final_decision': decision, 'final_requested_loan_eur': '150000'}),))
    conn.commit()
    return conn


class ValidationTests(unittest.TestCase):
    def test_plan_mortgage_valid_and_normalised(self):
        value = mp.validate_entry('plan_mortgage', {**PLAN, 'reference_rate_bp': -50, 'next_rate_check': '2027-03', 'payment_day': None})
        self.assertEqual(value['reference_rate_bp'], -50)  # Euribor can be negative
        self.assertNotIn('payment_day', value)
        self.assertEqual(mp.validate_entry('plan_mortgage', {k: v for k, v in PLAN.items() if k != 'remaining_months'} | {'monthly_payment_cents': 95000})['monthly_payment_cents'], 95000)

    def test_plan_mortgage_rejects_bad_values(self):
        bad = [{**PLAN, 'loan_type': 'balloon'}, {**PLAN, 'reference_rate': 'prime'}, {**PLAN, 'margin_bp': -1},
               {k: v for k, v in PLAN.items() if k != 'remaining_months'},
               {k: v for k, v in PLAN.items() if k != 'remaining_months'} | {'loan_type': 'equal_principal', 'monthly_payment_cents': 1000},
               {**PLAN, 'remaining_months': 0}, {**PLAN, 'principal_cents': 10.5}, {**PLAN, 'surprise': 1}, {**PLAN, 'next_rate_check': '2027-13'}]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                mp.validate_entry('plan_mortgage', value)

    def test_plan_tax(self):
        self.assertEqual(mp.validate_entry('plan_tax', {'on': True, 'expected_back_tax_cents': 60000}), {'on': True, 'expected_back_tax_cents': 60000})
        for value in ({'on': False}, {}, {'on': True, 'expected_refund_cents': -1}, {'on': True, 'rate': 1}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                mp.validate_entry('plan_tax', value)
        self.assertIn('plan_mortgage', mp.SINGLE_KEYS)
        self.assertIn('plan_tax', mp.SINGLE_KEYS)


class MortgageMathTests(unittest.TestCase):
    def test_annuity_payment_matches_the_standard_formula(self):
        # 180 000 € over 20 years at 2.85 % (12-month Euribor 2.25 % + 0.60 % margin): about €984.82 a month.
        self.assertEqual(mortgage.annuity_payment(18_000_000, 285, 240), 98482)
        self.assertEqual(mortgage.annuity_payment(120_000, 0, 12), 10000)
        run = mortgage.simulate(18_000_000, 285, 'annuity', months=240)
        self.assertEqual(run['months'], 240)
        self.assertEqual(run['rows'][-1]['balance_cents'], 0)
        self.assertEqual(sum(r['principal_cents'] for r in run['rows']), 18_000_000)
        self.assertEqual(run['total_paid_cents'], 18_000_000 + run['total_interest_cents'])

    def test_equal_principal_payment_falls_and_costs_less_interest(self):
        equal = mortgage.simulate(18_000_000, 285, 'equal_principal', months=240)
        annuity = mortgage.simulate(18_000_000, 285, 'annuity', months=240)
        self.assertEqual(equal['rows'][0]['principal_cents'], 75000)
        self.assertEqual(equal['rows'][0]['interest_cents'], 42750)  # 180 000 × 2.85 % / 12
        self.assertGreater(equal['rows'][0]['payment_cents'], equal['rows'][-1]['payment_cents'])
        self.assertLess(equal['total_interest_cents'], annuity['total_interest_cents'])

    def test_extra_payment_shortens_the_loan(self):
        p = mortgage.projection(PLAN, '2026-09-30', extra_cents=10000)
        self.assertEqual(p['monthly_payment_cents'], 98482)
        self.assertEqual(p['first_payment_month'], '2026-10')
        self.assertEqual(p['payoff_month'], '2046-09')
        self.assertGreater(p['what_if']['months_saved'], 0)
        self.assertGreater(p['what_if']['interest_saved_cents'], 0)
        self.assertLess(p['what_if']['payoff_month'], p['payoff_month'])

    def test_rate_change_moves_the_payment(self):
        p = mortgage.projection(PLAN, '2026-09-30', rate_delta_bp=100)
        self.assertEqual(p['rate_change']['up']['rate_bp'], 385)
        self.assertGreater(p['rate_change']['up']['payment_change_cents'], 0)
        self.assertLess(p['rate_change']['down']['payment_change_cents'], 0)
        self.assertEqual(p['selected_rate'], p['rate_change']['up'])
        # A typed payment with no term: a rate rise lengthens the loan instead.
        fixed = mortgage.projection({k: v for k, v in PLAN.items() if k != 'remaining_months'} | {'monthly_payment_cents': 95000}, '2026-09-30')
        self.assertEqual(fixed['rate_change']['up']['monthly_payment_cents'], 95000)
        self.assertGreater(fixed['rate_change']['up']['months_left'], fixed['months_left'])

    def test_payment_below_interest_is_refused(self):
        with self.assertRaises(ValueError):
            mortgage.projection({k: v for k, v in PLAN.items() if k != 'remaining_months'} | {'monthly_payment_cents': 40000}, '2026-09-30')

    def test_typed_payment_that_differs_is_noted(self):
        p = mortgage.projection({**PLAN, 'monthly_payment_cents': 136260}, '2026-09-30')
        self.assertEqual(p['monthly_payment_cents'], 136260)  # what the customer really pays is held back
        self.assertIn('payment_differs', p['notes'])

    def test_extra_payments_are_not_suggested_in_steady_mode_or_with_a_thin_buffer(self):
        self.assertEqual(mortgage.projection(PLAN, '2026-09-30', steady=True)['extra_advice'], {'suggest': False, 'reason': 'steady'})
        self.assertEqual(mortgage.projection(PLAN, '2026-09-30', buffer={'thin': True})['extra_advice'], {'suggest': False, 'reason': 'buffer_thin'})
        self.assertTrue(mortgage.projection(PLAN, '2026-09-30', buffer={'thin': False})['extra_advice']['suggest'])


class AccountTests(unittest.TestCase):
    def test_detects_housing_payment_and_buffer(self):
        conn = synthetic(balance=50000)
        found = mortgage.detect_loan_payment(conn, 'CUST09999', '2026-09-30')
        self.assertEqual((found['found'], found['monthly_payment_cents'], found['payment_day'], found['source']), (True, 90000, 5, 'housing_payment'))
        self.assertIsNone(found['principal_cents'])
        buffer = mortgage.buffer_check(conn, 'CUST09999', '2026-09-30')
        self.assertEqual(buffer['monthly_spending_cents'], 150000)
        self.assertTrue(buffer['thin'])
        self.assertFalse(mortgage.buffer_check(synthetic(balance=400000), 'CUST09999', '2026-09-30')['thin'])

    def test_only_an_approved_application_prefills_the_loan_amount(self):
        approved = mortgage.detect_loan_payment(synthetic(decision='approved'), 'CUST09999', '2026-09-30')
        self.assertEqual((approved['principal_cents'], approved['principal_source']), (15_000_000, 'loan_application'))
        rejected = mortgage.detect_loan_payment(synthetic(decision='rejected'), 'CUST09999', '2026-09-30')
        self.assertIsNone(rejected['principal_cents'])

    def test_profile_mortgage_wins(self):
        conn = synthetic()
        mp.save_entry(conn, 'CUST09999', 'debts', {'type': 'mortgage', 'monthly_payment_cents': 88000, 'remaining_cents': 9_000_000}, 'you_told_me')
        found = mortgage.detect_loan_payment(conn, 'CUST09999', '2026-09-30')
        self.assertEqual((found['monthly_payment_cents'], found['principal_cents'], found['source']), (88000, 9_000_000, 'profile'))

    def test_plan_card_uses_steady_mode_and_thin_buffer(self):
        conn = synthetic(balance=50000)
        plans.save_plan(conn, 'CUST09999', 'mortgage', PLAN, as_of='2026-09-30')
        self.assertEqual(plans.mortgage_plan(conn, 'CUST09999', '2026-09-30')['projection']['extra_advice']['reason'], 'buffer_thin')
        mp.save_entry(conn, 'CUST09999', 'life_event', {'type': 'job_loss', 'since': '2026-09'}, 'you_told_me')
        card = plans.mortgage_plan(conn, 'CUST09999', '2026-09-30', extra_cents=10000)
        self.assertTrue(card['steady'])
        self.assertEqual(card['projection']['extra_advice']['reason'], 'steady')


class ProfileIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.conn = synthetic()
        self.cid = 'CUST09999'

    def test_plans_are_profile_entries_with_audit_undo_and_forget(self):
        saved = plans.save_plan(self.conn, self.cid, 'mortgage', PLAN, as_of='2026-09-30')
        self.assertEqual(saved['entry']['source_label'], 'You told me')
        profile = mp.get_profile(self.conn, self.cid, '2026-09-30')
        self.assertEqual(profile['by_key']['plan_mortgage']['id'], saved['entry']['id'])
        self.assertIn('Mortgage plan on', mp.profile_summary(profile))
        # Saving again replaces (single key).
        again = plans.save_plan(self.conn, self.cid, 'mortgage', {**PLAN, 'margin_bp': 50}, as_of='2026-09-30')
        self.assertEqual(again['replaced_entry_ids'], [saved['entry']['id']])
        undo_last(self.conn, self.cid)
        self.assertEqual(mp.get_profile(self.conn, self.cid)['by_key']['plan_mortgage']['value']['margin_bp'], 60)
        plans.save_plan(self.conn, self.cid, 'tax', {'on': True}, as_of='2026-09-30')
        mp.forget_all(self.conn, self.cid)
        self.assertEqual(plans.plans_overview(self.conn, self.cid, '2026-09-30')['set_asides'], [])

    def test_unrepayable_plan_is_refused(self):
        with self.assertRaises(ValueError):
            plans.save_plan(self.conn, self.cid, 'mortgage', {k: v for k, v in PLAN.items() if k != 'remaining_months'} | {'monthly_payment_cents': 30000})

    def test_planning_inputs_expose_monthly_set_asides(self):
        empty = mp.planning_inputs(mp.get_profile(self.conn, self.cid, '2026-09-30'))
        self.assertEqual((empty['plan_set_asides'], empty['plan_set_asides_monthly_total_cents']), ([], 0))
        plans.save_plan(self.conn, self.cid, 'mortgage', PLAN)
        plans.save_plan(self.conn, self.cid, 'tax', {'on': True, 'expected_back_tax_cents': 60000})
        inputs = mp.planning_inputs(mp.get_profile(self.conn, self.cid, '2026-09-30'))
        loan, tax_item = inputs['plan_set_asides']
        self.assertEqual((loan['kind'], loan['amount_cents'], loan['day_of_month']), ('loan', 98482, 4))
        self.assertEqual(loan['dedupe_hint']['transaction_type'], 'housing_payment')
        # 600 € spread over the 12 calendar months until about September next year.
        self.assertEqual((tax_item['kind'], tax_item['amount_cents'], tax_item['until']), ('tax', 5000, '2027-09-01'))
        self.assertEqual(inputs['plan_set_asides_monthly_total_cents'], 103482)
        self.assertEqual(inputs['debts'], [])  # plans are not debts: never held back twice
        json.dumps(inputs)

    def test_tax_plan_off_holds_nothing_back(self):
        mp.save_entry(self.conn, self.cid, 'tax', {'tax_year': 2025, 'decision_result': 'back_tax', 'decision_amount_cents': 40000,
                                                   'assessment_end_month': '2026-09'}, 'you_told_me')
        self.assertEqual(mp.planning_inputs(mp.get_profile(self.conn, self.cid, '2026-09-30'))['plan_set_asides'], [])


class TaxPlanTests(unittest.TestCase):
    def setUp(self):
        self.conn = synthetic()
        self.cid = 'CUST09999'
        plans.save_plan(self.conn, self.cid, 'tax', {'on': True})

    def test_back_tax_decision_is_split_over_the_calendar_instalments(self):
        mp.save_entry(self.conn, self.cid, 'tax', {'tax_year': 2025, 'decision_result': 'back_tax', 'decision_amount_cents': 40000,
                                                   'assessment_end_month': '2026-09', 'already_set_aside_cents': 5000}, 'you_told_me')
        result = plans.tax_set_aside(mp.get_profile(self.conn, self.cid, '2026-09-30'), '2026-09-30')
        dates = [(i['due_date'], i['amount_cents'], i['already_set_aside_cents']) for i in result['instalments']]
        self.assertEqual(dates, [('2026-11-02', 20000, 5000), ('2027-01-04', 20000, 0)])
        # 150 € over two months, 200 € over four months.
        self.assertEqual(result['monthly_cents'], 7500 + 5000)
        self.assertEqual(result['until'], '2027-01-04')
        card = plans.tax_plan(self.conn, self.cid, '2026-09-30')
        self.assertTrue(card['on'])
        self.assertEqual([d['kind'] for d in card['dates']], ['back_tax', 'back_tax'])

    def test_refund_expectation_and_tax_card_check(self):
        mp.save_entry(self.conn, self.cid, 'tax', {'tax_year': 2025, 'decision_result': 'refund', 'decision_amount_cents': 35000,
                                                   'assessment_end_month': '2026-10'}, 'you_told_me')
        mp.save_entry(self.conn, self.cid, 'tax', {'tax_year': 2026, 'base_rate_bp': 2000, 'income_limit_cents': 3_000_000,
                                                   'gross_monthly_cents': 400_000}, 'you_told_me')
        card = plans.tax_plan(self.conn, self.cid, '2026-09-30')
        self.assertEqual((card['refund']['amount_cents'], card['refund']['expected_date']), (35000, '2026-12-03'))
        self.assertEqual(card['tax_card']['status'], 'income_above_limit')  # 48 000 € a year vs a 30 000 € limit
        self.assertEqual(card['set_aside']['monthly_cents'], 0)
        self.assertTrue(any('OmaVero' in task for task in card['tasks']))

    def test_missing_tax_card_asks_for_two_fields(self):
        card = plans.tax_plan(self.conn, self.cid, '2026-09-30')
        self.assertEqual(card['tax_card'], {'status': 'missing', 'missing': ['gross_monthly_cents', 'base_rate_bp']})
        self.assertEqual(card['stage']['stage'], 'decision_pending')


class ApiTests(unittest.TestCase):
    def setUp(self):
        if not DEMO_DB.is_file():
            self.skipTest('demo database not built')
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / 'db.sqlite3'
        shutil.copy(DEMO_DB, self.db)
        self.app = Application(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, method, target, body=None):
        return self.app.handle(method, target, body)

    def test_plans_round_trip(self):
        status, body = self.call('GET', '/api/plans?customer_id=' + TAYLOR)
        self.assertEqual(status, 200, body)
        self.assertEqual([p['id'] for p in body['data']['plans']], ['mortgage', 'tax'])
        self.assertTrue(body['data']['plans'][0]['detected'])
        self.assertFalse(body['data']['plans'][0]['on'])
        status, body = self.call('POST', '/api/plans/mortgage', {'customer_id': TAYLOR, 'plan': PLAN})
        self.assertEqual(status, 400)  # confirmation required
        status, body = self.call('POST', '/api/plans/mortgage', {'customer_id': TAYLOR, 'plan': PLAN, 'confirmed': True})
        self.assertEqual(status, 200, body)
        status, body = self.call('GET', '/api/plans/mortgage/projection?customer_id=%s&extra_cents=5000&rate_delta_bp=-100' % TAYLOR)
        self.assertEqual(status, 200, body)
        projection = body['data']['projection']
        self.assertEqual(projection['monthly_payment_cents'], 98482)
        self.assertEqual(projection['what_if']['extra_cents'], 5000)
        self.assertEqual(projection['selected_rate']['rate_bp'], 185)
        status, body = self.call('GET', '/api/plans?customer_id=' + TAYLOR)
        self.assertEqual(body['data']['held_back_monthly_cents'], 98482)
        self.assertEqual(self.call('GET', '/api/plans/mortgage/projection?customer_id=%s&rate_delta_bp=--1' % TAYLOR)[0], 400)
        self.assertEqual(self.call('GET', '/api/plans/mortgage/projection?customer_id=%s&extra_cents=9999999' % TAYLOR)[0], 400)
        self.assertEqual(self.call('GET', '/api/plans?customer_id=%s&bogus=1' % TAYLOR)[0], 400)

    def test_tax_plan_and_validation(self):
        status, body = self.call('POST', '/api/plans/tax', {'customer_id': ALEX, 'plan': {'on': True, 'expected_refund_cents': 20000}, 'confirmed': True})
        self.assertEqual(status, 200, body)
        status, body = self.call('GET', '/api/plans/tax?customer_id=' + ALEX)
        self.assertEqual(status, 200, body)
        self.assertTrue(body['data']['on'])
        self.assertEqual(body['data']['refund']['source'], 'your_estimate')
        self.assertEqual(self.call('POST', '/api/plans/tax', {'customer_id': ALEX, 'plan': 'on', 'confirmed': True})[0], 400)
        self.assertEqual(self.call('POST', '/api/plans/mortgage', {'customer_id': ALEX, 'plan': {**PLAN, 'loan_type': 'x'}, 'confirmed': True})[0], 400)
        status, body = self.call('GET', '/api/profile?customer_id=' + ALEX)
        self.assertIn('plan_tax', [e['key'] for e in body['data']['profile']['entries']])


class AgentToolTests(unittest.TestCase):
    def setUp(self):
        if not DEMO_DB.is_file():
            self.skipTest('demo database not built')
        self.conn = demo_connection()

    def ctx(self, message=''):
        return ToolContext(self.conn, TAYLOR, '2026-09', message=message)

    def test_tools_are_declared(self):
        names = {d['name'] for d in DECLARATIONS}
        self.assertTrue({'mortgage_plan', 'tax_plan'} <= names)
        action = next(d for d in DECLARATIONS if d['name'] == 'propose_action')
        self.assertIn('enable_plan', action['parameters']['properties']['kind']['enum'])
        update = next(d for d in DECLARATIONS if d['name'] == 'propose_profile_update')
        self.assertNotIn('plan_mortgage', update['parameters']['properties']['entries']['items']['properties']['key']['enum'])

    def test_mortgage_plan_off_then_on(self):
        ctx = self.ctx()
        result = dispatch(self.conn, TAYLOR, ctx, 'mortgage_plan', {})
        self.assertFalse(result['on'])
        self.assertTrue(result['likely_loan_payment_seen'])
        plans.save_plan(self.conn, TAYLOR, 'mortgage', PLAN)
        ctx = self.ctx('what if I pay 100 euros extra each month?')
        result = dispatch(self.conn, TAYLOR, ctx, 'mortgage_plan', {'extra_cents': 10000})
        self.assertEqual(result['projection']['what_if']['months_saved'], 28)
        with self.assertRaises(ValueError):  # amounts must come from the customer
            dispatch(self.conn, TAYLOR, self.ctx('hello'), 'mortgage_plan', {'extra_cents': 12345})

    def test_tax_plan_and_enable_action(self):
        ctx = self.ctx()
        result = dispatch(self.conn, TAYLOR, ctx, 'tax_plan', {})
        self.assertFalse(result['on'])
        dispatch(self.conn, TAYLOR, ctx, 'propose_action', {'kind': 'enable_plan', 'params': {'plan': 'tax'}})
        self.assertEqual(ctx.actions[-1]['kind'], 'enable_plan')
        self.assertEqual(ctx.actions[-1]['params'], {'plan': 'tax'})
        with self.assertRaises(ValueError):
            dispatch(self.conn, TAYLOR, ctx, 'propose_action', {'kind': 'enable_plan', 'params': {'plan': 'car'}})


@unittest.skipUnless(shutil.which('node'), 'Node is required for UI checks')
class PlansUiTests(unittest.TestCase):
    def run_node(self, body):
        script = ('import assert from "node:assert/strict";\n'
                  'const m = await import(' + json.dumps((WEB / 'plans.js').as_uri()) + ');\n' + body)
        result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_copy_exists_in_three_languages(self):
        self.run_node(r"""
for (const key of m.PLAN_COPY_KEYS) for (const l of ['en','fi','sv']) { const v = m.planText(l, key); assert.ok(v && v !== key, key + ' ' + l); }
assert.equal(m.formatRate(285, 'en'), '2.85%'); assert.equal(m.formatRate(285, 'fi'), '2,85 %'); assert.equal(m.formatRate(60, 'sv'), '0,6 %');
assert.equal(m.formatRate(-50, 'fi'), '-0,5 %');
assert.equal(m.annuityPayment(18000000, 285, 240), 98482);
""")

    def test_form_value_conversion(self):
        self.run_node(r"""
const ok = m.mortgageValue({principal_cents: 18000000, loan_type: 'annuity', reference_rate: 'euribor_12m', reference_rate_pct: 2.25, margin_pct: 0.6, remaining_years: 20, monthly_payment_cents: null, payment_day: 4, next_rate_check: null});
assert.deepEqual(ok.value, {principal_cents: 18000000, loan_type: 'annuity', reference_rate: 'euribor_12m', reference_rate_bp: 225, margin_bp: 60, remaining_months: 240, payment_day: 4});
assert.equal(m.mortgageValue({principal_cents: 1, loan_type: 'annuity', reference_rate_pct: 1, margin_pct: 0}).error, 'f.needTerm');
assert.equal(m.mortgageValue({principal_cents: 1, loan_type: 'equal_principal', monthly_payment_cents: 5000, reference_rate_pct: 1, margin_pct: 0}).error, 'f.needTerm');
assert.deepEqual(m.taxValue({expected_back_tax_cents: 60000, expected_refund_cents: null}).value, {on: true, expected_back_tax_cents: 60000});
const spec = m.mortgageSpec('fi', {prefill: {monthly_payment_cents: 136260, payment_day: 4}});
assert.equal(spec.fields.find(f => f.name === 'monthly_payment_cents').value, 136260);
assert.equal(new Set(spec.fields.map(f => f.name)).size, spec.fields.length);
""")

    def test_cards_render_calm_and_respect_steady_mode(self):
        self.run_node(r"""
const h = {locale: 'en', money: c => '€' + (c / 100).toFixed(2), dateLabel: d => d, monthLabel: d => d};
const off = m.renderPlansSection({mortgage: {on: false, prefill: {found: true, source: 'housing_payment', monthly_payment_cents: 136260, payment_day: 4}}, tax: {on: false}}, h);
assert.match(off, /data-plan-on="mortgage"/); assert.match(off, /data-plan-on="tax"/); assert.match(off, /€1362.60/);
const projection = {inputs: {reference_rate: 'euribor_12m', reference_rate_bp: 225, margin_bp: 60, remaining_months: 240}, rate_bp: 285,
  monthly_payment_cents: 98482, calculated_payment_cents: 98482, payoff_month: '2046-09', total_interest_cents: 5635485, notes: ['rate_checked'],
  extra_advice: {suggest: true, reason: null}, rate_change: {up: {rate_bp: 385, monthly_payment_cents: 107660, payment_change_cents: 9178}, down: null},
  what_if: {extra_cents: 10000, months_saved: 28, interest_saved_cents: 724381, payoff_month: '2044-05'}};
const on = m.renderMortgageCard({on: true, projection}, {extra: 10000, rate: 100}, h);
assert.match(on, /€984.82/); assert.match(on, /28 months sooner/); assert.match(on, /\+€91.78/); assert.match(on, /data-plan-extra/);
const steady = m.renderMortgageCard({on: true, projection: {...projection, extra_advice: {suggest: false, reason: 'steady'}}}, {}, h);
assert.ok(!steady.includes('data-plan-extra')); assert.match(steady, /cushion first/);
const thin = m.renderMortgageCard({on: true, projection: {...projection, extra_advice: {suggest: false, reason: 'buffer_thin'}}}, {}, h);
assert.match(thin, /cushion looks thin/);
const tax = m.renderTaxCard({on: true, set_aside: {monthly_cents: 5000, until: '2027-09-01', instalments: [{status: 'upcoming', date_is_estimate: true}]},
  tax_card: {status: 'income_above_limit'}, omavero_text: 'OmaVero (vero.fi)', dates: [{date: '2027-09-01', kind: 'back_tax'}]}, h);
assert.match(tax, /€50.00/); assert.match(tax, /OmaVero \(vero\.fi\)/); assert.match(tax, /Back tax due/);
for (const html of [off, on, tax]) for (const word of ['scenario', 'deterministic', 'provenance', 'quartile', 'MCC']) assert.ok(!html.includes(word), word);
""")

    def test_me_page_lists_plans(self):
        self.run_node(r"""
const p = await import(""" + json.dumps((WEB / 'money-profile.js').as_uri()) + r""");
const entries = [{id: 'profile:1', key: 'plan_mortgage', value: {principal_cents: 18000000, reference_rate_bp: 225, margin_bp: 60, loan_type: 'annuity', reference_rate: 'euribor_12m', remaining_months: 240}, source: 'you_told_me', active: true},
                 {id: 'profile:2', key: 'plan_tax', value: {on: true}, source: 'from_our_chat', active: true}];
const html = p.renderProfilePage({entries, by_key: {}}, [], 'fi', {money: c => (c / 100) + ' €'});
assert.match(html, /data-profile-section="plans"/); assert.match(html, /Asuntolainasuunnitelma/); assert.match(html, /Verosuunnitelma/);
assert.match(html, /data-profile-delete="profile:1"/); assert.match(html, /data-profile-edit="profile:2"/);
assert.match(p.describeEntry(entries[0], 'en', {money: c => '€' + c / 100}), /€180000/);
""")


if __name__ == '__main__':
    unittest.main()
