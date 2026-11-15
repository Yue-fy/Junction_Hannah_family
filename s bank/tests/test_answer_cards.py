"""V4 lane U: answer cards, catalogue-driven Coach empty state, topic menu and quick-answers fallback.

Lane C's endpoints (GET /api/catalogue, POST /api/catalogue/answer, catalogue fallback from /api/agent) are mocked
here strictly from the contract in docs/V4_SPEC.md; nothing in web/ ships a mock.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

import test_web_contract

WEB = Path(__file__).resolve().parents[1] / 'web'

CARD = {
    'question_id': 'spend.cut', 'title': 'If you cut Restaurants',
    'headline': {'label': 'a month, from €225.70 spent in September', 'value_text': '€45.14', 'value_cents': 4514},
    'lines': ['That is about €541.68 a year.', 'Groceries stay as they are.', 'Line three <b>bold</b>', 'Line four', 'Line five is dropped'],
    'chart': {'kind': 'bars', 'data': [{'label': 'Now', 'value_cents': 22570}, {'label': 'After', 'value_cents': 18056}]},
    'caveat': 'An estimate from last month.',
    'evidence': [{'label': 'See 10 restaurant payments', 'query': {'category': 'Restaurants', 'month': '2026-09'}}],
    'followups': [{'id': 'goals.new', 'text': 'Save this towards a goal'}, {'id': 'money.leaks', 'text': 'What are my Little leaks?'}],
    'pickers': [{'name': 'category', 'kind': 'category', 'value': 'Restaurants', 'options': [{'value': 'Restaurants', 'label': 'Restaurants'}, {'value': 'Groceries', 'label': 'Groceries'}]},
                {'name': 'percent', 'kind': 'percent', 'value': 20}],
    'params_used': {'category': 'Restaurants', 'percent': 20},
}
CATALOGUE = {
    'groups': [
        {'id': 'money', 'title': 'Where my money goes', 'questions': [{'id': 'money.month', 'text': 'Where did my money go this month?'}, {'id': 'money.leaks', 'text': 'What are my Little leaks?'}]},
        {'id': 'room', 'title': 'Safe & save', 'questions': [{'id': 'room.payday', 'text': 'What can I safely spend until payday?'}, {'id': 'spend.cut', 'text': 'What if I cut a category?'}]},
    ],
    'starters': ['money.month', 'room.payday', 'unknown.id'],
}


def run_modules(test, body):
    """Import web modules with their relative imports resolved, then run body (assert is available)."""
    if not shutil.which('node'):
        test.skipTest('Node is not installed')
    sources = {path.name: path.read_text() for path in WEB.glob('*.js')}
    script = 'const sources=' + json.dumps(sources) + r''';
import assert from 'node:assert/strict';
const dataURL=source=>'data:text/javascript;base64,'+Buffer.from(source).toString('base64');
const resolved=new Map();
const resolveModule=file=>{if(!resolved.has(file))resolved.set(file,dataURL(sources[file].replace(/from ['"]\.\/([^'"]+)['"]/g,(_,name)=>'from "'+resolveModule(name)+'"')));return resolved.get(file);};
const cards=await import(resolveModule('answer-card.js'));
const topics=await import(resolveModule('topic-menu.js'));
const chat=await import(resolveModule('coach-chat.js'));
const CARD=''' + json.dumps(CARD) + ''';
const CATALOGUE=''' + json.dumps(CATALOGUE) + ''';
''' + body
    result = subprocess.run(['node', '--input-type=module'], input=script, capture_output=True, text=True, timeout=30)
    test.assertEqual(result.returncode, 0, result.stderr[-4000:])


class AnswerCardRenderTests(unittest.TestCase):
    def test_card_shows_headline_four_lines_chart_pickers_evidence_and_followups(self):
        run_modules(self, r'''
const html=cards.renderCard(CARD,{locale:'en',turnId:'7',index:0});
assert.ok(html.includes('class="answer-card__value">€45.14<'));
assert.ok(html.includes('a month, from €225.70 spent in September'));
assert.equal((html.match(/answer-card__lines">(.*?)<\/ul>/)[1].match(/<li>/g)||[]).length,4,'at most four lines');
assert.ok(!html.includes('Line five'));
assert.ok(html.includes('Line three &lt;b&gt;bold&lt;/b&gt;'),'server text is escaped');
assert.ok(html.includes('<figure class="answer-card__chart"><ul class="card-bars">')&&html.includes('€225.70')&&html.includes('€180.56'),'bars are a compact list with locale money');
assert.ok(cards.renderCard(CARD,{locale:'fi'}).includes('225,70\u00a0€'),'FI money format in bars');
assert.ok(html.includes('An estimate from last month.'));
assert.ok(/<select id="card-7-0-category" data-card-picker="category" data-card-kind="category" data-card-turn="7" data-card-index="0">/.test(html));
assert.ok(html.includes('<option value="Restaurants" selected>Restaurants</option>'));
assert.ok(html.includes('<option value="20" selected>20%</option>'),'percent picker gets default options');
assert.ok(html.includes('data-card-evidence="7" data-card-index="0" data-index="0">See 10 restaurant payments'));
assert.ok(html.includes('data-catalogue-question="goals.new" data-catalogue-text="Save this towards a goal"'));
assert.ok(!html.includes('↗'),'in-app links use a chevron');
const old=cards.renderCard(CARD,{locale:'en',turnId:'7',latest:false});
assert.ok(!old.includes('data-catalogue-question'),'only the latest turn offers follow-up chips');
''')

    def test_card_localizes_ui_labels_and_shows_what_the_customer_told_us(self):
        run_modules(self, r'''
const fi=cards.renderCard({...CARD,profile_note:'Käytin kertomaasi: olet perhevapaalla.'},{locale:'fi',turnId:'1'});
assert.ok(fi.includes('<option value="20" selected>20 %</option>'),'FI percent format');
// V5 fix (lane CO): the server's profile_note is a full sentence and is shown once, with no second prefix.
assert.ok(fi.includes('>Käytin kertomaasi: olet perhevapaalla.</p>'));assert.ok(!fi.includes('Käytän sitä'));
const sv=cards.renderCard({...CARD,using_profile:['du har två barn','lön den 15:e']},{locale:'sv'});
assert.ok(sv.includes('Jag använder det du berättade: du har två barn · lön den 15:e'));
const en=cards.renderCard({...CARD,profile_note:'Using what you told me: steady mode (lost your job).'},{locale:'en'});
assert.equal((en.match(/Using what you told me/g)||[]).length,1,'the prefix appears once');
assert.ok(!cards.renderCard(CARD,{locale:'en'}).includes('answer-card__profile'),'no profile line unless the server sends one');
const amount=cards.renderCard({...CARD,pickers:[{name:'target',kind:'amount',value:200000},{name:'by',kind:'date',value:'2027-06-30'},{name:'month',kind:'month',value:'2026-09',options:['2026-08','2026-09']}]},{locale:'en',turnId:'2',monthLabel:m=>'M'+m});
assert.ok(amount.includes('type="number"')&&amount.includes('value="2000"'),'amount picker shows euros');
assert.ok(amount.includes('type="date" value="2027-06-30"'));
assert.ok(amount.includes('<option value="2026-09" selected>M2026-09</option>'));
''')

    def test_invalid_cards_and_charts_fail_safe(self):
        run_modules(self, r'''
assert.equal(cards.renderCard(null),'');assert.equal(cards.renderCard({lines:['x']}),'');
const bare=cards.renderCard({title:'Only a title',headline:{label:'',value_text:''},chart:{kind:'bars',data:'nonsense'},pickers:[{name:'x',kind:'weird'}],evidence:[{label:'no query'}],followups:[{id:'',text:'x'}]});
assert.ok(bare.includes('Only a title'));
for(const part of ['<figure','<select','data-card-evidence','data-catalogue-question','answer-card__headline'])assert.ok(!bare.includes(part),part);
assert.ok(cards.chartHTML({kind:'progress',data:{current_cents:50000,target_cents:200000}}).includes('class="goal-progress"'),'progress is the HTML goal bar (V5 lane GL)');
assert.ok(cards.chartHTML({kind:'trend',data:{series:[{label:'Aug',value_cents:1},{label:'Sep',value_cents:2}]}}).includes('<svg'));
// V5 fix (lane CO): parts of a whole are one labelled bar with a legend; a single part (e.g. all held back, €0 free) shows no chart.
assert.equal(cards.chartHTML({kind:'ring',data:[{label:'Held back',value_cents:263628},{label:'For daily life',value_cents:0}]}),'');
const split=cards.chartHTML({kind:'ring',data:[{label:'Held back',value_cents:123296,value_text:'€1,232.96'},{label:'For daily life until payday',value_cents:57711,value_text:'€577.11'},{label:'Could be saved',value_cents:291351,value_text:'€2,913.51'}]});
assert.ok(split.includes('card-split__bar')&&!split.includes('<svg'));
for(const text of ['Held back','€1,232.96','For daily life until payday','€577.11','Could be saved','€2,913.51'])assert.ok(split.includes(text),text);
assert.ok(cards.renderCard({...CARD,lines:['Bills and must-pays used']}).includes('must\u2011pays'),'short hyphenated words do not break');
assert.equal(cards.chartHTML({kind:'progress',data:{current_cents:5}}),'');
assert.deepEqual(cards.cardSummary(CARD).slice(0,2),['If you cut Restaurants','€45.14 a month, from €225.70 spent in September']);
''')

    def test_quick_answers_turn_is_honest_localized_and_offers_three_chips(self):
        run_modules(self, r'''
const suggestions=[{id:'room.payday',text:'What can I safely spend until payday?'},{id:'room.buffer',text:'How big should my buffer be?'},{id:'me.life',text:'Tell the coach about a life change'},{id:'x',text:'Fourth'}];
const turn={id:'4',message:'I lost my job',response:{source:'catalogue',fallback_reason:'model_unavailable',supportive:'I’m sorry, that is a lot to deal with.',suggestions,cards:[]}};
const html=cards.catalogueTurnHTML(turn,{locale:'en',latest:true,retryLabel:'Try again with the AI coach'});
assert.ok(html.includes('Quick answers – here are the closest questions I can answer exactly.'));
assert.ok(html.includes('I’m sorry, that is a lot to deal with.'));
assert.equal((html.match(/data-catalogue-question=/g)||[]).length,3);
assert.ok(html.includes('data-retry-agent="4">Try again with the AI coach ↻'));
assert.ok(!cards.catalogueTurnHTML(turn,{locale:'en',latest:false,retryLabel:'Retry'}).includes('data-retry-agent'));
assert.ok(cards.catalogueTurnHTML(turn,{locale:'fi',latest:true}).includes('Pikavastaukset – tässä lähimmät kysymykset'));
assert.ok(cards.catalogueTurnHTML(turn,{locale:'sv',latest:true}).includes('Snabbsvar – här är de närmaste frågorna'));
assert.ok(!cards.catalogueTurnHTML({...turn,response:{...turn.response,fallback_reason:'not_configured'}},{locale:'en',latest:true,retryLabel:'Retry'}).includes('data-retry-agent'),'no retry when no AI is configured');
for(const locale of ['en','fi','sv'])assert.ok(cards.introChipHTML(locale).includes('data-open-intro')&&cards.introChipHTML(locale).includes('data-dismiss-intro'));
assert.ok(cards.introChipHTML('fi').includes('Kerro itsestäsi (1 min)'));
const withCard=cards.catalogueTurnHTML({id:'5',message:'where did my money go',response:{source:'catalogue',suggestions:[],cards:[CARD]}},{locale:'en',latest:true});
// V5 fix (lane CO): a confident match is answered directly: the card, no notice, no chips above it.
assert.ok(!withCard.includes('quick-notice')&&!withCard.includes('Quick answers')&&withCard.includes('€45.14'));
''')

    def test_catalogue_normalizes_and_drives_the_topic_menu(self):
        run_modules(self, r'''
const data=cards.normalizeCatalogue(CATALOGUE);
assert.deepEqual(data.starters.map(q=>q.id),['money.month','room.payday']);
assert.equal(cards.normalizeCatalogue({groups:[]}),null);assert.equal(cards.normalizeCatalogue(null),null);
assert.deepEqual(cards.normalizeCatalogue({groups:CATALOGUE.groups}).starters.map(q=>q.id),['money.month','room.payday']);
const sheet=topics.renderTopicSheet('en',{catalogue:data});
assert.ok(sheet.includes('Safe &amp; save')&&sheet.includes('data-catalogue-id="spend.cut"'));
assert.ok(!sheet.includes('Bills &amp; debts'),'server groups replace the built-in list');
assert.ok(topics.renderTopicSheet('en').includes('Bills &amp; debts'),'built-in list stays the fallback');
const target={closest:sel=>sel==='[data-topic-question]'?{getAttribute:name=>({'data-topic-question':'What if I cut a category?','data-catalogue-id':'spend.cut'})[name]??null}:null};
assert.deepEqual(topics.topicAction(target),{action:'ask',text:'What if I cut a category?',id:'spend.cut'});
''')

    def test_ai_answer_renders_lead_and_the_same_cards(self):
        run_modules(self, r'''
const turn={id:'9',message:'Where did my money go?',response:{source:'agent',answer:['September was calmer than August.'],highlight:{label:'Spent',value:'€1,878.66',caption:'x'},
  chart:{kind:'bar',title:'t',series:[{label:'a',value_cents:1}]},cards:[CARD],suggestions:['Agent suggestion']}};
const html=chat.agentTurnHTML(turn,{esc:s=>String(s),t:k=>k,charts:{barChart:()=>'<svg id="old"/>',trendChart:()=>'',runwayChart:()=>''},flowName:x=>x,latest:true,locale:'en'});
assert.ok(html.includes('September was calmer than August.')&&html.includes('answer-card__value">€45.14<'));
assert.ok(!html.includes('agent-highlight')&&!html.includes('id="old"'),'cards replace the separate highlight and chart');
assert.ok(html.includes('data-catalogue-question="goals.new"')&&!html.includes('Agent suggestion'));
const plain=chat.agentTurnHTML({...turn,response:{...turn.response,cards:undefined}},{esc:s=>String(s),t:k=>k,charts:{barChart:()=>'<svg id="old"/>',trendChart:()=>'',runwayChart:()=>''},flowName:x=>x,latest:true});
assert.ok(plain.includes('agent-highlight')&&plain.includes('Agent suggestion'),'answers without cards are unchanged');
''')


class CoachCatalogueAppTests(unittest.TestCase):
    read = test_web_contract.WebContractTests.read
    node_app = test_web_contract.WebContractTests.node_app

    PRELUDE = r'''
const CARD=''' + json.dumps(CARD) + ''';
const CATALOGUE=''' + json.dumps(CATALOGUE) + r''';
const baseFetch=globalThis.fetch;let catalogueUp=true,agentReply=null,profileEmpty=true;
globalThis.fetch=async(url,options)=>{
 const parsed=new URL(url,'http://local'),path=parsed.pathname,body=options.body?JSON.parse(options.body):{};
 const reply=data=>{calls.push({path,method:options.method,customer:body.customer_id||parsed.searchParams.get('customer_id'),body,query:Object.fromEntries(parsed.searchParams)});return {ok:true,json:async()=>({ok:true,data})};};
 if(path==='/api/catalogue'){if(!catalogueUp){calls.push({path,query:Object.fromEntries(parsed.searchParams)});return {ok:false,status:404,json:async()=>({ok:false,error:{message:'Not found'}})};}return reply(CATALOGUE);}
 if(path==='/api/catalogue/answer'){if(!catalogueUp){calls.push({path,body});return {ok:false,status:404,json:async()=>({ok:false,error:{message:'Not found'}})};}
   const percent=body.params?.percent??20;return reply({card:{...CARD,question_id:body.question_id,headline:{...CARD.headline,value_text:percent===30?'€67.71':'€45.14'},params_used:{...CARD.params_used,...(body.params||{})}}});}
 if(path==='/api/agent'&&agentReply)return reply(agentReply);
 if(path==='/api/profile')return reply({profile:{empty:profileEmpty,entries:[]},suggestions:[]});
 return baseFetch(url,options);
};
const button=dataset=>{const node=document.createElement('button');node.dataset=dataset;return node;};
const click=async dataset=>{documentListeners.click({target:button(dataset)});await settle();};
const openCoach=async()=>{await click({view:'coach'});await settle();};
'''

    def test_coach_opens_into_chat_with_catalogue_starters_and_intro_chip(self):
        self.node_app(self.PRELUDE + r'''
calls.length=0;await openCoach();
assert.equal(app.state.view,'coach');
assert.ok(!get('onboarding-root').innerHTML.includes('data-onboarding-step'),'the intro must not open by itself');
const catalogueCall=calls.find(c=>c.path==='/api/catalogue');assert.ok(catalogueCall,'empty state loads the catalogue');assert.equal(catalogueCall.query.locale,'en');
const starters=get('coach-starters').innerHTML;
assert.ok(starters.includes('data-catalogue-question="money.month"')&&starters.includes('What can I safely spend until payday?'));
assert.ok(get('topic-menu-root').innerHTML.includes('data-catalogue-id="spend.cut"'),'topic menu shows the server catalogue');
assert.ok(get('coach-intro-chip').innerHTML.includes('Tell me about you (1 min)'));
const intro=new Element();intro.attributes={'data-open-intro':''};intro.dataset={};documentListeners.click({target:intro});await settle();
assert.ok(get('onboarding-root').innerHTML.includes('data-onboarding-step'),'the chip opens the intro on request');
const hide=new Element();hide.attributes={'data-dismiss-intro':''};hide.dataset={};documentListeners.click({target:hide});await settle();
assert.equal(get('coach-intro-chip').innerHTML,'','the chip can be dismissed');
''')

    def test_tapping_a_question_renders_an_instant_card_without_the_ai(self):
        self.node_app(self.PRELUDE + r'''
await openCoach();calls.length=0;
await click({catalogueQuestion:'spend.cut',catalogueText:'What if I cut a category?'});
const answer=calls.find(c=>c.path==='/api/catalogue/answer');
assert.ok(answer);assert.equal(answer.body.question_id,'spend.cut');assert.equal(answer.body.locale,'en');
assert.equal(answer.query.customer_id,'CUST00001');assert.equal(answer.query.month,'2026-09');
assert.equal(calls.filter(c=>c.path==='/api/agent'||c.path==='/api/coach').length,0,'no AI call for a catalogue tap');
const html=get('coach-response').innerHTML;
assert.ok(html.includes('What if I cut a category?')&&html.includes('€45.14')&&html.includes('If you cut Restaurants'));
assert.equal(app.state.conversation.at(-1).response.source,'catalogue_card');
assert.ok(get('coach-empty').hidden);assert.equal(get('coach-mode').textContent,'Numbers come from your account. Nothing changes without your OK.','the footer never changes');
// A picker re-asks the same question with the changed parameter and replaces the card in place.
const turn=app.state.conversation.at(-1);calls.length=0;
const picker=new Element();picker.dataset={cardPicker:'percent',cardKind:'percent',cardTurn:turn.id,cardIndex:'0'};picker.value='30';
documentListeners.change({target:picker});await settle();
const again=calls.find(c=>c.path==='/api/catalogue/answer');
assert.deepEqual(again.body.params,{category:'Restaurants',percent:30});
assert.equal(app.state.conversation.length,1,'the card is replaced, not appended');
assert.ok(get('coach-response').innerHTML.includes('€67.71')&&!get('coach-response').innerHTML.includes('€45.14'));
// Evidence opens the existing transactions dialog with the card's query.
calls.length=0;await click({cardEvidence:turn.id,cardIndex:'0',index:'0'});
const rows=calls.find(c=>c.path==='/api/transactions');assert.ok(rows,'evidence opens transactions');assert.equal(rows.query.category,'Restaurants');
assert.ok(get('transactions-dialog').open);
// History sent to the AI later carries the card summary, not an empty coach turn.
get('transactions-dialog').close();calls.length=0;await app.askCoach('Why is that?');
const history=calls.find(c=>c.path==='/api/agent').body.history;
assert.ok(history.some(item=>item.role==='coach'&&item.text.includes('€67.71')));
''')

    def test_typed_text_without_ai_shows_quick_answers_notice_chips_and_retry(self):
        self.node_app(self.PRELUDE + r'''
await openCoach();calls.length=0;
agentReply={source:'catalogue',fallback_reason:'model_unavailable',supportive:'I’m sorry. Let’s look at what is coming up first.',
 suggestions:[{id:'room.payday',text:'What can I safely spend until payday?'},{id:'me.life',text:'Tell the coach about a life change'}],intent_hint:'life_event',card:null};
await app.askCoach('I lost my job');
assert.equal(calls.filter(c=>c.path==='/api/coach').length,0,'the old regex coach is not used');
const html=get('coach-response').innerHTML;
assert.ok(html.includes('Quick answers – here are the closest'));assert.ok(html.includes('I’m sorry. Let’s look at what is coming up first.'));
assert.ok(html.includes('data-catalogue-question="me.life"'));assert.ok(html.includes('data-retry-agent="'));
assert.ok(!html.includes('Did this help?'));
// Retrying with the AI replaces the quick answer with the AI's answer and its cards.
agentReply={source:'agent',answer:['Here is what you can spend.'],cards:[CARD],steps:[],evidence:[],actions:[],suggestions:[]};
const turn=app.state.conversation.at(-1);await click({retryAgent:turn.id});
assert.equal(app.state.conversation.length,1);
const after=get('coach-response').innerHTML;
assert.ok(after.includes('Here is what you can spend.')&&after.includes('€45.14')&&!after.includes('quick-notice'));
''')

    def test_finnish_catalogue_and_fallback_when_catalogue_is_missing(self):
        self.node_app(self.PRELUDE + r'''
calls.length=0;get('language').value='fi';get('language').listeners.change();await settle();await openCoach();
assert.equal(calls.find(c=>c.path==='/api/catalogue').query.locale,'fi');
assert.ok(get('coach-intro-chip').innerHTML.includes('Kerro itsestäsi'));
agentReply={source:'catalogue',fallback_reason:'model_unavailable',supportive:null,suggestions:[],card:null};
await app.askCoach('mitä kuuluu');
assert.ok(get('coach-response').innerHTML.includes('Valitse kysymys aiheista'),'no suggestions: one line pointing to the topics');
// Without lane C's endpoints the built-in starters stay and a catalogue tap still gets an answer.
catalogueUp=false;agentReply=null;const fresh=new Element();fresh.attributes={'data-new-conversation':''};fresh.dataset={};documentListeners.click({target:fresh});await settle();
get('language').value='en';get('language').listeners.change();await settle();await openCoach();
assert.ok(get('coach-starters').innerHTML.includes('data-coach-question="agent.starter.where"'),'built-in starters when the catalogue fails');
assert.ok(!get('topic-menu-root').innerHTML.includes('data-catalogue-id'));
calls.length=0;await click({catalogueQuestion:'money.month',catalogueText:'Where did my money go this month?'});
assert.equal(calls.find(c=>c.path==='/api/agent')?.body.message,'Where did my money go this month?','falls back to the coach with the same text');
''')

    def test_typed_exact_question_is_answered_like_a_tap(self):
        # V5 fix (lane CO): word-for-word catalogue text gets its card directly, with or without the AI coach.
        self.node_app(self.PRELUDE + r'''
await openCoach();calls.length=0;
agentReply={source:'agent',answer:['AI answer'],cards:[],steps:[],evidence:[],actions:[],suggestions:[]};
get('coach-input').value='  what if i cut a CATEGORY  ';
get('coach-form').listeners.submit({preventDefault(){},submitter:get('coach-send')});await settle();
assert.equal(calls.filter(c=>c.path==='/api/agent').length,0,'no AI call for an exact catalogue question');
const answer=calls.find(c=>c.path==='/api/catalogue/answer');assert.ok(answer);assert.equal(answer.body.question_id,'spend.cut');
const html=get('coach-response').innerHTML;assert.ok(html.includes('€45.14')&&!html.includes('quick-notice'));
// Anything else still goes to the AI coach.
calls.length=0;get('coach-input').value='what if i cut a category and more';get('coach-form').listeners.submit({preventDefault(){},submitter:get('coach-send')});await settle();
assert.equal(calls.filter(c=>c.path==='/api/agent').length,1);
''')

    def test_intro_chip_only_while_the_profile_is_empty(self):
        self.node_app(self.PRELUDE + r'''
profileEmpty=false;await select('CUST00676');await openCoach();await settle();
assert.equal(get('coach-intro-chip').innerHTML,'','no "Tell me about you" once the profile has facts');
''')


if __name__ == '__main__':
    unittest.main()
