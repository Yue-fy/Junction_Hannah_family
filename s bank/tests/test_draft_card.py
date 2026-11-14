"""Draft card (web/draft-card.js): parsing, validation, rendering and wiring."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

WEB = Path(__file__).resolve().parents[1] / 'web'

# A tiny DOM, enough for the markup our components render: well-formed tags, attribute
# selectors, descendant combinators, bubbling events and focus. Shared with test_topic_menu.
FAKE_DOM = r'''
const VOID=new Set(['input','br','img','meta','link','hr']);
const decode=s=>s.replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
const doc={activeElement:null};
class Text{constructor(t){this.text=t;this.parentNode=null;}get textContent(){return this.text;}}
class El{
  constructor(tag,attrs){this.tagName=tag.toUpperCase();this.attrs=new Map(attrs);this.childNodes=[];this.parentNode=null;this.listeners={};this._value=null;}
  get children(){return this.childNodes.filter(n=>n instanceof El);}
  getAttribute(n){return this.attrs.has(n)?this.attrs.get(n):null;}
  setAttribute(n,v){this.attrs.set(n,String(v));}
  removeAttribute(n){this.attrs.delete(n);}
  hasAttribute(n){return this.attrs.has(n);}
  get hidden(){return this.attrs.has('hidden');} set hidden(v){if(v)this.attrs.set('hidden','');else this.attrs.delete('hidden');}
  get disabled(){return this.attrs.has('disabled');} set disabled(v){if(v)this.attrs.set('disabled','');else this.attrs.delete('disabled');}
  get open(){return this.attrs.has('open');} set open(v){if(v)this.attrs.set('open','');else this.attrs.delete('open');}
  get value(){
    if(this._value!==null)return this._value;
    if(this.tagName==='SELECT'){const opts=this.querySelectorAll('option');const sel=opts.find(o=>o.hasAttribute('selected'))||opts[0];return sel?sel.getAttribute('value'):'';}
    return this.getAttribute('value')||'';
  }
  set value(v){this._value=String(v);}
  get textContent(){return this.childNodes.map(n=>n.textContent).join('');}
  set textContent(v){this.childNodes=[new Text(String(v))];}
  focus(){doc.activeElement=this;}
  addEventListener(t,f){(this.listeners[t]=this.listeners[t]||[]).push(f);}
  removeEventListener(t,f){this.listeners[t]=(this.listeners[t]||[]).filter(g=>g!==f);}
  dispatch(type,props={}){
    const ev={type,target:this,defaultPrevented:false,preventDefault(){this.defaultPrevented=true;},...props};
    for(let n=this;n;n=n.parentNode)for(const f of [...(n.listeners[type]||[])])f(ev);
    return ev;
  }
  descendants(){const out=[];const walk=n=>{for(const c of n.children){out.push(c);walk(c);}};walk(this);return out;}
  matches(sel){return sel.split(',').some(s=>matchComplex(this,s.trim()));}
  closest(sel){for(let n=this;n instanceof El;n=n.parentNode)if(n.matches(sel))return n;return null;}
  querySelectorAll(sel){return this.descendants().filter(e=>e.matches(sel));}
  querySelector(sel){return this.querySelectorAll(sel)[0]||null;}
}
function parts(sel){return sel.match(/(?:[^\s\[]+|\[[^\]]*\])+/g)||[];}
function matchCompound(el,c){
  const tag=c.match(/^[a-zA-Z][\w-]*/);
  if(tag&&el.tagName!==tag[0].toUpperCase())return false;
  for(const m of c.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g)){
    if(!el.hasAttribute(m[1]))return false;
    if(m[2]!==undefined&&el.getAttribute(m[1])!==m[2])return false;
  }
  return true;
}
function matchComplex(el,sel){
  const ps=parts(sel);if(!ps.length)return false;
  if(!matchCompound(el,ps[ps.length-1]))return false;
  let i=ps.length-2,n=el.parentNode;
  while(i>=0&&n instanceof El){if(matchCompound(n,ps[i]))i--;n=n.parentNode;}
  return i<0;
}
function parse(html){
  const root=new El('div',[]);let cur=root;
  const re=/<(\/?)([a-zA-Z][\w-]*)((?:\s+[\w:-]+(?:="[^"]*")?)*)\s*(\/?)>|([^<]+)/g;let m;
  while((m=re.exec(html))){
    if(m[5]!==undefined){const t=new Text(decode(m[5]));t.parentNode=cur;cur.childNodes.push(t);continue;}
    const tag=m[2].toLowerCase();
    if(m[1]){if(cur.tagName.toLowerCase()!==tag)throw new Error('Mismatched </'+tag+'> in '+cur.tagName);cur=cur.parentNode;continue;}
    const attrs=[...m[3].matchAll(/([\w:-]+)(?:="([^"]*)")?/g)].map(a=>[a[1],a[2]===undefined?'':decode(a[2])]);
    const el=new El(tag,attrs);el.parentNode=cur;cur.childNodes.push(el);
    if(!VOID.has(tag)&&!m[4])cur=el;
  }
  if(cur!==root)throw new Error('Unclosed '+cur.tagName);
  return root;
}
'''


def run_node(test_case, module_file, body):
    source = (WEB / module_file).read_text()
    script = ('import assert from "node:assert/strict";\n'
              'const m=await import("data:text/javascript;base64,"+Buffer.from(' + json.dumps(source) + ').toString("base64"));\n'
              + FAKE_DOM + body)
    result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True, timeout=60)
    test_case.assertEqual(result.returncode, 0, result.stderr)
    return result.stdout


@unittest.skipUnless(shutil.which('node'), 'Node is required for draft card checks')
class DraftCardTests(unittest.TestCase):
    def test_node_check(self):
        result = subprocess.run(['node', '--check', str(WEB / 'draft-card.js')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_parse_amount(self):
        run_node(self, 'draft-card.js', r'''
const cases={'1 200,50':120050,'1,200.50':120050,'1200':120000,'€1 200':120000,'1 200 €':120000,'1.200,50':120050,
 '1200.5':120050,'1200,5':120050,'1,200':120000,'0,50':50,'.5':50,'12 EUR':1200,'€ 99,99':9999,'1 200,00':120000,
 '1 234 567,89':123456789,'1,234,567.89':123456789,'-5':-500,'250':25000,' 250 ':25000,'0':0};
for(const [text,cents] of Object.entries(cases))assert.equal(m.parseAmount(text),cents,text);
for(const bad of ['','abc','1,2,3','12 34','1.2.3,4,5','1,234.567','1.234,567','12,345,67','€','1e5','1..2','12.345.6'])assert.equal(m.parseAmount(bad),null,bad);
assert.equal(m.parseAmount(12.5),1250);
assert.equal(m.parseAmount(null),null);
assert.equal(m.formatAmountInput(120050,'en'),'1,200.50');
assert.equal(m.formatAmountInput(120050,'fi'),'1 200,50');
assert.equal(m.formatAmountInput(120000,'sv'),'1 200');
assert.equal(m.formatAmountInput(5,'en'),'0.05');
assert.equal(m.formatAmountInput(1.5,'en'),'');
for(const cents of [0,5,99,120050,123456789,25000])for(const l of ['en','fi','sv'])assert.equal(m.parseAmount(m.formatAmountInput(cents,l)),cents,l+cents);
assert.equal(m.formatAmountDisplay(25000,'en'),'€250');
assert.equal(m.formatAmountDisplay(120050,'fi'),'1 200,50 €');
''')

    def test_parse_percent_and_number(self):
        run_node(self, 'draft-card.js', r'''
assert.equal(m.parsePercent('21,5'),21.5);
assert.equal(m.parsePercent('21.5'),21.5);
assert.equal(m.parsePercent('21,5 %'),21.5);
assert.equal(m.parsePercent('7%'),7);
assert.equal(m.parsePercent('0,125'),0.13);
for(const bad of ['','x','21,5,1','%','1.2.3'])assert.equal(m.parsePercent(bad),null,bad);
assert.equal(m.parseNumber('2,5'),2.5);
assert.equal(m.parseNumber('3'),3);
assert.equal(m.parseNumber('three'),null);
assert.equal(m.formatPercent(21.5,'en'),'21.5%');
assert.equal(m.formatPercent(21.5,'fi'),'21,5 %');
''')

    def test_validate_draft(self):
        run_node(self, 'draft-card.js', r'''
const spec={id:'g1',kind:'goal',fields:[
 {name:'name',label:'Name',type:'text',required:true,value:''},
 {name:'target',label:'Target',type:'amount',required:true,min:100,max:10000000,value:null},
 {name:'by',label:'By',type:'month',min:'2026-12',max:'2030-12',value:'2027-06'},
 {name:'day',label:'Day',type:'date',value:''},
 {name:'rate',label:'Rate',type:'percent',min:0,max:100,value:null},
 {name:'kind',label:'Kind',type:'select',options:[{value:'trip',label:'Trip'},'car'],value:'trip'},
 {name:'n',label:'N',type:'number',min:1,value:null}]};
let r=m.validateDraft(spec,{},'en');
assert.equal(r.valid,false);
assert.equal(r.errors.name.code,'required');
assert.equal(r.errors.target.code,'required');
assert.equal(r.values.by,'2027-06');
assert.equal(r.values.day,null);
assert.equal(r.values.kind,'trip');
assert.equal(r.errors.by,undefined);
r=m.validateDraft(spec,{name:' Trip ',target:'1 200,50',by:'2027-06',day:'2027-02-28',rate:'21,5',kind:'car',n:'2'},'fi');
assert.equal(r.valid,true,JSON.stringify(r.errors));
assert.deepEqual(r.values,{name:'Trip',target:120050,by:'2027-06',day:'2027-02-28',rate:21.5,kind:'car',n:2});
r=m.validateDraft(spec,{name:'x',target:'0,50',by:'2026-01',day:'2027-02-30',rate:'120',kind:'boat',n:'0'},'en');
assert.equal(r.errors.target.code,'min');
assert.match(r.errors.target.message,/€1/);
assert.equal(r.errors.by.code,'minDate');
assert.match(r.errors.by.message,/December 2026/);
assert.equal(r.errors.day.code,'date');
assert.equal(r.errors.rate.code,'max');
assert.equal(r.errors.kind.code,'select');
assert.equal(r.errors.n.code,'min');
r=m.validateDraft(spec,{name:'x',target:'lots',by:'2031-01',day:'',rate:'',kind:'trip',n:''},'sv');
assert.equal(r.errors.target.code,'amount');
assert.equal(r.errors.target.message,m.message('sv','draft.error.amount'));
assert.equal(r.errors.by.code,'maxDate');
assert.equal(m.validateDraft(spec,{name:'y'.repeat(201),target:12000},'en').errors.name.code,'tooLong');
assert.equal(m.validateDraft(spec,{name:'ok',target:12000},'en').values.target,12000);
''')

    def test_messages_have_identical_keys(self):
        run_node(self, 'draft-card.js', r'''
const en=Object.keys(m.DRAFT_CARD_MESSAGES.en).sort();
for(const l of ['fi','sv']){assert.deepEqual(Object.keys(m.DRAFT_CARD_MESSAGES[l]).sort(),en,l);
 for(const k of en){assert.ok(m.DRAFT_CARD_MESSAGES[l][k],l+k);
  assert.deepEqual((m.DRAFT_CARD_MESSAGES[l][k].match(/\{\w+\}/g)||[]).sort(),(m.DRAFT_CARD_MESSAGES.en[k].match(/\{\w+\}/g)||[]).sort(),k);}}
assert.equal(m.message('fi','draft.save'),'Tallenna');
assert.equal(m.message('de','draft.save'),'Save');
assert.equal(m.message('sv','draft.error.min',{min:'5'}),'Värdet måste vara minst 5.');
''')

    def test_render_escapes_and_modes(self):
        run_node(self, 'draft-card.js', r'''
const evil='<img src=x onerror=alert(1)>"\'&';
const spec={id:'g"1<',kind:'goal',title:evil,intro:evil,preview:evil,fields:[
 {name:'name',label:evil,type:'text',value:evil,help:evil,required:true},
 {name:'target',label:'Target',type:'amount',value:120050,required:true},
 {name:'by',label:'By',type:'month',value:'2027-06'},
 {name:'kind',label:'Kind',type:'select',options:[{value:'a"b',label:evil}],value:'a"b'}]};
const html=m.renderDraftCard(spec,'en');
assert.ok(!html.includes('<img'),'unescaped tag');
assert.ok(!html.includes('onerror=alert(1)>"'));
assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;&quot;&#39;&amp;'));
const root=parse(html);
const card=root.querySelector('[data-draft-card]');
assert.equal(card.getAttribute('data-draft-card'),'g"1<');
assert.equal(card.getAttribute('data-mode'),'review');
assert.equal(card.querySelector('[data-draft-view="target"]').textContent,'€1,200.50');
assert.equal(card.querySelector('[data-draft-view="by"]').textContent,'June 2027');
assert.equal(card.querySelector('[data-draft-view="kind"]').textContent,evil);
assert.equal(card.querySelector('[data-draft-input="target"]').value,'1,200.50');
assert.ok(card.querySelector('[data-draft-edit]').hidden);
assert.ok(!card.querySelector('[data-draft-change]').hidden);
assert.ok(card.querySelector('[data-draft-save]'));
assert.ok(card.querySelector('[data-draft-dismiss]'));
assert.equal(card.querySelector('[data-draft-preview]').textContent,evil);
assert.equal(card.querySelector('[data-draft-confirm]'),null);
const input=card.querySelector('[data-draft-input="name"]');
const described=input.getAttribute('aria-describedby').split(' ');
for(const id of described)assert.ok(root.querySelector('[id="'+id+'"]'),id);
assert.equal(input.getAttribute('aria-required'),'true');
assert.equal(card.querySelector('label').getAttribute('for'),input.getAttribute('id'));
const ids=root.descendants().map(e=>e.getAttribute('id')).filter(Boolean);
assert.equal(new Set(ids).size,ids.length,'ids unique');
const fi=parse(m.renderDraftCard({...spec,mode:'edit'},'fi')).querySelector('[data-draft-card]');
assert.equal(fi.getAttribute('data-mode'),'edit');
assert.ok(!fi.querySelector('[data-draft-edit]').hidden);
assert.ok(fi.querySelector('[data-draft-view]').hidden);
assert.ok(fi.querySelector('[data-draft-change]').hidden);
assert.equal(fi.querySelector('[data-draft-input="target"]').value,'1 200,50');
assert.equal(fi.querySelector('[data-draft-save]').textContent,'Tallenna');
assert.equal(fi.querySelector('[data-draft-view="by"]').textContent,'kesäkuu 2027');
const empty=parse(m.renderDraftCard({id:'p',kind:'profile',fields:[]},'sv')).querySelector('[data-draft-card]');
assert.equal(empty.querySelector('h3').textContent,'Ska jag anteckna det här?');
assert.ok(empty.querySelector('[data-draft-preview]').hidden);
''')

    def test_danger_has_second_step(self):
        run_node(self, 'draft-card.js', r'''
const spec={id:'del',kind:'goal',danger:true,title:'Delete goal?',fields:[{name:'name',label:'Goal',type:'text',value:'Trip'}]};
const root=parse(m.renderDraftCard(spec,'en'));
const card=root.querySelector('[data-draft-card]');
assert.equal(card.getAttribute('data-danger'),'true');
const confirm=card.querySelector('[data-draft-confirm]');
assert.ok(confirm&&confirm.hidden);
assert.equal(card.querySelector('[data-draft-save]').textContent,'Delete');
assert.equal(card.querySelector('[data-draft-confirm-yes]').textContent,'Yes, delete');
const saved=[];
m.attachDraftCard(card,{spec,locale:'en',onSave:v=>saved.push(v)});
card.querySelector('[data-draft-save]').dispatch('submit');
assert.equal(saved.length,0,'first tap only asks');
assert.ok(!confirm.hidden);
assert.ok(card.querySelector('[data-draft-actions]').hidden);
assert.equal(doc.activeElement,card.querySelector('[data-draft-confirm-yes]'));
card.querySelector('[data-draft-confirm-no]').dispatch('click');
assert.ok(confirm.hidden);
assert.equal(saved.length,0);
card.querySelector('[data-draft-save]').dispatch('submit');
card.querySelector('[data-draft-confirm-yes]').dispatch('click');
assert.deepEqual(saved,[{name:'Trip'}]);
''')

    def test_attach_wiring_and_idempotence(self):
        run_node(self, 'draft-card.js', r'''
const spec={id:'g1',kind:'goal',fields:[
 {name:'name',label:'Name',type:'text',value:'Trip',required:true},
 {name:'target',label:'Target',type:'amount',value:120000,required:true,min:100}]};
const root=parse('<div>'+m.renderDraftCard(spec,'en')+'</div>');
const card=root.querySelector('[data-draft-card]');
const saves=[],changes=[];let dismissed=0;
const detach=m.attachDraftCard(root,{spec,locale:'en',debounceMs:0,onSave:(v,raw)=>{saves.push([v,raw]);},onChange:v=>changes.push(v),onDismiss:()=>dismissed++});
assert.equal(typeof detach,'function');
assert.equal(m.attachDraftCard(root,{spec,locale:'en',debounceMs:0,onSave:(v,raw)=>{saves.push([v,raw]);},onChange:v=>changes.push(v),onDismiss:()=>dismissed++}),detach,'idempotent');
assert.equal(m.attachDraftCard(card,{spec,locale:'en',debounceMs:0,onSave:(v,raw)=>{saves.push([v,raw]);},onChange:v=>changes.push(v),onDismiss:()=>dismissed++}),detach);
card.querySelector('[data-draft-dismiss]').dispatch('click');
assert.equal(dismissed,1,'one listener only');
card.querySelector('[data-draft-change]').dispatch('click');
assert.equal(card.getAttribute('data-mode'),'edit');
assert.ok(!card.querySelector('[data-draft-edit]').hidden);
assert.equal(doc.activeElement,card.querySelector('[data-draft-input="name"]'));
const target=card.querySelector('[data-draft-input="target"]');
target.value='abc';
card.querySelector('[data-draft-save]').dispatch('submit');
assert.equal(saves.length,0);
assert.equal(target.getAttribute('aria-invalid'),'true');
const err=card.querySelector('[data-draft-error="target"]');
assert.ok(!err.hidden);
assert.equal(err.textContent,m.message('en','draft.error.amount'));
assert.equal(doc.activeElement,target);
target.value='1 500,25';
target.dispatch('input');
assert.equal(target.getAttribute('aria-invalid'),null);
assert.ok(err.hidden);
await new Promise(r=>setTimeout(r,5));
assert.deepEqual(changes.at(-1),{name:'Trip',target:150025});
assert.equal(card.querySelector('[data-draft-view="target"]').textContent,'€1,500.25');
assert.ok(m.updateDraftPreview(root,'€250 a month until June 2027'));
const preview=card.querySelector('[data-draft-preview]');
assert.equal(preview.textContent,'€250 a month until June 2027');
assert.ok(!preview.hidden);
m.updateDraftPreview(card,'');
assert.ok(preview.hidden);
card.querySelector('[data-draft-save]').dispatch('submit');
assert.equal(saves.length,1);
assert.deepEqual(saves[0][0],{name:'Trip',target:150025});
assert.deepEqual(saves[0][1],{name:'Trip',target:'1 500,25'});
assert.equal(card.getAttribute('aria-busy'),'true');
card.querySelector('[data-draft-save]').dispatch('submit');
assert.equal(saves.length,1,'no double save while busy');
m.setDraftStatus(card,'error');
assert.equal(card.querySelector('[data-draft-status]').textContent,m.message('en','draft.saveFailed'));
assert.ok(!card.querySelector('[data-draft-save]').disabled);
detach();
card.querySelector('[data-draft-dismiss]').dispatch('click');
assert.equal(dismissed,1,'detached');
const again=m.attachDraftCard(card,{spec,onDismiss:()=>dismissed++});
assert.notEqual(again,detach);
card.querySelector('[data-draft-dismiss]').dispatch('click');
assert.equal(dismissed,2);
assert.equal(m.attachDraftCard(parse('<p>x</p>'),{}),null);
// Promise-returning onSave drives the status automatically.
const r2=parse(m.renderDraftCard({...spec,id:'g2'},'fi'));const c2=r2.querySelector('[data-draft-card]');
m.attachDraftCard(c2,{spec,locale:'fi',onSave:()=>Promise.resolve()});
c2.querySelector('[data-draft-save]').dispatch('submit');
await new Promise(r=>setTimeout(r,0));
assert.equal(c2.getAttribute('data-status'),'saved');
assert.equal(c2.querySelector('[data-draft-status]').textContent,'Tallennettu');
assert.equal(m.draftAction(c2.querySelector('[data-draft-change]')),'change');
assert.equal(m.draftAction(c2.querySelector('h3')),null);
''')

    def test_module_never_fetches(self):
        source = (WEB / 'draft-card.js').read_text()
        for word in ('fetch(', 'XMLHttpRequest', 'localStorage', 'innerHTML'):
            self.assertNotIn(word, source)


if __name__ == '__main__':
    unittest.main()
