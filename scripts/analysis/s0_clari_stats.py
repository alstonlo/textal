import pathlib

import polars as pl
from jsonargparse import auto_cli

from dataset.csd import NOT_JOURNALS, read_papers, summarize_dois
from dataset.paths import DATA_DIR

CLARI_DIR = pathlib.Path.home() / "code" / "clari-2"


def main(
    csd: str = str(DATA_DIR / "raw" / "csd_metadata.full.parquet"),
    clari: str = str(CLARI_DIR / "data" / "csd" / "metadata.parquet"),
):
    pl.Config.set_tbl_rows(20)
    pl.Config.set_fmt_str_lengths(60)

    meta = pl.read_parquet(clari, columns=["id", "keep", "split", "error"])
    print(meta.group_by("split", "keep").len("entries").sort("split", "keep"))

    dropped = meta.filter(~pl.col("keep"))
    reasons = dropped.group_by(reason=pl.col("error").struct.field("reason")).len("entries")
    print(reasons.sort("entries", descending=True))

    # Only entries with keep set are used to train, validate or test the model.
    df = meta.filter(pl.col("keep")).join(read_papers(csd), on="id", how="left", validate="1:1")
    assert df["journal"].null_count() == 0, "used entry missing from the CSD metadata"

    aggs = [
        pl.len().alias("entries"),
        (~pl.col("journal").is_in(NOT_JOURNALS)).sum().alias("journal"),
        pl.col("doi").is_not_null().sum().alias("with_doi"),
        pl.col("doi").drop_nulls().n_unique().alias("unique_dois"),
    ]
    splits = df.group_by("split").agg(aggs).sort("entries", descending=True)
    print(pl.concat([splits, df.select(pl.lit("all").alias("split"), *aggs)]))

    summary, top = summarize_dois(df)
    print(summary)
    print(top)

    shared = df.drop_nulls("doi").group_by("doi").agg(pl.col("split").n_unique())
    print(shared.select(dois_in_many_splits=(pl.col("split") > 1).sum()))


if __name__ == "__main__":
    auto_cli(main)
