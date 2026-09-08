QA_PASS
Task-ID: CORE-001
Head-SHA: 6e9ee61cfc7c0d69db56f72bf927c9cd5c50058f
Role: nemotron

1: OK - pyproject.toml lists src/agents plus six domain packages (kmx, evidence, rules, storage, database, sources)
2: OK - single definitions: KmxLevel/KmxId in kmx/models, 24 categories in evidence/categories, EvidenceStatus/RuleOutcome as frozen namespaces, lane vs slug distinguished in sources/config and storage/keys
3: OK - load_source_configs in sources/config loads all 27 lanes through one fail-closed interface; SourceRegistry.load uses it
4: OK - database/config defines KMX_TABLES(5), EVIDENCE_TABLES(6), RULES_TABLES(3) and load_database_contract validates exact match
5: OK - small hierarchy: KemirixError base in kmx/exceptions with 3 subclasses; domain errors (DatabaseContractError, SourceContractError, StorageContractError) extend same base
6: OK - SourceRegistry in sources/registry holds 27 lanes with _by_lane/_by_slug, describe() exposes lane policies (acquisition, roles, kmx_levels, evidence, rules, jurisdiction, storage, rate_limit)
7: OK - Manifest uses ConfigDict(extra="forbid") rejecting unknown fields; storage/keys validates slugs, rejects lane IDs (S01-S27) and escapes in object keys
8: OK - no boto3/psycopg/HTTP/parsers/adapters imported; only stdlib, yaml, pydantic, hatchling
Findings: All eight domain-contract requirements are satisfied by the new packages and tests.
Checks: Verified package list, single-definition types, common fail-closed loaders, 5+6+3 database contract, small error hierarchy, 27-lane registry with policies, manifest/key validation, and absence of forbidden dependencies.
