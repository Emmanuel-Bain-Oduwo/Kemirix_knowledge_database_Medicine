# CI, checkpoints and exact-SHA development delivery

## Branches and checks

`main` is stable/release. `develop` integrates reviewed work. Agents use `agent/<agent>/<task-id>`. Configure GitHub rulesets to prohibit direct agent pushes to main/develop and require the `foundation` CI check and independent review. No automatic production deployment or merge exists.

CI runs on PRs targeting develop/main and pushes to develop/main on GitHub-hosted ubuntu runners. Python 3.12 and uv 0.12.10 install the committed lockfile with `uv sync --frozen`. Configuration validation, a conservative secret-pattern scan, Ruff lint/format, foundation/unit tests, an isolated PostgreSQL 17 migration gate and engineering integration tests follow. Future domain contract tests are required once any migration is executable; an absent contract suite then fails rather than silently passing.

CI never reads /etc/kemirix/*.env, connects to OVH PostgreSQL or production S3, or runs provider APIs. PostgreSQL's documented disposable password is CI-only. The migration gate verifies PostgreSQL 17 and an empty database; it runs only the declared executable prefix in config/migration_suite.yaml. Currently all three SQL files are comment-only and declared pending: **no executable migration suite is claimed**. SQL hidden under a pending declaration fails validation. Hosted success still means foundation checks only until the domain suite is implemented.

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

`--execute-ci` is reserved for the isolated hosted PostgreSQL service. Local tests use mocks and disposable synthetic Git objects, with no real repository commit, provider request or deployment.

## Meaningful checkpoints

After human authorization lifts the current no-commit/no-push instruction:

```sh
# From the matching agent/task worktree; stage only intended changes first.
./scripts/agent-submit.sh "KMX-001 implement registry constraints"
# Alternatively name each intended changed file explicitly:
./scripts/agent-submit.sh "TASK-001 checkpoint" --path tests/fixtures/example.txt
```

The tool refuses main/develop and malformed agent branches, requires a valid shared task contract and ownership, rejects unrelated dirty files and partial staging unless full-file --path scope is explicit, scans intended contents, runs safe checks and required test profiles, and checks for changes during testing. It stages only the intended paths, commits, pushes an explicit current-branch refspec, prints the branch/SHA and reports open PR status if gh is installed. A failed push preserves the local checkpoint; it does not reset work. It never auto-merges, deploys or runs on every save.

Checkpoint metadata and committed role reports are mirrored into the control checkout at this lifecycle boundary. These governance changes remain explicit uncommitted control-checkout work for owner review and incorporation into the PR; the agent submit path intentionally cannot modify/commit governance files. The owner/integrator must include them before declaring the task durable in GitHub. Do not discard them during sync.

A separate `agent-open-pr.sh --title '...' --body-file /path/to/reviewed-body.md` creates only a draft PR into develop. The current task authorizes writing and testing these tools, **not executing commits, pushes or PR creation**.

## Development workflow

Deploy development listens to completed CI workflow runs and requires success, event=push, head_branch=develop and the same source repository. It never deploys PR builds. The exact SHA is `github.event.workflow_run.head_sha`: this is the develop run's tested GITHUB_SHA, not the workflow_run handler's default-branch SHA. No PR artifacts are downloaded or executed.

SSH uses pinned known_hosts, strict host-key validation, a private temporary key file and a deployment-specific user. Required GitHub environment secrets:

- KEMIRIX_DEV_VM_HOST
- KEMIRIX_DEV_VM_USER
- KEMIRIX_DEV_VM_SSH_KEY
- KEMIRIX_DEV_VM_KNOWN_HOSTS

Keep DATABASE_URL, OVH S3 keys, Nebius keys and Cloudflare tokens VM-side in /etc/kemirix/app.env and /etc/kemirix/agents.env. The deployment does not load either file. GitHub receives no application/provider credentials.

An operator must provision `/srv/kemirix/deploy/repository.git` as a dedicated bare repository with an origin and read-only GitHub access. Provision Python 3.12, uv 0.12.10 and permission to create `/srv/kemirix/runtime/development/` for the dedicated deploy user. Agents must have no write permission to this runtime or trusted deployment repository. Restrict the deploy SSH key/account to the documented deployment operations, and obtain the VM host key through a trusted channel. Never use ssh-keyscan output without independent verification. Configure the development environment and ensure the workflow exists on the default branch so workflow_run can trigger.

The VM fetches the exact SHA and verifies develop ancestry before loading its deployment code from Git. The runner serializes deployments, rejects stale SHAs relative to the active release, creates releases/<sha> from git archive, syncs frozen non-editable dependencies, runs offline smoke validation, checks the future migration hook and seals the release read-only. It atomically replaces current and DEPLOYED_SHA and verifies the result. It retains all releases initially, hence at least the last three. There is no destructive cleanup policy yet.

```text
/srv/kemirix/runtime/development/
  releases/<sha>/
  manifests/<sha>.json
  current -> releases/<active-sha>
  DEPLOYED_SHA
```

The two pointer updates are individually atomic, not one filesystem transaction. On an ordinary failure the previous pair is restored. A crash between replacements is detected as drift; an operator must reconcile using a known-good exact SHA. Failed incomplete releases are preserved for investigation and require operator quarantine before retry, never arbitrary overwriting.

## Integrity and rollback

`./scripts/verify-runtime.sh EXPECTED_SHA` obtains verification code from the trusted Git object store. It reports expected SHA, DEPLOYED_SHA, symlink target, release existence, integrity and offline smoke result. Source bytes/executable bits are compared with Git; dependency files, symlink targets and unexpected files are compared with the deployment-time inventory. A mismatch reports **RUNTIME DRIFT DETECTED** and prevents executing drifted release code. No runtime change is ever pushed to Git.

The manifest and Git object store require deploy-account/OS protection. This is drift detection, not protection against a compromised deploy account or host. The external Python interpreter/OS is not hashed as part of a release. Agent processes sharing a Unix identity with the deploy user would defeat this separation and must not be configured that way.

For an authorized development rollback, extract scripts/runtime.py from a trusted Git SHA to a temporary file and invoke `python3 <trusted-runner> rollback <previous-known-good-sha>`. It accepts only an existing intact release, validates smoke, then switches pointers. No automatic production rollback is implemented. Investigate detected drift before rollback; the runner does not silently repair corrupted files.

## Migration policy

Migration files are versioned in Git and become immutable once released. Correct a released schema using a new migration, never by silently rewriting history. CI rehearses from empty PostgreSQL 17. Development migration execution may be added only after CI validation and separate review; the current hook explicitly refuses executable domain migrations until implemented. Destructive migrations require explicit data/recovery handling. Production migration requires human release approval. Clinical Evidence approval/knowledge activation is always separate from code delivery.

References: [GitHub workflow_run behavior/security](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run), [PostgreSQL services](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers), [setup-uv](https://github.com/astral-sh/setup-uv/tree/v6).
