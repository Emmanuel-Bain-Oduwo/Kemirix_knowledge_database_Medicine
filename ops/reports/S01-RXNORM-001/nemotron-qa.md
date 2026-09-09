QA_PASS
Task-ID: S01-RXNORM-001
Head-SHA: ab6bdfda7ee066fac2af53bbc06be44ab7479a9b
Role: nemotron

1: OK - Discovery runs first, verify_pinned gates download, MD5 verified before vault upload, wrong MD5 leaves vault untouched (tested), pinned file not current.zip
2: OK - UTS_API_KEY from env only, only in download URL query param, never logged/echoed/stored/manifested, test asserts key absent from vault bytes
3: OK - Loader uses official RXCUI2-to-RXCUI1 direction for all 7 RELAs, fixture tests catch reversal, unproven PINs stay unlinked, multi-target relations require single target/binding
4: OK - Only ING/CD minted (zero PROD, tested), ordinals sorted for determinism, reruns idempotent with zero new IDs/duplicate bindings, suppressed rows filtered, unresolved structures record provenance-rich exceptions
5: OK - Only src/sources/rxnorm and tests/test_rxnorm.py changed, fully offline (MockTransport, synthetic ZIPs, fake vault/builder), end-to-end test covers discovery through stored-copy load with both fail-closed paths
Findings: The implementation correctly enforces pinned-release verification before any download, verifies official MD5 before vault upload, keeps UTS_API_KEY out of all persistent artifacts, honors the official RXCUI2-to-RXCUI1 relation direction for all seven RELA types, mints only ING/CD identities with deterministic ordering and idempotent reruns, and the test suite is fully offline with synthetic fixtures covering both success and fail-closed paths.
Checks: Verified pin-bypass prevention via discovery-first flow and MD5-gate before vault; confirmed secret safety via env-only key, query-param-only use, and vault-secrecy assertion; validated relation-direction integrity against the official convention with fixture tests for proven/unproven PINs and multi-target guards; confirmed zero-PROD, deterministic ordinals, idempotent reruns, suppress filtering, and provenance-rich exceptions; confirmed scope limited to rxnorm adapter/loader with honest offline tests including pin-drift and MD5-mismatch fail-closed cases.
