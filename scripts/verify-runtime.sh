#!/usr/bin/env bash
set -euo pipefail
sha=${1:?expected SHA required}
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || exit 2
repo=/srv/kemirix/deploy/repository.git
runner=$(mktemp /tmp/kemirix-verify-XXXXXXXX.py)
trap 'rm -f -- "$runner"' EXIT
# Use trusted Git, not potentially drifted current/scripts/runtime.py.
git --git-dir="$repo" show "$sha:scripts/runtime.py" > "$runner"
python3 "$runner" verify "$sha"
