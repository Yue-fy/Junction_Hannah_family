"""V5 lane EM: designed empty states (web/empty-states.js) and every call site that can be empty."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

import test_web_contract as contracts

WEB = Path(__file__).resolve().parents[1] / 'web'


def run_modules(test, body):
    """Run `body` as an ES module with the real web modules importable by file URL (relative imports resolve)."""
    if not shutil.which('node'):
        test.skipTest('Node is not installed')
    imports = '\n'.join(f'import * as {name} from {json.dumps((WEB / file).resolve().as_uri())};' for name, file in (
        ('E', 'empty-states.js'), ('C', 'charts.js'), ('A', 'answer-card.js'), ('Y', 'year-review.js'),
        ('P', 'plans.js'), ('M', 'money-profile.js'), ('H', 'home-v4.js')))
    script = "import assert from 'node:assert/strict';\n" + imports + '\n' + body
    result = subprocess.run(['node', '--input-type=module'], input=script, capture_output=True, text=True, timeout=30)
    test.assertEqual(result.returncode, 0, result.stderr[-4000:])
    return result.stdout


class ComponentTests(unittest.TestCase):
    def test_every_kind_has_art_title_body_and_a_safe_action(self):
        run_modules(self, r'''
for (const kind of E.EMPTY_KINDS) {
  const html = E.emptyStateHTML({kind, title: 'T <b>', body: 'B & c', action: {label: 'Go', attrs: {'data-view': 'goals', onclick: 'evil()', 'aria-label': 'Go there'}}});
  assert.ok(html.includes(`es--${kind}`), kind);
  assert.ok(html.includes('<svg class="es-art"') && html.includes('aria-hidden="true"'), 'decorative art');
  assert.ok(html.includes('T &lt;b&gt;') && html.includes('B &amp; c'), 'escaped');
  assert.ok(html.includes('data-view="goals"') && html.includes('aria-label="Go there"'));
  assert.ok(!html.includes('onclick'), 'only data-/aria- attributes pass');
  assert.ok(html.includes('empty-state'), 'legacy marker class kept');
}
assert.ok(E.emptyStateHTML({kind: 'nope', title: 'x'}).includes('es--list'), 'unknown kind falls back');
const c = E.emptyStateHTML({kind: 'coin', title: 'x', compact: true, celebrate: true, eyebrow: 'Sept'});
assert.ok(c.includes('es--compact') && c.includes('es--celebrate') && c.includes('es-spark') && c.includes('es-eyebrow'));
assert.ok(!E.emptyStateHTML({kind: 'coin', title: 'x'}).includes('es-actions'), 'no action → no button row');
''')

    def test_copy_exists_in_en_fi_sv_with_matching_placeholders(self):
        out = run_modules(self, 'console.log(JSON.stringify(E.EMPTY_COPY));')
        copy = json.loads(out)
        self.assertGreater(len(copy), 30)
        for key, values in copy.items():
            self.assertTrue(key.startswith('v5.em.'), key)
            self.assertEqual(len(values), 3, key)
            self.assertTrue(all(v.strip() for v in values), key)
            self.assertNotEqual(values[0], values[1], key + ' FI is not translated')
            self.assertNotEqual(values[0], values[2], key + ' SV is not translated')
            holes = [sorted(re.findall(r'\{(\w+)\}', v)) for v in values]
            self.assertTrue(holes[0] == holes[1] == holes[2], key)
            for banned in ('deterministic', 'scenario', 'MCC', 'quartile', 'provenance'):
                self.assertNotIn(banned, ' '.join(values), key)

    def test_surprise_filter_uses_the_last_real_surprise_cost_when_known(self):
        run_modules(self, r'''
const last = {what: 'Health', amount: '€134.50', date: '27 Aug 2026'};
const known = E.spendingEmptyHTML({group: 'irregular', locale: 'en', monthLabel: 'September 2026', last});
assert.ok(known.includes('No surprise costs') && known.includes('Last one: Health, €134.50 on 27 Aug 2026'));
assert.ok(known.includes('data-spending-group="all"') && known.includes('See all spending'));
assert.ok(known.includes('September 2026') && known.includes('es--celebrate'));
assert.ok(E.spendingEmptyHTML({group: 'irregular', last: null}).includes('Nothing unexpected in the past year'));
assert.ok(E.spendingEmptyHTML({group: 'irregular'}).includes('dentist'), 'generic line while looking');
const fi = E.spendingEmptyHTML({group: 'irregular', locale: 'fi', last: {what: 'Terveys', amount: '134,50 €', date: '27.8.2026'}});
assert.ok(fi.includes('Ei yllätysmenoja') && fi.includes('Edellinen: Terveys, 134,50 €') && fi.includes('Näytä kaikki menot'));
assert.ok(E.spendingEmptyHTML({group: 'leaks', locale: 'sv'}).includes('Inga småutgifter'));
assert.ok(E.spendingEmptyHTML({group: 'regular'}).includes('No must-pays recorded'));
const all = E.spendingEmptyHTML({group: 'all'});
assert.ok(all.includes('No spending recorded') && !all.includes('data-spending-group'), 'no "see all" loop when already on all');
assert.ok(E.spendingEmptyHTML({group: 'home'}).includes('Nothing in this group'));
''')


class CallSiteTests(unittest.TestCase):
    def test_charts_empty_helper_uses_the_designed_state_once_configured(self):
        run_modules(self, r'''
assert.ok(C.spendingRing([]).startsWith('<p class="empty-state">'), 'unconfigured charts stay plain (standalone use)');
C.configureCharts({locale: 'fi-FI', translate: (key, values) => key.startsWith('v5.em.') ? E.emptyText('fi', key, values) : key, emptyState: E.emptyStateHTML});
const trend = C.trendChart([]);
assert.ok(trend.includes('data-empty="chart-chart"') && trend.includes('es--compact'));
assert.ok(trend.includes('Kuva täydentyy'), 'helpful line is localized');
assert.ok(C.cashflowChart([]).includes('es--coin'));
assert.ok(C.goalChart(0, 0).includes('es--goal'));
assert.ok(C.spendingRing([]).includes('es--ring'));
assert.ok(C.flowChart([]).includes('Tälle valinnalle ei ole rahavirtoja'));
''')

    def test_answer_cards_with_no_data_show_an_empty_state_but_keep_pickers_and_next_questions(self):
        run_modules(self, r'''
const zero = {question_id: 'money.category', title: 'Travel in April 2025', headline: {label: 'Spent', value_text: '€0.00', value_cents: 0},
  lines: ['No payments in this category in April 2025.', 'Your monthly average over 6 months: €0.00.'],
  chart: {kind: 'trend', data: [{label: 'March 2025', value_cents: 0}, {label: 'April 2025', value_cents: 0}]},
  pickers: [{name: 'category', kind: 'category', value: 'Travel', options: [{value: 'Travel', label: 'Travel'}]}],
  followups: [{id: 'money.trend', text: 'How has my spending changed lately?'}], evidence: []};
assert.equal(A.emptyCardKind(zero), 'zero', 'an all-zero chart is no chart');
const html = A.renderCard(zero, {locale: 'en', turnId: '1'});
assert.ok(html.includes('data-empty="card-zero"') && html.includes('No payments in this category in April 2025.'));
assert.ok(!html.includes('answer-card__lines') && !html.includes('<svg xmlns'), 'no bare zero chart or duplicate lines');
assert.ok(html.includes('data-card-picker="category"') && html.includes('data-catalogue-question="money.trend"'));
const down = {question_id: 'money.where', title: 'Where?', headline: {label: 'Not available right now', value_text: '—', value_cents: null}, lines: ['Try another month.']};
assert.equal(A.emptyCardKind(down), 'unavailable');
assert.ok(A.renderCard(down).includes('data-empty="card-unavailable"'));
const tight = {question_id: 'room.week', title: 'Room', headline: {label: 'Safe to spend', value_text: '€0.00', value_cents: 0}, lines: ['Bills come first.']};
assert.equal(A.emptyCardKind(tight), null, '€0 safe to spend is a real answer, not an empty state');
assert.ok(!A.renderCard(tight).includes('data-empty'));
const real = {...zero, headline: {label: 'Spent', value_text: '€20.00', value_cents: 2000}};
assert.equal(A.emptyCardKind(real), null);
''')

    def test_year_review_without_data_paints_a_closable_empty_card(self):
        run_modules(self, r'''
const review = {year: 2023, available: false, cards: []};
const html = Y.renderStory(review, {locale: 'sv'});
assert.ok(html.includes('data-empty="year"') && html.includes('Tillbaka till min månad'));
assert.ok(/<button[^>]*es-action[^>]*data-story-close/.test(html), 'the next step closes the story');
const listeners = {};
const root = {innerHTML: '', ownerDocument: null, contains: () => false, querySelector: () => null,
  addEventListener: (name, fn) => { listeners[name] = fn; }, removeEventListener: () => {}};
const detach = Y.attachStory(root, {review, reducedMotion: true, render: i => Y.renderStory(review, {locale: 'en', index: i})});
assert.ok(root.innerHTML.includes('data-empty="year"'), 'an empty year is painted, not an invisible overlay');
detach();
''')

    def test_plans_profile_and_home_empty_states(self):
        run_modules(self, r'''
const h = {locale: 'fi', money: c => String(c), dateLabel: d => d, monthLabel: m => m};
const section = P.renderPlansSection({error: true}, h);
assert.ok(section.includes('data-empty="plans"') && section.includes('Suunnitelmat eivät juuri nyt lataudu'));
const tax = P.renderTaxCard({on: true, set_aside: {monthly_cents: 0}, tax_card: {status: 'looks_ok'}, dates: []}, h);
assert.ok(tax.includes('data-empty="tax-nothing"') && tax.includes('Ei mitään varattavaa'));
const me = M.renderProfilePage({entries: []}, [], 'en');
assert.ok(me.includes('data-profile-empty') && me.includes('class="es-art"'));
const goals = H.goalsHTML([], [], {locale: 'sv'});
assert.ok(goals.includes('data-empty="home-goals"') && goals.includes('data-view="goals"') && goals.includes('Starta ett mål'));
assert.ok(H.monthHTML([], {locale: 'en'}).includes('data-empty="home-month"'));
''')

    def test_styles_are_linked_and_call_sites_import_the_component(self):
        index = (WEB / 'index.html').read_text()
        self.assertIn('/empty-states.css', index)
        self.assertLess(index.index('/styles.css'), index.index('/empty-states.css'), 'empty states load after the base styles')
        for name in ('app.js', 'answer-card.js', 'year-review.js', 'plans.js', 'money-profile.js', 'home-v4.js'):
            self.assertIn("from './empty-states.js'", (WEB / name).read_text(), name)
        css = (WEB / 'empty-states.css').read_text()
        self.assertIn('.spending-layout.is-empty .ring-center', css, 'the ring centre never overlaps the empty state')
        self.assertIn('emptyState:emptyStateHTML', (WEB / 'app.js').read_text())


class AppIntegrationTests(unittest.TestCase):
    read = contracts.WebContractTests.read
    node_app = contracts.WebContractTests.node_app

    def test_empty_surprise_filter_replaces_the_ring_and_looks_up_the_last_surprise_cost(self):
        self.node_app(r'''
const originalFixture=fixture;
const month=[{transaction_ref:'rent',category:'Housing',transaction_type:'housing_payment',role:'fixed_obligation',date:'2026-09-05',amount_cents:-10000},
 {transaction_ref:'meal',category:'Restaurants',transaction_type:'purchase',role:'discretionary',date:'2026-09-09',amount_cents:-4000}];
const earlier=[{transaction_ref:'old',category:'Health',transaction_type:'purchase',role:'flexible_essential',date:'2026-06-02',amount_cents:-9000},
 {transaction_ref:'dentist',category:'Health',transaction_type:'purchase',role:'flexible_essential',date:'2026-08-27',amount_cents:-13450}];
fixture=(path,customer)=>path==='/api/transactions'?{transactions:calls.at(-1).query.role?earlier:month}:originalFixture(path,customer);
await app.load();
app.state.observedStart='2025-01-01';calls.length=0;
const group=new Element('irregular-group');group.dataset.spendingGroup='irregular';
documentListeners.click({target:group});
let html=get('spending-donut').innerHTML;
assert.ok(html.includes('data-empty="spending-irregular"'),'designed empty state replaces the ring');
assert.ok(!html.includes('spending-ring'),'no empty ring is drawn');
assert.equal(get('spending-categories').innerHTML,'','no second "no transactions" line');
await settle();
const lookup=calls.find(call=>call.path==='/api/transactions'&&call.query.role==='flexible_essential');
assert.ok(lookup,'the last surprise cost is looked up');
assert.equal(lookup.query.end,'2026-08-31');assert.equal(lookup.query.start,'2025-09-01');
html=get('spending-donut').innerHTML;
assert.ok(html.includes('Last one: Health, €134.50'),'uses the most recent real surprise cost');
const all=new Element('all-group');all.dataset.spendingGroup='all';
documentListeners.click({target:all});
assert.ok(get('spending-donut').innerHTML.includes('spending-ring'),'See all spending brings the ring back');
''')

    def test_empty_transactions_sheet_and_goals_page_are_designed(self):
        self.node_app(r'''
const originalFixture=fixture;
fixture=(path,customer)=>path==='/api/transactions'?{transactions:[]}:path==='/api/goals'?{goals:[]}:originalFixture(path,customer);
await app.load();
await app.showTransactions();await settle();
assert.ok(get('transaction-list').innerHTML.includes('data-empty="transactions"'));
assert.ok(get('transaction-list').innerHTML.includes('No transactions here'));
await app.loadGoals();await settle();
assert.equal(get('goals-list').innerHTML,'','one empty state for the goals page, not two');
assert.ok(get('wishes-list').innerHTML.includes('data-empty="goals"'));
assert.ok(get('wishes-list').innerHTML.includes('data-goal-template="custom"'),'next step opens the detailed planner');
''')


if __name__ == '__main__':
    unittest.main()
