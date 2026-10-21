# CSD journal statistics

Statistics of the journals that the Cambridge Structural Database (CSD) entries were published
in: how many papers each journal has, how many have a DOI, and which journals are open access.
Last updated 2026-10-21.

## Sources

- `data/raw/csd_metadata.full.parquet`: the metadata of every CSD entry, one row per entry. The
  paper of an entry is in the `publication` column, which holds the journal (abbreviated and full
  name), the year and the DOI. The `publications` column always holds exactly one item, the same
  paper, so we ignore it.
- `data/raw/doaj/journals.csv`: the list of fully open-access journals from the
  [Directory of Open Access Journals (DOAJ)](https://doaj.org), with the year each journal started
  to publish all content under an open licence, and the licence.

To reproduce the numbers below, run these scripts from the repository root:

```bash
pixi run python scripts/download/s0_doaj.py              # downloads the DOAJ list
pixi run python scripts/download/s1_csd_journal_stats.py
```

## Definitions

- **Journal**: every entry has a journal name, but some names are not journals. These are left
  out of everything below (`NOT_JOURNALS` in `src/dataset/csd.py`), which removes 72,492 entries:
  - `CSD Communication`: a structure sent straight to the CSD with no paper.
  - `ICSD Communication`, `Thesis`, `U.S.Patents`, `NASA Technical Reports`,
    `University of Southampton, Crystal Structure Report Archive`.

  A few book titles are still counted as journals. They cover very few entries.
- **DOI**: a missing DOI is null (never an empty string). DOIs are not case-sensitive, so we strip
  spaces and make them lowercase before counting unique DOIs.
- **Open-access paper**: a paper in a journal listed in the DOAJ, published in or after the year
  the journal became fully open access. Journals are matched by full title or alternative title,
  after making both lowercase and removing accents and punctuation. Two CSD journals match a
  different DOAJ journal of the same name, so they are not counted: Synthesis (Thieme) and Matter
  (Cell Press). Open-access papers in subscription journals (hybrid open access) are not counted,
  because the DOAJ only lists fully open-access journals.

## Overview

| | Count |
|---|---:|
| Journal entries | 1,340,730 |
| Journals | 2,614 |
| Entries with a DOI | 1,276,644 (95.2%) |
| Unique DOIs | 554,956 |

- **Entries per DOI**: 2.3 on average, because most papers report several structures. 287,252
  DOIs (52%) cover only one entry, 90% cover 5 or fewer, and 99% cover 11 or fewer. The largest is
  `10.1002/cssc.201601752` with 1,853 entries. The next largest is `10.1107/s2052252520010441`
  with 417 entries.

## Largest journals

By number of unique DOIs. "Years" gives the first, median and last publication year.

| Journal | Entries | Unique DOIs | Years |
|---|---:|---:|---|
| Acta Crystallogr., Sect. E: Struct. Rep. Online | 39,541 | 39,466 | 2001, 2008, 2022 |
| Inorg. Chem. | 98,842 | 31,979 | 1962, 2011, 2025 |
| J. Am. Chem. Soc. | 70,318 | 25,900 | 1928, 2012, 2025 |
| Organometallics | 62,869 | 20,374 | 1982, 2009, 2025 |
| Acta Crystallogr., Sect. C: Cryst. Struct. Commun. | 24,780 | 19,662 | 1983, 1996, 2013 |
| Angew. Chem., Int. Ed. | 50,763 | 19,319 | 1968, 2017, 2025 |
| Chem. Commun. | 40,034 | 18,919 | 0, 2014, 2025 |
| Dalton Trans. | 65,182 | 17,802 | 0, 2015, 2025 |
| J. Org. Chem. | 34,489 | 16,287 | 1962, 2013, 2025 |
| Org. Lett. | 29,734 | 15,411 | 1999, 2018, 2025 |
| J. Organomet. Chem. | 32,365 | 14,900 | 1963, 2004, 2025 |
| Inorg. Chim. Acta | 33,997 | 14,183 | 1967, 2009, 2026 |
| Chem. Eur. J. | 48,878 | 13,325 | 1995, 2016, 2025 |
| Polyhedron | 32,351 | 12,670 | 1982, 2012, 2025 |
| J. Mol. Struct. | 22,894 | 11,327 | 1968, 2018, 2026 |
| Eur. J. Inorg. Chem. | 30,926 | 8,650 | 1998, 2012, 2025 |
| Tetrahedron Lett. | 12,540 | 8,526 | 1960, 2007, 2025 |
| J. Chem. Soc., Dalton Trans. | 17,455 | 8,158 | 1972, 1996, 2002 |
| Tetrahedron | 15,564 | 7,820 | 1958, 2009, 2025 |
| Cryst. Growth Des. | 35,397 | 7,559 | 2001, 2016, 2025 |
| CrystEngComm | 31,094 | 7,511 | 1999, 2015, 2025 |
| Z. Anorg. Allg. Chem. | 17,924 | 7,299 | 1928, 2008, 2025 |
| Acta Crystallogr., Sect. B (1968–1982) | 8,530 | 7,219 | 1968, 1977, 1982 |
| Z. Kristallogr. - New Cryst. Struct. | 8,179 | 6,584 | 1997, 2013, 2025 |
| Inorg. Chem. Commun. | 10,141 | 6,265 | 0, 2012, 2025 |

- **Acta Crystallographica Section E** has the most papers of any journal, and almost exactly
  one entry per paper. It is listed under two names: "Structure Reports Online" (39,466 DOIs,
  2001–2014) and "Crystallographic Communications" (4,169 DOIs, 2015 onward). It peaked at 4,000
  to 5,000 papers a year in 2007–2011, then fell to 200–400 a year after 2015. A few entries from
  2018–2022 are still filed under the old name.
- **Crystallography journals** (Acta Cryst. B, C and E, Z. Kristallogr. NCS) have about one entry
  per paper. Chemistry journals have many: Inorg. Chem. has 3.1 entries per paper and Cryst.
  Growth Des. has 4.7.
- **Year 0** appears for some entries of Chem. Commun., Dalton Trans., Inorg. Chem. Commun. and a
  few others (34 entries in all). It means the year is missing.

## Publishers

By DOI prefix, which identifies the publisher, and counting unique DOIs.

| Prefix | Publisher | Unique DOIs |
|---|---|---:|
| `10.1021/` | American Chemical Society (ACS) | 131,761 |
| `10.1016/` | Elsevier | 102,310 |
| `10.1039/` | Royal Society of Chemistry (RSC) | 88,195 |
| `10.1107/` | International Union of Crystallography (IUCr) | 77,743 |
| `10.1002/` | Wiley | 77,617 |
| `10.1007/` | Springer | 12,662 |
| `10.1080/` | Taylor & Francis | 10,311 |
| `10.1515/` | De Gruyter | 5,723 |
| `10.1246/` | Chemical Society of Japan | 5,470 |
| `10.3390/` | MDPI | 4,872 |

The top five publishers hold 86% of the DOIs. 20 DOIs do not start with `10.<number>/`, so they
are malformed.

## Journals without DOIs

64,086 journal entries have no DOI. Most are from older or regional journals that did not assign
DOIs. The median year in the table is the median publication year of the entries without a DOI.

| Journal | Entries without a DOI | Median year |
|---|---:|---:|
| Z. Naturforsch., B: Chem. Sci. | 6,150 | 1997 |
| Jiegou Huaxue | 4,167 | 2006 |
| Izv. Akad. Nauk SSSR, Ser. Khim. | 3,575 | 2005 |
| Zh. Strukt. Khim. | 3,193 | 1991 |
| Koord. Khim. | 2,903 | 2001 |
| J. Chem. Soc. Chem. Comm. | 2,534 | 1988 |
| Wuji Huaxue Xuebao | 2,335 | 2009 |
| Cryst. Struct. Commun. | 2,022 | 1979 |
| Zh. Neorg. Khim. | 2,016 | 2002 |
| Kristallografiya | 1,631 | 1992 |

## Open-access journals

380 CSD journals are in the DOAJ. Their papers published after each journal became fully open
access make up 65,981 entries and **27,809 unique DOIs** (5% of all DOIs). The largest:

| Journal | Open access since | Licence | Open-access DOIs |
|---|---:|---|---:|
| Acta Crystallogr., Sect. E: Cryst. Commun. | 2015 | CC BY | 4,168 |
| Z. Kristallogr. - New Cryst. Struct. | 2014 | CC BY | 4,022 |
| Chemical Science | 2015 | CC BY, CC BY-NC | 3,858 |
| Molecules | 1997 | CC BY | 1,994 |
| IUCrData | 2016 | CC BY | 1,907 |
| RSC Advances | 2017 | CC BY, CC BY-NC | 1,845 |
| Nature Communications | 2015 | CC BY, CC BY-NC-ND | 1,664 |
| ACS Omega | 2016 | CC BY, CC BY-NC-ND | 1,073 |
| Crystals | 2011 | CC BY | 802 |
| Beilstein J. Org. Chem. | 2005 | CC BY | 724 |
| Inorganics | 2013 | CC BY | 381 |
| Molbank | 2002 | CC BY | 346 |
| Scientific Reports | 2011 | CC BY, CC BY-NC-ND | 339 |
| ARKIVOC | 2000 | CC BY | 241 |
| CCS Chemistry | 2019 | CC BY-NC | 232 |
| J. Braz. Chem. Soc. | 1990 | CC BY | 195 |
| IUCrJ | 2014 | CC BY | 166 |
| JACS Au | 2021 | CC BY, CC BY-NC-ND | 159 |
| Communications Chemistry | 2018 | CC BY, CC BY-NC-ND | 153 |
| Materials Advances | 2020 | CC BY, CC BY-NC | 151 |

- Acta E under its old name, "Structure Reports Online" (2001–2014), is not matched, because the
  DOAJ only lists the current title.
- The three journals in the table that publish one structure per paper, Acta E, Z. Kristallogr.
  NCS and IUCrData, make up 36% of the open-access DOIs.
- A journal that lists several licences lets authors choose. Only CC BY allows reuse for any
  purpose, including commercial use.

## Data quirks

- `issn` and `eissn` are 0 for every entry, and `publisher_name` and `url` are always empty. So
  journals can only be identified by name or by the CODEN (`international_coden`).
- DOIs that differ only in letter case occur: there are 18 more unique DOIs before making them
  lowercase.
