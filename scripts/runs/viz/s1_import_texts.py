"""Import only allowlisted publisher Markdown records into the private text cache."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    seen = set()
    files = 0
    with gzip.open(a.input, "rt") as source:
        for line in source:
            row = json.loads(line)
            if set(row) != {"doi", "name", "text", "kind"} or row["kind"] not in (
                "main",
                "supplementary",
            ):
                raise ValueError("Unexpected publisher Markdown export")
            doi = row["doi"]
            path = a.output / (hashlib.sha256(doi.encode()).hexdigest() + ".json.gz")
            data = {"doi": doi, "main_text": "", "supplements": []}
            if path.exists():
                with gzip.open(path, "rt") as stream:
                    data = json.load(stream)
            if row["kind"] == "main":
                data["main_text"] = row["text"]
            else:
                data["supplements"] = [x for x in data["supplements"] if x["name"] != row["name"]]
                data["supplements"].append({"name": row["name"], "text": row["text"]})
            temp = path.with_suffix(".gz.part")
            with gzip.open(temp, "wt", compresslevel=3) as out:
                json.dump(data, out, ensure_ascii=False)
            temp.replace(path)
            seen.add(doi)
            files += 1
    print(json.dumps({"papers": len(seen), "markdown_files": files, "cache": str(a.output)}))


if __name__ == "__main__":
    main()
