# FOUNDATION-DRYRUN-001 — prepared, not executed

No provider outputs or reviewer PASS statuses have been produced. This is a harmless engineering rehearsal, not a clinical task.

1. Human approves/integrates the foundation and records the latest approved main SHA in the prepared task. Provision worktrees, access separation and provider credentials through the operator workflow.
2. Create the five role worktrees with setup-worktrees.sh TASK_ID --approved-sha SHA --role ROLE. No session is launched automatically.
3. Move created -> research. KIMI investigates a harmless text-fixture change and writes kimi-analysis.md with ANALYSIS_COMPLETE or BLOCKED, findings and references.
4. Mirror the committed role report into canonical context via agent-submit or have the operator import the reviewed report. Advance to implementation only after actual successful analysis.
5. CODEX writes tests/fixtures/foundation-dryrun.txt with harmless text, runs foundation checks and makes an authorized checkpoint. Do not use clinical content.
6. Reviewers inspect the exact writer checkpoint (read-only writer worktree or Git diff), each writing only its report: qwen-crosscheck.md, glm-review.md, nemotron-qa.md. Use context --code from the appropriate checkout; never copy raw provider transcripts into Git.
7. Advance crosscheck -> review -> qa. Any failed review sends the task to fixes and repeats crosscheck/review/QA. CODEX alone changes the implementation fixture.
8. Run foundation/integration checks, record CI-ready evidence, advance to ci then awaiting_human. CODEX writes final-summary.md with actual results and remaining limitations. Stop for approval. No merge or deployment is implied.

Expected durable paths: kimi-analysis.md, qwen-crosscheck.md, glm-review.md, nemotron-qa.md, final-summary.md; handoff.md exists only if a real approved handoff occurs. Do not prepopulate these files with fabricated results.
