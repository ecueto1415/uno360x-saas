"""Check content order and invalidation without Odoo or customer data."""
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'addons/uno360x_workspace/billing_assets.py'

class BillingAssetsTest(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('billing_assets_under_test', SOURCE)
        self.assets = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.assets)
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.assets.ROOT = Path(self.tmp.name)
        for paths in self.assets.FILES.values():
            for index, name in enumerate(paths):
                file = self.assets.ROOT / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(('/* part %s */' % index).encode())

    def test_preserves_css_and_javascript_order(self):
        for kind, paths in self.assets.FILES.items():
            digest, body = self.assets.billing_asset(kind)
            separator = b'\n' if kind == 'css' else b';\n'
            self.assertEqual(body, separator.join((self.assets.ROOT / name).read_bytes() for name in paths))
            self.assertIn(digest + '.' + kind, self.assets.billing_asset_urls()[kind])

    def test_source_edit_changes_url_without_rebuild(self):
        before = self.assets.billing_asset_urls()
        file = self.assets.ROOT / self.assets.FILES['css'][0]
        file.write_bytes(file.read_bytes() + b'\n.changed { color: green; }')
        after = self.assets.billing_asset_urls()
        self.assertNotEqual(before['css'], after['css'])
        self.assertEqual(before['js'], after['js'])

if __name__ == '__main__':
    unittest.main()
