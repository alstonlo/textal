"""Build allowlisted publisher records across journals; never reads raw CSD metadata.

Refcode/DOI associations are the identifier bridge. Paper identities come from
publisher XML, Europe PMC or publisher Crossref deposits. Publisher Markdown and
quoted extraction evidence provide text; matching context and raw errors stay private.
"""

import argparse
import gzip
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from functools import lru_cache
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
    "paper_id": pl.String,
    "extraction_json": pl.String,
}
PAPER_COLUMNS = {
    "paper_id": pl.String,
    "pmcid": pl.String,
    "doi": pl.String,
    "title": pl.String,
    "journal": pl.String,
    "year": pl.Int64,
    "paragraphs_json": pl.String,
    "sections_json": pl.String,
    "licenses_json": pl.String,
    "provenance_json": pl.String,
}


def normalized(value):
    return "".join(c for c in str(value).casefold() if c.isalnum())


def text_cache_path(folder, doi):
    return Path(folder) / (hashlib.sha256(doi.encode()).hexdigest() + ".json.gz")


@lru_cache(maxsize=64)
def publisher_text(folder, doi):
    if not folder:
        return {}
    path = text_cache_path(folder, doi)
    if not path.is_file():
        return {}
    with gzip.open(path, "rt") as stream:
        data = json.load(stream)
    if data.get("doi") != doi or set(data) - {"doi", "main_text", "supplements"}:
        raise ValueError("Unexpected publisher text cache")
    if any(set(item) != {"name", "text"} for item in data.get("supplements", [])):
        raise ValueError("Unexpected publisher supplement fields")
    return data


def text_supported(value, corpus):
    """Conservative lexical check for generated prose, not semantic validation."""
    if not value or re.search(
        r"(?i)(?:CSD|CCDC)\s+(?:metadata|synonym|record|entry\s+says)", value
    ):
        return False
    words = {normalized(w) for w in re.findall(r"\w{4,}", value)}
    return bool(words) and sum(word in corpus for word in words) / len(words) >= 0.75


def public_extraction(row, paper, fulltext=None, recorded=False):
    if not row:
        return {
            "status": "pending",
            "summary": None,
            "compound_label": None,
            "fields": {},
            "evidence": [],
            "evidence_policy": "publisher text",
        }
    fulltext = fulltext or {}
    text = " ".join(
        ([] if recorded else [p["text"] for p in paper["paragraphs"]])
        + [fulltext.get("main_text", "")]
        + [p["text"] for p in fulltext.get("supplements", [])]
    )
    corpus = normalized(text)
    sources = {
        str(s.get("name") or "").replace("\\", "/").rsplit("/", 1)[-1]
        for s in row.get("source_files") or []
    }
    evidence = []
    for ev in row.get("evidence") or []:
        quote = ev.get("quote") or ""
        field = ev.get("field")
        name = str(ev.get("source_file") or "").replace("\\", "/").rsplit("/", 1)[-1]
        if field not in (*FIELDS, "summary", "compound_label") or len(normalized(quote)) < 20:
            continue
        verified = normalized(quote) in corpus
        recorded_source = name in sources and name.lower().endswith((".md", ".pdf", ".xml", ".txt"))
        if verified or (recorded and recorded_source):
            evidence.append(
                {
                    "field": field,
                    "quote": quote,
                    "source_file": (
                        "Supplementary information" if "supp" in name.lower() else "Publisher text"
                    ),
                    "verified": verified,
                }
            )
    supported = {ev["field"] for ev in evidence}
    # Generated summaries remain paper-based prose; no CSD matching rationale is exported.
    summary_corpus = corpus or normalized(" ".join(ev["quote"] for ev in evidence))
    summary = row.get("summary") if text_supported(row.get("summary"), summary_corpus) else None
    label = row.get("compound_label")
    if not label or not (
        (len(normalized(label)) >= 6 and normalized(label) in corpus)
        or any(
            ev["field"] == "compound_label" and normalized(label) in normalized(ev["quote"])
            for ev in evidence
        )
    ):
        label = None
    return {
        "status": row.get("extraction_status") or "unknown",
        "summary": summary,
        "compound_label": label,
        "fields": {key: row[key] for key in FIELDS if key in supported and row.get(key)},
        "evidence": evidence,
        "extracted_at": str(row.get("extracted_at") or ""),
        "model": row.get("model"),
        "prompt_version": row.get("prompt_version"),
        "evidence_policy": "publisher text checked"
        if all(e["verified"] for e in evidence)
        else "recorded publisher quotes; some not independently matched",
    }


def paper_record(paper, sections, licenses, provenance):
    return {
        **{key: paper.get(key) for key in ("paper_id", "pmcid", "doi", "title", "journal", "year")},
        "paragraphs_json": json.dumps(paper["paragraphs"], ensure_ascii=False),
        "sections_json": json.dumps(sections, ensure_ascii=False),
        "licenses_json": json.dumps(licenses, ensure_ascii=False),
        "provenance_json": json.dumps(provenance, ensure_ascii=False),
    }


def publish(entries, papers, output, preserve_existing=False):
    if preserve_existing and (output / "entries.parquet").exists():
        old_entries = pl.read_parquet(output / "entries.parquet").to_dicts()
        old_papers = pl.read_parquet(output / "papers.parquet").to_dicts()
        for old in old_papers:
            if "paper_id" not in old:
                old["paper_id"] = "doi:" + old["doi"]
                old["provenance_json"] = json.dumps(
                    {
                        "collection": "Acta E",
                        "bibliography_source": "Publisher XML",
                        "text_source": "Publisher XML sections",
                        "has_full_text": False,
                    }
                )
            papers.setdefault(old["paper_id"], old)
        for old in old_entries:
            old.setdefault("paper_id", "doi:" + old["doi"])
            entries.setdefault(old["id"], old)
    # Drop any unreferenced paper records after replacing a newer extraction snapshot.
    used = {e["paper_id"] for e in entries.values()}
    papers = {k: p for k, p in papers.items() if k in used}
    statuses = Counter(json.loads(e["extraction_json"])["status"] for e in entries.values())
    collections = {}
    for name in ("Acta E", "Other journals"):
        ids = {
            k for k, p in papers.items() if json.loads(p["provenance_json"])["collection"] == name
        }
        collections[name] = {
            "papers": len(ids),
            "refcodes": sum(e["paper_id"] in ids for e in entries.values()),
        }
    manifest = {
        "schema": "publisher-only-v2",
        "built_at": datetime.now(UTC).isoformat(),
        "refcodes": len(entries),
        "papers": len(papers),
        "extraction_statuses": dict(statuses),
        "with_snippets": sum(bool(json.loads(p["paragraphs_json"])) for p in papers.values()),
        "collections": collections,
        "journals": dict(Counter(p["journal"] for p in papers.values()).most_common()),
        "source": "Publisher text and article bibliography; CSD refcodes provide identifier linkage only.",
        "extraction_policy": "Publisher quotes are marked as matched to stored text or recorded in the extraction. No CSD matching rationale or raw CSD metadata is exported.",
    }
    output.mkdir(parents=True, exist_ok=True)
    for filename, rows, schema in (
        (
            "entries.parquet",
            sorted(entries.values(), key=lambda e: e["id"]),
            ENTRY_COLUMNS,
        ),
        ("papers.parquet", list(papers.values()), PAPER_COLUMNS),
    ):
        temporary = output / (filename + ".part")
        pl.DataFrame(rows, schema=schema).write_parquet(temporary)
        temporary.replace(output / filename)
    (output / "snapshot.json.part").write_text(json.dumps(manifest, indent=2))
    (output / "snapshot.json.part").replace(output / "snapshot.json")
    print(json.dumps(manifest, indent=2))
    return manifest


def build(
    sections,
    extractions,
    output,
    bibliography=None,
    linkage=None,
    texts=None,
    preserve_existing=False,
):
    ext = {r["identifier"]: r for r in pl.read_parquet(extractions).to_dicts()}
    bibliography = json.loads(Path(bibliography).read_text()) if bibliography else {}
    links = {r["doi"]: r for r in json.loads(Path(linkage).read_text())} if linkage else {}
    papers, entries, acta_dois = {}, {}, set()
    with gzip.open(sections, "rt") as stream:
        for line in stream:
            raw = json.loads(line)
            refs = raw.get("refcodes") or []
            if not refs:
                continue
            pmcid, doi = raw["pmcid"], raw["doi"].lower()
            if not re.fullmatch(r"PMC[0-9]+", pmcid):
                raise ValueError("Invalid PMC identifier")
            acta_dois.add(doi)
            paper = {
                "paper_id": "doi:" + doi,
                "pmcid": pmcid,
                "doi": doi,
                "title": raw.get("article_title") or doi,
                "journal": raw.get("journal") or "Acta Crystallographica E",
                "year": raw.get("year"),
                "paragraphs": [
                    {k: p[k] for k in ("text", "paragraph_index")}
                    for p in raw.get("paragraphs", [])
                ],
            }
            fulltext = publisher_text(str(texts) if texts else "", doi)
            papers[paper["paper_id"]] = paper_record(
                paper,
                [
                    {key: s.get(key) for key in ("title", "label", "paragraph_indices")}
                    for s in raw.get("matched_sections", [])
                ],
                [
                    {key: v.get(key) for key in ("url", "type", "text")}
                    for v in raw.get("article_license_evidence", [])
                ],
                {
                    "collection": "Acta E",
                    "bibliography_source": "Publisher XML",
                    "bibliography_url": "https://pmc.ncbi.nlm.nih.gov/articles/" + pmcid + "/",
                    "text_source": "Publisher XML sections",
                    "has_publisher_package": True,
                    "has_full_text": bool(fulltext.get("main_text")),
                },
            )
            for ref in refs:
                if not re.fullmatch(r"[A-Z]{6}[0-9]{0,2}", ref):
                    raise ValueError("Invalid refcode")
                row = ext.get(ref)
                if row and (row.get("doi") or "").lower() != doi:
                    row = None
                entries[ref] = {
                    "id": ref,
                    "doi": doi,
                    "pmcid": pmcid,
                    "paper_id": paper["paper_id"],
                    "extraction_json": json.dumps(
                        public_extraction(row, paper, fulltext), ensure_ascii=False
                    ),
                }
    # A plain Acta E import still imports only Acta E; the combined import opts in
    # with publisher bibliography and preserves the exact supplied row identities.
    if bibliography:
        groups = {}
        for row in ext.values():
            if row["identifier"] not in entries:
                doi = (row["doi"] or "").strip().lower()
                groups.setdefault(doi, []).append(row)
        for doi, rows in groups.items():
            bib = bibliography.get(doi, {})
            pmcid = links.get(doi, {}).get("pmcid") or bib.get("pmcid")
            if pmcid and not re.fullmatch(r"PMC[0-9]+", pmcid):
                pmcid = None
            fulltext = publisher_text(str(texts) if texts else "", doi)
            # Source snippets are recorded publisher passages, never the private matching text.
            paragraphs, seen = [], set()
            for row in rows:
                sources = {
                    str(s.get("name") or "").replace("\\", "/").rsplit("/", 1)[-1]
                    for s in row.get("source_files") or []
                }
                for ev in row.get("evidence") or []:
                    quote = ev.get("quote") or ""
                    source = str(ev.get("source_file") or "").replace("\\", "/").rsplit("/", 1)[-1]
                    if ev.get("field") not in FIELDS or source not in sources or quote in seen:
                        continue
                    seen.add(quote)
                    paragraphs.append({"paragraph_index": len(paragraphs), "text": quote})
            paper = {
                "paper_id": "doi:" + doi,
                "pmcid": pmcid,
                "doi": doi,
                "title": bib.get("title") or doi,
                "journal": bib.get("journal") or "Journal unavailable",
                "year": bib.get("year"),
                "paragraphs": paragraphs,
            }
            papers[paper["paper_id"]] = paper_record(
                paper,
                [],
                bib.get("licenses") or [],
                {
                    "collection": "Other journals",
                    "bibliography_source": bib.get("source") or "DOI only",
                    "bibliography_url": bib.get("source_url") or "https://doi.org/" + doi,
                    "text_source": "Recorded publisher excerpts from extraction",
                    "has_publisher_package": bool(links.get(doi, {}).get("pmcid")),
                    "has_full_text": bool(fulltext.get("main_text")),
                },
            )
            for row in rows:
                ref = row["identifier"]
                if not re.fullmatch(r"[A-Z]{6}[0-9]{0,2}", ref):
                    raise ValueError("Invalid refcode")
                entries[ref] = {
                    "id": ref,
                    "doi": doi,
                    "pmcid": pmcid,
                    "paper_id": paper["paper_id"],
                    "extraction_json": json.dumps(
                        public_extraction(row, paper, fulltext, recorded=True), ensure_ascii=False
                    ),
                }
    return publish(entries, papers, output, preserve_existing)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sections", type=Path, required=True)
    p.add_argument("--extractions", type=Path, required=True)
    p.add_argument("--output", type=Path, default=Path("data/textal"))
    p.add_argument("--bibliography", type=Path)
    p.add_argument("--linkage", type=Path)
    p.add_argument("--texts", type=Path)
    p.add_argument("--preserve-existing", action="store_true")
    a = p.parse_args()
    build(
        a.sections, a.extractions, a.output, a.bibliography, a.linkage, a.texts, a.preserve_existing
    )


if __name__ == "__main__":
    main()
