#!/usr/bin/env bash
set -euo pipefail
# Reports expected SHA, DEPLOYED_SHA, symlink target, release existence,
# runtime integrity and smoke/health result. Drift never gets pushed back to Git.
sha=${1:?expected SHA required}
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || exit 2
repo=/srv/kemirix/deploy/repository.git
runner=$(mktemp /tmp/kemirix-verify-XXXXXXXX.py)
trap 'rm -f -- "$runner"' EXIT
# Use trusted Git, not potentially drifted current/scripts/runtime.py.
git --git-dir="$repo" fetch origin "$sha" >/dev/null 2>&1 || true
git --git-dir="$repo" show "$sha:scripts/runtime.py" > "$runner"
python3 "$runner" verify "$sha"
