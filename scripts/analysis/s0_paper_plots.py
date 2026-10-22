import pathlib
import textwrap

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from jsonargparse import auto_cli

from dataset.csd import JOURNAL_NAMES, merge_acta_e
from dataset.paths import DATA_DIR, REPO_ROOT
from viz import theme

PLOTS = ["years", "downloads"]


def main(
    papers: str = str(DATA_DIR / "papers"),
    out: str = str(REPO_ROOT / "assets"),
    first_year: int = 2008,
):
    """Plots the corpus figures, from `<papers>/metadata.parquet` and `parsed.parquet`.

    Writes `<out>/<plot>.png` for each plot in `PLOTS`: the papers per year since `first_year`
    stacked by journal, and the licences and files of the downloaded papers.

    Args:
        papers: The papers folder, with `metadata.parquet` and `parsed.parquet`.
        out: The folder to write the figures to.
        first_year: The first year of the papers-per-year figure.
    """
    papers, out = pathlib.Path(papers), pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    meta = pl.read_parquet(papers / "metadata.parquet").filter(pl.col("error").is_null())
    parsed = pl.read_parquet(papers / "parsed.parquet")
    theme.apply()

    # Papers per year, stacked by the five largest journals. Years before `first_year` have a
    # handful of papers each, so they are left out.
    all_papers = meta.select(merge_acta_e(pl.col("journal")), "year")
    journals = all_papers.group_by("journal").len("papers")
    top5 = journals.sort("papers", "journal", descending=True).head(5)["journal"].to_list()
    group = pl.when(pl.col("journal").is_in(top5)).then("journal").otherwise(pl.lit("Other"))
    by_year = all_papers.filter(pl.col("year") >= first_year).group_by("year", group=group).len()
    by_year = by_year.pivot("group", index="year", values="len").fill_null(0).sort("year")
    years = by_year["year"].to_numpy()
    fig, ax = plt.subplots(figsize=(theme.WIDTH, 2.4), layout="constrained")
    bottom = np.zeros(len(years))
    for name, color in zip(top5 + ["Other"], theme.PALETTE[:5] + ["0.7"]):
        label = JOURNAL_NAMES[name] if name in top5 else "Other journals"
        label = "\n".join(textwrap.wrap(label, 24))
        ax.bar(years, by_year[name].to_numpy(), bottom=bottom, color=color, width=0.8, label=label)
        bottom += by_year[name].to_numpy()
    ax.set_xticks(years[::2])
    ax.set_xlabel("Publication year")
    ax.set_ylabel("Papers")
    ax.grid(axis="y", lw=0.4, alpha=0.5)
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1), fontsize=6)
    left_out = (meta["year"] < first_year).sum()
    ax.set_title(f"{len(meta):,} papers by year ({left_out:,} before {first_year} not shown)")
    theme.save(fig, out / "years")

    # The licence and the files of the downloaded papers.
    licenses = meta.group_by(license=pl.col("license").fill_null("not in record")).len("papers")
    licenses = licenses.sort("papers", descending=True)
    files = {
        "Full text (XML)": pl.col("files").list.contains("paper.xml"),
        "PDF": pl.col("files").list.contains("paper.pdf"),
        "Supplementary documents": pl.col("supplementary_names").list.len() > 0,
        "Author manuscript": pl.col("is_manuscript"),
    }
    shares = [100 * meta.select(has.mean()).item() for has in files.values()]
    shares.append(100 * parsed.select((pl.col("needs_ocr").list.len() > 0).mean()).item())
    labels = list(files) + ["Scanned supplementary"]

    fig, axes = plt.subplots(1, 2, figsize=(theme.WIDTH, 2.6), layout="constrained")
    axes[0].bar(licenses["license"], licenses["papers"], color=theme.PERIWINKLE[2], width=0.7)
    for i, c in enumerate(licenses["papers"]):
        axes[0].text(i, c, f"{c:,}", ha="center", va="bottom", fontsize=6)
    axes[0].set_ylim(top=1.15 * licenses["papers"].max())
    axes[0].set_ylabel("Papers")
    axes[0].set_title("Licence in the PMC record")
    axes[1].bar(labels, shares, color=theme.ROSEWOOD[1], width=0.7)
    for i, v in enumerate(shares):
        axes[1].text(i, v, f"{v:.1f}%", ha="center", va="bottom", fontsize=6)
    axes[1].set_ylim(0, 115)
    axes[1].set_ylabel("Papers (%)")
    axes[1].set_title("Files available")
    for ax in axes:
        ax.tick_params(axis="x", rotation=45)
        plt.setp(ax.get_xticklabels(), ha="right", rotation_mode="anchor")
        ax.grid(axis="y", lw=0.4, alpha=0.5)
    fig.suptitle(f"{len(meta):,} downloaded papers")
    theme.save(fig, out / "downloads")


if __name__ == "__main__":
    auto_cli(main)
