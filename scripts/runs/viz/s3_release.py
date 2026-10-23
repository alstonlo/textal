"""Pack the publisher files into the dataset folder, next to the tables of `s2_assets.py`.

Each paper of the tables with `has_publisher_package` (set only for a Creative Commons licence)
becomes one tar of `data/publisher-cache/` (its manifest and the publisher's CIFs and chemical
schemes, as supplied) at the path `viz.publisher_data.package_name` gives, so the folder is the
public dataset as uploaded to Hugging Face (`dataset-card.md` is its README), and what the website
reads. The generated thumbnails are left out. Papers already packed are skipped, and the packages
of papers no longer released are removed. The folders `files/` and `texts/` (tens of thousands of
small files) are then bundled into `files.tar` and `texts.tar`, which are uploaded in their place:
`hf upload alstonlo/textal-data data/textal . --repo-type dataset --exclude "files/*"
--exclude "texts/*" --delete "*"`, which also deletes the remote files that are no longer in it.
The bundles are not gzipped, since the files in them already are.
"""

import argparse
import io
import json
import shutil
import tarfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import polars as pl

from viz.publisher_data import package_name

CARD = Path(__file__).with_name("dataset-card.md")


def pack(folder, target):
    """Writes the paper's package to `target`; returns the number of files in it."""
    data = json.loads((folder / "manifest.json").read_text())
    names = [f["cache_name"] for f in data["cifs"] + data["figures"]]
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz", compresslevel=6) as tar:
        for name in ["manifest.json"] + names:
            tar.add(folder / name, arcname=name)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".part")
    temp.write_bytes(buffer.getvalue())
    temp.replace(target)
    return len(names)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", type=Path, default=Path("data/publisher-cache"))
    p.add_argument("--output", type=Path, default=Path("data/textal"))
    p.add_argument("--workers", type=int, default=32)
    a = p.parse_args()

    shutil.copy(CARD, a.output / "README.md")
    papers = pl.read_parquet(a.output / "papers.parquet", columns=["pmcid", "provenance_json"])
    released = {
        a.output / package_name(pmcid)
        for pmcid, provenance in papers.iter_rows()
        if json.loads(provenance)["has_publisher_package"]
    }
    counts = {"papers": 0, "files": 0, "skipped": 0, "removed": 0}
    for path in (a.output / "files").glob("*/*.tar.gz"):
        if path not in released:
            path.unlink()
            counts["removed"] += 1
    jobs = {}
    for target in sorted(released):
        if target.is_file():
            counts["skipped"] += 1
        else:
            jobs[a.cache / target.name.removesuffix(".tar.gz")] = target
    with ProcessPoolExecutor(a.workers) as pool:
        for n in pool.map(pack, jobs.keys(), jobs.values(), chunksize=64):
            counts["papers"] += 1
            counts["files"] += n

    for name in ("files", "texts"):
        target = a.output / (name + ".tar")
        temp = target.with_name(target.name + ".part")
        with tarfile.open(temp, mode="w") as tar:
            for path in sorted((a.output / name).glob("*/*.gz")):
                tar.add(path, arcname=path.relative_to(a.output).as_posix())
        temp.replace(target)
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
