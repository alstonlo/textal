"""Cache public article identities from Europe PMC and publisher Crossref deposits.

Uses DOI/PMCID linkage only; never reads CSD bibliography or crystal metadata.
No article files are downloaded. Responses are projected to a small allowlist.
"""

import argparse
import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def clean(value):
    return html.unescape(re.sub("<[^>]*>", "", value or "")).strip()


def request(url):
    for attempt in range(3):
        try:
            with urlopen(
                Request(url, headers={"User-Agent": "TEXtalPublisherBrowser/1.0"}), timeout=45
            ) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def europe_batch(dois):
    query = " OR ".join('DOI:"' + d + '"' for d in dois)
    url = (
        BASE
        + "?"
        + urlencode({"query": query, "format": "json", "pageSize": 1000, "resultType": "core"})
    )
    data = request(url)
    found = {}
    for record in data.get("resultList", {}).get("result", []):
        doi = (record.get("doi") or "").lower().strip()
        if doi not in dois:
            continue
        journal_info = record.get("journalInfo") or {}
        journal = journal_info.get("journal") or {}
        year = str(record.get("pubYear") or journal_info.get("yearOfPublication") or "")
        found[doi] = {
            "doi": doi,
            "title": clean(record.get("title")) or doi,
            "journal": clean(journal.get("title") or record.get("journalTitle"))
            or "Journal unavailable",
            "year": int(year) if year.isdigit() else None,
            "pmcid": record.get("pmcid"),
            "source": "Europe PMC article bibliography",
            "source_url": "https://europepmc.org/search?query=" + quote("DOI:" + doi),
            "licenses": [],
        }
    return found


def crossref(doi):
    url = "https://api.crossref.org/works/" + quote(doi, safe="")
    try:
        record = request(url)["message"]
    except (HTTPError, URLError, TimeoutError, KeyError, ValueError):
        return doi, {
            "doi": doi,
            "title": doi,
            "journal": "Journal unavailable",
            "year": None,
            "pmcid": None,
            "source": "DOI only; publisher bibliography unavailable",
            "source_url": "https://doi.org/" + doi,
            "licenses": [],
        }
    returned = (record.get("DOI") or "").lower()
    if returned != doi:
        raise ValueError("Crossref DOI mismatch")
    date = (
        record.get("published")
        or record.get("published-print")
        or record.get("published-online")
        or {}
    )
    parts = date.get("date-parts") or [[]]
    return doi, {
        "doi": doi,
        "title": clean((record.get("title") or [doi])[0]),
        "journal": clean((record.get("container-title") or ["Journal unavailable"])[0]),
        "year": parts[0][0] if parts[0] else None,
        "pmcid": None,
        "source": "Publisher-deposited Crossref bibliography",
        "source_url": url,
        "licenses": [
            {
                "url": item["URL"],
                "type": "Publisher-deposited terms",
                "text": "Licence URL deposited by the publisher in Crossref.",
            }
            for item in record.get("license", [])
            if item.get("URL", "").startswith(("https://", "http://"))
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--targets", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    target = json.loads(args.targets.read_text())
    wanted = {r["doi"].lower() for r in target}
    found = json.loads(args.output.read_text()) if args.output.exists() else {}
    todo = sorted(wanted - found.keys())
    for index in range(0, len(todo), 160):
        batches = [todo[i : i + 40] for i in range(index, min(index + 160, len(todo)), 40)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            for future in as_completed([pool.submit(europe_batch, batch) for batch in batches]):
                try:
                    found.update(future.result())
                except (HTTPError, URLError, TimeoutError, ValueError):
                    pass
        args.output.write_text(json.dumps(found, ensure_ascii=False))
        print(
            json.dumps(
                {
                    "stage": "Europe PMC",
                    "bibliographies": len(found),
                    "targets": len(wanted),
                    "batches_checked": min(index + 160, len(todo)),
                }
            ),
            flush=True,
        )
        time.sleep(0.3)
    todo = sorted(wanted - found.keys())
    with ThreadPoolExecutor(max_workers=3) as pool:
        for index, future in enumerate(as_completed([pool.submit(crossref, doi) for doi in todo])):
            doi, record = future.result()
            found[doi] = record
            if index % 25 == 0:
                args.output.write_text(json.dumps(found, ensure_ascii=False))
                print(
                    json.dumps(
                        {"stage": "Crossref", "bibliographies": len(found), "targets": len(wanted)}
                    ),
                    flush=True,
                )
    args.output.write_text(json.dumps(found, ensure_ascii=False))
    print(
        json.dumps({"stage": "complete", "bibliographies": len(found), "targets": len(wanted)}),
        flush=True,
    )


if __name__ == "__main__":
    main()
