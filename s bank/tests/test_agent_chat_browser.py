"""Optional rendered Home/chat acceptance with Chrome and a disposable synthetic ledger."""
import os
import subprocess
import threading
import unittest

from agent_helper import AgentFixture
from scoach.api import Application, create_server
from scoach.db import DEFAULT_CUSTOMERS


@unittest.skipUnless(os.environ.get('SCOACH_CHAT_PLAYWRIGHT_PATH'),
                     'Set SCOACH_CHAT_PLAYWRIGHT_PATH for rendered chat acceptance')
class AgentChatBrowserTests(AgentFixture):
    def test_three_turn_layout_sources_confirmations_and_scope_reset(self):
        for customer in DEFAULT_CUSTOMERS:
            self.conn.execute('INSERT INTO customers VALUES(?,?,?,?)', (customer, '00100', 30, '{}'))
            for row in self.conn.execute('SELECT * FROM transactions WHERE customer_id=?', (self.customer,)).fetchall():
                values = list(row)
                values[0], values[1], values[2] = customer + ':' + values[0], customer, 'ACC' + customer[4:]
                self.conn.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)', values)
        self.conn.commit()
        server = create_server(Application(self.database), port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        env = {**os.environ, 'SCOACH_TEST_URL': f'http://127.0.0.1:{server.server_port}'}
        script = r'''
const assert=require('node:assert/strict');
const {chromium}=require(process.env.SCOACH_CHAT_PLAYWRIGHT_PATH);
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,chromiumSandbox:true});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1100},locale:'en-US'});
  const errors=[],requests=[],posts=[];let hold=true,release,recapOffline=false;
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{if(request.method()==='POST')posts.push({url:request.url(),body:request.postDataJSON()});});
  const answer={source:'agent',answer:[
   'You spent **€225.70** on restaurants in September. These are recorded payments from your selected account.',
   'A smaller dining budget is a planning option. Open the transactions to review the purchases, then decide whether to change anything.',
   'The comparison uses the same category in each month. Income and transfers to savings are separate from consumption.'
  ],highlight:{label:'Restaurants',value:'€225.70',caption:'September 2026'},
   chart:{kind:'bar',title:'Recorded spending',series:[{label:'August',value_cents:22570},{label:'September',value_cents:22570}]},
   steps:[{tool:'spending_total',label:'Checked spending'}],
   evidence:[{id:'test',label:'September restaurants',count:2,query:{start:'2026-09-01',end:'2026-09-28',category:'Restaurants',consumption_only:'true'}}],
   actions:[{kind:'create_goal',label:'Review goal',params:{name:'Italy',target_cents:300050,target_date:'2027-06-01'}},
    {kind:'save_scenario',label:'Review scenario',params:{name:'Dining',category:'Restaurants',percent:'12.5',month:'2026-09'}}],
   suggestions:['What about groceries?'],scope:{start:'2026-09-01',end:'2026-09-28'}};
  await page.route('**/api/agent',async route=>{
   const body=route.request().postDataJSON();requests.push(body);
   if(hold)await new Promise(resolve=>{release=resolve;});
   const recap=body.message.startsWith('Write a monthly recap for ');
   const homeAnswer=recapOffline?{source:'deterministic',fallback_reason:'not_configured'}:{...answer,steps:[{tool:'get_overview',label:'Reviewed your account overview'}],answer:['Your recorded income was €2,000.00. You spent €988.70, including €225.70 on restaurants, and transferred €100.00 to savings.'],suggestions:['Show my restaurant spending in September 2026.']};
   await route.fulfill({json:{ok:true,data:recap?homeAnswer:answer}});
  });
  await page.goto(process.env.SCOACH_TEST_URL+'/device-preview.html');
  const frame=page.frameLocator('#app-preview');
  await frame.locator('#open-story:not([disabled])').waitFor({state:'attached'});
  await frame.locator('#home-recap-status').filter({hasText:'Writing'}).waitFor();
  assert.match(await frame.locator('#insight-description').innerText(),/988\.70/);
  assert.match(await frame.locator('#insight-description').innerText(),/2,000\.00/);
  assert.equal(await frame.locator('#home-coach-card').getAttribute('aria-busy'),'true');
  while(!release)await new Promise(resolve=>setImmediate(resolve));
  hold=false;release();release=null;
  await frame.locator('#home-recap-status').filter({hasText:'AI recap'}).waitFor();
  assert.match(await frame.locator('#insight-headline').innerText(),/September 2026/);
  assert.match(await frame.locator('#insight-description').innerText(),/225\.70/);
  assert.equal(await frame.locator('.coach-turn').count(),0);
  assert.equal(requests.length,1);assert.deepEqual(requests[0].history,[]);
  assert.ok(posts.every(post=>post.url.endsWith('/api/agent')),'Automatic recap must not execute actions');
  for(const [preset,width,height] of [['chat-phone',375,812],['current-phone',390,844],['desktop',1280,800]]){
   await page.locator('[data-preset="'+preset+'"].preset').click();
   const geometry=await frame.locator('#home-coach-card').evaluate(card=>{
    const doc=card.ownerDocument,win=doc.defaultView,box=card.getBoundingClientRect();
    return {width:win.innerWidth,height:win.innerHeight,left:box.left,right:box.right,overflow:doc.documentElement.scrollWidth>win.innerWidth,cardOverflow:card.scrollWidth>card.clientWidth};
   });
   assert.equal(geometry.width,width);assert.equal(geometry.height,height);
   assert.equal(geometry.overflow,false);assert.equal(geometry.cardOverflow,false);
   assert.ok(geometry.left>=0&&geometry.right<=width);
   if(process.env.SCOACH_SCREENSHOT_DIR)await frame.locator('#home-coach-card').screenshot({path:process.env.SCOACH_SCREENSHOT_DIR+'/home-recap-'+preset+'.png'});
  }
  await frame.locator('nav [data-view="trends"]').click();await frame.locator('nav [data-view="home"]').click();
  assert.match(await frame.locator('#home-recap-status').innerText(),/AI recap/);assert.equal(requests.length,1);
  await frame.locator('#home-coach-question').click();
  await frame.locator('.coach-turn [data-agent-suggestion]').waitFor();
  assert.equal(requests.at(-1).message,'Show my restaurant spending in September 2026.');
  assert.deepEqual(requests.at(-1).history,[],'Home text must not become hidden chat history');
  await frame.locator('[data-new-conversation]').click();requests.length=0;posts.length=0;
  await page.locator('[data-preset="current-phone"].preset').click();
  await frame.locator('[data-view="coach"]').click();
  await frame.locator('[data-coach-question="agent.starter.where"]').click();
  await frame.locator('.coach-turn:nth-child(1) [data-agent-suggestion]').waitFor();
  await frame.locator('[data-agent-suggestion]').click();
  await frame.locator('.coach-turn:nth-child(2) [data-agent-suggestion]').waitFor();
  assert.equal(requests[1].message,'What about groceries?');assert.equal(requests[1].history.length,2);
  hold=true;
  await frame.locator('#coach-input').fill('What could I change?');
  await frame.locator('#coach-input').press('Enter');
  await frame.locator('#coach-pending .coach-turn-user').waitFor();
  assert.equal(await frame.locator('#coach-send').isDisabled(),true);
  assert.ok((await frame.locator('#coach-live-status').innerText()).length>0);
  await page.waitForFunction(()=>document.querySelector('#app-preview').contentDocument.querySelector('#coach-send').disabled);
  while(!release)await new Promise(resolve=>setImmediate(resolve));
  hold=false;release();
  await frame.locator('.coach-turn:nth-child(3) [data-agent-suggestion]').waitFor();
  assert.equal(await frame.locator('[data-agent-suggestion]').count(),1);assert.equal(requests[2].history.length,4);
  for(const [preset,width,height] of [['chat-phone',375,812],['current-phone',390,844],['desktop',1280,800]]){
   await page.locator('[data-preset="'+preset+'"].preset').click();
   const geometry=await frame.locator('body').evaluate(body=>{
    const doc=body.ownerDocument,win=doc.defaultView,rect=id=>{const r=doc.querySelector(id).getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom};};
    return {width:win.innerWidth,height:win.innerHeight,messages:rect('#coach-scroll'),composer:rect('#coach-form'),nav:rect('.bottom-dock'),chat:rect('#coach-view'),end:rect('#coach-end'),overflow:doc.documentElement.scrollWidth>win.innerWidth,scrollable:doc.querySelector('#coach-scroll').scrollHeight>doc.querySelector('#coach-scroll').clientHeight};
   });
   console.log(JSON.stringify({preset,...geometry}));
   assert.equal(geometry.width,width);assert.equal(geometry.height,height);
   assert.ok(geometry.messages.height>=height*.6,'Messages must occupy at least 60% of '+preset);
   assert.ok(geometry.scrollable,'Long conversations must scroll independently');
   assert.ok(geometry.messages.bottom<=geometry.composer.y+1,'Composer overlaps messages');
   assert.ok(geometry.composer.bottom<=geometry.nav.y+1,'Composer overlaps navigation');
   assert.ok(geometry.composer.y>=0&&geometry.nav.bottom<=height+1,'Controls must remain in the viewport');
   assert.equal(geometry.overflow,false);
   assert.ok(geometry.chat.width<=720);assert.ok(Math.abs(geometry.chat.x-(width-geometry.chat.width)/2)<1);
   if(process.env.SCOACH_SCREENSHOT_DIR)await page.locator('#app-preview').screenshot({path:process.env.SCOACH_SCREENSHOT_DIR+'/coach-'+preset+'.png'});
  }
  await page.locator('[data-preset="current-phone"].preset').click();
  await frame.locator('.coach-turn').last().locator('.agent-work summary').click();
  const evidenceRequest=page.waitForRequest(request=>request.url().includes('/api/transactions?'));
  await frame.locator('.coach-turn').last().locator('[data-agent-evidence]').click();
  const query=new URL((await evidenceRequest).url()).searchParams;
  assert.equal(query.get('category'),'Restaurants');assert.equal(query.get('start'),'2026-09-01');assert.equal(query.get('end'),'2026-09-28');
  await frame.locator('#transactions-dialog[open] .transaction-row').first().waitFor();
  assert.equal(await frame.locator('#transactions-dialog .transaction-row').count(),2);
  await frame.locator('#transactions-dialog [data-close]').click();
  await frame.locator('.coach-turn').last().locator('[data-agent-action][data-index="0"]').click();
  assert.equal(await frame.locator('#goal-name').inputValue(),'Italy');assert.equal(await frame.locator('#goal-target').inputValue(),'3000.50');
  assert.equal(posts.filter(post=>post.url.endsWith('/api/goals')).length,0);
  await frame.locator('[data-view="coach"]').click();
  await frame.locator('.coach-turn').last().locator('[data-agent-action][data-index="1"]').click();
  await frame.locator('#agent-action-dialog[open]').waitFor();
  assert.equal(posts.filter(post=>post.url.endsWith('/api/scenarios')).length,0);
  await frame.locator('#agent-action-confirm').click();
  await frame.locator('#goal-handoff').filter({hasText:'28.21'}).waitFor();
  const saved=posts.filter(post=>post.url.endsWith('/api/scenarios'));
  assert.equal(saved.length,1);assert.equal(saved[0].body.confirmed,true);assert.equal(saved[0].body.percent,'12.5');
  await frame.locator('[data-view="coach"]').click();await frame.locator('#coach-scope-button').click();
  await frame.locator('#coach-month').selectOption('2026-08');
  await frame.locator('#coach-empty:not([hidden])').waitFor();assert.equal(await frame.locator('.coach-turn').count(),0);
  await frame.locator('[data-coach-question="agent.starter.where"]').click();
  await frame.locator('[data-agent-suggestion]').waitFor();assert.equal(requests.at(-1).history.length,0);
  recapOffline=true;
  await frame.locator('#persona-button').click();await frame.locator('#persona').selectOption('CUST00676');
  await frame.locator('#home-recap-status').filter({hasText:'Account summary'}).waitFor();
  assert.match(await frame.locator('#insight-description').innerText(),/988\.70/);
  assert.equal(await frame.locator('#home-coach-card').getAttribute('aria-busy'),'false');
  await frame.locator('[data-view="coach"]').click();
  await frame.locator('#coach-empty:not([hidden])').waitFor();assert.equal(await frame.locator('.coach-turn').count(),0);
  assert.deepEqual(errors,[]);console.log('PASS Home recap loading/fallback/cache/handoff and chat geometry, three turns, pending, suggestions, sources, confirmations and scope resets');
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
'''
        try:
            result = subprocess.run(['node'], input=script, env=env, capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout.strip())
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
