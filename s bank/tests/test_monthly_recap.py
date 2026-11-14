"""Home recap behavior at the real client/API boundary, with no live model calls."""
import unittest
import test_web_contract as contracts


SETUP = r'''
const originalFixture=fixture;
let recap={source:'agent',steps:[{tool:'get_overview',label:'Reviewed your account overview'}],answer:['Income was **€2,000.00**. Recorded spending was **€988.70**, with **€100.00** transferred to savings.'],suggestions:['Which category made up most of my September spending?'],actions:[{kind:'save_scenario',params:{category:'Restaurants',percent:'20',month:'2026-09'}}]};
let consumption=98870,scopeMonth='2026-09';
fixture=(path,customer)=>path==='/api/agent'?recap:path==='/api/overview'?{...originalFixture(path,customer),month:scopeMonth,salary_cents:200000,other_income_cents:0,consumption_cents:consumption,committed_saving_transfers_cents:10000}:originalFixture(path,customer);
'''


class MonthlyRecapTests(unittest.TestCase):
    read = contracts.WebContractTests.read
    node_app = contracts.WebContractTests.node_app

    def test_home_generates_a_scoped_recap_without_chat_history_or_writes(self):
        self.node_app(SETUP + r'''
calls.length=0;await app.load();await settle();
assert.match(get('insight-description').textContent,/988\.70/);
assert.match(get('insight-headline').textContent,/September 2026/);
assert.ok(!get('insight-headline').textContent.includes('110.27'));
assert.match(get('home-recap-status').textContent,/AI/);
const sent=calls.filter(call=>call.path==='/api/agent');assert.equal(sent.length,1);
assert.equal(sent[0].body.customer_id,'CUST00001');assert.equal(sent[0].body.month,'2026-09');assert.equal(sent[0].body.locale,'en');
assert.deepEqual(sent[0].body.history,[]);assert.ok(!sent[0].body.message.includes('CUST00001'));
assert.deepEqual(app.state.conversation,[]);assert.equal(get('coach-response').textContent,'');
assert.equal(calls.filter(call=>call.method==='POST'&&call.path!=='/api/agent').length,0);
''')

    def test_repeated_loads_reuse_recap_but_changed_figures_are_rechecked(self):
        self.node_app(SETUP + r'''
calls.length=0;await app.load();await settle();await app.load();await settle();
assert.equal(calls.filter(call=>call.path==='/api/agent').length,1);
consumption=120000;recap={...recap,answer:['Recorded spending is now €1,200.00.']};
await app.load();await settle();assert.equal(calls.filter(call=>call.path==='/api/agent').length,2);
assert.match(get('insight-description').textContent,/1,200\.00/);
''')

    def test_slow_generation_keeps_facts_and_navigation_available(self):
        self.node_app(SETUP + r'''
const delayed=hold('/api/agent');const loading=app.load();await loading;await settle();assert.ok(pending.used,'Home must start a recap request');await delayed.started;
assert.match(get('insight-description').textContent,/988\.70/);
assert.match(get('insight-description').textContent,/2,000\.00/);
assert.equal(get('open-story').disabled,false);assert.equal(app.state.busy,false);
assert.equal(get('home-coach-card').attributes['aria-busy'],'true');
delayed.release();await loading;await settle();
assert.equal(get('home-coach-card').attributes['aria-busy'],'false');assert.match(get('home-recap-status').textContent,/AI/);
''')

    def test_obsolete_scope_answers_cannot_replace_active_recap(self):
        for change in ('persona', 'month', 'language'):
            with self.subTest(change=change):
                self.node_app(SETUP + 'const change=' + repr(change) + r''';
recap={...recap,answer:['Late answer for the previous scope.']};
const delayed=hold('/api/agent');const loading=app.load();await loading;await settle();assert.ok(pending.used,'Home must start a recap request');await delayed.started;
recap={...recap,answer:['Fresh answer for the active scope.']};
if(change==='persona')await select('CUST00676');
if(change==='month'){scopeMonth='2026-08';get('selected-month').value='2026-08';get('selected-month').listeners.change();}
if(change==='language'){get('language').value='fi';get('language').listeners.change();}
await settle();assert.ok(get('insight-description').textContent.includes('Fresh answer'));
delayed.release();await loading;await settle();
assert.ok(get('insight-description').textContent.includes('Fresh answer'));assert.ok(!get('insight-description').textContent.includes('Late answer'));
assert.deepEqual(app.state.conversation,[]);
''')

    def test_model_fallback_and_invalid_copy_keep_facts_without_an_ai_label(self):
        self.node_app(SETUP + r'''
for(const response of [{source:'deterministic',legacy:{explanation_blocks:[{text:'Not a monthly recap'}]}},{...recap,answer:[]},{...recap,answer:['x'.repeat(601)]},{...recap,steps:[],answer:['Things are looking fine.']},{...recap,answer:['**']},{...recap,answer:['** **']}]){
 consumption+=100;recap=response;await app.load();await settle();
 assert.ok(!get('home-recap-status').textContent.includes('AI'));
 assert.match(get('insight-description').textContent,/2,000\.00/);assert.match(get('insight-description').textContent,/100\.00/);
 assert.ok(!get('insight-description').textContent.includes('Not a monthly recap'));
 assert.equal(get('home-coach-card').attributes['aria-busy'],'false');
}
''')

    def test_network_failure_is_cached_without_blocking_the_card(self):
        self.node_app(SETUP + r'''
let requests=0;const previousFetch=globalThis.fetch;
globalThis.fetch=async(url,options)=>{if(new URL(url,'http://local').pathname==='/api/agent'){requests++;throw new Error('Offline');}return previousFetch(url,options);};
await app.load();await settle();await app.load();await settle();
assert.equal(requests,1);assert.match(get('insight-description').textContent,/988\.70/);
assert.ok(!get('home-recap-status').textContent.includes('AI'));assert.equal(get('open-story').disabled,false);
''')

    def test_account_failure_clears_recap_and_missing_figures_do_not_become_zero(self):
        self.node_app(SETUP + r'''
await app.load();await settle();const previousFetch=globalThis.fetch;
globalThis.fetch=async(url,options)=>new URL(url,'http://local').pathname==='/api/overview'?{ok:false,json:async()=>({ok:false,error:{message:'Unavailable'}})}:previousFetch(url,options);
await app.load();await settle();assert.ok(!get('insight-description').textContent.includes('988.70'));
assert.ok(!get('home-recap-status').textContent.includes('AI'));assert.equal(get('open-story').disabled,true);
globalThis.fetch=previousFetch;
fixture=(path,customer)=>path==='/api/agent'?{source:'deterministic'}:path==='/api/overview'?{...originalFixture(path,customer),consumption_cents:0}:originalFixture(path,customer);
await app.load();await settle();assert.match(get('insight-description').textContent,/€0\.00/);
assert.ok(!get('insight-description').textContent.toLowerCase().includes('income'));
''')

    def test_model_text_is_escaped_and_home_question_starts_only_the_requested_chat(self):
        self.node_app(SETUP + r'''
recap={...recap,answer:['<img src=x onerror=bad()> Monthly facts.'],suggestions:['Show September groceries <script>bad()</script>']};
await app.load();await settle();
assert.ok(!get('insight-description').innerHTML.includes('<img'));assert.ok(get('insight-description').innerHTML.includes('&lt;img'));
assert.equal(get('home-coach-question').dataset.directQuestion,recap.suggestions[0]);
calls.length=0;await documentListeners.click({target:get('home-coach-question')});await settle();
const sent=calls.filter(call=>call.path==='/api/agent');assert.equal(sent.length,1);assert.equal(sent[0].body.message,recap.suggestions[0]);assert.deepEqual(sent[0].body.history,[]);
assert.equal(app.state.conversation.length,1);assert.equal(app.state.view,'coach');
''')

    def test_automatic_prompt_excludes_local_profile_notes(self):
        self.node_app(SETUP + r'''
const exp=await import('data:text/javascript;base64,'+Buffer.from(sources['experience.js']).toString('base64'));
const store=exp.createExperienceStore(null,'CUST00001');store.addNote({text:'PRIVATE_NOTE_FOR_THIS_BROWSER'});
calls.length=0;await app.load();await settle();
const request=calls.find(call=>call.path==='/api/agent');assert.ok(request);assert.ok(!JSON.stringify(request.body).includes('PRIVATE_NOTE_FOR_THIS_BROWSER'));
''')


if __name__ == '__main__':
    unittest.main()


class MonthlyRecapV3Tests(unittest.TestCase):
    read = contracts.WebContractTests.read
    node_app = contracts.WebContractTests.node_app

    def test_three_paragraph_recap_renders_headline_and_two_lines_with_tiles(self):
        self.node_app(SETUP + r'''
recap={...recap,answer:['Spending stayed close to August.','You moved €100.00 to savings.','Little leaks took €988.70 <b>this</b> month.']};
await app.load();await settle();
const html=get('insight-description').innerHTML;
assert.ok(html.includes('recap-lead'));assert.ok(html.includes('Went well:'));assert.ok(html.includes('Worth a look:'));
assert.ok(html.includes('&lt;b&gt;'));
const tiles=get('recap-tiles').innerHTML;
assert.ok(tiles.includes('Money in'));assert.ok(tiles.includes('Spent'));assert.ok(tiles.includes('To savings'));
assert.match(tiles,/988\.70/);
''')

    def test_recap_tiles_compute_change_against_previous_month(self):
        self.node_app(r'''
const mod=await import('data:text/javascript;base64,'+Buffer.from(sources['monthly-recap.js']).toString('base64'));
const tiles=mod.recapTiles({salary_cents:200000,other_income_cents:5000,consumption_cents:90000,committed_saving_transfers_cents:10000},{salary_cents:200000,other_income_cents:0,consumption_cents:100000,committed_saving_transfers_cents:10000});
assert.deepEqual(tiles.map(t=>[t.key,t.cents,t.delta_cents]),[['income',205000,5000],['spent',90000,-10000],['saved',10000,0]]);
assert.deepEqual(mod.recapTiles({consumption_cents:500},null).map(t=>[t.key,t.delta_cents]),[['spent',null]]);
''')
