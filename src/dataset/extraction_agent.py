"""Run the extraction agent on prompt jobs and collect rows in the extraction schema.

Calls a model through the LiteLLM proxy (OpenAI Responses API), one request per
paper, with the paper's PDFs attached. Jobs come from `dataset.extraction_prompt`.

Usage:
    uv run python -m dataset.extraction_agent [JOB.json ...] [--model M] [--out FILE]

Needs LITELLM_API_KEY in the environment; LITELLM_BASE_URL overrides the proxy URL.
"""

import argparse
import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from openai import APIError, OpenAI
from tqdm import tqdm

from dataset.extraction_schema import EVIDENCED_FIELDS, SCHEMA

ROOT = Path(__file__).parents[2]
JOBS = ROOT / "data" / "prompts"
DEFAULT_MODEL = "gpt-6-luna"
DEFAULT_BASE_URL = "https://litellm.elagente.ca"
MAX_OUTPUT_TOKENS = 64_000
DEFAULT_EFFORT = "max"

PARAGRAPHS = [
    "synthesis",
    "crystallisation",
    "characterisation",
    "solid_form",
    "purpose_and_properties",
    "summary",
    "other_notes",
]


def client() -> OpenAI:
    return OpenAI(
        base_url=os.environ.get("LITELLM_BASE_URL", DEFAULT_BASE_URL),
        api_key=os.environ["LITELLM_API_KEY"],
        timeout=600,
        max_retries=3,
    )


def _pdf_part(label: str, path: str) -> dict:
    data = base64.b64encode(Path(path).read_bytes()).decode()
    return {
        "type": "input_file",
        "filename": label,
        "file_data": f"data:application/pdf;base64,{data}",
    }


def call_agent(
    job: dict,
    model: str = DEFAULT_MODEL,
    effort: str = DEFAULT_EFFORT,
    client: OpenAI | None = None,
) -> dict:
    """Send one paper's job to the model; return the parsed output and call metadata.

    The result has `entries` (the model's records, or None), `status` (`ok`,
    `truncated`, `refused` or `failed`), `error`, token `usage`, and `reasoning`
    (the model's reasoning summary, if it returned one).
    """
    client = client or globals()["client"]()
    content = [_pdf_part(a["label"], a["path"]) for a in job["attachments"]]
    content.append({"type": "input_text", "text": job["user"]})
    try:
        response = client.responses.create(
            model=model,
            instructions=job["system"],
            input=[{"role": "user", "content": content}],
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
        )
    except APIError as e:
        return {
            "entries": None,
            "status": "failed",
            "error": str(e),
            "usage": None,
            "reasoning": None,
        }

    usage = response.usage.model_dump() if response.usage else None
    reasoning = "\n\n".join(
        part.text for o in response.output if o.type == "reasoning" for part in o.summary or []
    )
    meta = {"usage": usage, "reasoning": reasoning or None}
    if response.status == "incomplete":
        reason = getattr(response.incomplete_details, "reason", None)
        status = "refused" if reason == "content_filter" else "truncated"
        return {"entries": None, "status": status, "error": f"incomplete: {reason}", **meta}
    refusal = next(
        (
            c.refusal
            for o in response.output
            for c in getattr(o, "content", []) or []
            if c.type == "refusal"
        ),
        None,
    )
    if refusal:
        return {"entries": None, "status": "refused", "error": refusal, **meta}
    try:
        entries = json.loads(response.output_text)["entries"]
    except (json.JSONDecodeError, KeyError) as e:
        return {"entries": None, "status": "failed", "error": f"bad JSON: {e}", **meta}
    return {"entries": entries, "status": "ok", "error": None, **meta}


def _clean(value):
    """Turn empty strings and placeholder text into null."""
    if isinstance(value, str):
        v = value.strip()
        if not v or v.lower().rstrip(".") in {"n/a", "na", "none", "not reported", "not mentioned"}:
            return None
        return v
    return value


def to_rows(job: dict, result: dict, model: str) -> list[dict]:
    """One schema row per CSD entry in the job, whatever the model returned."""
    by_label = {a["label"]: Path(a["path"]).name for a in job["attachments"]}
    returned = {e["identifier"]: e for e in result["entries"] or []}
    now = datetime.now(UTC)
    rows = []
    for identifier in job["identifiers"]:
        e = returned.get(identifier, {})
        status = result["status"]
        error = result["error"]
        if status == "ok" and not e:
            status, error = "compound_not_found", "model returned no record for this entry"
        quotes = e.get("evidence", [])
        dropped = [q["field"] for q in quotes if q["field"] not in EVIDENCED_FIELDS]
        if dropped:
            error = f"dropped evidence for unknown fields: {', '.join(sorted(set(dropped)))}"
        row = {
            "identifier": identifier,
            "doi": job["doi"],
            "compound_label": _clean(e.get("compound_label")),
            "match_confidence": e.get("match_confidence"),
            "match_basis": _clean(e.get("match_basis")),
            "related_identifiers": [i for i in e.get("related_identifiers", []) if i != identifier],
            **{p: _clean(e.get(p)) for p in PARAGRAPHS},
            "evidence": [
                {**q, "source_file": by_label.get(q["source_file"], q["source_file"])}
                for q in quotes
                if q["field"] in EVIDENCED_FIELDS
            ],
            "source_files": job["source_files"],
            "model": model,
            "prompt_version": job["prompt_version"],
            "extracted_at": now,
            "extraction_status": status,
            "error": error,
        }
        rows.append(row)
    return rows


def run(job_paths: list[Path], model: str = DEFAULT_MODEL, workers: int = 8) -> pl.DataFrame:
    """Run the agent on each job in parallel and return all rows as one DataFrame.

    Each paper's raw result, including the reasoning summary, is saved next to its
    job as `<job>.result.json`.
    """
    c = client()

    def one(path: Path) -> list[dict]:
        job = json.loads(path.read_text())
        result = call_agent(job, model=model, client=c)
        path.with_suffix(".result.json").write_text(
            json.dumps(result, indent=1, ensure_ascii=False)
        )
        tokens = (result["usage"] or {}).get("total_tokens")
        tqdm.write(
            f"{path.stem}: {result['status']}, {tokens} tokens"
            + (f" ({result['error']})" if result["error"] else "")
        )
        return to_rows(job, result, model)

    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, path) for path in job_paths]
        for future in tqdm(as_completed(futures), total=len(futures), desc="papers", unit="paper"):
            rows += future.result()
    return pl.DataFrame(rows, schema=SCHEMA)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "jobs", nargs="*", type=Path, help="Job files (default: all in data/prompts/)"
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "extractions.parquet")
    args = parser.parse_args()

    jobs = args.jobs or sorted(p for p in JOBS.glob("*.json") if not p.stem.endswith(".result"))
    df = run(jobs, model=args.model)
    df.write_parquet(args.out)
    print(f"{df.height} rows -> {args.out}")


if __name__ == "__main__":
    main()
