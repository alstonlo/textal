---
pretty_name: TEXtal
license: other
license_name: per-paper
license_link: https://github.com/alstonlo/textal#licence
---

# TEXtal data

Crystallization procedures extracted from the open-access papers of 50,405 CSD entries, with the
CIFs and chemical schemes the publishers supplied. See https://github.com/alstonlo/textal.

- `entries.parquet`: one row per CSD refcode, with its extracted record (`extraction_json`).
- `papers.parquet`: one row per paper, with its bibliography, licence and quoted passages.
- `snapshot.json`: counts per extraction status, collection and journal.
- `files/<NN>/<PMCID>.tar.gz`: the publisher's CIFs and chemical schemes of one paper, with a
  manifest; `NN` is the last two digits of the PMCID.

```bash
hf download alstonlo/textal-data --repo-type dataset --local-dir textal
```
