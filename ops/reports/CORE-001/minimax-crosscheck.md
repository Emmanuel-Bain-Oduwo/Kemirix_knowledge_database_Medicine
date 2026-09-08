PASS
Task-ID: CORE-001
Head-SHA: 6e9ee61cfc7c0d69db56f72bf927c9cd5c50058f
Role: minimax

1: OK - pyproject.toml wheel packages list src/agents plus all six domain packages.
2: OK - KMX levels/IDs, 24 categories (follow_up excluded), Evidence statuses, JoinLevel/TruthLevel reusing KmxLevel, RuleOutcome, storage statuses, and lane-ID vs slug patterns are each defined once.
3: OK - load_source_configs rejects duplicate lanes, duplicate slugs, lane-ID-as-slug (uppercase S fails SLUG_PATTERN), missing/extra fields, unknown categories, and unknown jurisdictions.
4: OK - load_database_contract enforces the exact 5+6+3 inventory across kmx/evidence/rules schemas.
5: OK - KemirixError base plus ConfigurationError, IdentityResolutionError, MappingExceptionBoundaryError, StorageContractError, DatabaseContractError, SourceContractError; plain exceptions, no framework.
6: OK - SourceRegistry.load yields 27 lanes and describe exposes lane_id, source_id, acquisition_mode, source_role, kmx_capability, evidence_role, rule_policy.
7: OK - Manifest uses extra="forbid" rejecting credentials/presigned URLs, validates controlled values, sha256 (64 hex) and adapter_git_sha (40 hex); object keys reject lane-ID slugs and path escapes.
8: OK - No boto3/psycopg/HTTP/parsers/lane adapters introduced; only pyproject.toml, the six src/ domain packages, and tests/test_core.py changed.
Findings: All eight contract checks are satisfied by the diff. The foundation cleanly separates identity, evidence, rules, storage, database, and sources with a single shared error hierarchy and fail-closed loaders. Tests cover the 27-lane registry, frozen enums, KMX ID validation, manifest secret rejection, and object-key safety.
Checks: Cross-referenced each requirement against the new modules and tests; every required rejection path, vocabulary, and packaging entry is present and no forbidden dependency or path was introduced.
