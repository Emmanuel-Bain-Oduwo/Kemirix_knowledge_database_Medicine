# Current state

Phase 0 (engineering foundation) is complete. FOUNDATION-QWEN-MINIMAX-SWAP-001 (#4)
closed the owner-directed cross-checker rename at main checkpoint
bdfd2ebae9bc01c973e0077a1b2992d792937325: the role is minimax executing MiniMax-M3
(MiniMaxAI/MiniMax-M3) through the Nebius endpoint, Cloudflare serves only the glm
role, the corrected Nemotron default model id is nvidia/Nemotron-3-Ultra-550b-a55b,
and qwen naming is eliminated from the active engineering system (historical
audit trail preserved per D019). The task is closed with commit_sha and
deployed_sha bdfd2eb.

## Proven delivery execution

The full automatic path is proven end-to-end on main: five-agent review chain
(codex writer, minimax cross-check via real Nebius MiniMax-M3, GLM review,
Nemotron adversarial QA via real Nebius Nemotron 3 Ultra) -> deterministic merge
gate MERGE_READY (all 13 checks) -> `kemirix-agent-gate` SUCCESS on the exact PR
head -> squash merge into main -> main CI SUCCESS -> Deploy development
workflow deployed the exact CI-tested SHA to the OVH development environment
(DEPLOYED_SHA = merge SHA; bdfd2eb for the swap, 94d6c59 for the closeout, both
runtime-verified). The automation rehearsal (#2) previously proved the same path.

## Implemented and locally validated

The foundation provides task ownership, deterministic coordination, checkpoint/PR
tooling, writer handoff, provider adapters, safe research boundaries, exact-SHA
runtime deployment/verification and main-only delivery. Codex is the primary
writer harness; OpenCode GLM then OpenCode MiniMax-M3 (writer minimax) are fallback
harnesses requiring explicit writer handoff. The ordinary hosted CI job remains
`foundation`.

The closeout gate requires reports bound to the task and reviewed checkpoint,
correct branch/base/head and ancestry, all required tests, CI and an eligible
lifecycle state. Missing or unverifiable conditions cannot produce MERGE_READY.
The local coordinator consumes operator CI/test attestations. The separate
`agents.publish_gate` command verifies live PR/CI identity, executes required safe
tests and publishes `kemirix-agent-gate` only after MERGE_READY; executed
externally on PR #3 (db709d7) and PR #4 (8753c1d). Local synthetic regression
tests are not external provider PASS reports.

## Pending

- Main protection is now ACTIVE (protect-main ruleset, created 2026-09-08 13:04):
  squash-only merges, required checks `foundation` + `kemirix-agent-gate`, linear
  history, no force pushes, branches up to date. The required-status-check
  contexts were corrected 2026-09-08 from an accidental joined-context entry
  ("foundation kemirix-agent-gate") to the two documented separate contexts
  (D021). GitHub auto-merge feature enablement and automatic head-branch
  deletion remain owner-side; gated squash merges are executed by the delivery
  automation after all gates pass.
- Development deployment of executable-migration releases is refused BY DESIGN
  by scripts/runtime.py until the separately approved development migration
  execution exists (roadmap DATABASE-001). KMX-SCHEMA-001 merged at main
  b36b909 without a development deployment; the development runtime stays on
  the healthy 744156d release and the refused incomplete b36b909 release
  directory was quarantined (D022). After the migration runner lands, re-run
  the Deploy development workflow for the pending main SHAs.
- DBeaver verification remains unverified; full five-agent worktree/access
  separation is not yet applied (single control VM, one active writer worktree).
- Codex CLI login is functional (ChatGPT-authenticated); an inference smoke
  remains structurally validated only.

## Phase 1

KMX-SCHEMA-001 is MERGED at main b36b909bbfd96b59ee19343c3c39177c2a236c79
(PR #6, branch agent/glm/KMX-SCHEMA-001). It delivered reviewed executable
PostgreSQL 17 DDL for the five kmx tables aligned to the owner-approved
2026-09-08 blueprints: container/member containment (container_kmx_id,
member_kmx_id, relationship_type, ordinal), lane_id (S01-S27) separated from
source_id slugs, recordable external-identifier conflicts (no global unique
binding; conflicts fail closed into kmx.mapping_exception), full
mapping_exception provenance (source/version/record/reason/candidate/review),
registry normalized_name/updated_at, lookup-only name_index, and migration 001
independent of future Evidence tables. Review chain proven: MiniMax-M3
cross-check PASS (real Nebius run), GLM review PASS, Nemotron 3 Ultra QA_PASS
(real Nebius run), merge gate MERGE_READY (all 13 checks), kemirix-agent-gate
SUCCESS on exact head 61d8b74, main foundation CI SUCCESS on b36b909 including
the migration-from-zero gate on hosted PostgreSQL 17. The writer seat is glm
(human-approved handoff from codex at checkpoint fb3109d, owner directive
2026-09-08); the glm review seat was executed by the same GLM 5.3 harness under
that explicit owner directive with the two independent provider seats remaining
real Nebius runs (D020). DOMAIN-CONTRACT-001 (Phase 1 contract freeze) is the
active next task. No clinical approval or production domain deployment is
claimed.
