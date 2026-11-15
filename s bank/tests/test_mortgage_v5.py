"""V5 lane MG: mortgage plan example, rich result and preview endpoint.

The repayment maths in scoach/mortgage.py is checked against independent float
calculations (standard annuity formula, closed-form equal-principal interest,
payoff-term formula) for the owner's example: EUR 180,000, 2.90 %, 22 years.
"""
import json
import math
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from scoach import money_profile as mp, mortgage, plans
from scoach.agent_tools import ToolContext, dispatch
from scoach.api import Application
from tests.core_helper import demo_connection
from tests.test_plans import DEMO_DB, PLAN, synthetic

WEB = pathlib.Path(__file__).resolve().parents[1] / 'web'
ALEX, TAYLOR = 'CUST00001', 'CUST00296'
P, RATE_BP, MONTHS = 18_000_000, 290, 264  # EUR 180,000 at 2.30 % + 0.60 %, 22 years
R = 0.029 / 12


def float_annuity(principal_cents, annual, months):
    r = annual / 12
    return principal_cents * r / (1 - (1 + r) ** -months)


def months_to_repay(principal_cents, annual, payment_cents):
    """Payments needed to repay principal with a fixed monthly payment (closed form, rounded up)."""
    r = annual / 12
    return math.ceil(-math.log(1 - r * principal_cents / payment_cents) / math.log(1 + r))


class IndependentMathTests(unittest.TestCase):
    def test_annuity_matches_the_closed_form(self):
        expected = float_annuity(P, 0.029, MONTHS)
        self.assertAlmostEqual(expected / 100, 923.09, places=1)  # computed by hand: EUR 923.09
        payment = mortgage.annuity_payment(P, RATE_BP, MONTHS)
        self.assertEqual(payment, math.ceil(expected))
        run = mortgage.simulate(P, RATE_BP, 'annuity', months=MONTHS)
        self.assertEqual(run['months'], MONTHS)
        self.assertEqual(run['rows'][-1]['balance_cents'], 0)
        # Total interest = everything paid minus the loan; a rounded-up payment ends a little early, so allow EUR 5.
        self.assertLess(abs(run['total_interest_cents'] - (expected * MONTHS - P)), 500)
        self.assertEqual(run['total_paid_cents'], P + run['total_interest_cents'])
        # First month: interest is balance x monthly rate.
        self.assertEqual(run['rows'][0]['interest_cents'], round(P * R))

    def test_equal_principal_matches_the_closed_form(self):
        run = mortgage.simulate(P, RATE_BP, 'equal_principal', months=MONTHS)
        instalment = P / MONTHS
        self.assertEqual(run['rows'][0]['payment_cents'], math.ceil(instalment) + round(P * R))
        # Interest on a balance falling by P/n each month: r * P * (n + 1) / 2.
        self.assertLess(abs(run['total_interest_cents'] - R * P * (MONTHS + 1) / 2), 300)
        payments = [row['payment_cents'] for row in run['rows'][:-1]]
        self.assertEqual(payments, sorted(payments, reverse=True))
        annuity = mortgage.simulate(P, RATE_BP, 'annuity', months=MONTHS)
        self.assertLess(run['total_interest_cents'], annuity['total_interest_cents'])

    def test_extra_payment_and_rate_change_match_the_closed_forms(self):
        result = mortgage.projection({**mortgage.EXAMPLE_PLAN}, '2026-09-30', detail=True)
        base_payment = math.ceil(float_annuity(P, 0.029, MONTHS))
        self.assertEqual(result['monthly_payment_cents'], base_payment)
        for option in result['extra_options']:
            months = months_to_repay(P, 0.029, base_payment + option['extra_cents'])
            self.assertLessEqual(abs(option['months_left'] - months), 1, option)
            self.assertEqual(option['months_saved'], MONTHS - option['months_left'])
            self.assertGreater(option['interest_saved_cents'], 0)
        self.assertEqual([o['extra_cents'] for o in result['extra_options']], [5000, 10000, 20000])
        up, down = result['rate_change']['up'], result['rate_change']['down']
        self.assertEqual(up['monthly_payment_cents'], math.ceil(float_annuity(P, 0.039, MONTHS)))
        self.assertEqual(down['monthly_payment_cents'], math.ceil(float_annuity(P, 0.019, MONTHS)))
        self.assertEqual((up['rate_bp'], down['rate_bp']), (390, 190))

    def test_principal_for_payment_is_the_inverse(self):
        principal = mortgage.principal_for_payment(136260, RATE_BP, MONTHS)
        self.assertAlmostEqual(principal, 136260 * (1 - (1 + R) ** -MONTHS) / R, delta=1)
        self.assertLessEqual(abs(mortgage.annuity_payment(principal, RATE_BP, MONTHS) - 136260), 1)
        self.assertEqual(mortgage.principal_for_payment(0, RATE_BP, MONTHS), 0)
        self.assertEqual(mortgage.principal_for_payment(1000, 0, 12), 12000)


class RichResultTests(unittest.TestCase):
    def setUp(self):
        self.result = mortgage.projection(dict(mortgage.EXAMPLE_PLAN), '2026-09-30', detail=True)

    def test_headline_numbers(self):
        r = self.result
        self.assertEqual((r['first_payment_month'], r['payoff_month'], r['months_left']), ('2026-10', '2048-09', 264))
        self.assertEqual(r['years_left'], {'years': 22, 'months': 0})
        self.assertEqual(r['total_paid_cents'], P + r['total_interest_cents'])

    def test_balance_curve_and_split(self):
        curve = self.result['balance_curve']
        self.assertEqual(curve[0], {'n': 0, 'month': '2026-09', 'balance_cents': P})
        self.assertEqual(curve[-1]['balance_cents'], 0)
        self.assertEqual(len(curve), 23)  # start + 22 year ends
        balances = [p['balance_cents'] for p in curve]
        self.assertEqual(balances, sorted(balances, reverse=True))
        split = self.result['split']
        first, last = split['first_year'], split['last_year']
        self.assertEqual((first['payments'], last['payments']), (12, 12))
        self.assertGreater(first['interest_cents'], 10 * last['interest_cents'])
        self.assertEqual(first['interest_cents'] + first['principal_cents'], first['paid_cents'])
        self.assertEqual(first['principal_cents'], P - curve[1]['balance_cents'])
        for option in self.result['extra_options']:
            self.assertEqual(option['balance_curve'][-1]['balance_cents'], 0)
            self.assertEqual(option['balance_curve'][-1]['month'], option['payoff_month'])

    def test_detail_is_opt_in_and_steady_has_no_extra_options(self):
        plain = mortgage.projection(dict(mortgage.EXAMPLE_PLAN), '2026-09-30')
        self.assertNotIn('balance_curve', plain)
        steady = mortgage.projection(dict(mortgage.EXAMPLE_PLAN), '2026-09-30', steady=True, detail=True)
        self.assertEqual(steady['extra_options'], [])
        self.assertEqual(steady['extra_advice'], {'suggest': False, 'reason': 'steady'})

    def test_short_loan_has_no_last_year_split(self):
        short = mortgage.projection({**mortgage.EXAMPLE_PLAN, 'principal_cents': 500_000, 'remaining_months': 10}, '2026-09-30', detail=True)
        self.assertIsNone(short['split']['last_year'])
        self.assertEqual(short['years_left'], {'years': 0, 'months': 10})


class ExampleTests(unittest.TestCase):
    def test_example_plan(self):
        self.assertEqual(mortgage.example_plan(None), (mortgage.EXAMPLE_PLAN, 'generic'))
        plan, basis = mortgage.example_plan({'found': True, 'monthly_payment_cents': 136260, 'payment_day': 4})
        self.assertEqual(basis, 'detected_payment')
        self.assertEqual(plan['principal_cents'] % 100_000, 0)
        self.assertEqual(plan['payment_day'], 4)
        payment = mortgage.annuity_payment(plan['principal_cents'], 290, 264)
        self.assertLessEqual(136260 - payment, 600)  # within about EUR 6 of what they pay now
        tiny, basis = mortgage.example_plan({'found': True, 'monthly_payment_cents': 5000})
        self.assertEqual(basis, 'generic')  # too small to be a home loan: the generic example

    def test_rent_alone_does_not_size_the_example_but_a_saved_mortgage_does(self):
        conn = synthetic()
        preview = plans.mortgage_preview(conn, 'CUST09999', '2026-09-30')
        self.assertEqual((preview['example'], preview['basis']), (True, 'generic'))
        self.assertEqual(preview['projection']['inputs']['principal_cents'], P)
        mp.save_entry(conn, 'CUST09999', 'debts', {'type': 'mortgage', 'monthly_payment_cents': 88000}, 'you_told_me')
        self.assertEqual(plans.mortgage_preview(conn, 'CUST09999', '2026-09-30')['basis'], 'detected_payment')

    def test_preview_never_saves_and_follows_steady_mode(self):
        conn = synthetic(balance=400000)
        before = len(mp.get_profile(conn, 'CUST09999', '2026-09-30')['entries'])
        own = plans.mortgage_preview(conn, 'CUST09999', '2026-09-30', dict(PLAN))
        self.assertEqual((own['example'], own['basis'], own['saved']), (False, 'your_numbers', False))
        self.assertEqual(len(mp.get_profile(conn, 'CUST09999', '2026-09-30')['entries']), before)
        self.assertEqual(len(own['projection']['extra_options']), 3)
        mp.save_entry(conn, 'CUST09999', 'life_event', {'type': 'job_loss', 'since': '2026-09'}, 'you_told_me')
        steady = plans.mortgage_preview(conn, 'CUST09999', '2026-09-30')
        self.assertTrue(steady['steady'])
        self.assertEqual(steady['projection']['extra_options'], [])
        with self.assertRaises(ValueError):
            plans.mortgage_preview(conn, 'CUST09999', '2026-09-30', {**PLAN, 'loan_type': 'balloon'})


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

    def get(self, target):
        return self.app.handle('GET', target, None)

    def test_example_for_alex_and_taylor(self):
        status, body = self.get('/api/plans/mortgage/preview?customer_id=' + ALEX)
        self.assertEqual(status, 200, body)
        data = body['data']
        self.assertEqual((data['example'], data['basis']), (True, 'generic'))
        p = data['projection']
        self.assertEqual((p['monthly_payment_cents'], p['payoff_month'], p['rate_bp']), (92309, '2048-09', 290))
        self.assertEqual(len(p['extra_options']), 3)
        status, body = self.get('/api/plans/mortgage/preview?customer_id=' + TAYLOR)
        self.assertEqual(body['data']['basis'], 'detected_payment')  # past home-loan application + housing payment
        self.assertLessEqual(abs(body['data']['projection']['monthly_payment_cents'] - body['data']['prefill']['monthly_payment_cents']), 600)

    def test_own_numbers_and_validation(self):
        query = '/api/plans/mortgage/preview?customer_id=%s&principal_cents=18000000&loan_type=equal_principal&reference_rate_bp=230&margin_bp=60&remaining_months=264' % ALEX
        status, body = self.get(query)
        self.assertEqual(status, 200, body)
        self.assertEqual((body['data']['example'], body['data']['basis']), (False, 'your_numbers'))
        self.assertIn('payment_falls', body['data']['projection']['notes'])
        status, body = self.get(query + '&extra_cents=10000&rate_delta_bp=100')
        self.assertEqual(body['data']['projection']['what_if']['extra_cents'], 10000)
        for bad in ('&margin_bp=60', '&principal_cents=0', '&principal_cents=100000&loan_type=balloon&remaining_months=12',
                    '&principal_cents=100000', '&principal_cents=1e5&remaining_months=12', '&bogus=1'):
            self.assertEqual(self.get('/api/plans/mortgage/preview?customer_id=' + ALEX + bad)[0], 400, bad)
        status, body = self.app.handle('GET', '/api/profile?customer_id=' + ALEX, None)
        self.assertNotIn('plan_mortgage', [e['key'] for e in body['data']['profile']['entries']])

    def test_saved_plan_projection_is_rich_but_agent_tool_is_unchanged(self):
        self.app.handle('POST', '/api/plans/mortgage', {'customer_id': TAYLOR, 'plan': PLAN, 'confirmed': True})
        status, body = self.get('/api/plans/mortgage/projection?customer_id=' + TAYLOR)
        self.assertEqual(status, 200)
        projection = body['data']['projection']
        for key in ('balance_curve', 'split', 'years_left', 'extra_options'):
            self.assertIn(key, projection)
        conn = demo_connection()
        try:
            plans.save_plan(conn, TAYLOR, 'mortgage', PLAN)
            result = dispatch(conn, TAYLOR, ToolContext(conn, TAYLOR, '2026-09'), 'mortgage_plan', {})
            self.assertNotIn('balance_curve', result['projection'])
            self.assertNotIn('extra_options', result['projection'])
        finally:
            conn.close()


@unittest.skipUnless(shutil.which('node'), 'Node is required for UI checks')
class MortgageUiTests(unittest.TestCase):
    def run_node(self, body):
        script = ('import assert from "node:assert/strict";\n'
                  'const m = await import(' + json.dumps((WEB / 'plans-mortgage.js').as_uri()) + ');\n'
                  'const plans = await import(' + json.dumps((WEB / 'plans.js').as_uri()) + ');\n' + body)
        result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def projection(self):
        conn = synthetic(balance=400000)
        return plans.mortgage_preview(conn, 'CUST09999', '2026-09-30')

    def test_copy_in_three_languages_and_formats(self):
        self.run_node(r"""
for (const key of m.MORTGAGE_COPY_KEYS) for (const l of ['en','fi','sv']) { const v = m.mortgageText(l, key); assert.ok(v && v !== key, key + ' ' + l); }
for (const key of m.MORTGAGE_COPY_KEYS.filter(k => k.startsWith('v5.mg.'))) { const row = m.MORTGAGE_COPY[key]; assert.equal(row.length, 3, key); assert.notEqual(row[1], row[0], key + ' fi untranslated'); }
assert.equal(m.formatTerm(264, 'en'), '22 years'); assert.equal(m.formatTerm(256, 'fi'), '21 v 4 kk'); assert.equal(m.formatTerm(18, 'sv'), '1 år 6 mån');
assert.equal(m.formatTerm(12, 'en'), '1 year'); assert.equal(m.formatTerm(7, 'en'), '7 months');
assert.equal(m.wholeEuros(24369448, 'en'), '€243,694'); assert.equal(m.wholeEuros(24369448, 'fi').replace(/\s/g, ' '), '243 694 €');
assert.equal(m.compactEuros(18000000, 'en'), '€180k');
// plans.js keeps the old names working (other modules and older tests import them from there).
assert.equal(plans.formatRate(285, 'fi'), '2,85 %'); assert.equal(plans.annuityPayment(18000000, 290, 264), 92309);
assert.equal(plans.planText('en', 'm.left'), 'Loan left'); assert.equal(typeof plans.renderMortgageCard, 'function');
""")

    def test_off_card_example_and_rich_result(self):
        data = self.projection()
        self.run_node(r"""
const data = """ + json.dumps(data) + r""";
const h = {locale: 'en', money: c => '€' + (c / 100).toFixed(2), dateLabel: d => d, monthLabel: d => d};
const off = m.renderMortgageCard({on: false, prefill: data.prefill}, {}, h);
assert.match(off, /data-plan-on="mortgage"/); assert.match(off, /data-plan-example="mortgage"/); assert.match(off, /See an example/);
const loading = m.renderMortgageCard({on: false}, {example: {loading: true}}, h);
assert.match(loading, /Calculating the example/);
const failed = m.renderMortgageCard({on: false}, {example: {error: true}}, h);
assert.match(failed, /could not be calculated/); assert.match(failed, /data-plan-example-close/);
const ex = m.renderMortgageCard({on: false}, {example: {data}, extra: 10000}, h);
for (const text of ['Example — not your numbers', 'Use my own numbers', 'data-plan-own="mortgage"', '€923.09', '2048-09', '22 years',
  '€63,694', '€243,694', 'Loan left over time', 'data-mg-chart', 'Where your payments go', 'First year', 'Last year',
  'If the rate rises by 1 percentage point', '€1016.69', '+€93.60', '€834.75', 'Year by year', 'With +€100 a month · paid off 2045'])
  assert.ok(ex.includes(text), text);
assert.equal((ex.match(/data-plan-extra=/g) || []).length, 3);
assert.match(ex, /data-plan-extra="10000" aria-pressed="true"/);
assert.match(ex, /mg-line-extra/);
assert.match(ex, /You would pay €923.09 a month for 22 years, until 2048-09/);
assert.ok(!ex.includes('held back on each payday'), 'the example is not held back');
const fi = m.renderMortgageCard({on: false}, {example: {data}}, {...h, locale: 'fi'});
assert.match(fi, /Esimerkki – ei sinun lukujasi/); assert.match(fi, /Käytä omia lukujani/); assert.ok(!fi.includes('mg-line-extra'));
for (const html of [off, ex, fi]) for (const word of ['scenario', 'deterministic', 'provenance', 'quartile', 'MCC', 'undefined', 'NaN']) assert.ok(!html.includes(word), word);
// Saved plan: same rich result plus the plan's own details; steady mode has no extra-payment options.
const saved = m.renderMortgageCard({on: true, projection: data.projection}, {}, h);
assert.match(saved, /held back on each payday/); assert.match(saved, /data-plan-edit="mortgage"/); assert.match(saved, /data-mg-chart/);
const steady = m.renderMortgageCard({on: true, projection: {...data.projection, extra_options: [], extra_advice: {suggest: false, reason: 'steady'}}}, {}, h);
assert.ok(!steady.includes('data-plan-extra')); assert.match(steady, /cushion first/);
const thin = m.renderMortgageCard({on: true, projection: {...data.projection, extra_advice: {suggest: false, reason: 'buffer_thin'}}}, {}, h);
assert.match(thin, /cushion looks thin/); assert.match(thin, /data-plan-extra/);
// The plans section renders the example from its ui state.
const section = plans.renderPlansSection({mortgage: {on: false}, tax: {on: false}, ui: {example: {data}}}, h);
assert.match(section, /plan-card--example/); assert.match(section, /data-plan-on="tax"/);
""")

    def test_chart_points_and_form_preview(self):
        data = self.projection()
        self.run_node(r"""
const p = """ + json.dumps(data['projection']) + r""";
const h = {locale: 'en', money: c => '€' + (c / 100).toFixed(2), monthLabel: d => d};
const html = m.balanceChartSVG(p.balance_curve, p.extra_options[2].balance_curve, h, {extraCents: 20000});
const points = JSON.parse(html.match(/data-points="([^"]+)"/)[1].replace(/&quot;/g, '"'));
assert.equal(points.length, p.balance_curve.length);
assert.equal(points[0].b, 18000000); assert.equal(points.at(-1).b, 0);
assert.ok(points.every(q => q.e === null || q.e <= q.b), 'extra line never above the plan');
assert.equal(points.at(-1).e, 0);
assert.match(html, /role="img"/); assert.match(html, /aria-label="Loan left from 2026 to 2048/);
assert.equal(m.balanceChartSVG([], null, h), '');
const text = m.mortgageFormPreview({principal_cents: 18000000, loan_type: 'annuity', reference_rate: 'euribor_12m', reference_rate_pct: 2.3, margin_pct: 0.6, remaining_years: 22}, 'en', {money: h.money, monthLabel: d => d, referenceDate: '2026-09-30'});
assert.equal(text, 'About €923.09 a month, paid off in 2048-09.');
""")


if __name__ == '__main__':
    unittest.main()
