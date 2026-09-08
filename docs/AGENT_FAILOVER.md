# Writer failover

Frozen priority: codex -> glm -> minimax -> kimi. Nemotron remains QA. A failed API request or exhausted harness session never automatically transfers writer ownership.

## Engineering harness chain

Codex + GPT-6 Astra is the primary engineering harness (writer `codex`). OpenCode + GLM 5.3 is the first fallback harness (writer `glm`); OpenCode + MiniMax-M3 (Nebius) is the second fallback harness (writer `minimax`). GLM 5.3 and MiniMax-M3 are not Codex model-brain fallback profiles: each fallback runs in the independent OpenCode harness with its own writer identity.

Switching from Codex to OpenCode is therefore an explicit writer handoff (codex -> glm, then glm -> minimax if the first fallback is also unavailable), never a silent model swap behind one harness. The handoff preserves the same task, branch, base/HEAD SHA, Git-backed memory, reports and deterministic coordinator state: the task keeps its recorded base SHA, the replacement writer resumes at the exact recorded checkpoint (HEAD) SHA on the task branch, and no shared state is forked or lost. See [engineering harnesses](ENGINEERING_HARNESSES.md).

## Human-approved writer handoff

Use this procedure for any execution-environment/writer switch, including switching Codex to OpenCode:

1. Stop the old writer session and revoke its write access. Preserve uncommitted work. The writer/owner must make a meaningful authorized checkpoint; do not reset or discard pending edits.
2. Confirm the old task worktree is clean at the task's recorded commit_sha. Produce a handoff details YAML with last_commit_sha, completed_work, remaining_work, tests_passed, tests_failed, known_issues, files_touched, forbidden_changes and next_action. No secrets or giant transcripts.
3. Obtain explicit human approval naming the old/new writer, checkpoint and scope. The `--human-approved` flag records that prior approval; it does not obtain it or authenticate a human.
4. Run `./scripts/task-handoff.sh TASK-001 --new-writer glm --details /path/to/reviewed-handoff.yaml --human-approved`. The coordinator checks the clean old worktree and exact checkpoint, creates/continues agent/glm/TASK-001 from that exact checkpoint SHA while preserving the task's recorded base SHA, then atomically changes active_writer and production_writer. The handoff record captures the preserved base and checkpoint SHAs. It never launches a new writer process.
5. The task retains append-only handoff records including old/new branches, writers and timestamp. ops/reports/<task-id>/handoff.md is a human-readable projection. If that projection write fails, reconstruct it from the task YAML; do not repeat the ownership transfer blindly.
6. Build new canonical context and confirm the permission banner before granting the replacement write access. The old writer's implementation writes are now rejected by write/submit gates. Preserve all previous report authorship.

A worktree already occupied by another task or a different checkpoint is rejected. The operator must archive/finish that worktree explicitly; tooling never forces checkout, deletes branches or overwrites dirty files.

If the replacement writer normally performs one of the independent review roles (GLM/MINIMAX/KIMI), it cannot approve its own stage. A separate human review with explicit evidence is required at that stage; do not relabel the writer's output as an independent review. Other role ownership remains fixed. Clinical approval is never part of writer failover.
