# Deterministic agent coordination

The Python coordinator is foreground deterministic software, not an AI authority. It loads canonical memory, validates a strict task, calculates ownership, provides context and records lifecycle state. No daemon, database queue or broker is used.

| Agent | Responsibility | Own report | Output contract |
| --- | --- | --- | --- |
| CODEX | Primary implementation writer | final-summary.md | Factual checkpoint and validation |
| KIMI | Source/data analyst | kimi-analysis.md | ANALYSIS_COMPLETE or BLOCKED |
| QWEN | Independent cross-check | qwen-crosscheck.md | PASS or REQUEST_CHANGES |
| GLM | Architecture/code review | glm-review.md | PASS or REQUEST_CHANGES; CRITICAL/MAJOR/MINOR |
| NEMOTRON | Adversarial QA | nemotron-qa.md | QA_PASS or QA_FAIL |

All report paths are under ops/reports/<task-id>/. Reports begin with the status on the first line and include findings and check evidence. No reviewer may approve Clinical Evidence. Reports are not fabricated or populated with passing statuses before a real review.

Task lifecycle:

```text
created -> research -> implementation -> crosscheck -> review -> qa
                                                        |       |
                                                        +-> fixes -> crosscheck
qa -> ci -> awaiting_human -> merged -> deployed -> verified -> closed
```

Crosscheck/review/QA can request fixes; fixes repeat independent reviews. Missing or failed reports block advancement. For merge/deploy/verify/close, explicit human attestation and exact commit/deployed SHAs are required. The CLI records attested evidence; it does not independently query GitHub or deploy as a side effect of a status update. The operator must provide actual verification references, not invented PASS claims.

Task YAML records one production_writer/active_writer, researcher, cross_checker, reviewer, validator, frozen writer priority, allowed/forbidden paths, exact base SHA, branch, criteria/tests, timestamps, status and commit/deployed SHAs. Path scopes use exact files or directory prefixes, never arbitrary globs or repository-wide ownership. Required test profiles are foundation, integration and contract; commands from model-written YAML are never executed as shell code.

The active writer can write assigned implementation paths only during implementation/fixes. Everyone owns only their designated report otherwise. `coordinator write` requires the matching branch and validates the destination; submit rechecks all intended changed paths against the shared contract. Symlinks, path traversal, runtime paths and protected governance writes are refused. Locks serialize gated writes and state changes.

These gates enforce operations routed through the tooling. They cannot sandbox an independently launched unrestricted shell under the same Unix user. Before real multi-provider writers run, the operator must restrict external agents to gated file operations/read-only worktrees or separate OS users/permissions; reviewers must not receive a general production-editing shell. Human approval flags are operator attestations, not an authentication mechanism. Never expose handoff/transition commands as autonomous model tools. Only one production writer process may run; stop/revoke its session before human-approved handoff. See [failover](AGENT_FAILOVER.md).

CLI examples (after foundation approval and integration):

```sh
uv run python -m agents.coordinator create /path/to/completed-contract.yaml
./scripts/task-status.sh TASK-001
./scripts/task-start.sh TASK-001 --approved-sha <full-approved-develop-sha> --role codex
./scripts/task-finish.sh TASK-001 --to research --evidence 'Task scope reviewed by owner'
```

The five-agent harmless rehearsal is prepared in ops/tasks/FOUNDATION-DRYRUN-001.yaml. Follow its report-directory README. No provider was invoked to create it, and no review result is implied.
