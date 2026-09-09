PASS
Task-ID: KMX-002
Head-SHA: 700e63347411d5b585523681ceaea052a5dea36e
Role: minimax

1: OK - normalizer applies only NFKC, casefold and whitespace collapse; tests assert NFKC compatibility folding and strength/punctuation inequality.
2: OK - repository exposes external_bindings, level-filtered name_candidates, get_kmx and record_mapping_exception with the five frozen reason codes and full provenance; psycopg is not imported in the domain module.
3: OK - resolver implements PRODUCT_IDENTITY_UNPROVEN gate, MULTIPLE_MATCHES, IDENTIFIER_CONFLICT (including level mismatch), single-KMX resolve, and gated name fallback with FORMULATION_AMBIGUITY/NO_MATCH; import inspection proves no AI/network/psycopg path.
4: OK - tests cover RXCUI, UNII, zero match, multiple matches, identifier disagreement, ambiguous formulation, combination containment non-touch, regulator/non-regulator product lanes, conservative normalization, request validation, provenance, no-AI import inspection, and the CI-gated PostgreSQL integration test that applies migrations and cleans up synthetic rows.
5: OK - only src/kmx and tests/test_kmx_resolver.py changed; no builders, Evidence/Rule work, source adapters or new dependencies; models/exceptions untouched.
Findings: The implementation faithfully encodes the frozen deterministic algorithm with conservative normalization and a pure resolver over a thin repository abstraction. The CI-gated integration test is properly scoped to the isolated hosted PostgreSQL and cleans up its synthetic rows. No prohibited paths or dependencies were introduced.
Checks: All five requirements verified against the diff: conservative normalizer, psycopg-backed repository with frozen reason codes, deterministic resolver with no AI/network path, comprehensive test coverage including CI-gated integration, and allowed-path-only changes.
