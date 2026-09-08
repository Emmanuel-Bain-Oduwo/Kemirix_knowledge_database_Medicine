# Current state

FOUNDATION-CLOSEOUT-001 tightens the mechanical agent gate and corrects engineering
memory on agent/codex/FOUNDATION-CLOSEOUT-001. No checkpoint, PR or merge is
performed by this task before the owner's next instruction.

## Proven delivery execution

PR creation, automatic squash merge, main CI and exact-SHA development deployment
executed successfully in the automation rehearsal, as confirmed by the owner.
Repository history includes AUTOMATION-REHEARSAL-001 (#2), main checkpoint 7882b81.
These results prove the engineering delivery path. They do not prove completion
of the full five-agent external rehearsal or current repository protection settings.

## Implemented and locally validated

The foundation provides task ownership, deterministic coordination, checkpoint/PR
tooling, writer handoff, provider adapters, safe research boundaries, exact-SHA
runtime deployment/verification and main-only delivery. Codex is the primary
writer harness; OpenCode GLM then Qwen are fallback harnesses requiring explicit
writer handoff. The ordinary hosted CI job remains `foundation`.

The closeout gate requires reports bound to the task and reviewed checkpoint,
correct branch/base/head and ancestry, all required tests, CI and an eligible
lifecycle state. Missing or unverifiable conditions cannot produce MERGE_READY.
The local coordinator consumes operator CI/test attestations. The separate
`agents.publish_gate` command verifies live PR/CI identity, executes required safe
tests and publishes `kemirix-agent-gate` only after MERGE_READY. It is locally
tested with mocked GitHub calls; external publication is not executed here.
Local synthetic regression tests are not external provider PASS reports.

Closeout validation: `uv run --frozen pytest -q` passed all 260 tests (257
foundation/unit and 3 isolated integration). Frozen dependency sync, Ruff lint and
format checks, configuration validation, common-pattern secret scan and
`git diff --check` passed. Migration status is 0 executable / 3 pending. The code
is ready for the checkpoint command; no commit, publication, PR or merge was run.

## Pending

- Full five-agent external rehearsal: prepared, not executed. No provider PASS
  reports are fabricated. Real provider smoke calls, fallback execution and
  reviewer access separation remain pending verification.
- Owner-side main protection, required-check configuration, automatic head-branch
  deletion and old branch cleanup after this code checkpoint. Successful automatic
  merge does not establish those settings.
- Full worktree setup and DBeaver verification remain unverified; the active Codex
  task worktree exists.
- Phase 1 readiness remains blocked pending external agent validation and owner review.

## Domain scope

Migrations remain three non-executable placeholders. KMX, Clinical Evidence, Rules
and S01–S27 integrations remain not started. No domain implementation, clinical
approval or production deployment is claimed.
