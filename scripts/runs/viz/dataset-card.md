---
pretty_name: TEXtal
license: other
license_name: per-paper
license_link: https://github.com/alstonlo/textal#licence
---

# TEXtal data

Crystallization procedures extracted from the open-access papers of CSD entries, with the paper
texts, CIFs and chemical schemes of the papers whose licence allows them to be shared. This folder
is everything the TEXtal website reads. See https://github.com/alstonlo/textal.

- `entries.parquet`: one row per CSD refcode, with its extracted record (`extraction_json`).
- `papers.parquet`: one row per paper, with its bibliography, authors, licence and quoted passages.
- `snapshot.json`: counts per extraction status, collection and journal.
- `texts/<NN>/<PMCID>.json.gz`: the text of one paper and of its supplementary documents, as
  Markdown; `NN` is the last two digits of the PMCID.
- `files/<NN>/<PMCID>.tar.gz`: the publisher's CIFs and chemical schemes of one paper, with a
  manifest of each file's source URL and SHA-256.

```bash
hf download alstonlo/textal-data --repo-type dataset --local-dir textal
```

## Licences

Every file of `texts/` and `files/` belongs to one paper and keeps that paper's licence, which is
in `licenses_json` of `papers.parquet`. Only papers under a Creative Commons licence (CC BY,
CC BY-SA, CC BY-NC, CC BY-NC-SA, CC BY-NC-ND or CC0) have them; author manuscripts and papers
under the publisher's own terms have only their record and short quotes. In using these files:

- Credit the paper: its authors (`authors_json`), title, journal, year and DOI.
- Under a licence with NC, use the files for non-commercial purposes only.
- Under a licence with ND, share the texts only unchanged. They were converted from the PMC
  XML to Markdown (with pandoc) and from PDF to Markdown (with PyMuPDF4LLM), without their
  images; the words are not edited.
- Under a licence with SA, share what you make from the files under the same licence.

The licence is the one of the copy in PubMed Central, which is the copy released here.

## What comes from where

The CSD contributes only the refcodes and their link to a paper (DOI). No CSD metadata is
included: sentences of the extracted records that repeat a value of the CSD entry that the paper
does not state (a name, formula, colour, solvent and the like), or that cite the CSD entry, were
removed. This check compares words, so a value that the model reworded is not caught. The
records are the language model's summaries of the papers; each paragraph is kept only if one of
its quotes is found in the paper. The bibliography comes from the publisher's XML, Europe PMC or
Crossref.
