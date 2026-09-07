# Final Execution Plan

## Phase 1 — Infrastructure

1. Create OVH Managed PostgreSQL database `kemirix_knowledge`.
2. Create Object Storage bucket `kemirix-knowledge-raw`.
3. Create one OVH ingestion VM.
4. Connect DBeaver to Managed PostgreSQL over TLS.

## Phase 2 — KMX identity

1. Create the five KMX architecture tables.
2. Acquire RxNorm/Athena.
3. Mint KMX-ING from ingredient identities.
4. Mint KMX-CD from clinical drug identities.
5. Connect RXCUI, UNII, ChEMBL, ChEBI, MED-RT, CIEL and other exact external IDs.
6. Integrate PPB Product Register, EMA and MHRA product identity to mint KMX-PROD.

Acceptance: a source record deterministically resolves to ING/CD/PROD or goes to mapping_exception.

## Phase 3 — Evidence foundation

1. Create source, source_block, clinical_evidence and evidence_support architecture.
2. Implement the shared 24-category map.
3. Implement DailyMed API first.
4. Implement openFDA Label API second as structured FDA-label projection.
5. Add PPB SmPC, EMA, MHRA, KNMF, Kenya MoH, KDIGO, CPIC/ClinPGx and WHO actionable guidance.

Acceptance: source → KMX → source block → category → full Evidence package.

## Phase 4 — Rules

1. Create clinical_rule, rule_evidence and rule_test.
2. Only executable approved Evidence can create a Rule.
3. Rule KMX/category/jurisdiction are inherited from Evidence.
4. Test MATCH, NO_MATCH and CANNOT_FULLY_EVALUATE.

## Phase 5 — Supporting databases

Add MED-RT, Inxight, DrugCentral, OnSIDES, CIViC, ChEMBL, Guide to Pharmacology, DGIdb, Open Targets and DrugMechDB as supporting evidence/identity lanes.

## First medicine acceptance target

Prove the complete architecture with Metformin before scaling the same adapter contract across the medication catalogue.
