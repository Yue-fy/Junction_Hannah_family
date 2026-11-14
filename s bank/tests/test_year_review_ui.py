"""Exercise the year-in-review story viewer module (web/year-review.js) in Node without a browser."""
import json
from pathlib import Path
import shutil
import subprocess
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'web' / 'year-review.js'
CSS = ROOT / 'web' / 'year-review.css'

SAMPLE = '''
const review={year:2025,complete:true,available:true,cards:[
  {id:'intro',kind:'intro',facts:{year:2025,purchase_count:1234}},
  {id:'inout',kind:'money_in_out',facts:{money_in_cents:4200000,money_out_cents:3650050}},
  {id:'saved',kind:'saved',facts:{saved_cents:480000,saving_rate_percent:'11.4',previous_saved_cents:300000}},
  {id:'top',kind:'top_category',facts:{category:'Groceries <b>',amount_cents:612345,share_percent:'18.2'}},
  {id:'baskets',kind:'baskets',facts:{must_pays_cents:1800000,surprise_must_pays_cents:400000,little_leaks_cents:900000,must_pays_percent:'58.1',surprise_must_pays_percent:'12.9',little_leaks_percent:'29.0'}},
  {id:'leaks',kind:'little_leaks',facts:{little_leaks_cents:900000,rent_months:'1.4'}},
  {id:'peak',kind:'peak_month',facts:{month:'2025-12',amount_cents:420000,calmest_month:'2025-02',calmest_amount_cents:190000}},
  {id:'day',kind:'busiest_day',facts:{date:'2025-12-20',amount_cents:51230,purchase_count:7}},
  {id:'fav',kind:'favourite_weekday_or_mcc',facts:{weekday:4,mcc_label:'Grocery stores',mcc_count:211}},
  {id:'arch',kind:'archetype',facts:{archetype_label:'Steady planner',previous_archetype_label:'Weekend treater'}},
  {id:'close',kind:'closing',facts:{year:2025}}
]};
const money=c=>'EUR '+(c/100).toFixed(2);
const text=html=>html.replace(/<[^>]+>/g,' ').replace(/\\s+/g,' ');
'''


@unittest.skipUnless(shutil.which('node'), 'Node is needed to exercise the client module')
class YearReviewUITests(unittest.TestCase):
    def run_module(self, body):
        script = textwrap.dedent(f'''
            import assert from 'node:assert/strict';
            import * as yrm from {json.dumps(MODULE.as_uri())};
        ''') + SAMPLE + textwrap.dedent(body)
        result = subprocess.run(['node', '--input-type=module', '--eval', script], cwd=ROOT.parent, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_syntax(self):
        result = subprocess.run(['node', '--check', str(MODULE)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_kind_renders_in_every_locale_without_placeholders(self):
        self.run_module('''
        for(const locale of ['en','fi','sv']){
          review.cards.forEach((card,index)=>{
            const html=yrm.renderStory(review,{locale,money,index});
            assert.ok(html.includes('role="dialog"')&&html.includes('aria-modal="true"')&&html.includes('aria-labelledby="yr-headline"'));
            assert.ok(html.includes('id="yr-headline"'));
            assert.ok(html.includes('data-kind="'+card.kind+'"'),card.kind);
            assert.ok(!/\\{\\w+\\}/.test(html),locale+' '+card.kind+' leftover placeholder: '+text(html));
            assert.ok(html.includes('class="yr-caption"'));
            assert.ok(!html.includes('undefined')&&!html.includes('null')&&!html.includes('NaN'),locale+' '+card.kind+': '+text(html));
          });
        }
        ''')

    def test_facts_fill_default_captions(self):
        self.run_module('''
        const en=i=>text(yrm.renderStory(review,{locale:'en',money,index:i}));
        assert.match(en(1),/EUR 42000\\.00 came in and EUR 36500\\.50 went out\\./);
        assert.match(en(1),/Left over: EUR 5499\\.50\\./);
        assert.match(en(2),/You moved EUR 4800\\.00 to savings, 11\\.4% of what came in\\./);
        assert.match(en(5),/about 1\\.4 months of your own rent/);
        assert.match(en(4),/Must-pays took 58\\.1%, surprise must-pays 12\\.9% and little leaks 29%\\./);
        assert.match(en(8),/Friday/);
        const fi=text(yrm.renderStory(review,{locale:'fi',money,index:4}));
        assert.ok(fi.includes('Pakolliset kuukausimenot')&&fi.includes('Yllättävät pakolliset menot')&&fi.includes('Arjen pikkumenot'));
        assert.ok(yrm.renderStory(review,{locale:'fi',money,index:4}).includes('58,1\\u00a0%'));
        const sv=text(yrm.renderStory(review,{locale:'sv',money,index:4}));
        assert.ok(sv.includes('Fasta måsten')&&sv.includes('Oväntade måsten')&&sv.includes('Vardagens småutgifter'));
        const svSaved=text(yrm.renderStory(review,{locale:'sv',money,index:2}));
        assert.ok(svSaved.includes('Du flyttade EUR 4800.00 till sparande'));
        const fiPeak=text(yrm.renderStory(review,{locale:'fi',money,index:6,monthLabel:m=>m==='2025-12'?'joulukuu 2025':'helmikuu 2025'}));
        assert.ok(fiPeak.includes('Joulukuu 2025 oli vuoden kallein kuukausi'),fiPeak);
        // missing optional facts fall back to a shorter caption and hide the supporting line
        const partial={year:2025,cards:[{id:'s',kind:'saved',facts:{saved_cents:1000}}]};
        const html=yrm.renderStory(partial,{locale:'en',money,index:0});
        assert.ok(text(html).includes('You moved EUR 10.00 to savings this year.'));
        assert.ok(!html.includes('yr-support'));
        ''')

    def test_escapes_and_prefers_ai_caption(self):
        self.run_module('''
        const top=yrm.renderStory(review,{locale:'en',money,index:3});
        assert.ok(top.includes('Groceries &lt;b&gt;')&&!top.includes('Groceries <b>'));
        const ai=yrm.renderStory(review,{locale:'fi',money,index:3,captions:{top:'<script>alert(1)</script> Ruokaa!'}});
        assert.ok(ai.includes('&lt;script&gt;alert(1)&lt;/script&gt; Ruokaa!'));
        assert.ok(!ai.includes('<script>'));
        assert.ok(!text(ai).includes('Eniten rahaa meni'));
        const closing=yrm.renderStory(review,{locale:'en',money,index:10,closingMessage:'What a year & more.'});
        assert.ok(closing.includes('What a year &amp; more.'));
        const fromReview=yrm.renderStory({...review,captions:{saved:'Nice saving.'}},{locale:'en',money,index:2});
        assert.ok(fromReview.includes('Nice saving.'));
        ''')

    def test_progress_states_tap_zones_and_last_card_actions(self):
        self.run_module('''
        const html=yrm.renderStory(review,{locale:'en',money,index:3});
        const states=[...html.matchAll(/class="yr-progress-bar" data-state="(\\w+)"/g)].map(m=>m[1]);
        assert.equal(states.length,11);
        assert.deepEqual(states.slice(0,5),['filled','filled','filled','current','pending']);
        assert.ok(html.includes('data-story-prev')&&html.includes('data-story-next')&&html.includes('data-story-close'));
        assert.ok(!html.includes('data-story-save')&&!html.includes('data-story-ask'));
        assert.ok(html.includes('aria-valuenow="4"'));
        const first=yrm.renderStory(review,{locale:'en',money,index:0});
        assert.match(first,/data-story-prev[^>]*disabled/);
        const last=yrm.renderStory(review,{locale:'sv',money,index:99});
        assert.ok(last.includes('data-story-save')&&last.includes('data-story-ask'));
        assert.ok(last.includes('Spara i min profil')&&last.includes('Fråga coachen om mitt år'));
        assert.match(last,/data-story-next[^>]*disabled/);
        assert.ok(!last.includes('data-state="pending"'));
        const en=yrm.renderStory(review,{locale:'en',money,index:10});
        assert.ok(en.includes('Save to my profile')&&en.includes('Ask coach about my year'));
        ''')

    def test_visuals_and_count_up_hooks(self):
        self.run_module('''
        const inout=yrm.renderStory(review,{locale:'en',money,index:1});
        const widths=[...inout.matchAll(/yr-bar-fill" style="width:([\\d.]+)%/g)].map(m=>Number(m[1]));
        assert.deepEqual(widths,[100,Number((3650050/4200000*100).toFixed(2))]);
        assert.ok(inout.includes('data-count-cents="4200000"'));
        const baskets=yrm.renderStory(review,{locale:'en',money,index:4});
        assert.equal((baskets.match(/class="yr-seg yr-seg-/g)||[]).length,3);
        assert.ok(baskets.includes('data-count-cents="3100000"'));
        assert.ok(!/<img|<canvas/.test(inout+baskets));
        ''')

    def test_unavailable_review(self):
        self.run_module('''
        const html=yrm.renderStory({year:2026,available:false,cards:[]},{locale:'fi'});
        assert.ok(html.includes('role="dialog"')&&html.includes('data-story-close'));
        assert.ok(text(html).includes('Vuodelta 2026 ei ole vielä tarpeeksi tilitapahtumia.'));
        const partial=yrm.renderStory({...review,complete:false},{locale:'en',money,index:0});
        assert.ok(text(partial).includes('2025 is still in progress'));
        ''')

    def test_controller_bounds_pause_resume_and_auto_advance(self):
        self.run_module('''
        let now=0,seq=0;const timers=new Map();
        const scheduler={setTimeout:(fn,ms)=>{const id=++seq;timers.set(id,{fn,at:now+ms});return id;},clearTimeout:id=>timers.delete(id),now:()=>now};
        const advance=ms=>{now+=ms;for(const [id,t] of [...timers]){if(t.at<=now){timers.delete(id);t.fn();}}};
        const seen=[];
        const c=yrm.createStoryController({count:3,onIndex:i=>seen.push(i),autoAdvanceMs:1000,scheduler});
        c.start();assert.deepEqual(seen,[0]);
        assert.equal(c.prev(),false);assert.equal(c.index,0);
        advance(999);assert.equal(c.index,0);advance(1);assert.equal(c.index,1);
        advance(400);c.pause();assert.equal(c.paused,true);assert.equal(timers.size,0);
        advance(5000);assert.equal(c.index,1);
        c.resume();advance(599);assert.equal(c.index,1);advance(1);assert.equal(c.index,2);
        assert.equal(c.isLast,true);assert.equal(timers.size,0,'no timer on the last card');
        assert.equal(c.next(),false);assert.equal(c.index,2);
        assert.equal(c.goTo(0),true);assert.equal(c.goTo(7),false);assert.equal(c.goTo(-1),false);
        assert.equal(c.prev(),false);assert.equal(c.next(),true);
        assert.deepEqual(seen,[0,1,2,0,1]);
        c.destroy();assert.equal(timers.size,0);assert.equal(c.next(),false);
        // auto-advance disabled
        const manual=yrm.createStoryController({count:3,autoAdvanceMs:0,scheduler});
        manual.start();assert.equal(timers.size,0);advance(10000);assert.equal(manual.index,0);
        assert.equal(manual.toggle(),true);assert.equal(manual.toggle(),false);
        ''')

    def test_attach_story_keyboard_close_and_detach(self):
        self.run_module('''
        const listeners=new Map();
        const doc={activeElement:null,contains:()=>false,defaultView:{setTimeout,clearTimeout,matchMedia:()=>({matches:true})}};
        const root={ownerDocument:doc,innerHTML:'',renders:[],
          set html(v){},querySelector:()=>null,querySelectorAll:()=>[],contains:()=>false,
          addEventListener:(t,fn)=>listeners.set(t,fn),removeEventListener:t=>listeners.delete(t)};
        Object.defineProperty(root,'innerHTML',{set(v){root.renders.push(v);},get(){return root.renders.at(-1)||'';}});
        let closed=0;
        const detach=yrm.attachStory(root,{review,render:i=>yrm.renderStory(review,{locale:'en',money,index:i}),onClose:()=>closed++});
        assert.equal(root.renders.length,1);
        const key=k=>listeners.get('keydown')({key:k,preventDefault(){}});
        key('ArrowRight');key('ArrowRight');key('ArrowLeft');
        assert.equal(root.renders.length,4);
        assert.ok(root.renders.at(-1).includes('data-index="1"'));
        key('Escape');assert.equal(closed,1);
        detach();assert.equal(listeners.size,0);
        ''')

    def test_message_maps_have_identical_keys(self):
        self.run_module('''
        const keys=Object.keys(yrm.YEAR_REVIEW_MESSAGES.en).sort();
        for(const locale of ['fi','sv']){
          assert.deepEqual(Object.keys(yrm.YEAR_REVIEW_MESSAGES[locale]).sort(),keys);
          for(const key of keys){
            const ph=s=>[...s.matchAll(/\\{(\\w+)\\}/g)].map(m=>m[1]).sort();
            assert.deepEqual(ph(yrm.YEAR_REVIEW_MESSAGES[locale][key]),ph(yrm.YEAR_REVIEW_MESSAGES.en[key]),locale+' '+key);
            assert.ok(yrm.YEAR_REVIEW_MESSAGES[locale][key].trim(),locale+' '+key);
          }
        }
        assert.equal(yrm.yr('xx','ui.close'),'Close');
        ''')

    def test_banner_markup(self):
        self.run_module('''
        const en=yrm.renderYearBanner(2025,'en');
        assert.ok(en.includes('data-story-open="2025"')&&en.includes('data-story-dismiss="2025"'));
        assert.ok(text(en).includes('Your 2025 in money is ready'));
        assert.ok(text(yrm.renderYearBanner(2025,'fi')).includes('Rahavuotesi 2025 on valmis'));
        assert.ok(text(yrm.renderYearBanner(2025,'sv')).includes('Ditt 2025 i pengar är klart'));
        const evil=yrm.renderYearBanner('<x>','en');
        assert.ok(!evil.includes('<x>'));
        ''')

    def test_css_contract(self):
        css = CSS.read_text(encoding='utf-8')
        for needle in ['100dvh', 'safe-area-inset-top', 'safe-area-inset-bottom', 'max-width: 420px', 'prefers-reduced-motion', '44px', '@keyframes yr-fill', 'animation-play-state: paused']:
            self.assertIn(needle, css)
        for kind in ['intro', 'money_in_out', 'saved', 'top_category', 'baskets', 'little_leaks', 'peak_month', 'busiest_day', 'favourite_weekday_or_mcc', 'archetype', 'closing']:
            self.assertIn('.yr-kind-' + kind, css)


if __name__ == '__main__':
    unittest.main()
