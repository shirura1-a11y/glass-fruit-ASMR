import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from glass_fruit.cli import main
from glass_fruit.import_assets import fruit_for, import_assets


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'release'
        self.source.mkdir()
        self.target = self.root / 'assets'

    def test_phone_filename_uses_selected_fruit_and_preserves_bytes(self):
        (self.source / 'VID_20261023.MP4').write_bytes(b'video bytes')
        report = import_assets(self.source, self.target, 'apple')
        self.assertEqual(report['mode'], 'direct-mp4')
        self.assertEqual((self.target / 'apple' / '0001.mp4').read_bytes(), b'video bytes')
        self.assertEqual(json.loads((self.target / 'import-report.json').read_text()), report)
        self.assertTrue((self.source / 'VID_20261023.MP4').exists())

    def test_fruit_names_override_default(self):
        for name, expected in [('apple-01.mp4', 'apple'), ('ブドウ_02.mp4', 'grapes'),
                               ('スイカ.mp4', 'watermelon'), ('いちご 01.mp4', 'strawberry')]:
            self.assertEqual(fruit_for(name, 'apple'), expected)

    def test_direct_mp4_preferred_over_old_zip(self):
        (self.source / 'export.mp4').write_bytes(b'new')
        (self.source / 'fruit-assets.zip').write_bytes(b'invalid old zip')
        self.assertEqual(import_assets(self.source, self.target)['mode'], 'direct-mp4')

    def test_legacy_zip_and_uppercase_extension(self):
        with zipfile.ZipFile(self.source / 'fruit-assets.zip', 'w') as archive:
            archive.writestr('strawberry/01.MP4', b'legacy')
        report = import_assets(self.source, self.target)
        self.assertEqual(report['mode'], 'legacy-zip')
        self.assertEqual((self.target / 'strawberry' / '0001.mp4').read_bytes(), b'legacy')

    def test_unsafe_zip_leaves_no_partial_destination(self):
        with zipfile.ZipFile(self.source / 'fruit-assets.zip', 'w') as archive:
            archive.writestr('strawberry/good.mp4', b'good')
            archive.writestr('../outside.mp4', b'bad')
        with self.assertRaises(ValueError):
            import_assets(self.source, self.target)
        self.assertFalse(self.target.exists())
        self.assertFalse((self.root / 'outside.mp4').exists())

    def test_symlink_input_rejected(self):
        outside = self.root / 'outside.mp4'
        outside.write_bytes(b'outside')
        (self.source / 'export.mp4').symlink_to(outside)
        with self.assertRaises(ValueError):
            import_assets(self.source, self.target)
        self.assertFalse(self.target.exists())

    def test_empty_release_and_existing_destination(self):
        with self.assertRaisesRegex(ValueError, 'No MP4'):
            import_assets(self.source, self.target)
        self.target.mkdir()
        (self.target / 'keep').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            import_assets(self.source, self.target)
        self.assertEqual((self.target / 'keep').read_text(), 'keep')

    def test_cli_reports_corrupt_zip_without_traceback(self):
        (self.source / 'fruit-assets.zip').write_bytes(b'not a zip')
        self.assertEqual(main(['import-assets', '--source', str(self.source), '--assets', str(self.target)]), 1)
