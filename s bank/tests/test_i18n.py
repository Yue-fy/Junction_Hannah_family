import json
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "web" / "i18n.js"


class I18nModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("Node is required to exercise the real browser module")

    def run_module(self, body):
        script = textwrap.dedent(
            f"""
            import assert from 'node:assert/strict';
            import * as i18n from {json.dumps(MODULE.as_uri())};
            {body}
            """
        )
        result = subprocess.run(
            ["node", "--input-type=module", "--eval", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_normalizes_supported_browser_tags_and_returns_intl_locale(self):
        """Catches regressions that mistake Finnish-Swedish tags for unsupported languages."""
        self.run_module(
            """
            assert.deepEqual(i18n.SUPPORTED_LOCALES, ['en', 'fi', 'sv']);
            assert.equal(i18n.normalizeLocale('fi-FI'), 'fi');
            assert.equal(i18n.normalizeLocale('FI_fi'), 'fi');
            assert.equal(i18n.normalizeLocale('sv-FI'), 'sv');
            assert.equal(i18n.normalizeLocale('sv-SE'), 'sv');
            assert.equal(i18n.normalizeLocale('de-DE'), 'en');
            assert.equal(i18n.normalizeLocale(null), 'en');
            assert.equal(i18n.intlLocale('fi'), 'fi-FI');
            assert.equal(i18n.intlLocale('sv'), 'sv-FI');
            assert.equal(i18n.intlLocale('en'), 'en-FI');
            """
        )

    def test_catalogs_have_matching_nonblank_keys_for_core_customer_journey(self):
        """Catches shipping a language selector with missing navigation or disclosure copy."""
        required = [
            "language.label", "nav.home", "nav.trends", "nav.goals",
            "common.observed", "common.scenario", "home.title", "period.month.label",
            "period.range.label", "period.range.3", "period.range.24", "money.balance",
            "money.income", "basket.regular", "basket.irregular", "basket.everyday",
            "basket.saving", "forecast.title", "trends.title", "goals.title",
            "coach.title", "coach.input.label", "loading.account", "empty.transactions",
            "error.network", "error.period", "action.retry", "safe.title",
            "safe.disclaimer", "investment.title", "investment.limitation",
        ]
        self.run_module(
            f"""
            const required = {json.dumps(required)};
            const base = Object.keys(i18n.MESSAGES.en).sort();
            assert.ok(base.length >= 75, `catalog is too small to cover the core journey: ${{base.length}}`);
            for (const locale of i18n.SUPPORTED_LOCALES) {{
              const entries = i18n.MESSAGES[locale];
              assert.deepEqual(Object.keys(entries).sort(), base, `${{locale}} key set differs from English`);
              for (const [key, value] of Object.entries(entries)) {{
                assert.equal(typeof value, 'string', `${{locale}}.${{key}} is not text`);
                assert.ok(value.trim(), `${{locale}}.${{key}} is blank`);
              }}
              for (const key of required) assert.ok(key in entries, `${{locale}} misses ${{key}}`);
            }}
            """
        )

    def test_translator_interpolates_and_falls_back_to_english(self):
        """Catches raw placeholders and missing localized keys leaking into the interface."""
        self.run_module(
            """
            const catalog = {
              en: {greeting: 'Hello, {name}', englishOnly: 'English fallback'},
              fi: {greeting: 'Hei, {name}'},
              sv: {greeting: 'Hej, {name}'},
            };
            const app = i18n.createI18n({catalog, navigatorLanguages: ['fi-FI'], storage: null});
            assert.equal(app.locale, 'fi');
            assert.equal(app.t('greeting', {name: 'Aino'}), 'Hei, Aino');
            assert.equal(app.t('englishOnly'), 'English fallback');
            assert.equal(app.t('missing.key'), 'missing.key');
            assert.equal(app.t('greeting'), 'Hei, {name}');
            """
        )

    def test_explicit_choice_persists_and_storage_failures_stay_usable(self):
        """Catches privacy-mode storage errors breaking language selection or startup."""
        self.run_module(
            """
            const values = new Map([[i18n.STORAGE_KEY, 'sv']]);
            const storage = {
              getItem(key) { return values.get(key) ?? null; },
              setItem(key, value) { values.set(key, value); },
            };
            const saved = i18n.createI18n({storage, navigatorLanguages: ['fi-FI']});
            assert.equal(saved.locale, 'sv');
            assert.equal(saved.setLocale('fi-FI'), 'fi');
            assert.equal(saved.locale, 'fi');
            assert.equal(values.get(i18n.STORAGE_KEY), 'fi');

            const unavailable = {
              getItem() { throw new Error('storage denied'); },
              setItem() { throw new Error('storage denied'); },
            };
            const fallback = i18n.createI18n({storage: unavailable, navigatorLanguages: ['sv-SE']});
            assert.equal(fallback.locale, 'sv');
            assert.doesNotThrow(() => fallback.setLocale('fi'));
            assert.equal(fallback.locale, 'fi');
            """
        )


if __name__ == "__main__":
    unittest.main()
