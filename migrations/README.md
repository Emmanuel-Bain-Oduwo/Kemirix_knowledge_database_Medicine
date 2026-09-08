# Database Migrations

Reviewed SQL migrations, executed only by the CI migration-from-zero gate
(`scripts/migration_gate.py --execute-ci`) on a clean, isolated PostgreSQL 17
database (`kemirix_knowledge`). The gate refuses non-prefix execution, undeclared
files, empty inventories and non-empty target databases.

Order and state:

1. `001_kmx.sql` — executable (KMX-SCHEMA-001). Creates the `kmx` schema:
   `registry`, `contains`, `external_identifier`, `name_index`,
   `mapping_exception` per the owner-approved blueprints (2026-09-08).
   Containment uses `container_kmx_id`/`member_kmx_id`/`relationship_type`/
   `ordinal` (a combination clinical drug contains ingredient members; a
   product contains a clinical drug). `lane_id` (S01–S27 architecture lane) is
   deliberately separate from `source_id` (stable implementation slug such as
   `dailymed`). External-identifier conflicts stay recordable — there is no
   global unique binding — so they fail closed into `kmx.mapping_exception`
   with full source/version/record/reason/candidate/review provenance.
   Migration 001 stays independent of the future Evidence tables.
2. `002_evidence.sql` — pending placeholder.
3. `003_rules.sql` — pending placeholder.

Promote a pending migration to executable only inside its reviewed task; the
declaration in `config/migration_suite.yaml` must always match the SQL content
(placeholder files stay comment-only). Production application to the OVH managed
database is an operator-controlled deployment step, never a CI side effect.
