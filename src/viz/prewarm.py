"""Prepare the availability index and first-page previews when building the Space."""
import logging


def main():
    from viz import publisher_assets
    from viz.app import ENTRIES, PAGE_SIZE

    papers = list(dict.fromkeys(
        e["pmcid"] for e in ENTRIES if publisher_assets.has_cif(e["pmcid"])
    ))[:PAGE_SIZE]
    for pmcid in papers:
        try:
            publisher_assets.thumbnail(pmcid)
        except Exception:
            logging.exception("Could not pre-render publisher preview for %s", pmcid)
    publisher_assets.save_cif_index()


if __name__ == "__main__":
    main()
