"""Build the per-paper prompt for the extraction agents.

One agent call per paper: the system prompt is fixed (so it can be cached across
calls), and the user message lists the paper's CSD entries. The paper's files go in
either as attached PDFs or as their text marked by page: `--input text` extracts it
with PyMuPDF, `--input mineru` reads MinerU's parse from data/mineru/ (run
`mineru-kit parse data/papers -o data/mineru -f zip` and unzip each bundle first). The model returns one record per entry; the pipeline adds the
provenance columns itself.

Usage:
    pixi run python -m dataset.extraction_prompt [--doi DOI] [--input pdf|text|mineru]
        [--out DIR]
"""

import argparse
import json
import re
from pathlib import Path

import polars as pl
import pymupdf

from dataset.extraction_schema import COLUMNS, EVIDENCED_FIELDS, describe

PROMPT_VERSION = "v2"

ROOT = Path(__file__).parents[2]
METADATA = ROOT / "data" / "csd_metadata.full.parquet"
DOIS = ROOT / "data" / "csd_dois.parquet"
PAPERS = ROOT / "data" / "papers"
MINERU = ROOT / "data" / "mineru"

# MinerU block types that are page furniture rather than paper content.
MINERU_SKIP = {"header", "footer", "page_number", "aside_text"}

# Columns the model fills; everything else in the schema is added by the pipeline.
MODEL_FIELDS = [
    "identifier",
    "compound_label",
    "match_confidence",
    "match_basis",
    "related_identifiers",
    "synthesis",
    "crystallisation",
    "characterisation",
    "solid_form",
    "purpose_and_properties",
    "summary",
    "other_notes",
    "evidence",
]

# CSD fields shown to the model to tell entries apart; ordered by usefulness.
ENTRY_FIELDS = [
    "identifier",
    "ccdc_number",
    "chemical_name",
    "synonyms",
    "formula",
    "temperature",
    "pressure",
    "polymorph",
    "color",
    "habit",
    "solvent",
    "melting_point",
    "phase_transition",
    "source",
]

# Supplementary-file suffix in a DOI, e.g. 10.1021/acs.jpcc.9b06912.s005.
SI_SUFFIX = re.compile(r"[._]s\d{3}$", re.IGNORECASE)


# Wording for the model where the schema's description is written for colleagues.
MODEL_DESCRIPTIONS = {
    "identifier": "The entry's CSD refcode, exactly as in the table.",
    "evidence": "The supporting quotes described above.",
}


def _field_list(names: list[str]) -> str:
    by_name = {c.name: c for c in COLUMNS}
    return "\n".join(f"- `{n}`: {MODEL_DESCRIPTIONS.get(n) or describe(by_name[n])}" for n in names)


SYSTEM_PROMPT = f"""\
You read scientific papers that report crystal structures and record what each \
paper says about each of its structures in the Cambridge Structural Database (CSD).

You get one paper's files (the main paper and any supplementary files), either \
attached as PDFs or as their extracted text, and a table of the CSD entries linked \
to it. Return one record \
for every entry in the table, in the same order. The CSD already holds the crystal \
structure itself and the fields shown in the table; your job is to capture what the \
paper adds about each entry.

Matching entries to the paper
- Papers name compounds by label ("3a", "complex 2") or by name. Use the chemical \
names, formulas and the other CSD fields to work out which compound in the paper \
each entry is. Several entries can be the same compound: polymorphs, solvates, \
salts, or the same crystal measured at different temperatures or pressures. Use the \
temperature, polymorph and colour fields to tell them apart, and keep their details \
separate.
- If the paper gives a shared procedure for several compounds ("compounds 1-4 were \
prepared by..."), copy it into each compound's paragraphs and add that compound's \
own details.
- If you cannot find an entry's compound in the paper, still return its record \
with `match_confidence` `low`, explain in `match_basis`, and leave the paragraphs \
empty.

Writing the paragraphs
- Write in English, staying close to the paper: keep numbers, units, conditions, \
reagent and solvent names as the paper gives them. Do not summarise away details.
- Only write what the paper says. Do not add background knowledge, and do not guess.
- The topics are deliberately broad. Put each piece of information in the first \
paragraph that fits, and do not repeat it in another. Anything useful that fits no \
paragraph goes in `other_notes`.
- If the paper says nothing on a topic for an entry, return null for that field. \
Never write placeholders such as "not reported" or "N/A".
- Older papers are often scans. Read them as carefully as typeset text, and ignore \
page furniture such as running headers, journal adverts and reference lists. \
Extracted text can have broken line wraps, odd spacing or scrambled tables; read \
through those, but never correct the paper's numbers or wording.
- Skip what the CSD already holds from the crystal structure: unit cell, space \
group, refinement details, atom coordinates, bond lengths and angles, ring \
conformations, dihedral angles, hydrogen bonding and packing. Record them only when \
the paper uses them to explain something else, such as a property or a difference \
between forms, and then only that point.

Evidence
- For every non-null field, give at least one quote that supports it: `field` is \
the field name, `source_file` is the file's label as listed in the message, \
`page` is the 1-based page number within that file (not the journal's printed \
page number; in extracted text, the number in the `[page N]` marker above the \
quote), and `quote` is a short span (one sentence or less) copied character for \
character from the paper, in the original language. Never paraphrase a quote, \
join separate fragments into one, or change its numbers, signs or words. A quote \
must contain the fact it supports.

Fields to return for each entry
{_field_list(MODEL_FIELDS)}
"""


def output_schema() -> dict:
    """JSON schema for structured output: one record per CSD entry."""
    text = {"type": ["string", "null"]}
    record = {
        "type": "object",
        "additionalProperties": False,
        "required": MODEL_FIELDS,
        "properties": {
            "identifier": {"type": "string"},
            "compound_label": text,
            "match_confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "match_basis": {"type": "string"},
            "related_identifiers": {"type": "array", "items": {"type": "string"}},
            **{
                n: text
                for n in MODEL_FIELDS
                if n
                in {
                    "synthesis",
                    "crystallisation",
                    "characterisation",
                    "solid_form",
                    "purpose_and_properties",
                    "summary",
                    "other_notes",
                }
            },
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["field", "source_file", "page", "quote"],
                    "properties": {
                        "field": {
                            "type": "string",
                            "enum": EVIDENCED_FIELDS,
                        },
                        "source_file": {"type": "string"},
                        "page": {"type": ["integer", "null"]},
                        "quote": {"type": "string"},
                    },
                },
            },
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["entries"],
        "properties": {"entries": {"type": "array", "items": record}},
    }


def normalize_doi(doi: str) -> str:
    doi = doi.strip().lower()
    return re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", doi)


def doi_key(doi: str) -> str:
    """Filename-safe DOI as used in the downloaded file names ('/' and '.' -> '_')."""
    return re.sub(r"[/.]", "_", normalize_doi(doi))


def paper_files() -> dict[str, list[Path]]:
    """Group downloaded PDFs by the DOI key of their main paper."""
    groups: dict[str, list[Path]] = {}
    for pdf in sorted(PAPERS.glob("*.pdf")):
        m = re.search(r"-- doi (\S+) --", pdf.name)
        if not m:
            continue
        key = SI_SUFFIX.sub("", m.group(1).lower())
        groups.setdefault(key, []).append(pdf)
    return groups


def entries_for(doi: str) -> pl.DataFrame:
    """CSD entries linked to a paper, with the fields the model sees."""
    ids = (
        pl.scan_parquet(DOIS)
        .filter(
            (pl.col("kind") == "publication")
            & (pl.col("doi").str.to_lowercase() == normalize_doi(doi))
        )
        .select("identifier")
        .unique()
        .collect()["identifier"]
    )
    return (
        pl.scan_parquet(METADATA)
        .select(ENTRY_FIELDS)
        .filter(pl.col("identifier").is_in(ids.implode()))
        .sort("identifier")
        .collect()
    )


def _entry_table(entries: pl.DataFrame) -> str:
    """Markdown table of the entries, dropping columns that are empty for all of them."""

    def cell(v) -> str:
        if v is None or v == "" or v == []:
            return ""
        if isinstance(v, list):
            v = "; ".join(map(str, v))
        return str(v).replace("|", "/").replace("\n", " ")

    rows = [{k: cell(v) for k, v in r.items()} for r in entries.iter_rows(named=True)]
    cols = [c for c in entries.columns if any(r[c] for r in rows)]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(r[c] for c in cols) + " |" for r in rows]
    return "\n".join(lines)


def file_kind(pdf: Path) -> str:
    m = re.search(r"-- doi (\S+) --", pdf.name)
    return "supplementary" if m and SI_SUFFIX.search(m.group(1)) else "main"


def file_labels(pdfs: list[Path]) -> list[str]:
    """Short names for the attachments: main.pdf, supplementary_1.pdf, ..."""
    labels, n_si = [], 0
    for pdf in pdfs:
        if file_kind(pdf) == "main":
            labels.append("main.pdf")
        else:
            n_si += 1
            labels.append(f"supplementary_{n_si}.pdf")
    return labels


def pdf_text(pdf: Path) -> str:
    """The PDF's text layer, each page under a `[page N]` marker."""
    with pymupdf.open(pdf) as doc:
        pages = [re.sub(r"[ \t]+", " ", page.get_text()).strip() for page in doc]
    return "\n\n".join(f"[page {i}]\n{text}" for i, text in enumerate(pages, 1))


def mineru_text(pdf: Path) -> str:
    """MinerU's parse of the PDF, each page under a `[page N]` marker.

    Drops headers, footers and page numbers; keeps figure captions.
    """
    content = json.loads((MINERU / pdf.stem / "structured_content.json").read_text())
    pages = []
    for page in content["pages"]:
        parts = []
        for block in page["blocks"]:
            if block["type"] in MINERU_SKIP:
                continue
            parts += [c["content"] for c in block.get("captions", [])]
            parts.append(block.get("content") or "")
            parts += [f["content"] for f in block.get("footnotes", [])]
        pages.append("\n\n".join(p for p in parts if p))
    return "\n\n".join(f"[page {i}]\n{text}" for i, text in enumerate(pages, 1))


def user_message(doi: str, entries: pl.DataFrame, pdfs: list[Path], input: str = "pdf") -> str:
    labels = file_labels(pdfs)
    files = "\n".join(f"- {label} ({file_kind(pdf)} paper)" for label, pdf in zip(labels, pdfs))
    extract = mineru_text if input == "mineru" else pdf_text
    texts = [f'<file name="{label}">\n{extract(pdf)}\n</file>' for label, pdf in zip(labels, pdfs)]
    heading = "Attached files" if input == "pdf" else "Files (extracted text follows the table)"
    return "\n".join(
        [
            f"Paper DOI: {normalize_doi(doi)}",
            "",
            f"{heading}:\n{files}",
            "",
            (
                f"CSD entries linked to this paper ({len(entries)}). "
                "Return one record for each, in this order:"
            ),
            "",
            _entry_table(entries),
            *(["", *texts] if input != "pdf" else []),
        ]
    )


def build(doi: str, pdfs: list[Path], input: str = "pdf") -> dict:
    """Everything one agent call needs, plus the provenance the pipeline will record.

    `input` is `pdf` to attach the files, or `text` or `mineru` to put their text,
    from PyMuPDF or MinerU, in the user message.
    """
    entries = entries_for(doi)
    return {
        "doi": normalize_doi(doi),
        "prompt_version": PROMPT_VERSION,
        "identifiers": entries["identifier"].to_list(),
        # The model cites files by label; map labels back to files with this list.
        # Only `pdf` attachments are sent as files, before the user message.
        "attachments": [
            {"label": label, "path": str(pdf), "input": input}
            for label, pdf in zip(file_labels(pdfs), pdfs)
        ],
        "source_files": [{"name": p.name, "kind": file_kind(p), "input": input} for p in pdfs],
        "system": SYSTEM_PROMPT,
        "user": user_message(doi, entries, pdfs, input),
        "output_schema": output_schema(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--doi", help="Build only this paper (default: every paper in data/papers/)"
    )
    parser.add_argument(
        "--input",
        choices=["pdf", "text", "mineru"],
        default="pdf",
        help="Attach the PDFs, or send their text from PyMuPDF or MinerU",
    )
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "prompts")
    args = parser.parse_args()

    # The CSD lists DOIs with original case; map file keys back to them.
    dois = pl.read_parquet(DOIS, columns=["doi"])["doi"].unique().to_list()
    by_key = {doi_key(d): d for d in dois}

    args.out.mkdir(parents=True, exist_ok=True)
    for key, pdfs in paper_files().items():
        doi = by_key.get(key)
        if doi is None or (args.doi and normalize_doi(args.doi) != normalize_doi(doi)):
            if doi is None:
                print(f"skip {key}: no CSD entry links to this DOI")
            continue
        job = build(doi, pdfs, args.input)
        path = args.out / f"{key}.json"
        path.write_text(json.dumps(job, indent=1, ensure_ascii=False))
        print(f"{key}: {len(job['identifiers'])} entries, {len(pdfs)} PDF(s) -> {path}")


if __name__ == "__main__":
    main()
