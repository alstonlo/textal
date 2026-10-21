import polars as pl
from jsonargparse import auto_cli

from dataset.csd import NOT_JOURNALS, read_papers, summarize_dois
from dataset.paths import DATA_DIR

# CSD journals whose full name matches a different DOAJ journal of the same name.
DOAJ_FALSE_MATCHES = ["Synthesis", "Matter"]


def norm_title(col):
    return (
        col.str.normalize("NFKD")
        .str.replace_all(r"\p{M}", "")
        .str.to_lowercase()
        .str.replace_all("&", " and ")
        .str.replace_all(r"[^a-z0-9]+", " ")
        .str.replace_all(r"^the ", "")
        .str.strip_chars()
    )


def main(
    csd: str = str(DATA_DIR / "raw" / "csd_metadata.full.parquet"),
    doaj: str = str(DATA_DIR / "raw" / "doaj" / "journals.csv"),
):
    pl.Config.set_tbl_rows(30)
    pl.Config.set_fmt_str_lengths(60)
    pl.Config.set_tbl_width_chars(200)

    df = read_papers(csd)
    print(df.select(not_journal=pl.col("journal").is_in(NOT_JOURNALS).sum()))

    df = df.filter(~pl.col("journal").is_in(NOT_JOURNALS))
    has_doi = pl.col("doi").is_not_null()
    print(
        df.select(
            entries=pl.len(),
            journals=pl.col("journal").n_unique(),
            with_doi=has_doi.sum(),
        )
    )

    summary, top = summarize_dois(df)
    print(summary)
    print(top)

    journals = df.group_by("journal").agg(
        entries=pl.len(),
        dois=pl.col("doi").n_unique(),
        first=pl.col("year").min(),
        median=pl.col("year").median(),
        last=pl.col("year").max(),
    )
    print(journals.top_k(25, by="dois"))

    # A null prefix is a DOI that does not start with 10.<number>/.
    prefix = pl.col("doi").str.extract(r"^(10\.\d+)/")
    publishers = df.filter(has_doi).group_by(prefix=prefix).agg(dois=pl.col("doi").n_unique())
    print(publishers.top_k(10, by="dois"))
    print(publishers.filter(pl.col("prefix").is_null()))

    no_doi = df.filter(~has_doi).group_by("journal")
    print(no_doi.agg(entries=pl.len(), median=pl.col("year").median()).top_k(10, by="entries"))

    # Fully open-access journals, matched to the DOAJ by full title or alternative title.
    oa_col = "When did the journal start to publish all content using an open license?"
    oa = pl.read_csv(doaj, infer_schema=False).select(
        title=pl.concat_list(
            norm_title(pl.col("Journal title")), norm_title(pl.col("Alternative title"))
        ),
        oa_since=pl.col(oa_col).cast(pl.Int32),
        license="Journal license",
    )
    oa = oa.explode("title").drop_nulls("title").filter(pl.col("title") != "")
    oa = oa.unique("title", keep="first", maintain_order=True)

    df = df.with_columns(title=norm_title(pl.col("journal_full"))).join(oa, on="title", how="left")
    df = df.with_columns(
        oa_since=pl.when(~pl.col("journal").is_in(DOAJ_FALSE_MATCHES)).then("oa_since")
    )
    is_oa = pl.col("year") >= pl.col("oa_since")
    print(
        df.select(
            doaj_journals=pl.col("journal").filter(pl.col("oa_since").is_not_null()).n_unique(),
            oa_entries=is_oa.sum(),
            oa_dois=pl.col("doi").filter(is_oa).n_unique(),
        )
    )
    oa_journals = df.filter(is_oa).group_by("journal", "oa_since", "license")
    print(oa_journals.agg(dois=pl.col("doi").n_unique()).top_k(25, by="dois"))


if __name__ == "__main__":
    auto_cli(main)
