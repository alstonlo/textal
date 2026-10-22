"""Read only publisher Markdown from the supplied paper archive, never CSD metadata.

Targets are DOI identities. The existing fulltext index supplies exact archive
members. All non-Markdown files, CSD tables and structure files are excluded.
"""

import argparse
import gzip
import json
import tarfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath


def xml_paper_text(package, pmcid, doi):
    """Read DOI-verified main JATS from an existing publisher package."""
    raw = None
    with tarfile.open(package, "r|gz") as archive:
        for member in archive:
            name = PurePosixPath(member.name).name
            if member.isfile() and name.startswith(pmcid + ".") and name.endswith(".xml"):
                if member.size > 20_000_000:
                    raise ValueError("Publisher XML exceeds text-export limit")
                raw = archive.extractfile(member).read()
                break
    if raw is None:
        raise ValueError("No main publisher XML")
    root = ET.fromstring(raw)

    def tag(node):
        return node.tag.rsplit("}", 1)[-1]

    def text(node):
        return " ".join("".join(node.itertext()).split())

    dois = {
        text(node).lower()
        for node in root.iter()
        if tag(node) == "article-id" and node.get("pub-id-type") == "doi"
    }
    if doi not in dois:
        raise ValueError("Publisher XML DOI mismatch")
    title = next((text(n) for n in root.iter() if tag(n) == "article-title"), doi)
    lines = ["# " + title, ""]

    def walk(node):
        kind = tag(node)
        if kind in {"ref-list", "table-wrap", "fig", "fig-group"}:
            return
        if kind in {"title", "p"}:
            lines.extend([("## " if kind == "title" else "") + text(node), ""])
            return
        for child in node:
            walk(child)

    for node in root.iter():
        if tag(node) in {"abstract", "body"}:
            walk(node)
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--targets", type=Path, required=True)
    p.add_argument("--control", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--xml-fallback-packages",
        type=Path,
        help="Existing publisher package directory, for missing main texts only",
    )
    p.add_argument("--pmcid-map", type=Path, help="Private DOI-to-PMCID identity map")
    a = p.parse_args()
    if bool(a.xml_fallback_packages) != bool(a.pmcid_map):
        p.error("--xml-fallback-packages and --pmcid-map must be supplied together")
    targets = set(json.loads(a.targets.read_text()))
    fulltexts = json.loads((a.control / "fulltext-reuse-index.json").read_text())
    index = json.loads((a.control / "shared-archive-index.json").read_text())
    archive = Path(json.loads((a.control / "shared-archive-summary.json").read_text())["archive"])
    wanted = {}
    directories = {
        str(PurePosixPath(r["archive_member"]).parent): doi
        for doi, r in fulltexts.items()
        if doi in targets
    }
    for group in index.values():
        for f in group["files"]:
            member = f["path"]
            folder = str(PurePosixPath(member).parent)
            if (
                folder not in directories
                or f["section"] != "parsed"
                or not f["name"].endswith(".md")
            ):
                continue
            if (
                f["name"] not in ("paper.md", "supplementary.md")
                and "suppl" not in f["name"].lower()
            ):
                continue
            wanted[member] = (directories[folder], f["name"])
    a.output.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    n = 0
    with tarfile.open(archive, "r|gz") as source, gzip.open(a.output, "wt", compresslevel=1) as out:
        for member in source:
            if member.name not in wanted or not member.isfile():
                continue
            doi, name = wanted[member.name]
            if member.size > 20_000_000:
                continue
            raw = source.extractfile(member).read()
            out.write(
                json.dumps(
                    {
                        "doi": doi,
                        "name": name,
                        "text": raw.decode("utf-8", errors="replace"),
                        "kind": "main" if name == "paper.md" else "supplementary",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            seen.add(doi)
            n += 1
            if n % 2000 == 0:
                print(json.dumps({"files": n, "papers": len(seen)}), flush=True)
    xml_added, xml_gaps = 0, []
    if a.xml_fallback_packages:
        mapping = json.loads(a.pmcid_map.read_text())
        with gzip.open(a.output, "at", compresslevel=1) as out:
            for doi in sorted(targets - seen):
                pmcid = mapping.get(doi)
                if not pmcid or not str(pmcid).startswith("PMC") or not str(pmcid)[3:].isdigit():
                    xml_gaps.append({"doi": doi, "reason": "No publisher PMCID linkage"})
                    continue
                try:
                    text = xml_paper_text(a.xml_fallback_packages / (pmcid + ".tar.gz"), pmcid, doi)
                except (OSError, ValueError, ET.ParseError, tarfile.TarError) as exc:
                    xml_gaps.append({"doi": doi, "reason": str(exc)})
                    continue
                out.write(
                    json.dumps(
                        {"doi": doi, "name": "paper.md", "kind": "main", "text": text},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                seen.add(doi)
                n += 1
                xml_added += 1
    report = {
        "at": datetime.now(UTC).isoformat(),
        "target_papers": len(targets),
        "papers": len(seen),
        "markdown_files": n,
        "missing_dois": sorted(targets - seen),
        "bytes": a.output.stat().st_size,
        "xml_fallback_added": xml_added,
        "xml_gaps": xml_gaps,
    }
    a.output.with_suffix(".summary.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
