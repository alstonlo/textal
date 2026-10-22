"""TEXtal public website: publisher-only structures, schemes and paper snippets."""

import json
import math
import os
import textwrap
import threading
from pathlib import Path
from urllib.parse import urlencode

import plotly.graph_objects as go
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from viz import publisher_assets
from viz.publisher_data import load_public_data

HERE = Path(__file__).parent
ASSETS = Path(os.environ.get("TEXTAL_ASSETS", str(HERE / "assets")))
INK, MUTED, GRID = "#111111", "#6B6B68", "#E5E5E3"
ENTRIES, PAPERS, SNAPSHOT = load_public_data(ASSETS)
BY_ID = {e["id"]: e for e in ENTRIES}
POSITIONS = {e["id"]: i for i, e in enumerate(ENTRIES)}
SEARCH = {
    e["id"]: " ".join([e["id"], e["doi"], e["paper"]["title"], e["paper"]["journal"]]).casefold()
    for e in ENTRIES
}
publisher_assets.configure(PAPERS)
FIELDS = [
    "crystallisation",
    "synthesis",
    "solid_form",
    "characterisation",
    "purpose_and_properties",
    "other_notes",
]


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
    counts = stats["counts"] | {"acta_entries": len(entries), "acta_papers": len(PAPERS)}

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


STATS = load_stats(ENTRIES)
SNAPSHOT_MTIME = (ASSETS / "publisher_snapshot.json").stat().st_mtime_ns
RELOAD_LOCK = threading.Lock()


def refresh_snapshot():
    global ENTRIES, PAPERS, SNAPSHOT, BY_ID, POSITIONS, SEARCH, SNAPSHOT_MTIME
    stamp = (ASSETS / "publisher_snapshot.json").stat().st_mtime_ns
    if stamp == SNAPSHOT_MTIME:
        return
    with RELOAD_LOCK:
        if stamp == SNAPSHOT_MTIME:
            return
        entries, papers, snapshot = load_public_data(ASSETS)
        ENTRIES, PAPERS, SNAPSHOT = entries, papers, snapshot
        BY_ID = {e["id"]: e for e in entries}
        POSITIONS = {e["id"]: i for i, e in enumerate(entries)}
        SEARCH = {
            e["id"]: " ".join(
                [e["id"], e["doi"], e["paper"]["title"], e["paper"]["journal"]]
            ).casefold()
            for e in entries
        }
        publisher_assets.configure(papers)
        SNAPSHOT_MTIME = stamp


app = FastAPI(title="TEXtal", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


@app.middleware("http")
async def update_public_snapshot(request, call_next):
    # A completed import becomes visible on the next page load; the API never reads
    # in-progress extraction output or legacy CSD tables.
    refresh_snapshot()
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    hero = [
        BY_ID[r]
        for r in ("DUQZAR", "COVPIN01", "SUHKUD", "SUHLAK", "SUHLEO", "WADCUB")
        if r in BY_ID
    ]
    return templates.TemplateResponse(
        request, "index.html", {"stats": STATS, "hero": hero, "snapshot": SNAPSHOT}
    )


@app.get("/explore", response_class=HTMLResponse)
def explore(request: Request, q: str = "", status: str = "", sort: str = "refcode", page: int = 1):
    words = q.casefold().split()
    found = [
        e
        for e in ENTRIES
        if all(w in SEARCH[e["id"]] for w in words)
        and (not status or e["extraction"]["status"] == status)
    ]
    if sort == "year":
        found.sort(key=lambda e: (e["paper"]["year"] or 0, e["id"]), reverse=True)
    total = len(found)
    pages = max(1, math.ceil(total / 48))
    page = max(1, min(page, pages))

    def link(n):
        return "/explore?" + urlencode({"q": q, "status": status, "sort": sort, "page": n})

    return templates.TemplateResponse(
        request,
        "explore.html",
        {
            "entries": found[(page - 1) * 48 : page * 48],
            "total": total,
            "page": page,
            "pages": pages,
            "q": q,
            "status": status,
            "sort": sort,
            "snapshot": SNAPSHOT,
            "previous": link(page - 1) if page > 1 else None,
            "next": link(page + 1) if page < pages else None,
            "statuses": SNAPSHOT["extraction_statuses"],
        },
    )


@app.get("/entry/{refcode}", response_class=HTMLResponse)
def entry(request: Request, refcode: str):
    e = BY_ID.get(refcode.upper())
    if e is None:
        raise HTTPException(404, "Unknown refcode")
    i = POSITIONS[e["id"]]
    return templates.TemplateResponse(
        request,
        "entry.html",
        {
            "e": e,
            "paper": e["paper"],
            "fields": FIELDS,
            "snapshot": SNAPSHOT,
            "previous": ENTRIES[i - 1]["id"] if i else None,
            "next": ENTRIES[i + 1]["id"] if i + 1 < len(ENTRIES) else None,
            "related": [x["id"] for x in ENTRIES if x["pmcid"] == e["pmcid"]],
        },
    )


@app.get("/api/collection")
def collection():
    return SNAPSHOT


@app.get("/api/paper-assets/{pmcid}")
def paper_assets(pmcid: str):
    if pmcid not in PAPERS:
        raise HTTPException(404, "Unknown publisher paper")
    try:
        return publisher_assets.public_manifest(pmcid)
    except (ValueError, RuntimeError, OSError):
        return JSONResponse(
            {
                "error": "Publisher files are unavailable or failed provenance verification. Retry after reconnecting the archive."
            },
            status_code=503,
        )


@app.get("/api/cif-models/{pmcid}/{name}")
def cif_models(pmcid: str, name: str):
    if pmcid not in PAPERS:
        raise HTTPException(404, "Unknown publisher paper")
    try:
        return publisher_assets.cif_models(pmcid, name)
    except Exception:  # noqa: BLE001 -- never expose parser internals or private paths
        return JSONResponse(
            {
                "error": "This publisher CIF could not be parsed or verified. Use its original publisher download."
            },
            status_code=422,
        )


@app.get("/paper-assets/{pmcid}/{name}")
def paper_asset(pmcid: str, name: str):
    try:
        path, asset = publisher_assets.asset_file(pmcid, name)
    except (ValueError, RuntimeError, OSError):
        raise HTTPException(404, "Unknown publisher asset") from None
    return FileResponse(
        path,
        filename=Path(asset["name"]).name,
        content_disposition_type="inline",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:",
        },
    )


@app.get("/crystal-frame.html", response_class=HTMLResponse)
def crystal_frame(request: Request):
    return templates.TemplateResponse(request, "crystal-frame.html", {})


@app.get("/api/publisher-thumbnail/{pmcid}.svg")
def publisher_thumbnail(pmcid: str):
    if pmcid not in PAPERS:
        raise HTTPException(404, "Unknown publisher paper")
    try:
        return FileResponse(publisher_assets.thumbnail(pmcid), media_type="image/svg+xml")
    except Exception:  # noqa: BLE001 -- never expose parser internals or private paths
        # A missing publisher preview must never fall back to a CSD depiction.
        return Response(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240"><text x="120" y="116" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#6B6B68">Publisher preview unavailable</text><text x="120" y="135" text-anchor="middle" font-family="sans-serif" font-size="10" fill="#6B6B68">Open paper to inspect saved files</text></svg>',
            media_type="image/svg+xml",
        )
