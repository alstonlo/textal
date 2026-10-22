"""Strict public dataset loader. Legacy entries.parquet is never opened."""

import json
from pathlib import Path

import polars as pl

ENTRY_COLUMNS = {"id", "doi", "pmcid", "extraction_json"}
PAPER_COLUMNS = {
    "pmcid",
    "doi",
    "title",
    "journal",
    "year",
    "paragraphs_json",
    "sections_json",
    "licenses_json",
}


def load_public_data(folder: Path):
    snapshot = json.loads((folder / "publisher_snapshot.json").read_text())
    if snapshot.get("schema") != "publisher-only-v1":
        raise ValueError("Rebuild publisher-only web assets; legacy CSD tables are not supported.")
    if set(snapshot) - {
        "schema",
        "built_at",
        "refcodes",
        "papers",
        "extraction_statuses",
        "with_snippets",
        "source",
        "extraction_policy",
    }:
        raise ValueError("Unexpected public snapshot fields")
    entry_table = pl.read_parquet(folder / "publisher_entries.parquet")
    paper_table = pl.read_parquet(folder / "publisher_papers.parquet")
    if set(entry_table.columns) != ENTRY_COLUMNS or set(paper_table.columns) != PAPER_COLUMNS:
        raise ValueError("Unexpected public columns. Refusing to expose an unreviewed data schema.")
    papers = {}
    for p in paper_table.to_dicts():
        for key in ("paragraphs", "sections", "licenses"):
            p[key] = json.loads(p.pop(key + "_json"))
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
        papers[p["pmcid"]] = p
    entries = []
    for e in entry_table.to_dicts():
        x = json.loads(e.pop("extraction_json"))
        if set(x) - {"status", "fields", "evidence", "extracted_at", "model", "prompt_version"}:
            raise ValueError("Unexpected extraction fields")
        if set(x["fields"]) - {
            "synthesis",
            "crystallisation",
            "characterisation",
            "solid_form",
            "purpose_and_properties",
            "other_notes",
        }:
            raise ValueError("Unexpected extraction topic")
        if any(set(v) != {"field", "quote"} for v in x["evidence"]):
            raise ValueError("Unexpected evidence fields")
        e["extraction"] = x
        p = papers[e["pmcid"]]
        if e["doi"] != p["doi"]:
            raise ValueError("Paper / refcode DOI mismatch")
        e["paper"] = p
        entries.append(e)
    if snapshot["refcodes"] != len(entries) or snapshot["papers"] != len(papers):
        raise ValueError("Incomplete publisher snapshot")
    return entries, papers, snapshot
