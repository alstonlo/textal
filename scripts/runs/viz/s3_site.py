"""Render the website into a static folder, for GitHub Pages.

Every page and every API response the pages fetch is written once, so the folder needs no
server. The Explorer is rendered with all entries on one page and searches in the browser.
"""

import argparse
import json
import os
import shutil
from collections import Counter
from pathlib import Path

import polars as pl


def subset_assets(assets, refcodes, output):
    """Writes the website tables restricted to `refcodes` (and their papers) into `output`."""
    entries = pl.read_parquet(assets / "publisher_entries.parquet")
    entries = entries.filter(pl.col("id").is_in(refcodes))
    papers = pl.read_parquet(assets / "publisher_papers.parquet")
    papers = papers.filter(pl.col("paper_id").is_in(entries["paper_id"].implode()))

    snapshot = json.loads((assets / "publisher_snapshot.json").read_text())
    statuses = Counter(json.loads(x)["status"] for x in entries["extraction_json"])
    collections = {}
    for name in ("Acta E", "Other journals"):
        ids = {
            p["paper_id"]
            for p in papers.select("paper_id", "provenance_json").to_dicts()
            if json.loads(p["provenance_json"])["collection"] == name
        }
        collections[name] = {
            "papers": len(ids),
            "refcodes": int(entries["paper_id"].is_in(ids).sum()),
        }
    snapshot.update(
        refcodes=entries.height,
        papers=papers.height,
        extraction_statuses=dict(statuses),
        with_snippets=sum(bool(json.loads(x)) for x in papers["paragraphs_json"]),
        collections=collections,
        journals=dict(Counter(papers["journal"]).most_common()),
    )
    output.mkdir(parents=True, exist_ok=True)
    entries.write_parquet(output / "publisher_entries.parquet")
    papers.write_parquet(output / "publisher_papers.parquet")
    (output / "publisher_snapshot.json").write_text(json.dumps(snapshot, indent=2))
    shutil.copy(assets / "stats.json", output / "stats.json")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default="/textal", help="the path the site is served under")
    p.add_argument("--subset", type=Path, help="a Parquet table whose `id` column lists refcodes")
    p.add_argument("--assets", type=Path, default=Path("src/viz/assets"))
    p.add_argument("--cache", type=Path, default=Path("data/publisher-cache"))
    p.add_argument("--output", type=Path, default=Path("data/site"))
    a = p.parse_args()

    assets = a.assets
    if a.subset:
        assets = a.output.with_name(a.output.name + "-assets")
        refcodes = pl.read_parquet(a.subset)["id"].implode()
        subset_assets(a.assets, refcodes, assets)
    os.environ["TEXTAL_ASSETS"] = str(assets.resolve())
    os.environ["TEXTAL_PUBLISHER_CACHE"] = str(a.cache.resolve())
    os.environ.pop("TEXTAL_ASSET_SSH", None)

    from fastapi.testclient import TestClient

    from viz import app as web

    web.templates.env.globals["root"] = a.root
    web.templates.env.globals["static_site"] = True
    web.PAGE_SIZE = 10**9
    client = TestClient(web.app)

    out = a.output
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(web.HERE / "static", out / "static")
    (out / ".nojekyll").touch()

    def save(url, path, replace=()):
        r = client.get(url)
        if r.status_code != 200:
            return None
        body = r.content
        for old, new in replace:
            body = body.replace(old.encode(), new.encode())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return body

    save("/", out / "index.html")
    save("/explore", out / "explore" / "index.html")
    save("/crystal-frame.html", out / "crystal-frame.html")
    (out / "404.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Not found</title>"
        f'<p>Page not found. <a href="{a.root}/">Back to TEXtal</a>.</p>'
    )
    for e in web.ENTRIES:
        save("/entry/" + e["id"], out / "entry" / e["id"] / "index.html")

    # The JSON the entry pages fetch; its file links are site-absolute and get the root too.
    links = [('"/paper-assets/', f'"{a.root}/paper-assets/')]
    counts = Counter()
    for pmcid in web.publisher_assets.PAPERS:
        body = save("/api/paper-assets/" + pmcid, out / "api" / "paper-assets" / pmcid, links)
        if body is None:
            counts["papers without files"] += 1
            continue
        counts["papers"] += 1
        save(
            f"/api/publisher-thumbnail/{pmcid}.svg",
            out / "api" / "publisher-thumbnail" / f"{pmcid}.svg",
        )
        data = json.loads(body)
        for f in data["cifs"] + data["figures"]:
            name = f["cache_name"]
            save(f"/paper-assets/{pmcid}/{name}", out / "paper-assets" / pmcid / name)
            counts["files"] += 1
        for f in data["cifs"]:
            name = f["cache_name"]
            if save(
                f"/api/cif-models/{pmcid}/{name}", out / "api" / "cif-models" / pmcid / name, links
            ):
                counts["3D models"] += 1
    counts["entries"] = len(web.ENTRIES)
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
