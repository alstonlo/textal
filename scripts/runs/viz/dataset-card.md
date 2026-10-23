---
pretty_name: TEXtal
license: other
license_name: per-paper
license_link: https://github.com/alstonlo/textal#licence
---

# TEXtal data

Crystallization procedures extracted from the open-access papers of 50,405 CSD entries, with the
texts, CIFs and chemical schemes of the papers under a Creative Commons licence. See
https://github.com/alstonlo/textal.

- `entries.parquet`: one row per CSD refcode, with its extracted record (`extraction_json`).
- `papers.parquet`: one row per paper, with its bibliography, authors, licence and quoted passages.
- `snapshot.json`: counts per extraction status, collection and journal.
- `texts.tar`: the folder `texts/`, where `texts/<NN>/<PMCID>.json.gz` is the text of one paper
  and of its supplementary documents, as Markdown; `NN` is the last two digits of the PMCID.
- `files.tar`: the folder `files/`, where `files/<NN>/<PMCID>.tar.gz` holds the publisher's CIFs
  and chemical schemes of one paper, with a manifest.

Download the dataset and unpack the two folders:

```bash
hf download alstonlo/textal-data --repo-type dataset --local-dir data/textal
cd data/textal && tar -xf texts.tar && tar -xf files.tar && rm texts.tar files.tar
```

## License

Each paper keeps its licence, which is in `licenses_json` of `papers.parquet`. The texts, CIFs
and chemical schemes of a paper are included only if it is under a Creative Commons licence;
when you use them, credit the paper's authors, title, journal and DOI and follow its licence
terms (for example, non-commercial use only under CC BY-NC). The CSD metadata is licensed by
the CCDC and is not included: the dataset holds only refcodes and DOIs from the CSD.
