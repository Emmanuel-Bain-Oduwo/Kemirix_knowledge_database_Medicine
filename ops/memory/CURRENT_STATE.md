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

- Owner-side main protection, required-check configuration (foundation +
  kemirix-agent-gate), GitHub auto-merge enablement and automatic head-branch
  deletion remain owner-side GitHub configuration. Successful gated merges do
  not establish those settings.
- DBeaver verification remains unverified; full five-agent worktree/access
  separation is not yet applied (single control VM, one active writer worktree).
- Codex CLI login smoke remains pending (structural validation only).

## Phase 1

Production database/domain implementation has started: KMX-SCHEMA-001 is the
active phase_1 task (executable kmx schema DDL first). Until it lands, domain
modules (src/kmx, src/evidence, src/rules, src/sources) and the three migrations
remain non-executable placeholders. No clinical approval or production domain
deployment is claimed.
