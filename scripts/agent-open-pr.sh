#!/usr/bin/env bash
set -euo pipefail
# Open (or reuse) the task's draft PR into main. Never source VM secret files.
# Usage: ./scripts/agent-open-pr.sh --title '...' --body-file /path/body.md [--auto-merge]
# --auto-merge enables GitHub squash auto-merge once required checks pass; it never bypasses CI.
branch=$(git branch --show-current)
if [[ -z "$branch" || "$branch" == main || "$branch" != agent/*/* ]]; then
  echo "refusing PR from branch '${branch:-detached}': agent/<agent>/<task-id> required" >&2
  exit 2
fi
exec uv run --frozen python -m agents.checkpoint open-pr "$@"
