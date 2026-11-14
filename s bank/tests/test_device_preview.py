import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "web" / "device-preview.html"
INDEX = ROOT / "web" / "index.html"


class DevicePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = PREVIEW.read_text(encoding="utf-8")
        match = re.search(r"<script>([\s\S]*?)</script>", cls.html)
        if not match:
            raise AssertionError("device preview needs one local inline script")
        cls.script = match.group(1)

    def test_has_required_generic_viewports_and_real_app_iframe(self):
        expected = {
            "small-phone": (320, 568),
            "compact-phone": (375, 667),
            "current-phone": (390, 844),
            "large-phone": (412, 915),
            "tablet": (768, 1024),
            "desktop": (1280, 800),
        }
        self.assertIn('src="/"', self.html)
        self.assertIn('title="S-Coach application preview"', self.html)
        for key, (width, height) in expected.items():
            with self.subTest(key=key):
                self.assertIn(f'data-preset="{key}"', self.html)
                self.assertRegex(self.html, rf"{width}\s*[×x]\s*{height}")

        lowered = self.html.casefold()
        for trademark in ("iphone", "ipad", "pixel", "galaxy", "samsung"):
            self.assertNotIn(trademark, lowered)

    def test_is_accessible_local_only_and_absent_from_customer_app(self):
        self.assertIn("Development preview — not part of the customer experience", self.html)
        self.assertRegex(self.html, r"<fieldset[\s>]", "preset buttons need a named group")
        self.assertIn("<legend", self.html)
        self.assertIn('id="orientation"', self.html)
        self.assertIn('id="fit-window"', self.html)
        self.assertIn('aria-pressed="true"', self.html)
        self.assertIn('aria-live="polite"', self.html)
        self.assertIn("Browser DevTools and automated viewport tests remain authoritative", self.html)

        # This utility is intentionally discoverable only by its local URL.
        self.assertNotIn("device-preview", INDEX.read_text(encoding="utf-8").casefold())
        self.assertNotRegex(self.html, r"<(?:script|link)[^>]+(?:src|href)=['\"]https?://")

    @unittest.skipUnless(shutil.which("node"), "Node is required for the inline-JS contract")
    def test_inline_js_is_valid_and_dimension_helpers_execute(self):
        self.assertNotIn("querySelectorAll('[data-preset]')", self.script)
        self.assertIn("querySelectorAll('.preset[data-preset]')", self.script)
        syntax = subprocess.run(
            ["node", "--check", "-"],
            input=self.script,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

        harness = f"""
        import assert from 'node:assert/strict';
        globalThis.window = {{}};
        globalThis.document = undefined;
        eval({json.dumps(self.script)});
        const preview = window.DevicePreview;
        assert.ok(preview);
        assert.deepEqual(preview.dimensionsFor('current-phone', false), {{width:390,height:844}});
        assert.deepEqual(preview.dimensionsFor('current-phone', true), {{width:844,height:390}});
        assert.deepEqual(preview.dimensionsFor('tablet', false), {{width:768,height:1024}});
        assert.equal(preview.fitScale(390, 844, 390, 844, false), 1);
        assert.equal(preview.fitScale(390, 844, 195, 422, true), 0.5);
        assert.equal(Object.keys(preview.PRESETS).length, 6);
        """
        executed = subprocess.run(
            ["node", "--input-type=module", "--eval", harness],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(executed.returncode, 0, executed.stderr or executed.stdout)


if __name__ == "__main__":
    unittest.main()
