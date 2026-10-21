# CSD statistics

Statistics of the Cambridge Structural Database (CSD) entries, focused on whether each entry links
to a journal paper and a DOI. Last updated 2026-10-21.

## Sources

- `data/raw/csd_metadata.full.parquet`: the metadata of every CSD entry, one row per entry. The
  paper of an entry is in the `publication` column, which holds the journal name and the DOI. The
  `publications` column always holds exactly one item, the same paper, so we ignore it.
- `~/code/clari-2/data/csd/metadata.parquet`: the entries seen by the Clari model, whose code is in
  `~/code/clari-2`. Each row has a `split` (train, val or test) and a `keep` flag. An entry is
  used to train, validate or test the model only if `keep` is true. The `id` column matches
  `identifier` in the file above.

To reproduce the numbers below, run these scripts from the repository root:

- `pixi run python scripts/download/s0_csd_stats.py`: the section "All CSD entries".
- `pixi run python scripts/download/s0_clari_stats.py`: the section "Entries used by the Clari
  model".

## Definitions

- **Real journal**: every entry has a journal name, but some names are not journals. We count an
  entry as having a real journal unless its name is one of the following (`NOT_JOURNALS` in
  `src/dataset/csd.py`):
  - `CSD Communication`: a structure sent straight to the CSD with no paper.
  - `ICSD Communication`, `Thesis`, `U.S.Patents`, `NASA Technical Reports`,
    `University of Southampton, Crystal Structure Report Archive`.

  A few book titles are still counted as real journals. They cover very few entries.
- **DOI**: a missing DOI is null (never an empty string). DOIs are not case-sensitive, so we strip
  spaces and make them lowercase before counting unique DOIs. This merges 18 DOIs that appear
  twice with different letter case.

## All CSD entries

| | Entries | With a DOI |
|---|---:|---:|
| All entries | 1,413,222 | 1,277,514 (90.4%) |
| Real journal | 1,340,730 | 1,276,644 (95.2%) |
| Not a journal | 72,492 | 870 (1.2%) |

- **Unique DOIs**: 555,768.
- **Entries per DOI**: 2.3 on average. 288,056 DOIs (52%) cover only one entry, 90% cover 5 or
  fewer, and 99% cover 11 or fewer. The largest is `10.1002/cssc.201601752` with 1,853 entries.
  The next largest is `10.1107/s2052252520010441` with 417 entries.
- **Publishers**: about half of the DOIs come from ACS (`10.1021/`, 365,230 entries), RSC
  (`10.1039/`, 240,520) and Wiley (`10.1002/`, 212,571). Elsevier (`10.1016/`, 211,670) and the
  IUCr (`10.1107/`, 97,635) follow. 27 DOIs do not start with `10.<number>/`, so they are
  malformed.
- **Real journals without a DOI** (about 64,000 entries) are mostly older or regional journals,
  such as Z. Naturforsch. B, Jiegou Huaxue and Russian journals like Zh. Strukt. Khim. The median
  publication year of these entries is between 1979 and 2009, depending on the journal.
- **Largest journals**: Inorg. Chem. (98,842 entries), J. Am. Chem. Soc. (70,318), CSD
  Communication (69,896, not a journal), Dalton Trans. (65,182) and Organometallics (62,869).
- **ISSN**: the `issn` and `eissn` fields are 0 for every entry, so they cannot be used.

## Entries used by the Clari model

The Clari metadata lists 1,333,470 entries. Of these, 921,058 are kept and used by the model.

| Split | Entries used | Real journal | With a DOI | Unique DOIs |
|---|---:|---:|---:|---:|
| train | 917,014 | 865,361 (94.4%) | 825,155 (90.0%) | 416,112 |
| val | 1,048 | 988 (94.3%) | 941 (89.8%) | 935 |
| test | 2,996 | 2,700 (90.1%) | 2,519 (84.1%) | 1,559 |
| **All** | **921,058** | **869,049 (94.4%)** | **828,615 (90.0%)** | **417,567** |

- **Entries per DOI**: 2.0 on average. 242,264 DOIs (58%) cover only one entry, 90% cover 4 or
  fewer, and 99% cover 9 or fewer. The largest is `10.1107/s2052252520010441` with 417 entries.
  The 1,853 entries of `10.1002/cssc.201601752` are all filtered out.
- **Papers shared between splits**: 1,039 DOIs have entries in more than one split. The split
  seems to be based on chemical compounds (one filter reason is "contains test component"), so
  this is likely expected. It does mean the model may have seen other structures from the same
  paper as a test entry during training.

### Why entries were filtered out

These are the reasons for the 412,412 entries with `keep` false.

| Reason | Entries |
|---|---:|
| polymeric | 138,011 |
| over 512 atoms in unit cell | 127,535 |
| r factor too high | 49,092 |
| contains test component | 37,746 |
| too recent | 21,210 |
| overlapping atoms within a body | 9,889 |
| powder study | 9,416 |
| clashing atoms within a body | 6,844 |
| overlapping atoms between bodies | 5,761 |
| non-ambient pressure | 4,971 |
| clashing atoms between bodies | 1,235 |
| cif missing field `_atom_site_label` | 536 |
| failed to parse mol2 | 135 |
| no bonds | 22 |
| dummy atom in mol2 | 7 |
| atom in mol2 not in cif | 2 |

The filter settings, from the Clari `config.json`: R factor at most 10.0, deposited before
2025-05-01, and at most 512 atoms in the unit cell.
