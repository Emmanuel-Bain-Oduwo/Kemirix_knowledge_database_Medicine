# Development workflow

1. Read SKILL.md, invariants, decisions/current state/phase status, role and task contract. Preserve existing uncommitted work. Confirm task ID, role, phase, active writer, permissions, allowed/forbidden paths and exact base SHA.
2. Complete ops/tasks/TEMPLATE.yaml and create the contract through the coordinator under owner control. Approve a develop SHA explicitly. Task-start fetches develop and requires that approved SHA still be its latest head; it never silently rebases the task.
3. Create a task worktree using task-start or setup-worktrees, selecting one of codex/kimi/qwen/glm/nemotron. Paths are /srv/kemirix/worktrees/<agent>; branches are agent/<agent>/<task-id>. Existing conflicting/dirty worktrees are rejected. Never edit /srv/kemirix/runtime/development from these worktrees.
4. KIMI researches and reports; the active writer implements only its assigned scope; QWEN cross-checks, GLM reviews and NEMOTRON tests adversarial cases. Report owners do not overwrite one another. Use canonical context and the write/submit gates. See AGENT_COORDINATION.md for the lifecycle.
5. Run safe local checks in CI_CD.md. Submit meaningful checkpoints only after authorization, using staged or explicitly named intended files. Reviews reference the exact checkpoint. Use separate draft PR creation, never auto-merge. Owner/integrator incorporates reviewed canonical task/memory/report updates into Git.
6. Successful hosted CI and independent review permit owner-approved PR merge into develop. The tested develop SHA deploys through the development workflow. Record actual CI/deployment references and verification output before updating pass states. Main/release and production migrations remain human-controlled.

Existing tmux sessions are named codex, kimi, qwen, glm and nemotron. `tmux attach -t codex` attaches to the relevant session; use the matching worktree and confirm task context after reconnecting. tmux is convenience only: task YAML, reports and Git checkpoints preserve state if sessions die. Do not run two production writer sessions for one task.

For the prepared FOUNDATION-DRYRUN-001, read ops/reports/FOUNDATION-DRYRUN-001/README.md. Its recorded base is the pre-foundation repository commit; after this foundation is approved and integrated, the owner must update the prepared task to the exact approved develop SHA before creating worktrees. Uncommitted files are never copied into worktrees or deployment releases.

Current task stopping rule: do not commit, push, create real provider sessions or deploy. Present the complete diff and local validation; wait for human approval. After approval, complete pending external setup/checks before declaring Phase 1 ready. Domain source-ID/schema questions remain tracked in KNOWN_ISSUES.md.
