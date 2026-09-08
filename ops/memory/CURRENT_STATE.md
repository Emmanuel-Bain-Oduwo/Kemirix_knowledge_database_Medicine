# Current state

Phase 0 (engineering foundation) is complete and proven. Phase 1
(DOMAIN-CONTRACT-001) and Phase 2 (CORE-001) are MERGED, DEPLOYED, VERIFIED
and CLOSED per the owner's 2026-09-08 Phase 1 + Phase 2 execution directive.

## Phase 1 + Phase 2 delivery (owner-directed, writer glm per D020)

Main is at c255ea0f64eb8976f890ab6df45cdce9f191e153 (CORE-001 squash merge).
Every task below went through the full chain: MiniMax-M3 cross-check (real
Nebius run) -> GLM review -> Nemotron 3 Ultra QA (real Nebius run) ->
deterministic merge gate MERGE_READY (all 13 checks) -> kemirix-agent-gate
SUCCESS on the exact PR head -> squash merge -> main CI SUCCESS -> Deploy
development exact-SHA deployment -> verify-runtime PASS -> lifecycle closed.

- KMX-SCHEMA-001: executable kmx DDL merged at b36b909 (PR #6) aligned to the
  owner-approved blueprints (container/member containment, lane_id vs
  source_id slugs, recordable identifier conflicts, full mapping_exception
  provenance); migration 001 applied from-zero to the development PostgreSQL
  17 (five kmx tables live); deployment verified within main 44db32f.
- FOUNDATION-CD-AND-SKILL-001: merged at 44db32f (PR #8) — implemented the
  separately approved development migration execution (operator-provisioned
  0600 credential file at /srv/kemirix/secrets/dev-postgres.env, from-zero
  single-transaction apply, idempotent inventory verification, fail-closed
  semantics) and the owner-approved SKILL.md task mechanism; fixed the red
  Deploy development workflow.
- FOUNDATION-SKILL-SYNC-001: merged at 5380864 (PR #9) — repository SKILL.md
  is byte-identical to the owner-approved v5.0 blueprint.
- DOMAIN-CONTRACT-001: merged at ad4f48b (PR #10) — universal contracts
  frozen for all 27 lanes: 5+6+3 database inventory, storage/manifest
  contract, evidence contract, rule contract with authority invariants,
  frozen SOURCE_MATRIX, 15-test validation suite.
- CORE-001: merged at c255ea0 (PR #11) — production-ready importable domain
  foundation: packaging fixed (wheel-verified), single-definition shared core
  types, common fail-closed config loading for all 27 lanes, small error
  hierarchy, 27-lane source registry foundation.

The development environment runs DEPLOYED_SHA=c255ea0 with the kmx schema
applied. All 27 source contracts/configs validate; the repository SKILL
matches the owner-approved blueprint; Git memory matches reality.

## Proven delivery execution

The full automatic path is proven end-to-end on main: five-agent review chain
(writer, minimax cross-check via real Nebius MiniMax-M3, GLM review, Nemotron
adversarial QA via real Nebius Nemotron 3 Ultra) -> deterministic merge gate
MERGE_READY -> kemirix-agent-gate SUCCESS on the exact PR head -> squash merge
into main -> main CI SUCCESS -> Deploy development deploys the exact
CI-tested SHA (including executable migrations) -> runtime verification PASS.
The protect-main ruleset is active (squash-only, PR required, linear history,
required checks foundation + kemirix-agent-gate after the D021 context
correction, up-to-date branches).

## Pending

- GitHub auto-merge feature enablement and automatic head-branch deletion
  remain owner-side; gated squash merges are executed by the delivery
  automation after all gates pass.
- The legacy develop branch still exists; the owner may delete it in GitHub.
- Multi-migration development upgrades (when 002/003 become executable)
  require the DATABASE-001 migration runner; the current hook intentionally
  refuses them.
- DBeaver verification remains unverified; source integrations remain
  not_started (roadmap STORAGE-001 onward).
- Codex CLI inference smoke remains structurally validated only.

## Next roadmap task ready to start

STORAGE-001 (immutable S3 raw vault) per the execution book phase table —
from main c255ea0.
