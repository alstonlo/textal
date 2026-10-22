# Project organization

An open dataset of crystallization procedures and outcomes, linked to crystal structures. For each structure in the CCDC, we download its metadata and the DOI of its paper, download the paper if it is open access, OCR it with [MinerU](https://github.com/opendatalab/mineru), and extract the crystallization procedure and outcome from the text. Each extracted record links back to its PDF.

## Layout

- `src/dataset/`: the Python package that builds the dataset: CCDC metadata, paper download, OCR and extraction.
- `src/viz/`: the Python package for the website that shows examples, and the figures for the
  report (`theme.py`: the colours, fonts and sizes of every figure, and `save`, which writes a
  figure as PNG).
- `scripts/`: the scripts, run from the repository root. [`Snakefile`](../scripts/Snakefile)
  names which script produces which file from which input, and runs them in order; see
  [`scripts/README.md`](../scripts/README.md).
  - `runs/`: the scripts that make the data, one folder per stage, from CCDC metadata download to
    extraction.
    - `bib/`: the bibliography, i.e. the papers of the CSD entries: downloads the open-access
      papers from PubMed Central (PMC), with the PMCID of each DOI.
  - `analysis/`: the scripts that only read the data: they print statistics (e.g., the numbers
    in [`csd-journal-stats.md`](csd-journal-stats.md)) or plot it (to `results/`).
- `data/` (untracked): the downloaded metadata, PDFs, OCR output and extracted records.
  - `raw/`: the files as downloaded, before any processing (e.g., `csd_metadata.full.parquet`, the
    metadata of every CSD entry).
  - `papers/`: one folder per stage (`raw/`, then e.g. `ocr/`), each holding one folder `<DOI>/`
    per paper, i.e. `<publisher prefix>/<suffix>/`, such as `10.1107/s2056989015009986/`. The
    folder name is the DOI itself (lowercase), except that the characters of the suffix that are
    not safe in a folder name become `_`, so the true DOI is in `metadata.parquet`. A paper's
    folder never changes, unlike its title or year, so every stage can point at it.
    - `raw/<DOI>/`: the paper as downloaded: `paper.pdf`, `paper.xml` (the full text from PMC,
      indented to be readable) and the supplementary files that are text documents (PDF, Word,
      RTF, ODT, plain text, TeX or HTML), `supplementary.<ext>`, or `supplementary-<n>.<ext>`
      when there are several. Other supplementary files (data such as CIFs, archives, images,
      videos) are not downloaded.
    - `parsed/<DOI>/`: the same files as Markdown, `paper.md` (from `paper.xml`, through pandoc
      and the filter `s1_parse.lua`, which keeps HTML out of the Markdown) and
      `supplementary*.md` (PDFs through PyMuPDF4LLM, which reads the text layer and drops the
      images; the rest through pandoc). `paper.pdf` is not parsed, since the XML has the same
      text.
    `papers/metadata.parquet` has one row per CSD paper in PMC, retracted papers left out: its
    folder (`dir`, relative to a stage folder), DOI, the CSD refcodes of its entries, its licence
    and what was downloaded (the columns are in `SCHEMA` of `scripts/runs/bib/s0_download.py`).
    `papers/parsed.parquet` has one row per downloaded paper: the Markdown files, their sizes,
    the scanned PDFs that have no text layer (`needs_ocr`) and errors (`SCHEMA` of
    `s1_parse.py`). `papers/download.jsonl` and `papers/parsed.jsonl` log each paper a stage
    finished, so a stopped run can resume.
- `results/`: the plots (PNG), one folder per data folder they describe, e.g. `papers/plots/`
  for `data/papers/`.
- `docs/`: the documents for people, listed in [`README.md`](README.md).
- `sandbox/` (untracked): dated scratch folders.

## Rules

- Every subfolder of `sandbox/` is named `YYYY-MM-DD-HH-MM-<topic>`, stamped with the local date
  and time (24-hour clock) at which it was created, e.g. `2026-10-21-14-17-journal-subset`.
- Every script in a stage folder of `scripts/runs/` is named `s<N>_<name>.py`, where `<N>` is the
  order in which it runs: `s0_` first, then `s1_`, `s2_`, and so on. A script may only use the
  outputs of scripts with a smaller `<N>`. Scripts that share the same `<N>` do not depend on each
  other, so they can run at the same time. Run scripts from the repository root, e.g.
  `pixi run python scripts/runs/bib/s0_download.py`. The same rules hold for
  `scripts/analysis/`, whose scripts may also use the outputs of any script in `scripts/runs/`.
