"""Publisher metadata before a data_ header must not prevent structure rendering."""
import unittest
from unittest.mock import patch

from viz import publisher_assets as assets


class PublisherCifPreambleTests(unittest.TestCase):
    def test_headerless_metadata_and_original_download(self):
        cif = b"""# Publisher submission
_publ_requested_journal 'Angewandte Chemie'
data_5
_cell_length_a 10
_cell_length_b 10
_cell_length_c 10
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_space_group_name_H-M_alt 'P 1'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
C1 C 0.1 0.2 0.3
"""
        for raw in (cif, cif[cif.index(b'data_5'):]):
            asset = {'cache_name': 'test.cif', 'local_url': '/test.cif', 'name': 'test.cif',
                     'bytes': len(raw), 'sha256': '0' * 64}
            with self.subTest(preamble=raw.startswith(b'#')), patch.object(
                assets, 'package', return_value=({'cifs': [asset]}, {'test.cif': raw})
            ):
                data = assets.cif_models('PMC1', 'test.cif')
                self.assertEqual([b['name'] for b in data['blocks']], ['5'])
                self.assertEqual(data['blocks'][0]['asymmetric_atoms'], 1)
                self.assertEqual(assets.asset_file('PMC1', 'test.cif')[0], raw)
