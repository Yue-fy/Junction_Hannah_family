"""V5 fix wave, lane NB (numbers and terms backend): one regression test per QA report case.

Every test works on a copy of the demo database (an in-memory copy, or a temp file for the
API), never on var/ itself. Cases (docs/critique/qa/qa-flows.md, qa-lang.md):
  1. Taylor: a mortgage plan double-counted the detected housing payment; payment day after payday.
  2. Mortgage card mixed the typed payment with the calculated one (totals, split, rate what-ifs).
  3. Kai (steady) / Robin: the shortfall blamed bills when the cushion caused it.
  4. Alex: the saved surprise buffer ("Set aside €400 monthly") was not held back.
  5. An empty tax plan claimed "your tax withholding looks enough".
  6. English "Rent" in the Finnish / Swedish payday plan and coach answer.
  7. One category label table (labels.py) for forecast, catalogue and spender.
  8. Goal card: €500 a month next to "about €196 left each month" with no warning.
  9. Salary figure: Me and the tax form showed two different "after tax" salaries.
 10. The plan summary shows the daily-life sum the daily number is made of.
"""
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from urllib.parse import urlencode

from scoach import catalogue, goals, labels, money_profile as mp, mortgage, plans
from scoach import forecast
from scoach.api import Application, planning_profile
from scoach.forecast import shortfall_breakdown, spending_plan
from tests.core_helper import demo_connection

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
DEMO_DB = ROOT / 'var/scoach.sqlite3'
ALEX, ROBIN, TAYLOR, KAI = 'CUST00001', 'CUST00676', 'CUST00296', 'CUST01331'
# Taylor's own numbers from qa-flows.md P1-1: €200k, 2.3 % + 0.6 %, 20 years, payment field empty, payment day 20.
TAYLOR_PLAN = {'principal_cents': 20_000_000, 'loan_type': 'annuity', 'reference_rate': 'euribor_12m',
               'reference_rate_bp': 230, 'margin_bp': 60, 'remaining_months': 240, 'payment_day': 20}
TAYLOR_HOUSING_CENTS = 136260


def plan_for(conn, customer_id):
    end = conn.execute('SELECT max(date) FROM transactions WHERE customer_id=?', (customer_id,)).fetchone()[0]
    return spending_plan(conn, customer_id, as_of=end, profile=planning_profile(conn, customer_id, end))


def node(script):
    result = subprocess.run(['node', '--input-type=module', '-e', 'import assert from "node:assert/strict";\n' + script],
                            capture_output=True, text=True)
    return result


class TaylorMortgageIsHeldBackOnce(unittest.TestCase):
    """qa-flows P1-1: Held back went from €1,363 to €2,462 (Rent 4 Oct + Mortgage payment)."""

    def setUp(self):
        self.conn = demo_connection()
        self.before = plan_for(self.conn, TAYLOR)

    def tearDown(self):
        self.conn.close()

    def test_detected_housing_payment_is_the_rent_line_before_a_plan(self):
        rent = [h for h in self.before['held_back'] if h['key'] == 'rent']
        self.assertEqual([(h['amount_cents'], h['date']) for h in rent], [(TAYLOR_HOUSING_CENTS, '2026-10-04')])

    def test_payment_day_after_payday_is_not_held_back_and_never_twice(self):
        plans.save_plan(self.conn, TAYLOR, 'mortgage', TAYLOR_PLAN)
        after = plan_for(self.conn, TAYLOR)
        self.assertEqual(after['next_payday'], '2026-10-15')
        keys = [h['key'] for h in after['held_back']]
        self.assertNotIn('rent', keys)        # the housing payment IS the mortgage
        self.assertNotIn('mortgage', keys)    # due 20 Oct, after the 15 Oct payday
        self.assertEqual(after['held_back_cents'], self.before['held_back_cents'] - TAYLOR_HOUSING_CENTS)
        self.assertEqual(after['upcoming_after_payday'][0]['date'], '2026-10-20')
        self.assertTrue(after['skipped_declared_items'][0]['replaced_by_plan'])
        self.assertIn('Your next mortgage payment (the 20th) comes after payday, so it is not held back from this pay.', after['assumptions'])

    def test_payment_equal_to_the_detected_one_is_labelled_mortgage_payment(self):
        plans.save_plan(self.conn, TAYLOR, 'mortgage', {**TAYLOR_PLAN, 'monthly_payment_cents': TAYLOR_HOUSING_CENTS, 'payment_day': 4})
        after = plan_for(self.conn, TAYLOR)
        bills = [(h['key'], h['label'], h['labels']['fi'], h['amount_cents'], h['date']) for h in after['held_back'] if h['kind'] in ('bill', 'loan')]
        self.assertEqual(bills, [('mortgage', 'Mortgage payment', 'Asuntolainan erä', TAYLOR_HOUSING_CENTS, '2026-10-04')])
        self.assertEqual(after['held_back_cents'], self.before['held_back_cents'])

    def test_no_payment_day_uses_the_day_it_is_paid(self):
        plan = {k: v for k, v in TAYLOR_PLAN.items() if k != 'payment_day'}
        plans.save_plan(self.conn, TAYLOR, 'mortgage', plan)
        calculated = mortgage.projection(plan, '2026-09-27')['monthly_payment_cents']
        after = plan_for(self.conn, TAYLOR)
        loans = [(h['key'], h['amount_cents'], h['date']) for h in after['held_back'] if h['kind'] in ('bill', 'loan')]
        self.assertEqual(loans, [('mortgage', calculated, '2026-10-04')])

    def test_through_the_api_on_a_database_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / 'db.sqlite3'
            shutil.copy(DEMO_DB, db)
            app = Application(db)
            status, body = app.handle('POST', '/api/plans/mortgage', {'customer_id': TAYLOR, 'plan': TAYLOR_PLAN, 'confirmed': True})
            self.assertEqual(status, 200, body)
            status, body = app.handle('GET', '/api/safe-to-spend?' + urlencode({'customer_id': TAYLOR, 'as_of': '2026-09-27',
                                                                               'horizon': 'until_payday', 'reserve_floor_cents': 50000}))
            self.assertEqual(status, 200, body)
            held = body['data']['held_back']
            self.assertFalse([h for h in held if h['key'] in ('rent', 'mortgage')])


class MortgageCardUsesOnePayment(unittest.TestCase):
    """qa-flows P1-2: €1,362.60 shown, but totals / first year / rate what-ifs used the calculated €1,099."""

    def test_typed_payment_is_the_base_of_every_number(self):
        p = mortgage.projection({**TAYLOR_PLAN, 'monthly_payment_cents': TAYLOR_HOUSING_CENTS}, '2026-09-27', detail=True)
        self.assertEqual(p['monthly_payment_cents'], TAYLOR_HOUSING_CENTS)
        self.assertEqual(p['term_basis'], 'payment')
        self.assertEqual(p['split']['first_year']['paid_cents'], 12 * TAYLOR_HOUSING_CENTS)
        self.assertNotEqual(p['total_paid_cents'], 240 * p['calculated_payment_cents'])
        self.assertLess(p['months_left'], 240)    # paying more than the 20-year payment ends the loan sooner
        self.assertIn('payment_differs', p['notes'])
        up, down = p['rate_change']['up'], p['rate_change']['down']
        self.assertGreater(up['monthly_payment_cents'], TAYLOR_HOUSING_CENTS)
        self.assertLess(down['monthly_payment_cents'], TAYLOR_HOUSING_CENTS)
        self.assertEqual(up['payment_change_cents'], up['monthly_payment_cents'] - TAYLOR_HOUSING_CENTS)
        self.assertEqual(p['payoff_month'], p['balance_curve'][-1]['month'])

    def test_kai_rate_rise_is_never_lower_than_the_payment_shown(self):
        # kai-mort-ratechange.png: "+1 point" showed €901.09 next to the €975.26 shown.
        plan = {'principal_cents': 15_000_000, 'loan_type': 'annuity', 'reference_rate': 'euribor_12m',
                'reference_rate_bp': 230, 'margin_bp': 60, 'remaining_months': 300, 'monthly_payment_cents': 97526}
        p = mortgage.projection(plan, '2026-09-30')
        self.assertEqual(p['monthly_payment_cents'], 97526)
        self.assertGreater(p['rate_change']['up']['monthly_payment_cents'], 97526)
        self.assertGreater(p['rate_change']['up']['payment_change_cents'], 0)
        self.assertLess(p['rate_change']['down']['payment_change_cents'], 0)

    def test_empty_payment_still_uses_the_years_left(self):
        p = mortgage.projection(TAYLOR_PLAN, '2026-09-27', detail=True)
        self.assertEqual((p['term_basis'], p['months_left']), ('years', 240))
        self.assertEqual(p['monthly_payment_cents'], p['calculated_payment_cents'])


class ShortfallCauseIsNamed(unittest.TestCase):
    """qa-flows P1-3: Kai (steady) was told bills were the problem; the steady cushion was."""

    def setUp(self):
        self.conn = demo_connection()

    def tearDown(self):
        self.conn.close()

    def test_kai_steady_mode_gap_comes_from_the_cushion(self):
        mp.save_entry(self.conn, KAI, 'life_event', {'type': 'job_loss', 'since': '2026-09-01'}, 'you_told_me')
        p = plan_for(self.conn, KAI)
        b = p['shortfall_breakdown']
        self.assertGreater(p['shortfall_cents'], 0)
        self.assertEqual((b['cause'], b['cushion_kind']), ('cushion', 'steady_reserve'))
        self.assertEqual(b['bills_over_balance_cents'], 0)
        self.assertEqual(b['below_zero_cents'], 0)
        self.assertEqual(b['cushion_short_cents'], p['shortfall_cents'])
        self.assertEqual(b['cushion_kept_cents'] + b['cushion_short_cents'], b['cushion_cents'])
        self.assertNotIn('Bills before payday', b['texts']['en'])
        self.assertIn('Steady mode keeps a month of must-pays (€1,639)', b['texts']['en'])
        self.assertIn('Rauhallisessa tahdissa', b['texts']['fi'])
        self.assertIn(b['texts']['en'], p['summary']['en'])
        self.assertNotIn('.', b['texts']['en'].split('€1,639')[0][-3:])  # whole euros, no cents

    def test_robin_rent_is_more_than_the_balance(self):
        p = plan_for(self.conn, ROBIN)
        b = p['shortfall_breakdown']
        self.assertEqual(b['cause'], 'bills')
        self.assertEqual(b['bills_over_balance_cents'], 85252 - 31214)
        self.assertEqual(b['cushion_short_cents'], 50000)
        self.assertEqual(b['texts']['en'], 'Bills before payday (€853) are €540 more than your balance (€312). '
                                           'Your safety cushion (€500) cannot be kept this time.')
        self.assertEqual(p['summary']['en'][0], 'Nothing is free to spend until payday on 15 Oct 2026 (15 days).')

    def test_coach_answer_uses_the_same_cause(self):
        mp.save_entry(self.conn, KAI, 'life_event', {'type': 'job_loss', 'since': '2026-09-01'}, 'you_told_me')
        card = catalogue.answer(self.conn, KAI, '2026-09', 'room.week', locale='en')
        text = ' '.join(card['lines'])
        self.assertIn('Steady mode keeps a month of must-pays', text)
        self.assertNotIn('Bills and the reserve', text)

    def test_breakdown_order_is_bills_everyday_saving_buffer_cushion(self):
        held = [{'kind': 'bill', 'amount_cents': 300}, {'kind': 'goal', 'amount_cents': 100},
                {'kind': 'buffer', 'amount_cents': 50}, {'kind': 'reserve', 'amount_cents': 500}]
        self.assertEqual(shortfall_breakdown(1000, held, 200)['cause'], 'cushion')
        self.assertEqual(shortfall_breakdown(620, held, 200)['cause'], 'buffer')
        self.assertEqual(shortfall_breakdown(550, held, 200)['cause'], 'saving')
        self.assertEqual(shortfall_breakdown(400, held, 200)['cause'], 'everyday')
        self.assertEqual(shortfall_breakdown(200, held, 200)['cause'], 'bills')
        self.assertIsNone(shortfall_breakdown(2000, held, 200)['cause'])
        self.assertIsNone(shortfall_breakdown(2000, held, 200)['texts'])


class SavedSurpriseBufferIsHeldBack(unittest.TestCase):
    """qa-flows P1-4: "Set aside €400 monthly" saved, but Held back still showed €204.58 from history."""

    def setUp(self):
        self.conn = demo_connection()
        self.before = plan_for(self.conn, ALEX)

    def tearDown(self):
        self.conn.close()

    def save_buffer(self):
        # What Home's "Set aside €400 monthly" confirm card saves (web/home-v4.js saveBuffer).
        return goals.create_goal(self.conn, ALEX, 'Surprise buffer', 120_000, '2026-12-31', reserve_floor_cents=50000, template='buffer')

    def test_plan_amount_replaces_the_history_estimate(self):
        history = next(h for h in self.before['held_back'] if h['kind'] == 'buffer')
        self.assertEqual((history['key'], history['amount_cents']), ('buffer', 20458))
        goal = self.save_buffer()
        self.assertEqual(goal['required_monthly_cents'], 40000)
        after = plan_for(self.conn, ALEX)
        buffer = [h for h in after['held_back'] if h['kind'] == 'buffer']
        self.assertEqual([(h['key'], h['amount_cents'], h['source'], h['goal_id']) for h in buffer], [('buffer_goal', 40000, 'goal', goal['id'])])
        self.assertEqual(after['buffer_cents'], 40000)
        self.assertEqual(after['free_cents'], self.before['free_cents'] - (40000 - 20458))
        self.assertEqual(after['extra_cents'], self.before['extra_cents'] - (40000 - 20458))
        self.assertEqual(buffer[0]['labels']['sv'], 'Buffert för oväntat (din plan)')

    def test_steady_mode_and_reached_goals_are_not_held(self):
        goal = self.save_buffer()
        goals.update_goal(self.conn, ALEX, goal['id'], {'current_saved_cents': 120_000})
        self.assertEqual(plan_for(self.conn, ALEX)['buffer_cents'], 20458)
        goals.update_goal(self.conn, ALEX, goal['id'], {'current_saved_cents': 0})
        mp.save_entry(self.conn, ALEX, 'life_event', {'type': 'job_loss', 'since': '2026-09-01'}, 'you_told_me')
        self.assertNotIn('buffer_goal', [h['key'] for h in plan_for(self.conn, ALEX)['held_back']])


class EmptyTaxPlanMakesNoClaim(unittest.TestCase):
    """qa-flows P1-6: "Turn on my tax plan" with every field empty said withholding looks enough."""

    def setUp(self):
        self.conn = demo_connection()

    def tearDown(self):
        self.conn.close()

    def test_needs_inputs_until_something_is_entered(self):
        plans.save_plan(self.conn, ALEX, 'tax', {'on': True})
        card = plans.tax_plan(self.conn, ALEX)
        self.assertEqual((card['status'], card['needs_inputs']), ('needs_inputs', True))
        self.assertIn('tax card', card['needs_inputs_text']['en'])
        self.assertTrue(any('do not say the withholding looks enough' in task for task in card['tasks']))
        mp.save_entry(self.conn, ALEX, 'tax', {'tax_year': 2026, 'base_rate_bp': 2000, 'gross_monthly_cents': 300_000}, 'you_told_me')
        card = plans.tax_plan(self.conn, ALEX)
        self.assertFalse(card['needs_inputs'])
        self.assertNotEqual(card['status'], 'needs_inputs')

    def test_card_asks_for_numbers_instead_of_celebrating(self):
        script = ('const m = await import(%s);\n' % json.dumps((WEB / 'plans-tax.js').as_uri())
                  + 'const h = {locale: "fi", money: c => String(c), dateLabel: d => d};\n'
                  + 'const html = m.renderTaxCard({on: true, status: "needs_inputs", needs_inputs: true, needs_inputs_text: %s,'
                    ' set_aside: {monthly_cents: 0, instalments: []}, tax_card: {status: "missing"}, dates: []}, h);\n'
                    % json.dumps(plans.NEEDS_INPUTS_TEXT)
                  + 'assert.ok(html.includes("Lisää verokorttisi"), html);\n'
                  + 'assert.ok(!html.includes("riittävältä"), html);\n'
                  + 'const ok = m.renderTaxCard({on: true, set_aside: {monthly_cents: 0}, tax_card: {status: "looks_ok"}, dates: []}, h);\n'
                  + 'assert.ok(ok.includes("tax-nothing"));\n')
        result = node(script)
        self.assertEqual(result.returncode, 0, result.stderr)


class HeldBackLabelsAreLocalized(unittest.TestCase):
    """qa-lang P1-1: "Rent 5.10." in the Finnish "Miksi tämä summa?" and the coach answer."""

    def setUp(self):
        self.conn = demo_connection()

    def tearDown(self):
        self.conn.close()

    def test_plan_items_carry_three_languages(self):
        p = plan_for(self.conn, ALEX)
        rent = next(h for h in p['held_back'] if h['key'] == 'rent')
        self.assertEqual(rent['labels'], {'en': 'Rent', 'fi': 'Vuokra', 'sv': 'Hyra'})
        reserve = next(h for h in p['held_back'] if h['kind'] == 'reserve')
        self.assertEqual(reserve['labels'], {'en': 'Safety cushion', 'fi': 'Turvatyyny', 'sv': 'Säkerhetsmarginal'})
        buffer = next(h for h in p['held_back'] if h['kind'] == 'buffer')
        self.assertEqual(buffer['labels'], {'en': 'Surprise buffer', 'fi': 'Yllätyspuskuri', 'sv': 'Buffert för oväntat'})

    def test_coach_answer_in_finnish_and_swedish(self):
        fi = ' '.join(catalogue.answer(self.conn, ALEX, '2026-09', 'room.week', locale='fi')['lines'])
        sv = ' '.join(catalogue.answer(self.conn, ALEX, '2026-09', 'room.week', locale='sv')['lines'])
        self.assertIn('(Vuokra 5.10.)', fi)
        self.assertIn('Hyra', sv)
        for text in (fi, sv):
            self.assertNotIn('Rent', text)
        self.assertIn('turvatyyny 500,00 €', fi)    # not "puskuri" for the cushion
        self.assertIn('yllätyspuskuri 204,58 €', fi)

    def test_home_keeps_the_server_labels(self):
        script = ('const m = await import(%s);\n' % json.dumps((WEB / 'home-v4.js').as_uri())
                  + 'const p = m.normalizePlan({balance_cents: 100, next_payday: "2026-10-15", days_to_payday: 15, free_cents: 0, '
                    'held_back: [{kind: "bill", key: "rent", label: "Rent", labels: {en: "Rent", fi: "Vuokra", sv: "Hyra"}, amount_cents: 500, date: "2026-10-05"}]});\n'
                  + 'assert.equal(p.items[0].labels.fi, "Vuokra");\n')
        result = node(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('item.labels?.[locale()]', (WEB / 'home-v4.js').read_text(encoding='utf-8'))


class OneCategoryLabelTable(unittest.TestCase):
    """qa-lang P1-4: Liikenne vs Liikkuminen, Restaurang vs Restauranger in different modules."""

    def test_forecast_catalogue_and_labels_agree(self):
        for name, names in labels.CATEGORY_LABELS.items():
            if name in forecast.HELD_CATEGORY_KEYS:
                continue
            self.assertEqual(forecast._category_labels(name), dict(zip(labels.LOCALES, names)), name)
            if name in catalogue.CATEGORY_LABELS:
                self.assertEqual(catalogue.CATEGORY_LABELS[name], dict(zip(labels.LOCALES, names)), name)
        self.assertEqual(labels.category_label('Restaurants', 'sv'), 'Restauranger')
        self.assertEqual(labels.category_label('Transportation', 'fi'), 'Liikenne')
        self.assertFalse(hasattr(forecast, 'CATEGORY_LABELS'))

    def test_protected_categories_note_uses_the_category_name(self):
        conn = demo_connection()
        p = spending_plan(conn, ALEX, profile={'protected_categories': ['Housing', 'Transportation']})
        self.assertIn('Suojaamasi luokat lasketaan arjen menoihin: Asuminen, Liikenne.', p['assumption_texts']['fi'])
        conn.close()


class GoalWarnsWhenItDoesNotFit(unittest.TestCase):
    """qa-flows P2-17 / qa-small 8: "€500 a month" next to "about €195.51 left each month", no warning."""

    def setUp(self):
        self.conn = demo_connection()
        self.italy = goals.create_goal(self.conn, ALEX, 'A summer in Italy', 300_000, '2027-03-31')

    def tearDown(self):
        self.conn.close()

    def test_over_what_is_usually_left(self):
        fit = self.italy['fit']
        self.assertEqual((fit['status'], fit['monthly_need_cents'], fit['usually_left_cents']), ('over', 50000, 19551))
        self.assertEqual(fit['gap_cents'], 50000 - 19551)
        self.assertTrue(fit['texts']['en'].startswith('€500 a month is more than the about €196 you usually have left each month.'))
        self.assertIn('500 € kuukaudessa', fit['texts']['fi'])
        self.assertIn('2 914 €', fit['texts']['fi'])        # the "move money now" route
        self.assertEqual(fit['suggested_monthly_cents'], 19551)
        self.assertEqual(fit['suggested_target_date'], '2028-01-31')

    def test_other_goals_count_too(self):
        goals.create_goal(self.conn, ALEX, 'Surprise buffer', 120_000, '2026-12-31', template='buffer', reserve_floor_cents=50000)
        fit = goals.goal_plan(self.conn, ALEX, self.italy['id'])['fit']
        self.assertEqual(fit['other_goals_monthly_cents'], 40000)
        self.assertEqual(fit['total_monthly_cents'], 90000)
        self.assertIn('Your other goals need €400 a month too.', fit['texts']['en'])

    def test_a_goal_that_fits_has_no_warning(self):
        small = goals.create_goal(self.conn, ALEX, 'Shoes', 30_000, '2027-09-30')
        self.assertEqual(small['fit']['status'], 'shared_over')   # €30 fits alone, not with Italy's €500
        goals.delete_goal(self.conn, ALEX, self.italy['id'])
        fit = goals.goal_plan(self.conn, ALEX, small['id'])['fit']
        self.assertEqual((fit['status'], fit['texts']), ('fits', None))

    def test_goal_card_shows_the_warning(self):
        # The goal card moved to goals-v5.js (lane GL): it shows the server's fit text as an amber warning.
        source = (WEB / 'goals-v5.js').read_text(encoding='utf-8')
        self.assertIn('texts?.[lang(locale)]', source)
        self.assertIn('.goal-fit--warn', (WEB / 'goals-v5.css').read_text(encoding='utf-8'))


class SalaryIsOneFigure(unittest.TestCase):
    """qa-flows P2-15 / qa-desktop: "about €2,365 after tax" on Me vs "about €2,325.60" in the tax form."""

    def test_tax_form_hint_equals_me(self):
        conn = demo_connection()
        me = next(s for s in mp.profile_suggestions(conn, ALEX) if s['kind'] == 'salary')
        prefill = plans.tax_plan(conn, ALEX)['prefill']
        self.assertEqual(prefill['net_salary_cents'], me['value']['typical_monthly_cents'])
        self.assertEqual(prefill['net_salary_basis'], 'median_month_last_complete_months')
        self.assertIn('a typical month over the last 6 months', me['question'])
        conn.close()


class DailyNumberAddsUp(unittest.TestCase):
    """V5 fix decision: everyday basics + free to spend = daily life -> per day; qa-lang P1-5, qa-flows P3-32."""

    def test_summary_shows_the_sum(self):
        conn = demo_connection()
        p = plan_for(conn, ALEX)
        self.assertEqual(p['per_day_cents'], p['daily_life_cents'] // p['days_to_payday'])
        self.assertEqual(p['summary']['en'][0], 'For daily life until payday on 15 Oct 2026 (15 days): everyday basics €311.45 + '
                                                'free to spend €265.66 = €577.11, about €38.47 a day.')
        self.assertIn('arjen perusmenot 311,45 € + vapaasti käytettävissä 265,66 € = 577,11 €', p['summary']['fi'][0])
        conn.close()



class ChartAndPlanShareThePayday(unittest.TestCase):
    """qa-flows P2-20: Home said Thu 14 Nov, the 30-day chart labelled payday 15 Nov (Alex, Oct 2024)."""

    def test_salary_in_the_30_day_preview_lands_on_the_plan_payday(self):
        from scoach.forecast import preview_30_days
        conn = demo_connection()
        for customer_id in (ALEX, ROBIN, TAYLOR, KAI):
            for as_of in ('2024-10-31', '2026-09-30'):
                plan = spending_plan(conn, customer_id, as_of)
                salary = [e['date'] for e in preview_30_days(conn, customer_id, as_of)['scheduled_items'] if e['transaction_type'] == 'salary']
                with self.subTest(customer=customer_id, as_of=as_of):
                    self.assertIn(plan['next_payday'], salary)
        conn.close()


if __name__ == '__main__':
    unittest.main()
