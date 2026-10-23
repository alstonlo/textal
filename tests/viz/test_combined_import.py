import contextlib
import gzip
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

import polars as pl
from test_publisher_site import write_csd, write_paper

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
            pmc = root / "papers"
            write_paper(pmc, "10.1234/other", "# Other publisher title\n\n" + quote)
            csd = root / "csd.parquet"
            write_csd(csd, [])
            with contextlib.redirect_stdout(io.StringIO()):
                result = builder.build(
                    sections, combined, output, csd, bibliography=bibliography, pmc=pmc
                )
            self.assertEqual(result["refcodes"], 2)
            self.assertEqual(result["collections"]["Other journals"]["refcodes"], 1)
            table = pl.read_parquet(output / "entries.parquet").to_dicts()
            other = next(r for r in table if r["id"] == "QWERTY")
            self.assertIsNone(other["pmcid"])
            self.assertEqual(other["paper_id"], "doi:10.1234/other")
            public = json.loads(other["extraction_json"])
            self.assertEqual(public["summary"], quote)
            self.assertTrue(public["evidence"][0]["verified"])
            self.assertNotIn("PRIVATE_CSD_SENTINEL", json.dumps(public))
            # Without a licence that allows it, the text is not released.
            self.assertFalse(list(output.glob("texts/*/*")))
            # Completing Acta E must not replace the other-journal dataset.
            acta = root / "acta.parquet"
            pl.DataFrame(rows[:1]).write_parquet(acta)
            with contextlib.redirect_stdout(io.StringIO()):
                result = builder.build(sections, acta, output, csd, pmc=pmc, preserve_existing=True)
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

    def test_sentences_copied_from_the_csd_are_dropped(self):
        paper = "Yellow blocks of C10H16O4 grew from ethanol; see CCDC 123456."
        csd = builder.csd_values(
            [
                {key: None for key in builder.ENTRY_FIELDS}
                | {"formula": "C10 H16 O4", "color": "yellow", "solvent": "benzene"}
                | {"habit": "plate // (1 0 1)", "temperature": "150.0 K", "synonyms": []}
            ]
        )
        corpus = builder.words(paper)
        for text in (
            "The yellow crystals have the formula C₁₀H₁₆O₄.",
            "The paper deposits the structure as CCDC 123456.",
        ):
            self.assertEqual(builder.without_csd(text, csd, corpus), text)
        for text in (
            "They grew from benzene.",
            "Each crystal is a plate.",
            "Data were collected at 150 K.",
            "The supplied name differs from the paper.",
            "This matches the CSD entry.",
            "A CSD search found no analogue.",
        ):
            self.assertEqual(builder.without_csd("Kept. " + text, csd, corpus), "Kept.")

    def test_only_creative_commons_papers_are_released(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sections = root / "sections.gz"
            with gzip.open(sections, "wt") as stream:
                for pmcid, ref, url in (
                    ("PMC1", "ABCDEF", "https://creativecommons.org/licenses/by/2.0/uk/"),
                    ("PMC2", "ABCDEG", "http://journals.iucr.org/services/termsofuse.html"),
                ):
                    row = {
                        "pmcid": pmcid,
                        "doi": "10.1107/" + pmcid.lower(),
                        "refcodes": [ref],
                        "article_license_evidence": [{"url": url}],
                    }
                    stream.write(json.dumps(row) + "\n")
            pmc, cache = root / "papers", root / "cache"
            for pmcid in ("PMC1", "PMC2"):
                (pmc / "parsed" / pmcid / "paper.md").parent.mkdir(parents=True)
                (pmc / "parsed" / pmcid / "paper.md").write_text("# Text")
                (cache / pmcid).mkdir(parents=True)
                (cache / pmcid / "manifest.json").touch()
            dois = ["10.1107/pmc1", "10.1107/pmc2"]
            pl.DataFrame({"doi": dois, "dir": ["PMC1", "PMC2"]}).write_parquet(
                pmc / "metadata.parquet"
            )
            ext = root / "ext.parquet"
            pl.DataFrame({"identifier": ["ABCDEF"], "doi": ["10.1107/pmc1"]}).write_parquet(ext)
            csd = root / "csd.parquet"
            write_csd(csd, [])
            output = root / "public"
            with contextlib.redirect_stdout(io.StringIO()):
                builder.build(sections, ext, output, csd, pmc=pmc, cache=cache)
            papers = pl.read_parquet(output / "papers.parquet")
            released = {p["pmcid"]: json.loads(p["provenance_json"]) for p in papers.to_dicts()}
            self.assertTrue(released["PMC1"]["has_full_text"])
            self.assertTrue(released["PMC1"]["has_publisher_package"])
            self.assertFalse(released["PMC2"]["has_full_text"])
            self.assertFalse(released["PMC2"]["has_publisher_package"])
            self.assertEqual([p.name for p in output.glob("texts/*/*")], ["PMC1.json.gz"])


if __name__ == "__main__":
    unittest.main()
