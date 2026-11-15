"""Agent-to-client boundaries: history, untrusted text, actions and stale responses."""
import unittest
import test_web_contract as contracts


AGENT = r'''
const agentAnswer={source:'agent',answer:['You spent **€225.70** on restaurants.'],highlight:{label:'Restaurants',value:'€225.70',caption:'September 2026'},chart:{kind:'bar',title:'Spending',series:[{label:'August',value_cents:11543},{label:'September',value_cents:22570}]},steps:[{tool:'spending_total',label:'Checked spending'}],evidence:[{id:'ev1',label:'September restaurants',count:2,query:{start:'2026-09-01',end:'2026-09-28',category:'Restaurants',consumption_only:'true'}}],actions:[],suggestions:['What about groceries?'],scope:{start:'2026-09-01',end:'2026-09-28'}};
const originalFixture=fixture;
fixture=(path,customer)=>path==='/api/agent'?agentAnswer:originalFixture(path,customer);
'''


class AgentChatTests(unittest.TestCase):
    read = contracts.WebContractTests.read
    node_app = contracts.WebContractTests.node_app

    def test_agent_answers_use_history_and_only_latest_suggestions_with_twenty_turn_cap(self):
        self.node_app(AGENT + r'''
await app.askCoach('How much on restaurants?');
assert.equal(calls.filter(call=>call.method==='POST').at(-1).path,'/api/agent');
assert.equal(app.state.conversation[0].response.source,'agent');
assert.equal(get('coach-mode').textContent,'Numbers come from your account. Nothing changes without your OK.');
assert.match(get('coach-response').innerHTML,/<strong>€225.70<\/strong>/);
const suggestion=new Element();suggestion.dataset.agentSuggestion=app.state.conversation[0].id;suggestion.dataset.index='0';
await documentListeners.click({target:suggestion});
const sent=calls.filter(call=>call.path==='/api/agent').at(-1).body;
assert.equal(sent.message,'What about groceries?');
assert.deepEqual(sent.history,[{role:'user',text:'How much on restaurants?'},{role:'coach',text:'You spent **€225.70** on restaurants.'}]);
assert.equal((get('coach-response').innerHTML.match(/data-agent-suggestion=/g)||[]).length,1);
for(let i=0;i<20;i++)await app.askCoach('Another question '+i);
assert.equal(app.state.conversation.length,20);
assert.equal(calls.filter(call=>call.path==='/api/agent').at(-1).body.history.length,8);
assert.equal(calls.filter(call=>call.path==='/api/coach').length,0);
''')

    def test_all_model_text_is_escaped_and_charts_only_use_series_values(self):
        self.node_app(AGENT + r'''
agentAnswer.answer=['<img src=x onerror=bad()>\n\n**safe** & <script>bad()</script>'];
agentAnswer.highlight={label:'<img>',value:'€225.70',caption:'" onfocus="bad'};
agentAnswer.chart.series[0].label='<script>chart</script>';
agentAnswer.evidence[0].label='<img evidence>';
agentAnswer.steps.push({tool:'unknown',label:'<img step>'});
agentAnswer.suggestions=['<svg onload=bad()>'];
await app.askCoach('<img user>');
const html=get('coach-response').innerHTML;
assert.ok(html.includes('&lt;img src=x'));assert.ok(html.includes('&lt;img user&gt;'));
assert.ok(html.includes('&lt;img evidence&gt;'));assert.ok(html.includes('<strong>safe</strong>'));
assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<img'));
assert.ok(html.includes('€115.43'));assert.ok(html.includes('€225.70'));assert.ok(!html.includes('NaN'));
assert.ok(html.indexOf('coach-prose')<html.indexOf('agent-highlight'));
assert.ok(html.indexOf('agent-highlight')<html.indexOf('agent-chart'));
assert.ok(html.indexOf('agent-chart')<html.indexOf('agent-work'));
''')

    def test_evidence_opens_exact_transactions_and_old_turn_buttons_are_inert_after_reset(self):
        self.node_app(AGENT + r'''
await app.askCoach('Restaurants?');
assert.ok(get('coach-response').innerHTML.includes('data-agent-evidence='));
const evidence=new Element();evidence.dataset.agentEvidence=app.state.conversation[0].id;evidence.dataset.index='0';
calls.length=0;await documentListeners.click({target:evidence});
const sent=calls.find(call=>call.path==='/api/transactions');
assert.equal(sent.query.start,'2026-09-01');assert.equal(sent.query.end,'2026-09-28');
assert.equal(sent.query.category,'Restaurants');assert.equal(sent.query.consumption_only,'true');
assert.equal(get('transactions-dialog').open,true);
const reset=new Element();reset.setAttribute('data-new-conversation','');await documentListeners.click({target:reset});
calls.length=0;await documentListeners.click({target:evidence});assert.equal(calls.length,0);
''')

    def test_goal_proposal_opens_editable_confirm_flow_without_saving(self):
        self.node_app(AGENT + r'''
agentAnswer.actions=[{kind:'create_goal',label:'Review goal',params:{name:'Italy',target_cents:300050,target_date:'2027-06-01'}}];
await app.askCoach('Plan a trip');
assert.ok(get('coach-response').innerHTML.includes('data-agent-action='));
const button=new Element();button.dataset.agentAction=app.state.conversation[0].id;button.dataset.index='0';
calls.length=0;await documentListeners.click({target:button});
assert.equal(calls.filter(call=>call.method==='POST').length,0);
assert.equal(app.state.view,'goals');assert.equal(get('goal-planner').open,true);
assert.equal(get('goal-name').value,'Italy');assert.equal(get('goal-target').value,'3000.50');
assert.equal(get('goal-date').value,'2027-06-01');assert.equal(get('goal-target').disabled,false);
await app.createGoal();
const saved=calls.find(call=>call.path==='/api/goals'&&call.method==='POST');
assert.equal(saved.body.target_cents,300050);assert.equal(saved.body.confirmed,true);
''')

    def test_scenario_proposal_requires_separate_confirmation_and_does_not_repeat_save(self):
        self.node_app(AGENT + r'''
agentAnswer.actions=[{kind:'save_scenario',label:'Review scenario',params:{name:'Dining',category:'Restaurants',percent:'12.5',month:'2026-08'}}];
await app.askCoach('Try a smaller change');
const button=new Element();button.dataset.agentAction=app.state.conversation[0].id;button.dataset.index='0';
calls.length=0;await documentListeners.click({target:button});
assert.equal(get('agent-action-dialog').open,true);
assert.equal(calls.filter(call=>call.method==='POST').length,0);
const submit=get('agent-action-confirm');await get('agent-action-form').listeners.submit({preventDefault(){},submitter:submit});await settle();
const saved=calls.filter(call=>call.path==='/api/scenarios'&&call.method==='POST');
assert.equal(saved.length,1);assert.equal(saved[0].body.month,'2026-08');assert.equal(saved[0].body.percent,'12.5');assert.equal(saved[0].body.confirmed,true);
await get('agent-action-form').listeners.submit({preventDefault(){},submitter:submit});await settle();
assert.equal(calls.filter(call=>call.path==='/api/scenarios'&&call.method==='POST').length,1);
''')

    def test_pending_message_and_send_state_clear_on_new_chat_before_late_answer(self):
        self.node_app(AGENT + r'''
let release;const gate=new Promise(resolve=>release=resolve),originalFetch=globalThis.fetch;
globalThis.fetch=async(url,options)=>{if(new URL(url,'http://local').pathname.startsWith('/api/'))await gate;return originalFetch(url,options);};
const job=app.askCoach('A pending question');await settle();
assert.equal(get('coach-send').disabled,true);
assert.ok(get('coach-pending').innerHTML.includes('A pending question'));
assert.ok(get('coach-live-status').textContent.length>0);
const reset=new Element();reset.setAttribute('data-new-conversation','');await documentListeners.click({target:reset});
assert.equal(get('coach-send').disabled,false);assert.equal(get('coach-pending').textContent,'');
release();await job;
assert.equal(app.state.conversation.length,0);assert.equal(get('coach-response').textContent,'');
assert.equal(get('coach-live-status').textContent,'');
''')

    def test_network_failure_clears_typing_and_keeps_retry_available(self):
        self.node_app(AGENT + r'''
globalThis.fetch=async()=>{throw new Error('Connection unavailable');};
await app.askCoach('Restaurants?');
assert.equal(get('coach-send').disabled,false);assert.equal(get('coach-response').attributes['aria-busy'],'false');
assert.ok(get('coach-live-status').children.some(node=>typeof node.onclick==='function'));
assert.equal(app.state.conversation.length,0);
''')

    def test_fallback_uses_legacy_answer_and_preserves_price_continuation(self):
        self.node_app(r'''
const originalFixture=fixture;
fixture=(path,customer)=>path==='/api/agent'?{source:'deterministic',fallback_reason:'not_configured',legacy:{intent:'safe_to_spend',source:'deterministic',needs_clarification:true,clarification_code:'planned_purchase_cost',clarification_question:'What total cost should we check?'}}:originalFixture(path,customer);
await app.askCoach('I want to see a movie this week');await app.askCoach('€20');
const posts=calls.filter(call=>call.method==='POST');assert.equal(posts[0].path,'/api/agent');
const legacy=posts.find(call=>call.path==='/api/coach');assert.ok(legacy.body.message.includes('movie'));assert.ok(legacy.body.message.includes('20'));
assert.equal(app.state.conversation.at(-1).message,'€20');assert.ok(!get('coach-mode').textContent.includes('AI coach'));
''')

    def test_composer_sends_enter_but_preserves_shift_enter_and_ime(self):
        self.node_app(r'''
assert.equal(typeof get('coach-input').listeners.keydown,'function');
let sent=0,prevented=0;get('coach-form').requestSubmit=()=>sent++;
const key=(extra={})=>({key:'Enter',shiftKey:false,isComposing:false,preventDefault(){prevented++;},...extra});
get('coach-input').value='Hello';
get('coach-input').listeners.keydown(key({shiftKey:true}));get('coach-input').listeners.keydown(key({isComposing:true}));
assert.equal(sent,0);assert.equal(prevented,0);
get('coach-input').listeners.keydown(key());assert.equal(sent,1);
get('coach-send').disabled=true;get('coach-input').listeners.keydown(key());assert.equal(sent,1);
''')

    def test_topic_questions_close_the_scope_modal_before_showing_the_answer(self):
        self.node_app(AGENT + r'''
for(const attributes of [{coachQuestion:'coach.question.safe'},{coachGoalTemplate:'buffer'},{openVat:''}]){
 get('coach-scope-button').listeners.click();assert.equal(get('coach-context-dialog').open,true);
 const button=new Element();Object.assign(button.dataset,attributes);
 if('openVat' in attributes)button.setAttribute('data-open-vat','');
 await documentListeners.click({target:button});await settle();
 assert.equal(get('coach-context-dialog').open,false,'Topic answers must be visible outside the scope dialog');
 assert.ok(get('coach-response').textContent.includes('225.70'));
}
''')


if __name__ == '__main__':
    unittest.main()
