# Database Migrations

Reviewed SQL migrations, executed only by the CI migration-from-zero gate
(`scripts/migration_gate.py --execute-ci`) on a clean, isolated PostgreSQL 17
database (`kemirix_knowledge`). The gate refuses non-prefix execution, undeclared
files, empty inventories and non-empty target databases.

Order and state:

1. `001_kmx.sql` — executable (KMX-SCHEMA-001). Creates the `kmx` schema:
   `registry`, `contains`, `external_identifier`, `name_index`,
   `mapping_exception` with KMX-ID format/level constraints, combination-safe
   containment and deterministic external-identifier binding.
2. `002_evidence.sql` — pending placeholder.
3. `003_rules.sql` — pending placeholder.

Promote a pending migration to executable only inside its reviewed task; the
declaration in `config/migration_suite.yaml` must always match the SQL content
(placeholder files stay comment-only). Production application to the OVH managed
database is an operator-controlled deployment step, never a CI side effect.
