"""Inventory publisher CIF availability in saved PMC packages; never reads CSD CIFs.

Counts refcode-to-paper associations, not verified refcode-to-CIF-block matches.
Coordinate CIF tags are checked, including CIFs inside supplementary ZIP files.
Oversized ZIP members are recorded as gaps instead of counted as absent. Each completed record is append-only/resumable.
"""

import argparse
import gzip
import io
import json
import tarfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

UTC = timezone.utc  # noqa: UP017 -- remote system Python may be 3.10


def inspect(row, roots, zip_fallback=False):
    pmcid = row["pmcid"]
    path = next(
        (
            r / "packages" / (pmcid + ".tar.gz")
            for r in roots
            if (r / "packages" / (pmcid + ".tar.gz")).is_file()
        ),
        None,
    )
    result = {key: row[key] for key in ("pmcid", "doi", "journal", "refcodes")}
    result.update(
        publisher_coordinate_cif=False,
        zip_needs_inspection=False,
        zip_inspected=zip_fallback,
        zip_scan_gaps=[],
    )
    if path is None:
        result["error"] = "package_missing"
        return result
    try:
        with tarfile.open(path, "r|gz") as tar:
            for member in tar:
                name = member.name.lower()
                if not member.isfile():
                    continue
                if name.endswith(".zip"):
                    result["zip_needs_inspection"] = not zip_fallback
                    if zip_fallback:
                        if member.size > 250_000_000:
                            result["zip_scan_gaps"].append(member.name)
                            result["zip_needs_inspection"] = True
                            continue
                        with zipfile.ZipFile(io.BytesIO(tar.extractfile(member).read())) as archive:
                            for info in archive.infolist():
                                if not info.filename.lower().endswith((".cif", ".cif.gz")):
                                    continue
                                if info.file_size > 50_000_000:
                                    result["zip_scan_gaps"].append(
                                        member.name + "::" + info.filename
                                    )
                                    result["zip_needs_inspection"] = True
                                    continue
                                blob = archive.read(info)
                                if info.filename.lower().endswith(".gz"):
                                    blob = gzip.decompress(blob)
                                if b"_atom_site_" in blob.lower():
                                    result.update(
                                        publisher_coordinate_cif=True,
                                        zip_needs_inspection=False,
                                        member=member.name + "::" + info.filename,
                                    )
                                    return result
                if name.endswith((".cif", ".cif.gz")):
                    stream = tar.extractfile(member)
                    if name.endswith(".gz"):
                        stream = gzip.GzipFile(fileobj=stream)
                    # Atom-site tags may follow long embedded publication sections.
                    blob = stream.read().lower()
                    if b"_atom_site_" in blob:
                        result.update(publisher_coordinate_cif=True, member=member.name)
                        return result
    except (tarfile.TarError, OSError, EOFError, ValueError, zipfile.BadZipFile) as exc:
        result["error"] = type(exc).__name__
    return result


def is_acta_e(row):
    return row["journal"] in {
        "Acta Crystallographica E",
        "Acta Crystallographica Section E: Structure Reports Online",
    }


def summarize(rows):
    rows = list({r["pmcid"]: r for r in rows}.values())
    out = {}
    for scope in ("acta_e", "all_csd_pmc"):
        selected = [r for r in rows if scope != "acta_e" or is_acta_e(r)]
        refs = {ref for r in selected for ref in r["refcodes"]}
        cif_refs = {ref for r in selected if r["publisher_coordinate_cif"] for ref in r["refcodes"]}
        out[scope] = dict(  # noqa: C408 -- named counts are easier to compare
            papers_checked=len(selected),
            refcodes_checked=len(refs),
            papers_with_publisher_cif=sum(r["publisher_coordinate_cif"] for r in selected),
            refcodes_linked_to_publisher_cif=len(cif_refs),
            zip_only_pending=sum(
                r["zip_needs_inspection"] and not r["publisher_coordinate_cif"] for r in selected
            ),
            errors=sum(bool(r.get("error")) for r in selected),
        )
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--root", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.index, "rt") as f:
        papers = [r for r in json.load(f)["papers"] if r["refcodes"]]
    ledger = args.output / "publisher-cif-inventory.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()] if ledger.exists() else []
    done = {r["pmcid"] for r in rows}
    # Finish Acta E first so its count is available before the broader inventory.
    for acta in (True, False):
        todo = [r for r in papers if (is_acta_e(r)) == acta and r["pmcid"] not in done]
        with ThreadPoolExecutor(max_workers=args.workers) as pool, ledger.open("a") as stream:
            futures = [pool.submit(inspect, r, args.root) for r in todo]
            for future in as_completed(futures):
                result = future.result()
                rows.append(result)
                stream.write(json.dumps(result) + "\n")
                stream.flush()
                if len(rows) % 200 == 0:
                    report = {
                        "at": datetime.now(UTC).isoformat(),
                        "target_papers": len(papers),
                        "phase": "acta_e" if acta else "all_csd_pmc",
                        **summarize(rows),
                    }
                    temp = args.output / "publisher-cif-summary.json.part"
                    temp.write_text(json.dumps(report, indent=2))
                    temp.replace(args.output / "publisher-cif-summary.json")
    latest = {r["pmcid"]: r for r in rows}
    todo = [
        r
        for r in latest.values()
        if r["zip_needs_inspection"]
        and not r["publisher_coordinate_cif"]
        and not r.get("zip_inspected")
    ]
    with ThreadPoolExecutor(max_workers=args.workers) as pool, ledger.open("a") as stream:
        futures = [pool.submit(inspect, row, args.root, True) for row in todo]
        for future in as_completed(futures):
            result = future.result()
            rows.append(result)
            stream.write(json.dumps(result) + "\n")
            stream.flush()
            report = {
                "at": datetime.now(UTC).isoformat(),
                "target_papers": len(papers),
                "phase": "zip_fallback",
                **summarize(rows),
            }
            temp = args.output / "publisher-cif-summary.json.part"
            temp.write_text(json.dumps(report, indent=2))
            temp.replace(args.output / "publisher-cif-summary.json")
    report = {
        "at": datetime.now(UTC).isoformat(),
        "target_papers": len(papers),
        "phase": "finished",
        **summarize(rows),
    }
    (args.output / "publisher-cif-summary.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
