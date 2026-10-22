# Publisher-only TEXtal website

This branch starts from `main` at `6e681d5` and preserves its FastAPI/Jinja
layout, crystal thumbnails, element palette, unit-cell drawing, whole-molecule
packing and optional faint surrounding molecules. Geometry comes from the
publisher's original CIF, parsed with Gemmi. Original downloads are unchanged.

The entry view puts **What the paper says about this crystal** on the left and
the full paper on the right. Narrow screens stack those columns. Quoted evidence
can jump to matching article or supplementary paragraphs. The full Acta E
procedure snippets remain available in a disclosure below the extraction.

## Public data boundary

The website opens only `publisher_entries.parquet`, `publisher_papers.parquet`
and `publisher_snapshot.json`, using the checked `publisher-only-v2` schema.
It never opens legacy `entries.parquet`, CSD CIFs, `csd_metadata.full.parquet`,
SMILES, DrugBank attributes or raw CSD record fields. Refcodes and DOI linkage
are the identifier bridge. The front page explains this disclosure policy.

Article titles, journals, years and licences come from publisher XML, Europe PMC
or publisher Crossref deposits. Titles remain citation details. Crystal headings
use publisher-supported compound names/labels; Acta E chemical titles supply a
fallback. Broad multi-compound paper titles are not presented as molecule names.
When a name cannot be identified, a compound label or refcode remains visible.
The front-page examples span six journals and different kinds of compounds.

Extraction exports are allowlisted: status, generated summary, compound label,
six procedural topics, source quotations and extraction timestamps/model.
Matching rationale, raw model errors and private input metadata are excluded.
A topic requires source evidence; quotes are labelled as independently matched
to saved publisher text or merely recorded in the extraction. A summary passes a
conservative lexical overlap check against publisher text; this is **not semantic
validation**. Compound labels require presence in publisher text or their source
quote. Generated prose and refcode assignments still need human review.

Full Markdown comes from the user-supplied publisher-text archive, with missing
Acta E texts filled from already downloaded publisher XML. Only article and
supplementary text are copied into a private DOI-keyed cache. The public endpoint
requires an imported DOI and validates the cache fields. Markdown HTML is disabled,
front matter is hidden, and archive image paths are not served. No private cache
or source archive is mounted as a static directory.

Publisher media routes allow only receipt-listed, checksum-verified CIFs and
chemical schemes with an approved PMC OA source URL and matching DOI. Internal
package paths, receipts and arbitrary cache files are not exposed. A missing
publisher file never falls back to a CSD file or depiction.

A CIF is a **paper-level asset**. A thumbnail previews the first coordinate block
of the first publisher CIF. Multiple refcodes may therefore share a preview.
The file/block selector exposes all available structures; no automatic
refcode-to-block match is claimed. Audit counts represent links to papers with
publisher CIFs, not independently matched individual structure blocks.

## Build and run

Python 3.12:

```sh
uv venv --python python3.12 .venv
uv pip install --python .venv/bin/python -e '.[web]'
.venv/bin/python scripts/runs/viz/import_publisher_texts.py \
  --input /path/to/publisher-texts.jsonl.gz --output data/publisher-texts
.venv/bin/python scripts/runs/viz/build_publisher_assets.py \
  --sections /path/to/acta-e-papers.jsonl.gz \
  --extractions /path/to/extractions-with-acta-e-20261022.parquet \
  --bibliography /path/to/publisher-bibliography.json \
  --linkage /path/to/publisher-targets.json \
  --texts data/publisher-texts --output src/viz/assets

TEXTAL_PUBLISHER_CACHE=/path/to/private/publisher-cache \
TEXTAL_PAPER_TEXTS=data/publisher-texts \
PYTHONPATH=src .venv/bin/python -m uvicorn viz.app:app --host 127.0.0.1 --port 8010
```

The sections corpus supplies every linked Acta E refcode, including pending
extractions. Other journals come from the combined Parquet, with independently
retrieved publisher bibliography and DOI/PMCID identity linkage. The Oct22 import
contains 50,405 refcodes  / 33,109 papers: 28,759 Acta E refcodes and 21,646 from
other journals. Generated data, private text caches and media are Git-ignored.
The source scripts are committed; the datasets are provisioned separately.

`fetch_publisher_bibliography.py` queries Europe PMC and publisher Crossref deposits
for DOI targets. `export_publisher_texts.py` runs against the supplied archive and
its existing private index to select article/SI Markdown only. `s0_assets.py`
delegates to the publisher-only builder instead of the former CSD asset export.

For local comparison, uncached media can be read from saved Trillium packages:

```sh
export TEXTAL_ASSET_SSH=1
export TEXTAL_SSH_CONTROL="$HOME/.ssh/trillium-%C"
export TEXTAL_ARCHIVE_SSH=auhcheng@trillium.alliancecan.ca
export TEXTAL_ARCHIVE_NODE=tri-dm2
```

Cached files do not need SSH. A deployed installation should provision a
publisher-only cache/backend instead of relying on the laptop's SSH session.
This app does not crawl publishers or redownload main papers. The old comparison
viewer on port 8766 remains separate.

## Final Luna import

The authorized extraction runs independently on Trillium. The completion check
exits 3 while running and imports only when all 28,759 Acta E refcodes are terminal:

```sh
.venv/bin/python scripts/runs/viz/import_completed_acta_e.py \
  --sections /path/to/acta-e-papers.jsonl.gz --texts data/publisher-texts \
  --output src/viz/assets
```

It checks the completed Parquet checksum and distinct refcode count, updates
Acta E and **preserves the other-journal records**. The snapshot is published last;
the app reloads it on the next page request. `completed-luna-import.json` records
the final import. A local heartbeat performs the completion check every 10 minutes.

## Validation

```sh
uv pip install --python .venv/bin/python httpx
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests/viz -v
```

Synthetic tests include deliberately poisoned legacy CSD assets. They cover
private-field exclusion, fail-closed schemas, cache-route isolation, original
publisher hashes, quoted atom labels, multi-block CIFs, whole molecules across
cell boundaries, molecule-name fallbacks, non-Acta imports and preservation of
other journals when the final Acta E snapshot is imported.
