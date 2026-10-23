"""Journal display names must remain stable when used as filter values."""
import unittest

from viz.publisher_data import format_journal


class JournalFormattingTests(unittest.TestCase):
    def test_compact_abbreviations(self):
        for raw, expected in {
            'Angew.Chem.,Int.Ed.': 'Angew. Chem., Int. Ed.',
            'Chem.-Eur.J.': 'Chem. Eur. J.',
            'J.Biol.Inorg.Chem.(JBIC)': 'J. Biol. Inorg. Chem. (JBIC)',
            'Chem.Mater.': 'Chem. Mater.',
            '  Cryst.Growth  Des. ': 'Cryst. Growth Des.',
            'ChemMedChem': 'ChemMedChem',
            'iScience': 'iScience',
            '': '',
        }.items():
            with self.subTest(raw=raw):
                self.assertEqual(format_journal(raw), expected)
                self.assertEqual(format_journal(expected), expected)
