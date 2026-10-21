import polars as pl

# Journal names that the CSD uses for sources that are not journal papers.
NOT_JOURNALS = [
    "CSD Communication",
    "ICSD Communication",
    "Thesis",
    "U.S.Patents",
    "NASA Technical Reports",
    "University of Southampton, Crystal Structure Report Archive",
]


def read_papers(path):
    """Reads the paper of each CSD entry from the full CSD metadata.

    Args:
        path: Path to the full CSD metadata parquet.

    Returns:
        A frame with columns `id`, `journal` (abbreviated name), `journal_full`, `year` and `doi`.
        DOIs are not case-sensitive, so they are stripped and lowercased.
    """
    df = pl.read_parquet(path, columns=["identifier", "publication", "publications"])
    assert df["identifier"].is_unique().all()
    assert (df["publications"].list.len() == 1).all(), "entry with more than one paper"

    pub = pl.col("publication")
    df = df.select(
        id="identifier",
        journal=pub.struct.field("journal").struct.field("name"),
        journal_full=pub.struct.field("journal").struct.field("full_name"),
        year=pub.struct.field("year"),
        doi=pub.struct.field("doi").str.strip_chars().str.to_lowercase(),
    )
    assert df["journal"].null_count() == 0
    return df


def summarize_dois(df):
    """Summarizes how many entries share each DOI.

    Returns:
        A one-row summary of entries per DOI, and the 5 DOIs with the most entries.
    """
    counts = df.drop_nulls("doi").group_by("doi").len("entries")
    summary = counts.select(
        unique_dois=pl.len(),
        single=(pl.col("entries") == 1).sum(),
        mean=pl.col("entries").mean(),
        p90=pl.col("entries").quantile(0.9),
        p99=pl.col("entries").quantile(0.99),
    )
    return summary, counts.top_k(5, by="entries")
