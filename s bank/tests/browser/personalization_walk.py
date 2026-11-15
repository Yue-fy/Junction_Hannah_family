"""Personalization walk in a real browser (lane G). Not run by unittest (file name does not start with test).

Clicks through every personalization behaviour the owner asked every V4 lane to keep (docs/PERSONALIZATION.md):
Me page with sources, "Things I noticed" Keep / Not this, "Add something" saving target changing the
safe-to-spend card, a profile fact from chat (review card, then steady mode banner and Turn off),
a goal from chat (prefilled form, saved only on submit), protected spending shown on Me, local preference
consent, and "Forget everything".

It starts its own server on a temporary copy of the demo database (never the original) with a scripted
AI coach, so the chat flows are reproducible without a model key. Each check prints PASS/FAIL; screenshots
go to --out. Exit status 1 if any check failed.

    cd "s bank" && python3 tests/browser/personalization_walk.py --out /tmp/pg-walk
    python3 tests/browser/personalization_walk.py --chrome /usr/bin/google-chrome --width 1280 --height 800
"""
import argparse
import json
import shutil
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scoach.api import Application, create_server  # noqa: E402

CUSTOMER = 'CUST00001'   # Alex
GOAL_MESSAGE = 'Help me save 2000 euros for a trip by the end of June 2027'
JOB_MESSAGE = 'I lost my job this month.'


class RoutedCoach:
    """Scripted AI coach: picks a script by the customer's latest message, one step per tool round."""

    def __init__(self, job_since):
        self.job_since = job_since

    def __call__(self, contents, **kwargs):
        texts = [i for i, c in enumerate(contents) if c['role'] == 'user' and any('text' in p for p in c['parts'])]
        last = texts[-1] if texts else 0
        message = ' '.join(p.get('text', '') for p in contents[last]['parts']).lower()
        step = sum(1 for c in contents[last + 1:] if any('functionResponse' in p for p in c['parts']))
        call = lambda tool, **args: {'role': 'model', 'parts': [{'functionCall': {'name': tool, 'args': args}}]}
        say = lambda text: {'role': 'model', 'parts': [{'text': text}]}
        if 'trip' in message:
            goal = {'name': 'Trip', 'target_cents': 200_000, 'target_date': '2027-06-30'}
            return [call('goal_plan', **goal), call('propose_action', kind='create_goal', params=goal),
                    say('I prepared a goal for you to review. Nothing is saved until you choose to.')][min(step, 2)]
        if 'lost my job' in message:
            entries = [{'key': 'life_event', 'value': json.dumps({'type': 'job_loss', 'since': self.job_since}), 'note': 'Told in chat'}]
            return [call('propose_profile_update', entries=entries),
                    say("I'm sorry, that is a lot to deal with. I prepared a note for you to review.")][min(step, 1)]
        return say('Hello, I am here to help.')


class Walk:
    def __init__(self, page, base, out):
        self.page, self.base, self.out, self.results, self.shot = page, base, Path(out), [], 0
        self.out.mkdir(parents=True, exist_ok=True)

    # -- helpers ------------------------------------------------------------------------------
    def api(self, method, path, body=None):
        url = self.base + path + ('&' if '?' in path else '?') + 'customer_id=' + CUSTOMER
        data = json.dumps({**(body or {}), 'customer_id': CUSTOMER}).encode() if method == 'POST' else None
        request = urllib.request.Request(url, data=data, method=method, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read())['data']
        except urllib.error.HTTPError as error:
            return json.loads(error.read()).get('error')

    def check(self, name, condition, detail=''):
        self.results.append((name, bool(condition)))
        print(('PASS ' if condition else 'FAIL ') + name + ('' if condition or not detail else '  -- ' + str(detail)[:300]), flush=True)
        return bool(condition)

    def snap(self, label):
        self.shot += 1
        self.page.screenshot(path=str(self.out / f'{self.shot:02d}-{label}.png'), full_page=True)

    def step(self, name, function):
        try:
            function()
        except Exception as error:  # a broken step must not hide the remaining checks
            self.check(name + ' (step ran)', False, repr(error))
            try:
                self.snap('error-' + name.replace(' ', '-')[:30])
                self.page.keyboard.press('Escape')
            except Exception:
                pass

    def nav(self, view):
        self.page.click(f'nav [data-view="{view}"]')
        self.page.wait_for_timeout(900)

    def profile(self):
        return self.api('GET', '/api/profile')

    def until_payday(self):
        return self.api('GET', '/api/safe-to-spend?horizon=until_payday')

    def save_draft(self):
        """Press Save in the open review dialog (and the second confirmation on danger cards)."""
        dialog = self.page.locator('#v3-dialog')
        dialog.locator('[data-draft-save]').first.click()
        self.page.wait_for_timeout(400)
        confirm = dialog.locator('[data-draft-confirm-yes]')
        if confirm.count() and confirm.first.is_visible():
            confirm.first.click()
        self.page.wait_for_timeout(1200)

    def ask(self, message):
        self.nav('coach')
        self.page.fill('#coach-input', message)
        self.page.click('#coach-send')
        self.page.wait_for_selector('[data-agent-action]', timeout=20000)
        self.page.wait_for_timeout(500)

    # -- the walk ------------------------------------------------------------------------------
    def run(self):
        page = self.page
        page.goto(self.base + '/')
        page.wait_for_selector('#current-balance:not(.skeleton)', timeout=20000)
        page.wait_for_timeout(800)
        self.api('POST', '/api/profile/forget', {'confirmed': True})   # start from an empty profile
        page.reload(); page.wait_for_selector('#current-balance:not(.skeleton)', timeout=20000)
        self.baseline = self.until_payday()
        self.step('me page', self.me_page)
        self.step('things I noticed', self.things_noticed)
        self.step('add saving target', self.add_saving_target)
        self.step('profile fact from chat', self.profile_from_chat)
        self.step('goal from chat', self.goal_from_chat)
        self.step('protected spending', self.protected_spending)
        self.step('local consent', self.local_consent)
        self.step('forget everything', self.forget_everything)

    def me_page(self):
        self.nav('profile')
        self.snap('me-empty')
        self.check('Me: empty profile offers the intro', self.page.locator('#profile-content [data-profile-onboarding]').count() > 0)
        self.check('Me: Add something and Forget everything are there',
                   self.page.locator('#profile-content [data-profile-add]').count() and self.page.locator('#profile-content [data-profile-forget]').count())

    def things_noticed(self):
        suggestions = self.profile()['suggestions']
        if not self.check('Things I noticed: suggestions offered', suggestions, 'none for this persona'):
            return
        keep = self.page.locator('#profile-content [data-suggestion-keep]').first
        kept_id = keep.get_attribute('data-suggestion-keep')
        keep.click(); self.page.wait_for_timeout(1500)
        profile = self.profile()
        entries = profile['profile']['entries']
        self.check('Keep saves the suggestion with its source', any(e['source'] == 'from_your_transactions' for e in entries), entries)
        self.check('Kept suggestion leaves the list', kept_id not in {s['id'] for s in profile['suggestions']})
        self.check('Kept entry shows on Me', self.page.locator('#profile-content [data-profile-entry]').count() >= 1)
        dismiss = self.page.locator('#profile-content [data-suggestion-dismiss]').first
        if dismiss.count():
            dismissed = dismiss.get_attribute('data-suggestion-dismiss')
            before = len(self.profile()['profile']['entries'])
            dismiss.click(); self.page.wait_for_timeout(1500)
            after = self.profile()
            self.check('Not this hides the suggestion', dismissed not in {s['id'] for s in after['suggestions']})
            self.check('Not this saves nothing', len(after['profile']['entries']) == before)
        self.snap('me-noticed')

    def add_saving_target(self):
        self.nav('profile')
        self.page.click('#profile-content [data-profile-add]')
        self.page.wait_for_timeout(500)
        option = self.page.locator('[data-profile-add-key="saving_rate_target_pct"]')
        self.check('Add something menu lists the saving target', option.count() > 0)
        option.first.click(); self.page.wait_for_timeout(700)
        field = self.page.locator('#v3-dialog [data-draft-input]').first
        if self.check('Saving target opens a review card', field.count() > 0, 'Add something option did nothing (lane F bug)'):
            field.fill('20')
            self.snap('add-saving-target')
            self.save_draft()
        else:
            self.page.keyboard.press('Escape')
            self.api('POST', '/api/profile/entries', {'key': 'saving_rate_target_pct', 'value': 20, 'confirmed': True})
            self.page.reload(); self.page.wait_for_selector('#current-balance:not(.skeleton)', timeout=20000)
        plan = self.until_payday()
        self.check('Saving target is saved and visible on Me',
                   any(e['key'] == 'saving_rate_target_pct' for e in self.profile()['profile']['entries']))
        self.check('Saving target changes safe-to-spend', plan['planned_saving_cents'] > 0 and plan['free_cents'] < self.baseline['free_cents'], plan.get('planned_saving_basis'))
        self.nav('trends')
        self.page.evaluate("document.querySelectorAll('#trends-view details').forEach(d => d.open = true)")
        self.page.wait_for_timeout(600)
        self.snap('spending-safe-card')

    def profile_from_chat(self):
        self.ask(JOB_MESSAGE)
        self.snap('chat-job-loss')
        self.check('Chat proposes, nothing saved yet', self.profile()['profile']['mode'] == 'normal')
        self.page.locator('[data-agent-action]').last.click()
        self.page.wait_for_timeout(700)
        self.check('Chat fact opens a review card', self.page.locator('#v3-dialog [data-draft-card]').count() > 0)
        self.snap('chat-review-card')
        self.save_draft()
        profile = self.profile()['profile']
        self.check('Saved with source "From our chat"', any(e['source'] == 'from_our_chat' for e in profile['entries']))
        self.check('Steady mode is on', profile['mode'] == 'steady')
        self.check('Steady mode raises the reserve', self.until_payday()['reserve_floor_cents'] > self.baseline['reserve_floor_cents'])
        self.nav('profile')
        banner = self.page.locator('#profile-content [data-profile-banner="steady"]')
        self.check('Me shows the steady banner', banner.count() > 0)
        self.snap('me-steady')
        banner.locator('[data-profile-mode-off]').click(); self.page.wait_for_timeout(1500)
        self.check('Turn off ends steady mode', self.profile()['profile']['mode'] == 'normal')
        self.check('Banner goes away', self.page.locator('#profile-content [data-profile-banner="steady"]').count() == 0)

    def goal_from_chat(self):
        before = len(self.api('GET', '/api/goals')['goals'])
        self.ask(GOAL_MESSAGE)
        self.page.locator('[data-agent-action]').last.click()
        self.page.wait_for_timeout(900)
        self.snap('goal-review')
        self.check('Goal from chat is prefilled for review', self.page.input_value('#goal-name') == 'Trip')
        self.check('Goal not saved before confirming', len(self.api('GET', '/api/goals')['goals']) == before)
        self.page.click('#goal-submit'); self.page.wait_for_timeout(1500)
        names = [g['name'] for g in self.api('GET', '/api/goals')['goals']]
        self.check('Goal saved after confirming', len(names) == before + 1 and 'Trip' in names, names)

    def protected_spending(self):
        self.api('POST', '/api/profile/entries', {'key': 'protected_categories', 'value': ['Restaurants'], 'confirmed': True})
        self.page.reload(); self.page.wait_for_selector('#current-balance:not(.skeleton)', timeout=20000)
        self.nav('profile')
        self.page.wait_for_timeout(600)
        text = self.page.inner_text('#profile-content')
        self.check('Me shows protected spending', 'Restaurants' in text or 'Ravintol' in text or 'Restaurang' in text)
        self.snap('me-protected')

    def local_consent(self):
        key = 'scoach.experience.v1.' + CUSTOMER
        opener = self.page.locator('[data-open-notebook]')
        if not self.check('Preferences can be opened', opener.count() > 0):
            return
        self.page.evaluate("document.querySelector('[data-open-notebook]').click()")
        self.page.wait_for_selector('#preference-consent', timeout=5000)
        self.check('Remember-on-this-browser is off by default', not self.page.is_checked('#preference-consent'))
        self.page.select_option('#preference-style', 'direct')
        self.page.click('#preferences-form [type="submit"]'); self.page.wait_for_timeout(400)
        self.check('Without consent nothing is stored in the browser', self.page.evaluate(f'localStorage.getItem({json.dumps(key)})') is None)
        self.page.check('#preference-consent')
        self.page.click('#preferences-form [type="submit"]'); self.page.wait_for_timeout(400)
        stored = self.page.evaluate(f'localStorage.getItem({json.dumps(key)})')
        self.check('With consent the preference is remembered', stored and '"direct"' in stored, stored)
        self.page.uncheck('#preference-consent')
        self.page.click('#preferences-form [type="submit"]'); self.page.wait_for_timeout(400)
        stored = self.page.evaluate(f'localStorage.getItem({json.dumps(key)})')
        self.check('Revoking consent clears it', not stored or '"consent":false' in stored, stored)
        self.page.keyboard.press('Escape')

    def forget_everything(self):
        self.nav('profile')
        self.page.click('#profile-content [data-profile-forget]')
        self.page.wait_for_timeout(500)
        self.check('Forget everything asks first', self.page.locator('#v3-dialog [data-draft-card]').count() > 0)
        self.save_draft()
        self.check('Profile is empty after forgetting', self.profile()['profile']['empty'])
        plan = self.until_payday()
        self.check('Safe-to-spend is back to the unpersonalised plan', plan['free_cents'] == self.baseline['free_cents'])
        self.snap('me-forgotten')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--db', default=str(ROOT / 'var' / 'scoach.sqlite3'), help='demo database to copy (read only)')
    parser.add_argument('--out', default=tempfile.gettempdir() + '/scoach-personalization-walk')
    parser.add_argument('--chrome', default=None, help='browser executable (default: Playwright chromium)')
    parser.add_argument('--width', type=int, default=390)
    parser.add_argument('--height', type=int, default=844)
    parser.add_argument('--locale', default='en', choices=['en', 'fi', 'sv'])
    args = parser.parse_args(argv)
    from playwright.sync_api import sync_playwright

    temp = tempfile.TemporaryDirectory()
    database = Path(temp.name) / 'walk.sqlite3'
    shutil.copyfile(args.db, database)
    from scoach.db import connect
    from scoach.ledger import account_scope
    conn = connect(database)
    try:
        job_since = account_scope(conn, CUSTOMER)['observed_end'][:7]
    finally:
        conn.close()
    server = create_server(Application(database, agent_transport=RoutedCoach(job_since)), port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = 'http://127.0.0.1:%s' % server.server_address[1]
    errors = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**({'executable_path': args.chrome} if args.chrome else {}), args=['--no-sandbox'])
            context = browser.new_context(viewport={'width': args.width, 'height': args.height})
            context.add_init_script('try { localStorage.setItem("scoach.locale", %s); } catch (e) {}' % json.dumps(args.locale))
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            walk = Walk(page, base, args.out)
            walk.run()
            walk.check('No script errors on the page', not errors, errors)
            browser.close()
    finally:
        server.shutdown(); server.server_close(); temp.cleanup()
    failed = [name for name, ok in walk.results if not ok]
    print('\n%d checks, %d failed. Screenshots: %s' % (len(walk.results), len(failed), args.out))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
