"""V5 lane TX: the optional tax plan with an example (preview without saving), the off card and the Me row."""
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from scoach import money_profile as mp, plans
from scoach.api import Application
from tests.core_helper import demo_connection

WEB = pathlib.Path(__file__).resolve().parents[1] / 'web'
DEMO_DB = pathlib.Path(__file__).resolve().parents[1] / 'var/scoach.sqlite3'
ALEX = 'CUST00001'
AS_OF = '2026-09-30'


class PreviewTests(unittest.TestCase):
    def setUp(self):
        if not DEMO_DB.is_file():
            self.skipTest('demo database not built')
        self.conn = demo_connection()

    def entry_count(self):
        return len(mp.get_profile(self.conn, ALEX, AS_OF)['entries'])

    def test_example_runs_the_real_calculation_and_saves_nothing(self):
        before = self.entry_count()
        result = plans.tax_plan_preview(self.conn, ALEX, AS_OF)
        self.assertTrue(result['preview']); self.assertTrue(result['example']); self.assertFalse(result['on'])
        self.assertIsNone(result['entry_id'])
        self.assertEqual(result['inputs'], plans.TAX_EXAMPLE)
        # €630 expected back tax, spread until about 1 Sep next year (12 months from 30 Sep): €52.50 a month.
        self.assertEqual(result['set_aside']['monthly_cents'], 5250)
        self.assertEqual(result['set_aside']['until'], '2027-09-01')
        self.assertEqual(result['tax_card']['status'], 'income_above_limit')
        self.assertEqual(result['tax_card']['projected_gross_cents'], 3_720_000)
        self.assertNotIn('transaction_refs', result['tax_card'])
        self.assertEqual([d['kind'] for d in result['dates']], ['decision_pending', 'back_tax'])
        self.assertEqual(result['stage']['next_date'], '2026-10-31')  # verotuspäätös by 31 Oct (calendar)
        self.assertEqual(result['stage']['tax_year'], 2025)
        self.assertEqual(self.entry_count(), before)
        self.assertFalse(plans.tax_plan(self.conn, ALEX, AS_OF)['on'])

    def test_preview_matches_a_saved_plan_with_the_same_inputs(self):
        inputs = {'expected_back_tax_cents': 63_000, 'expected_refund_cents': 0}
        preview = plans.tax_plan_preview(self.conn, ALEX, AS_OF, inputs=inputs)
        self.assertFalse(preview['example'])
        plans.save_plan(self.conn, ALEX, 'tax', {'on': True, 'expected_back_tax_cents': 63_000})
        saved = plans.tax_plan(self.conn, ALEX, AS_OF)
        self.assertEqual(preview['set_aside'], saved['set_aside'])
        self.assertEqual(preview['tax_card']['status'], 'missing')

    def test_refund_only_and_bad_inputs(self):
        result = plans.tax_plan_preview(self.conn, ALEX, AS_OF, inputs={'expected_refund_cents': 20_000})
        self.assertEqual(result['set_aside']['monthly_cents'], 0)
        self.assertEqual(result['refund']['source'], 'your_estimate')
        for bad in ({'expected_refund_cents': -1}, {'base_rate_bp': 20_000}, {'salary': 1}, {'gross_monthly_cents': '3100'}):
            with self.assertRaises(ValueError):
                plans.tax_plan_preview(self.conn, ALEX, AS_OF, inputs=bad)

    def test_prefill_uses_own_tax_card_and_net_salary_hint(self):
        prefill = plans.tax_plan(self.conn, ALEX, AS_OF)['prefill']
        self.assertIsNone(prefill['gross_monthly_cents'])
        self.assertGreater(prefill['net_salary_cents'], 0)
        mp.save_entry(self.conn, ALEX, 'tax', {'tax_year': 2026, 'base_rate_bp': 2_150, 'gross_monthly_cents': 310_000}, 'you_told_me')
        prefill = plans.tax_plan(self.conn, ALEX, AS_OF)['prefill']
        self.assertEqual((prefill['base_rate_bp'], prefill['gross_monthly_cents']), (2_150, 310_000))
        self.assertIsNotNone(prefill['tax_card_entry_id'])
        # The example is never mixed with the customer's own card.
        self.assertEqual(plans.tax_plan_preview(self.conn, ALEX, AS_OF)['inputs'], plans.TAX_EXAMPLE)


class PreviewApiTests(unittest.TestCase):
    def setUp(self):
        if not DEMO_DB.is_file():
            self.skipTest('demo database not built')
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / 'db.sqlite3'
        shutil.copy(DEMO_DB, self.db)
        self.app = Application(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def get(self, query):
        return self.app.handle('GET', '/api/plans/tax/preview?customer_id=%s%s' % (ALEX, query), None)

    def test_route(self):
        status, body = self.get('')
        self.assertEqual(status, 200, body)
        self.assertTrue(body['data']['example'])
        self.assertEqual(body['data']['set_aside']['monthly_cents'], 5250)
        status, body = self.get('&gross_monthly_cents=250000&base_rate_bp=1800&income_limit_cents=4000000&expected_back_tax_cents=12000')
        self.assertEqual(status, 200, body)
        self.assertFalse(body['data']['example'])
        self.assertEqual(body['data']['set_aside']['monthly_cents'], 1000)
        self.assertEqual(body['data']['tax_card']['status'], 'income_below_limit')
        for bad in ('&expected_refund_cents=-1', '&base_rate_bp=21.5', '&bogus=1', '&base_rate_bp=20000'):
            self.assertEqual(self.get(bad)[0], 400, bad)
        status, body = self.app.handle('GET', '/api/profile?customer_id=' + ALEX, None)
        self.assertNotIn('plan_tax', [e['key'] for e in body['data']['profile']['entries']])
        self.assertEqual(self.app.handle('POST', '/api/plans/tax/preview', {'customer_id': ALEX})[0], 405)


@unittest.skipUnless(shutil.which('node'), 'Node is required for UI checks')
class TaxPlanUiTests(unittest.TestCase):
    def run_node(self, body):
        script = ('import assert from "node:assert/strict";\n'
                  'const m = await import(' + json.dumps((WEB / 'plans-tax.js').as_uri()) + ');\n'
                  'const fi = d => d ? d.slice(8).replace(/^0/, "") + "." + d.slice(5, 7).replace(/^0/, "") + "." + d.slice(0, 4) : "";\n'
                  'const H = {en: {locale: "en", money: c => "€" + (c / 100).toFixed(2), dateLabel: d => d},\n'
                  '  fi: {locale: "fi", money: c => (c / 100).toFixed(2).replace(".", ",") + " €", dateLabel: fi},\n'
                  '  sv: {locale: "sv", money: c => (c / 100).toFixed(2).replace(".", ",") + " €", dateLabel: fi}};\n'
                  'const OFF = {on: false, stage: {stage: "decision_pending", next_date: "2026-10-31", tax_year: 2025}, omavero_text: "OmaVero (vero.fi)"};\n'
                  'const EXAMPLE = {preview: true, example: true, inputs: {gross_monthly_cents: 310000, base_rate_bp: 2150, income_limit_cents: 3400000, expected_back_tax_cents: 63000},\n'
                  '  set_aside: {monthly_cents: 5250, until: "2027-09-01", instalments: [{status: "upcoming", amount_cents: 63000, due_date: "2027-09-01", date_is_estimate: true}]},\n'
                  '  tax_card: {status: "income_above_limit", projected_gross_cents: 3720000, income_limit_cents: 3400000},\n'
                  '  dates: [{date: "2026-10-31", kind: "decision_pending"}, {date: "2027-09-01", kind: "back_tax"}], omavero_text: "OmaVero (vero.fi)"};\n'
                  + body)
        result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_copy_in_three_languages_with_finnish_terms(self):
        self.run_node(r"""
for (const key of m.TAX_COPY_KEYS) for (const l of ['en', 'fi', 'sv']) { const v = m.taxText(l, key); assert.ok(v && v !== key, key + ' ' + l); }
for (const key of m.TAX_COPY_KEYS.filter(k => k.startsWith('v5.tx.'))) assert.notEqual(m.taxText('fi', key), m.taxText('en', key), key);
assert.equal(m.omaVero('sv'), 'MinSkatt'); assert.equal(m.omaVero('fi'), 'OmaVero');
assert.equal(m.nextTaxDateText(OFF.stage, 'fi', H.fi.dateLabel), 'Vuoden 2025 verotuspäätöksesi on OmaVero-palvelussa viimeistään 31.10.2026.');
assert.equal(m.nextTaxDateText(OFF.stage, 'en', d => '31 Oct'), 'Your 2025 tax decision will be in OmaVero by 31 Oct at the latest.');
assert.match(m.nextTaxDateText(OFF.stage, 'sv', H.sv.dateLabel), /beskattningsbeslut för 2025 finns i MinSkatt senast 31\.10\.2026/);
assert.match(m.nextTaxDateText({stage: 'return_coming', tax_year: 2026}, 'fi', H.fi.dateLabel), /esitäytetyt veroilmoitukset.*huhtikuussa/);
assert.match(m.nextTaxDateText({stage: 'back_tax_due', next_date: null}, 'en', H.en.dateLabel), /exact tax dates are in OmaVero/);
assert.equal(m.nextTaxDateText(null, 'en', H.en.dateLabel), '');
""")

    def test_off_card_is_useful_and_example_is_labelled(self):
        self.run_node(r"""
const off = m.renderTaxCard(OFF, H.en);
assert.match(off, /data-plan-on="tax"/); assert.match(off, /data-plan-tax-example/); assert.match(off, /aria-expanded="false"/);
assert.match(off, /2025 tax decision will be in OmaVero by 2026-10-31/); assert.match(off, /back taxes/);
assert.ok(!off.includes('tax-example__badge'));
const loading = m.renderTaxCard({...OFF, example: {open: true}}, H.en);
assert.match(loading, /Working out the example/); assert.ok(!loading.includes('data-plan-on="tax"'), 'the example replaces the card body, like the mortgage example');
const open = m.renderTaxCard({...OFF, example: {open: true, data: EXAMPLE}}, H.en);
assert.match(open, /Example — not your numbers/); assert.match(open, /data-plan-tax-own/); assert.match(open, /data-plan-tax-example-close/);
assert.match(open, /€52\.50/); assert.match(open, /€3,100\/month/); assert.match(open, /21\.5%/); assert.match(open, /about €630 expected/);
// One close control, at the bottom next to "Use my own numbers" (no × in a nested box).
assert.equal((open.match(/data-plan-tax-example-close/g) || []).length, 1); assert.ok(!open.includes('×'));
assert.ok(open.indexOf('data-plan-tax-own') < open.indexOf('data-plan-tax-example-close'));
assert.match(open, /higher than the income limit/); assert.match(open, /Back tax due/); assert.match(open, /Nothing is saved/);
const fiOpen = m.renderTaxCard({...OFF, example: {open: true, data: EXAMPLE}}, H.fi);
assert.match(fiOpen, /Esimerkki – ei sinun lukujasi/); assert.match(fiOpen, /21,5 %/); assert.match(fiOpen, /52,50 €/); assert.match(fiOpen, /OmaVero-palvelussa/);
const svOpen = m.renderTaxCard({...OFF, example: {open: true, data: EXAMPLE}}, H.sv);
assert.match(svOpen, /MinSkatt/); assert.ok(!svOpen.includes('OmaVero'));
assert.match(m.renderTaxCard({...OFF, example: {open: true, error: true}}, H.en), /not available right now/);
for (const html of [off, open, fiOpen]) for (const word of ['scenario', 'deterministic', 'provenance', 'preview', 'MCC']) assert.ok(!html.includes(word), word);
const on = m.renderTaxCard({on: true, set_aside: EXAMPLE.set_aside, tax_card: {status: 'looks_ok'}, dates: EXAMPLE.dates}, H.en);
assert.match(on, /data-plan-off="tax"/); assert.match(on, /data-plan-edit="tax"/); assert.ok(!on.includes('data-plan-tax-example'));
""")

    def test_form_conversion_and_card_merge(self):
        self.run_node(r"""
const spec = m.taxSpec('fi', {prefill: {base_rate_bp: 2150, net_salary_cents: 232560, money: H.fi.money}});
assert.deepEqual(spec.fields.map(f => f.name), ['gross_monthly_cents', 'base_rate_pct', 'income_limit_cents', 'expected_back_tax_cents', 'expected_refund_cents']);
assert.equal(spec.fields[1].value, 21.5); assert.match(spec.fields[0].help, /2325,60 €/);
const own = m.taxSpec('en', {value: {on: true, expected_back_tax_cents: 63000}, prefill: {expected_back_tax_cents: 1}});
assert.equal(own.fields[3].value, 63000);
const v = m.taxValue({gross_monthly_cents: 310000, base_rate_pct: 21.5, income_limit_cents: null, expected_back_tax_cents: 63000, expected_refund_cents: 0});
assert.deepEqual(v.value, {on: true, expected_back_tax_cents: 63000});
assert.deepEqual(v.card, {gross_monthly_cents: 310000, base_rate_bp: 2150});
assert.deepEqual(v.inputs, {gross_monthly_cents: 310000, base_rate_bp: 2150, expected_back_tax_cents: 63000});
assert.equal(m.taxValue({}).card, null);
assert.deepEqual(m.mergeTaxCard({tax_year: 2026, income_limit_cents: 1, decision_result: 'none'}, {base_rate_bp: 2000}, 2026), {tax_year: 2026, decision_result: 'none', base_rate_bp: 2000});
assert.deepEqual(m.mergeTaxCard({tax_year: 2025, decision_result: 'refund'}, {base_rate_bp: 2000}, 2026), {tax_year: 2026, base_rate_bp: 2000});
assert.equal(m.previewLine(EXAMPLE, 'en', H.en), 'About €52.50 a month for back taxes, until 2027-09-01. Your income looks higher than the tax card limit.');
assert.equal(m.previewLine({set_aside: {monthly_cents: 0}}, 'fi', H.fi), 'Jäännösveroa varten ei tarvitse varata.');
""")

    def test_me_row_is_compact_and_points_to_the_plan(self):
        self.run_node(r"""
const offRow = m.meTaxRowHTML(null, OFF, H.en);
assert.match(offRow, /data-profile-open-tax-plan/); assert.match(offRow, /Off/); assert.match(offRow, /see an example/); assert.match(offRow, /2025 tax decision/);
assert.ok(!offRow.includes('data-profile-edit'));
const entry = {id: 'profile:9', key: 'plan_tax', value: {on: true, expected_back_tax_cents: 63000}};
const onRow = m.meTaxRowHTML(entry, {on: true, set_aside: EXAMPLE.set_aside, stage: OFF.stage}, H.fi);
assert.match(onRow, /52,50 € kuukaudessa jäännösveroa varten, 1\.9\.2027 asti/); assert.match(onRow, /data-profile-edit="profile:9"/); assert.match(onRow, /Käytössä/);
assert.match(m.meTaxRowHTML(entry, null, H.en), /Back taxes I expect for this year: €630\.00/);
const p = await import(""" + json.dumps((WEB / 'money-profile.js').as_uri()) + r""");
const entries = [{id: 'profile:1', key: 'plan_mortgage', value: {principal_cents: 18000000, reference_rate_bp: 225, margin_bp: 60, loan_type: 'annuity', reference_rate: 'euribor_12m', remaining_months: 240}, source: 'you_told_me', active: true},
  entry && {...entry, source: 'you_told_me', active: true}, {id: 'profile:3', key: 'tax', value: {tax_year: 2026, base_rate_bp: 2150}, source: 'you_told_me', active: true}];
const html = p.renderProfilePage({entries, by_key: {}}, [], 'en', {money: H.en.money});
const taxes = html.slice(html.indexOf('data-profile-section="taxes"'));
assert.match(taxes, /data-me-tax-row/); assert.match(taxes, /data-profile-edit="profile:3"/);
assert.ok(!html.includes('Open my taxes'));
const plansSection = html.slice(html.indexOf('data-profile-section="plans"'));
assert.ok(!plansSection.slice(0, plansSection.indexOf('</section>')).includes('profile:9'), 'tax plan is shown once, in the Taxes row');
const empty = p.renderProfilePage({entries: [], by_key: {}}, [], 'sv', {});
assert.match(empty, /data-me-tax-row/); assert.match(empty, /Skatteplan/);
let action = null;
const button = {hasAttribute: a => a === 'data-profile-open-tax-plan', getAttribute: () => null, disabled: false, closest() { return this; }};
const root = {contains: () => true, addEventListener(_n, f) { this.f = f; }, removeEventListener() {}};
p.attachProfilePage(root, {onAction: a => { action = a; }});
root.f({target: button});
assert.deepEqual(action, {type: 'open_tax_plan'});
""")


if __name__ == '__main__':
    unittest.main()
