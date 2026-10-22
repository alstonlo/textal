# The website

The website (`src/viz/app.py`) shows the extracted records next to their papers. It keeps the
look of the first version (FastAPI and Jinja, crystal thumbnails, the element colours, the flat
unit-cell drawing, whole molecules across the cell boundary) but draws every structure from the
publisher's original CIF, parsed with Gemmi, never from a CSD CIF. The downloaded files are
served unchanged.

The entry page puts **What the paper says about this crystal** on the left and the full paper on
the right; on a narrow screen the two columns stack. A quote jumps to the matching paragraph of
the paper or its supplementary document. For Acta E papers, the experimental sections that the
extraction read are also shown, folded below the record.

## What the website may show

The website opens only `publisher_entries.parquet`, `publisher_papers.parquet` and
`publisher_snapshot.json` in `src/viz/assets/`, in the `publisher-only-v2` schema, and refuses
tables with any other column. It never opens the CSD metadata, a CSD CIF, SMILES or DrugBank
attributes. The refcodes and their DOIs are the only link to the CSD. The front page says so.

- The title, journal, year and licence of a paper come from the publisher's XML, Europe PMC or
  the publisher's Crossref deposit. The heading of an entry is a compound name that the paper
  supports (its label in the paper, or the chemical title of an Acta E paper); when none is
  found, the compound label or the refcode is shown instead.
- Of a record, only these are exported: the status, the summary, the compound label, the six
  topic paragraphs, their quotes, and the time and model of the extraction. The matching
  rationale, the raw errors and the input metadata stay private. A paragraph is shown only when
  one of its quotes is found in the paper's text; the quote is marked as found in the text, or
  as merely recorded by the extraction when the text is not available. A summary is shown only
  when most of its words occur in the paper. These are lexical checks, not a check of meaning:
  the paragraphs are the model's paraphrase and still need a reader's review.
- The paper texts come from the archive of PMC packages (`data/publisher-texts/`, one file per
  DOI). Markdown is rendered without HTML, front matter is hidden, and image paths are not served.
- The CIFs and chemical schemes come from the same archive, copied into `data/publisher-cache/`
  the first time a page asks for them, and are served only when their checksum matches the
  package's receipt and their DOI matches the paper. A missing file is a gap; the website never
  falls back to a CSD file.
- A CIF belongs to a paper, not to a refcode. The thumbnail shows the first structure of the
  paper's first CIF, so refcodes of the same paper share a thumbnail, and the viewer lets the
  reader pick the file and block. The audit (`s0_audit_cifs.py`) counts refcodes whose paper has
  a CIF, not matched structures.

## Build and run

The inputs are listed in [`project-organization.md`](project-organization.md) under `data/viz/`.
The texts are exported where the archive of PMC packages is (Trillium), with the targets and
the archive's index:

```bash
pixi run python scripts/runs/viz/s0_export_texts.py --targets data/viz/publisher-targets.json \
  --control <archive>/control --output data/viz/publisher-texts.jsonl.gz
```

Everything else runs here. The Snakefile fetches the bibliography, imports the texts and builds
the tables:

```bash
pixi run snakemake -s scripts/Snakefile -j1 assets
pixi run web --port 8000
```

The collection of 22 October 2026 holds 50,405 refcodes of 33,109 papers: 28,759 refcodes of
Acta E and 21,646 of the other journals. The website reloads the tables when
`publisher_snapshot.json` changes, so they can be rebuilt while it runs.

To show CIFs and schemes that are not yet in `data/publisher-cache/`, the website needs a login
to the machine that holds the archive, through an SSH control socket:

```bash
export TEXTAL_ASSET_SSH=1
export TEXTAL_SSH_CONTROL="$HOME/.ssh/trillium-%C"
export TEXTAL_ARCHIVE_SSH=<user>@trillium.alliancecan.ca
export TEXTAL_ARCHIVE_NODE=tri-dm2
```

Cached files need no login. A deployed website should be given a copy of the cache instead.

## Tests

```bash
pixi run python -m unittest discover -s tests/viz -v
```

The tests build the tables from synthetic papers, including deliberately planted CSD tables that
the loader must refuse. They cover the exclusion of private fields, the refusal of unknown
schemas, the isolation of the cache routes, the checksums of the original files, quoted atom
labels and multi-block CIFs, whole molecules across cell boundaries, the fallbacks for the
compound name, imports of other journals, and the preservation of the other journals' records
when the Acta E records are reimported.
