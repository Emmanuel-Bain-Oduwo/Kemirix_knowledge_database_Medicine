# Current state

Final engineering foundation correction on branch agent/codex/FOUNDATION-001 (base checkpoint dd3cb34), uncommitted and awaiting owner review. This final correction fixes the execution model: Codex + GPT-6 Astra is the primary engineering harness; OpenCode + GLM 5.3 is the first fallback harness; OpenCode + Qwen 3.8 is the second fallback harness; switching Codex to OpenCode is an explicit writer handoff. No real domain implementation or external execution is claimed.

## IMPLEMENTED

- Main-only git model: develop/staging/release/environment-branch assumptions removed from workflows, scripts, coordinator, git helpers, task models, worktree tooling, deployment tooling, memory, documentation and tests. `main` is the only permanent branch; work flows main -> agent/<agent>/<task-id> -> checkpoint commits -> PR -> automated gates -> automatic squash merge -> automatic OVH development CD.
- Agent role contracts; strict task schema (now with `research_required` so Kimi research is required only where relevant); deterministic coordinator; gated path ownership; file lock; canonical context and atomic lifecycle updates.
- Deterministic mechanical merge gate (coordinator `merge-gate`): correct task, valid contract, expected branch/base SHA on main, active writer, required reports, Qwen/GLM/Nemotron results, required tests, CI pass, no unresolved blockers — fails closed; no LLM decides it.
- Human-approved checkpoint handoff, explicit checkpoint/PR scripts (agent-submit.sh refuses main and non-task branches; agent-open-pr.sh targets main only, reuses existing PRs, optional squash auto-merge that never bypasses CI), safe worktree setup and harmless five-agent dry-run preparation. A harness switch (Codex to OpenCode) is an explicit writer handoff that preserves the same task, branch, base/HEAD SHA, Git-backed memory, reports and deterministic coordinator state.
- Engineering harness chain (src/agents/harness.py): Codex + GPT-6 Astra primary harness, OpenCode + GLM 5.3 first fallback harness, OpenCode + Qwen 3.8 second fallback harness; KEMIRIX_ENGINEERING_HARNESS selection; the fallback order matches the frozen writer priority prefix (codex -> glm -> qwen); switching harnesses is always an explicit writer handoff; no keys in Git.
- Provider smoke validation is structural (non-empty choices/message, content or reasoning_content, or Cloudflare result.response); no exact-phrase requirement. Nebius/Cloudflare adapters; bounded public HTTPS research with disabled search backend.
- Exact-Git development release/deployment/verification code, drift detection, pointer recovery and explicit pending migration gate — all main-anchored.

## LOCALLY_VALIDATED

- 111 local tests passed: 108 foundation/unit and 3 isolated integration tests (temporary Git/worktree/release fixtures only). Ruff check and ruff format --check passed; `git diff --check` clean; configuration validation and common-pattern secret scan passed; migration gate reports 0 executable / 3 pending files.
- Merge-gate fail-closed behavior, reviewer report ownership, writer ownership, context ordering, main-only branch validation, main submit rejection, task-branch requirement, harness-chain writer-handoff mapping, handoff base/checkpoint SHA preservation with post-handoff merge-gate continuity, structural provider response validation (including the reported GLM/Cloudflare 200 "CONNECT" case), runtime SHA validation, drift detection, disabled research provider and secret redaction are all covered by tests.

## CONFIGURED

- Python 3.12, uv 0.12.10, Pydantic 2/httpx/PyYAML, pytest/Ruff and lockfile.
- GitHub-hosted CI (main-only triggers) with PostgreSQL 17; workflow_run development deployment definition triggered by successful main-push CI runs. Neither hosted workflow has been executed here.
- GitHub deployment secrets contract: KEMIRIX_DEV_VM_HOST, KEMIRIX_DEV_VM_USER, KEMIRIX_DEV_VM_SSH_KEY, KEMIRIX_DEV_VM_KNOWN_HOSTS. Actual secret values are VM/operator-side only.
- Engineering harness selection via the KEMIRIX_ENGINEERING_HARNESS environment variable; documented in docs/ENGINEERING_HARNESSES.md. OpenCode harness configuration lives in opencode.json with the Cloudflare credential referenced by environment variable only (no secret values in Git).

## PENDING_EXTERNAL_EXECUTION

- Hosted GitHub CI PASS, GitHub auto-merge enablement + required checks + main branch protection (one-time repository configuration, not yet performed), actual GitHub-to-OVH deployment, real provider smoke tests, fallback harness execution, worktree initialization, five-agent rehearsal, DBeaver verification.

## PLACEHOLDER

- migrations/001_kmx.sql, 002_evidence.sql, 003_rules.sql remain unchanged comments, explicitly pending/non-executable. CI reports them as pending/not executable.
- Domain packages, adapter directories and ingest/resolve/build entry points remain scaffolding.
- Development migration execution is a refusing future hook; domain contract tests await real migration implementation.

## NOT STARTED / NOT EXECUTED

KMX, Clinical Evidence, Rules and S01–S27 integrations. The legacy `develop` branch still exists in GitHub/local refs and must be deleted by the owner once main-only operation is confirmed.

See PHASE_STATUS.yaml and KNOWN_ISSUES.md for precise gates. Implementation presence is not an external PASS: hosted CI, auto-merge, real GitHub→OVH deployment and fallback harnesses are not claimed as passing until they actually occur.
