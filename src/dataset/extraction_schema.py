"""Schema for LLM-extracted paper information, one row per CSD entry and run.

Run `uv run python -m dataset.extraction_schema` to regenerate
docs/EXTRACTION_SCHEMA.md, docs/EXTRACTION_SCHEMA.slack.txt and an empty
docs/extraction_template.parquet.
The conventions shared with colleagues are in NOTES below.
"""

from dataclasses import dataclass
from pathlib import Path

import polars as pl

KEY = ["identifier", "doi", "prompt_version"]

NOTES = [
    "One row per CSD entry, paper and prompt version: the key is `identifier` + `doi` + `prompt_version`.",
    "Paper content is free text, one paragraph per topic, written in English and staying close to the paper: numbers, conditions and names are kept. Structured fields are derived from the paragraphs later.",
    "The topics are deliberately broad, because we don't know in advance what the papers contain. Something that fits several paragraphs goes in the first one that fits; anything that fits none goes in `other_notes`.",
    'An empty value means none of the files in `source_files` covers the topic. Supplementary files may be missing, so check `source_files` before reading empty as "the paper doesn\'t say".',
    "`extraction_status` says whether extraction ran and finished.",
    "Each filled column has at least one supporting quote in `evidence`, in the paper's original language.",
]

MATCH_CONFIDENCE = ["high", "medium", "low"]
FILE_KINDS = ["main", "supplementary"]
FILE_INPUTS = ["text", "pdf"]
EXTRACTION_STATUSES = ["ok", "no_paper", "compound_not_found", "truncated", "refused", "failed"]

# Columns read from the paper; evidence quotes must name one of these.
EVIDENCED_FIELDS = [
    "compound_label",
    "synthesis",
    "crystallisation",
    "characterisation",
    "solid_form",
    "purpose_and_properties",
    "summary",
    "other_notes",
]
EVIDENCE = pl.Struct(
    {
        "field": pl.Enum(EVIDENCED_FIELDS),
        "source_file": pl.String,
        "page": pl.Int32,
        "quote": pl.String,
    }
)
SOURCE_FILE = pl.Struct(
    {
        "name": pl.String,
        "kind": pl.Enum(FILE_KINDS),
        "input": pl.Enum(FILE_INPUTS),
    }
)


@dataclass(frozen=True)
class Column:
    name: str
    dtype: pl.DataType
    group: str
    description: str
    values: list[str] | None = None


def enum(values: list[str]) -> pl.Enum:
    return pl.Enum(values)


COLUMNS = [
    # Linking
    Column("identifier", pl.String, "Linking", "CSD refcode; joins to csd_metadata."),
    Column(
        "doi",
        pl.String,
        "Linking",
        "DOI of the paper, lowercase, without the https://doi.org/ prefix.",
    ),
    Column(
        "compound_label",
        pl.String,
        "Linking",
        'The paper\'s own name or label for this compound, e.g. "3a" or "complex 2".',
    ),
    Column(
        "match_confidence",
        enum(MATCH_CONFIDENCE),
        "Linking",
        "How sure the match between this refcode and the compound in the paper is: `high` if unambiguous, `medium` if inferred, `low` if a best guess.",
        MATCH_CONFIDENCE,
    ),
    Column(
        "match_basis",
        pl.String,
        "Linking",
        "Short explanation of how the refcode was matched to the compound in the paper.",
    ),
    Column(
        "related_identifiers",
        pl.List(pl.String),
        "Linking",
        "Other refcodes from the same paper that the paper relates to this entry, e.g. the same compound under other conditions or in another form.",
    ),
    # Paper content
    Column(
        "synthesis",
        pl.String,
        "Paper content",
        'How the compound was made or obtained, including any procedure cited from elsewhere (e.g. "prepared as in ref. 12").',
    ),
    Column(
        "crystallisation",
        pl.String,
        "Paper content",
        "How the crystals that were measured were obtained, with any conditions given.",
    ),
    Column(
        "characterisation",
        pl.String,
        "Paper content",
        "Measurements and analyses of this compound other than the crystal structure itself, with their main results.",
    ),
    Column(
        "solid_form",
        pl.String,
        "Paper content",
        "What the paper says about this solid form and how it relates to other forms of the compound.",
    ),
    Column(
        "purpose_and_properties",
        pl.String,
        "Paper content",
        "Why the work was done, and any properties, behaviour, activity or uses reported for this compound.",
    ),
    Column(
        "summary",
        pl.String,
        "Paper content",
        "Two or three sentences on what is specific to this entry within the paper; empty if nothing distinguishes it from the paper's other entries.",
    ),
    Column(
        "other_notes",
        pl.String,
        "Paper content",
        "Anything else useful about this entry that does not fit the paragraphs above.",
    ),
    # Provenance
    Column(
        "evidence",
        pl.List(EVIDENCE),
        "Provenance",
        "Supporting quotes, at least one per filled column: `field` (the column supported), `source_file` (a name from `source_files`), `page` (1-based page of that file, empty if unknown) and `quote` (verbatim).",
    ),
    Column(
        "source_files",
        pl.List(SOURCE_FILE),
        "Provenance",
        "Files the model saw for this row: `name` (file name as downloaded), `kind` (`main` or `supplementary`) and `input` (sent as extracted `text` or as the `pdf`).",
    ),
    Column("model", pl.String, "Provenance", "Model ID used for extraction."),
    Column(
        "prompt_version",
        pl.String,
        "Provenance",
        "Version of the extraction prompt; part of the key.",
    ),
    Column("extracted_at", pl.Datetime("us", "UTC"), "Provenance", "When the extraction ran."),
    Column(
        "extraction_status",
        enum(EXTRACTION_STATUSES),
        "Provenance",
        "Outcome for this row. `truncated` means the output was cut off, so content may be missing; `refused` means the model declined.",
        EXTRACTION_STATUSES,
    ),
    Column("error", pl.String, "Provenance", "Error message when the status is not `ok`."),
]

SCHEMA = pl.Schema({c.name: c.dtype for c in COLUMNS})


def type_label(dtype: pl.DataType) -> str:
    if isinstance(dtype, pl.List):
        return "list of records" if isinstance(dtype.inner, pl.Struct) else "list of text"
    if isinstance(dtype, pl.Enum):
        return "fixed choice"
    return "timestamp" if isinstance(dtype, pl.Datetime) else "text"


def describe(c: Column) -> str:
    if not c.values:
        return c.description
    return c.description + " One of: " + ", ".join(f"`{v}`" for v in c.values) + "."


def to_markdown() -> str:
    lines = [
        "# Paper extraction schema",
        "",
        "Generated from `src/dataset/extraction_schema.py`; edit that file, not this one.",
        "",
        *(f"- {n}" for n in NOTES),
    ]
    group = None
    for c in COLUMNS:
        if c.group != group:
            group = c.group
            lines += ["", f"## {group}", "", "| Column | Type | Description |", "|---|---|---|"]
        lines.append(f"| `{c.name}` | {type_label(c.dtype)} | {describe(c)} |")
    return "\n".join(lines) + "\n"


def to_slack() -> str:
    """Slack mrkdwn: Slack renders neither MDX nor Markdown tables."""
    lines = ["*Paper extraction schema*", *(f"• {n}" for n in NOTES)]
    group = None
    for c in COLUMNS:
        if c.group != group:
            group = c.group
            lines += ["", f"*{group}*"]
        lines.append(f"• `{c.name}` ({type_label(c.dtype)}): {describe(c)}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    docs = Path(__file__).parents[2] / "docs"
    (docs / "EXTRACTION_SCHEMA.md").write_text(to_markdown())
    (docs / "EXTRACTION_SCHEMA.slack.txt").write_text(to_slack())
    pl.DataFrame(schema=SCHEMA).write_parquet(docs / "extraction_template.parquet")
    print(f"{len(COLUMNS)} columns written")
