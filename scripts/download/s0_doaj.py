import pathlib
import urllib.request

from jsonargparse import auto_cli

from dataset.paths import DATA_DIR


def main(out: str = str(DATA_DIR / "raw" / "doaj" / "journals.csv")):
    out = pathlib.Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # The Directory of Open Access Journals (DOAJ) lists every fully open-access journal.
    urllib.request.urlretrieve("https://doaj.org/csv", out)
    print(f"Wrote {out}")


if __name__ == "__main__":
    auto_cli(main)
