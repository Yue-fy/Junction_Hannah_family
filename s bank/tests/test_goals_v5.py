"""V5 fix lane GL: Goals page order, goal card (whole euros, HTML progress bar, "does it fit" line),
one card pattern for the mortgage and tax plans, mortgage chart axis and FI/SV grammar."""
import json
import pathlib
import re
import shutil
import subprocess
import unittest

WEB = pathlib.Path(__file__).resolve().parents[1] / 'web'


class GoalsMarkupTests(unittest.TestCase):
    def test_own_goals_come_before_the_form_and_the_optional_plans(self):
        html = (WEB / 'index.html').read_text(encoding='utf-8')
        view = html[html.index('<section id="goals-view"'):html.index('<section id="journal-view"')]
        order = [view.index(marker) for marker in ('id="goals-title"', 'id="goals-list"', 'id="wishes-list"', 'id="wish-form"', 'id="goal-planner"', 'id="plans-root"')]
        self.assertEqual(order, sorted(order))
        self.assertIn('data-i18n="goals.title"', view)
        self.assertIn('goals-v5.css', html)

    def test_goal_cards_and_wishes_share_one_full_width_grid(self):
        css = (WEB / 'goals-v5.css').read_text(encoding='utf-8')
        self.assertIn('repeat(auto-fit, minmax(min(100%, 340px), 1fr))', css)
        self.assertRegex(css, r'#goals-list, #goals-view \.goals-grid > #wishes-list \{ display: contents; \}')
        plans_css = (WEB / 'plans-v4.css').read_text(encoding='utf-8')
        self.assertIn('align-items: stretch', plans_css)
        self.assertIn('.plan-list.plan-list--wide', (WEB / 'plans-v5.css').read_text(encoding='utf-8'))


@unittest.skipUnless(shutil.which('node'), 'Node is required for UI checks')
class GoalsUiTests(unittest.TestCase):
    def run_node(self, body):
        script = ('import assert from "node:assert/strict";\n'
                  'const g = await import(' + json.dumps((WEB / 'goals-v5.js').as_uri()) + ');\n'
                  'const C = await import(' + json.dumps((WEB / 'charts.js').as_uri()) + ');\n'
                  'const m = await import(' + json.dumps((WEB / 'plans-mortgage.js').as_uri()) + ');\n'
                  'const x = await import(' + json.dumps((WEB / 'plans-tax.js').as_uri()) + ');\n'
                  'const plans = await import(' + json.dumps((WEB / 'plans.js').as_uri()) + ');\n'
                  'const T = {"goal.by": "By {date}", "common.estimate": "Estimate", "goal.assumptions": "How we worked this out"};\n'
                  'const H = {locale: "en", t: (k, v = {}) => T[k].replace(/\\{(\\w+)\\}/g, (_, n) => v[n]), dateLabel: d => d, monthLabel: m => m,\n'
                  '  actionsHTML: goal => `<div class="goal-actions" data-id="${goal.id}"></div>`};\n'
                  'const ITALY = {id: "g1", name: "A summer in Italy", target_date: "2027-03-31", as_of: "2026-09-30", target_cents: 300000, current_saved_cents: 0,\n'
                  '  remaining_cents: 300000, required_monthly_cents: 50000, conservative_monthly_contribution_cents: 19551, capacity_available: true,\n'
                  '  upfront_available_cents: 291351, required_monthly_after_now_cents: 1442, monthly_gap_cents: 0, reserve_floor_cents: 50000};\n'
                  + body)
        result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])

    def test_goal_fit_explains_the_gap_instead_of_contradicting_itself(self):
        self.run_node(r"""
const now = g.goalFit(ITALY);
assert.equal(now.kind, 'now'); assert.equal(now.after, 1442);
const card = g.goalCardHTML(ITALY, H, C.goalChart);
assert.match(card, /€500 <span>a month/); assert.ok(!card.includes('€500.00'), 'goal amounts are whole euros');
assert.match(card, /about €196\)\. If €2,914 from your account goes to this goal now, about €14 a month is enough/);
assert.match(card, /goal-fit--info/); assert.match(card, /safety cushion of €500 stays untouched/);
assert.match(card, /data-goal-evidence="g1"/); assert.match(card, /class="goal-actions"/);
const car = {...ITALY, id: 'g2', name: 'New car', target_cents: 1500000, current_saved_cents: 200000, remaining_cents: 1300000,
  required_monthly_cents: 86667, required_monthly_after_now_cents: 67244, monthly_gap_cents: 47693};
const over = g.goalFit(car);
assert.equal(over.kind, 'over'); assert.equal(over.gap, 47693); assert.equal(over.reachMonth, '2032-04');
const carCard = g.goalCardHTML(car, H, C.goalChart);
assert.match(carCard, /goal-fit--warn/); assert.match(carCard, /€867 a month is €477 more than you usually have left \(about €196\)/);
assert.match(carCard, /get there in 2032-04/);
assert.equal(g.goalFit({...ITALY, required_monthly_cents: 10000}).kind, 'ok');
assert.equal(g.goalFit({...ITALY, conservative_monthly_contribution_cents: 0}).kind, 'none');
assert.equal(g.goalFit({...ITALY, capacity_available: false}).kind, 'unknown');
assert.equal(g.goalFit({...ITALY, remaining_cents: 0}).kind, 'done');
// Finnish: inessive month, whole euros with a space.
const fi = g.goalCardHTML(car, {...H, locale: 'fi', monthLabel: () => 'huhtikuu 2032'}, C.goalChart);
assert.match(fi, /pääsisit tavoitteeseen huhtikuussa 2032/); assert.match(fi.replace(/\s/g, ' '), /867 € kuukaudessa/);
// lane NB's goal.fit wording wins when the server sends it, still shown as a clear warning.
const nb = g.goalCardHTML({...car, fit: {status: 'over', gap_cents: 47693, texts: {en: 'Server says: too much a month.', fi: 'Palvelin: liikaa.', sv: 'Servern: för mycket.'}}}, H, C.goalChart);
assert.match(nb, /goal-fit--warn/); assert.match(nb, /Server says: too much a month\./);
assert.match(g.goalCardHTML({...ITALY, fit: {status: 'fits', texts: {en: 'Fits.'}}}, {...H, locale: 'fi'}, C.goalChart), /goal-fit--ok[^]*Fits\./);
for (const key of g.GOALS_COPY_KEYS) for (const l of ['en', 'fi', 'sv']) assert.ok(g.goalsText(l, key) !== key, key + ' ' + l);
for (const key of g.GOALS_COPY_KEYS) assert.notEqual(g.goalsText('sv', key), g.goalsText('en', key), key + ' sv untranslated');
""")

    def test_goal_progress_is_html_so_text_never_scales(self):
        self.run_node(r"""
const bar = C.goalChart(75000, 300000);
assert.ok(!bar.includes('<svg') && !bar.includes('<text'), 'no SVG text that scales with the card width');
assert.match(bar, /class="goal-progress"/); assert.match(bar, /width:25\.0%/); assert.match(bar, /25% saved/); assert.match(bar, /€3,000 target/);
assert.match(bar, /role="img" aria-label="€750 saved toward €3,000\. 25% complete\."/);
assert.match(C.goalChart(0, 0), /Choose a target/);
""")

    def test_both_plans_use_one_card_and_example_pattern(self):
        self.run_node(r"""
const h = {locale: 'en', money: c => '€' + (c / 100).toFixed(2), dateLabel: d => d, monthLabel: d => d};
const mort = m.renderMortgageCard({on: false, prefill: {found: true, source: 'detected', monthly_payment_cents: 52838, payment_day: 5}}, {}, h);
const tax = x.renderTaxCard({on: false, stage: {stage: 'decision_pending', tax_year: 2025, next_date: '2026-10-31'}}, h);
for (const html of [mort, tax]) {
  assert.match(html, /plan-pill plan-pill--off">Off</); assert.match(html, /class="plan-actions plan-off-actions"/);
  assert.match(html, /class="secondary-button plan-turn-on"/); assert.match(html, /See an example<span class="plan-chevron" aria-hidden="true">›<\/span>/);
}
assert.match(mort, /around the 5th\./);
// Examples replace the card body; "Use my own numbers ›" then one close link at the bottom, in both plans.
const taxEx = x.renderTaxCard({on: false, example: {open: true, data: {inputs: {gross_monthly_cents: 310000}, set_aside: {monthly_cents: 0}}}}, h);
assert.match(taxEx, /plan-card--example plan-card--wide/); assert.ok(!taxEx.includes('data-plan-on="tax"'));
assert.match(taxEx, /data-plan-tax-own>Use my own numbers <span aria-hidden="true">›<\/span><\/button><button type="button" class="text-button" data-plan-tax-example-close>Close the example</);
assert.match(taxEx, /€3,100\/month/);
const failed = m.renderMortgageCard({on: false}, {example: {error: true}}, h);
assert.equal((failed.match(/data-plan-example-close/g) || []).length, 1);
// One wide plan makes every plan card full width.
assert.match(plans.renderPlansSection({loading: false, mortgage: {on: false}, tax: {on: false}, ui: {example: {loading: true}}}, h), /plan-list plan-list--wide/);
assert.ok(!plans.renderPlansSection({loading: false, mortgage: {on: false}, tax: {on: false}, ui: {}}, h).includes('plan-list--wide'));
assert.match(plans.renderPlansSection({loading: false, mortgage: {on: false}, tax: {on: false}, ui: {}}, h), /Plans \(optional\)/);
""")

    def test_empty_tax_plan_asks_for_numbers_and_never_says_withholding_is_enough(self):
        self.run_node(r"""
const h = {locale: 'en', money: c => '€' + (c / 100).toFixed(2), dateLabel: d => d, monthLabel: d => d};
const empty = x.renderTaxCard({on: true, set_aside: {monthly_cents: 0, instalments: []}, refund: null, tax_card: {status: 'missing'}}, h);
assert.match(empty, /Nothing is set aside yet\. Add the numbers from your tax card/); assert.match(empty, /data-plan-edit="tax">Add tax card numbers/);
assert.ok(!/looks enough|enough for now/i.test(empty.replace(/check whether your withholding is enough/, '')));
assert.ok(!x.renderTaxCard({on: true, needs_inputs: false, set_aside: {monthly_cents: 0, instalments: []}, tax_card: {status: 'missing'}}, h).includes('Add tax card numbers'));
assert.match(x.renderTaxCard({on: true, needs_inputs: true, set_aside: {monthly_cents: 0}, tax_card: {status: 'looks_ok'}}, h), /Add tax card numbers/);
assert.match(x.taxText('fi', 'v5.tx.outlook'), /^Ennuste$/); assert.equal(x.taxText('sv', 'v5.tx.outlook'), 'Prognos');
assert.equal(x.taxText('sv', 'v5.tx.in.rate'), 'Skatteprocent på skattekortet');
""")

    def test_mortgage_wording_axis_and_what_if_feedback(self):
        self.run_node(r"""
assert.equal(m.formatTerm(18, 'en'), '1 year 6 months'); assert.equal(m.formatTerm(34, 'en'), '2 years 10 months');
assert.equal(m.formatTerm(13, 'en'), '1 year 1 month'); assert.equal(m.formatTerm(1, 'en'), '1 month');
assert.equal(m.mortgageText('fi', 'v5.mg.rateUp'), 'Jos korko nousee 1 prosenttiyksiköllä');
assert.equal(m.mortgageText('sv', 'v5.mg.rateDown'), 'Om räntan sjunker med 1 procentenhet');
assert.equal(m.mortgageText('fi', 'v5.mg.extraPaid', {month: 'maaliskuu 2047'}), 'Maksettu maaliskuussa 2047');
assert.equal(m.mortgageText('sv', 'v5.mg.extraPaid', {month: 'mars 2047'}), 'Betalt i mars 2047');
const editSpec = m.mortgageSpec('en', {value: {principal_cents: 20000000, remaining_months: 240}, prefill: {monthly_payment_cents: 136260}});
assert.equal(editSpec.fields.find(f => f.name === 'monthly_payment_cents').value, '', 'a cleared payment stays cleared when editing');
assert.equal(m.mortgageSpec('en', {prefill: {monthly_payment_cents: 136260}}).fields.find(f => f.name === 'monthly_payment_cents').value, 136260);
assert.equal(m.mortgageText('fi', 'f.years'), 'Laina-aikaa jäljellä, vuotta');
assert.equal(m.ordinalDay(1, 'en'), '1st'); assert.equal(m.ordinalDay(12, 'en'), '12th'); assert.equal(m.ordinalDay(23, 'en'), '23rd');
assert.equal(m.ordinalDay(5, 'sv'), '5:e'); assert.equal(m.ordinalDay(2, 'sv'), '2:a');
// x axis: first and last year plus round years in between; light read-out with the hint while idle.
const curve = Array.from({length: 23}, (_, i) => ({n: i * 12, month: (2026 + i) + '-09', balance_cents: 18000000 - i * 800000}));
const svg = m.balanceChartSVG(curve, null, {locale: 'en'});
const ticks = [...svg.matchAll(/class="mg-xtick[^"]*"[^>]*>(\d{4})</g)].map(t => t[1]);
assert.deepEqual(ticks, ['2026', '2030', '2035', '2040', '2045', '2048']);
assert.match(svg, /class="mg-tip is-idle"[^>]*><span class="mg-tip-hint">Tap or hover the chart to see any year\./);
assert.ok(!/#2f6fb5/.test(svg));
""")


if __name__ == '__main__':
    unittest.main()
