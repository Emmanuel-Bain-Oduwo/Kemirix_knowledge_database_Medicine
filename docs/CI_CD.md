# CI, checkpoints, automatic merge and exact-SHA development delivery

## Branch model

There is one permanent branch only: `main`. Normal engineering work flows
`main -> temporary agent/<agent>/<task-id> branch -> checkpoint commits -> PR -> main`.
Do not introduce develop/staging/release/environment branches. The legacy `develop`
refs that may still exist in a clone are not part of the model and must not be used.

Routine engineering PRs merge automatically once every required gate passes.
Human approval is reserved for high-consequence actions only: Clinical Evidence
approval, Clinical Rule approval/activation, changes to frozen KMX
architecture/invariants, destructive production DB migrations, and production
release/deployment.

## CI

CI runs on PRs targeting main and pushes to main, on GitHub-hosted runners with
Python 3.12, uv and a PostgreSQL 17 service. Pipeline: checkout → install uv →
`uv sync --frozen` → configuration validation → secret-pattern safety scan →
`ruff check` → `ruff format --check` → pytest → PostgreSQL 17 service →
migration-from-zero gate → integration tests → future KMX/Evidence/Rule contract
tests (required once any migration is executable; an absent contract suite then
fails rather than silently passing).

The three current migrations are placeholders. CI reports them as pending/not
executable and never pretends they are production-ready. CI never reads
/etc/kemirix/*.env, connects to OVH PostgreSQL or production Object Storage,
contains real credentials, or deploys PR code. PostgreSQL's documented disposable
password is CI-only.

Local checks:

```sh
uv sync --frozen --python 3.12
uv run --frozen python scripts/validate_config.py
uv run --frozen python scripts/scan-secrets.py
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest -q
uv run --frozen python scripts/migration_gate.py
git diff --check
```

`--execute-ci` is reserved for the isolated hosted PostgreSQL service. Local tests
use mocks and disposable synthetic Git objects, with no real repository commit,
provider request or deployment.

## Meaningful checkpoints

```sh
# From the matching agent/task worktree; stage only intended changes first.
./scripts/agent-submit.sh "KMX-001 implement registry constraints"
# Alternatively name each intended changed file explicitly:
./scripts/agent-submit.sh "TASK-001 checkpoint" --path tests/fixtures/example.txt
```

The tool refuses main and non-task branches, requires an
`agent/<agent>/<task-id>` branch, verifies changes exist, requires a valid shared
task contract and ownership, rejects unrelated dirty files and partial staging
unless full-file `--path` scope is explicit, scans intended contents, runs relevant
fast validation (configuration validation and Ruff) and the required test
profiles, and re-checks that nothing changed during testing. It stages only the
intended paths, commits, pushes the task branch, prints the branch and commit SHA,
and reports PR state when `gh` is installed. A failed push preserves the local
checkpoint. It never prints secrets, auto-deploys, force-pushes or commits every
keystroke/save. Humans should not routinely type git add/commit/push.

## PR creation and automatic merge

```sh
# Draft during active work; target is always main:
./scripts/agent-open-pr.sh --title '...' --body-file /path/to/reviewed-body.md
# When work is complete, enable squash auto-merge (marks a draft ready):
./scripts/agent-open-pr.sh --title '...' --body-file /path/to/reviewed-body.md --auto-merge
```

The tool accepts task branches only, reuses an existing open PR when present,
otherwise creates a draft PR into main. It never targets develop, bypasses CI or
leaks secrets.

Ordinary engineering PRs require: GitHub CI = PASS, Qwen = PASS, GLM = PASS,
Nemotron = QA_PASS, required tests = PASS, a valid task contract and no unresolved
blocking findings. Kimi research is required only where the task contract declares
`research_required: true`; unrelated infrastructure tasks do not force it. Review
outputs remain durable reports under `ops/reports/<TASK_ID>/`.

When all gates pass, GitHub merges the PR automatically using squash merge into
main. No direct push to main, no `--admin` bypass, no force merge, no merge with
failed checks, no bypassing branch protection. The coordinator's deterministic
`merge-gate` command evaluates the same conditions mechanically and fails closed:

```sh
uv run --frozen python -m agents.coordinator merge-gate TASK-001 \
  --branch agent/codex/TASK-001 --base-sha <full-sha> --head-sha <full-sha> \
  --ci-pass --test-result foundation
```

### One-time GitHub repository configuration (required, not yet performed)

Until these steps are actually performed in GitHub settings, automatic merge is
not operational:

1. Settings → General → Pull Requests: enable **Allow auto-merge**; select squash
   merge as the default; enable **Automatically delete head branches**.
2. Settings → Branches → Branch protection for `main`: require a pull request
   before merging, require approvals as configured, require status checks
   (the `foundation` CI job) and require branches to be up to date before merging;
   prohibit force pushes and deletions.
3. Grant agents push access to their own `agent/*` branches only (ruleset);
   direct pushes to main are prohibited for everyone.
4. Delete the legacy `develop` branch in GitHub once main-only operation is confirmed.

After a squash merge, the resulting main SHA becomes the approved engineering
baseline and development CD begins automatically.

## Automatic development CD to OVH

Deploy development listens to completed CI workflow runs and requires success,
event=push, head_branch=main and the same source repository. It never deploys PR
builds. The exact SHA is `github.event.workflow_run.head_sha`: this is the main
run's tested GITHUB_SHA, not the workflow_run handler's default-branch SHA. No PR
artifacts are downloaded or executed.

SSH uses pinned known_hosts, strict host-key validation, a private temporary key
file and a deployment-specific user. Required GitHub environment secrets:

- KEMIRIX_DEV_VM_HOST
- KEMIRIX_DEV_VM_USER
- KEMIRIX_DEV_VM_SSH_KEY
- KEMIRIX_DEV_VM_KNOWN_HOSTS

Keep DATABASE_URL, OVH S3 keys, Nebius keys and Cloudflare tokens VM-side in
/etc/kemirix/app.env and /etc/kemirix/agents.env. The deployment loads neither
file. GitHub receives no application/provider credentials.

An operator must provision `/srv/kemirix/deploy/repository.git` as a dedicated
bare repository with an origin and read-only GitHub access. Provision Python
3.12, uv 0.12.10 and permission to create `/srv/kemirix/runtime/development/` for
the dedicated deploy user. Agents must have no write permission to this runtime or
the trusted deployment repository. Restrict the deploy SSH key/account to the
documented deployment operations, and obtain the VM host key through a trusted
channel. Never use ssh-keyscan output without independent verification. Configure
the development environment and ensure both workflows exist on the default branch
so workflow_run can trigger.

The VM fetches the exact SHA, verifies main ancestry, then deploys: create the
immutable `releases/<sha>` directory from the Git archive (never the mutable
engineering checkout), sync frozen non-editable dependencies with `uv sync`,
run safe offline smoke checks and the future migration hook, atomically switch
the `current` symlink, write `DEPLOYED_SHA`, verify the deployment and keep at
least the three most recent releases. The human should not routinely SSH, git
pull, copy code, run uv sync, change symlinks, write DEPLOYED_SHA or verify
runtime manually.

```text
/srv/kemirix/runtime/development/
  releases/<sha>/
  manifests/<sha>.json
  current -> releases/<active-sha>
  DEPLOYED_SHA
```

Code deployment and clinical knowledge activation are completely separate. A
merge/deploy never approves Clinical Evidence, activates Clinical Rules, publishes
clinical knowledge or approves ambiguous KMX mappings.

The two pointer updates are individually atomic, not one filesystem transaction.
On an ordinary failure the previous pair is restored. A crash between
replacements is detected as drift; an operator must reconcile using a known-good
exact SHA. Failed incomplete releases are preserved for investigation and require
operator quarantine before retry, never arbitrary overwriting.

## Integrity, verification and rollback

`./scripts/verify-runtime.sh EXPECTED_SHA` obtains verification code from the
trusted Git object store. It reports expected SHA, DEPLOYED_SHA, symlink target,
release existence, integrity and offline smoke/health result. Source
bytes/executable bits are compared with Git; dependency files, symlink targets and
unexpected files are compared with the deployment-time inventory. A mismatch
reports **RUNTIME DRIFT DETECTED** and prevents executing drifted release code. No
runtime change is ever pushed back to Git.

Rollback stays simple: switch `current` back to a previous known-good
`releases/<SHA>`. For an authorized development rollback, extract
scripts/runtime.py from a trusted Git SHA to a temporary file and invoke
`python3 <trusted-runner> rollback <previous-known-good-sha>`. It accepts only an
existing intact release, validates smoke, then switches pointers. No automatic
production rollback and no complicated deployment platform exist. Investigate
detected drift before rollback; the runner does not silently repair corrupted
files.

## Migration policy

Migration files are versioned in Git and become immutable once released. Correct
a released schema using a new migration, never by silently rewriting history. CI
rehearses from empty PostgreSQL 17. Development migration execution may be added
only after CI validation and separate review; the current hook explicitly refuses
executable domain migrations until implemented. Destructive migrations require
explicit data/recovery handling and human approval. Production migration requires
human release approval. Clinical Evidence approval/knowledge activation is always
separate from code delivery.

References: [GitHub workflow_run behavior/security](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run), [PostgreSQL services](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers), [setup-uv](https://github.com/astral-sh/setup-uv/tree/v6).
