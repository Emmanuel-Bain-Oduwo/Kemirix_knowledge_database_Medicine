#!/usr/bin/env bash
set -euo pipefail
# Invoked on VM with exact tested SHA; never sources /etc/kemirix/*.env.
sha=${1:?exact tested develop SHA required}
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || exit 2
repo=/srv/kemirix/deploy/repository.git
runner=$(mktemp /tmp/kemirix-deploy-XXXXXXXX.py)
trap 'rm -f -- "$runner"' EXIT
git --git-dir="$repo" fetch origin "$sha" >/dev/null 2>&1
git --git-dir="$repo" show "$sha:scripts/runtime.py" > "$runner"
python3 "$runner" deploy "$sha"
