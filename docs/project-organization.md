# Project organization

An open dataset of crystallization procedures and outcomes, linked to crystal structures. For each structure in the CCDC, we download its metadata and the DOI of its paper, download the paper if it is open access, OCR it with [MinerU](https://github.com/opendatalab/mineru), and extract the crystallization procedure and outcome from the text. Each extracted record links back to its PDF.

## Layout

- `src/dataset/`: the Python package that builds the dataset: CCDC metadata, paper download, OCR and extraction.
- `src/viz/`: the Python package for the website that shows examples, and the figures for the report.
- `scripts/`: the scripts that run each stage, from CCDC metadata download to extraction.
- `data/` (untracked): the downloaded metadata, PDFs, OCR output and extracted records.
- `docs/`: the documents for people, listed in [`README.md`](README.md).
- `sandbox/` (untracked): dated scratch folders.

## Rules

- Every subfolder of `sandbox/` is named `YYYY-MM-DD-<topic>`, dated the day it was created.
