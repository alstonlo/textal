import html
import pathlib
import re
import subprocess

import polars as pl
from jsonargparse import auto_cli

from dataset.csd import nlm_abbrevs
from dataset.paths import DATA_DIR, REPO_ROOT
from viz.crystal import draw_cell

ROWS = {
    "synthesis": "Synthesis",
    "crystallisation": "Crystallization",
    "solid_form": "Solid form",
}

# The look of the website's entry page (`src/viz/static/style.css`), laid out for one wide image.
PAGE = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
  :root {{ --soft: #f5f5f4; --line: #e5e5e3; --ink: #111111; --muted: #6b6b68; --accent: #394287; }}
  body {{ margin: 0; width: 1200px; background: #fff; color: var(--ink);
         font: 15px/1.5 Inter, system-ui, sans-serif; -webkit-font-smoothing: antialiased; }}
  .page {{ display: grid; grid-template-columns: 400px 1fr; gap: 56px; padding: 36px 40px; }}
  .left {{ display: flex; flex-direction: column; height: 0; min-height: 100%; }}
  .tile {{ background: var(--soft); border-radius: 14px; padding: 12px; margin-top: 18px;
           flex: 1; min-height: 0; display: grid; place-items: center; }}
  .tile svg {{ display: block; width: auto; height: 100%; max-width: 100%; }}
  h1 {{ font-size: 24px; margin: 0 0 6px; }}
  .names {{ color: var(--muted); font-size: 13.5px; line-height: 1.5; }}
  .kicker {{ color: var(--muted); font-size: 13.5px; padding-bottom: 10px;
             border-bottom: 1px solid var(--line); }}
  .row {{ display: grid; grid-template-columns: 136px 1fr; gap: 12px; padding: 15px 0;
          border-bottom: 1px solid var(--line); }}
  .row .label {{ color: var(--muted); font-size: 13.5px; }}
  .muted {{ color: var(--muted); }}
</style></head><body><div class="page">
<div class="left"><h1>{name}</h1>
<div class="names">{chemical_name}<br>CSD {refcode}, CCDC {ccdc}</div>
<div class="tile">{cell}</div></div>
<div><div class="kicker">Extracted from {authors}, {journal} ({year})</div>
<div class="row"><span class="label">Match confidence</span><span>{confidence}</span></div>
{rows}
</div></div></body></html>"""


def main(
    refcode: str = "AYUBEC",
    extractions: str = str(DATA_DIR / "extractions.parquet"),
    out: str = str(REPO_ROOT / "assets" / "example.png"),
    chrome: str = "google-chrome",
):
    """Renders the README's example record: the unit cell of one CSD entry beside its record.

    The entry must be in the CSD drug subset (`data/viz/csd_drugs_with_paper.parquet`), which
    supplies the CIF. The page is laid out in HTML and screenshotted with headless Chrome, so
    `chrome` must be installed.
    """
    data = DATA_DIR
    drug = pl.read_parquet(data / "viz" / "csd_drugs_with_paper.parquet")
    drug = drug.filter(pl.col("id") == refcode).row(0, named=True)
    csd = pl.scan_parquet(data / "raw" / "csd_metadata.full.parquet")
    csd = csd.filter(pl.col("identifier") == refcode).collect().row(0, named=True)
    meta = pl.read_parquet(data / "papers" / "metadata.parquet")
    paper = meta.filter(pl.col("doi") == drug["doi"]).row(0, named=True)
    ext = pl.read_parquet(extractions).filter(pl.col("identifier") == refcode).row(0, named=True)
    assert all(ext[f] for f in ROWS), f"{refcode} has an empty paragraph"

    # Authors are "Initials.Surname, ..." in the CSD; the figure names the first author only.
    first = paper["authors"].split(",")[0].split(".")[-1]
    authors = first if ("," not in paper["authors"]) else f"{first} et al."
    journal = nlm_abbrevs(meta, [paper["journal"]], data / "papers" / "raw")[paper["journal"]]
    # The view shows the caffeinium rings face on, beside the hydrogen sulfates and the waters.
    # The drawing is a square with empty bands above and below the cell; cropping the view to the
    # drawn contents makes the tile as wide as the cell and no taller.
    cell = draw_cell(drug["cif"], size=240, view=(-0.52, 0.6))
    ys = [float(y) for y in re.findall(r'(?:[ML]-?[\d.]+ |cy=")(-?[\d.]+)', cell)]
    lo, hi = min(ys) - 8, max(ys) + 8
    cell = re.sub(
        r'viewBox="[^"]*" width="\d+" height="\d+"', f'viewBox="0 {lo:.1f} 240 {hi - lo:.1f}"', cell
    )
    rows = "".join(
        f'<div class="row"><span class="label">{label}</span><span>{html.escape(ext[f])}</span></div>'
        for f, label in ROWS.items()
    )
    page = PAGE.format(
        cell=cell,
        name=html.escape(ext["compound_label"]),
        chemical_name=html.escape(csd["chemical_name"]),
        refcode=refcode,
        ccdc=csd["ccdc_number"],
        authors=html.escape(authors),
        journal=html.escape(journal),
        year=paper["year"],
        confidence=ext["match_confidence"],
        rows=rows,
    )
    out = pathlib.Path(out)
    page_path = out.with_suffix(".html")
    page_path.write_text(page)
    subprocess.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=2",
            "--window-size=1200,436",
            "--virtual-time-budget=5000",
            f"--screenshot={out}",
            page_path.as_uri(),
        ],
        check=True,
        capture_output=True,
    )
    page_path.unlink()
    print(f"{refcode} written to {out}")


if __name__ == "__main__":
    auto_cli(main)
