"""V5 lane NV: the app shell.

The tab bar is fixed to the bottom on every screen size (it used to jump to the top on wide screens), the
header is one compact row, the demo customer and month live behind a one-line chip, and page content sits in a
centred column that never hides behind the bar.

Static checks always run. The rendered checks run only when Python Playwright, Google Chrome and the demo
database (var/scoach.sqlite3) are available; they work on a copy of the database. Set SCOACH_SCREENSHOT_DIR to
keep a screenshot of every page at every size.
"""
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from html.parser import HTMLParser
from pathlib import Path

from scoach.api import Application, create_server

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
DATABASE = ROOT / 'var' / 'scoach.sqlite3'
CHROME = os.environ.get('SCOACH_CHROME', '/usr/bin/google-chrome')
SIZES = [(320, 640), (375, 812), (390, 844), (430, 932), (768, 1024), (1024, 768), (1280, 800), (1440, 900)]
TABS = [('home', 'home'), ('trends', 'spending'), ('coach', 'coach'), ('goals', 'goals'), ('profile', 'me')]


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.elements = [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs, [(t, a.get('id'), a.get('class')) for t, a in self.stack]))
        if tag not in ('meta', 'link', 'input', 'br', 'img', 'path', 'circle', 'option'):
            self.stack.append((tag, attrs))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


def _shell_css():
    css = (WEB / 'styles.css').read_text(encoding='utf-8')
    start = css.index('V5 shell (lane NV)')
    return css[start:css.index('/* End V5 shell */', start)]


class ShellMarkupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parser = _Collector()
        parser.feed((WEB / 'index.html').read_text(encoding='utf-8'))
        cls.elements = parser.elements

    def find(self, element_id):
        matches = [element for element in self.elements if element[1].get('id') == element_id]
        self.assertEqual(len(matches), 1, element_id)
        return matches[0]

    def test_one_tab_bar_with_five_tabs_in_order(self):
        tabs = [attrs['data-view'] for tag, attrs, parents in self.elements
                if tag == 'button' and 'data-view' in attrs and any(p[0] == 'nav' for p in parents)]
        self.assertEqual(tabs, [view for view, _ in TABS])

    def test_month_and_customer_live_in_one_sheet_behind_a_chip_and_the_profile_button(self):
        tag, attrs, _ = self.find('persona-panel')
        self.assertEqual(tag, 'dialog')
        _, _, month_parents = self.find('selected-month')
        self.assertIn(('dialog', 'persona-panel'), [(t, i) for t, i, _ in month_parents])
        _, _, persona_parents = self.find('persona')
        self.assertIn(('dialog', 'persona-panel'), [(t, i) for t, i, _ in persona_parents])
        for control in ('context-chip', 'persona-button'):
            tag, attrs, _ = self.find(control)
            self.assertEqual(tag, 'button')
            self.assertEqual(attrs.get('aria-controls'), 'persona-panel')
            self.assertEqual(attrs.get('aria-haspopup'), 'dialog')
        _, _, caption_parents = self.find('app-data-context')
        self.assertIn('context-chip', [i for _, i, _ in caption_parents])

    def test_shell_css_pins_the_bar_to_the_bottom_on_every_width(self):
        css = _shell_css()
        rules = re.findall(r'([^{}]*\.bottom-dock)\s*\{([^}]*)\}', css)
        self.assertTrue(rules)
        declarations = ' '.join(body for _, body in rules)
        self.assertIn('position: fixed', declarations)
        self.assertIn('bottom: 0', declarations)
        self.assertIn('env(safe-area-inset-bottom', declarations)
        self.assertNotIn('sticky', css)
        self.assertRegex(css, r'grid-template-columns:\s*repeat\(5,\s*minmax\(0,\s*1fr\)\)')
        self.assertRegex(css, r'white-space:\s*nowrap')
        self.assertIn('padding-bottom: calc(var(--dock-clearance)', css)

    def test_new_shell_copy_exists_in_all_three_languages(self):
        if not shutil.which('node'):
            self.skipTest('Node is required to load the i18n module')
        script = f"""
import assert from 'node:assert/strict';
import * as i18n from {json.dumps((WEB / 'i18n.js').as_uri())};
for (const key of ['v5.nv.sheetTitle', 'v5.nv.chipLabel']) {{
  for (const locale of i18n.SUPPORTED_LOCALES) assert.ok(i18n.MESSAGES[locale][key], locale + '.' + key);
  assert.notEqual(i18n.MESSAGES.fi[key], i18n.MESSAGES.en[key]);
  assert.notEqual(i18n.MESSAGES.sv[key], i18n.MESSAGES.en[key]);
}}
"""
        result = subprocess.run(['node', '--input-type=module', '--eval', script], cwd=ROOT,
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


def _browser_ready():
    if importlib.util.find_spec('playwright') is None:
        return False, 'Python Playwright is not installed'
    if not Path(CHROME).exists():
        return False, 'Google Chrome is not installed'
    if not DATABASE.is_file() or DATABASE.stat().st_size == 0:
        return False, 'Build the demo database first'
    try:
        with sqlite3.connect(DATABASE) as conn:
            conn.execute('SELECT 1 FROM transactions LIMIT 1')
    except sqlite3.Error:
        return False, 'Build the demo database first'
    return True, ''


READY, REASON = _browser_ready()

# Geometry of the shell after scrolling the page to its end.
GEOMETRY = r"""() => {
  const doc = document.documentElement, rect = el => el.getBoundingClientRect();
  window.scrollTo({top: doc.scrollHeight, behavior: 'instant'});
  const dock = rect(document.querySelector('.bottom-dock')), header = rect(document.querySelector('.app-header'));
  const view = [...document.querySelectorAll('main > section')].find(section => !section.hidden);
  let contentBottom = 0;
  for (const el of view.querySelectorAll('*')) {
    if (!el.checkVisibility({visibilityProperty: true, contentVisibilityAuto: true})) continue;
    const box = rect(el); if (!(box.width > 0 && box.height > 0)) continue;
    let bottom = box.bottom;
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement)
      if (getComputedStyle(a).overflowY !== 'visible') bottom = Math.min(bottom, rect(a).bottom);
    contentBottom = Math.max(contentBottom, bottom);
  }
  const tabs = [...document.querySelectorAll('.bottom-dock nav button')].map(button => {
    const label = button.querySelector('span:not([aria-hidden])');
    return {width: rect(button).width, lines: label.getClientRects().length, clipped: label.scrollWidth > label.clientWidth + 1,
            current: button.getAttribute('aria-current') === 'page', view: button.dataset.view};
  });
  window.scrollTo({top: 0, behavior: 'instant'});
  return {width: innerWidth, height: innerHeight, scrollWidth: doc.scrollWidth, dockTop: dock.top, dockBottom: dock.bottom,
          dockLeft: dock.left, dockRight: dock.right, dockPosition: getComputedStyle(document.querySelector('.bottom-dock')).position,
          headerBottom: rect(document.querySelector('.app-header')).bottom, headerHeight: header.height,
          contentBottom, viewWidth: rect(view).width, tabs};
}"""


@unittest.skipUnless(READY, REASON)
class ShellBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.tmp = tempfile.mkdtemp(prefix='scoach-v5nv-')
        database = Path(cls.tmp) / 'scoach.sqlite3'
        shutil.copyfile(DATABASE, database)
        cls.server = create_server(Application(database), port=0)
        cls.server.handle_error = lambda *args: None
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/'
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
        cls.shots = os.environ.get('SCOACH_SCREENSHOT_DIR')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def new_page(self, width, height, locale=None):
        context = self.browser.new_context(viewport={'width': width, 'height': height}, locale='en-US')
        self.addCleanup(context.close)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        self.addCleanup(lambda: self.assertEqual(errors, [], 'The page threw JavaScript errors'))
        if locale:
            context.add_init_script(f"localStorage.setItem('scoach.locale', {json.dumps(locale)})")
        page.goto(self.url + '#home')
        page.wait_for_selector('#current-balance:not(.skeleton)', state='attached', timeout=20000)
        page.wait_for_load_state('networkidle')
        return page

    def test_every_page_at_every_size_keeps_the_bar_at_the_bottom_without_overflow(self):
        for width, height in SIZES:
            page = self.new_page(width, height)
            for view, slug in TABS:
                with self.subTest(size=f'{width}x{height}', page=slug):
                    page.click(f'.bottom-dock nav [data-view="{view}"]')
                    page.wait_for_load_state('networkidle')
                    page.wait_for_timeout(250)
                    geometry = page.evaluate(GEOMETRY)
                    if self.shots:
                        page.screenshot(path=os.path.join(self.shots, f'v5-shell-{slug}-{width}x{height}.png'))
                    self.assertEqual(geometry['scrollWidth'], width, 'Horizontal overflow')
                    self.assertEqual(geometry['dockPosition'], 'fixed')
                    self.assertAlmostEqual(geometry['dockBottom'], height, delta=1, msg='Tab bar is not at the bottom')
                    self.assertGreater(geometry['dockTop'], geometry['headerBottom'], 'Tab bar is above the content')
                    self.assertLessEqual(geometry['dockTop'], height - 56)
                    self.assertAlmostEqual(geometry['dockLeft'], 0, delta=1)
                    self.assertAlmostEqual(geometry['dockRight'], width, delta=1)
                    self.assertLessEqual(geometry['headerHeight'], 64, 'Header is not compact')
                    self.assertLessEqual(geometry['contentBottom'], geometry['dockTop'] + 1, 'Content hides behind the tab bar')
                    tabs = geometry['tabs']
                    self.assertEqual(len(tabs), 5)
                    self.assertLess(max(t['width'] for t in tabs) - min(t['width'] for t in tabs), 1, 'Tabs are not equal')
                    self.assertTrue(all(t['lines'] == 1 and not t['clipped'] for t in tabs), 'A tab label wraps or is cut')
                    self.assertEqual([t['view'] for t in tabs if t['current']], [view])
                    # V5 design system: one 720px column below 1000px; from 1000px pages use the 1120px frame
                    # (Coach stays a reading column).
                    if view in ('trends', 'goals', 'profile'):
                        limit = 1120 if width >= 1000 else 720
                        self.assertLessEqual(geometry['viewWidth'], limit + 1, 'Pages stay in the frame')

    def test_tab_labels_fit_in_finnish_and_swedish_on_the_narrowest_phone(self):
        for locale in ('fi', 'sv'):
            with self.subTest(locale=locale):
                page = self.new_page(320, 640, locale=locale)
                geometry = page.evaluate(GEOMETRY)
                self.assertEqual(geometry['scrollWidth'], 320)
                self.assertTrue(all(t['lines'] == 1 and not t['clipped'] for t in geometry['tabs']), geometry['tabs'])

    def test_chip_and_profile_button_open_the_customer_and_month_sheet(self):
        for width, height in ((390, 844), (1280, 800)):
            with self.subTest(size=f'{width}x{height}'):
                page = self.new_page(width, height)
                page.click('.bottom-dock nav [data-view="goals"]')
                chip = page.locator('#context-chip')
                self.assertTrue(chip.is_visible())
                self.assertLessEqual(chip.bounding_box()['height'], 44, 'The context chip is one line')
                chip.click()
                page.wait_for_selector('#persona-panel[open]')
                self.assertTrue(page.is_visible('#selected-month'))
                self.assertTrue(page.is_visible('#persona'))
                self.assertEqual(page.get_attribute('#persona-button', 'aria-expanded'), 'true')
                if self.shots:
                    page.screenshot(path=os.path.join(self.shots, f'v5-shell-sheet-{width}x{height}.png'))
                page.keyboard.press('Escape')
                page.wait_for_selector('#persona-panel:not([open])', state='attached')
                page.wait_for_function("document.querySelector('#persona-button').getAttribute('aria-expanded') === 'false'")
                page.click('#persona-button')
                page.wait_for_selector('#persona-panel[open]')
                page.select_option('#selected-month', '2026-08')
                page.wait_for_function("document.querySelector('#app-data-context').textContent.includes('August 2026')")
                page.wait_for_selector('#persona-panel:not([open])', state='attached')  # choosing a month closes the sheet
                page.click('#context-chip')
                page.wait_for_selector('#persona-panel[open]')
                page.click('#persona-panel [data-view="journal"]')
                page.wait_for_selector('#persona-panel:not([open])', state='attached')
                self.assertEqual(page.evaluate("document.documentElement.dataset.currentView"), 'journal')

    def test_chip_is_not_repeated_on_coach_and_the_sheet_is_the_same_on_every_page(self):
        # V5 design system: the customer-and-month sheet shows Month from every entry point (QA wave 3).
        page = self.new_page(390, 844)
        page.click('.bottom-dock nav [data-view="coach"]')
        self.assertFalse(page.is_visible('#context-chip'))
        page.click('.bottom-dock nav [data-view="trends"]')
        page.click('#context-chip')
        page.wait_for_selector('#persona-panel[open]')
        self.assertTrue(page.is_visible('#selected-month'))
        self.assertTrue(page.is_visible('#persona'))
        page.select_option('#selected-month', '2026-08')
        page.wait_for_function("document.querySelector('.period-stepper select')?.value === '2026-08'")


if __name__ == '__main__':
    unittest.main()
