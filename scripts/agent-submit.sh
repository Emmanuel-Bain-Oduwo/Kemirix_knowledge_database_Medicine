#!/usr/bin/env bash
set -euo pipefail
# Automatic checkpoint commit for the current task branch. Never source VM secret files.
# Usage: ./scripts/agent-submit.sh "TASK-001 meaningful message" [--path FILE ...]
# Refuses main and non-task branches before any mutation; the Python gate re-validates.
branch=$(git branch --show-current)
if [[ -z "$branch" || "$branch" == main || "$branch" != agent/*/* ]]; then
  echo "refusing to submit from branch '${branch:-detached}': agent/<agent>/<task-id> required" >&2
  exit 2
fi
exec uv run --frozen python -m agents.checkpoint submit "$@"
