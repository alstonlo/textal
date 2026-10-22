#!/usr/bin/env bash
# Run the extraction over the whole corpus until every paper is done, restarting the
# runner whenever it stops for the login node's CPU-time limit (exit status 3) or dies.
# Meant to run detached so it outlives the shell that started it:
#
#   tmux new -d -s extraction scripts/run_extraction.sh [RUN_DIR] [extra runner args]
#
# Output goes to RUN_DIR/stdout.log. Stop it with `tmux kill-session -t extraction`;
# starting it again resumes.
set -u
cd "$(dirname "$0")/.."

run=${1:-data/runs/corpus}
shift || true
mkdir -p "$run"
log="$run/stdout.log"

attempt=0
while true; do
    attempt=$((attempt + 1))
    echo "=== start $attempt at $(date -u +%FT%TZ)" >>"$log"
    uv run python -m dataset.extraction_stream --run "$run" "$@" >>"$log" 2>&1
    status=$?
    echo "=== exit $status at $(date -u +%FT%TZ)" >>"$log"
    case $status in
        0) break ;;           # every paper has an answer; extractions.parquet written
        3) sleep 5 ;;         # CPU budget used up; restart with a fresh process
        *) sleep 60 ;;        # crashed or was killed; wait a minute and resume
    esac
done
