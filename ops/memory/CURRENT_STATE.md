# Current state

Phase 0 (engineering foundation) is complete and proven. Phase 1
(DOMAIN-SCHEMA/CONTRACT work), Phase 2 (CORE-001) and the owner-directed
Phase 1/2 contract hardening (PHASE1-2-CONTRACT-HARDENING-001) are MERGED,
DEPLOYED, VERIFIED and CLOSED per the owner's 2026-09-08 directives.

## Phase 1 + Phase 2 delivery and hardening (owner-directed, writer glm per D020)

Main is at 6876f04d0695e45d44cd2f52c074abaa700c3891 (PHASE1-2-CONTRACT-
HARDENING-001 squash merge). Every task below went through the full chain:
MiniMax-M3 cross-check (real Nebius run) -> GLM review -> Nemotron 3 Ultra
QA (real Nebius run) -> deterministic merge gate MERGE_READY (all 13 checks)
-> kemirix-agent-gate SUCCESS on the exact PR head -> squash merge -> main
CI SUCCESS -> Deploy development exact-SHA deployment -> verify-runtime
PASS -> lifecycle closed.

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
- FOUNDATION-PHASE12-CLOSEOUT-001: merged at dfae74a (PR #12) — canonical
  memory synchronized to the completed Phase 1 + Phase 2 reality.
- PHASE1-2-CONTRACT-HARDENING-001: merged at 6876f04 (PR #13) — closed the six
  still-valid PR #10 review findings (audited against current main; the
  seventh, canonical memory, was already fixed by
  FOUNDATION-PHASE12-CLOSEOUT-001): manifest artifact object_keys are now
  exactly bound to manifest provenance and fail closed (never rewritten); the
  full structural Rule contract is frozen in config/rule_contract.yaml
  (clinical_rule 24-field inventory covering the 17-part logical Rule,
  rule_evidence, rule_test, exact three outcomes with all-trigger MATCH /
  missing-data CANNOT_FULLY_EVALUATE / wrong-formulation NO_MATCH semantics,
  immutable Evidence inheritance, no medicine remapping); one canonical
  frozen source_rule_policies map enforces the exact owner-approved S01-S27
  rule policies (arbitrary policy strings fail, non-primary lanes accept only
  false/false_initially); docs/OBJECT_STORAGE.md matches the frozen
  five-segment layout with __release__ bulk keys and the full manifest field
  list; migrations/002_evidence.sql lists exactly the six planned Evidence
  tables and remains non-executable (suite still pending); the
  forbidden-manifest-field check inspects mapping keys recursively and
  exactly (secretin.xml passes, credential field names fail at any depth).
  337 tests. Review chain on checkpoint 85b0ecb: real Nebius MiniMax-M3 PASS,
  GLM PASS, real Nebius Nemotron 3 Ultra QA_PASS; merge gate MERGE_READY;
  kemirix-agent-gate SUCCESS; main CI SUCCESS; DEPLOYED_SHA verified.

The development environment runs DEPLOYED_SHA=6876f04 with the kmx schema
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
from main 6876f04. Phase 3 has NOT started; no STORAGE-001, INGESTION-CORE-001,
DATABASE-001, KMX resolver, RxNorm/DailyMed ingestion, Evidence DDL, Rule DDL
or source loading work has begun (all remain roadmap items).
