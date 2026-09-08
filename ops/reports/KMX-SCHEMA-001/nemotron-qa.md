QA_PASS
Task-ID: KMX-SCHEMA-001
Head-SHA: 61d8b7490fb4c69f87badb56116de6248cf99a14
Role: nemotron

1: OK - registry has exactly the seven required columns with correct names and types
2: OK - kmx_id format regex and prefix-level binding check constraints present
3: OK - contains table has composite PK on (container_kmx_id, member_kmx_id, relationship_type) and self-reference check
4: OK - external_identifier unique constraint only on (kmx_id, identifier_system, identifier_value)
5: OK - all source_id columns use slug regex ^[a-z][a-z0-9_]*$ with no S01-S27 pattern
6: OK - mapping_exception includes lane_id S01-S27 regex, source_version_key, source_record_key, five reason codes, candidate_kmx_ids jsonb, status enum, reviewed_at/reviewed_by with provenance check
7: OK - no references to evidence or rules schemas anywhere in the DDL
8: OK - registry level and prefix constraints only allow ING/CD/PROD, no PRES
9: OK - only CREATE SCHEMA/TABLE/INDEX and COMMENT statements; no DROP/GRANT/CREATE EXTENSION/CREATE DATABASE/COPY
10: OK - name_index has no unique constraint on normalized_name or name columns, only a non-unique index
Findings: All ten adversarial checks pass against the provided SQL for Kemirix KMX-SCHEMA-001 checkpoint 61d8b7490fb4c69f87badb56116de6248cf99a14.
Checks: Verified registry columns, KMX ID format and prefix binding, contains composite PK and self-check, external_identifier unique scope, source_id slug format, mapping_exception completeness, absence of evidence/rules references, absence of KMX-PRES, absence of forbidden DDL, and name_index non-uniqueness.
