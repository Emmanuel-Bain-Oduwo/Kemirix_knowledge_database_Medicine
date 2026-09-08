# Engineering foundation 0A–0F local validation

Status: ready for human review, uncommitted. Phase 1 KMX implementation is NOT READY to start until owner approval and the outstanding external/configuration gates are resolved.

## Actual local results

- Python 3.12.3 / uv 0.12.10; frozen dependency sync and lockfile check passed.
- 84 tests passed: 81 foundation/unit and 3 isolated engineering integration tests.
- Ruff lint and format checks passed.
- Configuration validation covers 27 source contracts and strict task contracts.
- Common-pattern secret/file scan passed; this is not a guarantee against all possible secret formats. A blank-value/newline false positive was corrected with a regression test.
- Workflow YAML/security assertions and bash syntax checks passed. This is local validation, not a hosted Actions execution.
- Migration suite: 0 executable files, 3 pending placeholders. No domain SQL was executed or edited.
- Read-only status/context CLI returned the prepared task and correct KIMI report-only permission banner.
- Temporary Git/worktree/release integration tests proved exact-object extraction, conflict preservation, three-release retention, stale-SHA rejection, rollback and failed-switch recovery. Network/dependency installation for the release rehearsal was simulated; no real development runtime was touched.

## External status

| Operation | Status |
| --- | --- |
| Hosted GitHub CI / PostgreSQL 17 service | Pending |
| Development deployment workflow | Implemented, not executed |
| Real Codex/provider smoke suite | Pending; HTTP tests used mocks |
| Worktree provisioning | Tooling implemented, real paths not initialized |
| Five-agent dry run | Prepared, not executed; no reports fabricated |
| DBeaver verification | Pending |
| KMX / Evidence / Rules / adapters | Not started |

## Decisions and required human setup

GitHub owns code/config/tests/memory; Object Storage owns immutable raw originals; Managed PostgreSQL owns normalized knowledge. The VM executes only. Deterministic tooling controls task ownership; models never approve clinical knowledge. Checkpoints are explicit and exact-file scoped. Development deployment uses the successful main CI head SHA and Git archive, never dirty checkout copies. Search is disabled by default; public fetch remains untrusted engineering input. Follow-up is retained as source-backed Evidence/Rule content, never a category.

Final foundation correction (FOUNDATION-001 follow-up): the branch model is now main-only (no develop branch); routine PRs auto-merge with squash when gates pass; development CD deploys validated main SHAs; provider smoke validation is structural; the engineering harness chain is Codex + GPT-6 Astra (primary), OpenCode + GLM 5.3 (first fallback) and OpenCode + Qwen 3.8 (second fallback), with harness switching as an explicit writer handoff preserving task, branch, base/HEAD SHA, memory, reports and coordinator state. See ops/memory/DECISIONS.md D012+ and docs/CI_CD.md.

Before Phase 1: approve/review/checkpoint this foundation; configure protected branches/required CI and the development environment; configure the four SSH secrets, verified host keys and dedicated deploy/agent permissions; provision the trusted bare repository and runtime paths; run hosted CI, actual provider smoke tests, development verification and the five-agent rehearsal; update the dry-run base SHA; reconcile documented source-ID/schema contracts. Do not weaken secret-file permissions. See KNOWN_ISSUES.md and the operating documents for exact steps.

The actual repository has no new commit or staged changes. No push, PR creation, deployment, source acquisition or provider API call was performed by this implementation task. Synthetic Git objects exist only in temporary test directories.

## Git status

```text
 M .gitignore
 M config/sources/12_kenya_moh.yaml
 M ops/agents/AGENTS.md
 M ops/agents/CODEX.md
 M ops/agents/GLM.md
 M ops/agents/KIMI.md
 M ops/agents/NEMOTRON.md
 M ops/agents/QWEN.md
 M ops/memory/CURRENT_STATE.md
 M ops/memory/DECISIONS.md
 M ops/memory/INVARIANTS.md
 M ops/memory/KNOWN_ISSUES.md
 M ops/memory/PHASE_STATUS.yaml
 M ops/memory/SOURCE_STATUS.yaml
 M ops/tasks/TEMPLATE.yaml
 M pyproject.toml
?? .github/workflows/ci.yml
?? .github/workflows/deploy-dev.yml
?? config/migration_suite.yaml
?? docs/AGENT_COORDINATION.md
?? docs/AGENT_FAILOVER.md
?? docs/AGENT_MEMORY.md
?? docs/CI_CD.md
?? docs/DEVELOPMENT_WORKFLOW.md
?? docs/OPERATING_MODEL.md
?? docs/RESEARCH_GATEWAY.md
?? ops/providers/README.md
?? ops/reports/FOUNDATION-DRYRUN-001/README.md
?? ops/reports/RESEARCH_TEMPLATE.md
?? ops/reports/foundation-validation.md
?? ops/tasks/FOUNDATION-DRYRUN-001.yaml
?? scripts/agent-open-pr.sh
?? scripts/agent-submit.sh
?? scripts/deploy-dev.sh
?? scripts/migration_gate.py
?? scripts/provider-smoke-test.py
?? scripts/runtime.py
?? scripts/scan-secrets.py
?? scripts/setup-worktrees.sh
?? scripts/task-finish.sh
?? scripts/task-handoff.sh
?? scripts/task-start.sh
?? scripts/task-status.sh
?? scripts/validate_config.py
?? scripts/verify-runtime.sh
?? src/agents/__init__.py
?? src/agents/checkpoint.py
?? src/agents/context.py
?? src/agents/coordinator.py
?? src/agents/gitops.py
?? src/agents/memory.py
?? src/agents/models.py
?? src/agents/providers.py
?? src/agents/research.py
?? src/agents/security.py
?? src/agents/tasks.py
?? tests/test_agents.py
?? tests/test_foundation.py
?? tests/test_runtime.py
?? uv.lock
```

## git diff --stat (tracked files only)

```text
 .gitignore                       |   6 +++
 config/sources/12_kenya_moh.yaml |   2 +-
 ops/agents/AGENTS.md             |  17 ++++++
 ops/agents/CODEX.md              |  11 ++++
 ops/agents/GLM.md                |  11 ++++
 ops/agents/KIMI.md               |  11 ++++
 ops/agents/NEMOTRON.md           |  11 ++++
 ops/agents/QWEN.md               |  11 ++++
 ops/memory/CURRENT_STATE.md      |  31 +++++++++++
 ops/memory/DECISIONS.md          |  34 ++++++++++++
 ops/memory/INVARIANTS.md         |  15 ++++++
 ops/memory/KNOWN_ISSUES.md       |  17 ++++++
 ops/memory/PHASE_STATUS.yaml     |  25 +++++++++
 ops/memory/SOURCE_STATUS.yaml    | 110 +++++++++++++++++++++++++++++++++++++++
 ops/tasks/TEMPLATE.yaml          |  38 ++++++++++++++
 pyproject.toml                   |  22 +++++++-
 16 files changed, 370 insertions(+), 2 deletions(-)
```

Untracked new files are excluded from git diff --stat. Full inventory below includes preserved Phase 0A work.

## Modified tracked files

- `.gitignore`
- `config/sources/12_kenya_moh.yaml`
- `ops/agents/AGENTS.md`
- `ops/agents/CODEX.md`
- `ops/agents/GLM.md`
- `ops/agents/KIMI.md`
- `ops/agents/NEMOTRON.md`
- `ops/agents/QWEN.md`
- `ops/memory/CURRENT_STATE.md`
- `ops/memory/DECISIONS.md`
- `ops/memory/INVARIANTS.md`
- `ops/memory/KNOWN_ISSUES.md`
- `ops/memory/PHASE_STATUS.yaml`
- `ops/memory/SOURCE_STATUS.yaml`
- `ops/tasks/TEMPLATE.yaml`
- `pyproject.toml`

## New untracked files

- `.github/workflows/ci.yml`
- `.github/workflows/deploy-dev.yml`
- `config/migration_suite.yaml`
- `docs/AGENT_COORDINATION.md`
- `docs/AGENT_FAILOVER.md`
- `docs/AGENT_MEMORY.md`
- `docs/CI_CD.md`
- `docs/DEVELOPMENT_WORKFLOW.md`
- `docs/OPERATING_MODEL.md`
- `docs/RESEARCH_GATEWAY.md`
- `ops/providers/README.md`
- `ops/reports/FOUNDATION-DRYRUN-001/README.md`
- `ops/reports/RESEARCH_TEMPLATE.md`
- `ops/reports/foundation-validation.md`
- `ops/tasks/FOUNDATION-DRYRUN-001.yaml`
- `scripts/agent-open-pr.sh`
- `scripts/agent-submit.sh`
- `scripts/deploy-dev.sh`
- `scripts/migration_gate.py`
- `scripts/provider-smoke-test.py`
- `scripts/runtime.py`
- `scripts/scan-secrets.py`
- `scripts/setup-worktrees.sh`
- `scripts/task-finish.sh`
- `scripts/task-handoff.sh`
- `scripts/task-start.sh`
- `scripts/task-status.sh`
- `scripts/validate_config.py`
- `scripts/verify-runtime.sh`
- `src/agents/__init__.py`
- `src/agents/checkpoint.py`
- `src/agents/context.py`
- `src/agents/coordinator.py`
- `src/agents/gitops.py`
- `src/agents/memory.py`
- `src/agents/models.py`
- `src/agents/providers.py`
- `src/agents/research.py`
- `src/agents/security.py`
- `src/agents/tasks.py`
- `tests/test_agents.py`
- `tests/test_foundation.py`
- `tests/test_runtime.py`
- `uv.lock`
