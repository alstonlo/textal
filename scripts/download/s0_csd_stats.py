import polars as pl
from jsonargparse import auto_cli

from dataset.csd import NOT_JOURNALS, read_papers, summarize_dois
from dataset.paths import DATA_DIR


def main(csd: str = str(DATA_DIR / "raw" / "csd_metadata.full.parquet")):
    pl.Config.set_tbl_rows(20)
    pl.Config.set_fmt_str_lengths(60)

    df = read_papers(csd)
    has_doi = pl.col("doi").is_not_null()
    is_journal = ~pl.col("journal").is_in(NOT_JOURNALS)
    print(df.group_by(is_journal=is_journal).agg(entries=pl.len(), with_doi=has_doi.sum()))

    summary, top = summarize_dois(df)
    print(summary)
    print(top)

    # A null prefix is a DOI that does not start with 10.<number>/.
    prefix = pl.col("doi").str.extract(r"^(10\.\d+)/")
    publishers = df.filter(has_doi).group_by(prefix=prefix).len("entries")
    print(publishers.top_k(10, by="entries"))
    print(publishers.filter(pl.col("prefix").is_null()))
    print(df.group_by("journal").len("entries").top_k(10, by="entries"))

    no_doi = df.filter(is_journal & ~has_doi)
    print(
        no_doi.group_by("journal")
        .agg(entries=pl.len(), year=pl.col("year").median())
        .top_k(10, by="entries")
    )

    # DOIs that differ only in letter case are merged by read_papers.
    raw = pl.read_parquet(csd, columns=["publication"]).unnest("publication")
    print(raw.select(raw_unique_dois=pl.col("doi").drop_nulls().n_unique()))

    journals = raw["journal"].struct.unnest()
    print(journals.select(issn=(pl.col("issn") > 0).sum(), eissn=(pl.col("eissn") > 0).sum()))


if __name__ == "__main__":
    auto_cli(main)
