"""Regression checks for the public-data boundary and publisher crystal geometry."""

import gzip
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

import polars as pl
from fastapi.testclient import TestClient

# The website's modules read these when imported, which the builder already does.
TEMP = tempfile.TemporaryDirectory()
os.environ.update(
    TEXTAL_DATA=str(Path(TEMP.name) / "assets"),
    TEXTAL_PUBLISHER_CACHE=str(Path(TEMP.name) / "cache"),
    TEXTAL_ASSET_SSH="0",
)

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("builder", ROOT / "scripts/runs/viz/s2_assets.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

CIF = """data_I
_cell_length_a 10
_cell_length_b 11
_cell_length_c 12
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_space_group_name_H-M_alt 'P 1'
loop_
_symmetry_equiv_pos_as_xyz
'x,y,z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
_atom_site_occupancy
"C1'" C 0.05 0.1 0.2 1
O1 O 0.95 0.1 0.2 1
"""
SECRET = "PRIVATE_CSD_SENTINEL"
QUOTE = "Crystals were grown by slow evaporation from ethanol."


def write_csd(path, rows):
    """Writes CSD rows with the columns the extraction model saw, the rest left empty."""
    schema = {key: pl.String for key in builder.ENTRY_FIELDS}
    schema |= {"ccdc_number": pl.Int64, "synonyms": pl.List(pl.String)}
    columns = {key: None for key in schema} | {"synonyms": []}
    pl.DataFrame([columns | row for row in rows], schema=schema).write_parquet(path)


def write_paper(pmc, doi, text):
    """Writes the parsed Markdown of one paper and its row of `metadata.parquet`."""
    (pmc / "parsed" / doi / "paper.md").parent.mkdir(parents=True)
    (pmc / "parsed" / doi / "paper.md").write_text(text)
    pl.DataFrame({"doi": [doi], "dir": [doi]}).write_parquet(pmc / "metadata.parquet")


class PublisherSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = Path(TEMP.name)
        cls.output = cls.folder / "assets"
        cls.output.mkdir()
        sections = cls.folder / "sections.jsonl.gz"
        source = {
            "pmcid": "PMC1234",
            "doi": "10.1107/test",
            "article_title": "Publisher title",
            "journal": "Acta Crystallographica E",
            "year": 2010,
            "refcodes": ["ABCDEF", "ABCDEF01"],
            "ccdc_numbers": [123456],
            "chemical_name": SECRET,
            "cif": SECRET,
            "paragraphs": [{"paragraph_index": 0, "text": QUOTE}],
            "matched_sections": [
                {"title": "Synthesis and crystallization", "paragraph_indices": [0]}
            ],
            "article_license_evidence": [
                {
                    "url": "https://creativecommons.org/licenses/by/4.0/",
                    "type": "CC BY",
                    "text": "Publisher terms",
                }
            ],
        }
        with gzip.open(sections, "wt") as f:
            f.write(json.dumps(source) + "\n")
        extraction = {
            "identifier": "ABCDEF",
            "doi": "10.1107/test",
            "crystallisation": "Slow evaporation from ethanol. The CSD entry says so.",
            "synthesis": "Unverified field is withheld.",
            "match_basis": SECRET,
            "compound_label": SECRET,
            "summary": SECRET,
            "source_files": [{"name": SECRET}],
            "error": SECRET,
            "extraction_status": "ok",
            "evidence": [
                {
                    "field": "crystallisation",
                    "quote": source["paragraphs"][0]["text"],
                    "source_file": SECRET,
                }
            ],
        }
        ext = cls.folder / "extractions.parquet"
        pl.DataFrame([extraction]).write_parquet(ext)
        csd = cls.folder / "csd.parquet"
        write_csd(csd, [{"identifier": "ABCDEF", "chemical_name": SECRET, "color": "yellow"}])
        pmc = cls.folder / "papers"
        write_paper(pmc, "10.1107/test", "# Publisher article\n\n" + QUOTE)
        cls.cache = cls.folder / "cache"
        paper = cls.cache / "PMC1234"
        paper.mkdir(parents=True)
        (paper / "manifest.json").touch()
        builder.build(sections, ext, cls.output, csd, pmc=pmc, cache=cls.cache)
        pl.DataFrame({"cif": [SECRET], "chemical_name": [SECRET]}).write_parquet(
            cls.output / "csd_entries.parquet"
        )
        cls.raw = (CIF + CIF.replace("data_I", "data_II")).encode()
        (paper / "0-publisher.cif").write_bytes(cls.raw)
        (paper / "1-scheme1.png").write_bytes(b"publisher image bytes")
        (paper / "private.cif").write_text(SECRET)

        def asset(name, blob, kind=None):
            return {
                "name": name,
                "cache_name": name,
                "bytes": len(blob),
                "sha256": hashlib.sha256(blob).hexdigest(),
                "archive_member": "PMC1234/files/" + name,
                "source_url": "https://pmc-oa-opendata.s3.amazonaws.com/PMC1234.1/" + name,
                "kind": kind,
            }

        manifest = {
            "pmcid": "PMC1234",
            "doi": "10.1107/test",
            "private": SECRET,
            "package_path": "/project/rrg-aspuru/auhcheng/iucr_open_access_full_2026-10-21/packages/PMC1234.tar.gz",
            "cifs": [asset("0-publisher.cif", cls.raw)],
            "figures": [
                asset("1-scheme1.png", b"publisher image bytes", "chemical_scheme"),
                asset("private.cif", SECRET.encode(), "article_figure"),
            ],
        }
        (paper / "manifest.json").write_text(json.dumps(manifest))
        from viz.app import app

        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        TEMP.cleanup()

    def test_import_includes_pending_refcodes(self):
        result = self.client.get("/api/collection").json()
        self.assertEqual(result["refcodes"], 2)
        self.assertEqual(result["extraction_statuses"], {"ok": 1, "pending": 1})
        self.assertIn("ABCDEF01", self.client.get("/explore").text)
        self.assertIn("Extraction pending", self.client.get("/entry/ABCDEF01").text)

    def test_private_fields_never_render_or_export(self):
        from viz.publisher_data import load_public_data

        data = load_public_data()
        text = json.dumps(data)
        for url in (
            "/",
            "/explore",
            "/entry/ABCDEF",
            "/api/collection",
            "/api/paper-assets/PMC1234",
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            text += response.text
        self.assertNotIn(SECRET, text)
        self.assertNotIn("ccdc_numbers", text)
        self.assertNotIn("match_basis", text)
        self.assertNotIn("package_path", text)
        self.assertNotIn("Unverified field", text)
        self.assertIn("Slow evaporation from ethanol.", text)
        self.assertNotIn("The CSD entry says so", text)

    def test_full_publisher_text_is_scoped_to_imported_papers(self):
        from viz.publisher_data import text_name

        response = self.client.get("/api/paper-text/PMC1234").json()
        self.assertEqual(response["main_text"], "# Publisher article\n\n" + QUOTE)
        self.assertEqual(self.client.get("/api/paper-text/PMC9999").status_code, 404)
        path = self.output / text_name("PMC1234")
        original = path.read_bytes()
        try:
            with gzip.open(path, "wt") as stream:
                json.dump({**response, "csd_metadata": SECRET}, stream)
            with self.assertRaises(ValueError):
                self.client.get("/api/paper-text/PMC1234")
        finally:
            path.write_bytes(original)
        page = self.client.get("/entry/ABCDEF").text
        self.assertLess(
            page.index("What the paper says about this crystal"), page.index('class="paper"')
        )
        self.assertIn("main-reading", page)

    def test_original_publisher_cif_bytes_unchanged(self):
        response = self.client.get("/paper-assets/PMC1234/0-publisher.cif")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.raw)
        manifest = self.client.get("/api/paper-assets/PMC1234").json()
        self.assertEqual(
            manifest["cifs"][0]["sha256"], hashlib.sha256(response.content).hexdigest()
        )
        self.assertEqual(len(manifest["figures"]), 1)

    def test_private_cache_and_legacy_tables_are_not_routes(self):
        for url in (
            "/paper-assets/PMC1234/manifest.json",
            "/paper-assets/PMC1234/private.cif",
            "/assets/entries.parquet",
            "/data/csd_metadata.full.parquet",
            "/api/paper-assets/PMC9999",
        ):
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_public_schema_fails_closed_on_extra_columns(self):
        from viz.publisher_data import load_public_data

        table = pl.read_parquet(self.output / "entries.parquet")
        try:
            table.with_columns(pl.lit(SECRET).alias("cif")).write_parquet(
                self.output / "entries.parquet"
            )
            with self.assertRaises(ValueError):
                load_public_data()
        finally:
            table.write_parquet(self.output / "entries.parquet")

    def test_gemmi_handles_quoted_labels_and_multiple_blocks(self):
        result = self.client.get("/api/cif-models/PMC1234/0-publisher.cif")
        self.assertEqual(result.status_code, 200)
        blocks = result.json()["blocks"]
        self.assertEqual([b["name"] for b in blocks], ["I", "II"])
        self.assertEqual(blocks[0]["sites"][0]["label"], "C1'")
        self.assertIn("A0 C", blocks[0]["text"])
        self.assertEqual(blocks[0]["viewer"]["atoms"], 2)
        # Molecules crossing the cell face stay whole in the original-main view.
        xyz = blocks[0]["viewer"]["xyz"].splitlines()[2:]
        positions = [list(map(float, line.split()[1:])) for line in xyz]
        self.assertAlmostEqual(abs(positions[0][0] - positions[1][0]), 1.0)

    def test_thumbnail_uses_original_main_svg_style(self):
        response = self.client.get("/api/publisher-thumbnail/PMC1234.svg")
        self.assertEqual(response.status_code, 200)
        self.assertIn("<circle", response.text)
        self.assertIn('stroke-width="0.7"', response.text)
        self.assertNotIn(SECRET, response.text)

    def test_tampered_publisher_bytes_fail_verification(self):
        path = self.cache / "PMC1234/0-publisher.cif"
        try:
            path.write_bytes(b"tampered")
            self.assertEqual(
                self.client.get("/paper-assets/PMC1234/0-publisher.cif").status_code, 404
            )
            self.assertEqual(
                self.client.get("/api/cif-models/PMC1234/0-publisher.cif").status_code, 422
            )
        finally:
            path.write_bytes(self.raw)

    def test_completed_snapshot_reloads_without_restarting(self):
        path = self.output / "snapshot.json"
        original = path.read_text()
        value = json.loads(original)
        value["built_at"] = "2026-10-22T23:00:00+00:00"
        try:
            path.write_text(json.dumps(value))
            self.assertEqual(
                self.client.get("/api/collection").json()["built_at"], value["built_at"]
            )
        finally:
            path.write_text(original)
            self.client.get("/api/collection")

    def test_unknown_paper_never_falls_back_to_csd(self):
        self.assertEqual(self.client.get("/entry/ZZZZZZ").status_code, 404)
        self.assertEqual(self.client.get("/api/publisher-thumbnail/PMC9999.svg").status_code, 404)


if __name__ == "__main__":
    unittest.main()
