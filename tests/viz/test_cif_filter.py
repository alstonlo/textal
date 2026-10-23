"""CIF availability must reflect files, rather than the package provenance flag."""
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from viz import publisher_assets as assets
from viz.publisher_data import package_name


class CifFilterTests(unittest.TestCase):
    def test_only_packages_with_existing_cifs_match(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(assets, 'DATA', Path(folder)), patch.object(assets, 'PAPERS', {}):
            assets.PAPERS.update({f'PMC{i}': {'doi': '10.1/test'} for i in range(1, 5)})
            for i, listed, present in [(1, True, True), (2, False, False), (3, True, False)]:
                name = f'PMC{i}'
                manifest = {'pmcid': name, 'doi': '10.1/test', 'cifs': []}
                if listed:
                    manifest['cifs'] = [{'cache_name': 'structure.cif', 'sha256': '0' * 64,
                                         'archive_member': name + '/structure.cif',
                                         'source_url': 'https://pmc-oa-opendata.s3.amazonaws.com/structure.cif'}]
                path = Path(folder) / package_name(name)
                path.parent.mkdir(parents=True, exist_ok=True)
                with tarfile.open(path, 'w:gz') as archive:
                    for filename, content in [('manifest.json', json.dumps(manifest).encode())] + ([('structure.cif', b'data_test')] if present else []):
                        info = tarfile.TarInfo(filename)
                        info.size = len(content)
                        archive.addfile(info, io.BytesIO(content))
            assets.has_cif.cache_clear()
            try:
                with patch.object(tarfile.TarFile, 'getmember', side_effect=AssertionError('Full archive scan')):
                    self.assertTrue(assets.has_cif('PMC1'))
                for name in ['PMC2', 'PMC3', 'PMC4', 'PMC999']:
                    self.assertFalse(assets.has_cif(name), name)
            finally:
                assets.has_cif.cache_clear()
