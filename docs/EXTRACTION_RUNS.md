# Extraction runs

What was run, on what, and why. Each run directory in `data/runs/<name>/` (not in git) holds
the exact record: `manifest.jsonl` (one line per start: command, git commit, uncommitted diff
saved as `diff-<hash>.patch`, prompt version, system prompt hash, model, effort, the papers sent),
`system.txt`, `log.jsonl` (one line per paper: status, tokens, seconds, reasoning summary),
`rows.jsonl` and `extractions.parquet`.

## Input

From 2026-10-22, the PMC open-access corpus in `papers/` (see `papers/README.md`): for each paper,
`papers/parsed/<dir>/paper.md` and every `supplementary*.md`, sent raw as text in the user
message. The only change is that `paper.md`'s YAML front matter (authors, licence, reference
list) is cut to the title. Equation images left by the parse as inline `<svg>` are kept as-is.
Scanned supplementary PDFs with no text (`needs_ocr`) are listed by name but not sent. The CSD
entries of a paper are its `refcodes` in `papers/metadata.parquet`, with fields from
`data/csd_metadata.full.parquet`. Runner: `src/dataset/extraction_stream.py`.

The earlier pilot input, five PDFs from Anna's Archive in `data/papers/`, was deleted on
2026-10-22; its runs are in `data/prompts*/` and `data/extractions*.parquet`.

## Runs

| run | date | papers | model, effort | outcome |
|---|---|---|---|---|
| `pilot10` | 2026-10-22 | 10 random (seed 0) | gpt-6-luna, max | Stopped after 3 papers: 160-540 s and 12-19k output tokens per one-entry paper, too slow for the corpus. |
| `pilot10_high` | 2026-10-22 | same 10 | gpt-6-luna, high | 10/10 ok, 23 rows, 102 s wall. All 23 entries checked by hand against the paper: matched to the right compound (18 by the CCDC number next to the label, 5 by the paper's description). Core paragraphs as complete as `max`; `purpose_and_properties` and `other_notes` shorter. 27/337 quotes not verbatim, mostly hyphen/case differences or merged list items; one with a changed word. |
| `pilot200_high` | 2026-10-22 | 200 random (seed 1) | gpt-6-luna, high, 200 in flight | First start: all 200 failed with 429, the Bedrock output-tokens-per-minute quota for gpt-6-luna. Runner then given a shared cooldown on 429 and resumed: 200/200 ok, 437 rows, 161 s wall, 0 rate limits; median 42 s per paper; 4.86M input and 1.38M output tokens; match confidence 411 high, 23 medium, 3 low. Shared as `/project/rrg-aspuru/lmucko/clari-osi-hackathon/example_200.parquet` (read-write for everyone; only reachable by `rrg-aspuru` members because `/project/rrg-aspuru` is group-only). |

## Decisions

- Effort `high`, not `max`: same matches and core content on the pilot, about 10x faster.
- Input kept raw (no cleaning of `<svg>` or other parse leftovers) to avoid tuning to a sample.
- Quotes are not yet checked against the source; that runs after extraction.
