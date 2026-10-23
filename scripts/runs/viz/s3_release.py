"""Pack the publisher files into the dataset folder, next to the tables of `s2_assets.py`.

Each paper of `data/publisher-cache/` becomes one tar (its manifest and the publisher's CIFs and
chemical schemes, as supplied) at the path `viz.publisher_data.package_name` gives, so the folder
is the public dataset as uploaded to Hugging Face (`dataset-card.md` is its README), and what the
website reads. Only what the papers themselves provide is released: the website's tables carry no
CSD matching rationale or CSD metadata, and the generated thumbnails are left out. Papers already
packed are skipped. Upload the folder with
`hf upload alstonlo/textal-data data/textal . --repo-type dataset`.
"""

import argparse
import io
import json
import shutil
import tarfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

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

    a.output.mkdir(parents=True, exist_ok=True)
    shutil.copy(CARD, a.output / "README.md")
    jobs = {}
    counts = {"papers": 0, "files": 0, "skipped": 0}
    for folder in sorted(a.cache.iterdir()):
        if not (folder / "manifest.json").is_file():
            continue
        target = a.output / package_name(folder.name)
        if target.is_file():
            counts["skipped"] += 1
        else:
            jobs[folder] = target
    with ProcessPoolExecutor(a.workers) as pool:
        for n in pool.map(pack, jobs.keys(), jobs.values(), chunksize=64):
            counts["papers"] += 1
            counts["files"] += n
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
