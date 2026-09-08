# Current state

FOUNDATION-QWEN-MINIMAX-SWAP-001 is completing the owner-directed cross-checker
rename: the second-fallback-writer role is renamed to minimax
and executes MiniMax-M3 (MiniMaxAI/MiniMax-M3) through the Nebius endpoint, with
Cloudflare serving only the glm role. FOUNDATION-CLOSEOUT-001 (#3) merged through the
automatic path at main checkpoint 94d6c59 and its exact SHA is deployed and verified
on development.

## Proven delivery execution

PR creation, automatic squash merge, main CI and exact-SHA development deployment
executed successfully: the automation rehearsal (#2) and the closeout (#3, main
checkpoint 94d6c59; runtime verification PASS). The closeout's full external review
chain also executed against real providers (MiniMax cross-check, GLM review, Nemotron
adversarial QA) before its deterministic gate published `kemirix-agent-gate` success.
These results prove the delivery path and the reviewed closeout; they do not by
themselves establish current repository protection settings.

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
tests and publishes `kemirix-agent-gate` only after MERGE_READY; it has now been
executed externally (PR #3, exact head db709d7). Local synthetic regression tests are
not external provider PASS reports.

The minimax role rename covers the Agent literal, frozen writer priority
(codex -> glm -> minimax -> kimi), report filename minimax-crosscheck.md, merge-gate
and transition role gates, branch patterns, the MINIMAX_MODEL environment variable,
the role document, task contracts, tests and documentation; historical decision
entries, reports and git history keep their original wording as an immutable audit
trail (D019). Provider smoke and the full suite pass with the renamed role.

## Pending

- Owner-side main protection, required-check configuration (foundation +
  kemirix-agent-gate) and automatic head-branch deletion remain owner-side GitHub
  configuration. Successful automatic merges do not establish those settings.
- Full five-agent worktree/access separation and DBeaver verification remain
  unverified; the active Codex task worktree exists.
- Phase 1 readiness remains blocked pending owner review of the completed foundation.

## Domain scope

Migrations remain three non-executable placeholders. KMX, Clinical Evidence, Rules
and S01–S27 integrations remain not started. No domain implementation, clinical
approval or production deployment is claimed.
