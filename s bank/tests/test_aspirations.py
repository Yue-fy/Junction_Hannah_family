"""Exercise optional wishes through the real browser-local experience store."""
import json
from pathlib import Path
import shutil
import subprocess
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'web' / 'experience.js'


@unittest.skipUnless(shutil.which('node'), 'Node is needed to exercise the client module')
class AspirationTests(unittest.TestCase):
    def run_module(self, body):
        script = textwrap.dedent(f'''
            import assert from 'node:assert/strict';
            import * as experience from {json.dumps(MODULE.as_uri())};
            function storageFor(values=new Map()){{
              return {{values,writes:0,getItem:key=>values.get(key)??null,
                setItem(key,value){{this.writes++;values.set(key,value)}},
                removeItem:key=>values.delete(key)}};
            }}
            {body}
        ''')
        result = subprocess.run(
            ['node', '--input-type=module', '--eval', script], cwd=ROOT.parent,
            text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_title_only_wish_needs_no_amount_or_date_and_returns_detached_data(self):
        self.run_module('''
        const store=experience.createExperienceStore(storageFor(),'CUST00001');
        assert.deepEqual(store.load().wishes,[]);
        const wish=store.addWish({title:'  A little more freedom\\u0000  '});
        assert.deepEqual(Object.keys(wish).sort(),['contribution_cents','created_at','id','template','title']);
        assert.equal(wish.title,'A little more freedom');
        assert.equal(wish.template,'custom');assert.equal(wish.contribution_cents,null);
        assert.match(wish.id,/^wish-[a-zA-Z0-9_-]+$/);
        assert.ok(Number.isFinite(Date.parse(wish.created_at)));
        const original=store.load().wishes[0];
        wish.title='Mutated result';store.load().wishes[0].title='Mutated load';
        assert.deepEqual(store.load().wishes,[original]);
        assert.equal(store.load().notes.length,0);
        ''')

    def test_titles_templates_and_explicit_contributions_are_bounded(self):
        self.run_module('''
        const store=experience.createExperienceStore(storageFor(),'CUST00001');
        const long=store.addWish({title:'x'.repeat(90),template:' TRIP ',contribution_cents:0});
        assert.equal(long.title,'x'.repeat(80));assert.equal(long.template,'trip');
        assert.equal(long.contribution_cents,0);
        for(const template of ['custom','buffer','trip','vehicle','home','purchase']){
          const wish=store.addWish({title:template,template,contribution_cents:Number.MAX_SAFE_INTEGER});
          assert.equal(wish.template,template);assert.equal(wish.contribution_cents,Number.MAX_SAFE_INTEGER);
        }
        assert.equal(new Set(store.load().wishes.map(wish=>wish.id)).size,7);
        ''')

    def test_invalid_creation_and_updates_do_not_mutate_or_persist(self):
        self.run_module('''
        const storage=storageFor(),store=experience.createExperienceStore(storage,'CUST00001');
        store.setConsent(true);const wish=store.addWish({title:'Trip'});
        const before=store.load(),writes=storage.writes;
        for(const input of [null,[],12,'Trip',{}, {title:''},{title:' \\u0000 '},{title:12},
          {title:'Trip',template:'invented'}, {title:'Trip',template:12}]){
          assert.throws(()=>store.addWish(input));
        }
        for(const contribution_cents of [-1,0.5,'500',true,NaN,Infinity,Number.MAX_SAFE_INTEGER+1]){
          assert.throws(()=>store.addWish({title:'Trip',contribution_cents}));
          assert.throws(()=>store.updateWish(wish.id,{title:'Changed',contribution_cents}));
        }
        for(const patch of [null,[],12,{title:''},{title:null},{template:'invented'}]){
          assert.throws(()=>store.updateWish(wish.id,patch));
        }
        assert.throws(()=>store.updateWish('missing',{title:'Changed'}));
        assert.deepEqual(store.load(),before);assert.equal(storage.writes,writes);
        ''')

    def test_wish_limit_can_be_reused_after_deletion(self):
        self.run_module('''
        const store=experience.createExperienceStore(storageFor(),'CUST00001');
        for(let i=0;i<20;i++)store.addWish({title:'Wish '+i});
        const wishes=store.load().wishes;
        assert.throws(()=>store.addWish({title:'Too many'}));
        assert.deepEqual(store.load().wishes,wishes);
        const deleted=store.deleteWish(wishes[5].id);
        assert.equal(deleted.wishes.length,19);
        assert.ok(!store.load().wishes.some(wish=>wish.id===wishes[5].id));
        store.addWish({title:'New wish'});assert.equal(store.load().wishes.length,20);
        ''')

    def test_update_changes_only_editable_fields_and_can_clear_contribution(self):
        self.run_module('''
        const store=experience.createExperienceStore(storageFor(),'CUST00001');
        const wish=store.addWish({title:'My wish',id:'injected',created_at:'2000-01-01T00:00:00Z'});
        assert.notEqual(wish.id,'injected');assert.notEqual(wish.created_at,'2000-01-01T00:00:00Z');
        const updated=store.updateWish(wish.id,{title:'  My home  ',template:'home',contribution_cents:1500,
          id:'other-id',created_at:'2000-01-01T00:00:00Z',target_date:'2027-01-01',target_cents:500000});
        assert.deepEqual(updated,{...wish,title:'My home',template:'home',contribution_cents:1500});
        updated.title='Mutated';assert.equal(store.load().wishes[0].title,'My home');
        const cleared=store.updateWish(wish.id,{contribution_cents:null});
        assert.equal(cleared.contribution_cents,null);assert.equal(cleared.title,'My home');
        ''')

    def test_save_cannot_insert_replace_or_clear_wishes(self):
        self.run_module('''
        const store=experience.createExperienceStore(storageFor(),'CUST00001');
        store.save({wishes:[{title:'Unconfirmed wish'}]});
        assert.deepEqual(store.load().wishes,[]);
        const wish=store.addWish({title:'My choice'});
        store.save({focus:'travel',wishes:[]});
        assert.deepEqual(store.load().wishes,[wish]);assert.equal(store.load().focus,'travel');
        store.save({wishes:[{...wish,title:'Silently changed'}]});
        assert.deepEqual(store.load().wishes,[wish]);
        ''')

    def test_without_consent_wishes_survive_navigation_but_never_write_storage(self):
        self.run_module('''
        const storage=storageFor(),store=experience.createExperienceStore(storage,'CUST00001');
        const wish=store.addWish({title:'A trip'});
        store.updateWish(wish.id,{contribution_cents:2000});
        assert.equal(storage.writes,0);assert.equal(storage.values.size,0);
        const navigated=experience.createExperienceStore(storage,'CUST00001');
        assert.equal(navigated.load().wishes[0].contribution_cents,2000);
        navigated.setConsent(false);
        assert.equal(navigated.load().wishes.length,1,'Initial decline preserves this visit');
        const newVisit=experience.createExperienceStore(storageFor(storage.values),'CUST00001');
        assert.deepEqual(newVisit.load().wishes,[]);
        store.deleteWish(wish.id);assert.equal(storage.writes,0);
        assert.equal(store.isPersisted(),false);
        ''')

    def test_consent_persists_creation_edit_and_deletion_across_visits(self):
        self.run_module('''
        const storage=storageFor(),store=experience.createExperienceStore(storage,'CUST00001');
        const wish=store.addWish({title:'A trip'});
        store.setConsent(true);assert.equal(store.isPersisted(),true);
        const fresh=()=>experience.createExperienceStore(storageFor(storage.values),'CUST00001');
        assert.deepEqual(fresh().load().wishes,[wish]);
        store.updateWish(wish.id,{contribution_cents:2500});
        assert.equal(fresh().load().wishes[0].contribution_cents,2500);
        const later=store.addWish({title:'A cushion',template:'buffer'});
        assert.equal(fresh().load().wishes.length,2);
        store.deleteWish(wish.id);
        assert.deepEqual(fresh().load().wishes,[later]);
        ''')

    def test_personas_stay_isolated_when_wishes_are_edited_revoked_and_forgotten(self):
        self.run_module('''
        const storage=storageFor(),alex=experience.createExperienceStore(storage,'CUST00001'),
          kai=experience.createExperienceStore(storage,'CUST01331');
        const alexWish=alex.addWish({title:'Home'}),kaiWish=kai.addWish({title:'Freedom'});
        alex.setConsent(true);kai.setConsent(true);alex.markOnboarded();
        assert.throws(()=>alex.updateWish(kaiWish.id,{title:'Wrong persona'}));
        alex.deleteWish(kaiWish.id);assert.deepEqual(kai.load().wishes,[kaiWish]);
        alex.setConsent(false);assert.deepEqual(alex.load().wishes,[]);
        assert.equal(alex.isOnboarded(),true);assert.equal(alex.isCleared(),true);
        assert.equal(storage.values.has(experience.PROFILE_PREFIX+'CUST00001'),false);
        assert.deepEqual(kai.load().wishes,[kaiWish]);
        alex.addWish({title:'Session wish'});alex.forget();
        assert.deepEqual(alex.load().wishes,[]);assert.equal(alex.isOnboarded(),false);
        kai.forget();assert.deepEqual(kai.load().wishes,[]);
        const reopened=experience.createExperienceStore(storageFor(storage.values),'CUST01331');
        assert.deepEqual(reopened.load().wishes,[]);
        ''')

    def test_existing_v1_profiles_keep_preferences_and_notes_without_wishes(self):
        self.run_module('''
        const note={id:'note-old',text:'Sunday dinners',source:'user',created_at:'2026-09-01T12:00:00.000Z'};
        const saved={version:1,profile:{consent:true,focus:'home',style:'direct',notes:[note]}};
        const storage=storageFor(new Map([[experience.PROFILE_PREFIX+'CUST00001',JSON.stringify(saved)]]));
        const store=experience.createExperienceStore(storage,'CUST00001');
        assert.deepEqual(store.load().wishes,[]);assert.equal(store.load().focus,'home');
        assert.equal(store.load().style,'direct');assert.deepEqual(store.load().notes,[note]);
        store.addWish({title:'A place of my own'});
        const envelope=JSON.parse(storage.values.get(experience.PROFILE_PREFIX+'CUST00001'));
        assert.equal(envelope.version,1);assert.deepEqual(envelope.profile.notes,[note]);
        assert.equal(envelope.profile.wishes.length,1);
        ''')

    def test_corrupt_saved_wishes_are_normalized_without_losing_valid_preferences(self):
        self.run_module('''
        const saved={version:1,profile:{consent:true,focus:'home',wishes:[null,'string',[],
          {id:'invalid<id>',title:'Bad identity'}, {id:'empty',title:' \\u0000 '},
          {id:'wish-1',title:' Trip\\u0000 ',template:' TRIP ',contribution_cents:0,created_at:'2026-09-01T12:00:00+03:00'},
          {id:'wish-1',title:'Duplicate'},
          {id:'wish-2',title:'x'.repeat(100),template:'unknown',contribution_cents:-50,created_at:'broken',raw_chat:'private'},
          {id:'wish-3',title:'A buffer',contribution_cents:'100'},
          {id:'wish-4',title:'A home',contribution_cents:9007199254740992}
        ]}};
        const storage=storageFor(new Map([[experience.PROFILE_PREFIX+'CUST00001',JSON.stringify(saved)]]));
        const store=experience.createExperienceStore(storage,'CUST00001'),wishes=store.load().wishes;
        assert.equal(store.load().focus,'home');assert.equal(wishes.length,4);
        assert.deepEqual(wishes[0],{id:'wish-1',title:'Trip',template:'trip',contribution_cents:0,created_at:'2026-09-01T09:00:00.000Z'});
        assert.equal(wishes[1].title,'x'.repeat(80));assert.equal(wishes[1].template,'custom');
        assert.ok(wishes.slice(1).every(wish=>wish.contribution_cents===null));
        assert.ok(wishes.every(wish=>Number.isFinite(Date.parse(wish.created_at))));
        store.save({style:'direct'});
        assert.ok(!storage.values.get(experience.PROFILE_PREFIX+'CUST00001').includes('private'));
        for(const wishes of [null,{},'wrong',Array.from({length:25},(_,i)=>({id:'wish-'+i,title:'Wish '+i}))]){
          const profile={version:1,profile:{consent:true,wishes}};
          const restored=experience.createExperienceStore(storageFor(new Map([[experience.PROFILE_PREFIX+'CUST00001',JSON.stringify(profile)]])),'CUST00001');
          assert.equal(restored.load().wishes.length,Array.isArray(wishes)?20:0);
        }
        ''')

    def test_unavailable_storage_never_prevents_session_wishes_or_claims_persistence(self):
        self.run_module('''
        const denied={getItem(){throw Error('denied')},setItem(){throw Error('denied')},removeItem(){throw Error('denied')}};
        const store=experience.createExperienceStore(denied,'CUST00001');
        store.setConsent(true);const wish=store.addWish({title:'A trip'});
        store.updateWish(wish.id,{title:'A weekend away'});
        assert.equal(store.load().wishes[0].title,'A weekend away');assert.equal(store.isPersisted(),false);
        store.setConsent(false);assert.deepEqual(store.load().wishes,[]);assert.equal(store.isCleared(),false);
        ''')
