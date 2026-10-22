"""Lay out the public dataset for Hugging Face: the website tables and the publisher files.

Only what the papers themselves provide is released: the extracted procedures (the public
website tables, which carry no CSD matching rationale or CSD metadata), and each paper's CIFs
and chemical schemes as supplied by the publisher. The generated thumbnails are left out, and
the files are hard-linked, so the folder costs little extra disk.
"""

import argparse
import json
import os
import shutil
from pathlib import Path

README = """\
# TEXtal data

Crystallisation and synthesis procedures extracted from the open-access papers of CSD entries,
with the CIFs and chemical schemes that the publishers supply with each paper. The CSD
contributes only the refcodes and their link to a paper (DOI); no CSD metadata is included.

- `entries.parquet`: one row per refcode (`id`), with the paper's DOI and PMCID and the
  extracted record as JSON (`extraction_json`).
- `papers.parquet`: one row per paper, with its bibliography, licence, the publisher text
  snippets the extraction quotes (`paragraphs_json`) and its provenance.
- `snapshot.json`: counts per extraction status, collection and journal.
- `files/<PMCID>/`: the publisher's files for that paper, from its PubMed Central OA package:
  `*.cif` and the chemical schemes, plus `manifest.json` with each file's original name,
  SHA-256 and source URL. The files keep the licence of their paper (see `papers.parquet`).
- `demo/`: the same tables restricted to the entries shown on the demo website.

Download everything with `hf download alstonlo/textal-data --repo-type dataset`.
"""


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--assets", type=Path, default=Path("src/viz/assets"))
    p.add_argument("--demo-assets", type=Path, default=Path("data/site-assets"))
    p.add_argument("--cache", type=Path, default=Path("data/publisher-cache"))
    p.add_argument("--output", type=Path, default=Path("data/release"))
    a = p.parse_args()

    out = a.output
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / "README.md").write_text(README)
    for folder, target in ((a.assets, out), (a.demo_assets, out / "demo")):
        if not folder.is_dir():
            continue
        target.mkdir(exist_ok=True)
        for name in ("entries", "papers"):
            shutil.copy(folder / f"publisher_{name}.parquet", target / f"{name}.parquet")
        shutil.copy(folder / "publisher_snapshot.json", target / "snapshot.json")

    counts = {"papers": 0, "files": 0}
    for folder in sorted(a.cache.iterdir()):
        manifest = folder / "manifest.json"
        if not manifest.is_file():
            continue
        data = json.loads(manifest.read_text())
        names = [f["cache_name"] for f in data["cifs"] + data["figures"]]
        if not names:
            continue
        target = out / "files" / folder.name
        target.mkdir(parents=True)
        for name in names:
            os.link(folder / name, target / name)
        os.link(manifest, target / "manifest.json")
        counts["papers"] += 1
        counts["files"] += len(names)
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
