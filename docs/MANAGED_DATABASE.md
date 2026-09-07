# OVH Managed PostgreSQL

## One database

```text
kemirix_knowledge
```

The managed database is the normalized clinical knowledge authority. The ingestion VM does not host the production PostgreSQL server.

## Schemas

### kmx

- `kmx.registry` — KMX-ING, KMX-CD, KMX-PROD
- `kmx.contains` — ING→CD→PROD and combination membership
- `kmx.external_identifier` — RXCUI, UNII, ChEMBL, ChEBI, MED-RT, CIEL, regulator IDs, etc.
- `kmx.name_index` — controlled names/synonyms used for deterministic resolution
- `kmx.mapping_exception` — unresolved or conflicting identities

### evidence

- `evidence.source` — the 27 source definitions and versions
- `evidence.source_block` — source section/block connected to KMX
- `evidence.clinical_evidence` — full source-specific Evidence package
- `evidence.evidence_support` — links supporting biomedical facts to Evidence

### rules

- `rules.clinical_rule` — full executable Rules
- `rules.rule_evidence` — exact Evidence connected to each Rule
- `rules.rule_test` — MATCH / NO_MATCH / CANNOT_FULLY_EVALUATE tests

## Raw database dumps

Large upstream database dumps such as ChEMBL or DrugCentral do not become the production knowledge database. Store the original dump in Object Storage, restore/read it temporarily on the VM if needed, extract/match the relevant data and write only normalized Kemirix records to Managed PostgreSQL.
