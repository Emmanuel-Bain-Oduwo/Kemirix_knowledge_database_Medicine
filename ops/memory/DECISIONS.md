# Decision record

## D001 — Authority and operational boundaries (2026-09-07)
Accepted from the owner's frozen instructions: GitHub owns code/config/tests, OVH Object Storage owns immutable raw sources, and OVH Managed PostgreSQL owns normalized knowledge. The VM is replaceable execution infrastructure. See INVARIANTS.md.

## D002 — Phase 0 scope (2026-09-07)
Prepare engineering operations and CI only. Runtime packages, source adapters and the three migration placeholders remain untouched. Owner approval is required before moving into production KMX implementation. Phase 0 here is an engineering preparation stage preceding SKILL.md's domain execution sequence.

## D003 — Coordination (2026-09-07)
CODEX is the primary implementation engineer; KIMI analyzes sources/data, QWEN independently cross-checks engineering, GLM reviews architecture/code, NEMOTRON performs adversarial QA. Assign exactly one writer per task and separate engineering review from human clinical approval.

## D004 — Reproducible checks (2026-09-07)
Use Python 3.12, uv with a committed lockfile, ruff and pytest. CI runs configuration validation and applies ordered migration files to a fresh PostgreSQL 17 service. Comment-only migrations prove runner plumbing only, not schema readiness. No deployment or production credentials in CI.

## D005 — Category correction (2026-09-07)
Remove `follow_up` from S12's configured categories to comply with the fixed 24-category vocabulary. Follow-up remains source-backed Evidence/Rule content. No adapter or clinical logic is added.

## D006 — Honest status (2026-09-07)
Keep the owner-supplied phase statuses unchanged: infrastructure passes are operator-reported, CI and provider smoke tests remain pending. Configuration presence and local checks do not prove deployed services or GitHub branch protection.

## D007 — Foundation 0B–0F (2026-09-07)
Supersedes the narrow implementation scope of D002 while preserving all domain exclusions. Add deterministic foreground coordination, shared Git-backed task/memory/report contracts, explicit checkpoints and exact-SHA development deployment. No actual commit/push/provider call/deployment is authorized in this implementation task.

## D008 — Provider and research boundaries (2026-09-07)
Codex is an external CLI writer with separate ChatGPT authentication. KIMI/NEMOTRON use Nebius; GLM/QWEN use Cloudflare. Preserve owner-specified model IDs until real availability is checked. Search defaults disabled; public HTTPS fetch is bounded and untrusted. Neither provider output nor web research approves clinical knowledge.

## D009 — One writer and human failover (2026-09-07)
Writer priority is codex, glm, qwen, kimi; Nemotron remains QA. Task ownership and shared lifecycle updates use deterministic gates and local file locking. Handoff requires a stopped writer, exact clean checkpoint and human approval. External Unix/process access controls remain necessary to prevent bypass of CLI gates.

## D010 — Honest migration and deployment gates (2026-09-07)
Supersedes D004's comment-only migration execution: CI explicitly reports the three migrations pending/non-executable. Future declared executable migrations must form an ordered prefix and run from an empty PostgreSQL 17 database. Development delivery uses only the successful CI head SHA (develop-based delivery superseded by D012/D015: main-only), immutable Git extraction and integrity verification. Code delivery never activates clinical knowledge.

## D011 — Release retention and failure recovery (2026-09-07)
Retain all development releases initially (at least three) rather than adding destructive pruning. Pointer replacements are individually atomic; mismatches fail closed. Preserve incomplete releases for operator quarantine. No automatic production rollback or production migration is implemented.

## D012 — Main-only git model (2026-09-07)
There is one permanent branch only: main. All develop/staging/release/environment-branch assumptions are removed from workflows, scripts, coordinator, git helpers, task models, worktree tooling, deployment tooling, memory, documentation and tests. Normal work: main -> temporary agent/<agent>/<task-id> branch -> checkpoint commits -> PR -> automated gates -> automatic squash merge -> main -> automatic OVH development deployment. The legacy develop branch ref must be deleted in GitHub once main-only operation is confirmed (one-time owner action).

## D013 — Model brains are not writer handoffs (2026-09-07)
The Codex CLI is the engineering execution harness. Changing the model brain behind it (GPT-6 Astra default; GLM 5.3, Qwen 3.8 27B, Kimi K3 fallbacks; Nemotron Ultra for adversarial QA) never changes task ownership: active_writer remains codex while Codex is the harness. A writer handoff is only required when another independent execution environment takes ownership of repository production edits. Brain selection uses the CODEX_MODEL_BRAIN environment variable; no API keys enter Git or committed Codex configuration, and the user's normal ChatGPT-authenticated Codex setup stays intact.

## D014 — Structural provider smoke validation (2026-09-07)
Connectivity smoke validation is structural, not phrase-based. PASS requires a successful HTTP request, a valid non-empty choices list, an assistant message and non-empty content or reasoning_content (Cloudflare's result.response legacy shape also accepted). The previous exact-JSON requirement misreported a successful GLM/Cloudflare 200 response ("CONNECT") as invalid_response. Timeout, auth/model error classification, malformed-response handling and no-credential-logging behavior are preserved; genuine failures exit nonzero.

## D015 — Automatic merge and development CD on main (2026-09-07)
Routine engineering PRs do not require a human merge click: when GitHub CI, Qwen, GLM, Nemotron and required tests pass with a valid contract and no unresolved blockers, GitHub auto-merges with squash into main; the coordinator merge-gate evaluates the same conditions mechanically and fails closed. A validated main push deploys its exact tested SHA to the OVH development environment automatically via GitHub Actions SSH with pinned host keys. No --admin bypass, force merge or merge with failed checks. Human approval remains for high-consequence actions only (Clinical Evidence/Rule approval, frozen-architecture changes, destructive production migration, production release). One-time GitHub repository configuration (allow auto-merge, required checks, main branch protection) is documented and still pending external execution.

## D016 — Kimi research only where relevant (2026-09-07)
Task contracts declare research_required (default true). Infrastructure tasks may set it false so the research stage does not force a Kimi report; the deterministic merge gate requires the kimi-analysis report only when research_required is true. Reviewer roles (Qwen/GLM/Nemotron) remain mandatory for ordinary engineering PRs.

## D017 — Engineering harness chain with explicit handoffs (2026-09-07)
Supersedes D013. Codex + GPT-6 Astra is the primary engineering harness; OpenCode + GLM 5.3 is the first fallback harness; OpenCode + Qwen 3.8 is the second fallback harness. GLM 5.3 and Qwen 3.8 are no longer Codex model-brain fallback profiles: each harness has its own writer identity (codex, glm, qwen) matching the frozen writer priority prefix. Switching from Codex to OpenCode is an explicit human-approved writer handoff that preserves the same task, branch, base/HEAD SHA, Git-backed memory, reports and deterministic coordinator state; the handoff keeps the task's recorded base SHA and resumes at the exact recorded checkpoint (HEAD) SHA on the task branch. Harness selection uses the KEMIRIX_ENGINEERING_HARNESS environment variable; no API keys enter Git, and the user's normal ChatGPT-authenticated Codex setup stays intact (OpenCode reads Cloudflare credentials by environment reference only).

## D018 — Qwen seat moves to Nebius MiniMax-M3 (2026-09-08)
Owner-directed model swap for the qwen engineering seat: the cross-checker and second-fallback-writer role now executes through the Nebius adapter with MiniMaxAI/MiniMax-M3, and the Cloudflare adapter serves only the glm role. Role names, report paths, report formats, merge-gate requirements and the frozen writer priority (codex -> glm -> qwen) are unchanged; only the model and provider behind the qwen seat change (Qwen 3.8 27B on Cloudflare superseded). The second fallback harness profile becomes OpenCode + MiniMax-M3 via Nebius (writer qwen, KEMIRIX_ENGINEERING_HARNESS=opencode-minimax-m3). Rationale: Cloudflare's request wall clock cannot host the qwen seat's thinking mode at review-sized contexts (HTTP 408), and MiniMax-M3 on the existing Nebius credential surface adds a distinct model family to the review chain. opencode.json references the Nebius credential by environment variable only; no API keys enter Git.

## D019 — Cross-checker role renamed to minimax (2026-09-08)
Owner directive: no qwen naming remains in the active engineering system. The cross-checker and second-fallback-writer role is renamed qwen -> minimax across the Agent literal, frozen writer priority (codex -> glm -> minimax -> kimi), REPORTS filename (minimax-crosscheck.md), merge-gate and transition role gates, branch patterns, the MINIMAX_MODEL environment variable, the role document (ops/agents/MINIMAX.md), task contracts, tests and documentation. The seat executes MiniMax-M3 (MiniMaxAI/MiniMax-M3) through the Nebius endpoint; Cloudflare serves only the glm role. Historical task contracts were mechanically migrated to the minimax vocabulary so they remain loadable; historical decision entries, reports and git history keep their original wording as an immutable audit trail. Supersedes the qwen-seat naming in D017/D018; the MiniMax-M3 provider binding from D018 is unchanged.
