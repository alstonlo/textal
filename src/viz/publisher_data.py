"""The dataset folder: the website's tables and the publisher files, in the layout of the
Hugging Face dataset, so that a downloaded copy of the dataset is exactly what the website reads.
Any table with a column this module does not know is refused."""

import json
import os
import re
from collections import Counter
from pathlib import Path

import polars as pl

from viz.names import crystal_name

DATA = Path(os.environ.get("TEXTAL_DATA", "data/textal")).resolve()

ENTRY_COLUMNS = {"id", "doi", "pmcid", "paper_id", "extraction_json"}
PAPER_COLUMNS = {
    "paper_id",
    "pmcid",
    "doi",
    "title",
    "journal",
    "year",
    "authors_json",
    "paragraphs_json",
    "sections_json",
    "licenses_json",
    "provenance_json",
}
FIELDS = {
    "synthesis",
    "crystallisation",
    "characterisation",
    "solid_form",
    "purpose_and_properties",
    "other_notes",
}


# The licence of a paper, from the first of these tokens found in its licence evidence: a
# Creative Commons URL (Acta E, where the URL is sometimes only quoted in the evidence text) or
# the licence code of its PMC record (the other journals), where "TDM" marks an author
# manuscript. The order matters, as "cc by" is a prefix of the other codes.
LICENCES = [
    (("publicdomain/zero", "cc0"), "CC0"),
    (("licenses/by-nc-nd/", "cc by-nc-nd"), "CC BY-NC-ND"),
    (("licenses/by-nc-sa/", "cc by-nc-sa"), "CC BY-NC-SA"),
    (("licenses/by-nc/", "cc by-nc"), "CC BY-NC"),
    (("licenses/by-sa/", "cc by-sa"), "CC BY-SA"),
    (("licenses/by/", "cc by"), "CC BY"),
    (("tdm",), "Author manuscript"),
]
PUBLISHER_TERMS, NOT_INDEXED = "Publisher terms", "Not indexed"


def licence(licenses):
    """The name of a paper's licence; only the Creative Commons ones start with "CC"."""
    text = " ".join(f"{e.get('url')} {e.get('type')} {e.get('text')}" for e in licenses).lower()
    names = [name for tokens, name in LICENCES if any(t in text for t in tokens)]
    if names:
        return names[0]
    return PUBLISHER_TERMS if licenses else NOT_INDEXED


def package_name(pmcid):
    """The path of a paper's publisher files in the dataset: a tar of its manifest and files."""
    return "files/" + pmcid[-2:] + "/" + pmcid + ".tar.gz"


def text_name(pmcid):
    """The path of a paper's Markdown in the dataset: its text and supplementary documents."""
    return "texts/" + pmcid[-2:] + "/" + pmcid + ".json.gz"


def format_journal(name: str) -> str:
    """Format compact journal abbreviations with spaces (e.g. Chem.Mater. -> Chem. Mater.)."""
    if not name:
        return ""
    # Add space after comma, colon, semicolon if not followed by whitespace
    s = re.sub(r"([,:;])(?=[^\s])", r"\1 ", name)
    # Add space after dot if followed by a letter (e.g. Chem.Mater. -> Chem. Mater.)
    s = re.sub(r"\.-(?=[A-Za-z])", ". ", s)
    s = re.sub(r"\.(?=[A-Za-z(])", r". ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_public_data():
    snapshot = json.loads((DATA / "snapshot.json").read_text())
    if snapshot.get("schema") not in {"publisher-only-v2", "publisher-only-v3"}:
        raise ValueError(
            f"{DATA} holds an older version of the dataset. Download the current one with"
            " `pixi run hf download alstonlo/textal-data --repo-type dataset --local-dir"
            " data/textal`, or rebuild it with `s2_assets.py`."
        )
    if set(snapshot) - {
        "schema",
        "built_at",
        "refcodes",
        "papers",
        "extraction_statuses",
        "with_snippets",
        "source",
        "extraction_policy",
        "collections",
        "journals",
    }:
        raise ValueError("Unexpected public snapshot fields")
    entry_table = pl.read_parquet(DATA / "entries.parquet")
    paper_table = pl.read_parquet(DATA / "papers.parquet")
    # The released v2 tables predate the publisher author list.
    if snapshot["schema"] == "publisher-only-v2" and set(paper_table.columns) == PAPER_COLUMNS - {"authors_json"}:
        paper_table = paper_table.with_columns(pl.lit("[]").alias("authors_json"))
    if set(entry_table.columns) != ENTRY_COLUMNS or set(paper_table.columns) != PAPER_COLUMNS:
        raise ValueError("Unexpected public columns; refusing an unreviewed schema.")
    papers = {}
    for p in paper_table.to_dicts():
        p["journal"] = format_journal(p.get("journal") or "")
        for key in ("authors", "paragraphs", "sections", "licenses", "provenance"):
            p[key] = json.loads(p.pop(key + "_json"))
        if set(p["provenance"]) - {
            "collection",
            "bibliography_source",
            "bibliography_url",
            "text_source",
            "has_full_text",
            "has_publisher_package",
        }:
            raise ValueError("Unexpected publisher provenance")
        for field, allowed in {
            "paragraphs": {"text", "paragraph_index"},
            "sections": {"title", "label", "paragraph_indices"},
            "licenses": {"url", "type", "text"},
        }.items():
            if any(set(row) - allowed for row in p[field]):
                raise ValueError("Unexpected nested publisher fields")
        for lic in p["licenses"]:
            if lic.get("url") and not lic["url"].startswith(("http://", "https://")):
                lic["url"] = None
        papers[p["paper_id"]] = p
    # Build filter options from the same normalized names used by entries.
    snapshot["journals"] = dict(sorted(Counter(p["journal"] for p in papers.values()).items()))
    entries = []
    for e in entry_table.to_dicts():
        x = json.loads(e.pop("extraction_json"))
        if set(x) - {
            "status",
            "fields",
            "evidence",
            "extracted_at",
            "model",
            "prompt_version",
            "summary",
            "compound_label",
            "evidence_policy",
        }:
            raise ValueError("Unexpected extraction fields")
        if set(x["fields"]) - FIELDS:
            raise ValueError("Unexpected extraction topic")
        if any(set(ev) - {"field", "quote", "source_file", "verified"} for ev in x["evidence"]):
            raise ValueError("Unexpected evidence fields")
        for ev in x["evidence"]:
            if "source_file" in ev:
                ev["source_file"] = (
                    "Supplementary information"
                    if "supp" in ev["source_file"].lower()
                    else "Publisher text"
                )
        x.setdefault("summary", None)
        x.setdefault("compound_label", None)
        e["extraction"] = x
        p = papers[e["paper_id"]]
        if e["doi"] != p["doi"]:
            raise ValueError("Paper / refcode DOI mismatch")
        e["paper"] = p
        e["name"], e["name_source"] = crystal_name(e)
        entries.append(e)
    if snapshot["refcodes"] != len(entries) or snapshot["papers"] != len(papers):
        raise ValueError("Incomplete publisher snapshot")
    return entries, papers, snapshot
