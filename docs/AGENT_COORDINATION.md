# Deterministic agent coordination

The Python coordinator is foreground deterministic software, not an AI authority. It loads canonical memory, validates a strict task, calculates ownership, provides context and records lifecycle state. No daemon, database queue or broker is used.

| Agent | Responsibility | Own report | Output contract |
| --- | --- | --- | --- |
| CODEX | Primary implementation writer | final-summary.md | Factual checkpoint and validation |
| KIMI | Source/data analyst | kimi-analysis.md | ANALYSIS_COMPLETE or BLOCKED |
| MINIMAX | Independent cross-check | minimax-crosscheck.md | PASS or REQUEST_CHANGES |
| GLM | Architecture/code review | glm-review.md | PASS or REQUEST_CHANGES; CRITICAL/MAJOR/MINOR |
| NEMOTRON | Adversarial QA | nemotron-qa.md | QA_PASS or QA_FAIL |

All report paths are under ops/reports/<task-id>/. Reports begin with the status on the first line and include findings and check evidence. No reviewer may approve Clinical Evidence. Reports are not fabricated or populated with passing statuses before a real review. The engineering harness chain is Codex + GPT-6 Astra (primary), OpenCode + GLM 5.3 (first fallback) and OpenCode + MiniMax-M3 (second fallback); switching harnesses is an explicit human-approved writer handoff that preserves the same task, branch, base/HEAD SHA, Git-backed memory, reports and deterministic coordinator state (see [failover](AGENT_FAILOVER.md)).

Task lifecycle:

```text
created -> research -> implementation -> crosscheck -> review -> qa
                                                        |       |
                                                        +-> fixes -> crosscheck
qa -> ci -> awaiting_human -> merged -> deployed -> verified -> closed
```

Crosscheck/review/QA can request fixes; fixes repeat independent reviews. Kimi research is required only when the task contract declares `research_required: true`. Missing or failed reports block advancement. The coordinator also provides a deterministic `merge-gate` command that mechanically evaluates PR merge-readiness (correct task, valid contract, expected branch/base SHA, active writer, required reports, MiniMax/GLM/Nemotron results, required tests, CI pass, no unresolved blockers) and fails closed; no LLM decides the mechanical gate. For merge/deploy/verify/close transitions, explicit human attestation and exact commit/deployed SHAs are required. The CLI records attested evidence; it does not independently query GitHub or deploy as a side effect of a status update. The operator must provide actual verification references, not invented PASS claims.

Task YAML records one production_writer/active_writer, researcher, cross_checker, reviewer, validator, frozen writer priority, allowed/forbidden paths, exact base SHA, branch, criteria/tests, timestamps, status and commit/deployed SHAs. Path scopes use exact files or directory prefixes, never arbitrary globs or repository-wide ownership. Required test profiles are foundation, integration and contract; commands from model-written YAML are never executed as shell code.

`SKILL.md` is protected for every task by default. The single sanctioned exception is an explicit owner-approved synchronization: a `phase_0` `FOUNDATION-` bootstrap task whose contract sets `owner_approved_skill_update: true` may list exactly `SKILL.md` in allowed_paths and write it through the normal gated flow; the flag, the phase and the task-id prefix must all be present and the change still passes the full review chain. Forbidden paths always win over the exception.

A tightly scoped phase 0 exception exists for the foundation bootstrap only: a task with `phase: phase_0`, a `FOUNDATION-` task ID and its matching `agent/<writer>/FOUNDATION-*` branch may own the engineering-governance files it must build (`ops/agents`, `ops/memory` except INVARIANTS.md, `ops/tasks`, `.github/workflows` and explicitly assigned non-report artifacts under `ops/reports`). The exception never covers `SKILL.md`, `ops/memory/INVARIANTS.md`, `.git`, `.env`, `migrations`, `src/kmx`, `src/evidence`, `src/rules` or `src/sources`, and role reports stay independently owned. Ordinary tasks, subphases such as `phase_0a` and later phases keep the full governance restriction. `coordinator create` fills status, timestamps and lifecycle bookkeeping automatically, so a submitted task contract is always schema-valid before any checkpoint.

The active writer can write assigned implementation paths only during implementation/fixes. Everyone owns only their designated report otherwise. `coordinator write` requires the matching branch and validates the destination; submit rechecks all intended changed paths against the shared contract. Symlinks, path traversal, runtime paths and protected governance writes are refused. Locks serialize gated writes and state changes.

These gates enforce operations routed through the tooling. They cannot sandbox an independently launched unrestricted shell under the same Unix user. Before real multi-provider writers run, the operator must restrict external agents to gated file operations/read-only worktrees or separate OS users/permissions; reviewers must not receive a general production-editing shell. Human approval flags are operator attestations, not an authentication mechanism. Never expose handoff/transition commands as autonomous model tools. Only one production writer process may run; stop/revoke its session before human-approved handoff. See [failover](AGENT_FAILOVER.md).

CLI examples (after foundation approval and integration):

```sh
uv run python -m agents.coordinator create /path/to/completed-contract.yaml
./scripts/task-status.sh TASK-001
./scripts/task-start.sh TASK-001 --approved-sha <full-approved-main-sha> --role codex
./scripts/task-finish.sh TASK-001 --to research --evidence 'Task scope reviewed by owner'
uv run python -m agents.coordinator merge-gate TASK-001 \
  --branch agent/codex/TASK-001 --base-sha <full-sha> --head-sha <full-sha> \
  --ci-pass --test-result foundation
```

The five-agent harmless rehearsal is prepared in ops/tasks/FOUNDATION-DRYRUN-001.yaml. Follow its report-directory README. No provider was invoked to create it, and no review result is implied.

## Exact-checkpoint merge gate

Gate reports must contain exactly one `Task-ID: <task-id>` line and exactly one
`Head-SHA: <40-character-reviewed-checkpoint>` line and `Role: <role>` line,
in addition to the status, nonempty `Findings:` and `Checks:` evidence
(`References:` for Kimi). Missing, duplicate, wrong-task and stale-SHA
bindings fail closed. These are reviewer-owned reports in the control checkout;
do not manufacture PASS files or embed a commit's own SHA into that commit.
Refresh independent reports after changing the reviewed checkpoint.

Readiness requires the supplied head to match the task checkpoint and descend
from its recorded base, with that base on fetched main. Only `ci` and
`awaiting_human` are merge-eligible; implementation, fixes, unfinished review and
already merged/deployed/closed states cannot authorize another merge. All required
test profiles and CI must be explicitly true. The CLI exits nonzero on NOT_READY
or unverifiable setup. Its CI/test flags are exact-checkpoint operator attestations,
not independent hosted verification; `foundation` remains the ordinary CI check.

Use `python -m agents.publish_gate` from a trusted operator session to publish
`kemirix-agent-gate` for GitHub merge readiness (see [CI/CD](CI_CD.md)). It reads
the canonical task/reports, verifies live PR and foundation CI identity, executes
required safe tests against a clean exact PR checkout, and publishes success only
after MERGE_READY and final identity/CI rechecks. It accepts no CI/test PASS flags.
The owner configures both required checks after this checkpoint. Publishing must
wait for real independent review; a local synthetic test PASS is not a provider
report. The publisher is implemented here but is not externally invoked by this
closeout task.
