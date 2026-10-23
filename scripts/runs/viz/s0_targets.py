"""List the papers of the other journals, i.e. those of the extracted refcodes outside the Acta E
collection, each with its PMCID and the licence code of its PMC record."""

import argparse
import gzip
import json
from pathlib import Path

import polars as pl


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sections", type=Path, default=Path("data/viz/acta-e-papers.jsonl.gz"))
    p.add_argument("--extractions", type=Path, default=Path("data/extractions.parquet"))
    p.add_argument("--metadata", type=Path, default=Path("data/papers/metadata.parquet"))
    p.add_argument("--output", type=Path, default=Path("data/viz/publisher-targets.json"))
    a = p.parse_args()

    # As in `s2_assets.py`, a refcode of the Acta E collection is not one of the other journals.
    with gzip.open(a.sections, "rt") as stream:
        acta = [ref for line in stream for ref in json.loads(line).get("refcodes") or []]
    ext = pl.read_parquet(a.extractions, columns=["identifier", "doi"])
    dois = ext.filter(~pl.col("identifier").is_in(acta))["doi"].str.to_lowercase().unique()
    meta = pl.read_parquet(a.metadata, columns=["doi", "pmcid", "license"])
    meta = meta.with_columns(pl.col("doi").str.to_lowercase())
    meta = meta.filter(pl.col("doi").is_in(dois.implode()))
    a.output.write_text(json.dumps(meta.sort("doi").to_dicts(), indent=1))
    print(json.dumps({"dois": len(dois), "in_pmc": meta.height}))


if __name__ == "__main__":
    main()
