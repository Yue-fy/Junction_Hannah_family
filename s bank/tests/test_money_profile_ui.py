"""Tests for web/money-profile.js (WP-I onboarding + Profile page UI), run through Node ESM."""
import json
import pathlib
import subprocess
import unittest

WEB = pathlib.Path(__file__).resolve().parents[1] / 'web'
MODULE = (WEB / 'money-profile.js').as_uri()

PRELUDE = (
    'import assert from "node:assert/strict";\n'
    'const p = await import(' + json.dumps(MODULE) + ');\n'
    'const money = c => "EUR" + (c / 100).toFixed(2);\n'
    'const H = {money, dateLabel: d => "D:" + String(d).slice(0, 10), monthLabel: m => "M:" + m};\n'
)


def run_node(body):
    result = subprocess.run(['node', '--input-type=module', '-e', PRELUDE + body], capture_output=True, text=True)
    return result


class MoneyProfileUiTest(unittest.TestCase):
    def node(self, body):
        result = run_node(body)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result.stdout

    def test_syntax(self):
        result = subprocess.run(['node', '--check', str(WEB / 'money-profile.js')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_message_maps_have_identical_keys(self):
        self.node(r'''
const keys = l => Object.keys(p.PROFILE_MESSAGES[l]).sort();
assert.deepEqual(keys('fi'), keys('en'));
assert.deepEqual(keys('sv'), keys('en'));
for (const l of ['en', 'fi', 'sv']) for (const [k, v] of Object.entries(p.PROFILE_MESSAGES[l])) {
  assert.ok(typeof v === 'string' && v.length > 0, l + ' ' + k);
  const ph = s => (s.match(/\{\w+\}/g) || []).sort().join();
  assert.equal(ph(v), ph(p.PROFILE_MESSAGES.en[k]), 'placeholders ' + l + ' ' + k);
}
for (const key of p.PROFILE_KEYS) assert.ok(p.PROFILE_MESSAGES.en['key.' + key], key);
for (const s of p.PROFILE_SOURCES) assert.ok(p.PROFILE_MESSAGES.en['source.' + s], s);
assert.equal(p.pm('de', 'page.title'), 'What your coach knows about you');
assert.equal(p.pm('fi', 'page.title'), 'Mitä valmentajasi tietää sinusta');
''')

    def test_onboarding_steps_definition(self):
        self.node(r'''
assert.deepEqual(p.ONBOARDING_STEPS.map(s => s.key), ['life_stage','household','income_stability','saving_rate_target_pct','regular_investing','debts','risk_attitude','upcoming']);
const slider = p.ONBOARDING_STEPS[3];
assert.equal(slider.type, 'slider'); assert.equal(slider.min, 0); assert.equal(slider.max, 30);
''')

    def test_reducer_full_flow_and_result_mapping(self):
        self.node(r'''
const sugg = [{id:'s1',key:'regular_investing',value:{active:true,monthly_cents:10000},question:'Is this a monthly investment?',evidence:{label:'Fund transfer on the 5th'},source:'from_your_transactions'},
              {id:'s2',key:'debts',value:[{type:'other',monthly_payment_cents:20000}],question:'Is this a loan?',evidence:{label:'Payment to bank'},source:'from_your_transactions'},
              {id:'s3',key:'life_stage',value:'working',question:'?',evidence:{label:'Salary'},source:'from_your_transactions'}];
let s = p.createOnboardingState({suggestions: sugg});
const start = JSON.stringify(s);
const answers = ['working', {adults:2, children:1}, 'varies', 15, {active:true, monthly_cents:5000},
  [{type:'mortgage', monthly_payment_cents:90000}, {type:'student_loan', monthly_payment_cents:8000}], 'cautious',
  [{what:'Moving', month:'2027-03', amount_cents:200000}]];
for (const value of answers) s = p.reduceOnboarding(s, {type:'answer', value});
assert.equal(JSON.stringify(p.createOnboardingState({suggestions: sugg})), start, 'input never mutated');
assert.equal(s.step, 8);
s = p.reduceOnboarding(s, {type:'toggleSuggestion', id:'s1', decision:'keep'});
s = p.reduceOnboarding(s, {type:'toggleSuggestion', id:'s2', decision:'dismiss'});
s = p.reduceOnboarding(s, {type:'toggleSuggestion', id:'s3', decision:'keep'});
s = p.reduceOnboarding(s, {type:'toggleSuggestion', id:'s3', decision:'keep'});
s = p.reduceOnboarding(s, {type:'toggleSuggestion', id:'nope', decision:'keep'});
s = p.reduceOnboarding(s, {type:'finish'});
assert.equal(s.done, true);
const r = p.onboardingResult(s);
assert.deepEqual(r.acceptedSuggestions, ['s1']);
assert.deepEqual(r.dismissedSuggestions, ['s2']);
assert.deepEqual(r.entries, [
  {key:'life_stage', value:'working', source:'you_told_me'},
  {key:'household', value:{adults:2, children:1}, source:'you_told_me'},
  {key:'income_stability', value:'varies', source:'you_told_me'},
  {key:'saving_rate_target_pct', value:15, source:'you_told_me'},
  {key:'regular_investing', value:{active:true, monthly_cents:5000}, source:'you_told_me'},
  {key:'debts', value:[{type:'mortgage', monthly_payment_cents:90000}, {type:'student_loan', monthly_payment_cents:8000}], source:'you_told_me'},
  {key:'risk_attitude', value:'cautious', source:'you_told_me'},
  {key:'upcoming', value:[{what:'Moving', month:'2027-03', amount_cents:200000}], source:'you_told_me'},
]);
''')

    def test_reducer_skip_back_and_validation(self):
        self.node(r'''
let s = p.createOnboardingState();
s = p.reduceOnboarding(s, {type:'back'});
assert.equal(s.step, 0);
s = p.reduceOnboarding(s, {type:'answer', value:'astronaut'});
assert.equal(s.step, 0); assert.equal(s.error, 'error.needChoice');
s = p.reduceOnboarding(s, {type:'answer', value:'student'});
assert.equal(s.error, null); assert.equal(s.step, 1);
s = p.reduceOnboarding(s, {type:'back'});
assert.equal(s.step, 0); assert.equal(s.answers.life_stage, 'student');
s = p.reduceOnboarding(s, {type:'skip'});
assert.equal(s.answers.life_stage, undefined, 'skip forgets the answer');
assert.deepEqual(s.skipped, ['life_stage']);
// slider range
s = p.reduceOnboarding(s, {type:'goto', step:3});
s = p.reduceOnboarding(s, {type:'answer', value:45});
assert.equal(s.error, 'error.badRange'); assert.equal(s.step, 3);
s = p.reduceOnboarding(s, {type:'skip'});   // "Not sure yet"
assert.equal(s.step, 4);
s = p.reduceOnboarding(s, {type:'answer', value:{active:false}});
assert.deepEqual(s.answers.regular_investing, {active:false});
s = p.reduceOnboarding(s, {type:'answer', value:[{type:'mortgage', monthly_payment_cents:0}]});
assert.equal(s.error, 'error.needAmount');
s = p.reduceOnboarding(s, {type:'answer', value:[]});
assert.deepEqual(s.answers.debts, []);
s = p.reduceOnboarding(s, {type:'skip'});
s = p.reduceOnboarding(s, {type:'answer', value:[{what:'Wedding'}]});
assert.equal(s.error, 'error.needMonth');
s = p.reduceOnboarding(s, {type:'answer', value:[{what:'  Wedding  ', month:'2027-06'}]});
assert.equal(s.step, 8);
assert.deepEqual(s.answers.upcoming, [{what:'Wedding', month:'2027-06'}]);
s = p.reduceOnboarding(s, {type:'skip'});
assert.equal(s.step, 8, 'skip is a no-op on the summary');
const r = p.onboardingResult(s);
assert.deepEqual(r.entries.map(e => e.key), ['regular_investing','debts','upcoming']);
assert.deepEqual(r.acceptedSuggestions, []);
// suggestions set later drop stale decisions
let t = p.createOnboardingState({suggestions:[{id:'a'}]});
t = p.reduceOnboarding(t, {type:'toggleSuggestion', id:'a', decision:'keep'});
t = p.reduceOnboarding(t, {type:'setSuggestions', suggestions:[{id:'b'}]});
assert.deepEqual(t.decisions, {});
''')

    def test_render_onboarding_steps_and_summary(self):
        self.node(r'''
let s = p.createOnboardingState({suggestions:[{id:'s<1>',key:'debts',value:[{type:'other',monthly_payment_cents:1500}],question:'Is <b>this</b> a loan?',evidence:{label:'Payee "X"'},source:'from_your_transactions'}]});
for (let i = 0; i < 8; i++) {
  const html = p.renderOnboarding(s, 'en', H);
  assert.ok(html.includes('data-onboarding-step="' + i + '"'));
  assert.ok(html.includes('data-onboarding-skip'), 'skip ' + i);
  assert.ok(html.includes('data-onboarding-back'), 'back ' + i);
  assert.equal((html.match(/class="onboarding-dot /g) || []).length, 9);
  assert.ok(html.includes(p.pm('en', 'onboarding.q.' + p.ONBOARDING_STEPS[i].key)));
  if (i === 0) { assert.ok(/data-onboarding-back disabled/.test(html)); assert.ok(html.includes('data-onboarding-choice="between_jobs"')); }
  if (i === 3) { assert.ok(html.includes('type="range"') && html.includes('max="30"') && html.includes('data-onboarding-notsure')); }
  if (i === 4) assert.ok(html.includes('data-onboarding-yesno="yes"'));
  if (i === 5) assert.ok(html.includes('data-onboarding-loan="mortgage"') && html.includes('data-onboarding-loans-none'));
  if (i === 7) assert.ok(html.includes('type="month"') && html.includes('data-onboarding-field="what"'));
  s = p.reduceOnboarding(s, i === 0 ? {type:'answer', value:'retired'} : {type:'skip'});
}
// draft reveals amounts for selected loans
let d = p.reduceOnboarding(p.reduceOnboarding(p.createOnboardingState(), {type:'goto', step:5}), {type:'draft', patch:{loans:['mortgage'], amounts:{mortgage:'900'}}});
const loansHtml = p.renderOnboarding(d, 'fi', H);
assert.ok(loansHtml.includes('data-onboarding-amount="mortgage"') && loansHtml.includes('value="900"') && loansHtml.includes('data-onboarding-next'));
const sum = p.renderOnboarding(s, 'en', H);
assert.ok(sum.includes('data-onboarding-finish') && sum.includes('Save to my money profile'));
assert.ok(sum.includes('data-onboarding-skipall') && sum.includes('Skip for now'));
assert.ok(sum.includes('Retired') && sum.includes('Skipped'));
assert.ok(sum.includes('data-onboarding-goto="0"'));
assert.ok(sum.includes('data-suggestion-keep="s&lt;1&gt;"') && sum.includes('data-suggestion-dismiss="s&lt;1&gt;"'));
assert.ok(sum.includes('Is &lt;b&gt;this&lt;/b&gt; a loan?') && sum.includes('Payee &quot;X&quot;'));
assert.ok(!sum.includes('<b>this'));
for (const l of ['fi', 'sv']) assert.ok(!p.renderOnboarding(s, l, H).includes('Save to my money profile'));
''')

    def test_attach_onboarding_with_fake_dom(self):
        self.node(r'''
const listeners = {};
const inputs = {};
const root = {innerHTML:'', addEventListener:(t, f) => { listeners[t] = f; }, removeEventListener:(t) => { delete listeners[t]; },
  contains: () => true,
  querySelector: sel => { const m = sel.match(/data-onboarding-field="(\w+)"/); return m && inputs[m[1]] !== undefined ? {value: inputs[m[1]]} : null; },
  querySelectorAll: sel => sel.includes('data-onboarding-amount') ? Object.entries(inputs).filter(([k]) => k.startsWith('loan:')).map(([k, v]) => ({value:v, getAttribute:() => k.slice(5)})) : []};
const btn = attrs => ({disabled:false, closest(){ return this; }, hasAttribute: a => a in attrs, getAttribute: a => attrs[a]});
const click = attrs => listeners.click({target: btn(attrs)});
const states = []; let finished = null, skipped = 0;
const ctl = p.attachOnboarding(root, {state: p.createOnboardingState({suggestions:[{id:'x', key:'note', value:'hi'}]}), onState: s => states.push(s), onFinish: r => { finished = r; }, onSkipAll: () => { skipped++; }, helpers: H});
assert.ok(root.innerHTML.includes('data-onboarding-step="0"'));
click({'data-onboarding-choice':'working'});
click({'data-onboarding-household':'partner_kids'});
assert.equal(ctl.getState().step, 1);
click({'data-onboarding-children':'2'});
click({'data-onboarding-next':''});
assert.deepEqual(ctl.getState().answers.household, {adults:2, children:2});
click({'data-onboarding-choice':'steady'});
inputs.pct = '12';
click({'data-onboarding-next':''});
assert.equal(ctl.getState().answers.saving_rate_target_pct, 12);
delete inputs.pct;
click({'data-onboarding-yesno':'yes'});
inputs.amount = '1 200,50';
click({'data-onboarding-next':''});
assert.deepEqual(ctl.getState().answers.regular_investing, {active:true, monthly_cents:120050});
delete inputs.amount;
click({'data-onboarding-loan':'mortgage'});
click({'data-onboarding-next':''});
assert.equal(ctl.getState().error, 'error.needAmount');
inputs['loan:mortgage'] = '900';
click({'data-onboarding-next':''});
assert.deepEqual(ctl.getState().answers.debts, [{type:'mortgage', monthly_payment_cents:90000}]);
click({'data-onboarding-skip':''});
click({'data-onboarding-skip':''});
assert.equal(ctl.getState().step, 8);
click({'data-suggestion-keep':'x'});
click({'data-onboarding-skipall':''});
assert.equal(skipped, 1);
click({'data-onboarding-finish':''});
assert.deepEqual(finished.acceptedSuggestions, ['x']);
assert.equal(finished.entries.length, 6);
assert.ok(finished.entries.every(e => e.source === 'you_told_me'));
assert.ok(states.length > 5);
ctl.detach();
assert.equal(listeners.click, undefined);
''')

    def test_render_profile_page(self):
        self.node(r'''
const E = (id, key, value, extra = {}) => ({id, key, value, source:'you_told_me', note:null, active:1, created_at:'2026-10-01T09:00:00Z', updated_at:'2026-11-01T09:00:00Z', ...extra});
const entries = [
  E('n1', 'note', 'I <script>alert(1)</script> want "calm"'),
  E('l1', 'life_stage', 'working', {source:'from_our_chat'}),
  E('d1', 'debts', [{type:'mortgage', monthly_payment_cents:90000}], {source:'from_your_transactions'}),
  E('s1', 'saving_rate_target_pct', 15),
  E('u1', 'upcoming', [{what:'Move & <new> flat', month:'2027-02'}]),
  E('ev1', 'life_event', {type:'job_loss', since:'2026-11-01'}),
  E('t1', 'tax', {tax_year:2026, base_rate_bp:2150}),
  E('y1', 'year_review', {year:2025}, {source:'year_review'}),
  E('h1', 'household', {adults:1, children:0}),
  E('gone', 'note', 'deleted note', {active:0}),
];
const sugg = [{id:'sg1', key:'regular_investing', value:{active:true, monthly_cents:10000}, question:'Do you invest <monthly>?', evidence:{label:'Transfers & funds'}, source:'from_your_transactions'}];
const normal = p.renderProfilePage({entries, mode:'normal'}, sugg, 'en', H);
assert.ok(normal.includes('What your coach knows about you'));
assert.ok(!normal.includes('data-profile-mode-off'), 'no banner in normal mode');
assert.ok(!normal.includes('<script>') && normal.includes('&lt;script&gt;') && normal.includes('&quot;calm&quot;'));
assert.ok(normal.includes('Move &amp; &lt;new&gt; flat') && normal.includes('Do you invest &lt;monthly&gt;?') && normal.includes('Transfers &amp; funds'));
assert.ok(!normal.includes('deleted note'), 'inactive entries hidden');
const order = ['about','income','loans','upcoming','events','taxes','notes','reviews','noticed'].map(id => normal.indexOf('data-profile-section="' + id + '"'));
order.forEach((pos, i) => { assert.ok(pos >= 0, 'section ' + i); if (i) assert.ok(pos > order[i - 1], 'order ' + i); });
const sectionOf = id => { const pos = normal.indexOf('data-profile-entry="' + id + '"'); const before = normal.slice(0, pos); return before.slice(before.lastIndexOf('data-profile-section="')).match(/data-profile-section="(\w+)"/)[1]; };
assert.equal(sectionOf('l1'), 'about'); assert.equal(sectionOf('h1'), 'about'); assert.equal(sectionOf('s1'), 'income');
assert.equal(sectionOf('d1'), 'loans'); assert.equal(sectionOf('u1'), 'upcoming'); assert.equal(sectionOf('ev1'), 'events');
assert.equal(sectionOf('t1'), 'taxes'); assert.equal(sectionOf('n1'), 'notes'); assert.equal(sectionOf('y1'), 'reviews');
for (const id of ['n1','l1','d1','s1','u1','ev1','t1','h1']) { assert.ok(normal.includes('data-profile-edit="' + id + '"'), id); assert.ok(normal.includes('data-profile-delete="' + id + '"'), id); }
assert.ok(normal.includes('data-profile-open-review="y1"') && normal.includes('data-profile-delete="y1"'));
for (const a of ['data-profile-open-tax', 'data-suggestion-keep="sg1"', 'data-suggestion-dismiss="sg1"', 'data-profile-add', 'data-profile-onboarding', 'data-profile-forget']) assert.ok(normal.includes(a), a);
for (const label of ['You told me', 'From your transactions', 'From our chat', 'Year in review']) assert.ok(normal.includes(label), label);
assert.ok(normal.includes('D:2026-11-01'));
assert.ok(normal.includes('EUR900.00'), 'uses passed money helper');
assert.ok(normal.includes('Things I noticed') && normal.includes('Keep') && normal.includes('Not this'));
const steady = p.renderProfilePage({entries, mode:'steady'}, [], 'en', H);
assert.ok(steady.includes('data-profile-mode-off="ev1"') && steady.includes('because you told me you lost your job'));
assert.ok(!steady.includes('data-profile-section="noticed"'));
const steadyNoEvent = p.renderProfilePage({entries:[E('a','note','x')], mode:'steady'}, [], 'sv', H);
assert.ok(steadyNoEvent.includes('data-profile-mode-off=""') && steadyNoEvent.includes('Vi tar det lite lugnare tills'));
const empty = p.renderProfilePage({entries:[], mode:'normal'}, [], 'fi', H);
assert.ok(empty.includes('data-profile-empty') && empty.includes('data-profile-onboarding') && empty.includes('data-profile-add') && empty.includes('Valmentajasi ei vielä tunne sinua'));
assert.ok(!empty.includes('data-profile-edit'));
const emptyNull = p.renderProfilePage(null, null, 'en');
assert.ok(emptyNull.includes('data-profile-empty'));
assert.ok(p.renderAddMenu('sv').includes('data-profile-add-key="note"'));
''')

    def test_attach_profile_page(self):
        self.node(r'''
let handler; const actions = [];
const root = {addEventListener:(t, f) => { handler = f; }, removeEventListener:() => { handler = null; }, contains:() => true};
const btn = (a, v = '') => ({disabled:false, closest(){ return this; }, hasAttribute: x => x === a, getAttribute: () => v});
const detach = p.attachProfilePage(root, {onAction: a => actions.push(a)});
handler({target: btn('data-profile-edit', 'e1')});
handler({target: btn('data-profile-forget')});
handler({target: btn('data-profile-add-key', 'note')});
handler({target: btn('data-suggestion-dismiss', 's9')});
assert.deepEqual(actions, [{type:'edit', id:'e1'}, {type:'forget'}, {type:'add_key', key:'note'}, {type:'suggestion_dismiss', id:'s9'}]);
detach(); assert.equal(handler, null);
''')

    def test_describe_entry_each_key(self):
        self.node(r'''
const d = (key, value, l = 'en') => p.describeEntry({key, value}, l, H);
assert.equal(d('life_stage', 'between_jobs'), 'Between jobs');
assert.equal(d('life_stage', 'between_jobs', 'fi'), 'Työnhaussa');
assert.equal(d('household', {adults:1, children:0}), 'Just you');
assert.equal(d('household', {adults:2, children:3}), '2 adults, 3 children');
assert.equal(d('household', {adults:1, children:1}, 'sv'), '1 vuxen, 1 barn');
assert.equal(d('income_stability', 'irregular'), 'It is irregular');
assert.equal(d('saving_rate_target_pct', 15), '15% of income');
assert.equal(d('saving_rate_target_pct', 12.5, 'fi'), '12,5 % tuloista');
assert.equal(d('emergency_fund_target_months', 3), '3 months of expenses');
assert.equal(d('emergency_fund_target_months', 1), '1 month of expenses');
assert.equal(d('regular_investing', {active:true, monthly_cents:10000}), 'Yes, EUR100.00 a month');
assert.equal(d('regular_investing', {active:true}), 'Yes, every month');
assert.equal(d('regular_investing', {active:false}), 'Not at the moment');
assert.equal(d('debts', []), 'No loans');
assert.equal(d('debts', [{type:'mortgage', monthly_payment_cents:90000, remaining_cents:15000000}, {type:'car_loan', monthly_payment_cents:25000}]), 'Mortgage EUR900.00 a month (EUR150000.00 left); Car loan EUR250.00 a month');
assert.equal(d('risk_attitude', 'balanced'), 'Somewhere in between');
assert.equal(d('coaching_style', 'direct', 'fi'), 'Suora');
assert.equal(d('protected_categories', ['Travel', 'Restaurants']), 'Travel, Restaurants');
assert.equal(d('protected_categories', []), 'None');
assert.equal(d('upcoming', [{what:'Wedding', month:'2027-06', amount_cents:500000}]), 'Wedding, M:2027-06, about EUR5000.00');
assert.equal(d('life_event', {type:'job_loss', since:'2026-11-01', note:'Company closed'}), 'Lost my job since D:2026-11-01 — Company closed');
assert.equal(d('life_event', {type:'moving', since:'2026-09'}, 'sv'), 'Flytt (sedan M:2026-09)');
assert.equal(d('note', 'Save for a bike'), 'Save for a bike');
assert.equal(d('tax', {tax_year:2026, base_rate_bp:2150, gross_monthly_cents:360000, decision_result:'back_tax', decision_amount_cents:42000}), 'Tax year 2026: Tax card 21.5%, gross EUR3600.00 a month, back taxes EUR420.00');
assert.equal(d('tax', {}), 'Tax details saved');
assert.equal(d('year_review', {year:2025}), 'Your 2025 in money');
assert.equal(d('year_review', {}), 'A saved year in review');
// default formatters work without helpers
assert.ok(p.describeEntry({key:'regular_investing', value:{active:true, monthly_cents:120050}}, 'fi').includes('1 200,50 €'));
''')

    def test_draft_spec_round_trip_each_key(self):
        self.node(r'''
const samples = {
  life_stage: 'self_employed', household: {adults:2, children:1}, income_stability: 'steady',
  saving_rate_target_pct: 12.5, emergency_fund_target_months: 3, regular_investing: {active:true, monthly_cents:15050},
  debts: [{type:'mortgage', monthly_payment_cents:90000, remaining_cents:12000000}, {type:'student_loan', monthly_payment_cents:8000}],
  risk_attitude: 'adventurous', coaching_style: 'gentle', protected_categories: ['Travel', 'Restaurants'],
  upcoming: [{what:'Wedding', month:'2027-06', amount_cents:500000}, {what:'New bike', month:'2027-01'}],
  life_event: {type:'income_drop', since:'2026-10-15', note:'Fewer shifts'},
  note: 'Mum’s birthday trip is important', tax: {tax_year:2026, base_rate_bp:2150, additional_rate_bp:4300, income_limit_cents:4000000, gross_monthly_cents:360000, assessment_end_month:7, decision_result:'refund', decision_amount_cents:31000},
  year_review: {year:2025, closing:'A calm year', facts:{saved_cents:100}},
};
const TYPES = ['text','amount','date','month','percent','select','number'];
assert.deepEqual(Object.keys(samples).sort(), [...p.PROFILE_KEYS].sort());
for (const [key, value] of Object.entries(samples)) {
  const entry = {id:'e-' + key, key, value, source:'you_told_me'};
  const spec = p.draftSpecForEntry(entry, 'en');
  assert.equal(spec.kind, 'profile'); assert.equal(spec.key, key); assert.equal(spec.entryId, 'e-' + key);
  assert.ok(spec.title.startsWith('Edit: ') && spec.saveLabel && spec.id === 'profile-e-' + key);
  for (const f of spec.fields) { assert.ok(TYPES.includes(f.type), key + ' ' + f.type); assert.ok(f.label && f.name); if (f.type === 'select') assert.ok(Array.isArray(f.options) && f.options.length); }
  const values = Object.fromEntries(spec.fields.map(f => [f.name, f.value]));
  const back = p.draftValueToEntry(key, values, key === 'year_review' ? value : undefined);
  assert.deepEqual(back.errors, {}, key);
  assert.deepEqual(back.value, value, 'round trip ' + key);
  const add = p.draftSpecForEntry(key, 'fi');
  assert.ok(add.title.startsWith('Lisää: ')); assert.equal(add.entryId, null); assert.equal(add.id, 'profile-new-' + key);
}
assert.throws(() => p.draftSpecForEntry('salary_iban'));
// amount fields carry cents; typed text is parsed
assert.equal(p.draftSpecForEntry({id:'x', key:'regular_investing', value:{active:true, monthly_cents:15050}}).fields[1].value, 15050);
assert.deepEqual(p.draftValueToEntry('debts', {type_0:'car_loan', monthly_0:'1 200,50', remaining_0:'', type_1:'', monthly_1:'', remaining_1:''}).value, [{type:'car_loan', monthly_payment_cents:120050}]);
assert.deepEqual(p.draftValueToEntry('debts', {type_0:'car_loan', monthly_0:''}).errors, {monthly_0:'error.needAmount'});
assert.deepEqual(p.draftValueToEntry('saving_rate_target_pct', {value:'95'}).errors, {value:'error.badRange'});
assert.equal(p.draftValueToEntry('note', {value:'x'.repeat(501)}).errors.value, 'error.tooLong');
assert.equal(p.draftValueToEntry('note', {value:'  '}).value, null);
assert.equal(p.draftValueToEntry('upcoming', {what_0:'Car', month_0:''}).errors.month_0, 'error.needMonth');
assert.equal(p.draftValueToEntry('tax', {decision_result:'refund', decision_amount:''}).errors.decision_amount, 'error.needAmount');
assert.deepEqual(p.draftValueToEntry('tax', {base_rate:'21,5'}, {decision_due_dates:['2026-08-01']}).value, {base_rate_bp:2150, decision_due_dates:['2026-08-01']});
assert.equal(p.draftValueToEntry('life_stage', {value:'pirate'}).errors.value, 'error.needChoice');
''')

    def test_parse_amount(self):
        self.node(r'''
const c = p.parseAmountToCents;
assert.equal(c('1 200,50'), 120050); assert.equal(c('1,200.50'), 120050); assert.equal(c('1.200,50'), 120050);
assert.equal(c('900'), 90000); assert.equal(c('900 €'), 90000); assert.equal(c('1,200'), 120000); assert.equal(c('12,5'), 1250);
assert.equal(c('1 200'), 120000); assert.equal(c(''), null); assert.equal(c('-5'), null); assert.equal(c('abc'), null); assert.equal(c('1,2,3.4.5'), null);
''')

    def test_css_rules(self):
        css = (WEB / 'profile-v3.css').read_text(encoding='utf-8')
        self.assertIn('prefers-reduced-motion', css)
        self.assertIn('min-height: 44px', css)
        for name in ['--green', '--deep-green', '--ink', '--muted', '--line', '--wash', '--mint', '--peach', '--radius']:
            self.assertIn('var(' + name + ')', css, name)
        for cls in ['.onboarding-dots', '.onboarding-bubble', '.profile-section', '.profile-source', '.profile-banner']:
            self.assertIn(cls, css)
        self.assertEqual(css.count('{'), css.count('}'))


if __name__ == '__main__':
    unittest.main()
