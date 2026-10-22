import re
from collections import Counter

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

# The NLM title abbreviation of a paper's journal, as in https://www.ncbi.nlm.nih.gov/nlmcatalog/.
NLM_TA = re.compile(r'<journal-id journal-id-type="nlm-ta">([^<]+)<')

# Acta Crystallographica Section E was renamed in 2014 (Structure Reports Online, then
# Crystallographic Communications), so the CSD lists it under two names.
ACTA_E = "Acta Crystallogr E"


def merge_acta_e(journal):
    """Replaces both CSD names of Acta Crystallographica Section E with `ACTA_E`."""
    is_acta_e = journal.str.starts_with("Acta Crystallogr.,Sect.E")
    return pl.when(is_acta_e).then(pl.lit(ACTA_E)).otherwise(journal)


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


def nlm_abbrevs(meta, journals, raw, sample=25):
    """Maps CSD journal names to their NLM title abbreviations, read from the papers' PMC XML.

    CSD journal names are terse (e.g. `J.Am.Chem.Soc.`). A few papers carry another journal's tag,
    so each journal takes the most common tag among `sample` of its papers.

    Args:
        meta: The papers, with columns `journal`, `dir` and `files` (`papers/metadata.parquet`).
        journals: The CSD journal names to map.
        raw: The folder of the downloaded papers (`papers/raw/`).
        sample: How many papers of each journal to read.

    Returns:
        A dict from CSD name to NLM abbreviation, or to the CSD name when no paper has the tag.
    """
    out = {}
    for name in journals:
        has_xml = (pl.col("journal") == name) & pl.col("files").list.contains("paper.xml")
        dirs = meta.filter(has_xml)["dir"]
        tags = [NLM_TA.search((raw / d / "paper.xml").read_text()) for d in dirs[:sample]]
        tags = [m.group(1) for m in tags if m]
        out[name] = Counter(tags).most_common(1)[0][0] if tags else name
    assert len(set(out.values())) == len(out), out
    return out
