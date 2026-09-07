#!/usr/bin/env bash
set -euo pipefail
# Run from the task worktree. Never source VM secret files.
exec uv run --frozen python -m agents.coordinator handoff "$@"
