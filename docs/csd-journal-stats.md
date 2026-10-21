# CSD journal statistics

Statistics of the journals that the Cambridge Structural Database (CSD) entries were published
in: how many papers each journal has, how many have a DOI, which are open access, and which
subset of papers to focus on.
Last updated 2026-10-21.

## Sources

- `data/raw/csd_metadata.full.parquet`: the metadata of every CSD entry, one row per entry. The
  paper of an entry is in the `publication` column, which holds the journal (abbreviated and full
  name), the year and the DOI. The `publications` column always holds exactly one item, the same
  paper, so we ignore it.
- `data/raw/doaj/journals.csv`: the list of fully open-access journals from the
  [Directory of Open Access Journals (DOAJ)](https://doaj.org), with the year each journal started
  to publish all content under an open licence, and the licence.
- `data/raw/pmc/PMC-ids.csv.gz`: the DOI and PMCID of every article in PubMed Central (PMC), from
  NCBI.
- `data/raw/pmc/s3.jsonl`: for every CSD DOI in PMC, its newest version in PMC's open-access
  bucket on AWS, the files of that version with their sizes, and PMC's record of it (licence,
  open-access flag, whether it is an author manuscript).

To reproduce the numbers below, run these scripts from the repository root:

```bash
# Downloads the PMC DOI list and lists each CSD paper in PMC's bucket.
pixi run python scripts/runs/bib/s0_download.py --list_only true
# Downloads the DOAJ list if it is missing, and prints the numbers.
pixi run python scripts/analysis/s0_csd_journal_stats.py
```

Facts about journals that do not come from these files (formats, licences, access routes) were
checked on the web on 2026-10-21. The source is linked next to each one.

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
| Acta Crystallogr., Sect. E: Struct. Rep. Online | 39,541 | 39,465 | 2001, 2008, 2022 |
| Inorg. Chem. | 98,842 | 31,978 | 1962, 2011, 2025 |
| J. Am. Chem. Soc. | 70,318 | 25,900 | 1928, 2012, 2025 |
| Organometallics | 62,869 | 20,374 | 1982, 2009, 2025 |
| Acta Crystallogr., Sect. C: Cryst. Struct. Commun. | 24,780 | 19,661 | 1983, 1996, 2013 |
| Angew. Chem., Int. Ed. | 50,763 | 19,318 | 1968, 2017, 2025 |
| Chem. Commun. | 40,034 | 18,918 | 0, 2014, 2025 |
| Dalton Trans. | 65,182 | 17,801 | 0, 2015, 2025 |
| J. Org. Chem. | 34,489 | 16,287 | 1962, 2013, 2025 |
| Org. Lett. | 29,734 | 15,411 | 1999, 2018, 2025 |
| J. Organomet. Chem. | 32,365 | 14,899 | 1963, 2004, 2025 |
| Inorg. Chim. Acta | 33,997 | 14,182 | 1967, 2009, 2026 |
| Chem. Eur. J. | 48,878 | 13,325 | 1995, 2016, 2025 |
| Polyhedron | 32,351 | 12,670 | 1982, 2012, 2025 |
| J. Mol. Struct. | 22,894 | 11,326 | 1968, 2018, 2026 |
| Eur. J. Inorg. Chem. | 30,926 | 8,650 | 1998, 2012, 2025 |
| Tetrahedron Lett. | 12,540 | 8,526 | 1960, 2007, 2025 |
| J. Chem. Soc., Dalton Trans. | 17,455 | 8,157 | 1972, 1996, 2002 |
| Tetrahedron | 15,564 | 7,820 | 1958, 2009, 2025 |
| Cryst. Growth Des. | 35,397 | 7,559 | 2001, 2016, 2025 |
| CrystEngComm | 31,094 | 7,510 | 1999, 2015, 2025 |
| Z. Anorg. Allg. Chem. | 17,924 | 7,298 | 1928, 2008, 2025 |
| Acta Crystallogr., Sect. B (1968–1982) | 8,530 | 7,218 | 1968, 1977, 1982 |
| Z. Kristallogr. - New Cryst. Struct. | 8,179 | 6,583 | 1997, 2013, 2025 |
| Inorg. Chem. Commun. | 10,141 | 6,265 | 0, 2012, 2025 |

- **Acta Crystallographica Section E** has the most papers of any journal, and almost exactly
  one entry per paper. It is listed under two names: "Structure Reports Online" (39,465 DOIs,
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
access make up 65,981 entries and **27,808 unique DOIs** (5% of all DOIs). The largest:

| Journal | Open access since | Licence | Open-access DOIs |
|---|---:|---|---:|
| Acta Crystallogr., Sect. E: Cryst. Commun. | 2015 | CC BY | 4,168 |
| Z. Kristallogr. - New Cryst. Struct. | 2014 | CC BY | 4,021 |
| Chemical Science | 2015 | CC BY, CC BY-NC | 3,857 |
| Molecules | 1997 | CC BY | 1,993 |
| IUCrData | 2016 | CC BY | 1,907 |
| RSC Advances | 2017 | CC BY, CC BY-NC | 1,845 |
| Nature Communications | 2015 | CC BY, CC BY-NC-ND | 1,664 |
| ACS Omega | 2016 | CC BY, CC BY-NC-ND | 1,073 |
| Crystals | 2011 | CC BY | 802 |
| Beilstein J. Org. Chem. | 2005 | CC BY | 723 |
| Inorganics | 2013 | CC BY | 381 |
| Molbank | 2002 | CC BY | 345 |
| Scientific Reports | 2011 | CC BY, CC BY-NC-ND | 339 |
| ARKIVOC | 2000 | CC BY | 240 |
| CCS Chemistry | 2019 | CC BY-NC | 232 |
| J. Braz. Chem. Soc. | 1990 | CC BY | 195 |
| IUCrJ | 2014 | CC BY | 166 |
| JACS Au | 2021 | CC BY, CC BY-NC-ND | 159 |
| Communications Chemistry | 2018 | CC BY, CC BY-NC-ND | 153 |
| Materials Advances | 2020 | CC BY, CC BY-NC | 151 |

- Acta E under its old name, "Structure Reports Online" (2001–2014), is not matched, because the
  DOAJ only lists the current title. It is open access from 2008 all the same: of its 23,125
  papers in the PMC bucket (2008 onward), PMC gives 22,490 a CC BY licence, and 634 carry IUCr
  terms of use (see "Full text in PubMed Central"). Before 2008, Crossref lists only IUCr's
  copyright policy as the licence (10 papers checked).
- The three journals in the table that publish one structure per paper, Acta E, Z. Kristallogr.
  NCS and IUCrData, make up 36% of the open-access DOIs.
- A journal that lists several licences lets authors choose. Only CC BY allows reuse for any
  purpose, including commercial use.

## Full text in PubMed Central

**56,276 CSD DOIs** (10%) are in PubMed Central (PMC), covering 121,207 entries. Which journals
have the most:

| Journal | Unique DOIs | In PMC |
|---|---:|---:|
| Acta Crystallogr., Sect. E: Struct. Rep. Online | 39,465 | 23,133 |
| Acta Crystallogr., Sect. E: Cryst. Commun. | 4,169 | 4,141 |
| Chemical Science | 4,452 | 3,904 |
| J. Am. Chem. Soc. | 25,900 | 2,940 |
| Angew. Chem., Int. Ed. | 19,318 | 1,987 |
| Molecules | 1,993 | 1,985 |
| Nature Communications | 1,756 | 1,677 |
| RSC Advances | 4,320 | 1,533 |
| Inorg. Chem. | 31,978 | 1,286 |
| Chem. Eur. J. | 13,325 | 1,274 |
| ACS Omega | 1,073 | 1,062 |
| Org. Lett. | 15,411 | 1,024 |
| J. Org. Chem. | 16,287 | 819 |
| Beilstein J. Org. Chem. | 723 | 722 |
| IUCrData | 1,907 | 625 |

PMC puts its reusable articles in an
[open-access bucket on AWS](https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/)
(`pmc-oa-opendata`), which anyone can download from without an account. That page says this
bucket and three APIs "are the only services that may be used for automated retrieval of PMC
content". Each article has a folder
with its PDF, its full text as XML, its figures and its supplementary files (CIFs, SI PDFs, ...),
and a record with its licence. So for these papers we have the text without OCR.

**55,052 of the 56,276 DOIs are in the bucket.** The other 1,224 are in PMC but not in the bucket;
the most are from PNAS (264), J. Am. Chem. Soc. (151) and ACS Med. Chem. Lett. (105).

The licence of each article in the bucket, from its PMC record:

| Licence | DOIs | With a PDF | Note |
|---|---:|---:|---|
| CC BY | 40,522 | 40,249 | |
| CC BY-NC | 4,012 | 3,896 | |
| CC BY-NC-ND | 2,292 | 2,270 | |
| CC BY-NC-SA, CC0 | 26 | 26 | |
| None given | 2,314 | 2,300 | open access under the publisher's own terms (see below) |
| TDM | 5,886 | 102 | author manuscripts (see below) |

- **No licence code** (2,314 DOIs): PMC flags these as open access, and the licence is stated in
  the article's XML instead. The two we read: ACS Omega's "ACS AuthorChoice License, which
  permits copying and redistribution of the article or any adaptations for non-commercial
  purposes", and Acta E's "terms described at journals.iucr.org/services/termsofuse.html". Most
  are from Acta E (634), ACS Omega (500) and J. Am. Chem. Soc. (365).
- **TDM** (5,886 DOIs): author manuscripts, i.e. the text the authors deposited in PMC after the
  paper was accepted. PMC does not flag most of them (5,784) as open access, but the bucket's page
  says that "all distributed author manuscripts" are "available for commercial reuse regardless
  of license". Almost none has a PDF (102), only the XML.
  They are most of the J. Am. Chem. Soc. (1,586 of 2,789), Org. Lett. and J. Org. Chem. papers in
  the bucket.
- **Size**: the PDFs, the XML and the files other than figures of all 55,052 articles take about
  290 GB, of which the PDFs are 77 GB. Acta E takes 30 GB for 27,266 DOIs; the other journals take
  the rest, mostly for SI PDFs. 15 articles have a file over 200 MB.

### PMC and the open-access journals

PMC and the DOAJ list overlap only in part: PMC has single articles from any journal, and many
open-access journals do not deposit in PMC.

| | In the PMC bucket | Not in the PMC bucket |
|---|---:|---:|
| In a DOAJ journal, after it became open access | 18,092 | 9,716 |
| Not | 36,960 | 490,188 |

- Of the 36,960 DOIs in the bucket but not in a DOAJ journal, 23,126 are Acta E 2008–2014 (see
  "Open-access journals" above), and the rest are open articles or author manuscripts in
  subscription journals.
- The 9,716 DOIs in DOAJ journals but not in the bucket are mostly from Z. Kristallogr. NCS
  (4,021), IUCrData before about 2020 (1,282), Crystals (797), Inorganics (379), Molbank (344),
  RSC Advances (317), ARKIVOC (240) and CCS Chemistry (232). Their publishers' sites refuse
  crawlers (robots.txt or HTTP 403 for MDPI, IUCr and RSC, a bot check for De Gruyter; checked on
  2026-10-21), so they would need a request to each publisher.

## Choosing a focus subset

We want papers that (1) report how each crystal was grown, (2) can be downloaded and shared, and
(3) link cleanly to one CSD entry. The candidate subsets:

| Subset | Entries | Unique DOIs | In PMC | CSD `solvent` filled |
|---|---:|---:|---:|---:|
| Acta E 2001–2007 | 16,353 | 16,340 | 8 | 63% |
| Acta E 2008–2014 | 23,179 | 23,117 | 23,117 | 37% |
| Acta E 2015 onward | 5,618 | 4,177 | 4,149 | 4% |
| IUCrData (2016 onward) | 1,917 | 1,907 | 625 | 11% |
| Z. Kristallogr. NCS 2019 onward | 2,568 | 2,547 | 0 | 3% |
| Other journals in PMC | 91,808 | 28,377 | 28,377 | 15% |

The CSD `solvent` field holds the crystallization solvent as a single string (e.g.,
`ethanol`), with no method, temperature or time. Where it is filled, it can check the solvents we
extract.

### Recommendation: Acta E from 2008 onward, from the PMC bucket (27,266 DOIs)

- **Open access under CC BY.** Acta E has been open access since 2008
  ([editorial](https://pmc.ncbi.nlm.nih.gov/articles/PMC4120596)). Its articles carry CC BY 2.0
  UK, and CC BY 4.0 since about 2022.
- **Crystallization is reported in a fixed place.** Before 2015, articles had Comment,
  Experimental and Refinement sections, and the Experimental section describes the synthesis and
  how the crystals were grown. Since 2015, research articles have a "Synthesis and
  crystallization" section ([editorial](https://pmc.ncbi.nlm.nih.gov/articles/PMC4120596)). A
  full-text search of Europe PMC suggests about 85% of 2008–2014 articles and 92% of articles from
  2015 onward mention how crystals were grown. This is a rough estimate from keyword matches.
- **One structure per paper**, so each paper links to one CSD entry.
- **Full text as XML, the PDF and the CIF, from the PMC bucket**, so no OCR. The publisher site
  (journals.iucr.org) blocks automated downloads.
- **The CSD `solvent` field is filled for 37% of the 2008–2014 entries**, which gives about 8,500
  papers to check the extracted solvents against.
- The deposited CIFs do not contain the article text, so the text must come from the article.
  The published CIFs we checked keep only `_publ_section_title`.

### Other subsets, in order of value

1. **IUCrData in PMC** (625 DOIs, 2020 onward): same publisher, CC BY, a "Synthesis and
   crystallization" section, one structure per paper. The 1,282 IUCrData DOIs from before 2020
   are not in PMC and must come from the publisher site.
2. **Z. Kristallogr. NCS 2019 onward** (2,547 DOIs): CC BY 4.0 from 2019 (CC BY-NC-ND from 2014
   to 2018), one structure per paper, and a "Source of material" section with the synthesis and
   crystallization. It is not in PMC, and the publisher site (degruyter.com) blocks automated
   downloads, so it may need a request to De Gruyter.
3. **Other journals in PMC** (28,377 DOIs, 3.2 entries per paper): more varied chemistry, led
   by Chemical Science, JACS, Angewandte, Molecules and Nature Communications. But crystallization
   details are often only in the supporting information (SI). The PMC bucket holds the SI as PDFs,
   which need text extraction. Licences are mixed: many articles are CC BY-NC or CC BY-NC-ND, and
   author manuscripts carry no CC licence (PMC still allows their reuse).
4. **Not worth it now:** Acta E 2001–2007 (16,340 DOIs) is not in PMC and not open access,
   although the CSD `solvent` field is filled for 63% of it. The large subscription journals
   (Inorg. Chem., Dalton Trans., Organometallics, ...) need publisher text-mining agreements.

### Prior work

As far as we found, no public dataset links small-molecule crystallization procedures (method,
solvent, temperature, time) to CSD entries. The closest work:

- Studies that use the CSD `solvent` field, e.g. Cole, Raithby and Taylor,
  [Cryst. Growth Des. 2021](https://doi.org/10.1021/acs.cgd.0c01490).
- LLM extraction of synthesis conditions for metal–organic frameworks linked to CSD entries, e.g.
  [L2M3](https://arxiv.org/abs/2404.13053) (about 40,000 papers).
- Small crystallization datasets from experiments, e.g. Pillong et al.,
  [CrystEngComm 2017](https://doi.org/10.1039/c7ce00738h) (5,710 evaporation trials).

## Data quirks

- `issn` and `eissn` are 0 for every entry, and `publisher_name` and `url` are always empty. So
  journals can only be identified by name or by the CODEN (`international_coden`).
- DOIs that differ only in letter case occur: there are 18 more unique DOIs before making them
  lowercase.
