"""V5 fix lane CO screenshots (not run by unittest): Coach empty state, a typed exact question, a tapped
starter, the safe-to-spend card (Alex, Robin, Kai), at 320x640, 375x812, 390x844, 768x1024 and 1280x800.

Usage: python3 tests/browser/coach_v5f_shots.py [base_url] [out_dir] [steady_base_url]
steady_base_url: a server on a copy of the demo DB where Kai told the coach about a job loss (steady mode).
Prints layout facts (conversation height, scroll position of the question) and any page errors.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8505/'
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else '/tmp/coshots')
STEADY = sys.argv[3] if len(sys.argv) > 3 else BASE
SIZES = [(320, 640), (375, 812), (390, 844), (768, 1024), (1280, 800)]
PERSONAS = {'alex': 'CUST00001', 'robin': 'CUST00676', 'kai': 'CUST01331'}

FACTS = """() => {
  const r = id => { const n = document.getElementById(id); if (!n) return null; const b = n.getBoundingClientRect(); return [Math.round(b.top), Math.round(b.bottom)]; };
  const scroll = document.getElementById('coach-scroll');
  const users = [...document.querySelectorAll('#coach-response .coach-turn-user')];
  const last = users.at(-1);
  const lastTop = last ? Math.round(last.getBoundingClientRect().top - scroll.getBoundingClientRect().top) : null;
  return {scroll: r('coach-scroll'), form: r('coach-form'), mode: document.getElementById('coach-mode')?.textContent,
    modeVisible: getComputedStyle(document.getElementById('coach-mode')).display !== 'none',
    questionTopInScroll: lastTop, notice: Boolean(document.querySelector('.quick-notice')),
    overflow: document.documentElement.scrollWidth > window.innerWidth,
    profile: [...document.querySelectorAll('.answer-card__profile')].map(n => n.textContent),
    chips: [...document.querySelectorAll('#coach-response .answer-chip')].map(n => n.textContent)};
}"""


def set_language(page, lang):
    page.evaluate("""lang => { const s = document.getElementById('language');
      if (s && s.value !== lang) { s.value = lang; s.dispatchEvent(new Event('change', {bubbles: true})); } }""", lang)
    page.wait_for_timeout(700)


def set_persona(page, customer):
    page.evaluate("""id => { const s = document.getElementById('persona');
      if (s && s.value !== id) { s.value = id; s.dispatchEvent(new Event('change', {bubbles: true})); } }""", customer)
    page.wait_for_timeout(1800)


def open_coach(page, lang='en', persona='alex', base=None):
    page.goto((base or BASE) + '#coach')
    page.wait_for_timeout(1600)
    set_persona(page, PERSONAS[persona])
    page.evaluate("location.hash = '#coach'")
    page.wait_for_timeout(500)
    set_language(page, lang)


def ask_typed(page, text):
    page.fill('#coach-input', text)
    page.click('#coach-send')
    page.wait_for_selector('#coach-response .coach-turn', timeout=15000)
    page.wait_for_function("!document.getElementById('coach-pending').innerHTML", timeout=15000)
    page.wait_for_timeout(500)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    errors, facts = [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
        for width, height in SIZES:
            tag = f'{width}x{height}'
            page = browser.new_page(viewport={'width': width, 'height': height})
            page.on('pageerror', lambda e: errors.append(str(e)))
            open_coach(page)
            page.screenshot(path=str(OUT / f'empty-{tag}.png'))
            facts[f'empty-{tag}'] = page.evaluate(FACTS)
            ask_typed(page, 'What is safe for me to spend this week?')
            page.screenshot(path=str(OUT / f'typed-safe-{tag}.png'))
            facts[f'typed-safe-{tag}'] = page.evaluate(FACTS)
            page.locator('#coach-response .answer-chip').first.click()
            page.wait_for_function("document.querySelectorAll('#coach-response .coach-turn').length >= 2", timeout=15000)
            page.wait_for_timeout(600)
            page.screenshot(path=str(OUT / f'followup-{tag}.png'))
            facts[f'followup-{tag}'] = page.evaluate(FACTS)
            if width in (320, 390, 1280):
                ask_typed(page, 'how could i save more')
                page.screenshot(path=str(OUT / f'typed-save-{tag}.png'))
                facts[f'typed-save-{tag}'] = page.evaluate(FACTS)
                ask_typed(page, 'blorp the frobnicator')
                page.screenshot(path=str(OUT / f'typed-unknown-{tag}.png'))
                facts[f'typed-unknown-{tag}'] = page.evaluate(FACTS)
            if width in (320, 390):
                page.click('#topic-menu-root .topic-button')
                page.wait_for_timeout(500)
                page.screenshot(path=str(OUT / f'topics-{tag}.png'))
                page.keyboard.press('Escape')
            page.close()
        for persona in ('robin', 'kai'):
            for lang in ('en', 'fi', 'sv'):
                for width, height in ((390, 844), (320, 640)) if lang == 'en' else ((390, 844),):
                    tag = f'{persona}-{lang}-{width}x{height}'
                    page = browser.new_page(viewport={'width': width, 'height': height})
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    open_coach(page, lang, persona, STEADY if persona == 'kai' else BASE)
                    page.locator('#coach-starters [data-catalogue-question="room.week"], #coach-starters [data-coach-question="coach.question.safe"]').first.click()
                    page.wait_for_selector('#coach-response .answer-card', timeout=15000)
                    page.wait_for_timeout(600)
                    page.screenshot(path=str(OUT / f'safe-{tag}.png'))
                    facts[f'safe-{tag}'] = page.evaluate(FACTS)
                    card = page.locator('#coach-response .answer-card').last
                    card.screenshot(path=str(OUT / f'safe-card-{tag}.png'))
                    page.close()
        browser.close()
    print(json.dumps(facts, indent=1, ensure_ascii=False))
    print('page errors:', errors or 'none')


if __name__ == '__main__':
    main()
