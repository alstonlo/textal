"""Names belong to a crystal; a broad multi-compound paper title does not."""

import unittest

from viz.names import crystal_name


def record(label=None, title="A broad paper about many compounds", collection="Other journals"):
    return {
        "id": "ABCDEF",
        "extraction": {"compound_label": label},
        "paper": {"title": title, "provenance": {"collection": collection}},
    }


class PublisherNamesTests(unittest.TestCase):
    def test_publisher_label_wins_over_paper_title(self):
        self.assertEqual(
            crystal_name(record("L-2,4-diaminobutyric acid"))[0], "L-2,4-diaminobutyric acid"
        )

    def test_acta_title_as_chemical_name(self):
        value = record("(I)", "Crystal structure of ciprofloxacin hexa\u00adhydrate", "Acta E")
        self.assertEqual(crystal_name(value)[0], "ciprofloxacin hexahydrate")

    def test_broad_title_is_not_a_molecule_name(self):
        self.assertEqual(crystal_name(record())[0], "Crystal ABCDEF")
        value = record("1", "The crystal structures of three polymorphs", "Acta E")
        self.assertEqual(crystal_name(value)[0], "Compound 1")

    def test_markup_is_displayed_as_chemical_text(self):
        self.assertEqual(crystal_name(record("Cu<sub>2</sub> &amp; ligand"))[0], "Cu2 & ligand")
