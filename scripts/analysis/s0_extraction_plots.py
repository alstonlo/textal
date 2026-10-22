import pathlib
import textwrap

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from jsonargparse import auto_cli

from dataset.csd import JOURNAL_NAMES, merge_acta_e
from dataset.paths import DATA_DIR, REPO_ROOT
from viz import theme

# The paragraphs of a record, named as the README names them (the columns spell them the British
# way). The `summary` and `other_notes` columns are not topics of the paper, so they are left out.
FIELDS = {
    "synthesis": "synthesis",
    "crystallisation": "crystallization",
    "characterisation": "characterization",
    "solid_form": "solid form",
    "purpose_and_properties": "purpose and\nproperties",
}

# The two extraction runs, keyed by prompt version.
RUNS = {
    "v2-actae-anchored-1": "Acta E",
    "v2": "Other journals",
}


def main(
    extractions: str = str(DATA_DIR / "extractions.parquet"),
    papers: str = str(DATA_DIR / "papers"),
    csd: str = str(DATA_DIR / "raw" / "csd_metadata.full.parquet"),
    out: str = str(REPO_ROOT / "assets"),
    top: int = 10,
):
    """Plots the figure of the README, `<out>/extraction.png`, and prints its statistics.

    The figure has three panels: the papers of the `top` journals split into extracted and not
    yet extracted, and the records of each run (filled paragraphs and match confidence).
    """
    papers, out = pathlib.Path(papers), pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    pl.Config.set_tbl_rows(30)
    ext = pl.read_parquet(extractions)
    meta = pl.read_parquet(papers / "metadata.parquet").filter(pl.col("error").is_null())
    assert ext.select(pl.struct("identifier", "doi").is_unique().all()).item()
    theme.apply()

    # Which papers of the corpus were extracted. Each paper went to exactly one run.
    runs = ext.group_by("doi").agg(pl.col("prompt_version").first().alias("run"))
    assert (
        ext.group_by("doi").agg(pl.n_unique("prompt_version")).select(pl.last().max()).item() == 1
    )
    assert ext["doi"].is_in(meta["doi"].implode()).all(), "extracted papers outside the corpus"
    done = meta.join(runs, on="doi", how="left").with_columns(pl.col("run").is_not_null())
    print(
        done.select(
            papers=pl.len(),
            extracted=pl.col("run").sum(),
            entries=pl.col("refcodes").list.len().sum(),
            extracted_entries=pl.col("refcodes").list.len().filter(pl.col("run")).sum(),
        )
    )
    print(ext.group_by("prompt_version", "model").agg(papers=pl.n_unique("doi"), rows=pl.len()))
    print(ext.group_by("prompt_version", "extraction_status").len().sort(pl.all()))

    # Papers of the largest journals: extracted versus not yet extracted.
    journals = done.group_by(journal=merge_acta_e(pl.col("journal"))).agg(
        pl.len().alias("papers"), pl.col("run").sum()
    )
    journals = journals.sort("papers", "journal", descending=True).head(top)
    labels = ["\n".join(textwrap.wrap(JOURNAL_NAMES[j], 26)) for j in journals["journal"]][::-1]
    total, extracted = journals["papers"].to_numpy()[::-1], journals["run"].to_numpy()[::-1]

    # The records of each run: which paragraphs were filled, and how sure the matches are.
    ok = ext.filter(pl.col("extraction_status") == "ok")
    filled = ok.group_by("prompt_version").agg(pl.col(*FIELDS).is_not_null().mean() * 100)
    confidence = (
        ext.group_by("prompt_version", "match_confidence")
        .len()
        .with_columns(pl.col("len") / pl.col("len").sum().over("prompt_version") * 100)
        .pivot("match_confidence", index="prompt_version", values="len")
        .fill_null(0)
    )
    print(filled, confidence)

    fig, axes = plt.subplot_mosaic(
        [["journals", "journals"], ["filled", "confidence"]],
        figsize=(theme.WIDTH, 5.0),
        width_ratios=[3, 1],
        height_ratios=[1.3, 1],
        layout="constrained",
    )
    fig.get_layout_engine().set(wspace=0.08, hspace=0.03)
    ax = axes["journals"]
    bars = {"height": 0.7, "linewidth": 0}
    ax.barh(labels, extracted, color=theme.PERIWINKLE[2], label="Extracted", **bars)
    ax.barh(
        labels, total - extracted, left=extracted, color="0.8", label="Not yet extracted", **bars
    )
    for i, (n, k) in enumerate(zip(total, extracted)):
        ax.text(n, i, f" {100 * k / n:.0f}%", va="center", fontsize=6)
    ax.set_xlim(right=1.12 * total.max())
    ax.set_xlabel("Papers")
    ax.grid(axis="x", lw=0.4, alpha=0.5)
    ax.legend(loc="lower right")
    n_done, n_all = done["run"].sum(), len(done)
    ax.set_title(f"(a) Extracted papers: {n_done:,} of {n_all:,} ({100 * n_done / n_all:.0f}%)")

    ax = axes["filled"]
    x = np.arange(len(FIELDS))
    for i, (run, label) in enumerate(RUNS.items()):
        row = filled.row(by_predicate=pl.col("prompt_version") == run, named=True)
        shares = [row[f] for f in FIELDS]
        ax.bar(x + 0.4 * i - 0.2, shares, width=0.4, color=theme.PALETTE[i], lw=0, label=label)
    ax.set_xticks(x, list(FIELDS.values()))
    ax.set_ylim(0, 135)
    ax.set_yticks(range(0, 101, 20))
    ax.set_ylabel("Records (%)")
    ax.set_title(f"(b) Filled paragraphs of the {len(ext):,} records")
    ax.legend(fontsize=6, loc="upper right")

    ax = axes["confidence"]
    bottom = np.zeros(len(RUNS))
    levels = {"high": theme.PERIWINKLE[3], "medium": theme.PERIWINKLE[1], "low": theme.BUTTER[0]}
    levels["null"] = "0.8"
    for level, color in levels.items():
        shares = np.array(
            [confidence.filter(pl.col("prompt_version") == r)[level].item() for r in RUNS]
        )
        name = "no record" if level == "null" else level
        runs = ["\n".join(textwrap.wrap(r, 8)) for r in RUNS.values()]
        ax.bar(runs, shares, bottom=bottom, color=color, width=0.7, lw=0, label=name)
        bottom += shares
    ax.set_ylim(0, 100)
    ax.set_ylabel("Records (%)")
    ax.set_title("(c) Match\nconfidence")
    ax.legend(fontsize=6, loc="upper left", bbox_to_anchor=(1, 1))
    axes["filled"].tick_params(axis="x", rotation=45)
    plt.setp(axes["filled"].get_xticklabels(), ha="right", rotation_mode="anchor")
    for ax in (axes["filled"], axes["confidence"]):
        ax.grid(axis="y", lw=0.4, alpha=0.5)
    theme.save(fig, out / "extraction")

    # How often the crystallisation paragraph fills a gap in the CSD, whose `solvent` field is
    # the only crystallisation condition it records.
    solvent = pl.scan_parquet(csd).select("identifier", "solvent").collect()
    cryst = ok.join(solvent, on="identifier", how="left").drop_nulls("crystallisation")
    print(
        cryst.select(
            with_crystallisation=pl.len(),
            csd_solvent_empty=pl.col("solvent").is_null().sum(),
            words=pl.col("crystallisation").str.split(" ").list.len().median(),
        )
    )


if __name__ == "__main__":
    auto_cli(main)
