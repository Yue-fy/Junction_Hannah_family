"""V5 lane DS: the design system pass.

One button system (primary filled, secondary outlined pill, text link; centred labels; 44px targets), one
dialog pattern (bottom sheet below 600px, centred 560px dialog from 600px, title in the sticky header), one
width system (720px column; 1120px frame from 1000px) and a quiet language control in the header.

Static checks always run. Rendered checks need Python Playwright, Google Chrome and var/scoach.sqlite3; they
use a copy of the database. Set SCOACH_SCREENSHOT_DIR to keep screenshots.
"""
import importlib.util
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from scoach.api import Application, create_server

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
DATABASE = ROOT / 'var' / 'scoach.sqlite3'
CHROME = os.environ.get('SCOACH_CHROME', '/usr/bin/google-chrome')


class DesignSystemStaticTests(unittest.TestCase):
    def setUp(self):
        self.css = (WEB / 'design-v5.css').read_text(encoding='utf-8')
        self.html = (WEB / 'index.html').read_text(encoding='utf-8')

    def test_design_stylesheet_is_linked_last(self):
        links = re.findall(r'<link rel="stylesheet" href="/([^"]+)"', self.html)
        self.assertEqual(links[-1], 'design-v5.css')

    def test_tokens_live_in_a_marked_block_in_styles_css(self):
        styles = (WEB / 'styles.css').read_text(encoding='utf-8')
        start = styles.index('V5 design system (lane DS)')
        block = styles[start:styles.index('End V5 design system tokens', start)]
        for token in ('--ds-tap: 44px', '--ds-dialog-width: 560px', '--frame-column: 720px', '--frame-wide: 1120px'):
            self.assertIn(token, block)

    def test_buttons_centre_their_labels(self):
        for selector in ('.primary-button:not(#coach-send)', '.secondary-button'):
            rule = self.css[self.css.index(selector):]
            rule = rule[:rule.index('}')]
            self.assertIn('justify-content: center', rule, selector)
            self.assertIn('text-align: center', rule, selector)

    def test_customer_ids_are_not_shown(self):
        self.assertNotRegex(self.html, r'<option value="CUST\d+">[^<]*CUST')

    def test_experience_dialogs_put_their_title_in_the_header(self):
        app = (WEB / 'app.js').read_text(encoding='utf-8')
        self.assertIn('<div class="sheet-header"><h2 id="${id}-title">', app)


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

SMALL_TARGETS = r"""() => {
  const out = [];
  for (const el of document.querySelectorAll('main button, main summary, main select, .app-header button, .app-header select, dialog[open] button, dialog[open] select')) {
    if (!el.checkVisibility({visibilityProperty: true})) continue;
    if (el.closest('dialog:not([open])')) continue;
    const r = el.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0)) continue;
    if (r.height < 43.5 || r.width < 43.5) out.push(`${el.className || el.tagName} "${(el.innerText || '').trim().slice(0, 30)}" ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  return out;
}"""

LEFT_ALIGNED_BUTTONS = r"""() => [...document.querySelectorAll('main .primary-button, main .secondary-button')]
  .filter(el => el.checkVisibility() && el.id !== 'coach-send')
  .filter(el => getComputedStyle(el).justifyContent !== 'center')
  .map(el => el.innerText.trim())"""


@unittest.skipUnless(READY, REASON)
class DesignSystemBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.tmp = tempfile.mkdtemp(prefix='scoach-v5ds-')
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

    def new_page(self, width, height):
        context = self.browser.new_context(viewport={'width': width, 'height': height}, locale='en-US')
        self.addCleanup(context.close)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        self.addCleanup(lambda: self.assertEqual(errors, [], 'The page threw JavaScript errors'))
        page.goto(self.url + '#home')
        page.wait_for_selector('#current-balance:not(.skeleton)', state='attached', timeout=20000)
        page.wait_for_load_state('networkidle')
        return page

    def test_every_page_has_44px_targets_and_centred_buttons(self):
        for width, height in ((320, 640), (390, 844), (1280, 800)):
            page = self.new_page(width, height)
            for view in ('home', 'trends', 'coach', 'goals', 'profile'):
                with self.subTest(size=width, view=view):
                    page.click(f'.bottom-dock nav [data-view="{view}"]')
                    page.wait_for_load_state('networkidle')
                    page.wait_for_timeout(300)
                    self.assertEqual(page.evaluate(SMALL_TARGETS), [])
                    self.assertEqual(page.evaluate(LEFT_ALIGNED_BUTTONS), [])

    def test_dialogs_are_bottom_sheets_on_phones_and_centred_from_600px(self):
        for width, height in ((375, 812), (768, 1024), (1440, 900)):
            with self.subTest(size=width):
                page = self.new_page(width, height)
                page.click('#persona-button')
                page.wait_for_selector('#persona-panel[open]')
                page.wait_for_timeout(200)
                box = page.locator('#persona-panel').bounding_box()
                header = page.locator('#persona-panel .sheet-header h2').bounding_box()
                self.assertLess(header['y'] - box['y'], 40, 'Title sits in the header')
                if width < 600:
                    self.assertAlmostEqual(box['width'], width, delta=1)
                    self.assertAlmostEqual(box['y'] + box['height'], height, delta=1)
                else:
                    self.assertLessEqual(box['width'], 561)
                    self.assertAlmostEqual(box['x'] + box['width'] / 2, width / 2, delta=2)
                    self.assertAlmostEqual(box['y'] + box['height'] / 2, height / 2, delta=2)
                for row in page.locator('#persona-panel .personal-actions button').all():
                    self.assertGreaterEqual(row.bounding_box()['height'], 44)
                if self.shots:
                    page.screenshot(path=os.path.join(self.shots, f'v5-ds-sheet-{width}.png'))

    def test_topic_sheet_follows_the_dialog_pattern(self):
        for width, height in ((390, 844), (844, 390), (1280, 800)):
            with self.subTest(size=f'{width}x{height}'):
                page = self.new_page(width, height)
                page.click('.bottom-dock nav [data-view="coach"]')
                page.click('.topic-button')
                page.wait_for_selector('.topic-sheet__panel')
                page.wait_for_timeout(400)
                box = page.locator('.topic-sheet__panel').bounding_box()
                self.assertLessEqual(box['y'] + box['height'], height + 1, 'The sheet fits on screen')
                if width >= 600:
                    self.assertLessEqual(box['width'], 561)
                    self.assertAlmostEqual(box['x'] + box['width'] / 2, width / 2, delta=2)
                page.evaluate("document.querySelector('.topic-sheet__panel').scrollTop = 1e6")
                last = page.locator('.topic-group').last.bounding_box()
                self.assertLessEqual(last['y'] + last['height'], box['y'] + box['height'] + 1, 'Last group can be reached')

    def test_language_control_is_quiet_on_phones(self):
        page = self.new_page(375, 812)
        box = page.locator('#language').bounding_box()
        self.assertLessEqual(box['width'], 44.5)
        self.assertGreaterEqual(box['height'], 44)
        self.assertEqual(page.evaluate("document.querySelector('label[for=language]').textContent.trim() !== ''"), True)

    def test_wide_pages_line_up_with_the_header_from_1000px(self):
        page = self.new_page(1280, 800)
        logo = page.locator('.wordmark').bounding_box()['x']
        for view, section in (('trends', '#trends-view'), ('goals', '#goals-view'), ('profile', '#profile-view')):
            with self.subTest(view=view):
                page.click(f'.bottom-dock nav [data-view="{view}"]')
                page.wait_for_load_state('networkidle')
                self.assertAlmostEqual(page.locator(section).bounding_box()['x'], logo, delta=2)
        page.click('.bottom-dock nav [data-view="trends"]')
        page.wait_for_timeout(300)
        trend, forecast = page.locator('#history-details').bounding_box(), page.locator('#spending-forecast').bounding_box()
        self.assertAlmostEqual(trend['y'], forecast['y'], delta=2, msg='Trend and 30-day cards sit side by side')


if __name__ == '__main__':
    unittest.main()
