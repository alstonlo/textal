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

# CSD journals whose full name matches a different DOAJ journal of the same name.
DOAJ_FALSE_MATCHES = ["Synthesis", "Matter"]


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


def add_doaj(df, path):
    """Adds the fully open-access journals of the DOAJ to the frame of `read_papers`.

    Journals are matched by full title or alternative title.

    Returns:
        The frame with columns `oa_since` (the year the journal started to publish all content
        under an open licence) and `license` (the licences the journal allows), both null for
        journals not in the DOAJ.
    """
    oa_col = "When did the journal start to publish all content using an open license?"
    oa = pl.read_csv(path, infer_schema=False).select(
        journal_title=pl.concat_list(
            norm_title(pl.col("Journal title")), norm_title(pl.col("Alternative title"))
        ),
        oa_since=pl.col(oa_col).cast(pl.Int32),
        license="Journal license",
    )
    oa = (
        oa.explode("journal_title")
        .drop_nulls("journal_title")
        .filter(pl.col("journal_title") != "")
    )
    oa = oa.unique("journal_title", keep="first", maintain_order=True)

    df = df.with_columns(journal_title=norm_title(pl.col("journal_full")))
    df = df.join(oa, on="journal_title", how="left").drop("journal_title")
    false_match = pl.col("journal").is_in(DOAJ_FALSE_MATCHES)
    return df.with_columns(
        oa_since=pl.when(~false_match).then("oa_since"),
        license=pl.when(~false_match).then("license"),
    )


def read_pmc_ids(path):
    """Reads the PMCID of every DOI in PubMed Central (PMC), with DOIs stripped and lowercased."""
    pmc = pl.read_csv(path, columns=["DOI", "PMCID"], infer_schema=False)
    pmc = pmc.select(doi=pl.col("DOI").str.strip_chars().str.to_lowercase(), pmcid="PMCID")
    return pmc.drop_nulls("doi").unique("doi")


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
