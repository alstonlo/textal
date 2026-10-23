"""The dataset folder: the website's tables and the publisher files, in the layout of the
Hugging Face dataset, so that a downloaded copy of the dataset is exactly what the website reads.
Any table with a column this module does not know is refused."""

import json
import os
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


def package_name(pmcid):
    """The path of a paper's publisher files in the dataset: a tar of its manifest and files."""
    return "files/" + pmcid[-2:] + "/" + pmcid + ".tar.gz"


def load_public_data():
    snapshot = json.loads((DATA / "snapshot.json").read_text())
    version = snapshot.get("schema")
    if version not in {"publisher-only-v1", "publisher-only-v2"}:
        raise ValueError("Rebuild publisher-only web assets; legacy CSD tables are unsupported.")
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
    entry_columns = ENTRY_COLUMNS if version.endswith("v2") else ENTRY_COLUMNS - {"paper_id"}
    paper_columns = (
        PAPER_COLUMNS if version.endswith("v2") else PAPER_COLUMNS - {"paper_id", "provenance_json"}
    )
    if set(entry_table.columns) != entry_columns or set(paper_table.columns) != paper_columns:
        raise ValueError("Unexpected public columns; refusing an unreviewed schema.")
    papers = {}
    for p in paper_table.to_dicts():
        p.setdefault("paper_id", "doi:" + p["doi"])
        for key in ("paragraphs", "sections", "licenses"):
            p[key] = json.loads(p.pop(key + "_json"))
        p["provenance"] = (
            json.loads(p.pop("provenance_json"))
            if "provenance_json" in p
            else {
                "collection": "Acta E",
                "bibliography_source": "Publisher XML",
                "text_source": "Publisher XML sections",
                "has_full_text": False,
                "has_publisher_package": True,
            }
        )
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
    entries = []
    for e in entry_table.to_dicts():
        e.setdefault("paper_id", "doi:" + e["doi"])
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
