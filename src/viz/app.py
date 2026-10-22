import json
import re
import textwrap
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

from dataset.extraction_schema import COLUMNS
from viz.crystal import ELEMENT_COLOURS, OTHER_COLOUR, draw_cell, draw_crystal

HERE = Path(__file__).parent
# Written by `scripts/runs/viz/s0_assets.py`, so the website needs neither the CSD nor the papers.
ASSETS = HERE / "assets"

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
    ext = pl.read_parquet(ASSETS / "extractions.parquet")
    extractions = {row["identifier"]: row for row in ext.to_dicts()}
    entries = pl.read_parquet(ASSETS / "entries.parquet").to_dicts()
    for e in entries:
        e.update(parse_cif(e["cif"]))
        e["name"] = ", ".join(e["drugs"])
        e["forms"] = [f for f in FORMS if e[f]]
        e["svg"] = draw(e["smiles"])
        e["cell"] = draw_cell(e["cif"])
        e["extraction"] = extractions[e["id"]]
    return entries


def figure(traces: list, **layout) -> dict:
    fig = go.Figure(traces)

    # The axes of `theme.apply()`: a thin black frame and outward ticks. A value axis turns on
    # its faint grid through `layout`, which is applied last so that it wins over the defaults.
    axis = {
        "showgrid": False,
        "gridcolor": GRID,
        "zeroline": False,
        "showline": True,
        "linecolor": INK,
        "linewidth": 1.25,
        "mirror": True,
        "ticks": "outside",
        "ticklen": 5,
        "tickwidth": 1,
        "tickcolor": INK,
        "ticklabelstandoff": 4,
        "tickfont": {"color": INK, "size": 11},
        "title": {"font": {"color": INK, "size": 12}, "standoff": 8},
        "fixedrange": True,
    }
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, system-ui, sans-serif", "color": MUTED, "size": 12},
        margin={"l": 4, "r": 12, "t": 8, "b": 4},
        hoverlabel={"bgcolor": INK, "bordercolor": INK, "font": {"color": "#FFFFFF"}},
        showlegend=False,
        bargap=0.3,
    )
    fig.update_layout(**layout)
    return json.loads(fig.to_json())


def load_stats(entries: list[dict]) -> dict:
    stats = json.loads((ASSETS / "stats.json").read_text())
    by_year, pmc_years = stats["coverage"], stats["pmc_years"]
    journals, licenses = stats["journals"], stats["licenses"]
    forms = {f: sum(e[f] for e in entries) for f in FORMS}
    forms["neat"] = sum(not e["forms"] for e in entries)

    counts = stats["counts"] | {
        "drug_entries": len(entries),
        "drugs": len({d for e in entries for d in e["drugbank_ids"]}),
        "drug_papers": len({e["doi"] for e in entries}),
        "forms": forms,
    }

    # Matplotlib-like margins: a year of room on both sides of the year axes, 8% above the tallest
    # bar, and 30% right of the longest horizontal bar for its count.
    first, last = by_year["year"][0], by_year["year"][-1]
    hover = "%{x}: %{y:,}<extra></extra>"
    tips = {
        "orientation": "h",
        "texttemplate": "\u2002%{x:,}",
        "textposition": "outside",
        "textfont": {"color": INK, "size": 10},
        "cliponaxis": False,
        "hovertemplate": "%{customdata}: %{x:,}<extra></extra>",
    }
    papers = {"title": {"text": "Papers"}, "tickformat": "~s", "showgrid": True}

    # Long journal names wrap onto two lines, so that the bars keep their width on a phone.
    names = ["<br>".join(textwrap.wrap(j, 24)) for j in journals["journal"]]
    other = counts["pmc_papers"] - sum(journals["len"])
    assert other >= 0, other

    figures = {
        "coverage": figure(
            [
                go.Bar(
                    x=by_year["year"], y=by_year["entries"], meta="bar-light", hovertemplate=hover
                ),
                go.Bar(x=by_year["year"], y=by_year["in_pmc"], meta="bar", hovertemplate=hover),
            ],
            barmode="overlay",
            xaxis={"range": [first - 1, last + 1], "dtick": 5},
            yaxis=papers
            | {"title": {"text": "CSD entries"}, "range": [0, 1.08 * max(by_year["entries"])]},
        ),
        "pmc_years": figure(
            [go.Bar(x=pmc_years["year"], y=pmc_years["len"], meta="bar", hovertemplate=hover)],
            xaxis={"range": [pmc_years["year"][0] - 1, last + 1], "dtick": 5},
            yaxis=papers | {"range": [0, 1.08 * max(pmc_years["len"])]},
        ),
        "journals": figure(
            [
                go.Bar(
                    **tips,
                    x=journals["len"],
                    y=names,
                    customdata=journals["journal"],
                    meta="bar-warm",
                ),
                go.Bar(
                    **tips,
                    x=[other],
                    y=["Other journals"],
                    customdata=["Other journals"],
                    meta="bar-other",
                ),
            ],
            barmode="overlay",
            xaxis=papers | {"range": [0, 1.3 * max(journals["len"] + [other])]},
            yaxis={"autorange": "reversed"},
        ),
        "licenses": figure(
            [
                go.Bar(
                    **tips,
                    x=licenses["len"],
                    y=licenses["license"],
                    customdata=licenses["license"],
                    meta="bar-warm",
                )
            ],
            xaxis=papers | {"range": [0, 1.3 * max(licenses["len"])]},
            yaxis={"autorange": "reversed"},
            bargap=0.5,
        ),
    }
    return {"counts": counts, "figures": figures}


ENTRIES = load_entries()
BY_ID = {e["id"]: e for e in ENTRIES}
STATS = load_stats(ENTRIES)

# The paragraphs of a record on the entry page, crystallisation first since it is what the dataset
# is for. The summary leads the record, so it is not among them.
FIELDS = [
    "crystallisation",
    "synthesis",
    "solid_form",
    "characterisation",
    "purpose_and_properties",
    "other_notes",
]
assert set(FIELDS) <= {c.name for c in COLUMNS}, FIELDS

app = FastAPI(title="TEXtal")
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
    ctx = {"stats": STATS, "hero": HERO}
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
    ctx = {
        "e": e,
        "viewer": draw_crystal(e["cif"], background="#FFFFFF"),
        "paper": e["paper"] or "",
        "fields": FIELDS,
        "counts": STATS["counts"],
    }
    return templates.TemplateResponse(request, "entry.html", ctx)
