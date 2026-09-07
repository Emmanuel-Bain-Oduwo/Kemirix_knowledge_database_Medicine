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
Supersedes D004's comment-only migration execution: CI explicitly reports the three migrations pending/non-executable. Future declared executable migrations must form an ordered prefix and run from an empty PostgreSQL 17 database. Development delivery uses only the successful develop CI head SHA, immutable Git extraction and integrity verification. Code delivery never activates clinical knowledge.

## D011 — Release retention and failure recovery (2026-09-07)
Retain all development releases initially (at least three) rather than adding destructive pruning. Pointer replacements are individually atomic; mismatches fail closed. Preserve incomplete releases for operator quarantine. No automatic production rollback or production migration is implemented.
