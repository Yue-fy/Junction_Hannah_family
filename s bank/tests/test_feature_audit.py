"""Customer-visible regressions found by exercising failure paths and navigation."""
import unittest

import test_web_contract as contracts


class FeatureAuditTests(unittest.TestCase):
    read = contracts.WebContractTests.read
    node_app = contracts.WebContractTests.node_app

    def test_failed_persona_load_cannot_display_the_previous_personas_finances(self):
        self.node_app(r'''
const base=fixture;
fixture=(path,customer)=>path==='/api/transactions'?{transactions:[
 {transaction_ref:'old-meal',date:'2026-09-09',amount_cents:-12345,transaction_type:'purchase',category:'Restaurants'}
]}:path==='/api/overview'?{...base(path,customer),flows:[
 {role:'discretionary',amount_cents:-12345,transaction_refs:['old-meal']}
]}:base(path,customer);
await app.load();
assert.equal(get('spending-total').textContent,'€123.45');
assert.ok(get('home-baskets-content').textContent.includes('€123.45'));
const oldInvestment=get('investment-content').textContent,oldVat=get('vat-content').textContent;
const originalFetch=globalThis.fetch;
globalThis.fetch=async(url,options)=>new URL(url,'http://local').pathname==='/api/overview'
 ?{ok:false,status:503,json:async()=>({ok:false,error:{message:'Unavailable'}})}
 :originalFetch(url,options);
await select('CUST00676');
assert.equal(app.state.customerId,'CUST00676');
assert.notEqual(get('spending-total').textContent,'€123.45','A failed persona load exposed the previous spending total');
assert.ok(!get('home-baskets-content').textContent.includes('€123.45'),'A failed persona load exposed the previous baskets');
assert.ok(!get('spending-categories').textContent.includes('€123.45'));
assert.notEqual(get('investment-content').textContent,oldInvestment);
assert.notEqual(get('vat-content').textContent,oldVat);
assert.ok(!get('home-greeting').textContent.includes('Alex'));
''')

    def test_direct_goal_retry_after_refresh_failure_does_not_create_a_duplicate(self):
        self.node_app(r'''
goalInputs();get('goal-date').value='2027-04-30';calls.length=0;
const originalFetch=globalThis.fetch;let failRefresh=true;
globalThis.fetch=async(url,options)=>{
 const path=new URL(url,'http://local').pathname;
 if(path==='/api/goals'&&options.method==='GET'&&failRefresh){failRefresh=false;throw new TypeError('Temporary network loss');}
 return originalFetch(url,options);
};
await assert.rejects(app.createGoal());
await app.createGoal();
assert.equal(calls.filter(call=>call.path==='/api/goals'&&call.method==='POST').length,1,'Retrying the acknowledged goal created a duplicate');
assert.equal(get('goal-name').value,'');
assert.equal(get('goal-target').disabled,false);
goalInputs();get('goal-name').value='A different plan';get('goal-date').value='2027-04-30';
await app.createGoal();
assert.equal(calls.filter(call=>call.path==='/api/goals'&&call.method==='POST').length,2,'A completed retry must still allow a new plan');
''')

    def test_reset_keeps_the_visible_navigation_and_state_consistent(self):
        self.node_app(r'''
for(const view of ['trends','coach','goals','journal']){
 const tab=new Element(view+'-tab');tab.dataset.view=view;documentListeners.click({target:tab});
 assert.equal(app.state.view,view);assert.equal(get(view+'-view').hidden,false);
 await get('reset-demo').listeners.click({currentTarget:get('reset-demo')});await settle();
 assert.equal(get(app.state.view+'-view').hidden,false,'Reset changed state without changing the visible page');
 for(const candidate of ['home','trends','coach','goals','journal']){
  assert.equal(get(candidate+'-view').hidden,candidate!==app.state.view,'Reset left inconsistent page visibility');
 }
}
''')
