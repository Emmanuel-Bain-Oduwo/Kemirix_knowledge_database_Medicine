QA_PASS
Task-ID: KMX-002
Head-SHA: 700e63347411d5b585523681ceaea052a5dea36e
Role: nemotron

1: OK - Resolver imports only kmx.exceptions and kmx.models (AST-verified); no similarity, fuzzy, probabilistic, LLM, or network logic; identity is exact-identifier or exact-normalized-name only; name fallback requires explicit per-request permission
2: OK - Product-level requests from non-approved lanes fail PRODUCT_IDENTITY_UNPROVEN before any lookup; exact identifier level mismatch fails IDENTIFIER_CONFLICT; name lookup level filter only narrows; frozen level set via KmxLevel.ALL
3: OK - Normalizer does only NFKC + casefold + whitespace collapse; strength, form, punctuation, etc. preserved (tests assert inequality); blank names rejected
4: OK - MULTIPLE_MATCHES for one identifier bound to several KMX; IDENTIFIER_CONFLICT for cross-identifier disagreement and level mismatch; FORMULATION_AMBIGUITY for multiple name candidates; NO_MATCH when nothing matches; PRODUCT_IDENTITY_UNPROVEN for unapproved product lanes; mapping-exception recording captures full provenance with five frozen reason codes; never auto-resolves
5: OK - Unit tests run against in-memory FakeRepository; integration test gated to KEMIRIX_CI_POSTGRES=1 and GITHUB_ACTIONS=true only; applies real migrations and cleans synthetic rows; only src/kmx and tests/test_kmx_resolver.py changed; no builders/minting, Evidence/Rule, adapters, or new dependencies
Findings: The resolver is a pure deterministic function over the repository with zero guessing surface. Level guards are correctly ordered (product unproven before lookup, identifier conflict on level mismatch). Normalization is provably conservative. All five conflict reason codes are used exactly as specified with full provenance capture.
Checks: AST inspection test pins resolver imports to exceptions and models only. Unit tests cover every algorithm branch with in-memory fakes. Integration test is CI-gated, migration-backed, and self-cleaning. No scope creep beyond Phase 7 resolver and repository.
