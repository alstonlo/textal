import pathlib

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from jsonargparse import auto_cli

from dataset.csd import nlm_abbrevs
from dataset.paths import DATA_DIR, REPO_ROOT
from viz import theme

PLOTS = ["journals", "refcodes", "years", "downloads", "chars"]


def main(
    papers: str = str(DATA_DIR / "papers"),
    out: str = str(REPO_ROOT / "results" / "papers" / "plots"),
    top: int = 20,
    first_year: int = 2000,
):
    """Plots the CSD papers in PMC, from `<papers>/metadata.parquet` and `parsed.parquet`.

    Writes `<out>/<plot>.png` for each plot in `PLOTS`: the `top` journals by papers,
    the share of papers with 1, 2, 3 and 4+ CSD entries, the papers per year since `first_year`
    stacked by journal, the licences and files of the downloaded papers, and the length of the
    Markdown of each paper and supplementary file.
    """
    papers, out = pathlib.Path(papers), pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    meta = pl.read_parquet(papers / "metadata.parquet")
    parsed = pl.read_parquet(papers / "parsed.parquet")
    theme.apply()
    n = len(meta)

    journals = meta.group_by("journal").len("papers").sort("papers", "journal", descending=True)
    head, tail = journals.head(top), journals.slice(top)
    abbrevs = nlm_abbrevs(meta, head["journal"], papers / "raw")
    names = [abbrevs[j] for j in head["journal"]] + [f"{len(tail):,} other journals"]
    counts = head["papers"].to_list() + [tail["papers"].sum()]
    fig, ax = plt.subplots(figsize=(theme.WIDTH, 0.18 * len(names) + 0.7), layout="constrained")
    y = np.arange(len(names))
    ax.barh(y, counts, color=([theme.PERIWINKLE[2]] * len(head)) + ["0.7"], height=0.7)
    for i, c in enumerate(counts):
        ax.text(c, i, f" {c:,} ({100 * c / n:.1f}%)", va="center", fontsize=6)
    ax.set_yticks(y, names)
    ax.invert_yaxis()
    ax.set_xlim(right=1.3 * max(counts))
    ax.set_xlabel("Papers")
    ax.grid(axis="x", lw=0.4, alpha=0.5)
    ax.set_title(f"Journals of the {n:,} CSD papers in PMC")
    theme.save(fig, out / "journals")

    # Most papers report one structure, but the few with many hold a large share of the entries.
    k = pl.col("refcodes").list.len()
    per = meta.group_by(k=k.clip(upper_bound=4)).agg(papers=pl.len(), entries=k.sum()).sort("k")
    assert per["k"].to_list() == [1, 2, 3, 4], per
    fig, axes = plt.subplots(1, 2, figsize=(theme.WIDTH, 2.0), layout="constrained")
    for ax, col, label in zip(axes, ["papers", "entries"], ["Papers", "CSD entries"]):
        pct = (100 * per[col] / per[col].sum()).to_numpy()
        ax.bar(["1", "2", "3", "4+"], pct, color=theme.ROSEWOOD, width=0.7)
        for i, v in enumerate(pct):
            ax.text(i, v, f"{v:.1f}%", ha="center", va="bottom", fontsize=6)
        ax.set_ylim(0, 1.15 * pct.max())
        ax.set_xlabel("CSD entries per paper")
        ax.set_ylabel(f"{label} (%)")
        ax.grid(axis="y", lw=0.4, alpha=0.5)
    fig.suptitle(f"{n:,} papers, {per['entries'].sum():,} CSD entries")
    theme.save(fig, out / "refcodes")

    # Papers per year, stacked by the five largest journals. Years before `first_year` have a
    # handful of papers each, so they are left out.
    top5 = journals.head(5)["journal"].to_list()
    group = pl.when(pl.col("journal").is_in(top5)).then("journal").otherwise(pl.lit("Other"))
    by_year = meta.filter(pl.col("year") >= first_year).group_by("year", group=group).len()
    by_year = by_year.pivot("group", index="year", values="len").fill_null(0).sort("year")
    years = by_year["year"].to_numpy()
    fig, ax = plt.subplots(figsize=(theme.WIDTH, 2.4), layout="constrained")
    bottom = np.zeros(len(years))
    for name, color in zip(top5 + ["Other"], theme.PALETTE[:5] + ["0.7"]):
        label = abbrevs.get(name, name)
        ax.bar(years, by_year[name].to_numpy(), bottom=bottom, color=color, width=0.8, label=label)
        bottom += by_year[name].to_numpy()
    ax.set_xlabel("Year")
    ax.set_ylabel("Papers")
    ax.grid(axis="y", lw=0.4, alpha=0.5)
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1), fontsize=6)
    left_out = (meta["year"] < first_year).sum()
    ax.set_title(f"Papers per year ({left_out:,} papers before {first_year} not shown)")
    theme.save(fig, out / "years")

    # The licence and the files of the downloaded papers; papers with an error have no folder.
    ok = meta.filter(pl.col("error").is_null())
    licenses = ok.group_by(license=pl.col("license").fill_null("not in record")).len("papers")
    licenses = licenses.sort("papers", descending=True)
    files = {
        "Full text (XML)": pl.col("files").list.contains("paper.xml"),
        "PDF": pl.col("files").list.contains("paper.pdf"),
        "Supplementary text": pl.col("supplementary_names").list.len() > 0,
        "Author manuscript": pl.col("is_manuscript"),
    }
    shares = [100 * ok.select(has.mean()).item() for has in files.values()]
    shares.append(100 * parsed.select((pl.col("needs_ocr").list.len() > 0).mean()).item())
    labels = list(files) + ["Scanned supplementary"]

    fig, axes = plt.subplots(1, 2, figsize=(theme.WIDTH, 2.6), layout="constrained")
    axes[0].bar(licenses["license"], licenses["papers"], color=theme.PERIWINKLE[2], width=0.7)
    for i, c in enumerate(licenses["papers"]):
        axes[0].text(i, c, f"{c:,}", ha="center", va="bottom", fontsize=6)
    axes[0].set_ylim(top=1.15 * licenses["papers"].max())
    axes[0].set_ylabel("Papers")
    axes[0].set_title("Licence in PMC's record")
    axes[1].bar(labels, shares, color=theme.ROSEWOOD[1], width=0.7)
    for i, v in enumerate(shares):
        axes[1].text(i, v, f"{v:.1f}%", ha="center", va="bottom", fontsize=6)
    axes[1].set_ylim(0, 115)
    axes[1].set_ylabel("Papers (%)")
    axes[1].set_title("Files")
    for ax in axes:
        ax.tick_params(axis="x", rotation=45)
        plt.setp(ax.get_xticklabels(), ha="right", rotation_mode="anchor")
        ax.grid(axis="y", lw=0.4, alpha=0.5)
    fig.suptitle(f"{len(ok):,} downloaded papers")
    theme.save(fig, out / "downloads")

    # Characters of Markdown per file, on a log scale; scans have no text and fall off the left.
    chars = parsed.filter(pl.col("error").is_null()).explode("files", "chars")
    is_paper = pl.col("files") == "paper.md"
    series = [
        ("Paper", is_paper, theme.PERIWINKLE[2]),
        ("Supplementary", ~is_paper, theme.ROSEWOOD[2]),
    ]
    bins = np.logspace(2.5, 5.7, 50)
    fig, ax = plt.subplots(figsize=(theme.WIDTH, 2.2), layout="constrained")
    for label, expr, color in series:
        values = chars.filter(expr)["chars"].to_numpy()
        ax.hist(values, bins=bins, color=color, alpha=0.8, label=f"{label} ({len(values):,} files)")
    ax.set_xscale("log")
    ax.set_xlabel("Characters of Markdown")
    ax.set_ylabel("Files")
    ax.grid(axis="y", lw=0.4, alpha=0.5)
    ax.legend(fontsize=6)
    ax.set_title("Length of the parsed files")
    theme.save(fig, out / "chars")


if __name__ == "__main__":
    auto_cli(main)
