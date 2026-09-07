#!/usr/bin/env bash
set -euo pipefail
# Usage: setup-worktrees.sh TASK_ID --approved-sha SHA --role codex
exec uv run --frozen python -m agents.coordinator start "$@"
