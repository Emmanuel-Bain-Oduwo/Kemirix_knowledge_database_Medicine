PASS
Task-ID: DATABASE-001
Head-SHA: 222491783cc8dcf9491646598b6602d708d66c8a
Role: minimax

1: OK - lazy psycopg import, secure sslmodes with allow_insecure escape, no credentials in errors, autocommit, PG17 healthcheck
2: OK - BEGIN/yield/COMMIT with exception-triggered ROLLBACK and re-raise
3: OK - canonical contains_sql/plan/expected_tables, apply_or_verify covers clean/verified/upgrade/foreign/partial/non-empty/unsupported, no history table
4: OK - migration_gate delegates to library, runtime bridges to release venv runner with PG* env, fails closed on missing venv or runner failure
5: OK - unit fakes cover all required cases plus real-repo expected tables; integration tests gated by KEMIRIX_CI_POSTGRES=1 and GITHUB_ACTIONS=true with scratch DB lifecycle
6: OK - only allowed paths changed, psycopg[binary] sole new dep, no SQLAlchemy/Alembic, no Evidence/Rule DDL
Findings: All six requirements are satisfied by the diff. The connection module keeps psycopg lazy and never echoes credentials; the transaction helper owns explicit boundaries; the migration runner is the single canonical implementation reused by both the CI gate and the development bridge.
Checks: Domain packages remain psycopg-free at import time. The development hook now delegates every SQL decision to the release-venv runner and only transports PG* credentials and the safe JSON status. Integration tests are strictly gated to the isolated CI service.
