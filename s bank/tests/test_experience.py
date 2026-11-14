"""Execute the real browser-only preference boundary without a browser or a server."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'web' / 'experience.js'


@unittest.skipUnless(shutil.which('node'), 'Node is needed to exercise the client module')
class ExperienceTests(unittest.TestCase):
    def run_module(self, body):
        script = textwrap.dedent(f'''
            import assert from 'node:assert/strict';
            import * as experience from {json.dumps(MODULE.as_uri())};
            function fakeStorage(values=new Map()){{
              return {{values,getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)}};
            }}
            {body}
        ''')
        result = subprocess.run(['node', '--input-type=module', '--eval', script], cwd=ROOT.parent, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_unconsented_choices_and_notes_remain_session_only(self):
        self.run_module('''
        const storage=fakeStorage(),store=experience.createExperienceStore(storage,'CUST00001');
        assert.equal(store.load().consent,false);
        assert.equal(storage.values.size,0);
        store.save({focus:'travel',style:'direct',consent:true,notes:[{text:'silently imported'}]});
        const note=store.addNote('Sunday dinners matter to me.');
        assert.equal(store.load().focus,'travel');assert.equal(store.load().consent,false);
        assert.equal(store.load().notes.length,1);assert.equal(storage.values.size,0);
        store.setConsent(false);assert.equal(store.load().notes.length,1,'Declining must not erase current session notes');
        assert.equal(store.isPersisted(),false);
        const returned=store.load();returned.notes[0].text='mutated';
        assert.equal(store.load().notes[0].text,note.text,'load must not expose mutable internal state');
        ''')

    def test_explicit_consent_persists_only_bounded_user_choices(self):
        self.run_module('''
        const storage=fakeStorage(),store=experience.createExperienceStore(storage,'CUST00001');
        store.save({focus:'home',style:'direct',protected_category:'Restaurants',milestones:true,raw_chat:'private transcript'});
        store.setConsent(true);
        const note=store.addNote({text:'Keep dinners with friends.',source:'confirmed_conversation'});
        assert.equal(store.isPersisted(),true);
        const serialized=storage.values.get(experience.PROFILE_PREFIX+'CUST00001');
        assert.ok(!serialized.includes('raw_chat'));assert.ok(!serialized.includes('private transcript'));
        const envelope=JSON.parse(serialized);assert.equal(envelope.version,1);
        const fresh=experience.createExperienceStore(fakeStorage(storage.values),'CUST00001');
        assert.equal(fresh.load().focus,'home');assert.equal(fresh.load().consent,true);
        assert.equal(fresh.load().notes[0].source,'confirmed_conversation');
        fresh.updateNote(note.id,'Keep one dinner each week.');
        assert.equal(fresh.load().notes[0].text,'Keep one dinner each week.');
        fresh.deleteNote(note.id);assert.equal(fresh.load().notes.length,0);
        ''')

    def test_revoke_and_forget_clear_personal_data_and_personas_are_isolated(self):
        self.run_module('''
        const storage=fakeStorage(),alex=experience.createExperienceStore(storage,'CUST00001'),kai=experience.createExperienceStore(storage,'CUST01331');
        alex.setConsent(true);alex.save({focus:'vehicle'});alex.addNote('My car goal');alex.markOnboarded();
        kai.setConsent(true);kai.save({focus:'buffer'});kai.addNote('My cushion');
        assert.equal(kai.load().notes.length,1);assert.equal(alex.load().notes.length,1);
        alex.setConsent(false);
        assert.equal(storage.values.has(experience.PROFILE_PREFIX+'CUST00001'),false);
        assert.equal(alex.load().notes.length,0);assert.equal(alex.load().focus,'flexibility');
        assert.equal(alex.load().consent,false);assert.equal(kai.load().focus,'buffer');
        const reopened=experience.createExperienceStore(fakeStorage(storage.values),'CUST00001');
        assert.equal(reopened.load().notes.length,0);assert.equal(reopened.load().consent,false);
        alex.forget();assert.equal(alex.isOnboarded(),false);
        assert.equal(storage.values.has(experience.TOUR_PREFIX+'CUST00001'),false);
        assert.equal(kai.load().notes[0].text,'My cushion');
        ''')

    def test_tour_completion_is_a_separate_minimal_boolean(self):
        self.run_module('''
        const storage=fakeStorage(),store=experience.createExperienceStore(storage,'CUST00001');
        store.save({focus:'travel'});store.markOnboarded();
        assert.equal(store.isOnboarded(),true);assert.equal(storage.values.size,1);
        assert.equal(storage.values.get(experience.TOUR_PREFIX+'CUST00001'),'1');
        const fresh=experience.createExperienceStore(fakeStorage(storage.values),'CUST00001');
        assert.equal(fresh.isOnboarded(),true);assert.equal(fresh.load().focus,'flexibility');
        ''')

    def test_denied_storage_is_usable_and_never_claims_persistence(self):
        self.run_module('''
        const storage={getItem(){throw Error('denied')},setItem(){throw Error('denied')},removeItem(){throw Error('denied')}};
        const store=experience.createExperienceStore(storage,'CUST00001');
        store.setConsent(true);store.save({focus:'travel'});store.addNote('A trip');store.markOnboarded();
        assert.equal(store.load().focus,'travel');assert.equal(store.isPersisted(),false);
        store.setConsent(false);assert.equal(store.load().notes.length,0);assert.equal(store.load().consent,false);
        store.forget();assert.equal(store.isOnboarded(),false);
        ''')

    def test_deletion_failure_is_reported_and_personal_data_can_be_overwritten_safely(self):
        self.run_module('''
        const storage=fakeStorage(),store=experience.createExperienceStore(storage,'CUST00001');
        store.setConsent(true);store.save({focus:'home'});store.addNote('Private preference');
        storage.removeItem=()=>{throw Error('cannot remove')};
        const normalSet=storage.setItem;storage.setItem=()=>{throw Error('cannot overwrite')};
        store.forget();assert.equal(store.isCleared(),false);assert.equal(store.load().notes.length,0);
        assert.ok(storage.values.get(experience.PROFILE_PREFIX+'CUST00001').includes('Private preference'));
        assert.ok(experience.ux('en','personal.clearFailed').includes('could not remove'));
        storage.setItem=normalSet;store.forget();assert.equal(store.isCleared(),true);
        assert.ok(!storage.values.get(experience.PROFILE_PREFIX+'CUST00001').includes('Private preference'));
        const fresh=experience.createExperienceStore(fakeStorage(storage.values),'CUST00001');
        assert.equal(fresh.load().consent,false);assert.equal(fresh.load().notes.length,0);
        ''')

    def test_unknown_corrupt_and_unconsented_saved_profiles_are_not_restored(self):
        self.run_module('''
        for(const bad of ['{broken',JSON.stringify({version:2,profile:{consent:true,focus:'home'}}),JSON.stringify({version:1,profile:{consent:false,focus:'home'}}),'x'.repeat(40001)]){
          const storage=fakeStorage(new Map([[experience.PROFILE_PREFIX+'CUST00001',bad]]));
          const store=experience.createExperienceStore(storage,'CUST00001');
          assert.equal(store.load().consent,false);assert.equal(store.load().focus,'flexibility');
          assert.equal(storage.values.has(experience.PROFILE_PREFIX+'CUST00001'),false);
        }
        const saved={version:1,profile:{consent:true,focus:'invented',style:'shaming',protected_category:'Health',notes:[null,{id:'bad<id>',text:'not allowed'},{id:'valid',text:'hello\\u0000',source:'model_inferred'}]}};
        const store=experience.createExperienceStore(fakeStorage(new Map([[experience.PROFILE_PREFIX+'CUST00001',JSON.stringify(saved)]])),'CUST00001');
        assert.equal(store.load().focus,'flexibility');assert.equal(store.load().style,'gentle');assert.equal(store.load().protected_category,'none');
        assert.deepEqual(store.load().notes.map(n=>n.source),['user']);assert.equal(store.load().notes[0].text,'hello');
        assert.throws(()=>experience.createExperienceStore(null,'../another-persona'));
        ''')

    def test_note_limits_and_user_text_have_no_implicit_interpretation(self):
        self.run_module('''
        const store=experience.createExperienceStore(null,'CUST00001');store.forget();
        const note=store.addNote({text:'<img src=x onerror=alert(1)>',source:'model_guessed'});
        assert.equal(note.source,'user');assert.equal(note.text,'<img src=x onerror=alert(1)>');
        assert.equal(store.load().focus,'flexibility');
        store.updateNote(note.id,'a'.repeat(700));assert.equal(store.load().notes[0].text.length,500);
        assert.throws(()=>store.addNote('   '));assert.throws(()=>store.updateNote('missing','text'));
        for(let i=1;i<50;i++)store.addNote('Note '+i);
        assert.throws(()=>store.addNote('Too many'));assert.equal(store.load().notes.length,50);
        ''')

    def test_memory_proposals_require_clear_first_person_statements(self):
        self.run_module('''
        assert.equal(experience.suggestedMemory('I want to save for a car.').value,'vehicle');
        assert.equal(experience.suggestedMemory('I prefer gentle coaching.').value,'gentle');
        assert.equal(experience.suggestedMemory('Do not cut dining out.').value,'Restaurants');
        assert.equal(experience.suggestedMemory('Haluan säästää autoa varten.','fi').value,'vehicle');
        assert.equal(experience.suggestedMemory('Jag vill spara till en resa.','sv').value,'travel');
        for(const text of ['Can I save for a car?','My friend says I want to save for a car.','I do not want to save for a car.','Maybe I want to save for a car.','I want to save for a car and travel.','I have a medical diagnosis.','You said I want to save for a car.','I prefer direct coaching, not gentle.','I prefer no gentle coaching.','I prefer gentle and direct coaching.','Jag föredrar rak coachning, inte varsam.'])assert.equal(experience.suggestedMemory(text),null,text);
        const proposal=experience.suggestedMemory('I want to save for a car because my salary changed.');
        assert.deepEqual(Object.keys(proposal).sort(),['field','text','value']);
        assert.ok(!proposal.text.includes('salary'));
        ''')

    def test_journal_uses_only_scoped_financial_events_and_no_invented_biography(self):
        self.run_module('''
        const overview={customer_id:'CUST00001',account_id:'ACC1',month:'2026-09',start:'2026-09-01',end:'2026-09-30'};
        const row=(ref,date,amount,kind,extra={})=>({transaction_ref:ref,date,amount_cents:amount,transaction_type:kind,customer_id:'CUST00001',account_id:'ACC1',category:'Restaurants',...extra});
        const rows=[row('salary','2026-09-29',200000,'salary'),row('rent','2026-09-05',-80000,'housing_payment'),row('large','2026-09-20',-10000,'purchase'),row('small','2026-09-22',-500,'purchase'),row('transfer','2026-09-24',-50000,'investment_deposit'),row('other-person','2026-09-23',-900000,'purchase',{customer_id:'CUST99999'}),row('other-account','2026-09-23',-900000,'purchase',{account_id:'ACC2'}),row('august','2026-08-23',-900000,'purchase')];
        const journal=experience.buildJournal(overview,rows,'en');
        assert.deepEqual(journal.map(x=>x.id),['salary','large','rent']);
        assert.ok(journal.every(x=>x.observed===true));assert.equal(journal[1].title,'Your largest recorded purchase');
        assert.equal(journal[1].amount_cents,-10000);assert.ok(!JSON.stringify(journal).match(/holiday|moved|job|happy|sad/i));
        assert.deepEqual(experience.buildJournal(null,rows),[]);
        assert.equal(experience.buildJournal(overview,rows,'fi')[0].title,'Tulo saapui');
        ''')

    def test_locales_cover_all_keys_and_html_hooks(self):
        html=(ROOT/'web'/'index.html').read_text()
        keys=re.findall(r'data-ux(?:-aria)?="([^"]+)"',html)
        self.run_module(f'''
        const keys={json.dumps(keys)};
        const base=Object.keys(experience.UX_MESSAGES.en).sort();
        for(const locale of ['en','fi','sv']){{
          assert.deepEqual(Object.keys(experience.UX_MESSAGES[locale]).sort(),base);
          for(const key of base)assert.ok(experience.ux(locale,key).trim());
          for(const key of keys)assert.notEqual(experience.ux(locale,key),key,locale+'.'+key);
        }}
        assert.equal(experience.ux('sv-FI','tour.step',{{step:2,total:3}}),'2 av 3');
        assert.equal(experience.ux('xx','home.greeting',{{name:'Alex'}}),'Hi, Alex.');
        assert.equal(experience.ux('en','coach.newQuestion'),'Start a new question');
        assert.equal(experience.ux('en','spending.home'),'Home & essentials');
        assert.ok(experience.ux('en','notebook.intro').includes('personal reflections'));
        for(const locale of ['en','fi','sv'])assert.notEqual(experience.ux(locale,'coach.newQuestion'),'coach.newQuestion');
        ''')
