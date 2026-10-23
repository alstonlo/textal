"""Generated previews survive a process restart and invalidate on package changes."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from viz import publisher_assets as assets
from viz.publisher_data import package_name


class ThumbnailCacheTests(unittest.TestCase):
    def test_disk_cache_and_changed_package(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            package = root / package_name('PMC1')
            package.parent.mkdir(parents=True)
            package.write_bytes(b'first package')
            with patch.object(assets, 'DATA', root), patch.object(assets, 'PAPERS', {'PMC1': {'doi': '10.1/test'}}), patch.object(assets, 'package', return_value=({'cifs': [{'cache_name': 'test.cif'}]}, {})) as read_package, patch.object(assets, 'cif_models', return_value={'blocks': [{'text': 'data_test'}]}), patch('viz.crystal.draw_cell', return_value='<svg/>') as draw:
                assets.thumbnail.cache_clear()
                try:
                    self.assertEqual(assets.thumbnail('PMC1'), '<svg/>')
                    assets.thumbnail.cache_clear()  # Simulate a server restart.
                    self.assertEqual(assets.thumbnail('PMC1'), '<svg/>')
                    self.assertEqual(read_package.call_count, 1)
                    self.assertEqual(draw.call_count, 1)
                    package.write_bytes(b'changed publisher package')
                    assets.thumbnail.cache_clear()
                    self.assertEqual(assets.thumbnail('PMC1'), '<svg/>')
                    self.assertEqual(draw.call_count, 2)
                finally:
                    assets.thumbnail.cache_clear()
