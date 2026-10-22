import contextlib
import gzip
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "combined_builder", ROOT / "scripts/runs/viz/s2_assets.py"
)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class CombinedImportTests(unittest.TestCase):
    def test_other_journal_without_pmc_is_imported_and_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sections = root / "sections.gz"
            output = root / "public"
            texts = root / "texts"
            texts.mkdir()
            quote = "Crystals were grown by slow evaporation from ethanol."
            with gzip.open(sections, "wt") as stream:
                stream.write(
                    json.dumps(
                        {
                            "pmcid": "PMC1234",
                            "doi": "10.1107/test",
                            "refcodes": ["ABCDEF"],
                            "article_title": "Acta publisher title",
                            "journal": "Acta Crystallographica E",
                            "year": 2010,
                            "paragraphs": [{"text": quote, "paragraph_index": 0}],
                        }
                    )
                    + "\n"
                )
            rows = [
                {
                    "identifier": "ABCDEF",
                    "doi": "10.1107/test",
                    "crystallisation": "Slow evaporation from ethanol.",
                    "extraction_status": "ok",
                    "summary": None,
                    "evidence": [
                        {"field": "crystallisation", "source_file": "paper.md", "quote": quote}
                    ],
                    "source_files": [{"name": "paper.md"}],
                },
                {
                    "identifier": "QWERTY",
                    "doi": "10.1234/other",
                    "crystallisation": "Slow evaporation from ethanol.",
                    "extraction_status": "ok",
                    "summary": "Crystals were grown by slow evaporation from ethanol.",
                    "compound_label": "PRIVATE_CSD_SENTINEL",
                    "match_basis": "PRIVATE_CSD_SENTINEL",
                    "evidence": [
                        {"field": "crystallisation", "source_file": "paper.md", "quote": quote}
                    ],
                    "source_files": [{"name": "paper.md"}],
                },
            ]
            combined = root / "combined.parquet"
            pl.DataFrame(rows).write_parquet(combined)
            bibliography = root / "bib.json"
            bibliography.write_text(
                json.dumps(
                    {
                        "10.1234/other": {
                            "title": "Other publisher title",
                            "journal": "Other journal",
                            "year": 2020,
                            "pmcid": None,
                            "source": "Publisher-deposited Crossref bibliography",
                            "licenses": [],
                        }
                    }
                )
            )
            path = texts / (hashlib.sha256(b"10.1234/other").hexdigest() + ".json.gz")
            with gzip.open(path, "wt") as stream:
                json.dump(
                    {
                        "doi": "10.1234/other",
                        "main_text": "# Other publisher title\n\n" + quote,
                        "supplements": [],
                    },
                    stream,
                )
            with contextlib.redirect_stdout(io.StringIO()):
                result = builder.build(
                    sections, combined, output, bibliography=bibliography, texts=texts
                )
            self.assertEqual(result["refcodes"], 2)
            self.assertEqual(result["collections"]["Other journals"]["refcodes"], 1)
            table = pl.read_parquet(output / "publisher_entries.parquet").to_dicts()
            other = next(r for r in table if r["id"] == "QWERTY")
            self.assertIsNone(other["pmcid"])
            self.assertEqual(other["paper_id"], "doi:10.1234/other")
            public = json.loads(other["extraction_json"])
            self.assertEqual(public["summary"], quote)
            self.assertTrue(public["evidence"][0]["verified"])
            self.assertNotIn("PRIVATE_CSD_SENTINEL", json.dumps(public))
            # Completing Acta E must not replace the other-journal dataset.
            acta = root / "acta.parquet"
            pl.DataFrame(rows[:1]).write_parquet(acta)
            with contextlib.redirect_stdout(io.StringIO()):
                result = builder.build(sections, acta, output, texts=texts, preserve_existing=True)
            self.assertEqual(result["refcodes"], 2)
            self.assertEqual(result["collections"]["Other journals"]["refcodes"], 1)

    def test_name_must_occur_in_publisher_source_not_just_have_an_evidence_tag(self):
        quote = "Crystals were grown by slow evaporation from ethanol."
        row = {
            "extraction_status": "ok",
            "compound_label": "PRIVATE_CSD_SENTINEL",
            "source_files": [{"name": "paper.md"}],
            "evidence": [{"field": "compound_label", "source_file": "paper.md", "quote": quote}],
        }
        result = builder.public_extraction(row, {"paragraphs": [{"text": quote}]})
        self.assertIsNone(result["compound_label"])

    def test_recorded_quote_is_not_its_own_independent_verification(self):
        quote = "Crystals were grown by slow evaporation from ethanol."
        row = {
            "extraction_status": "ok",
            "crystallisation": "Slow evaporation from ethanol.",
            "evidence": [{"field": "crystallisation", "source_file": "paper.md", "quote": quote}],
            "source_files": [{"name": "paper.md"}],
        }
        paper = {"paragraphs": [{"text": quote}]}
        result = builder.public_extraction(row, paper, recorded=True)
        self.assertFalse(result["evidence"][0]["verified"])
        self.assertIn("not independently matched", result["evidence_policy"])


if __name__ == "__main__":
    unittest.main()
