# Paper extraction schema

Generated from `src/dataset/extraction_schema.py`; edit that file, not this one.

- One row per CSD entry, paper and prompt version: the key is `identifier` + `doi` + `prompt_version`.
- Paper content is free text, one paragraph per topic, written in English and staying close to the paper: numbers, conditions and names are kept. Structured fields are derived from the paragraphs later.
- The topics are deliberately broad, because we don't know in advance what the papers contain. Something that fits several paragraphs goes in the first one that fits; anything that fits none goes in `other_notes`.
- An empty value means none of the files in `source_files` covers the topic. Supplementary files may be missing, so check `source_files` before reading empty as "the paper doesn't say".
- `extraction_status` says whether extraction ran and finished.
- Each filled column has at least one supporting quote in `evidence`, in the paper's original language.

## Linking

| Column | Type | Description |
|---|---|---|
| `identifier` | text | CSD refcode; joins to csd_metadata. |
| `doi` | text | DOI of the paper, lowercase, without the https://doi.org/ prefix. |
| `compound_label` | text | The paper's own name or label for this compound, e.g. "3a" or "complex 2". |
| `match_confidence` | fixed choice | How sure the match between this refcode and the compound in the paper is: `high` if unambiguous, `medium` if inferred, `low` if a best guess. One of: `high`, `medium`, `low`. |
| `match_basis` | text | Short explanation of how the refcode was matched to the compound in the paper. |
| `related_identifiers` | list of text | Other refcodes from the same paper that the paper relates to this entry, e.g. the same compound under other conditions or in another form. |

## Paper content

| Column | Type | Description |
|---|---|---|
| `synthesis` | text | How the compound was made or obtained, including any procedure cited from elsewhere (e.g. "prepared as in ref. 12"). |
| `crystallisation` | text | How the crystals that were measured were obtained, with any conditions given. |
| `characterisation` | text | Measurements and analyses of this compound other than the crystal structure itself, with their main results. |
| `solid_form` | text | What the paper says about this solid form and how it relates to other forms of the compound. |
| `purpose_and_properties` | text | Why the work was done, and any properties, behaviour, activity or uses reported for this compound. |
| `summary` | text | Two or three sentences on what is specific to this entry within the paper; empty if nothing distinguishes it from the paper's other entries. |
| `other_notes` | text | Anything else useful about this entry that does not fit the paragraphs above. |

## Provenance

| Column | Type | Description |
|---|---|---|
| `evidence` | list of records | Supporting quotes, at least one per filled column: `field` (the column supported), `source_file` (a name from `source_files`), `page` (1-based page of that file, empty if unknown) and `quote` (verbatim). |
| `source_files` | list of records | Files the model saw for this row: `name` (file name as downloaded), `kind` (`main` or `supplementary`) and `input` (sent as extracted `text` or as the `pdf`). |
| `model` | text | Model ID used for extraction. |
| `prompt_version` | text | Version of the extraction prompt; part of the key. |
| `extracted_at` | timestamp | When the extraction ran. |
| `extraction_status` | fixed choice | Outcome for this row. `truncated` means the output was cut off, so content may be missing; `refused` means the model declined. One of: `ok`, `no_paper`, `compound_not_found`, `truncated`, `refused`, `failed`. |
| `error` | text | Error message when the status is not `ok`. |
