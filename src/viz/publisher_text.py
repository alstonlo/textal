"""Serve only publisher Markdown selected by public DOI identity, never archive metadata."""

import gzip
import hashlib
import json
import os
from pathlib import Path

DIRECTORY = Path(os.environ.get("TEXTAL_PAPER_TEXTS", "data/publisher-texts")).resolve()


def read(doi):
    path = DIRECTORY / (hashlib.sha256(doi.encode()).hexdigest() + ".json.gz")
    if not path.is_file():
        return {"doi": doi, "main_text": "", "supplements": []}
    with gzip.open(path, "rt") as stream:
        data = json.load(stream)
    if data.get("doi") != doi or set(data) - {"doi", "main_text", "supplements"}:
        raise ValueError("Unexpected publisher text cache")
    if any(set(item) != {"name", "text"} for item in data.get("supplements", [])):
        raise ValueError("Unexpected publisher text fields")
    return data
