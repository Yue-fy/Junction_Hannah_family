"""Home as the Payday Plan (V4 lane H): plan adapter, plan card, insight, and app wiring."""
import json
import subprocess
import unittest
from pathlib import Path

import test_web_contract as contracts

WEB = Path(__file__).resolve().parents[1] / 'web'

# Alex, 30 Sept 2026, as returned today by safe_until_payday (trimmed to the fields Home reads).
LEGACY = {
    'reference_date': '2026-09-30', 'next_payday': '2026-10-22', 'days_until_payday': 22, 'payday_source': 'detected',
    'starting_balance_cents': 472358, 'reserve_floor_cents': 50000, 'committed_cents': 64595,
    'committed_items': [
        {'date': '2026-10-05', 'label': 'Housing', 'amount_cents': 52838, 'source': 'recurring', 'transaction_type': 'housing_payment'},
        {'date': '2026-10-17', 'label': 'Utilities', 'amount_cents': 11757, 'source': 'recurring', 'transaction_type': 'utilities_payment'},
    ],
    'planned_saving_cents': 0, 'free_cents': 357763, 'spendable_cents': 357763, 'shortfall_cents': 0,
    'per_day_cents': 16261, 'this_week_cents': 113827, 'everyday_buffer_cents': 127879,
    'safe_to_save_cents': 229884, 'safe_to_save_available': True, 'steady_mode': False,
}
# Lane N's spending_plan contract (docs/V4_SPEC.md).
PLAN = {
    'as_of': '2026-09-30', 'balance_cents': 472358, 'next_payday': '2026-10-15', 'days_to_payday': 15,
    'held_back': [
        {'kind': 'bill', 'label': 'Housing', 'amount_cents': 52838, 'date': '2026-10-05'},
        {'kind': 'loan', 'label': 'Car loan', 'amount_cents': 20000, 'date': '2026-10-10', 'source': 'declared'},
        {'kind': 'tax', 'label': '', 'amount_cents': 5000, 'date': None},
        {'kind': 'buffer', 'label': 'Surprise buffer', 'amount_cents': 8000, 'date': None},
        {'kind': 'reserve', 'label': 'Safety cushion', 'amount_cents': 50000, 'date': None},
    ],
    'everyday_cents': 90000, 'buffer_cents': 8000, 'reserve_floor_cents': 50000,
    'free_cents': 246520, 'per_day_cents': 9000, 'extra_cents': 111520, 'basis': {}, 'evidence': {},
}
# Robin: bills before payday exceed the balance.
SHORT = {**LEGACY, 'starting_balance_cents': 31214, 'committed_items': [{'date': '2026-10-01', 'label': 'Housing', 'amount_cents': 85252, 'source': 'recurring', 'transaction_type': 'housing_payment'}],
         'committed_cents': 85252, 'free_cents': -104038, 'spendable_cents': 0, 'shortfall_cents': 104038, 'per_day_cents': 0, 'safe_to_save_cents': 0}


def run_module(body):
    """Run `body` as an ES module with the Home helpers imported from the real file."""
    url = (WEB / 'home-v4.js').resolve().as_uri()
    script = f"import assert from 'node:assert/strict';\nimport * as H from {json.dumps(url)};\n" \
             f"const LEGACY={json.dumps(LEGACY)}, PLAN={json.dumps(PLAN)}, SHORT={json.dumps(SHORT)};\n" + body
    result = subprocess.run(['node', '--input-type=module'], input=script, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise AssertionError(result.stderr[-4000:])
    return result.stdout


class PlanAdapterTests(unittest.TestCase):
    def test_current_shape_uses_the_servers_own_split_without_double_counting(self):
        run_module(r'''
const p=H.normalizePlan(LEGACY);
assert.equal(p.shape,'legacy');assert.equal(p.balance,472358);assert.equal(p.days,22);assert.equal(p.nextPayday,'2026-10-22');
assert.equal(p.heldTotal,64595);assert.equal(p.reserve,50000);
assert.equal(p.extra,229884,'could be saved is what the server says can move to savings');
assert.equal(p.spendable,357763-229884);assert.equal(p.perDay,Math.floor((357763-229884)/22));
const total=H.planSegments(p).reduce((sum,s)=>sum+s.cents,0);assert.equal(total,p.balance,'the bar splits the balance exactly');
assert.equal(Math.round(H.planSegments(p).reduce((sum,s)=>sum+s.share,0)*1000),1000);
assert.deepEqual(p.items.map(i=>i.kind),['bill','bill']);
''')

    def test_spending_plan_shape_is_read_directly(self):
        run_module(r'''
const p=H.normalizePlan(PLAN);
assert.equal(p.shape,'plan');assert.equal(p.perDay,9000,'per day comes from the API');
assert.equal(p.days,15);assert.equal(p.reserve,50000);assert.equal(p.buffer,8000);assert.equal(p.everyday,90000);
assert.equal(p.extra,111520);assert.equal(p.spendable,246520-111520);
assert.deepEqual(p.items.map(i=>i.kind),['bill','loan','tax']);
assert.equal(p.items[1].told,true,'declared items are marked as told by the customer');
assert.equal(p.heldTotal,52838+20000+5000);
const total=H.planSegments(p).reduce((sum,s)=>sum+s.cents,0);assert.equal(total,PLAN.balance_cents);
assert.equal(H.normalizePlan({available:true,safe_to_spend_cents:1}),null,'the old 7-day shape is not a plan');
assert.equal(H.normalizePlan(null),null);
''')

    def test_shortfall_is_reported_and_nothing_is_spendable(self):
        run_module(r'''
const p=H.normalizePlan(SHORT);
assert.equal(p.shortfall,104038);assert.equal(p.spendable,0);assert.equal(p.perDay,0);assert.equal(p.extra,0);
const html=H.planCardHTML(p,{locale:'en'});
assert.match(html,/data-plan-state="short"/);assert.match(html,/hv4-plan-short/,'a calm warning card, not the green one');
assert.match(html,/Before payday you are short<\/span><span class="hv4-hero-amount">€540</,'the headline is the real gap: bills minus balance');
assert.match(html,/Housing €853 is €540 more than the €312 in your account\. Your €500 safety cushion can’t be kept this time\./);
assert.ok(!/a day/.test(html),'no per-day sentence when nothing is spendable');
const segs=H.planSegments(p);assert.deepEqual(segs.map(s=>[s.key,s.cents]),[['covered',31214],['missing',85252-31214]],'the bar never draws more than the balance covers');
assert.match(html,/Can’t be kept this time/);
assert.match(H.planCardHTML(p,{locale:'fi'}),/Turvatyynyäsi \(500\s€\) ei voi pitää/);
''')


class PlanCardTests(unittest.TestCase):
    def test_plan_card_answers_how_much_until_payday_and_why_in_three_languages(self):
        run_module(r'''
const legacy=H.normalizePlan(LEGACY),plan=H.normalizePlan(PLAN);
const en=H.planCardHTML(legacy,{locale:'en'});
assert.match(en,/>€58</);assert.match(en,/a day for food, getting around and fun/);assert.match(en,/Payday in 22 days · Thu, 22 Oct/);
assert.match(en,/Why this number\?/);assert.match(en,/Housing<small>5 Oct/);assert.match(en,/− €528\.38/);
assert.match(en,/Money for daily life until payday/);assert.match(en,/€4,723\.58/);assert.match(en,/€1,279 in total until payday/);
const fi=H.planCardHTML(legacy,{locale:'fi'});
assert.match(fi,/58\s€/);assert.match(fi,/päivässä ruokaan, liikkumiseen ja muuhun/);assert.match(fi,/4\s723,58\s€/);assert.match(fi,/Miksi tämä summa\?/);
const sv=H.planCardHTML(legacy,{locale:'sv'});
assert.match(sv,/om dagen för mat, resor och nöjen/);assert.match(sv,/4\s723,58\s€/);assert.match(sv,/Lönedag om 22 dagar/);
const fromPlan=H.planCardHTML(plan,{locale:'en',label:item=>item.label});
assert.match(fromPlan,/>€90</);assert.match(fromPlan,/Car loan/);assert.match(fromPlan,/You told me/);assert.match(fromPlan,/Tax set-aside/);
assert.match(fromPlan,/Everyday basics €900\.00 \+ free to spend €1,350\.00/);assert.match(fromPlan,/Surprise buffer, this payday/);assert.match(fromPlan,/could be saved/);
assert.match(fromPlan,/€900 \+ €1,350 = €2,250 → about €90 a day/,'the legend parts add up to the daily number');
assert.match(fromPlan,/Safety cushion<\/span><b>€500/);assert.match(fromPlan,/Surprise buffer<\/span><b>€80/);assert.ok(!/>Buffer</.test(fromPlan),'no unnamed buffer');
for(const html of [en,fi,sv,fromPlan])assert.ok(!/demo|scenario|deterministic|reserve floor|quartile|MCC/i.test(html.replace(/hv4-[a-z-]+/g,'')),html);
''')

    def test_plan_card_reflects_the_money_profile(self):
        run_module(r'''
const profile={empty:false,mode:'steady',entries:[{key:'life_event',active:true,value:{type:'job_loss',since:'2026-09-01'}},{key:'saving_rate_target_pct',active:true,value:10}]};
const steady=H.normalizePlan({...LEGACY,steady_mode:true,planned_saving_cents:23649});
const html=H.planCardHTML(steady,{locale:'en',profile});
assert.match(html,/Steady mode is on because you told me about losing your job/);assert.ok(!/Careful/.test(html));
assert.match(html,/Not needed before payday/,'no saving suggestion in steady mode');assert.ok(!/Could be saved/.test(html));
assert.match(html,/Your planned saving, 10% of salary/);assert.match(html,/You told me/);
const fi=H.planCardHTML(steady,{locale:'fi',profile});assert.match(fi,/työpaikan menetys/);assert.match(fi,/Rauhallinen tahti on päällä/);
assert.match(H.planCardHTML(steady,{locale:'sv',profile}),/Lugnt tempo är på/);assert.match(fi,/10\s%/);
assert.match(H.planCardHTML(null,{state:'loading'}),/Working out your plan/);
assert.match(H.planCardHTML(null,{state:'unavailable',locale:'sv'}),/inte tillgänglig/);
''')

    def test_every_message_exists_in_three_languages_without_developer_words(self):
        run_module(r'''
const keys=Object.keys(H.HOME_MESSAGES.en);
for(const l of ['fi','sv']){assert.deepEqual(Object.keys(H.HOME_MESSAGES[l]),keys);}
for(const l of ['en','fi','sv'])for(const k of keys){const v=H.HOME_MESSAGES[l][k];assert.ok(v&&v.trim(),l+' '+k);
  assert.ok(!/deterministic|demo reserve|\bMCC\b|quartile|scenario|provenance|reference day/i.test(v),l+' '+k);}
assert.notEqual(H.HOME_MESSAGES.fi.perDay,H.HOME_MESSAGES.en.perDay);
''')


class InsightAndCardsTests(unittest.TestCase):
    def test_insight_priorities_and_actions(self):
        run_module(r'''
const legacy=H.normalizePlan(LEGACY),buffer=H.bufferPlan({available:true,total_cents:477700,monthly_average_cents:39808,suggested_monthly_set_aside_cents:39808,largest:{amount_cents:48288}});
assert.deepEqual([buffer.monthly,buffer.target,buffer.months],[40000,120000,3]);
let i=H.pickInsight({plan:H.normalizePlan(SHORT),bufferInfo:buffer,locale:'en'});assert.equal(i.kind,'shortfall');
i=H.pickInsight({plan:legacy,profile:{mode:'steady',entries:[]},bufferInfo:buffer,locale:'en'});assert.equal(i.kind,'steady');
i=H.pickInsight({plan:legacy,bufferInfo:buffer,locale:'en'});assert.equal(i.kind,'buffer');
assert.equal(i.chips.length,2);assert.equal(i.chips[0].label,'See the surprise buffer');assert.equal(i.chips[0].attrs['data-home-scroll'],'buffer');
assert.ok(!JSON.stringify(i.chips).includes('€400'),'the €400 ask lives only on the buffer card');
assert.equal(i.chips[1].attrs['data-view'],'trends');
assert.match(H.insightHTML(i),/data-home-scroll="buffer"/);
i=H.pickInsight({plan:legacy,bufferInfo:buffer,hasBufferGoal:true,locale:'fi'});assert.equal(i.kind,'extra');assert.match(i.text,/2\s299\s€/);
assert.equal(i.chips[0].attrs['data-home-goal'],'229884','"Make it a goal" carries the amount to prefill');
const tiles=H.monthTiles({salary_cents:200000,other_income_cents:0,consumption_cents:150000},{salary_cents:200000,other_income_cents:0,consumption_cents:180000});
i=H.pickInsight({plan:{...legacy,extra:0},hasBufferGoal:true,tiles,previousMonth:'2026-08',locale:'en'});assert.equal(i.kind,'spentLess');assert.match(i.text,/€300 less than in August/);
i=H.pickInsight({plan:{...legacy,extra:0},profile:{entries:[{key:'saving_rate_target_pct',value:15}]},hasBufferGoal:true,locale:'sv'});assert.equal(i.kind,'calm');assert.match(i.text,/15\s%/);
''')

    def test_steady_mode_is_reserve_first_and_protected_categories_are_never_suggested(self):
        run_module(r'''
const steadyShort=H.normalizePlan({...SHORT,steady_mode:true});
let i=H.pickInsight({plan:steadyShort,locale:'en'});assert.equal(i.kind,'steady','careful mode wins over the shortfall message');
assert.match(i.text,/safety cushion comes first/);assert.ok('data-home-why' in i.chips[1].attrs);
assert.match(H.pickInsight({plan:steadyShort,locale:'fi'}).text,/Turvatyyny on nyt etusijalla/);
const rows=[{role:'discretionary',category:'Restaurants',amount_cents:-30000},{role:'discretionary',category:'Restaurants',amount_cents:-9000},
  {role:'discretionary',category:'Entertainment',amount_cents:-25000},{role:'fixed_obligation',category:'Housing',amount_cents:-90000}];
assert.deepEqual(H.topFlexibleCategory(rows),{category:'Restaurants',cents:39000});
const server={entries:[{key:'protected_categories',active:true,value:['Restaurants']}]};
assert.deepEqual(H.topFlexibleCategory(rows,H.protectedCategories(server)),{category:'Entertainment',cents:25000});
assert.equal(H.topFlexibleCategory(rows,H.protectedCategories(server,'Entertainment')),null,'local preference is honoured too');
const tiles=H.monthTiles({salary_cents:200000,other_income_cents:0,consumption_cents:190000},{salary_cents:200000,other_income_cents:0,consumption_cents:150000});
const plan={...H.normalizePlan(LEGACY),extra:0};
i=H.pickInsight({plan,hasBufferGoal:true,tiles,previousMonth:'2026-08',topCategory:H.topFlexibleCategory(rows,H.protectedCategories(server)),locale:'en'});
assert.equal(i.kind,'spentMore');assert.match(i.text,/€400 more than in August\. Entertainment was your biggest everyday extra this month, €250\./);
assert.ok(!/Restaurants/.test(JSON.stringify(i)),'a protected category is never suggested');
assert.match(i.chips[0].attrs['data-direct-question'],/Entertainment/);
''')

    def test_month_buffer_goals_and_personal_cards(self):
        run_module(r'''
const tiles=H.monthTiles({salary_cents:244781,other_income_cents:0,consumption_cents:187866},{salary_cents:240831,other_income_cents:0,consumption_cents:254189});
assert.deepEqual(tiles.map(t=>[t.key,t.cents,t.delta]),[['in',244781,3950],['out',187866,-66323],['left',56915,70273]]);
const month=H.monthHTML(tiles,{locale:'en',previousMonth:'2026-08',month:'2026-09'});
assert.match(month,/Money in/);assert.match(month,/Left over/);assert.match(month,/€663 vs Aug/);assert.match(month,/hv4-delta-good/);
assert.equal((month.match(/€2,448/g)||[]).length,1,'each figure appears once');
const info=H.bufferPlan({available:true,total_cents:172800,monthly_average_cents:14400,largest:{amount_cents:21300}});
assert.match(H.bufferHTML(info,null,{locale:'en',readyBy:'2026-12-31'}),/Set aside €150 monthly/);
assert.match(H.bufferHTML(info,null,{locale:'en',tight:true}),/once the bills before payday are covered/);
const goal={id:'g1',name:'Surprise buffer',template:'buffer',target_cents:120000,current_saved_cents:30000,required_monthly_cents:30000,target_date:'2026-12-31'};
const card=H.bufferHTML(info,goal,{locale:'en'});assert.match(card,/€300 of €1,200/);assert.match(card,/aria-valuenow="25"/);assert.match(card,/data-goal-edit="g1"/);
const goals=H.goalsHTML([goal,{id:'g2',name:'A summer in Italy',target_cents:300000,current_saved_cents:0,target_date:'2027-03-31',required_monthly_cents:50000,template:'custom'}],[{title:'A calmer December'}],{locale:'en'});
assert.match(goals,/A summer in Italy/);assert.match(goals,/Surprise buffer<small class="hv4-on">On<\/small><\/span><span class="hv4-goal-meta">About €300 a month/,'the buffer plan is listed');assert.match(goals,/A calmer December/);assert.match(goals,/€500 a month/);
assert.match(H.goalsHTML([],[],{locale:'fi'}),/Aloita tavoite/);
assert.match(H.personalHTML({empty:true,entries:[]},{locale:'en'}),/data-home-intro/);
assert.match(H.personalHTML({empty:true,entries:[]},{locale:'sv'}),/Berätta om dig för coachen/);
const known=H.personalHTML({empty:false,entries:[{key:'income_stability',value:'steady'},{key:'note',value:'x'}]},{locale:'en'});
assert.match(known,/knows 2 things/);assert.match(known,/data-view="profile"/);assert.match(known,/data-open-notebook/);
''')


# Kai after "I lost my job": rent is covered, but the steady-mode cushion (a month of must-pays) is not.
KAI_STEADY = {
    'as_of': '2026-09-30', 'balance_cents': 178094, 'next_payday': '2026-10-15', 'days_to_payday': 15, 'steady_mode': True,
    'held_back': [
        {'kind': 'bill', 'label': 'Rent', 'labels': {'en': 'Rent', 'fi': 'Vuokra', 'sv': 'Hyra'}, 'amount_cents': 97526, 'date': '2026-10-04'},
        {'kind': 'buffer', 'label': 'Surprise costs', 'amount_cents': 2205},
        {'kind': 'reserve', 'key': 'steady_reserve', 'label': 'A month of must-pays', 'amount_cents': 163897},
    ],
    'everyday_cents': 11001, 'buffer_cents': 2205, 'reserve_floor_cents': 163897, 'free_cents': 0, 'shortfall_cents': 96535,
    'spendable_cents': 0, 'per_day_cents': 0, 'extra_cents': 0,
}
KAI_JS = 'const KAI=' + json.dumps(KAI_STEADY) + ';\n'


class V5FixHomeTests(unittest.TestCase):
    """V5 fix wave, lane HM: consistent sums, buffer names, shortfall and steady states, plans in the summary."""

    def test_daily_parts_always_add_up_in_whole_euros(self):
        run_module(r'''
for(const [everyday,free] of [[31145,26566],[18989,35302],[150,150],[0,26566],[99950,50]]){
  const parts=H.dailyParts({everyday,spendable:free});
  assert.equal(parts.everyday+parts.free,parts.total);assert.equal(parts.total,Math.round((everyday+free)/100)*100);
}
''')

    def test_bills_covered_but_cushion_not_is_a_calm_tight_state_that_names_the_cause(self):
        run_module(KAI_JS + r'''
const p=H.normalizePlan(KAI);const status=H.planStatus(p);
assert.deepEqual([status.state,status.billsGap,status.left],['tight',0,178094-97526]);
const html=H.planCardHTML(p,{locale:'en',profile:{entries:[{key:'life_event',active:true,value:{type:'job_loss',since:'2026-09-01'}}]}});
assert.match(html,/hv4-plan-short/);assert.match(html,/Left after bills until payday<\/span><span class="hv4-hero-amount">€806</);
assert.match(html,/Your bills before payday are covered\. Steady mode keeps a month of must-pays \(€1,639\) as your safety cushion\. The €806 left doesn’t reach it yet/);
assert.ok(!/more than you have free/.test(html),'bills are not blamed for a cushion gap');
assert.ok(!/\bsav(e|ed|ing)\b/i.test(html.replace(/<[^>]+>/g,' ')),'no saving suggestion in steady mode');
assert.match(html,/Not fully covered this time/);
const total=H.planSegments(p).reduce((sum,s)=>sum+s.cents,0);assert.equal(total,KAI.balance_cents,'the bar splits the balance');
assert.match(H.planCardHTML(p,{locale:'fi'}),/Rauhallinen tahti pitää kuukauden/);
assert.match(H.planCardHTML(p,{locale:'sv'}),/Lugnt tempo håller en månads/);
''')

    def test_steady_mode_has_no_saving_asks_on_the_buffer_card(self):
        run_module(KAI_JS + r'''
const info=H.bufferPlan({available:true,total_cents:172800,monthly_average_cents:14400,largest:{amount_cents:21300}});
const html=H.bufferHTML(info,null,{locale:'en',readyBy:'2027-01-31',steady:true});
assert.match(html,/Steady mode is on, so I’m not suggesting new saving/);
assert.ok(!/a month, ready by|Set aside|data-home-buffer/.test(html),'no pace and no set-aside button in steady mode');
const goal={id:'g1',template:'buffer',target_cents:120000,current_saved_cents:0,required_monthly_cents:40000,target_date:'2026-12-31'};
const paused=H.bufferHTML(info,goal,{locale:'sv',steady:true});assert.match(paused,/Pausad medan lugnt tempo är på/);assert.ok(!/varje lönedag/.test(paused));
assert.equal(H.pickInsight({plan:H.normalizePlan(KAI),bufferInfo:info,locale:'en'}).kind,'steady');
''')

    def test_saved_buffer_plan_is_shown_only_when_the_payday_plan_holds_it_back(self):
        run_module(r'''
const info=H.bufferPlan({available:true,total_cents:477700,monthly_average_cents:39808,largest:{amount_cents:48288}});
const goal={id:'g1',template:'buffer',target_cents:120000,current_saved_cents:0,required_monthly_cents:40000,target_date:'2026-12-31'};
assert.ok(!/Held back this payday/.test(H.bufferHTML(info,goal,{locale:'en',heldNow:20458})),'no claim that contradicts the €400 plan');
assert.match(H.bufferHTML(info,goal,{locale:'en',heldNow:40000}),/Held back this payday: €400/);
const plan=H.normalizePlan({...PLAN,held_back:[...PLAN.held_back.filter(i=>i.kind!=='buffer'),{kind:'goal',template:'buffer',label:'Surprise buffer',amount_cents:40000}],buffer_cents:0});
assert.equal(plan.buffer,40000);assert.equal(plan.bufferFromPlan,true);assert.ok(!plan.items.some(i=>i.kind==='goal'));
assert.match(H.planCardHTML(plan,{locale:'en'}),/Surprise buffer, your plan/);
const noGoal=H.bufferHTML(info,null,{locale:'en',readyBy:'2026-12-31',heldNow:20458});
assert.match(noGoal,/already holds back €205 for surprise costs/);assert.match(noGoal,/Suggested target/);assert.equal((noGoal.match(/€400/g)||[]).length,2,'pace and the one button');
''')

    def test_goals_and_plans_lists_active_mortgage_and_tax_plans(self):
        run_module(r'''
const plans=[{id:'mortgage',on:true,monthly_cents:109921},{id:'tax',on:true,monthly_cents:5250}];
const html=H.goalsHTML([],[],{locale:'en',plans});
assert.match(html,/Mortgage plan/);assert.match(html,/About €1,099 a month held back/);assert.match(html,/Tax plan/);assert.match(html,/About €53 a month held back/);
assert.ok(!/Nothing planned yet/.test(html));
assert.match(H.goalsHTML([],[],{locale:'fi',plans}),/Asuntolainasuunnitelma/);
assert.match(H.goalsHTML([],[],{locale:'en',plans:[{id:'mortgage',on:false}]}),/Nothing planned yet/);
''')

    def test_localized_bill_labels_and_vocabulary(self):
        run_module(KAI_JS + r'''
const p=H.normalizePlan(KAI);
assert.deepEqual(p.items[0].labels,{en:'Rent',fi:'Vuokra',sv:'Hyra'});
for(const l of ['en','fi','sv'])for(const [k,v] of Object.entries(H.HOME_MESSAGES[l]))
  assert.ok(!/Careful|Varovainen|Försiktig|Överrask|överrask|Puskurirahasto|jmf\./.test(v),l+' '+k+': '+v);
assert.match(H.monthHTML([{key:'in',cents:100,delta:10,good:1}],{locale:'sv',previousMonth:'2026-08'}),/jfr aug/);
assert.match(H.monthHTML([{key:'left',cents:-42600,delta:null,good:1}],{locale:'en'}),/<b>\u2212€426<\/b>/,'a typographic minus with no gap');
''')


HOME_SETUP = r'''
const legacyPlan=%s, newPlan=%s;
let safeShape=legacyPlan;
const baseFixture=fixture;
fixture=(path,customer)=>path==='/api/safe-to-spend'?{customer_id:customer,...safeShape}
  :path==='/api/spender-profile'?{buffer:{available:true,total_cents:477700,monthly_average_cents:39808,suggested_monthly_set_aside_cents:39808,largest:{amount_cents:48288,category:'Health',date:'2026-02-26'}}}
  :path==='/api/profile'?{profile:{empty:true,entries:[],mode:'normal'},suggestions:[]}
  :path==='/api/overview'?{...baseFixture(path,customer),salary_cents:244781,other_income_cents:0,consumption_cents:187866,committed_saving_transfers_cents:23572}
  :baseFixture(path,customer);
''' % (json.dumps(LEGACY), json.dumps(PLAN))


class HomeAppTests(unittest.TestCase):
    read = contracts.WebContractTests.read
    node_app = contracts.WebContractTests.node_app

    def test_home_renders_the_plan_from_both_api_shapes(self):
        self.node_app(HOME_SETUP + r'''
await app.load();await settle();
assert.match(get('home-v4-plan').innerHTML,/>€58</);assert.match(get('home-v4-plan').innerHTML,/Payday in 22 days/);
assert.match(get('home-v4-insight').innerHTML,/See the surprise buffer/);
assert.match(get('home-v4-month').innerHTML,/Left over/);
assert.match(get('home-v4-personal').innerHTML,/Tell the coach about you/);
assert.match(get('home-v4-buffer').innerHTML,/Set aside €400 monthly/);
const sent=calls.find(call=>call.path==='/api/safe-to-spend');assert.equal(sent.query.horizon,'until_payday');
safeShape=newPlan;await app.load();await settle();
assert.match(get('home-v4-plan').innerHTML,/>€90</);assert.match(get('home-v4-plan').innerHTML,/Car loan/);
''')

    def test_failed_plan_says_so_instead_of_loading_forever(self):
        self.node_app(HOME_SETUP + r'''
safeShape={available:false};await app.load();await settle();
assert.match(get('home-v4-plan').innerHTML,/not available right now/);
''')

    def test_buffer_action_opens_a_confirm_card_and_never_saves_silently(self):
        self.node_app(HOME_SETUP + r'''
await app.load();await settle();calls.length=0;
get('v3-dialog-content').querySelectorAll=()=>[];
const chip=new Element('chip');chip.dataset.homeBuffer='';
await documentListeners.click({target:chip});await settle();
assert.equal(get('v3-dialog').open,true,'a review card opens');
assert.match(get('v3-dialog-content').innerHTML,/Start your surprise buffer/);
assert.match(get('v3-dialog-content').innerHTML,/No money moves from your account/);
assert.equal(calls.filter(call=>call.method==='POST').length,0,'nothing is saved before the customer confirms');
''')

    def test_language_switch_and_intro_entry(self):
        self.node_app(HOME_SETUP + r'''
await app.load();await settle();
get('language').value='fi';get('language').listeners.change();await settle();
const html=get('home-v4-plan').innerHTML;
assert.match(html,/päivässä ruokaan, liikkumiseen ja muuhun/);assert.match(html,/4\s723,58\s€/);
const intro=new Element('intro');intro.dataset.homeIntro='';
await documentListeners.click({target:intro});await settle();
assert.equal(app.state.view,'coach','the intro opens the coach');
''')


if __name__ == '__main__':
    unittest.main()
