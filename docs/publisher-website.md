# Publisher-only TEXtal website

This branch starts from `main` at `97595a9`. It preserves the main website's
FastAPI/Jinja layout, crystal thumbnails, element palette, unit-cell drawing,
whole-molecule packing and optional faint surrounding molecules. Geometry is
parsed with Gemmi from the publisher's original CIF, never from a CSD CIF.
The original download is byte-for-byte unchanged. The browser receives a safe
coordinate representation for display inside an isolated 3Dmol document.

## Public data boundary

The website only opens `publisher_entries.parquet`, `publisher_papers.parquet`
and `publisher_snapshot.json`. It never opens the old `entries.parquet`, a CSD
CIF, `csd_metadata.full.parquet`, SMILES, DrugBank attributes or CSD record fields.
Refcodes and their paper associations are the identifier bridge. Bibliography,
full procedure snippets, licence evidence, CIFs and chemical schemes come from
publisher records in saved PMC OA packages. Matching context, raw model errors,
compound labels and summaries are excluded. A procedural extraction field is
shown only when at least one supporting quote is verified in the source snippets.
The structured field is still a model paraphrase and should be checked against
its source. A quote match does not validate every claim in that paraphrase.

The private publisher cache is not mounted as a static directory. Download
routes allow only receipt-listed, checksum-verified publisher CIFs and chemical
schemes, with an approved PMC source URL and matching DOI. Receipts, XML,
manifest files, arbitrary cache files and internal archive paths are not exposed.
No CSD depiction is used as fallback when a publisher file is unavailable.

A CIF is a **paper-level asset**. A thumbnail previews the first coordinate block
of the first publisher CIF. Multiple refcodes can therefore show the same preview.
The file/block selector lets a reader inspect each structure; no automatic
refcode-to-block match is claimed. The audit counts associations to papers with
publisher CIFs, not independently matched structure blocks.

## Build and run

Python 3.12:

```sh
uv venv --python python3.12 .venv
uv pip install --python .venv/bin/python -e '.[web]'
.venv/bin/python scripts/runs/viz/build_publisher_assets.py \
  --sections /path/to/acta-e-papers.jsonl.gz \
  --extractions /path/to/extractions.parquet \
  --output src/viz/assets

TEXTAL_PUBLISHER_CACHE=/path/to/private/publisher-cache \
PYTHONPATH=src .venv/bin/python -m uvicorn viz.app:app --host 127.0.0.1 --port 8010
```

The source sections are the publisher XML extraction corpus, with refcode/DOI
associations. All linked Acta E refcodes are imported, including those without a
structured extraction yet. Generated data and cache files are ignored by Git.
`s0_assets.py` delegates to this publisher-only builder; the former CSD asset
export is no longer the default website pipeline.

For this local comparison, uncached publisher assets may be read from the saved
Trillium packages using the existing authorized SSH session:

```sh
export TEXTAL_ASSET_SSH=1
export TEXTAL_SSH_CONTROL="$HOME/.ssh/trillium-%C"
export TEXTAL_ARCHIVE_SSH=auhcheng@trillium.alliancecan.ca
export TEXTAL_ARCHIVE_NODE=tri-dm2
```

No SSH session is required for already cached files. A deployed installation
should provision its publisher cache or a publisher-only media backend; it
should not depend on this laptop's SSH connection. The exporter does not crawl
publishers or redownload articles. The old comparison site on port 8766 is separate.

## Final Luna import

The extraction remains independent on Trillium. This read-only completion check
exits 3 while it is still running and imports only when every refcode is terminal:

```sh
.venv/bin/python scripts/runs/viz/import_completed_acta_e.py \
  --sections /path/to/acta-e-papers.jsonl.gz --output src/viz/assets
```

It verifies the complete Parquet checksum and distinct refcode count. The new
snapshot is published last and the app reloads it on the next page request.
`completed-luna-import.json` records the provenance of the final import.
The local completion heartbeat checks this automatically every ten minutes.

## Validation

```sh
uv pip install --python .venv/bin/python httpx
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests/viz -v
```

The tests use synthetic publisher files and deliberately poisoned legacy CSD
assets. They cover pending entries, private-field exclusion, fail-closed schemas,
blocked cache paths, original download hashes, quoted atom labels, multiple CIF
blocks, whole molecules across cell boundaries and the original main thumbnail.
