"""Serve the paper texts of the dataset folder, only for the papers whose table row has one."""

import gzip
import json

from viz.publisher_data import DATA, text_name

PAPERS = {}


def configure(papers):
    global PAPERS
    PAPERS = {p["pmcid"]: p for p in papers.values() if p["provenance"].get("has_full_text")}


def read(paper):
    with gzip.open(DATA / text_name(paper["pmcid"]), "rt") as stream:
        data = json.load(stream)
    if data.get("doi") != paper["doi"] or set(data) != {"doi", "main_text", "supplements"}:
        raise ValueError("Unexpected publisher text")
    if any(set(item) != {"name", "text"} for item in data["supplements"]):
        raise ValueError("Unexpected publisher text fields")
    return data
