QA_PASS
Task-ID: KMX-003
Head-SHA: c380c6971f6d59f9bd921d5007286e48a430af3c
Role: nemotron

1: OK - PROD minting strictly gated: approved regulator lane (ppb_register/ema/mhra) AND exact regulator identifier (system+value) AND resolved clinical-drug members required; brand names, RxNorm SBD, non-regulator sources, missing identifiers all raise PRODUCT_IDENTITY_UNPROVEN; no alternate mint path exists
2: OK - Per-level transaction-scoped pg_advisory_xact_lock (910001/910002/910003) serializes concurrent allocations; max-suffix read under lock; exhaustion bound at 999,999 enforced; refresh reuses exact external identifiers via resolver so identities never renumber; 8-thread CI test proves unique allocation
3: OK - PINs mint own identities; MIN concepts refused; unproven PIN/base associations create no edge; distinct strength/release/route variants mint distinct IDs (three-variant test); reuse by exact external identifier only (never by name); combination CDs contain all ingredient members with deterministic ordinals
4: OK - Each build call wraps registry + external identifiers + name index + containment in owning_transaction (BEGIN/COMMIT/ROLLBACK); rollback test verifies no partial persistence on failure; fake store models real rollback via state snapshots
5: OK - Only src/kmx and tests/test_kmx_builders.py changed; resolver remains read-only; psycopg stays lazily imported; no Evidence/Rule work, no adapters, no live ingestion, no new dependencies, no new permanent tables
Findings: All five adversarial gates hold. PROD minting has no bypass; ID allocation is concurrency-safe and exhaustion-bounded; formulation identities never collapse silently; every build is atomic with verified rollback; scope is strictly confined to the two new builder/allocation modules and their tests.
Checks: Verified PROD proof gate requires approved regulator lane + exact regulator identifier + resolved clinical-drug members; verified advisory-lock allocation with max-suffix read and exhaustion bound; verified PIN own-identity + proven-only association + MIN refusal + variant separation + exact-identifier reuse + deterministic ordinals; verified atomic transaction wrapper and rollback test; verified diff scope limited to kmx builders/allocation and tests.
