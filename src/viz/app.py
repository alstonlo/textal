"""TEXtal public website: publisher-only structures, schemes and paper snippets."""

import json
import math
import mimetypes
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlencode

import plotly.graph_objects as go
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from viz import publisher_assets, publisher_text
from viz.publisher_data import DATA, format_journal, licence, load_public_data

HERE = Path(__file__).parent
INK, MUTED, GRID = "#111111", "#6B6B68", "#E5E5E3"
ENTRIES, PAPERS, SNAPSHOT = load_public_data()
BY_ID = {e["id"]: e for e in ENTRIES}
POSITIONS = {e["id"]: i for i, e in enumerate(ENTRIES)}
SEARCH = {
    e["id"]: " ".join(
        [e["id"], e["doi"], e["name"], e["paper"]["title"], e["paper"]["journal"]]
    ).casefold()
    for e in ENTRIES
}
publisher_assets.configure(PAPERS)
publisher_text.configure(PAPERS)
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
    # The margins are fixed, not fitted to the tick labels, so every chart has the same plot area.
    axis = {
        "automargin": False,
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
        margin={"l": 60, "r": 12, "t": 8, "b": 96},
        hoverlabel={"bgcolor": INK, "bordercolor": INK, "font": {"color": "#FFFFFF"}},
        showlegend=False,
        bargap=0.3,
    )
    fig.update_layout(**layout)
    return json.loads(fig.to_json())


# The names of the largest journals on the chart; the tables keep the publisher's names.
JOURNAL_ALIASES = {
    "Acta Crystallographica E": "Acta Cryst. E",
    "Angewandte Chemie (International ed. in English)": "Angew. Chem.",
    "Chemistry (Weinheim an der Bergstrasse, Germany)": "Chem. Eur. J.",
    "Inorganic chemistry": "Inorg. Chem.",
    "Crystal growth & design": "Cryst. Growth Des.",
    "ChemistryOpen": "ChemistryOpen",
    "Advanced science (Weinheim, Baden-Wurttemberg, Germany)": "Adv. Sci.",
}


def bars(counts: list[tuple[str, int]], other: str) -> dict:
    """A vertical bar chart of paper counts, one bar per name; the bar named `other` is grey."""
    labels = [JOURNAL_ALIASES.get(n, n) for n, _ in counts]
    traces = []
    for colour in ("bar-warm", "bar-other"):
        group = [
            (name, n, label)
            for (name, n), label in zip(counts, labels, strict=True)
            if (name == other) == (colour == "bar-other")
        ]
        if group:
            traces.append(
                go.Bar(
                    x=[lab for _, _, lab in group],
                    y=[n for _, n, _ in group],
                    customdata=[name for name, _, _ in group],
                    meta=colour,
                    hovertemplate="%{customdata}: %{y:,}<extra></extra>",
                )
            )
    return figure(
        traces,
        barmode="overlay",
        xaxis={"categoryorder": "array", "categoryarray": labels, "tickangle": -45},
        yaxis={
            "title": {"text": "Papers"},
            "tickformat": "~s",
            "showgrid": True,
            "range": [0, 1.1 * max(n for _, n in counts)],
        },
    )


def load_stats(entries):
    # Every plotted attribute comes from publisher bibliography; only identifier
    # linkage comes from the CSD. Legacy CSD statistics are not opened.
    from collections import Counter

    years = Counter(p["year"] for p in PAPERS.values() if p.get("year"))
    refyears = Counter(e["paper"]["year"] for e in entries if e["paper"].get("year"))
    journals = Counter(p["journal"] for p in PAPERS.values())
    licenses = Counter(licence(p["licenses"]) for p in PAPERS.values())

    # The largest journals and licences, the rest bucketed into one bar.
    top = journals.most_common(6)
    if len(journals) > 6:
        top.append(("Other journals", sum(journals.values()) - sum(n for _, n in top)))
    common = licenses.most_common(5)
    if len(licenses) > 5:
        common.append(("Other", sum(licenses.values()) - sum(n for _, n in common)))
    y = sorted(years)
    line = {
        "mode": "lines+markers",
        "marker": {"size": 5},
        "meta": "bar",
        "hovertemplate": "%{x}: %{y:,}<extra></extra>",
    }
    figures = {
        "coverage": figure(
            [go.Scatter(x=y, y=[refyears.get(v, 0) for v in y], **line)],
            xaxis={"title": {"text": "Publication year"}},
            yaxis={"title": {"text": "Refcode links"}, "rangemode": "tozero"},
        ),
        "pmc_years": figure(
            [go.Scatter(x=y, y=[years[v] for v in y], **line)],
            xaxis={"title": {"text": "Publication year"}},
            yaxis={"title": {"text": "Papers"}, "rangemode": "tozero"},
        ),
        "journals": bars(top, other="Other journals"),
        "licenses": bars(common, other="Other"),
    }
    return {
        "counts": {
            "entries": len(entries),
            "pmc_papers": len(PAPERS),
            "pmc_entries": sum(bool(e["pmcid"]) for e in entries),
        },
        "figures": figures,
    }


STATS = load_stats(ENTRIES)
SNAPSHOT_MTIME = (DATA / "snapshot.json").stat().st_mtime_ns
RELOAD_LOCK = threading.Lock()


def refresh_snapshot():
    global ENTRIES, PAPERS, SNAPSHOT, BY_ID, POSITIONS, SEARCH, SNAPSHOT_MTIME, STATS
    stamp = (DATA / "snapshot.json").stat().st_mtime_ns
    if stamp == SNAPSHOT_MTIME:
        return
    with RELOAD_LOCK:
        if stamp == SNAPSHOT_MTIME:
            return
        entries, papers, snapshot = load_public_data()
        ENTRIES, PAPERS, SNAPSHOT = entries, papers, snapshot
        BY_ID = {e["id"]: e for e in entries}
        POSITIONS = {e["id"]: i for i, e in enumerate(entries)}
        SEARCH = {
            e["id"]: " ".join(
                [e["id"], e["doi"], e["name"], e["paper"]["title"], e["paper"]["journal"]]
            ).casefold()
            for e in entries
        }
        publisher_assets.configure(papers)
        publisher_text.configure(papers)
        STATS = load_stats(entries)
        SNAPSHOT_MTIME = stamp


app = FastAPI(title="TEXtal", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")

# The path the site is served under; a static export for alstonlo.github.io/textal sets "/textal".
templates.env.globals["root"] = ""
templates.env.globals["static_site"] = False
templates.env.globals["thumb_version"] = publisher_assets.THUMB_VERSION
templates.env.globals["has_publisher_cif"] = publisher_assets.has_cif
PAGE_SIZE = 48


def extraction_date(value):
    try:
        return datetime.fromisoformat(str(value)).strftime("%-d %B %Y")
    except ValueError:
        return "date unavailable"


templates.env.filters["extraction_date"] = extraction_date
templates.env.filters["journal_spaces"] = format_journal
templates.env.filters["format_journal"] = format_journal


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
        for r in ("COVPIN01", "AWOHOM", "PODZIU", "XEXYOR", "BAPTUL", "BINBOT")
        if r in BY_ID
    ]
    return templates.TemplateResponse(
        request, "index.html", {"stats": STATS, "hero": hero, "snapshot": SNAPSHOT}
    )


@app.get("/explore", response_class=HTMLResponse)
def explore(
    request: Request,
    q: str = "",
    status: str = "",
    sort: str = "refcode",
    page: int = 1,
    journal: str = "",
    cif: int = 1,
):
    journal = format_journal(journal)
    words = q.casefold().split()
    found = [
        e
        for e in ENTRIES
        if all(w in SEARCH[e["id"]] for w in words)
        and (not status or e["extraction"]["status"] == status)
        and (not journal or e["paper"]["journal"] == journal)
        and (not cif or publisher_assets.has_cif(e["pmcid"]))
    ]
    if sort == "year":
        found.sort(key=lambda e: (e["paper"]["year"] or 0, e["id"]), reverse=True)
    publisher_assets.save_cif_index()
    total = len(found)
    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(1, min(page, pages))

    def link(n):
        return "/explore?" + urlencode(
            {"q": q, "status": status, "sort": sort, "page": n, "journal": journal, "cif": cif}
        )

    return templates.TemplateResponse(
        request,
        "explore.html",
        {
            "entries": found[(page - 1) * PAGE_SIZE : page * PAGE_SIZE],
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
            "journal": journal,
            "cif": cif,
            "journals": SNAPSHOT.get("journals", {}),
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
            "related": [x["id"] for x in ENTRIES if x["paper_id"] == e["paper_id"]],
        },
    )


@app.get("/api/collection")
def collection():
    return SNAPSHOT


@app.get("/api/paper-assets/{pmcid}")
def paper_assets(pmcid: str):
    if pmcid not in publisher_assets.PAPERS:
        raise HTTPException(404, "Unknown publisher paper")
    try:
        return publisher_assets.public_manifest(pmcid)
    except (ValueError, RuntimeError, OSError):
        return JSONResponse(
            {
                "error": "The publisher files are missing from the dataset or do not match their recorded hashes."
            },
            status_code=503,
        )


@app.get("/api/cif-models/{pmcid}/{name}")
def cif_models(pmcid: str, name: str):
    if pmcid not in publisher_assets.PAPERS:
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
        blob, asset = publisher_assets.asset_file(pmcid, name)
    except (ValueError, RuntimeError, OSError):
        raise HTTPException(404, "Unknown publisher asset") from None
    filename = Path(asset["name"]).name
    return Response(
        blob,
        media_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
        headers={
            "Content-Disposition": "inline; filename*=utf-8''" + quote(filename),
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:",
        },
    )


@app.get("/crystal-frame.html", response_class=HTMLResponse)
def crystal_frame(request: Request):
    return templates.TemplateResponse(request, "crystal-frame.html", {})


@app.get("/api/publisher-thumbnail/{pmcid}.svg")
def publisher_thumbnail(pmcid: str):
    if pmcid not in publisher_assets.PAPERS:
        raise HTTPException(404, "Unknown publisher paper")
    try:
        return Response(publisher_assets.thumbnail(pmcid), media_type="image/svg+xml")
    except Exception:  # noqa: BLE001 -- never expose parser internals or private paths
        # A missing publisher preview must never fall back to a CSD depiction.
        return Response(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240"><text x="120" y="116" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#6B6B68">Publisher preview unavailable</text><text x="120" y="135" text-anchor="middle" font-family="sans-serif" font-size="10" fill="#6B6B68">Open paper to inspect saved files</text></svg>',
            media_type="image/svg+xml",
        )


@app.get("/api/paper-text/{pmcid}")
def paper_text(pmcid: str):
    paper = publisher_text.PAPERS.get(pmcid)
    if paper is None:
        raise HTTPException(404, "Publisher text not in the dataset")
    return publisher_text.read(paper)
