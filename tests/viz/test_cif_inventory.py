import importlib.util
import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "audit", Path(__file__).resolve().parents[2] / "scripts/runs/viz/s0_audit_cifs.py"
)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class InventoryTests(unittest.TestCase):
    def test_cif_in_supplementary_zip_and_journal_alias(self):
        row = {
            "pmcid": "PMC123",
            "doi": "10.1107/test",
            "journal": "Acta Crystallographica Section E: Structure Reports Online",
            "refcodes": ["ABCDEF"],
        }
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "packages").mkdir()
            blob = io.BytesIO()
            with zipfile.ZipFile(blob, "w") as archive:
                archive.writestr("structures/strange.CIF", b"data_I\n_atom_site_label C1\n")
            payload = blob.getvalue()
            with tarfile.open(root / "packages/PMC123.tar.gz", "w:gz") as archive:
                info = tarfile.TarInfo("PMC123/files/supplement.zip")
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            first = audit.inspect(row, [root])
            self.assertFalse(first["publisher_coordinate_cif"])
            self.assertTrue(first["zip_needs_inspection"])
            second = audit.inspect(row, [root], True)
            self.assertTrue(second["publisher_coordinate_cif"])
            summary = audit.summarize([first, second])
            self.assertEqual(summary["acta_e"]["papers_checked"], 1)
            self.assertEqual(summary["acta_e"]["refcodes_linked_to_publisher_cif"], 1)
            self.assertEqual(summary["all_csd_pmc"]["zip_only_pending"], 0)


if __name__ == "__main__":
    unittest.main()
