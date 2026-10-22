import hashlib
import html
import http.client
import json
import pathlib
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import polars as pl
from jsonargparse import auto_cli
from lxml import etree
from tqdm import tqdm

from dataset.csd import NOT_JOURNALS, read_papers, read_pmc_ids
from dataset.paths import DATA_DIR

UA = "crystalog/0.1 (research; open-access papers of CSD entries)"
# The PubMed Central (PMC) open-access articles on AWS: one folder `PMC<id>.<version>/` per article
# version, holding its PDF, its XML full text, its figures and supplementary files, and its record.
BUCKET = "https://pmc-oa-opendata.s3.amazonaws.com"
# The columns of `metadata.parquet`, one row per paper in PMC.
SCHEMA = {
    "dir": pl.String,
    "doi": pl.String,
    "pmcid": pl.String,
    "pmc_version": pl.Int64,
    "refcodes": pl.List(pl.String),
    "year": pl.Int64,
    "journal": pl.String,
    "title": pl.String,
    "authors": pl.String,
    "license": pl.String,
    "is_pmc_openaccess": pl.Boolean,
    "is_manuscript": pl.Boolean,
    "files": pl.List(pl.String),
    "supplementary_names": pl.List(pl.String),
    "skipped": pl.List(pl.String),
    "bytes": pl.Int64,
    "pdf_sha256": pl.String,
    "error": pl.String,
}
# In the JATS XML, supplementary files are `media` (inside `supplementary-material`) and figures
# are `graphic`, so figures are not downloaded.
SUPPLEMENTARY = re.compile(r'<(?:media|supplementary-material)\b[^>]*?xlink:href="([^"]+)"')
# Only supplementary files that are text documents are kept, not data, archives, images or videos.
TEXT_EXTS = [".pdf", ".doc", ".docx", ".rtf", ".odt", ".txt", ".tex", ".htm", ".html"]
EXT = re.compile(r"\.[A-Za-z0-9]{1,5}$")


def get(url):
    """Returns the body at `url`, retrying on throttling, server errors and dropped connections."""
    for wait in [1, 4, 16, 64]:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(request, timeout=300) as r:
                return r.read()
        except urllib.error.HTTPError as err:
            if (err.code != 429) and (err.code < 500):
                raise
        except (OSError, http.client.HTTPException):
            pass
        time.sleep(wait)
    raise RuntimeError(f"failed after retries: {url}")


def save(body, path):
    """Writes `body` to `path` through a temporary file, so no file is left half written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.part")
    tmp.write_bytes(body)
    tmp.rename(path)


def paper_dir(doi):
    """Returns the folder of a paper: its DOI, as `<publisher prefix>/<suffix>`.

    The suffix is kept as it is but for the characters that are not safe in a folder name, which
    become `_`, e.g. `10.1016/s0020-1693(00)84406-0` becomes `10.1016/s0020-1693_00_84406-0`.
    """
    prefix, suffix = doi.lower().split("/", 1)
    assert re.fullmatch(r"10\.\d+", prefix), doi
    return f"{prefix}/{re.sub(r'[^a-z0-9._-]', '_', suffix)}"


def list_article(pmcid):
    """Finds the newest version of an article in the bucket, its files and PMC's record of it.

    Returns:
        The PMCID with `version`, `files` (name to size in bytes) and `meta`; `version` is None
        if the article is not in the bucket, and `error` is set if the requests failed.
    """
    try:
        keys, token = [], None
        while True:
            query = {"list-type": 2, "prefix": f"{pmcid}."}
            if token:
                query["continuation-token"] = token
            listing = get(f"{BUCKET}/?{urllib.parse.urlencode(query)}").decode()
            keys += re.findall(r"<Key>([^<]+)</Key>.*?<Size>(\d+)</Size>", listing)
            token = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", listing)
            if token is None:
                break
            token = token.group(1)
        if not keys:
            return {"pmcid": pmcid, "version": None}

        version = max(int(k.split("/")[0].split(".")[1]) for k, _ in keys)
        stem = f"{pmcid}.{version}"
        files = {k.removeprefix(f"{stem}/"): int(s) for k, s in keys if k.startswith(f"{stem}/")}
        meta = json.loads(get(f"{BUCKET}/{stem}/{stem}.json"))
    except (OSError, RuntimeError, ValueError) as err:
        return {"pmcid": pmcid, "version": None, "error": repr(err)}
    return {"pmcid": pmcid, "version": version, "files": files, "meta": meta}


def download(rec, raw, disk, max_bytes, min_free):
    """Downloads the PDF, the XML and the supplementary files of one article to `raw`, on `disk`.

    The files are saved as `paper.pdf`, `paper.xml` and `supplementary.<ext>`, or
    `supplementary-<n>.<ext>` in the order of the XML when there are several; supplementary files
    that are not text documents (`TEXT_EXTS`) are skipped. Old files in `raw` are deleted first,
    so a rerun starts from scratch. Each file is checked against the md5 in PMC's record, and then
    the XML is indented to be readable, so `paper.xml` differs from PMC's file in whitespace
    between elements.

    Returns:
        The columns of `metadata.parquet` that describe the download.
    """
    # Raised outside the try block, so that a full disk stops the whole run.
    if shutil.disk_usage(disk).free < min_free:
        raise RuntimeError(f"less than {min_free} bytes free in {disk}")

    stem = f"{rec['pmcid']}.{rec['version']}"
    files = {html.unescape(k): v for k, v in rec["files"].items()}
    meta = rec["meta"]
    urls = [meta.get("pdf_url"), meta.get("xml_url"), *(meta.get("media_urls") or [])]
    md5 = {
        urllib.parse.unquote(u.split("?")[0].rsplit("/", 1)[1]): u.split("md5=")[1]
        for u in urls
        if u and ("md5=" in u)
    }
    out = {"files": [], "supplementary_names": [], "skipped": [], "bytes": 0, "pdf_sha256": None}
    try:
        xml_name, pdf_name = f"{stem}.xml", f"{stem}.pdf"
        xml = get(f"{BUCKET}/{stem}/{xml_name}") if (xml_name in files) else b""
        hrefs = dict.fromkeys(
            html.unescape(h) for h in SUPPLEMENTARY.findall(xml.decode(errors="replace"))
        )
        exts = {h: m.group(0).lower() if (m := EXT.search(h)) else "" for h in hrefs}
        sup = [h for h in hrefs if (h in files) and (h not in [xml_name, pdf_name])]
        skipped = [f"{h} (not in bucket)" for h in hrefs if h not in files]
        skipped += [f"{h} (not a text document)" for h in sup if exts[h] not in TEXT_EXTS]
        sup = [h for h in sup if exts[h] in TEXT_EXTS]
        if pdf_name not in files:
            skipped.insert(0, "paper.pdf (not in PMC)")

        jobs = {n: d for n, d in [(pdf_name, "paper.pdf"), (xml_name, "paper.xml")] if n in files}
        for i, name in enumerate(sup):
            jobs[name] = f"supplementary-{i + 1}" if (len(sup) > 1) else "supplementary"
            jobs[name] += exts[name]

        if raw.exists():
            shutil.rmtree(raw)
        saved = []
        for name, dst in jobs.items():
            if files[name] > max_bytes:
                skipped.append(f"{name} (over {max_bytes} bytes)")
                continue
            body = xml if (name == xml_name) else get(f"{BUCKET}/{stem}/{urllib.parse.quote(name)}")
            if (name in md5) and (hashlib.md5(body).hexdigest() != md5[name]):
                raise ValueError(f"{name}: md5 differs from PMC's record")
            if dst == "paper.xml":
                # Like `xmllint --format`, this indents only elements without text of their own, so
                # no text changes. The DTD and entities are not loaded from the network.
                parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
                body = etree.tostring(
                    etree.fromstring(body, parser).getroottree(),
                    pretty_print=True,
                    xml_declaration=True,
                    encoding="UTF-8",
                )
            if dst == "paper.pdf":
                out["pdf_sha256"] = hashlib.sha256(body).hexdigest()
            save(body, raw / dst)
            saved.append(dst)
            out["bytes"] += len(body)

        out |= {"files": saved, "supplementary_names": sup, "skipped": skipped, "error": None}
    except (OSError, RuntimeError, ValueError, etree.XMLSyntaxError) as err:
        out["error"] = repr(err)
    return out


def main(
    csd: str = str(DATA_DIR / "raw" / "csd_metadata.full.parquet"),
    out: str = str(DATA_DIR / "papers"),
    threads: int = 32,
    max_mb: int = 200,
    min_free_gb: int = 100,
    resume: bool = True,
    list_only: bool = False,
):
    """Downloads every CSD paper in the PMC open-access bucket to `<out>/raw/<DOI>/`.

    First downloads, to `data/raw/pmc/` and only if they are not there yet, the PMCID of every DOI
    in PMC (`PMC-ids.csv.gz`) and the listing of each CSD paper in the bucket (`s3.jsonl`, which
    is extended when papers are missing from it). With `list_only`, it stops there.

    Then writes one row per paper to `<out>/metadata.parquet` (columns in `SCHEMA`), leaving out
    retracted papers. With `resume`, papers that downloaded without an error are skipped. Author
    manuscripts often have no PDF in PMC, only the XML; `skipped` says so.
    """
    pmc_dir, out = DATA_DIR / "raw" / "pmc", pathlib.Path(out)
    pmc_ids = pmc_dir / "PMC-ids.csv.gz"
    if not pmc_ids.exists():
        save(get("https://ftp.ncbi.nlm.nih.gov/pub/pmc/PMC-ids.csv.gz"), pmc_ids)

    df = read_papers(csd).filter(~pl.col("journal").is_in(NOT_JOURNALS)).drop_nulls("doi")
    pub = pl.col("publication")
    extra = pl.read_parquet(csd, columns=["identifier", "publication"]).select(
        id="identifier",
        title=pub.struct.field("title").str.strip_chars(),
        authors=pub.struct.field("authors"),
    )
    df = df.join(extra, on="id", validate="1:1")
    df = df.join(read_pmc_ids(pmc_ids), on="doi")
    papers = df.group_by("doi").agg(
        pl.col("pmcid").first(),
        refcodes=pl.col("id").sort(),
        year=pl.col("year").min(),
        journal=pl.col("journal").first(),
        title=pl.col("title").filter(pl.col("title") != "").first(),
        authors=pl.col("authors").first(),
    )
    assert papers["pmcid"].is_unique().all(), "two DOIs with one PMCID"

    # Articles whose listing failed are listed again.
    s3 = pmc_dir / "s3.jsonl"
    recs = {}
    if s3.exists():
        with open(s3) as f:
            recs = {r["pmcid"]: r for r in map(json.loads, f) if "error" not in r}
    missing = sorted(set(papers["pmcid"]) - set(recs))
    with ThreadPoolExecutor(threads) as ex, open(s3, "a") as f:
        for rec in tqdm(ex.map(list_article, missing), total=len(missing), desc="listing"):
            recs[rec["pmcid"]] = rec
            f.write(json.dumps(rec) + "\n")
    if list_only:
        return

    rows = []
    for p in papers.sort("doi").to_dicts():
        rec = recs[p["pmcid"]]
        meta = rec.get("meta", {})
        if meta.get("is_retracted"):
            continue
        p["title"] = p["title"] or meta.get("title") or ""
        if (p["year"] or 0) < 1900:
            year = re.search(r"\b(?:19|20)\d{2}\b", meta.get("citation", ""))
            p["year"] = int(year.group(0)) if year else 0
        p |= {
            "dir": paper_dir(p["doi"]) if rec["version"] else None,
            "pmc_version": rec["version"],
            "license": meta.get("license_code"),
            "is_pmc_openaccess": meta.get("is_pmc_openaccess"),
            "is_manuscript": meta.get("is_manuscript"),
            "error": rec.get("error")
            or (None if rec["version"] else "not in PMC open-access bucket"),
        }
        rows.append(p)

    dirs = [r["dir"] for r in rows if r["dir"]]
    assert len(dirs) == len(set(dirs)), "two DOIs with one folder"

    # Each finished paper is appended to the log, so a stopped run can resume.
    out.mkdir(parents=True, exist_ok=True)
    log = out / "download.jsonl"
    if not resume:
        log.unlink(missing_ok=True)
    done = {}
    if log.exists():
        with open(log) as f:
            done = {d["doi"]: d for d in map(json.loads, f)}
    ok = {r["doi"] for r in rows if r["dir"] and (out / "raw" / r["dir"]).exists()}
    ok &= {doi for doi, d in done.items() if not d["error"]}

    todo = [r for r in rows if r["dir"] and (r["doi"] not in ok)]
    print(f"{len(rows)} papers in PMC, {len(ok)} done, {len(todo)} to download")
    with ThreadPoolExecutor(threads) as ex, open(log, "a") as f:
        futures = {
            ex.submit(
                download,
                rec=recs[r["pmcid"]],
                raw=out / "raw" / r["dir"],
                disk=out,
                max_bytes=max_mb * 2**20,
                min_free=min_free_gb * 2**30,
            ): r["doi"]
            for r in todo
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="download"):
            done[futures[future]] = {"doi": futures[future], **future.result()}
            f.write(json.dumps(done[futures[future]]) + "\n")
            f.flush()

    metadata = pl.DataFrame([r | done.get(r["doi"], {}) for r in rows], schema=SCHEMA)
    metadata = metadata.sort("dir", "doi", nulls_last=True)
    metadata.write_parquet(out / "metadata.parquet")
    print(metadata.group_by(error=pl.col("error").str.extract(r"^([^:(]+)")).len().sort("len"))
    print(f"Wrote {out / 'metadata.parquet'}")


if __name__ == "__main__":
    auto_cli(main)
