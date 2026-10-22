import json
import re
from pathlib import Path

import plotly.graph_objects as go
import polars as pl
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from rdkit import Chem
from rdkit.Chem import rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D

from dataset.csd import NOT_JOURNALS
from dataset.extraction_schema import COLUMNS
from dataset.paths import DATA_DIR
from viz.crystal import ELEMENT_COLOURS, OTHER_COLOUR, draw_cell, draw_crystal, lattice_matrix

HERE = Path(__file__).parent
CSD = DATA_DIR / "raw" / "csd_metadata.full.parquet"
PAPERS = DATA_DIR / "papers"
DRUGS = DATA_DIR / "viz" / "csd_drugs_with_paper.parquet"

# Written by the extraction run, in the schema of `dataset.extraction_schema`. Optional: until it
# exists, the entry pages show the schema as placeholders.
EXTRACTIONS = DATA_DIR / "viz" / "extractions.parquet"

FORMS = ["salt", "cocrystal", "hydrate", "solvate"]
FORM_NAMES = {
    "salt": "Salts",
    "cocrystal": "Cocrystals",
    "hydrate": "Hydrates",
    "solvate": "Solvates",
    "neat": "Neat compounds",
}

CIF_TAGS = {
    "space_group": "_symmetry_space_group_name_H-M",
    "crystal_system": "_symmetry_cell_setting",
    "a": "_cell_length_a",
    "b": "_cell_length_b",
    "c": "_cell_length_c",
    "alpha": "_cell_angle_alpha",
    "beta": "_cell_angle_beta",
    "gamma": "_cell_angle_gamma",
    "cell_volume": "_cell_volume",
    "z": "_cell_formula_units_Z",
}


def rgb(hex_: str) -> tuple[float, float, float]:
    return tuple(int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5))


# 2D depictions in the same element colours as the cell drawings; RDKit wants RGB in [0, 1].
ATOM_COLOURS = {-1: rgb(OTHER_COLOUR), 1: rgb(ELEMENT_COLOURS["C"])}
ATOM_COLOURS |= {
    Chem.GetPeriodicTable().GetAtomicNumber(e): rgb(h) for e, h in ELEMENT_COLOURS.items()
}

INK = "#111111"
MUTED = "#6B6B68"
GRID = "#E5E5E3"


def parse_cif(cif: str) -> dict:
    """Reads the cell and space group of a CSD CIF; uncertainties like `(3)` are dropped."""
    out = {}
    for key, tag in CIF_TAGS.items():
        m = re.search(rf"^{re.escape(tag)}\s+(.+)$", cif, re.MULTILINE)
        out[key] = re.sub(r"\(\d+\)", "", m.group(1)).strip().strip("'") if m else None
    return out


def draw(smiles: str, width: int = 240, height: int = 170) -> str:
    """Draws a molecule as an inline SVG with RDKit; an empty string if the SMILES does not parse."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return ""
    rdDepictor.Compute2DCoords(mol)
    drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    opts = drawer.drawOptions()
    opts.clearBackground = False
    opts.bondLineWidth = 1.6
    opts.padding = 0.08
    opts.updateAtomPalette(ATOM_COLOURS)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    return drawer.GetDrawingText().split("?>", 1)[-1].strip()


def load_entries() -> list[dict]:
    drugs = pl.read_parquet(DRUGS)
    pub = pl.col("publication")
    meta = (
        pl.scan_parquet(CSD)
        .filter(pl.col("identifier").is_in(drugs["id"].unique().implode()))
        .select(
            id="identifier",
            chemical_name="chemical_name",
            formula="formula",
            color="color",
            habit="habit",
            temperature="temperature",
            solvent="solvent",
            r_factor="r_factor",
            density="calculated_density",
            is_organic="is_organic",
            polymorph="polymorph",
            melting_point="melting_point",
            bioactivity="bioactivity",
            disorder="disorder_details",
            remarks="remarks",
            synonyms="synonyms",
            journal=pub.struct.field("journal").struct.field("name"),
            year=pub.struct.field("year"),
            volume=pub.struct.field("volume"),
            first_page=pub.struct.field("first_page"),
        )
        .collect()
    )
    papers = pl.read_parquet(PAPERS / "metadata.parquet").select(
        "doi", "pmcid", "license", "files", title="title", authors="authors"
    )

    # One row per refcode: a refcode can match several DrugBank drugs (e.g. a salt of two drugs).
    df = (
        drugs.group_by("id", maintain_order=True)
        .agg(
            pl.col("ccdc_number", "smiles", "doi", "dir", "cif", *FORMS).first(),
            drugs=pl.col("common_name").unique(maintain_order=True),
            drugbank_ids=pl.col("drugbank_id").unique(maintain_order=True),
        )
        .join(meta, on="id", how="left")
        .join(papers, on="doi", how="left")
        .sort(pl.col("drugs").list.first(), "id")
    )
    assert df["id"].is_unique().all()

    extractions = {}
    if EXTRACTIONS.exists():
        ext = pl.read_parquet(EXTRACTIONS).sort("extracted_at").unique("identifier", keep="last")
        extractions = {row["identifier"]: row for row in ext.to_dicts()}

    entries = df.to_dicts()
    for e in entries:
        e.update(parse_cif(e["cif"]))
        e["name"] = ", ".join(e["drugs"])
        e["forms"] = [f for f in FORMS if e[f]]
        e["svg"] = draw(e["smiles"])
        e["cell"] = draw_cell(e["cif"])
        e["extraction"] = extractions.get(e["id"])
    return entries


def figure(traces: list, **layout) -> dict:
    fig = go.Figure(traces)
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, system-ui, sans-serif", "color": MUTED, "size": 12},
        margin={"l": 8, "r": 8, "t": 8, "b": 8},
        hoverlabel={"bgcolor": INK, "bordercolor": INK, "font": {"color": "#FFFFFF"}},
        legend={"orientation": "h", "x": 0, "y": 1.12, "bgcolor": "rgba(0,0,0,0)"},
        bargap=0.35,
        **layout,
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, showline=False, fixedrange=True)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, showline=False, fixedrange=True)
    return json.loads(fig.to_json())


def load_stats(entries: list[dict]) -> dict:
    pub = pl.col("publication")
    csd = pl.read_parquet(CSD, columns=["identifier", "publication"]).select(
        id="identifier",
        journal=pub.struct.field("journal").struct.field("name"),
        year=pub.struct.field("year"),
        doi=pub.struct.field("doi").str.strip_chars().str.to_lowercase(),
    )
    journal = csd.filter(~pl.col("journal").is_in(NOT_JOURNALS))
    papers = pl.read_parquet(PAPERS / "metadata.parquet")
    parsed = pl.read_parquet(PAPERS / "parsed.parquet").filter(pl.col("error").is_null())

    in_pmc = papers.select(pl.col("refcodes").explode().alias("id")).join(csd, on="id")
    by_year = (
        journal.filter(pl.col("year").is_between(2000, 2025))
        .group_by("year")
        .len("entries")
        .join(in_pmc.group_by("year").len("in_pmc"), on="year", how="left")
        .fill_null(0)
        .sort("year")
    )
    pmc_years = papers.filter(pl.col("year") >= 2005).group_by("year").len().sort("year")
    journals = papers.group_by("journal").len().sort("len", descending=True).head(12)
    licenses = (
        papers.with_columns(pl.col("license").fill_null("Not stated"))
        .group_by("license")
        .len()
        .sort("len", descending=True)
    )
    forms = {f: sum(e[f] for e in entries) for f in FORMS}
    forms["neat"] = sum(not e["forms"] for e in entries)

    counts = {
        "entries": len(csd),
        "journal_entries": len(journal),
        "dois": journal["doi"].n_unique(),
        "pmc_papers": len(papers),
        "pmc_entries": papers["refcodes"].list.len().sum(),
        "parsed": len(parsed),
        "with_supp": (parsed["files"].list.len() > 1).sum(),
        "drug_entries": len(entries),
        "drugs": len({d for e in entries for d in e["drugbank_ids"]}),
        "drug_papers": len({e["doi"] for e in entries}),
        "extracted": sum(e["extraction"] is not None for e in entries),
        "forms": forms,
    }
    hover = "%{x}: %{y:,}<extra></extra>"
    figures = {
        "coverage": figure(
            [
                go.Bar(
                    name="All CSD entries",
                    x=by_year["year"],
                    y=by_year["entries"],
                    meta="bar-light",
                    hovertemplate=hover,
                ),
                go.Bar(
                    name="With an open-access paper in PubMed Central",
                    x=by_year["year"],
                    y=by_year["in_pmc"],
                    meta="bar",
                    hovertemplate=hover,
                ),
            ],
            barmode="overlay",
        ),
        "pmc_years": figure(
            [
                go.Bar(
                    x=pmc_years["year"],
                    y=pmc_years["len"],
                    meta="bar",
                    hovertemplate=hover,
                )
            ]
        ),
        "journals": figure(
            [
                go.Bar(
                    x=journals["len"],
                    y=journals["journal"],
                    orientation="h",
                    meta="bar-warm",
                    hovertemplate="%{y}: %{x:,}<extra></extra>",
                )
            ],
            yaxis={"autorange": "reversed"},
        ),
        "licenses": figure(
            [
                go.Bar(
                    x=licenses["len"],
                    y=licenses["license"],
                    orientation="h",
                    meta="bar-warm",
                    hovertemplate="%{y}: %{x:,}<extra></extra>",
                )
            ],
            yaxis={"autorange": "reversed"},
        ),
    }
    return {"counts": counts, "figures": figures}


ENTRIES = load_entries()
BY_ID = {e["id"]: e for e in ENTRIES}
STATS = load_stats(ENTRIES)
SCHEMA = [c for c in COLUMNS if c.name not in ("identifier", "doi")]

app = FastAPI(title="csd-textal")
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


def featured(entries: list[dict], n: int) -> list[dict]:
    """Entries whose cell drawing reads well at a small size: mid-sized, one drug each."""
    seen, out = set(), []
    for e in sorted(entries, key=lambda e: abs(e["cell"].count("<circle") - 90)):
        if e["drugs"][0] not in seen and e["solvent"]:
            seen.add(e["drugs"][0])
            out.append(e)
        if len(out) == n:
            return out
    return out


HERO = featured(ENTRIES, 6)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    ctx = {
        "stats": STATS,
        "schema": SCHEMA,
        "hero": HERO,
    }
    return templates.TemplateResponse(request, "index.html", ctx)


@app.get("/explore", response_class=HTMLResponse)
def explore(request: Request, form: str = ""):
    ctx = {
        "entries": ENTRIES,
        "counts": STATS["counts"],
        "forms": FORMS,
        "names": FORM_NAMES,
        "form": form,
    }
    return templates.TemplateResponse(request, "explore.html", ctx)


@app.get("/entry/{refcode}", response_class=HTMLResponse)
def entry(request: Request, refcode: str):
    e = BY_ID.get(refcode.upper())
    if e is None:
        raise HTTPException(404, f"No entry {refcode}")
    folder = PAPERS / "parsed" / e["dir"]
    paper = (folder / "paper.md").read_text() if (folder / "paper.md").exists() else ""
    if paper.startswith("---"):
        paper = paper.split("\n---\n", 1)[-1]
    cell = [float(e[k]) for k in ("a", "b", "c", "alpha", "beta", "gamma")]
    ctx = {
        "e": e,
        "viewer": draw_crystal(e["cif"], lattice_matrix(*cell), background="#FFFFFF"),
        "paper": paper,
        "supplementary": sorted(p.name for p in folder.glob("supplementary*")),
        "schema": SCHEMA,
        "counts": STATS["counts"],
    }
    return templates.TemplateResponse(request, "entry.html", ctx)
