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

The earlier pilot input, five PDFs from Anna's Archive in `data/papers/`, and its runs
(`data/prompts*/`, `data/mineru*/`, `data/extractions*.parquet`) were deleted on 2026-10-22.

## Runs

| run | date | papers | model, effort | outcome |
|---|---|---|---|---|
| `pilot10` | 2026-10-22 | 10 random (seed 0) | gpt-6-luna, max | Stopped after 3 papers: 160-540 s and 12-19k output tokens per one-entry paper, too slow for the corpus. Run directory deleted. |
| `pilot10_high` | 2026-10-22 | same 10 | gpt-6-luna, high | 10/10 ok, 23 rows, 102 s wall. All 23 entries checked by hand against the paper: matched to the right compound (18 by the CCDC number next to the label, 5 by the paper's description). Core paragraphs as complete as `max`; `purpose_and_properties` and `other_notes` shorter. 27/337 quotes not verbatim, mostly hyphen/case differences or merged list items; one with a changed word. |
| `pilot200_high` | 2026-10-22 | 200 random (seed 1) | gpt-6-luna, high, 200 in flight | First start: all 200 failed with 429, the Bedrock output-tokens-per-minute quota for gpt-6-luna. Runner then given a shared cooldown on 429 and resumed: 200/200 ok, 437 rows, 161 s wall, 0 rate limits; median 42 s per paper; 4.86M input and 1.38M output tokens; match confidence 411 high, 23 medium, 3 low. Shared as `/project/rrg-aspuru/lmucko/clari-osi-hackathon/example_200.parquet` (read-write for everyone; only reachable by `rrg-aspuru` members because `/project/rrg-aspuru` is group-only). |
| `corpus` | 2026-10-22 | the corpus, journal by journal, Acta E skipped | gpt-6-luna, high | The production run on the full text (prompt `v2`). Stopped by the end of the hackathon after Angew. Chem., Chem. Eur. J., Cryst. Growth Des. and half of Inorg. Chem.: 5,843 papers, 21,646 rows (21,459 ok, 165 compound not found, 22 failed). |
| `acta_e` | 2026-10-22 | the 27,266 Acta E papers of the Acta E collection | gpt-5.6-luna, high | The production run on Acta E, by its own runner (`acta_e_stream.py` on the `acta-e-extraction-and-viewer` branch) with prompt `v2-actae-anchored-1`: the model reads the paper's experimental sections (and, when the match is unclear, its introduction) rather than the full text, and picks its quotes from numbered source passages, so quotes are verbatim by construction. gpt-6-luna's quota was used up by `corpus`, hence the other model. Still running when `data/extractions.parquet` was snapshotted (20:58 UTC): 23,117 papers, 23,460 rows (23,407 ok, 47 compound not found, 5 failed, 1 no paper). Output on Trillium under `/project/rrg-aspuru/auhcheng/acta_e_schema_2026-10-22/anchored-v1/`. |

`data/extractions.parquet` is the union of the `corpus` and `acta_e` rows at the time of the snapshot; `extraction_status` and `prompt_version` tell the two apart.

## Decisions

- Effort `high`, not `max`: same matches and core content on the pilot, about 10x faster.
- Input kept raw (no cleaning of `<svg>` or other parse leftovers) to avoid tuning to a sample.
- Quotes are not yet checked against the source; that runs after extraction.
