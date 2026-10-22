"""Stream the extraction over the PMC corpus in papers/, one request per paper.

Each paper's Markdown (papers/parsed/<dir>/paper.md and supplementary*.md) goes in the
user message as text, with the table of its CSD entries. Requests run concurrently on
one asyncio event loop, so the run needs only a few threads however many are in flight.
Every finished paper appends its rows to `rows.jsonl` and one line to `log.jsonl` in the
run directory; papers already in the log are skipped, so a stopped run resumes. Each
start appends to `manifest.jsonl` what produced the run: command, git commit and diff,
prompt version, model, effort and the papers sent, with the system prompt in `system.txt`.

The login node kills a process after 90 min of CPU time. After `--cpu-budget` seconds the
runner stops starting papers, lets those in flight finish and exits with status 3;
`scripts/run_extraction.sh` restarts it until every paper is done.

Usage:
    pixi run python -m dataset.extraction_stream [--sample N] [--seed S] [--concurrency C]
        [--model M] [--effort E] [--run DIR]
"""

import os

# The login node allows 1024 threads per user; polars and BLAS would otherwise start
# one per core (192).
for var in ("POLARS_MAX_THREADS", "RAYON_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(var, "4")

import argparse
import asyncio
import hashlib
import json
import random
import re
import resource
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from openai import APIError, AsyncOpenAI, RateLimitError

from dataset.extraction_agent import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    MAX_OUTPUT_TOKENS,
    failed,
    parse_response,
    to_rows,
)
from dataset.extraction_prompt import (
    ENTRY_FIELDS,
    METADATA,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    _entry_table,
    output_schema,
)
from dataset.extraction_schema import SCHEMA

ROOT = Path(__file__).parents[2]
CORPUS = ROOT / "papers"
PARSED = CORPUS / "parsed"

FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)

# Exit status meaning "stopped early, papers left": the wrapper restarts the runner.
MORE_TO_DO = 3

# Seconds every request waits after a 429. Kept short: the quota refills steadily,
# and a long pause leaves the whole pool idle after every hit.
COOLDOWN = 15


def corpus() -> pl.DataFrame:
    """One row per parsed paper: folder, DOI, Markdown files, refcodes, scanned files."""
    refcodes = (
        pl.read_parquet(CORPUS / "metadata.parquet", columns=["dir", "refcodes"])
        .filter(pl.col("dir").is_not_null())
        .group_by("dir")
        .agg(pl.col("refcodes").list.explode().unique().sort())
    )
    return (
        pl.read_parquet(CORPUS / "parsed.parquet")
        .filter(pl.col("error").is_null())
        .join(refcodes, on="dir")
        .sort("dir")
    )


def entry_fields(identifiers: list[str]) -> pl.DataFrame:
    return (
        pl.scan_parquet(METADATA)
        .select(ENTRY_FIELDS)
        .filter(pl.col("identifier").is_in(identifiers))
        .collect()
    )


def paper_text(path: Path) -> str:
    """The file's Markdown, with paper.md's front matter cut down to the title."""
    text = path.read_text()
    m = FRONT_MATTER.match(text)
    if not m:
        return text
    title = re.search(r"^title: (.*)$", m.group(1), re.MULTILINE)
    return (f"# {title.group(1)}\n\n" if title else "") + text[m.end() :]


def build(paper: dict, entries: pl.DataFrame) -> dict:
    """One agent job for a corpus paper, in the shape `extraction_agent` uses."""
    files = paper["files"]
    kinds = ["main" if f == "paper.md" else "supplementary" for f in files]
    listing = "\n".join(f"- {f} ({k} paper)" for f, k in zip(files, kinds))
    unread = "".join(
        f"\n- {f} (supplementary; a scan with no text, not included)" for f in paper["needs_ocr"]
    )
    texts = [f'<file name="{f}">\n{paper_text(PARSED / paper["dir"] / f)}\n</file>' for f in files]
    user = "\n".join(
        [
            f"Paper DOI: {paper['doi']}",
            "",
            f"Files (Markdown text follows the table; it has no page numbers, so set "
            f"`page` to null):\n{listing}{unread}",
            "",
            f"CSD entries linked to this paper ({len(entries)}). "
            "Return one record for each, in this order:",
            "",
            _entry_table(entries),
            "",
            *texts,
        ]
    )
    return {
        "doi": paper["doi"],
        "dir": paper["dir"],
        "prompt_version": PROMPT_VERSION,
        "identifiers": entries["identifier"].to_list(),
        "attachments": [
            {"label": f, "path": str(PARSED / paper["dir"] / f), "input": "md"} for f in files
        ],
        "source_files": [{"name": f, "kind": k, "input": "md"} for f, k in zip(files, kinds)],
        "system": SYSTEM_PROMPT,
        "user": user,
        "output_schema": output_schema(),
    }


class Throttle:
    """Shared pause: a 429 on any request holds back every request until it ends."""

    def __init__(self) -> None:
        self.until = 0.0
        self.hits = 0

    def hit(self) -> None:
        self.hits += 1
        self.until = max(self.until, time.monotonic() + COOLDOWN)

    async def wait(self) -> None:
        while (left := self.until - time.monotonic()) > 0:
            # Jitter so the waiting requests don't all return in the same second.
            await asyncio.sleep(left + random.uniform(0, COOLDOWN / 2))


async def call(client: AsyncOpenAI, job: dict, model: str, effort: str, throttle: Throttle) -> dict:
    """Like `extraction_agent.call_agent`, but retries rate limits until they pass."""
    while True:
        await throttle.wait()
        try:
            return await call_once(client, job, model, effort)
        except RateLimitError:
            throttle.hit()


async def call_once(client: AsyncOpenAI, job: dict, model: str, effort: str) -> dict:
    try:
        # Streamed so the connection stays busy: the proxy drops idle requests at ~20 min.
        async with client.responses.stream(
            model=model,
            instructions=job["system"],
            input=[{"role": "user", "content": [{"type": "input_text", "text": job["user"]}]}],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "extraction",
                    "schema": job["output_schema"],
                    "strict": True,
                }
            },
            reasoning={"effort": effort, "summary": "auto"},
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ) as stream:
            async for _ in stream:
                pass
            response = await stream.get_final_response()
    except RateLimitError:
        raise
    except APIError as e:
        return failed(str(e))
    except Exception as e:  # e.g. a stream cut before `response.completed`
        return failed(f"{type(e).__name__}: {e}")
    return parse_response(response)


def read_jsonl(path: Path) -> list[dict]:
    """The file's records, skipping a last line cut off when a process was killed."""
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def done(run: Path) -> set[str]:
    """Papers already run to an answer; `failed` ones are tried again."""
    return {r["dir"] for r in read_jsonl(run / "log.jsonl") if r["status"] != "failed"}


def cpu_seconds() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


async def stream(
    papers: pl.DataFrame,
    run: Path,
    model: str,
    effort: str,
    concurrency: int,
    cpu_budget: float,
) -> bool:
    """Run the papers; return False if the CPU budget ran out before all were started."""
    client = AsyncOpenAI(
        base_url=os.environ.get("LITELLM_BASE_URL", DEFAULT_BASE_URL),
        api_key=os.environ["LITELLM_API_KEY"],
        timeout=3600,
        # Rate limits are retried by `call`; this covers dropped connections.
        max_retries=3,
    )
    entries = entry_fields(papers["refcodes"].explode().unique().to_list())
    gate = asyncio.Semaphore(concurrency)
    throttle = Throttle()
    rows_file = (run / "rows.jsonl").open("a")
    log_file = (run / "log.jsonl").open("a")
    start = time.monotonic()
    n_done = 0
    stopping = False

    async def one(paper: dict) -> None:
        nonlocal n_done, stopping
        async with gate:
            if stopping or cpu_seconds() > cpu_budget:
                stopping = True
                return
            mine = entries.filter(pl.col("identifier").is_in(paper["refcodes"])).sort("identifier")
            job = build(paper, mine)
            t0 = time.monotonic()
            result = await call(client, job, model, effort, throttle)
            seconds = round(time.monotonic() - t0, 1)
        rows = to_rows(job, result, model)
        for row in rows:
            rows_file.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")
        usage = result["usage"] or {}
        log_file.write(
            json.dumps(
                {
                    "dir": paper["dir"],
                    "doi": paper["doi"],
                    "status": result["status"],
                    "error": result["error"],
                    "entries": len(job["identifiers"]),
                    "input_chars": len(job["user"]),
                    "usage": usage,
                    "seconds": seconds,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "reasoning": result["reasoning"],
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        rows_file.flush()
        log_file.flush()
        n_done += 1
        elapsed = time.monotonic() - start
        print(
            f"[{n_done}/{papers.height} {elapsed:.0f}s] {paper['dir']}: {result['status']}, "
            f"{len(rows)} rows, {usage.get('input_tokens')}+{usage.get('output_tokens')} "
            f"tokens, {seconds}s, {throttle.hits} rate limits so far"
            + (f" ({result['error']})" if result["error"] else ""),
            flush=True,
        )

    await asyncio.gather(*(one(p) for p in papers.iter_rows(named=True)))
    rows_file.close()
    log_file.close()
    print(
        f"{n_done} papers in {time.monotonic() - start:.0f}s, {cpu_seconds():.0f}s CPU"
        + (", CPU budget reached" if stopping else ""),
        flush=True,
    )
    return not stopping


def to_parquet(run: Path) -> pl.DataFrame:
    """The run's rows in the extraction schema, the latest attempt for each entry."""
    rows = run / "rows.jsonl"
    # Drop a last line cut off by a killed process; polars rejects partial JSON.
    text = rows.read_text()
    if text and not text.endswith("\n"):
        rows.write_text(text[: text.rfind("\n") + 1])
    df = (
        pl.read_ndjson(rows, schema=SCHEMA)
        .sort("extracted_at")
        .unique(subset=["identifier", "doi"], keep="last", maintain_order=True)
    )
    df.write_parquet(run / "extractions.parquet")
    return df


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout


def record(run: Path, args: argparse.Namespace, papers: pl.DataFrame) -> None:
    """Append what produced this run to `manifest.jsonl`; save the uncommitted diff."""
    diff = git("diff", "HEAD", "--", "src")
    digest = hashlib.sha256(diff.encode()).hexdigest()[:12]
    if diff:
        (run / f"diff-{digest}.patch").write_text(diff)
    (run / "system.txt").write_text(SYSTEM_PROMPT)
    entry = {
        "started_at": datetime.now(UTC).isoformat(),
        "command": sys.argv,
        "git_commit": git("rev-parse", "HEAD").strip(),
        "git_diff": f"diff-{digest}.patch" if diff else None,
        "prompt_version": PROMPT_VERSION,
        "system_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "model": args.model,
        "effort": args.effort,
        "concurrency": args.concurrency,
        "sample": args.sample,
        "seed": args.seed,
        "papers": papers["dir"].to_list(),
    }
    with (run / "manifest.jsonl").open("a") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", type=int, help="Run this many random papers (default: all)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=64, help="Requests in flight")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default="high", help="Reasoning effort")
    parser.add_argument("--run", type=Path, default=ROOT / "data" / "runs" / "corpus")
    parser.add_argument(
        "--cpu-budget",
        type=float,
        default=3000,
        help="CPU seconds before stopping for a restart (the node's soft limit is 3600)",
    )
    parser.add_argument(
        "--skip-journal",
        action="append",
        default=[],
        help="Skip papers whose journal contains this text (repeatable), e.g. 'Sect.E:'",
    )
    args = parser.parse_args()

    papers = corpus()
    if args.skip_journal:
        journals = pl.read_parquet(CORPUS / "metadata.parquet", columns=["dir", "journal"])
        skipped = journals.filter(
            pl.any_horizontal(pl.col("journal").str.contains(j, literal=True) for j in args.skip_journal)
        )["dir"]
        papers = papers.filter(~pl.col("dir").is_in(skipped.implode()))
    if args.sample:
        papers = papers.sample(args.sample, seed=args.seed)
    papers = papers.filter(~pl.col("dir").is_in(list(done(args.run))))
    args.run.mkdir(parents=True, exist_ok=True)
    record(args.run, args, papers)
    print(f"{papers.height} papers to run -> {args.run}", flush=True)
    finished = asyncio.run(
        stream(papers, args.run, args.model, args.effort, args.concurrency, args.cpu_budget)
    )
    if not finished:
        sys.exit(MORE_TO_DO)
    df = to_parquet(args.run)
    print(f"{df.height} rows -> {args.run / 'extractions.parquet'}")


if __name__ == "__main__":
    main()
