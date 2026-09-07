# Kemirix Knowledge Database — Medicine

This repository is the architecture and implementation home for the Kemirix medication knowledge foundation.

## Frozen scope

Kemirix resolves every medicine source to exactly one clinically correct KMX level:

- **KMX-ING** — ingredient
- **KMX-CD** — clinical drug: ingredient + clinically meaningful formulation attributes
- **KMX-PROD** — actual regulator/product identity

Then every clinical source follows the same path:

```text
SOURCE
  ↓
ACQUIRE: API / BULK DATABASE / PDF / WEB / MANUAL
  ↓
STORE ORIGINAL IN OVH OBJECT STORAGE
  ↓
RESOLVE KMX-ING / KMX-CD / KMX-PROD
  ↓
SOURCE BLOCK
  ↓
MAP TO ONE OF 24 CLINICAL CATEGORIES
  ↓
FULL SOURCE-SPECIFIC CLINICAL EVIDENCE
  ↓
EXECUTABLE RECOMMENDATION?
  ├── NO  → Evidence only
  └── YES → Full Rule
              ↓
          SAME KMX ID
          SAME CATEGORY
  ↓
OVH MANAGED POSTGRESQL
```

## Infrastructure

- **OVH VM** — runs source acquisition, parsing, KMX resolution, Evidence building and Rule building.
- **OVH Object Storage** — raw/immutable copy of every API response, database dump, PDF, XML, JSON, TSV, CSV and source manifest.
- **OVH Managed PostgreSQL** — clinical knowledge authority for KMX, Evidence and Rules.
- **DBeaver** — database viewer used to inspect the managed PostgreSQL tables.
- **GitHub** — source configuration, architecture, code and tests. Raw clinical datasets are never committed here.

## Managed PostgreSQL layout

One database: `kemirix_knowledge`.

```text
kmx
├── registry
├── contains
├── external_identifier
├── name_index
└── mapping_exception

evidence
├── source
├── source_block
├── clinical_evidence
└── evidence_support

rules
├── clinical_rule
├── rule_evidence
└── rule_test
```

## Evidence organization

Evidence is organized logically by:

```text
KMX ID + KMX level + category + source + jurisdiction
```

A source may join mechanically through one level and produce Evidence at another level. The clinical statement decides the Evidence level:

- Applies regardless of formulation/product → **KMX-ING**
- Depends on strength, dose form, release, concentration or route → **KMX-CD**
- Depends on a specific regulated product, brand, holder, excipient or product-specific property → **KMX-PROD**

Source-specific Evidence packages remain separate.

## Rules

Rules are only created from approved Evidence that contains an executable patient-specific decision. Rule identity is inherited directly from Evidence:

```text
Rule.target_kmx_id = Evidence.kmx_subject
Rule.target_level  = Evidence.kmx_level
Rule.category      = Evidence.category
Rule.jurisdiction  = Evidence.jurisdiction
```

Rules never resolve medicine identity a second time.

## 24 shared clinical categories

`indication`, `contraindication`, `drug_disease`, `drug_drug`, `drug_food_substance`, `allergy_hypersensitivity`, `dosing`, `renal`, `hepatic`, `paediatric`, `geriatric`, `pregnancy`, `lactation`, `laboratory`, `vital_signs`, `monitoring`, `adverse_effects`, `duplication`, `polypharmacy`, `administration`, `high_alert_safety`, `pharmacogenomic`, `treatment_appropriateness`, `counselling`.

## Source lanes

The repository contains configuration and architecture placeholders for all **27 source lanes**. Each source config freezes:

- acquisition method
- expected KMX level(s)
- primary external identifiers
- Evidence role
- Rule role
- expected clinical categories
- jurisdiction
- Object Storage path convention
- rate-limit policy where relevant

See [`docs/SOURCE_MATRIX.md`](docs/SOURCE_MATRIX.md).

## Repository purpose right now

This repository is intentionally **architecture-first**. It establishes the full folder structure, source contracts, storage/database layout and execution sequence without implementing ingestion logic yet.

## Execution order

1. Provision OVH Managed PostgreSQL, Object Storage and one ingestion VM.
2. Create KMX foundation from RxNorm/Athena → KMX-ING + KMX-CD.
3. Add external identifier bridges.
4. Build KMX-PROD from PPB/EMA/MHRA product identities.
5. Build Evidence tables and category mapping.
6. Implement DailyMed API first, then openFDA API.
7. Add PPB SmPC, EMA, MHRA, KNMF, Kenya MoH, KDIGO, CPIC/ClinPGx and WHO actionable guidance.
8. Build Rules from approved executable Evidence.
9. Add supporting biomedical databases.
10. Prove the complete flow with Metformin before scaling broadly.

> **Source → KMX → Category → Clinical Evidence → Rule when executable.**
