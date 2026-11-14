"""Customer-flow regressions. These use the client harness, not a real browser."""
import unittest
import test_web_contract as contracts


class CustomerExperienceTests(unittest.TestCase):
    read = contracts.WebContractTests.read
    node_app = contracts.WebContractTests.node_app

    def test_coach_is_a_page_and_opening_it_retains_the_conversation(self):
        self.node_app(r'''
await app.askCoach('Explain my recent spending');
const prior=get('coach-response').innerHTML;
const home=new Element('home-tab');home.dataset.view='home';documentListeners.click({target:home});
get('ask-coach').listeners.click();
assert.equal(app.state.view,'coach');
assert.equal(get('home-view').hidden,true);
assert.equal(get('coach-view').hidden,false);
assert.equal(app.state.conversation.length,1);
assert.equal(get('coach-response').innerHTML,prior,'Navigating back must preserve the readable answer');
assert.equal(get('coach-input').focused,true);
''')

    def test_title_only_wish_is_saved_locally_without_a_numeric_goal_write(self):
        self.node_app(r'''
const goals=new Element('goals-tab');goals.dataset.view='goals';documentListeners.click({target:goals});
get('wish-title').value='A calmer winter';get('wish-remember').checked=false;
assert.equal(get('goal-target').value,'');assert.equal(get('goal-date').value,'');calls.length=0;
get('wish-form').listeners.submit({preventDefault(){}});await settle();
assert.ok(get('wishes-list').innerHTML.includes('A calmer winter'));
assert.ok(get('wishes-list').innerHTML.includes('No target or deadline set'));
assert.ok(get('wish-storage').textContent.includes('this visit only'));
assert.equal(get('wish-title').value,'');assert.equal(get('goal-planner').open,false);
assert.equal(calls.filter(call=>call.path.startsWith('/api/goals')&&call.method==='POST').length,0);
assert.equal(calls.filter(call=>call.method==='POST').length,0,'A title-only wish needs no server write');
const home=new Element('home-tab');home.dataset.view='home';documentListeners.click({target:home});
assert.ok(get('home-goal-content').innerHTML.includes('A calmer winter'));
documentListeners.click({target:goals});
assert.ok(get('wishes-list').innerHTML.includes('A calmer winter'),'The wish must survive navigation');
''')

    def test_exploring_a_saved_wish_preserves_its_title_without_saving_a_duplicate(self):
        self.node_app(r'''
const goals=new Element('goals-tab');goals.dataset.view='goals';documentListeners.click({target:goals});
get('wish-title').value='A calmer winter';get('wish-remember').checked=false;
get('wish-form').listeners.submit({preventDefault(){}});
const exp=await import('data:text/javascript;base64,'+Buffer.from(sources['experience.js']).toString('base64'));
const store=exp.createExperienceStore(null,'CUST00001'),before=store.load().wishes;
assert.equal(before.length,1);
const explore=new Element('explore-wish');explore.dataset.wishExplore=before[0].id;calls.length=0;
await documentListeners.click({target:explore});await settle();
assert.equal(app.state.view,'coach');
assert.ok(get('coach-response').textContent.includes('A calmer winter'),'The answer must identify the saved wish being explored');
assert.deepEqual(store.load().wishes,before,'Exploring must not duplicate or mutate the saved wish');
assert.equal(calls.filter(call=>call.path.startsWith('/api/goals')&&call.method==='POST').length,0);
assert.equal(store.load().consent,false);
await select('CUST00676');
assert.equal(get('wish-title').value,'');assert.ok(!get('coach-response').textContent.includes('A calmer winter'));
documentListeners.click({target:goals});assert.ok(!get('wishes-list').textContent.includes('A calmer winter'));
const questionsBefore=calls.filter(call=>call.path==='/api/agent').length;
await documentListeners.click({target:explore});await settle();
assert.equal(calls.filter(call=>call.path==='/api/agent').length,questionsBefore,'An old wish action cannot cross into another persona');
assert.deepEqual(store.load().wishes,before);
''')

    def test_forgetting_or_revoking_preferences_immediately_removes_wish_copy(self):
        self.node_app(r'''
const exp=await import('data:text/javascript;base64,'+Buffer.from(sources['experience.js']).toString('base64'));
const store=exp.createExperienceStore(null,'CUST00001');
for(const action of ['forget','revoke']){
 const goals=new Element('goals-tab');goals.dataset.view='goals';documentListeners.click({target:goals});
 const title='Private wish to '+action;
 get('wish-title').value=title;get('wish-remember').checked=true;
 get('wish-form').listeners.submit({preventDefault(){}});
 assert.equal(store.load().consent,true);
 assert.ok(get('wishes-list').textContent.includes(title));assert.ok(get('home-goal-content').textContent.includes(title));
 const notebook=new Element('open-preferences');notebook.setAttribute('data-open-notebook','');documentListeners.click({target:notebook});
 calls.length=0;
 if(action==='forget'){
  const forget=new Element('forget-preferences');forget.setAttribute('data-forget-profile','');documentListeners.click({target:forget});
 }else{
  get('preference-focus').value='flexibility';get('preference-style').value='gentle';get('preference-protect').value='none';
  get('preference-milestones').checked=false;get('preference-consent').checked=false;
  get('preferences-form').listeners.submit({preventDefault(){}});
 }
 assert.deepEqual(store.load().wishes,[]);assert.equal(store.load().consent,false);
 assert.ok(!get('wishes-list').textContent.includes(title),action+' left a forgotten wish visible');
 assert.ok(!get('home-goal-content').textContent.includes(title),action+' left a forgotten wish on Home');
 assert.equal(get('wish-remember').checked,false);assert.equal(get('wish-remember').disabled,false);
 assert.equal(calls.filter(call=>call.method==='POST').length,0);
}
''')

    def test_a_ten_percent_dining_preview_keeps_its_percentage_when_saved(self):
        self.node_app(r'''
const originalFetch=globalThis.fetch;
globalThis.fetch=async(url,options)=>['/api/agent','/api/coach'].includes(new URL(url,'http://local').pathname)?{ok:true,json:async()=>({ok:true,data:offlineAnswer({intent:'simulate_adjustment',tool_kind:'spending_adjustment_preview',source:'deterministic',explanation_blocks:[{text:'A ten percent experiment.'}],tool_result:{category:'Restaurants',percent:10,start:'2026-09-01',end:'2026-09-30',actual_total_cents:22570,adjustable_base_cents:22570,modeled_monthly_contribution_cents:2257,transaction_refs:[]}},new URL(url,'http://local').pathname)})}:originalFetch(url,options);
await app.askCoach('How much could I save if I reduced dining out by 10%?');
const savesBefore=calls.filter(c=>c.path==='/api/scenarios').length;
const action=get('coach-response').children.filter(child=>child?.onclick).at(-1);
assert.ok(action,'The preview offers an explicit next step');action.onclick();await settle();
const saves=calls.filter(c=>c.path==='/api/scenarios');
assert.equal(saves.length,savesBefore+1);
assert.equal(saves.at(-1).body.percent,10);
assert.equal(saves.at(-1).body.month,'2026-09');
assert.equal(saves.at(-1).body.category,'Restaurants');
''')

    def test_opening_a_spending_explanation_does_not_save_a_scenario(self):
        self.node_app(r'''
const before=calls.filter(c=>c.path==='/api/scenarios').length;
await app.showStory();
assert.equal(calls.filter(c=>c.path==='/api/scenarios').length,before);
''')

    def test_fractional_historical_scenario_saves_the_answer_scope_after_confirmation(self):
        self.node_app(r'''
const originalFixture=fixture;
fixture=(path,customer)=>path==='/api/coach'?{intent:'simulate_adjustment',source:'deterministic',tool_kind:'spending_adjustment_preview',explanation_blocks:[{text:'An August experiment.'}],tool_result:{category:'Restaurants',percent:'12.5',start:'2026-08-01',end:'2026-08-31',actual_total_cents:11543,adjustable_base_cents:11543,modeled_monthly_contribution_cents:1443,transaction_refs:[]}}:originalFixture(path,customer);
get('coach-input').value='How much could I save if I reduced dining out by 12.5% in August 2026?';
get('coach-form').listeners.submit({preventDefault(){},submitter:new Element('send')});await settle();
assert.equal(app.state.selectedMonth,'2026-09');
assert.ok(get('coach-response').textContent.includes('12.5%'));
assert.ok(get('coach-response').textContent.includes('€14.43'));
assert.equal(calls.filter(call=>call.path==='/api/scenarios').length,0,'Reading the forecast must not save it');
const action=get('coach-response').children.find(child=>child?.onclick);assert.ok(action);
await action.onclick();await settle();
const saves=calls.filter(call=>call.path==='/api/scenarios');assert.equal(saves.length,1);
assert.equal(String(saves[0].body.percent),'12.5');assert.equal(saves[0].body.month,'2026-08');
assert.equal(saves[0].body.category,'Restaurants');assert.equal(saves[0].body.confirmed,true);
assert.equal(calls.filter(call=>call.path.startsWith('/api/goals')&&call.method==='POST').length,0);
''')

    def test_cashflow_question_produces_an_inline_forecast_answer(self):
        self.node_app(r'''
const originalFixture=fixture;
fixture=(path,customer)=>{
 if(path==='/api/coach')return {intent:'preview_cashflow',source:'deterministic',parameters:{reference_date:'2026-08-31',days:30},explanation_blocks:[]};
 if(path==='/api/forecast')return {customer_id:customer,as_of:'2026-08-31',observed:[{date:'2026-08-31',balance_cents:130000,observed:true}],projected:[{date:'2026-09-01',balance_cents:118600},{date:'2026-09-30',balance_cents:121000}],recurring_items:[],assumptions:[]};
 return originalFixture(path,customer);
};
calls.length=0;get('coach-input').value='Show cash flow as of 2026-08-31';
get('coach-form').listeners.submit({preventDefault(){},submitter:new Element('send')});await settle();
const forecast=calls.find(call=>call.path==='/api/forecast');assert.ok(forecast);
assert.equal(forecast.query.as_of,'2026-08-31');assert.equal(forecast.customer,'CUST00001');
assert.ok(get('coach-response').innerHTML.includes('coach-tool-result'));
const visible=get('coach-response').textContent;
assert.ok(/forecast|cash.flow/i.test(visible));
assert.ok(visible.includes('€1,210.00'));assert.ok(visible.includes('€1,186.00'));
assert.ok(visible.includes('past variation, not a probability'));
assert.equal(app.state.selectedMonth,'2026-09');
assert.equal(app.state.view,'coach');
assert.equal(calls.filter(call=>call.method==='POST'&&!['/api/agent','/api/coach'].includes(call.path)).length,0);
''')

    def test_failed_question_retains_the_successful_transcript_and_retries_the_same_question(self):
        self.node_app(r'''
const originalFetch=globalThis.fetch;let attempts=0;
globalThis.fetch=async(url,options)=>{
 const response=await originalFetch(url,options);
 if(!['/api/agent','/api/coach'].includes(new URL(url,'http://local').pathname))return response;
 attempts++;
 if(attempts===2)return {ok:false,status:503,json:async()=>({ok:false,error:{message:'Coach temporarily unavailable'}})};
 return {ok:true,json:async()=>({ok:true,data:offlineAnswer({source:'deterministic',intent:'transaction_statistics',explanation_blocks:[{text:attempts===1?'First verified answer':'Retried verified answer'}]},new URL(url,'http://local').pathname)})};
};
const submit=message=>{get('coach-input').value=message;get('coach-form').listeners.submit({preventDefault(){},submitter:new Element('send')});};
calls.length=0;
submit('Show my spending');await settle();
const successful=get('coach-response').innerHTML;
submit('What changed in August?');await settle();
assert.equal(get('coach-response').innerHTML,successful,'A failed question must not erase the prior answer');
assert.equal(app.state.conversation.length,1);
assert.ok(get('coach-live-status').textContent.includes('Coach temporarily unavailable'));
assert.equal(get('coach-response').attributes['aria-busy'],'false');assert.equal(app.state.busy,false);
const retry=get('coach-live-status').children.find(child=>typeof child.onclick==='function');
assert.ok(retry,'A failed question must have a reachable retry action');
await retry.onclick();await settle();
assert.equal(calls.filter(call=>call.path==='/api/agent').length,3);
assert.equal(calls.filter(call=>call.path==='/api/agent').at(-1).body.message,'What changed in August?');
assert.equal(app.state.conversation.length,2);
assert.ok(get('coach-response').textContent.includes('First verified answer'));
assert.ok(get('coach-response').textContent.includes('Retried verified answer'));
assert.equal(get('coach-live-status').textContent,'');assert.equal(app.state.view,'coach');
''')

    def test_persona_change_clears_prior_answers_and_discards_an_inflight_question(self):
        self.node_app(r'''
const originalFixture=fixture;
fixture=(path,customer)=>path==='/api/coach'?{source:'deterministic',intent:'transaction_statistics',query_scope:{start:'2026-08-01',end:'2026-08-31',metric:'outflow_total',filters:{category:'Restaurants'},concept:'Restaurants'},explanation_blocks:[{text:customer==='CUST00001'?'Alex private answer':'Robin current answer'}]}:originalFixture(path,customer);
get('coach-input').value='Show my restaurant spending';
get('coach-form').listeners.submit({preventDefault(){},submitter:new Element('send')});await settle();
assert.ok(get('coach-response').textContent.includes('Alex private answer'));assert.ok(app.state.queryScope);
const delayed=hold('/api/agent');get('coach-input').value='What about the previous month?';
get('coach-form').listeners.submit({preventDefault(){},submitter:new Element('send')});await delayed.started;
await select('CUST00676');
assert.equal(get('coach-response').textContent,'');assert.equal(get('coach-response').innerHTML,'');
assert.equal(get('coach-live-status').textContent,'');assert.equal(get('coach-response').attributes['aria-busy'],'false');
assert.deepEqual(app.state.conversation,[]);assert.equal(app.state.queryScope,null);
delayed.release();await settle();pending=null;
assert.equal(get('coach-response').textContent,'','A late Alex answer must not reappear for Robin');
assert.deepEqual(app.state.conversation,[]);assert.equal(app.state.queryScope,null);
get('coach-input').value='Show my spending';
get('coach-form').listeners.submit({preventDefault(){},submitter:new Element('send')});await settle();
const latest=calls.filter(call=>call.path==='/api/agent').at(-1);
assert.equal(latest.customer,'CUST00676');assert.ok(!('previous_query' in latest.body));
assert.ok(get('coach-response').textContent.includes('Robin current answer'));
assert.ok(!get('coach-response').textContent.includes('Alex private answer'));
''')

    def test_unsent_coach_draft_survives_navigation_but_not_context_resets(self):
        self.node_app(r'''
get('coach-input').value='A private question about Alex';
const home=new Element('home-tab');home.dataset.view='home';documentListeners.click({target:home});
get('ask-coach').listeners.click();
assert.equal(get('coach-input').value,'A private question about Alex','Ordinary navigation keeps an unfinished question');
await select('CUST00676');
assert.equal(get('coach-input').value,'','A draft cannot carry over to another customer');
const requestsBeforeEmptySubmit=calls.filter(call=>call.path==='/api/agent').length;
get('coach-form').listeners.submit({preventDefault(){},submitter:new Element('send')});await settle();
assert.equal(calls.filter(call=>call.path==='/api/agent').length,requestsBeforeEmptySubmit,'The old draft must not submit in the new customer context');
assert.ok(calls.every(call=>call.body.message!=='A private question about Alex'));
get('coach-input').value='What about this month?';
get('selected-month').value='2026-08';get('selected-month').listeners.change();await settle();
assert.equal(get('coach-input').value,'','A period change clears a question tied to the old scope');
get('coach-input').value='And that category?';
get('language').value='fi';get('language').listeners.change();
assert.equal(get('coach-input').value,'','Changing language resets the conversation and its unfinished follow-up');
get('coach-input').value='An old follow-up';
const restart=new Element('new-question');restart.setAttribute('data-new-conversation','');
documentListeners.click({target:restart});
assert.equal(get('coach-input').value,'');
get('coach-input').value='Before resetting demo state';
await get('reset-demo').listeners.click({currentTarget:get('reset-demo')});await settle();
assert.equal(get('coach-input').value,'');
''')

    def test_a_loading_demo_story_cannot_submit_into_a_changed_context(self):
        self.node_app(r'''
for(const change of ['persona','month','language','language-round-trip','new-conversation']){
 const delayed=hold('/api/overview');calls.length=0;
 const story=new Element('kai-story');story.dataset.demoStory='kai';
 documentListeners.click({target:story});await delayed.started;
 if(change==='persona')await select('CUST00676');
 else if(change==='month'){get('selected-month').value='2026-08';get('selected-month').listeners.change();await settle();}
 else if(change==='new-conversation'){
  const restart=new Element('new-question');restart.setAttribute('data-new-conversation','');documentListeners.click({target:restart});
 }else{
  const initialLanguage=get('language').value;
  get('language').value=initialLanguage==='fi'?'en':'fi';get('language').listeners.change();
  if(change==='language-round-trip'){get('language').value=initialLanguage;get('language').listeners.change();}
 }
 delayed.release();await settle();pending=null;
 const agentRequests=calls.filter(call=>call.path==='/api/agent');
 assert.ok(agentRequests.every(call=>call.body.message.startsWith('Write a monthly recap for ')),'Only automatic Home recaps may run after '+change+' changes, never the obsolete story question');
 assert.ok(agentRequests.every(call=>call.body.history.length===0));
 assert.deepEqual(app.state.conversation,[]);
}
''')

    def test_home_buffer_question_uses_supported_localized_starters(self):
        self.node_app(r'''
const exp=await import('data:text/javascript;base64,'+Buffer.from(sources['experience.js']).toString('base64'));
const store=exp.createExperienceStore(null,'CUST00001');store.save({focus:'buffer',protected_category:'none'});
for(const [locale,question] of Object.entries({en:'What is safe for me to spend this week?',fi:'Paljonko voin käyttää turvallisesti tällä viikolla?',sv:'Hur mycket är tryggt för mig att spendera den här veckan?'})){
 get('language').value=locale;get('language').listeners.change();
 const starter=get('home-coach-question');
 assert.equal(starter.dataset.directQuestion,question,'The emitted Home starter must be a supported '+locale+' question');
 await documentListeners.click({target:starter});await settle();
 assert.equal(calls.filter(call=>call.path==='/api/agent').at(-1).body.message,question);
}
''')


if __name__ == '__main__':
    unittest.main()
