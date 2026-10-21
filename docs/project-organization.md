# Project organization

An open dataset of crystallization procedures and outcomes, linked to crystal structures. For each structure in the CCDC, we download its metadata and the DOI of its paper, download the paper if it is open access, OCR it with [MinerU](https://github.com/opendatalab/mineru), and extract the crystallization procedure and outcome from the text. Each extracted record links back to its PDF.

## Layout

- `src/dataset/`: the Python package that builds the dataset: CCDC metadata, paper download, OCR and extraction.
- `src/viz/`: the Python package for the website that shows examples, and the figures for the report.
- `scripts/`: the scripts that run each stage, from CCDC metadata download to extraction.
  - `download/`: the scripts that download the CCDC metadata and the papers, and summarize them
    (the numbers in [`csd-journal-stats.md`](csd-journal-stats.md)).
- `data/` (untracked): the downloaded metadata, PDFs, OCR output and extracted records.
  - `raw/`: the files as downloaded, before any processing (e.g., `csd_metadata.full.parquet`, the
    metadata of every CSD entry).
- `docs/`: the documents for people, listed in [`README.md`](README.md).
- `sandbox/` (untracked): dated scratch folders.

## Rules

- Every subfolder of `sandbox/` is named `YYYY-MM-DD-HH-MM-<topic>`, stamped with the local date
  and time (24-hour clock) at which it was created, e.g. `2026-10-21-14-17-journal-subset`.
- Every script in a subfolder of `scripts/` is named `s<N>_<name>.py`, where `<N>` is the order
  in which it runs: `s0_` first, then `s1_`, `s2_`, and so on. A script may only use the outputs
  of scripts with a smaller `<N>`. Scripts that share the same `<N>` do not depend on each other,
  so they can run at the same time. Run scripts from the repository root, e.g.
  `pixi run python scripts/download/s0_csd_stats.py`.
