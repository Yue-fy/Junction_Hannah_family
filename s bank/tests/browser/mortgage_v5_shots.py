"""V5 lane MG: screenshots of the mortgage plan (off card, example, what-ifs, saved plan) at four sizes.

Not run by unittest. Usage (server already running):
    python3 tests/browser/mortgage_v5_shots.py --base http://127.0.0.1:8306 --out /tmp/mg-shots [--saved]
--saved switches a plan on for Taylor through the API first: use it only against a throwaway database copy.
"""
import argparse
import json
import pathlib
import urllib.request

from playwright.sync_api import sync_playwright

SIZES = [(375, 812), (390, 844), (768, 1024), (1280, 800)]
TAYLOR = 'CUST00296'
PLAN = {'principal_cents': 21000000, 'loan_type': 'annuity', 'reference_rate': 'euribor_12m', 'reference_rate_bp': 230,
        'margin_bp': 60, 'remaining_months': 240, 'payment_day': 4}


def api(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, method=method, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def shoot(page, locator, path):
    """Element screenshot without the fixed bottom navigation painted over it."""
    page.add_style_tag(content='nav, .bottom-nav, .app-dock { visibility: hidden !important; }')
    locator.screenshot(path=path)
    page.evaluate("document.querySelectorAll('style').forEach(s => { if (s.textContent.includes('visibility: hidden !important')) s.remove(); })")


def open_goals(page, base, customer):
    page.goto(base + '/')
    page.wait_for_selector('#current-balance:not(.skeleton)', state='attached', timeout=20000)
    page.evaluate("""id => { const s = document.getElementById('persona'); s.value = id; s.dispatchEvent(new Event('change', {bubbles: true})); }""", customer)
    page.wait_for_timeout(1200)
    page.evaluate("document.querySelector('nav [data-view=\"goals\"]').click()")
    page.wait_for_selector('#plans-root [data-plan="mortgage"]', timeout=20000)
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(800)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8306')
    parser.add_argument('--out', default='/tmp/mg-shots')
    parser.add_argument('--saved', action='store_true')
    parser.add_argument('--locales', default='en,fi')
    args = parser.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.saved:
        api(args.base, 'POST', '/api/plans/mortgage', {'customer_id': TAYLOR, 'plan': PLAN, 'confirmed': True})
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
        for locale in args.locales.split(','):
            for width, height in SIZES:
                context = browser.new_context(viewport={'width': width, 'height': height}, device_scale_factor=1,
                                              has_touch=width < 1000)
                context.add_init_script('try { localStorage.setItem("scoach.locale", %s); } catch (e) {}' % json.dumps(locale))
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                tag = '%s-%dx%d' % (locale, width, height)
                if args.saved:
                    open_goals(page, args.base, TAYLOR)
                    card = page.locator('#plans-root [data-plan="mortgage"]')
                    card.scroll_into_view_if_needed()
                    shoot(page, card, str(out / ('saved-%s.png' % tag)))
                    page.locator('[data-plan-extra="20000"]').click()
                    page.wait_for_timeout(300)
                    shoot(page, card, str(out / ('saved-extra-%s.png' % tag)))
                else:
                    for customer, name in (('CUST00001', 'alex'), (TAYLOR, 'taylor')):
                        open_goals(page, args.base, customer)
                        card = page.locator('#plans-root [data-plan="mortgage"]')
                        card.scroll_into_view_if_needed()
                        if name == 'alex':
                            page.screenshot(path=str(out / ('off-%s.png' % tag)))
                        page.locator('[data-plan-example="mortgage"]').click()
                        page.wait_for_selector('[data-mg-example]', timeout=10000)
                        page.wait_for_timeout(300)
                        shoot(page, card, str(out / ('example-%s-%s.png' % (name, tag))))
                        if name == 'alex':
                            page.locator('[data-plan-extra="10000"]').click()
                            page.wait_for_timeout(300)
                            chart = page.locator('[data-mg-chart]')
                            chart.scroll_into_view_if_needed()
                            box = chart.bounding_box()
                            page.mouse.move(box['x'] + box['width'] * 0.35, box['y'] + box['height'] * 0.5)
                            page.wait_for_timeout(200)
                            shoot(page, card, str(out / ('example-whatif-%s.png' % tag)))
                            page.screenshot(path=str(out / ('example-viewport-%s.png' % tag)))
                overflow = page.evaluate('document.documentElement.scrollWidth - window.innerWidth')
                print(tag, 'overflow', overflow, 'errors', errors)
                context.close()
        browser.close()


if __name__ == '__main__':
    main()
