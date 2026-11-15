"""V5 lane TX screenshots (not run by unittest): the tax plan card off, the example open, the form, and the Me row.

Usage: python3 tests/browser/tax_plan_shots.py [base_url] [out_dir]
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8305/'
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else '/tmp/txshots')
SIZES = [(375, 812), (390, 844), (768, 1024), (1280, 800)]


def set_language(page, lang):
    page.evaluate("""lang => { const s = document.getElementById('language');
      if (s) { s.value = lang; s.dispatchEvent(new Event('change', {bubbles: true})); } }""", lang)
    page.wait_for_timeout(900)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
        for lang in ('en', 'fi'):
            for width, height in SIZES:
                page = browser.new_page(viewport={'width': width, 'height': height})
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(BASE + '#goals')
                page.wait_for_timeout(1800)
                set_language(page, lang)
                card = page.locator('#plans-root [data-plan="tax"]')
                card.wait_for()
                card.scroll_into_view_if_needed()
                page.evaluate("document.querySelector('#plans-root [data-plan=\"tax\"]').scrollIntoView({block: 'start'}); window.scrollBy(0, -70)")
                page.wait_for_timeout(300)
                page.screenshot(path=str(OUT / f'tax-off-{lang}-{width}x{height}.png'))
                page.locator('[data-plan-tax-example]').click()
                page.locator('.tax-example [data-plan-tax-own]').wait_for()
                page.evaluate("document.querySelector('.tax-example').scrollIntoView({block: 'start'}); window.scrollBy(0, -70)")
                page.wait_for_timeout(300)
                page.screenshot(path=str(OUT / f'tax-example-{lang}-{width}x{height}.png'))
                page.locator('#plans-root [data-plan="tax"]').screenshot(path=str(OUT / f'tax-example-card-{lang}-{width}x{height}.png'))
                if width in (390, 1280):
                    page.locator('.tax-example [data-plan-tax-own]').click()
                    page.wait_for_timeout(1200)
                    page.screenshot(path=str(OUT / f'tax-form-{lang}-{width}x{height}.png'))
                    page.keyboard.press('Escape')
                page.goto(BASE + '#me')
                page.wait_for_timeout(1800)
                set_language(page, lang)
                page.wait_for_timeout(800)
                row = page.locator('[data-profile-section="taxes"]')
                if row.count():
                    page.evaluate("document.querySelector('[data-profile-section=\"taxes\"]').scrollIntoView({block: 'start'}); window.scrollBy(0, -70)")
                    page.wait_for_timeout(300)
                    page.screenshot(path=str(OUT / f'me-tax-{lang}-{width}x{height}.png'))
                    overflow = page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
                    if overflow:
                        errors.append(f'horizontal overflow on Me {lang} {width}')
                page.close()
        browser.close()
    print('errors:', errors)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
