"""Build allowlisted publisher records across journals.

Refcode/DOI associations are the identifier bridge. Paper identities come from
publisher XML, Europe PMC or publisher Crossref deposits. Publisher Markdown and
quoted extraction evidence provide text; matching context and raw errors stay private.
The CSD metadata is read only to remove what the records copied from it.
"""

import argparse
import gzip
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from dataset.extraction_prompt import ENTRY_FIELDS
from viz.publisher_data import licence, text_name

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
    "authors_json": pl.String,
    "paragraphs_json": pl.String,
    "sections_json": pl.String,
    "licenses_json": pl.String,
    "provenance_json": pl.String,
}


def normalized(value):
    return "".join(c for c in str(value).casefold() if c.isalnum())


# Wording by which a record cites the CSD rows the model was given, rather than the paper.
CSD_INPUT = re.compile(
    r"(?i)\bsupplied (?:CSD|CCDC|name|formula|table|metadata|chemical|entry|entries|record)|"
    r"linked[- ]entr|entry table|\b(?:CSD|CCDC)(?:'s)? (?:entry|entries|record|table|name|"
    r"formula|metadata|data|lists?|gives|says|reports|chemical)\b"
)
CSD_NAMES = re.compile(r"(?i)\b(?:CSD|CCDC|Cambridge Structural Database|refcodes?)\b")
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[\"'“])")


def paper_sources(pmc, folder):
    """The Markdown (text and supplementary documents) and the authors of a paper of `pmc`."""
    if pmc is None or folder is None:
        return {}, []
    parsed, xml = pmc / "parsed" / folder, pmc / "raw" / folder / "paper.xml"
    text = {}
    if (parsed / "paper.md").is_file():
        text = {
            "main_text": (parsed / "paper.md").read_text(),
            "supplements": [
                {"name": f.name, "text": f.read_text()}
                for f in sorted(parsed.glob("supplementary*.md"))
            ],
        }
    return text, authors(xml) if xml.is_file() else []


def write_text(output, paper, text):
    """Writes the Markdown of a paper whose licence allows it into the dataset folder."""
    path = output / text_name(paper["pmcid"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".part")
    with gzip.open(temp, "wt") as stream:
        json.dump({"doi": paper["doi"], **text}, stream, ensure_ascii=False)
    temp.replace(path)


def authors(path):
    """The authors of a paper, from its PMC XML."""
    meta = ET.parse(path).getroot().find(".//article-meta")
    names = []
    for c in meta.iter("contrib") if meta is not None else ():
        if c.get("contrib-type") == "author":
            parts = [c.findtext("name/given-names"), c.findtext("name/surname")]
            name = " ".join(p.strip() for p in parts if p) or (c.findtext("collab") or "").strip()
            if name:
                names.append(" ".join(name.split()))
    return names


def words(value):
    """The words of `value`, lowercased, with subscripts as digits, padded and joined by spaces."""
    found = re.findall(r"\w+", unicodedata.normalize("NFKC", value).casefold())
    return " " + " ".join(found) + " "


def csd_values(rows):
    """The values of the CSD rows that the model saw, in the form of `words`."""
    values = set()
    for row in rows:
        for key in ENTRY_FIELDS[1:]:
            items = row[key] if isinstance(row[key], list) else [row[key]]
            for item in (str(i).split("//")[0] for i in items if i is not None):
                parts = item.split(",") if key in ("formula", "solvent") else [item]
                # A paper writes "160 (2) K" where the CSD has "160 K": only the number is matched.
                if key in ("temperature", "pressure", "melting_point"):
                    parts = [re.sub(r"\.0$", "", n) for n in re.findall(r"\d+(?:\.\d+)?", item)]
                for part in parts:
                    values.add(words(part))
                    if key == "formula":
                        # "C10 H16 O4" as written in a paper: "C10H16O4"
                        values.add(words(re.sub(r"(?<=[A-Za-z])1(?!\d)|\s", "", part)))
    return {v for v in values if len(v.strip()) >= 3}


def without_csd(text, values, corpus):
    """Drops each sentence of `text` that says what only the CSD rows given to the model say.

    A sentence goes if it holds a CSD value that the paper does not, cites the rows given to the
    model ("the CSD entry", "the supplied name"), or names the CSD where the paper never does.
    The check is lexical: a value the model reworded is not caught.
    """
    kept = []
    for s in SENTENCE.split(text or ""):
        w = words(s)
        # The paper may have the plural, e.g. "blocks" for the CSD's "block".
        copied = any(
            (v in w) and (v not in corpus) and (v[:-1] + "s " not in corpus) for v in values
        )
        named = any(words(n) not in corpus for n in CSD_NAMES.findall(s))
        if not (copied or named or CSD_INPUT.search(s)):
            kept.append(s)
    return " ".join(kept) or None


def text_supported(value, corpus):
    """Conservative lexical check for generated prose, not semantic validation."""
    if not value or re.search(
        r"(?i)(?:CSD|CCDC)\s+(?:metadata|synonym|record|entry\s+says)", value
    ):
        return False
    words = {normalized(w) for w in re.findall(r"\w{4,}", value)}
    return bool(words) and sum(word in corpus for word in words) / len(words) >= 0.75


def public_extraction(row, paper, fulltext=None, recorded=False, csd=frozenset()):
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
    # Without the paper's text, its quotes are all that shows what the paper says.
    quotes = " ".join(ev.get("quote") or "" for ev in row.get("evidence") or [])
    paper_words = words(text if text.strip() else quotes)
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
    fields = {key: without_csd(row.get(key), csd, paper_words) for key in FIELDS}
    # Generated summaries remain paper-based prose; no CSD matching rationale is exported.
    summary_corpus = corpus or normalized(" ".join(ev["quote"] for ev in evidence))
    summary = without_csd(row.get("summary"), csd, paper_words)
    summary = summary if text_supported(summary, summary_corpus) else None
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
        "fields": {key: fields[key] for key in FIELDS if key in supported and fields[key]},
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
        "authors_json": json.dumps(paper["authors"], ensure_ascii=False),
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
            old.setdefault("authors_json", "[]")
            papers.setdefault(old["paper_id"], old)
        for old in old_entries:
            old.setdefault("paper_id", "doi:" + old["doi"])
            entries.setdefault(old["id"], old)
    # Drop any unreferenced paper records after replacing a newer extraction snapshot.
    used = {e["paper_id"] for e in entries.values()}
    papers = {k: p for k, p in papers.items() if k in used}
    # The texts of papers left out or no longer allowed are removed.
    texts = {
        output / text_name(p["pmcid"])
        for p in papers.values()
        if json.loads(p["provenance_json"])["has_full_text"]
    }
    for path in (output / "texts").glob("*/*.json.gz"):
        if path not in texts:
            path.unlink()
    missing = [path for path in texts if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"{len(missing)} texts are missing, e.g. {missing[0]}")
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
        "schema": "publisher-only-v3",
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
    csd,
    bibliography=None,
    linkage=None,
    pmc=None,
    cache=None,
    preserve_existing=False,
):
    """Writes the tables; `pmc` is `data/papers/` (texts, authors), `cache` the publisher files.

    Only papers under a Creative Commons licence get their text and publisher files released.
    """
    ext = {r["identifier"]: r for r in pl.read_parquet(extractions).to_dicts()}
    bibliography = json.loads(Path(bibliography).read_text()) if bibliography else {}
    links = {r["doi"]: r for r in json.loads(Path(linkage).read_text())} if linkage else {}
    with gzip.open(sections, "rt") as stream:
        acta = [r for r in map(json.loads, stream) if r.get("refcodes")]
    ids = set(ext) | {ref for raw in acta for ref in raw["refcodes"]}
    table = pl.read_parquet(csd, columns=ENTRY_FIELDS).filter(pl.col("identifier").is_in(ids))
    csd = {r["identifier"]: r for r in table.to_dicts()}
    dirs = {}
    if pmc:
        pmc = Path(pmc)
        meta = pl.read_parquet(pmc / "metadata.parquet", columns=["doi", "dir"]).drop_nulls()
        dirs = dict(zip(meta["doi"].str.to_lowercase(), meta["dir"], strict=True))
    papers, entries = {}, {}
    for raw in acta:
        refs = raw["refcodes"]
        pmcid, doi = raw["pmcid"], raw["doi"].lower()
        if not re.fullmatch(r"PMC[0-9]+", pmcid):
            raise ValueError("Invalid PMC identifier")
        fulltext, names = paper_sources(pmc, dirs.get(doi))
        paper = {
            "paper_id": "doi:" + doi,
            "pmcid": pmcid,
            "doi": doi,
            "title": raw.get("article_title") or doi,
            "journal": raw.get("journal") or "Acta Crystallographica E",
            "year": raw.get("year"),
            "authors": names,
            "paragraphs": [
                {k: p[k] for k in ("text", "paragraph_index")} for p in raw.get("paragraphs", [])
            ],
        }
        licenses = [
            {key: v.get(key) for key in ("url", "type", "text")}
            for v in raw.get("article_license_evidence", [])
        ]
        free = licence(licenses).startswith("CC")
        papers[paper["paper_id"]] = paper_record(
            paper,
            [
                {key: s.get(key) for key in ("title", "label", "paragraph_indices")}
                for s in raw.get("matched_sections", [])
            ],
            licenses,
            {
                "collection": "Acta E",
                "bibliography_source": "Publisher XML",
                "bibliography_url": "https://pmc.ncbi.nlm.nih.gov/articles/" + pmcid + "/",
                "text_source": "Publisher XML sections",
                "has_publisher_package": free
                and bool(cache and (Path(cache) / pmcid / "manifest.json").is_file()),
                "has_full_text": free and bool(fulltext.get("main_text")),
            },
        )
        if free and fulltext.get("main_text"):
            write_text(output, paper, fulltext)
        values = csd_values([csd[ref] for ref in refs if ref in csd])
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
                    public_extraction(row, paper, fulltext, csd=values), ensure_ascii=False
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
            link = links.get(doi, {})
            pmcid = link.get("pmcid") or bib.get("pmcid")
            if pmcid and not re.fullmatch(r"PMC[0-9]+", pmcid):
                pmcid = None
            fulltext, names = paper_sources(pmc, dirs.get(doi))
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
                "authors": names,
                "paragraphs": paragraphs,
            }
            # The licence of the PMC copy, which is the one released, not the publisher's.
            licenses = []
            if link.get("license"):
                licenses = [{"url": None, "type": "PMC licence", "text": link["license"]}]
            free = licence(licenses).startswith("CC")
            papers[paper["paper_id"]] = paper_record(
                paper,
                [],
                licenses,
                {
                    "collection": "Other journals",
                    "bibliography_source": bib.get("source") or "DOI only",
                    "bibliography_url": bib.get("source_url") or "https://doi.org/" + doi,
                    "text_source": "Recorded publisher excerpts from extraction",
                    "has_publisher_package": free
                    and bool(cache and pmcid and (Path(cache) / pmcid / "manifest.json").is_file()),
                    "has_full_text": free and bool(fulltext.get("main_text")),
                },
            )
            if free and fulltext.get("main_text"):
                write_text(output, paper, fulltext)
            values = csd_values([csd[r["identifier"]] for r in rows if r["identifier"] in csd])
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
                        public_extraction(row, paper, fulltext, recorded=True, csd=values),
                        ensure_ascii=False,
                    ),
                }
    return publish(entries, papers, output, preserve_existing)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sections", type=Path, required=True)
    p.add_argument("--extractions", type=Path, required=True)
    p.add_argument("--csd", type=Path, required=True)
    p.add_argument("--output", type=Path, default=Path("data/textal"))
    p.add_argument("--bibliography", type=Path)
    p.add_argument("--linkage", type=Path)
    p.add_argument("--papers", type=Path)
    p.add_argument("--cache", type=Path)
    p.add_argument("--preserve-existing", action="store_true")
    a = p.parse_args()
    build(
        a.sections,
        a.extractions,
        a.output,
        a.csd,
        bibliography=a.bibliography,
        linkage=a.linkage,
        pmc=a.papers,
        cache=a.cache,
        preserve_existing=a.preserve_existing,
    )


if __name__ == "__main__":
    main()
