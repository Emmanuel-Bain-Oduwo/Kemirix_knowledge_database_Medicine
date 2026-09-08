# KMX Module

Home for KMX-ING, KMX-CD, KMX-PROD registry, containment, external identifiers,
name index and deterministic resolution.

Current state (KMX-SCHEMA-001): the schema itself is executable DDL in
`migrations/001_kmx.sql` (registry, contains, external_identifier, name_index,
mapping_exception). Application code (resolver, identity minting/reuse,
ingestion into the schema) is intentionally not implemented yet; it lands in
reviewed follow-up tasks after the schema checkpoint is merged.
