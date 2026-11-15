"""V4 lane F rendered checks: the Me tab's Add menu, tab routing, sheets, chat-reset notice, desktop grid and the
personalization flows that must keep working (profile entries, Things I noticed, steady mode, intro, forget,
goal editing, local preferences and the notebook).

Runs only when Python Playwright and Google Chrome are installed and the demo database has been built
(var/scoach.sqlite3). Each test class works on its own copy of that database, so nothing persistent changes.
"""
import importlib.util
import os
import shutil
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from scoach.api import Application, create_server

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / 'var' / 'scoach.sqlite3'
CHROME = os.environ.get('SCOACH_CHROME', '/usr/bin/google-chrome')


def _ready():
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


READY, REASON = _ready()


@unittest.skipUnless(READY, REASON)
class V4FixesBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.tmp = tempfile.mkdtemp(prefix='scoach-v4f-')
        database = Path(cls.tmp) / 'scoach.sqlite3'
        shutil.copyfile(DATABASE, database)
        cls.server = create_server(Application(database), port=0)
        cls.server.handle_error = lambda *args: None  # the browser closing a connection early is not a failure
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/'
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 390, 'height': 844}, locale='en-US')
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [], 'The page threw JavaScript errors')

    # ---------- helpers ----------
    def open(self, hash_='', customer=None):
        self.page.goto(self.url + hash_)
        self.page.wait_for_selector('#current-balance:not(.skeleton)', state='attached', timeout=20000)
        if customer:
            self.page.click('#persona-button')
            self.page.select_option('#persona', customer)
            self.page.wait_for_function('document.querySelector("#current-balance").textContent !== "—"', timeout=20000)
        self.page.wait_for_timeout(300)

    def tab(self, view):
        self.page.click(f'nav [data-view="{view}"]')
        self.page.wait_for_timeout(250)

    def open_me(self):
        self.tab('profile')
        self.page.wait_for_selector('#profile-content[aria-busy="false"] [data-profile-add]')

    def sheet_title(self):
        return self.page.text_content('#v3-dialog-title').strip()

    def save_sheet(self):
        self.page.click('#v3-dialog [data-draft-save]')
        self.page.wait_for_selector('#v3-dialog', state='hidden', timeout=10000)
        self.page.wait_for_selector('#profile-content[aria-busy="false"]', timeout=10000)
        self.page.wait_for_timeout(300)

    # ---------- Me: Add something ----------
    def test_every_add_menu_option_opens_its_form_with_title_and_visible_save(self):
        self.open()
        self.open_me()
        self.page.click('[data-profile-add]')
        keys = self.page.eval_on_selector_all('#v3-dialog [data-profile-add-key]', 'nodes => nodes.map(node => node.dataset.profileAddKey)')
        self.assertGreaterEqual(len(keys), 13)
        self.assertEqual(self.sheet_title(), 'What would you like to add?')
        for key in keys:
            if not self.page.is_visible('#v3-dialog'):
                self.page.click('[data-profile-add]')
            self.page.click(f'#v3-dialog [data-profile-add-key="{key}"]')
            self.page.wait_for_selector('#v3-dialog [data-draft-card]', timeout=5000)
            self.assertTrue(self.sheet_title(), key + ' form has no title in the sheet header')
            self.assertFalse(self.page.is_visible('#v3-dialog .draft-card__title'), key + ' repeats its title inside the sheet')
            save = self.page.query_selector('#v3-dialog [data-draft-save]')
            box = save.bounding_box()
            self.assertIsNotNone(box, key)
            self.assertLessEqual(box['y'] + box['height'], 844, key + ': Save is cut off')
            self.page.keyboard.press('Escape')
            self.page.wait_for_selector('#v3-dialog', state='hidden')

    def test_profile_entries_add_edit_delete_and_forget_keep_working(self):
        self.open(customer='CUST00676')
        self.open_me()
        # Add a note through the Add menu.
        self.page.click('[data-profile-add]')
        self.page.click('#v3-dialog [data-profile-add-key="note"]')
        self.page.fill('#v3-dialog [data-draft-input="value"]', 'Saving for a bike')
        self.save_sheet()
        card = self.page.locator('#profile-content [data-profile-edit]').first
        self.assertIn('Saving for a bike', self.page.text_content('#profile-content'))
        self.assertIn('You told me', self.page.text_content('#profile-content'))
        # Edit opens straight into the form.
        card.click()
        self.page.wait_for_selector('#v3-dialog [data-draft-input="value"]:visible')
        self.page.fill('#v3-dialog [data-draft-input="value"]', 'Saving for a cargo bike')
        self.save_sheet()
        self.assertIn('Saving for a cargo bike', self.page.text_content('#profile-content'))
        # Delete asks once, then removes it.
        self.page.locator('#profile-content [data-profile-delete]').first.click()
        self.page.click('#v3-dialog [data-draft-save]')
        confirm = self.page.query_selector('#v3-dialog [data-draft-confirm-yes]')
        if confirm and confirm.is_visible():
            confirm.click()
        self.page.wait_for_selector('#v3-dialog', state='hidden', timeout=10000)
        self.page.wait_for_timeout(500)
        self.assertNotIn('cargo bike', self.page.text_content('#profile-content'))
        # Forget everything empties the profile.
        self.page.click('[data-profile-add]')
        self.page.click('#v3-dialog [data-profile-add-key="household"]')
        self.page.wait_for_selector('#v3-dialog [data-draft-card]')
        self.page.keyboard.press('Escape')
        self.page.click('[data-profile-forget]')
        self.page.click('#v3-dialog [data-draft-save]')
        confirm = self.page.query_selector('#v3-dialog [data-draft-confirm-yes]')
        if confirm and confirm.is_visible():
            confirm.click()
        self.page.wait_for_selector('#v3-dialog', state='hidden', timeout=10000)
        self.page.wait_for_selector('#profile-content [data-profile-empty]', timeout=10000)

    def test_life_event_in_local_date_format_turns_on_steady_mode_and_can_be_turned_off(self):
        self.open(customer='CUST00756')
        self.open_me()
        self.page.click('[data-profile-add]')
        self.page.click('#v3-dialog [data-profile-add-key="life_event"]')
        self.page.select_option('#v3-dialog [data-draft-input="type"]', 'job_loss')
        date_input = self.page.locator('#v3-dialog [data-draft-input="since"]')
        self.assertEqual(date_input.get_attribute('type'), 'text')
        self.assertEqual(date_input.get_attribute('placeholder'), 'dd/mm/yyyy')
        date_input.fill('15/09/2026')
        self.save_sheet()
        self.page.wait_for_selector('[data-profile-banner="steady"]', timeout=10000)
        self.page.click('[data-profile-banner="steady"] [data-profile-mode-off]')
        self.page.wait_for_selector('[data-profile-banner="steady"]', state='detached', timeout=10000)

    def test_things_i_noticed_keep_and_not_this(self):
        self.open(customer='CUST00296')
        self.open_me()
        keep = self.page.query_selector_all('[data-suggestion-keep]')
        if len(keep) < 2:
            self.skipTest('This customer has fewer than two suggestions')
        first_id = keep[0].get_attribute('data-suggestion-keep')
        second_id = keep[1].get_attribute('data-suggestion-keep')
        keep[0].click()
        self.page.wait_for_selector(f'[data-suggestion-keep="{first_id}"]', state='detached', timeout=10000)
        self.page.click(f'[data-suggestion-dismiss="{second_id}"]')
        self.page.wait_for_selector(f'[data-suggestion-dismiss="{second_id}"]', state='detached', timeout=10000)
        self.assertTrue(self.page.query_selector('#profile-content [data-profile-edit]'), 'Kept suggestion is not shown as an entry')

    def test_start_intro_again_opens_the_intro_in_coach(self):
        self.open(customer='CUST01331')
        self.open_me()
        self.page.click('#profile-content [data-profile-onboarding]')
        self.page.wait_for_function('location.hash === "#coach"')
        self.page.wait_for_selector('#onboarding-root :is(button, input, fieldset)', timeout=10000)

    # ---------- Goals and local preferences ----------
    def test_goal_edit_opens_as_a_form_with_local_date_and_saves(self):
        self.open()
        self.tab('goals')
        self.page.click('[data-goal-edit]')
        name = self.page.locator('#v3-dialog [data-draft-input="name"]')
        self.assertTrue(name.is_visible(), 'Edit must open as a form, not read-only tiles')
        self.assertRegex(self.page.input_value('#v3-dialog [data-draft-input="target_date"]'), r'^\d{2}/\d{2}/\d{4}$')
        self.page.fill('#v3-dialog [data-draft-input="target_cents"]', '3200')
        self.page.click('#v3-dialog [data-draft-save]')
        self.page.wait_for_selector('#v3-dialog', state='hidden', timeout=10000)
        self.page.wait_for_function('document.querySelector("#goals-list").textContent.includes("3,200")', timeout=10000)

    def test_goal_date_uses_finnish_format(self):
        self.open()
        self.page.select_option('#language', 'fi')
        self.tab('goals')
        self.page.click('[data-goal-edit]')
        self.assertRegex(self.page.input_value('#v3-dialog [data-draft-input="target_date"]'), r'^\d{1,2}\.\d{1,2}\.\d{4}$')
        self.assertEqual(self.page.get_attribute('#v3-dialog [data-draft-input="target_date"]', 'placeholder'), 'pp.kk.vvvv')

    def test_local_preferences_consent_and_notebook_keep_working(self):
        self.open()
        self.page.click('#persona-button')
        self.page.click('#persona-panel [data-open-notebook]')
        self.page.wait_for_selector('#preferences-form')
        self.page.check('#preference-consent')
        self.page.click('#preferences-form [type="submit"]')
        self.assertTrue(self.page.evaluate('Object.keys(localStorage).some(key => localStorage.getItem(key)?.includes("consent"))'))
        self.page.fill('#note-text', 'Keep weekends free for family')
        self.page.click('#note-form [type="submit"]')
        self.page.wait_for_selector('#notebook-dialog', state='hidden')
        self.assertIn('Keep weekends free for family', self.page.text_content('#notebook-content'))

    # ---------- Routing and chat ----------
    def test_tabs_have_addresses_and_back_forward_reload_stay_in_the_app(self):
        self.open()
        self.assertTrue(self.page.url.endswith('#home'))
        for view, address in [('trends', '#spending'), ('coach', '#coach'), ('goals', '#goals'), ('profile', '#me')]:
            self.tab(view)
            self.assertTrue(self.page.url.endswith(address), self.page.url)
        self.page.go_back()
        self.page.wait_for_function('!document.querySelector("#goals-view").hidden')
        self.page.go_back()
        self.page.wait_for_function('!document.querySelector("#coach-view").hidden')
        self.page.go_forward()
        self.page.wait_for_function('!document.querySelector("#goals-view").hidden')
        self.page.reload()
        self.page.wait_for_selector('#current-balance:not(.skeleton)', state='attached')
        self.assertFalse(self.page.is_hidden('#goals-view'))
        self.assertTrue(self.page.is_hidden('#home-view'))

    def test_month_change_tells_the_customer_the_chat_restarted(self):
        self.open('#coach')
        self.assertTrue(self.page.is_hidden('#coach-reset-notice'))
        self.page.fill('#coach-input', 'What is safe for me to spend this week?')
        self.page.click('#coach-send')
        self.page.wait_for_selector('#coach-response > *', timeout=20000)
        self.page.wait_for_function('!document.querySelector("#coach-send").disabled', timeout=20000)
        self.page.click('#coach-scope-button')
        self.page.select_option('#coach-month', '2026-08')
        self.page.wait_for_selector('#coach-reset-notice:not([hidden])', timeout=10000)
        self.assertIn('August 2026', self.page.text_content('#coach-reset-notice'))

    # ---------- Spending and desktop ----------
    def test_spending_has_one_period_control_and_readable_chart_months(self):
        self.open('#spending')
        self.assertTrue(self.page.is_hidden('#selected-month'), 'Spending shows a second month control')
        self.assertTrue(self.page.is_visible('#spending-month'))
        self.assertTrue(self.page.is_hidden('#spending-selection'), 'Empty selection box is shown')
        self.page.click('[data-period-step="-1"]')
        self.page.wait_for_function('document.querySelector("#spending-month")?.value === "2026-08"', timeout=10000)
        self.page.evaluate('document.querySelector("#history-details").open = true')
        self.page.wait_for_selector('#trend-chart .chart-note', state='attached', timeout=10000)
        labels = self.page.eval_on_selector_all('#trend-chart .chart-note', 'nodes => nodes.map(node => node.textContent)')
        self.assertTrue(labels)
        for label in labels:
            self.assertNotRegex(label, r'\d{2}-\d{2}|^-\d', 'Chart month labels must be month names')
        headings = self.page.eval_on_selector_all('#trends-view details > summary', 'nodes => nodes.map(node => node.textContent.trim())')
        inner = self.page.eval_on_selector_all('#trends-view details h2', 'nodes => nodes.map(node => node.textContent.trim())')
        self.assertFalse(set(headings) & set(inner), 'An accordion repeats its title as a heading')

    def test_desktop_year_banner_spans_the_home_grid(self):
        self.page.set_viewport_size({'width': 1280, 'height': 800})
        self.open()
        self.page.wait_for_timeout(800)
        banner = self.page.query_selector('#year-banner > *')
        if not banner:
            self.skipTest('No year banner for this customer')
        main = self.page.query_selector('#home-view').bounding_box()
        self.assertGreater(banner.bounding_box()['width'], main['width'] * 0.9)
