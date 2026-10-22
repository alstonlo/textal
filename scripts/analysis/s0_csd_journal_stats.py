import json
import pathlib
import re
import urllib.request

import polars as pl
from jsonargparse import auto_cli

from dataset.csd import NOT_JOURNALS, add_doaj, read_papers, read_pmc_ids, summarize_dois
from dataset.paths import DATA_DIR

FIGURE = re.compile(r"\.(jpe?g|gif|png|tiff?)$", re.IGNORECASE)


def main(
    csd: str = str(DATA_DIR / "raw" / "csd_metadata.full.parquet"),
    doaj: str = str(DATA_DIR / "raw" / "doaj" / "journals.csv"),
    pmc_ids: str = str(DATA_DIR / "raw" / "pmc" / "PMC-ids.csv.gz"),
    s3: str = str(DATA_DIR / "raw" / "pmc" / "s3.jsonl"),
):
    # The Directory of Open Access Journals (DOAJ) lists every fully open-access journal.
    doaj = pathlib.Path(doaj)
    if not doaj.exists():
        doaj.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve("https://doaj.org/csv", doaj)

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
        dois=pl.col("doi").drop_nulls().n_unique(),
        first=pl.col("year").min(),
        median=pl.col("year").median(),
        last=pl.col("year").max(),
    )
    print(journals.top_k(25, by="dois"))

    # A null prefix is a DOI that does not start with 10.<number>/.
    prefix = pl.col("doi").str.extract(r"^(10\.\d+)/")
    publishers = (
        df.filter(has_doi).group_by(prefix=prefix).agg(dois=pl.col("doi").drop_nulls().n_unique())
    )
    print(publishers.top_k(10, by="dois"))
    print(publishers.filter(pl.col("prefix").is_null()))

    no_doi = df.filter(~has_doi).group_by("journal")
    print(no_doi.agg(entries=pl.len(), median=pl.col("year").median()).top_k(10, by="entries"))

    # Fully open-access journals, matched to the DOAJ by full title or alternative title.
    df = add_doaj(df, doaj)
    is_oa = pl.col("year") >= pl.col("oa_since")
    print(
        df.select(
            doaj_journals=pl.col("journal").filter(pl.col("oa_since").is_not_null()).n_unique(),
            oa_entries=is_oa.sum(),
            oa_dois=pl.col("doi").filter(is_oa).drop_nulls().n_unique(),
        )
    )
    oa_journals = df.filter(is_oa).group_by("journal", "oa_since", "license")
    print(oa_journals.agg(dois=pl.col("doi").drop_nulls().n_unique()).top_k(25, by="dois"))

    # PubMed Central (PMC) has the full text of its articles as XML, so no OCR is needed.
    df = df.join(read_pmc_ids(pmc_ids), on="doi", how="left")
    in_pmc = pl.col("pmcid").is_not_null()
    print(df.select(pmc_entries=in_pmc.sum(), pmc_dois=pl.col("doi").filter(in_pmc).n_unique()))
    pmc_journals = df.group_by("journal").agg(
        dois=pl.col("doi").drop_nulls().n_unique(),
        pmc_dois=pl.col("doi").filter(in_pmc).n_unique(),
    )
    print(pmc_journals.top_k(25, by="pmc_dois"))

    # The PMC open-access bucket holds the PDF, the XML and the supplementary files of an article.
    bucket = []
    with open(s3) as f:
        for r in map(json.loads, f):
            if r["version"] is None:
                continue
            stem = f"{r['pmcid']}.{r['version']}"
            files = r["files"]
            not_text = [f"{stem}.json", f"{stem}.txt"]
            bucket.append(
                {
                    "pmcid": r["pmcid"],
                    "license_code": r["meta"]["license_code"],
                    "pmc_oa": r["meta"]["is_pmc_openaccess"],
                    "manuscript": r["meta"]["is_manuscript"],
                    "has_pdf": f"{stem}.pdf" in files,
                    "pdf_bytes": files.get(f"{stem}.pdf", 0),
                    # Figures are left out, as the download leaves them out.
                    "bytes": sum(
                        s for n, s in files.items() if (n not in not_text) and not FIGURE.search(n)
                    ),
                    "max_bytes": max(files.values()),
                }
            )
    papers = (
        df.drop_nulls("doi")
        .group_by("doi")
        .agg(
            pl.col("pmcid", "journal").first(),
            year=pl.col("year").min(),
            doaj=is_oa.fill_null(False).any(),
        )
    )
    papers = papers.join(pl.DataFrame(bucket), on="pmcid", how="left")
    in_bucket = pl.col("pmc_oa").is_not_null()
    print(papers.select(pmc=in_pmc.sum(), bucket=in_bucket.sum()))
    print(papers.filter(in_pmc & ~in_bucket).group_by("journal").len().top_k(5, by="len"))
    print(papers.group_by("doaj", in_bucket=in_bucket).len().sort("doaj", "in_bucket"))
    print(papers.filter(pl.col("doaj") & ~in_bucket).group_by("journal").len().top_k(8, by="len"))

    licenses = papers.filter(in_bucket).group_by("license_code", "pmc_oa", "manuscript")
    print(
        licenses.agg(
            dois=pl.len(),
            pdf=pl.col("has_pdf").sum(),
            gb=pl.col("bytes").sum() / 1e9,
        ).sort("dois", descending=True)
    )
    print(
        papers.filter(in_bucket).select(
            pdf_gb=pl.col("pdf_bytes").sum() / 1e9,
            gb=pl.col("bytes").sum() / 1e9,
            over_200mb=(pl.col("max_bytes") > 200 * 2**20).sum(),
        )
    )
    acta_e_old = pl.col("journal") == "Acta Crystallogr.,Sect.E:Struct.Rep.Online"
    acta_e_licenses = papers.filter(acta_e_old & in_bucket).group_by("license_code")
    print(acta_e_licenses.agg(dois=pl.len(), first=pl.col("year").min(), last=pl.col("year").max()))

    solvent = pl.read_parquet(csd, columns=["identifier", "solvent"])
    df = df.join(solvent.rename({"identifier": "id"}), on="id", how="left", validate="1:1")

    year = pl.col("year")
    journal = pl.col("journal")
    acta_e = journal.str.starts_with("Acta Crystallogr.,Sect.E")
    subsets = {
        "Acta E 2001-2007": acta_e & (year < 2008),
        "Acta E 2008-2014": acta_e & year.is_between(2008, 2014),
        "Acta E 2015+": acta_e & (year >= 2015),
        "IUCrData": journal == "IUCrData",
        "Z. Kristallogr. NCS 2019+": (journal == "Z.Kristallogr.-New Cryst.Struct.")
        & (year >= 2019),
        "Other journals in PMC": in_pmc & ~acta_e & (journal != "IUCrData"),
    }
    rows = [
        df.filter(expr).select(
            subset=pl.lit(name),
            entries=pl.len(),
            dois=pl.col("doi").drop_nulls().n_unique(),
            pmc_dois=pl.col("doi").filter(in_pmc).n_unique(),
            solvent=pl.col("solvent").is_not_null().mean(),
        )
        for name, expr in subsets.items()
    ]
    print(pl.concat(rows))


if __name__ == "__main__":
    auto_cli(main)
