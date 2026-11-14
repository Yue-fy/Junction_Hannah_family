"""Coach topic menu (web/topic-menu.js): topics, messages, rendering and wiring."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_draft_card import run_node  # noqa: E402

WEB = Path(__file__).resolve().parents[1] / 'web'

# WP-F in docs/COACH_V3_PLAN.md: topic -> English starter questions, in order.
WP_F = {
    'Where my money goes': ['Where did my money go this month?', 'What are my Little leaks?',
                            'Which weekday do I spend the most?', 'Compare this month with last month'],
    'Spending room': ['What can I safely spend this week?', 'How much can I save this month?', 'Will I make it to payday?'],
    'About me': ['What kind of spender am I?', 'Update my money profile', 'What do you know about me?'],
    'Goals': ['Help me save for something', 'How are my goals doing?', 'What if I cut eating out by 20%?'],
    'Bills & debts': ['What are my recurring payments?', 'How much goes to my mortgage and loans?'],
    'Taxes': ['How much tax has been taken from my salary this year?', 'When do I get my tax refund?',
              'Help me prepare for back taxes', 'How much VAT was in my groceries?'],
    'Learn': ['What are the three baskets?', 'What is an emergency fund?', 'What is a tax card?'],
    'My year': ['Show my year in review'],
}


@unittest.skipUnless(shutil.which('node'), 'Node is required for topic menu checks')
class TopicMenuTests(unittest.TestCase):
    def test_node_check(self):
        result = subprocess.run(['node', '--check', str(WEB / 'topic-menu.js')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_topics_cover_wp_f_in_three_locales(self):
        run_node(self, 'topic-menu.js', 'const expected=' + json.dumps(WP_F) + ';\n' + r'''
const got=Object.fromEntries(m.TOPICS.map(t=>[m.message('en',t.key),t.questions.map(q=>m.message('en',q.key))]));
assert.deepEqual(got,expected);
assert.deepEqual(m.TOPICS.map(t=>t.id),['money','room','me','goals','bills','taxes','learn','year']);
const keys=new Set();
for(const t of m.TOPICS)for(const q of t.questions){
  assert.ok(!keys.has(q.key));keys.add(q.key);
  const texts=['en','fi','sv'].map(l=>m.TOPIC_MESSAGES[l][q.key]);
  for(const text of texts)assert.ok(text&&text.length>3,q.key);
  assert.equal(new Set(texts).size,3,'translated: '+q.key);
}
for(const t of m.TOPICS)for(const l of ['en','fi','sv'])assert.ok(m.TOPIC_MESSAGES[l][t.key],t.key);
assert.equal(m.topicQuestions('fi').length,23);
assert.equal(m.topicQuestions('sv')[0].text,'Vart tog mina pengar vägen den här månaden?');
''')

    def test_messages_have_identical_keys(self):
        run_node(self, 'topic-menu.js', r'''
const en=Object.keys(m.TOPIC_MESSAGES.en).sort();
for(const l of ['fi','sv']){assert.deepEqual(Object.keys(m.TOPIC_MESSAGES[l]).sort(),en,l);
 for(const k of en)assert.deepEqual((m.TOPIC_MESSAGES[l][k].match(/\{\w+\}/g)||[]),(m.TOPIC_MESSAGES.en[k].match(/\{\w+\}/g)||[]),k);}
assert.equal(m.message('xx','topic.browse'),'Browse topics');
assert.equal(m.message('fi','topic.count',{count:3}),'3 kysymystä');
''')

    def test_legacy_keys_match_existing_i18n(self):
        i18n = (WEB / 'i18n.js').read_text()
        source = (WEB / 'topic-menu.js').read_text()
        import re
        for key in re.findall(r"'(coach\.question\.\w+)'", source):
            self.assertIn('"' + key + '"', i18n, key)

    def test_render_sheet_and_button(self):
        run_node(self, 'topic-menu.js', r'''
for(const l of ['en','fi','sv']){
  const root=parse(m.renderTopicButton(l)+m.renderTopicSheet(l));
  const button=root.querySelector('[data-topic-open]');
  assert.equal(button.textContent,m.message(l,'topic.browse'));
  assert.equal(button.getAttribute('aria-controls'),m.TOPIC_SHEET_ID);
  assert.equal(button.getAttribute('aria-expanded'),'false');
  const sheet=root.querySelector('[data-topic-sheet]');
  assert.equal(sheet.getAttribute('id'),m.TOPIC_SHEET_ID);
  assert.ok(sheet.hidden);
  assert.equal(sheet.querySelector('[role="dialog"]').getAttribute('aria-modal'),'true');
  const asked=sheet.querySelectorAll('[data-topic-question]').map(b=>b.getAttribute('data-topic-question'));
  assert.deepEqual(asked,m.topicQuestions(l).map(q=>q.text));
  for(const b of sheet.querySelectorAll('[data-topic-question]'))assert.equal(b.textContent,b.getAttribute('data-topic-question'));
  const groups=sheet.querySelectorAll('details');
  assert.equal(groups.length,8);
  assert.deepEqual(groups.filter(g=>g.open).map(g=>g.getAttribute('data-topic')),['money']);
}
const taxes=parse(m.renderTopicSheet('en',{openTopic:'taxes',open:true})).querySelector('[data-topic-sheet]');
assert.ok(!taxes.hidden);
assert.deepEqual(taxes.querySelectorAll('details').filter(g=>g.open).map(g=>g.getAttribute('data-topic')),['taxes']);
const html=m.renderTopicSheet('en');
assert.ok(html.includes('data-topic-question="Bills &amp; debts"')===false);
assert.ok(html.includes('Bills &amp; debts'));
''')

    def test_attach_open_ask_close_and_idempotence(self):
        run_node(self, 'topic-menu.js', r'''
const root=parse('<div><textarea id="composer"></textarea>'+m.renderTopicButton('fi')+m.renderTopicSheet('fi')+'</div>');
const button=root.querySelector('[data-topic-open]');
const sheet=root.querySelector('[data-topic-sheet]');
const asked=[],closed=[];
const cb={onAsk:t=>asked.push(t),onClose:r=>closed.push(r)};
const detach=m.attachTopicMenu(root,cb);
assert.equal(typeof detach,'function');
assert.equal(m.attachTopicMenu(root,cb),detach,'idempotent');
assert.equal(m.attachTopicMenu(root,cb),detach);
button.dispatch('click');
assert.ok(!sheet.hidden);
assert.equal(button.getAttribute('aria-expanded'),'true');
const first=sheet.querySelector('details[open] [data-topic-question]');
assert.equal(doc.activeElement,first,'focus first item');
const q=sheet.querySelectorAll('[data-topic-question]')[1];
q.dispatch('click');
assert.deepEqual(asked,['Mitkä ovat arjen pikkumenoni?'],'asked once despite repeated attach');
assert.deepEqual(closed,['ask']);
assert.ok(sheet.hidden);
assert.equal(button.getAttribute('aria-expanded'),'false');
assert.equal(doc.activeElement,button,'focus returns');
button.dispatch('click');
first.dispatch('keydown',{key:'Escape'});
assert.ok(sheet.hidden);
assert.deepEqual(closed,['ask','escape']);
assert.equal(doc.activeElement,button);
button.dispatch('keydown',{key:'Escape'});
assert.equal(closed.length,2,'Escape when closed does nothing');
// Tab wraps inside the sheet.
button.dispatch('click');
const items=sheet.querySelectorAll('[data-topic-focusable]').filter(el=>{const d=el.closest('details');return !d||el.tagName==='SUMMARY'||d.open;});
const last=items[items.length-1];
const ev=last.dispatch('keydown',{key:'Tab'});
assert.ok(ev.defaultPrevented);
assert.equal(doc.activeElement,items[0]);
const ev2=items[0].dispatch('keydown',{key:'Tab',shiftKey:true});
assert.ok(ev2.defaultPrevented);
assert.equal(doc.activeElement,last);
const mid=items[2].dispatch('keydown',{key:'Tab'});
assert.ok(!mid.defaultPrevented,'normal tab inside');
sheet.querySelector('[data-topic-backdrop]').dispatch('click');
assert.ok(sheet.hidden);
assert.equal(closed.at(-1),'close');
detach.open();
assert.ok(detach.isOpen());
sheet.querySelector('button[data-topic-close]').dispatch('click');
assert.equal(closed.at(-1),'close');
assert.ok(sheet.hidden);
detach();
button.dispatch('click');
assert.ok(sheet.hidden,'detached');
assert.notEqual(m.attachTopicMenu(root,cb),detach,'re-attach after detach');
assert.equal(m.attachTopicMenu(parse('<p></p>'),cb),null);
assert.deepEqual(m.topicAction(q),{action:'ask',text:'Mitkä ovat arjen pikkumenoni?'});
assert.deepEqual(m.topicAction(button.querySelector('span')),{action:'open'});
assert.equal(m.topicAction(root.querySelector('textarea')),null);
assert.equal(m.topicKeyAction({key:'Esc'}),'close');
assert.equal(m.topicKeyAction({key:'a'}),null);
''')

    def test_module_never_fetches(self):
        source = (WEB / 'topic-menu.js').read_text()
        for word in ('fetch(', 'XMLHttpRequest', 'localStorage', 'innerHTML'):
            self.assertNotIn(word, source)

    def test_css_has_breakpoints_and_reduced_motion(self):
        css = (WEB / 'cards-v3.css').read_text()
        for token in ('@media (min-width: 1024px)', 'prefers-reduced-motion', '.topic-sheet', '.draft-card',
                      '.topic-button', 'min-height: 44px', 'var(--green)'):
            self.assertIn(token, css)
        self.assertEqual(css.count('{'), css.count('}'))


if __name__ == '__main__':
    unittest.main()
