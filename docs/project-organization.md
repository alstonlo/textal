# Project organization

An open dataset of crystallization procedures and outcomes, linked to crystal structures. For
each structure in the CSD, we download its metadata and the DOI of its paper, download the paper
if it is open access in PubMed Central (PMC), convert it to Markdown, and extract the
crystallization procedure and outcome from the text with a language model. Each extracted record
quotes the paper. Acta Crystallographica Section E (Acta E), the journal with the most CSD
entries, was also collected whole from the publisher's side (its open-access list and PMC
packages, with the original CIFs and chemical schemes), which the website serves.

## Layout

- `src/dataset/`: the Python package that builds the dataset: CCDC metadata, paper download, OCR and extraction.
- `src/viz/`: the Python package for the website that shows the records, and the figures for
  the report (`theme.py`: the colours, fonts and sizes of every figure, and `save`, which writes
  a figure as PNG). [`website.md`](website.md) describes the website and what it may show.
  - `app.py`: the website, a FastAPI app; run it with `pixi run web --port 8000` and open
    http://localhost:8000. It reads only `assets/` and the two caches below, never `data/raw/`
    or `data/papers/`. The landing page shows the statistics of the collection; `/explore` lists
    the entries, each as the filled unit cell of its paper's publisher CIF drawn flat by
    `crystal.py` (a small CIF parser that applies the symmetry operators); `/entry/<refcode>`
    shows one entry: its crystal structures (the publisher CIFs, drawn by 3Dmol), its chemical
    scheme, its paper's text and its extracted record, with each paragraph's quotes.
    `publisher_assets.py` serves the CIFs and schemes from `data/publisher-cache/`,
    `publisher_text.py` the paper texts from `data/publisher-texts/`, `publisher_data.py` loads
    the tables and refuses any column it does not know, and `names.py` picks the compound name
    shown as each entry's heading.
  - `assets/` (untracked but for `stats.json`): the tables of the website, written by
    `scripts/runs/viz/s2_assets.py`: `publisher_papers.parquet`, one row per paper (its PMCID,
    DOI, title, journal, year, licence and, for Acta E, the paragraphs of its experimental
    section); `publisher_entries.parquet`, one row per CSD refcode with the part of its record
    that may be shown (the paragraphs that have a quote found in the paper's text; see
    [`website.md`](website.md)); and `publisher_snapshot.json`, the counts and the time of the
    build. `stats.json` has the corpus statistics of the landing page (counts only, so it can be
    tracked).
  - `templates/` (Jinja) and `static/` (CSS and the page scripts): the pages of the website.
- `scripts/`: the scripts, run from the repository root. [`Snakefile`](../scripts/Snakefile)
  names which script produces which file from which input, and runs them in order; see
  [`scripts/README.md`](../scripts/README.md).
  - `runs/`: the scripts that make the data, one folder per stage, from CCDC metadata download to
    extraction.
    - `csd/`: exports the metadata of every CSD entry with the CSD Python API, which needs a CCDC
      licence and runs in its own pixi environment (`pixi run -e csd ...`).
    - `bib/`: the bibliography, i.e. the papers of the CSD entries: downloads the open-access
      papers from PubMed Central (PMC), with the PMCID of each DOI.
    - `viz/`: the tables of the website. `s0_bibliography.py` fetches the title, journal, year
      and licence of each paper from Europe PMC and Crossref; `s0_export_texts.py` reads the
      paper texts out of the archive of PMC packages (it runs where that archive is) and
      `s1_import_texts.py` loads them into `data/publisher-texts/`; `s2_assets.py` joins the
      Acta E collection, the extracted records, the bibliography and the texts into the tables
      of `src/viz/assets/`; `s0_audit_cifs.py` counts the papers with a publisher CIF.
  - `analysis/`: the scripts that only read the data: they print statistics (e.g., the numbers
    in [`csd-journal-stats.md`](csd-journal-stats.md)) or plot the figures of the README (to
    `docs/assets/`).
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
  - `runs/<name>/`: one folder per extraction run, written by `dataset.extraction_stream`
    ([`EXTRACTION_RUNS.md`](EXTRACTION_RUNS.md) lists the runs and what each folder holds).
  - `extractions.parquet`: a snapshot of the extracted records of all runs, one row per CSD entry
    (in the schema of `dataset.extraction_schema`; [`EXTRACTION_SCHEMA.md`](EXTRACTION_SCHEMA.md)
    explains the columns). The analysis scripts, the example figure and the website's tables are
    built from it.
  - `viz/`: the inputs of the website's tables, made elsewhere and taken as given.
    `acta-e-papers.jsonl.gz` is the Acta E collection: one line per open-access Acta E paper in
    PMC, with its PMCID, DOI, title, year, licence, the paragraphs of its experimental sections
    and the CSD refcodes linked to it. `publisher-targets.json` lists the papers of the other
    journals (DOI and PMCID), `publisher-bibliography.json` their title, journal, year and
    licence (written by `s0_bibliography.py`), and `publisher-texts.jsonl.gz` the Markdown of
    their text and supplementary documents (written by `s0_export_texts.py`).
    `csd_drugs_with_paper.parquet` is the CSD drug subset (one row per refcode and DrugBank ID)
    with each entry's CCDC number, CIF and paper; the README's example record is drawn from it.
  - `publisher-texts/`: the paper texts of the website, one gzipped JSON per DOI, written by
    `s1_import_texts.py`.
  - `publisher-cache/`: the publisher CIFs and chemical schemes that the website has served,
    copied from the archive of PMC packages the first time a page asks for them.
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
