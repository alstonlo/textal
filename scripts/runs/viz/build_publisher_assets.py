"""Build the public website from publisher snippets, never from CSD metadata or CIFs.

The only CSD-linked values exported are refcode/DOI associations. Generated extraction
fields require supporting quotes found in the publisher snippet. Private matching
context, compound labels, raw errors and internal paths are deliberately omitted.
"""

import argparse
import gzip
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

FIELDS = (
    "synthesis",
    "crystallisation",
    "characterisation",
    "solid_form",
    "purpose_and_properties",
    "other_notes",
)
ENTRY_COLUMNS = {
    "id": pl.String,
    "doi": pl.String,
    "pmcid": pl.String,
    "extraction_json": pl.String,
}
PAPER_COLUMNS = {
    "pmcid": pl.String,
    "doi": pl.String,
    "title": pl.String,
    "journal": pl.String,
    "year": pl.Int64,
    "paragraphs_json": pl.String,
    "sections_json": pl.String,
    "licenses_json": pl.String,
}


def normalized(value):
    return "".join(c for c in str(value).casefold() if c.isalnum())


def public_extraction(row, paper):
    if not row:
        return {"status": "pending", "fields": {}, "evidence": []}
    corpus = normalized(" ".join(p["text"] for p in paper["paragraphs"]))
    evidence = []
    for ev in row.get("evidence") or []:
        quote = ev.get("quote") or ""
        if (
            ev.get("field") in FIELDS
            and len(normalized(quote)) >= 20
            and normalized(quote) in corpus
        ):
            evidence.append({"field": ev["field"], "quote": quote})
    supported = {ev["field"] for ev in evidence}
    return {
        "status": row.get("extraction_status") or "unknown",
        "fields": {key: row[key] for key in FIELDS if key in supported and row.get(key)},
        "evidence": evidence,
        "extracted_at": str(row.get("extracted_at") or ""),
        "model": row.get("model"),
        "prompt_version": row.get("prompt_version"),
    }


def build(sections, extractions, output):
    output.mkdir(parents=True, exist_ok=True)
    ext = {r["identifier"]: r for r in pl.read_parquet(extractions).to_dicts()}
    papers, entries = {}, {}
    with gzip.open(sections, "rt") as stream:
        for line in stream:
            raw = json.loads(line)
            refs = raw.get("refcodes") or []
            if not refs:
                continue
            pmcid = raw["pmcid"]
            if not re.fullmatch(r"PMC[0-9]+", pmcid):
                raise ValueError("Invalid PMC identifier")
            doi = raw["doi"].lower()
            paragraphs = [
                {"text": p["text"], "paragraph_index": p["paragraph_index"]}
                for p in raw.get("paragraphs", [])
            ]
            paper = {
                "pmcid": pmcid,
                "doi": doi,
                "title": raw.get("article_title") or doi,
                "journal": raw.get("journal") or "Acta Crystallographica E",
                "year": raw.get("year"),
                "paragraphs": paragraphs,
            }
            papers[pmcid] = {
                key: paper[key] for key in ("pmcid", "doi", "title", "journal", "year")
            }
            papers[pmcid].update(
                {
                    "paragraphs_json": json.dumps(paragraphs, ensure_ascii=False),
                    "sections_json": json.dumps(
                        [
                            {key: s.get(key) for key in ("title", "label", "paragraph_indices")}
                            for s in raw.get("matched_sections", [])
                        ],
                        ensure_ascii=False,
                    ),
                    "licenses_json": json.dumps(
                        [
                            {key: v.get(key) for key in ("url", "type", "text")}
                            for v in raw.get("article_license_evidence", [])
                        ],
                        ensure_ascii=False,
                    ),
                }
            )
            for ref in refs:
                if not re.fullmatch(r"[A-Z]{6}[0-9]{0,2}", ref):
                    raise ValueError("Invalid refcode")
                row = ext.get(ref)
                if row and (row.get("doi") or "").lower() != doi:
                    row = None
                entry = {
                    "id": ref,
                    "doi": doi,
                    "pmcid": pmcid,
                    "extraction_json": json.dumps(
                        public_extraction(row, paper), ensure_ascii=False
                    ),
                }
                if ref in entries and entries[ref]["doi"] != doi:
                    raise ValueError("Conflicting refcode DOI association: " + ref)
                entries[ref] = entry
    pl.DataFrame(
        sorted(entries.values(), key=lambda e: e["id"]), schema=ENTRY_COLUMNS
    ).write_parquet(output / "publisher_entries.parquet.part")
    (output / "publisher_entries.parquet.part").replace(output / "publisher_entries.parquet")
    pl.DataFrame(list(papers.values()), schema=PAPER_COLUMNS).write_parquet(
        output / "publisher_papers.parquet.part"
    )
    (output / "publisher_papers.parquet.part").replace(output / "publisher_papers.parquet")
    statuses = Counter(json.loads(e["extraction_json"])["status"] for e in entries.values())
    manifest = {
        "schema": "publisher-only-v1",
        "built_at": datetime.now(UTC).isoformat(),
        "refcodes": len(entries),
        "papers": len(papers),
        "extraction_statuses": dict(statuses),
        "with_snippets": sum(bool(json.loads(p["paragraphs_json"])) for p in papers.values()),
        "source": "Publisher XML from saved PMC OA packages; identifier linkage only from CSD.",
        "extraction_policy": "Only procedural fields with a supporting quote verified in publisher snippets are displayed. Private matching context and raw CSD metadata are excluded.",
    }
    (output / "publisher_snapshot.json.part").write_text(json.dumps(manifest, indent=2))
    (output / "publisher_snapshot.json.part").replace(output / "publisher_snapshot.json")
    print(json.dumps(manifest, indent=2))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sections", type=Path, required=True)
    parser.add_argument("--extractions", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("src/viz/assets"))
    args = parser.parse_args()
    build(args.sections, args.extractions, args.output)


if __name__ == "__main__":
    main()
