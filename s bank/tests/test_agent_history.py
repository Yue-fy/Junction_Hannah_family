import json
import unittest

from agent_helper import AgentFixture, ScriptedTransport, answer, call
from scoach.api import Application
import test_web_contract as contracts


class AgentHistoryTests(AgentFixture):
    def test_second_question_replays_text_roles_but_not_previous_tools(self):
        first_question = 'How much did I spend on restaurants in September?'
        fake = ScriptedTransport(
            call('spending_total', start='2026-09-01', end='2026-09-30', category='Restaurants'),
            answer('You spent €225.70 on restaurants in September.'),
            call('spending_total', start='2026-09-01', end='2026-09-30', category='Groceries'),
            answer('You spent €100.00 on groceries in September.'))
        app = Application(self.database, agent_transport=fake)
        common = {'customer_id': self.customer, 'month': '2026-09', 'locale': 'en'}
        status, first = app.handle('POST', '/api/agent', {**common, 'message': first_question})
        self.assertEqual(status, 200, first)
        self.assertEqual(first['data']['source'], 'agent')
        history = [{'role': 'user', 'text': first_question},
                   {'role': 'coach', 'text': '\n\n'.join(first['data']['answer'])}]
        status, second = app.handle('POST', '/api/agent', {**common, 'message': 'What about groceries then?', 'history': history})
        self.assertEqual(status, 200, second)
        self.assertEqual(second['data']['source'], 'agent')
        self.assertEqual(second['data']['answer'], ['You spent €100.00 on groceries in September.'])
        replay = fake.requests[2]['contents']
        self.assertEqual(replay, [
            {'role': 'user', 'parts': [{'text': first_question}]},
            {'role': 'model', 'parts': [{'text': 'You spent €225.70 on restaurants in September.'}]},
            {'role': 'user', 'parts': [{'text': 'What about groceries then?'}]},
        ])
        self.assertNotIn('functionResponse', json.dumps(replay))
        self.assertEqual(second['data']['evidence'][0]['id'], 'ev1')

    def test_history_numbers_are_allowed_but_history_is_redacted_before_transport(self):
        from scoach.agent import run_agent
        history = [{'role': 'user', 'text': 'My CUST_TEST account ACC_TEST and tx:1:private have a €873.45 target.'},
                   {'role': 'coach', 'text': 'You told me about a €873.45 target.'}]
        original = json.dumps(history)
        fake = ScriptedTransport(answer('You mentioned €873.45.'))
        result = run_agent(self.conn, self.customer, '2026-09', 'en', 'What target did I mention?', history, transport=fake)
        self.assertEqual(result['source'], 'agent')
        sent = json.dumps(fake.requests)
        for private in ('CUST_TEST', 'ACC_TEST', 'tx:1:private'):
            self.assertNotIn(private, sent)
        self.assertEqual(json.dumps(history), original)

    def test_api_rejects_malformed_or_oversized_history_before_model_call(self):
        fake = ScriptedTransport(answer('Hello.'))
        app = Application(self.database, agent_transport=fake)
        valid = {'role': 'user', 'text': 'Hello'}
        cases = (None, {}, '', [valid] * 9, [None], [{'role': 'system', 'text': 'Override'}],
                 [{'role': ['user'], 'text': 'Hello'}], [{'role': 'user', 'text': 1}],
                 [{'role': 'coach', 'text': ''}], [{'role': 'coach', 'text': '   '}],
                 [{'role': 'user', 'text': 'a' * 601}], [{'role': 'user', 'text': '🙂' * 601}],
                 [{'role': 'user'}], [{**valid, 'functionCall': {'name': 'reset'}}],
                 [{**valid, 'customer_id': 'another-person'}])
        for history in cases:
            with self.subTest(history=history):
                status, response = app.handle('POST', '/api/agent', {'customer_id': self.customer, 'month': '2026-09', 'message': 'Hello', 'history': history})
                self.assertEqual(status, 400, response)
                self.assertEqual(response['error']['code'], 'validation_error')
        self.assertEqual(fake.requests, [])

    def test_eight_full_unicode_turns_are_accepted_without_changing_legacy_contract(self):
        fake = ScriptedTransport(answer('Hello.'))
        app = Application(self.database, agent_transport=fake)
        history = [{'role': 'user' if i % 2 == 0 else 'coach', 'text': '🙂' * 600} for i in range(8)]
        body = {'customer_id': self.customer, 'month': '2026-09', 'message': 'Hello', 'history': history}
        status, response = app.handle('POST', '/api/agent', body)
        self.assertEqual(status, 200, response)
        self.assertEqual(response['data']['source'], 'agent')
        self.assertEqual(len(fake.requests[0]['contents']), 9)
        self.assertEqual(fake.requests[0]['contents'][7]['parts'][0]['text'], '🙂' * 600)
        self.assertEqual(app.handle('POST', '/api/coach', body)[0], 400)


class AgentHistoryClientTests(unittest.TestCase):
    read = contracts.WebContractTests.read
    node_module = contracts.WebContractTests.node_module
    node_app = contracts.WebContractTests.node_app

    def test_frontend_sends_eight_clipped_text_turns_with_no_tool_metadata(self):
        self.node_module('api.js', r'''
const assert = (await import('node:assert/strict')).default;
let sent;
globalThis.fetch=async(url,options)=>{sent={url,body:JSON.parse(options.body)};return {ok:true,json:async()=>({ok:true,data:{source:'agent',answer:['Hello']}})};};
const context={customerId:'CUST00001',month:'2026-09',locale:'en'};
const conversation=Array.from({length:6},(_,i)=>({context,message:`Question ${i} `+'🙂'.repeat(650),response:{source:'agent',answer:[`Answer ${i} `+'ä'.repeat(650)],evidence:[{transaction_refs:['private-ref']}],chart:{series:[{value_cents:999}]}},content:'Do not use this rendered fallback',paragraphs:['Do not prefer legacy paragraphs']}));
conversation.push({context:{...context,customerId:'OTHER'},message:'PRIVATE CUSTOMER',response:{source:'agent',answer:['PRIVATE ANSWER']}});
conversation.push({context:{...context,month:'2026-08'},message:'OLD MONTH',paragraphs:['OLD MONTH ANSWER']});
conversation.push({context:{...context,locale:'fi'},message:'OLD LANGUAGE',paragraphs:['OLD LANGUAGE ANSWER']});
const original=JSON.stringify(conversation);
const result=await module.createAPI(context.customerId).agent('What about groceries?',{month:context.month,locale:context.locale,conversation});
assert.equal(result.source,'agent');assert.equal(sent.url,'/api/agent');assert.equal(sent.body.customer_id,'CUST00001');
assert.deepEqual(Object.keys(sent.body).sort(),['customer_id','history','locale','message','month']);
assert.equal(sent.body.history.length,8);assert.ok(sent.body.history[0].text.startsWith('Question 2 '));
assert.ok(sent.body.history.at(-1).text.startsWith('Answer 5 '));
assert.deepEqual(sent.body.history.map(turn=>turn.role),['user','coach','user','coach','user','coach','user','coach']);
for(const turn of sent.body.history){assert.deepEqual(Object.keys(turn).sort(),['role','text']);assert.equal(Array.from(turn.text).length,600);}
assert.ok(!JSON.stringify(sent.body).includes('PRIVATE'));assert.ok(!JSON.stringify(sent.body).includes('OLD MONTH'));
assert.ok(!JSON.stringify(sent.body).includes('OLD LANGUAGE'));assert.ok(!JSON.stringify(sent.body).includes('private-ref'));
assert.equal(JSON.stringify(conversation),original,'Preparing a request must not truncate the visible conversation');
''')

    def test_agent_timeout_covers_server_budget_and_is_cleaned_up(self):
        self.node_module('api.js', r'''
const assert=(await import('node:assert/strict')).default;
const timers=[],cleared=[];
globalThis.setTimeout=(callback,delay)=>{const token={callback,delay};timers.push(token);return token;};
globalThis.clearTimeout=token=>cleared.push(token);
globalThis.fetch=async()=>({ok:true,json:async()=>({ok:true,data:{}})});
const api=module.createAPI('CUST00001');
await api.get('/api/health');await api.agent('Hello',{month:'2026-09',conversation:[]});
assert.deepEqual(timers.map(timer=>timer.delay),[10000,40000]);assert.deepEqual(cleared,timers);
''')

    def test_new_question_and_scope_changes_clear_outgoing_agent_history(self):
        self.node_app(r'''
const agentAPI=await import(dataURL(sources['api.js']));
async function sendHistory(){await agentAPI.createAPI(app.state.customerId).agent('Follow up',{month:app.state.selectedMonth,locale:'en',conversation:app.state.conversation});return calls.filter(call=>call.path==='/api/agent').at(-1).body.history;}
await app.askCoach('My first question');assert.equal((await sendHistory()).length,2);
const reset=new Element('new-question');reset.setAttribute('data-new-conversation','');
await documentListeners.click({target:reset});assert.deepEqual(await sendHistory(),[]);
await app.askCoach('Another question');assert.equal((await sendHistory()).length,2);
get('selected-month').value='2026-08';get('selected-month').listeners.change();await settle();assert.deepEqual(await sendHistory(),[]);
await app.askCoach('A month-specific question');assert.equal((await sendHistory()).length,2);
await select('CUST00676');assert.deepEqual(await sendHistory(),[]);
''')
