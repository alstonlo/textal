import json
import pathlib

import polars as pl
from jsonargparse import auto_cli

from dataset.csd import NOT_JOURNALS, nlm_abbrevs, read_papers
from dataset.paths import DATA_DIR, REPO_ROOT

FORMS = ["salt", "cocrystal", "hydrate", "solvate"]


def main(
    data: str = str(DATA_DIR),
    out: str = str(REPO_ROOT / "src" / "viz" / "assets"),
):
    """Writes the tables of the website, so that it runs without the CSD metadata or the papers.

    Args:
        data: The data folder, with `raw/`, `papers/` and `viz/`.
        out: The folder to write `entries.parquet`, `extractions.parquet` and `stats.json` to.
    """
    data, out = pathlib.Path(data), pathlib.Path(out)
    papers = data / "papers"
    out.mkdir(parents=True, exist_ok=True)

    ext = pl.read_parquet(data / "viz" / "priority-extractions.parquet")
    assert ext["identifier"].is_unique().all()
    ids = ext["identifier"].implode()
    drugs = pl.read_parquet(data / "viz" / "csd_drugs_with_paper.parquet")
    drugs = drugs.filter(pl.col("id").is_in(ids))
    assert drugs["id"].n_unique() == len(ext), "extraction of a refcode not in the drug subset"

    pub = pl.col("publication")
    csd = (
        pl.scan_parquet(data / "raw" / "csd_metadata.full.parquet")
        .filter(pl.col("identifier").is_in(ids))
        .select(
            id="identifier",
            chemical_name="chemical_name",
            formula="formula",
            color="color",
            habit="habit",
            temperature="temperature",
            solvent="solvent",
            r_factor="r_factor",
            density="calculated_density",
            is_organic="is_organic",
            polymorph="polymorph",
            melting_point="melting_point",
            bioactivity="bioactivity",
            disorder="disorder_details",
            remarks="remarks",
            synonyms="synonyms",
            journal=pub.struct.field("journal").struct.field("name"),
            year=pub.struct.field("year"),
            volume=pub.struct.field("volume"),
            first_page=pub.struct.field("first_page"),
        )
        .collect()
    )
    assert csd["journal"].str.starts_with("Acta Crystallogr.,Sect.E").all()
    meta = pl.read_parquet(papers / "metadata.parquet")

    # One row per refcode: a refcode can match several DrugBank drugs (e.g. a salt of two drugs).
    df = (
        drugs.group_by("id", maintain_order=True)
        .agg(
            pl.col("ccdc_number", "smiles", "doi", "dir", "cif", *FORMS).first(),
            drugs=pl.col("common_name").unique(maintain_order=True),
            drugbank_ids=pl.col("drugbank_id").unique(maintain_order=True),
        )
        .join(csd, on="id", how="left")
        .join(meta.select("doi", "pmcid", "license", "title", "authors"), on="doi", how="left")
        .sort(pl.col("drugs").list.first(), "id")
    )
    assert df["pmcid"].null_count() == 0

    # Only CC BY text is shared; the rest are Acta E papers of 2008 under the IUCr's own terms.
    texts = [
        (papers / "parsed" / d / "paper.md").read_text().split("\n---\n", 1)[1]
        if (lic == "CC BY")
        else None
        for d, lic in zip(df["dir"], df["license"])
    ]
    df = df.drop("dir").with_columns(paper=pl.Series(texts, dtype=pl.String))
    df.write_parquet(out / "entries.parquet")
    ext.write_parquet(out / "extractions.parquet")

    # The corpus statistics of the landing page, which need the whole CSD and every paper.
    entries = read_papers(data / "raw" / "csd_metadata.full.parquet")
    journal = entries.filter(~pl.col("journal").is_in(NOT_JOURNALS))
    in_pmc = meta.select(pl.col("refcodes").explode().alias("id")).join(entries, on="id")
    by_year = (
        journal.filter(pl.col("year").is_between(2000, 2025))
        .group_by("year")
        .len("entries")
        .join(in_pmc.group_by("year").len("in_pmc"), on="year", how="left")
        .fill_null(0)
        .sort("year")
    )
    pmc_years = meta.filter(pl.col("year") >= 2005).group_by("year").len().sort("year")
    journals = meta.group_by("journal").len().sort("len", descending=True).head(12)
    abbrevs = nlm_abbrevs(meta, journals["journal"], papers / "raw")
    journals = journals.with_columns(pl.col("journal").replace_strict(abbrevs))
    licenses = (
        meta.with_columns(pl.col("license").fill_null("Not stated"))
        .group_by("license")
        .len()
        .sort("len", descending=True)
    )
    stats = {
        "counts": {
            "entries": len(entries),
            "pmc_papers": len(meta),
            "pmc_entries": meta["refcodes"].list.len().sum(),
        },
        "coverage": by_year.to_dict(as_series=False),
        "pmc_years": pmc_years.to_dict(as_series=False),
        "journals": journals.to_dict(as_series=False),
        "licenses": licenses.to_dict(as_series=False),
    }
    (out / "stats.json").write_text(json.dumps(stats, indent=1) + "\n")
    print(f"{len(df)} entries of {df['doi'].n_unique()} papers written to {out}")


if __name__ == "__main__":
    auto_cli(main)
