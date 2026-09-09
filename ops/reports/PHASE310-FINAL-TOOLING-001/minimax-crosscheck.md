PASS
Task-ID: PHASE310-FINAL-TOOLING-001
Head-SHA: 958de909cdaa0459708dbfb9cd610d831449f5ca
Role: minimax

1: OK - credential checks (S3RawObjectStore.from_environment and require_uts_api_key) now execute before dev_database_env/connect_from_pg_env/healthcheck, so missing UTS_API_KEY or KEMIRIX_S3_* fails closed before any external touch
2: OK - diff shows only the reordering plus a clarifying comment; adapter statistics return, rerun idempotency, zero-PROD hard invariant, QA metrics JSON, in-process credential-file parsing, and secret-free surface are untouched
3: OK - the diff is minimal (two moved statements and three added comment lines), no other behavior or control flow changed
Findings: The fix correctly hoists both credential validations above the database connection and healthcheck, satisfying the fail-closed-before-any-external-touch invariant. No other code paths, return values, or invariants were altered. The change is surgical and confined to the ordering of these two statements plus an explanatory comment.
Checks: Verified the new ordering places S3RawObjectStore.from_environment and require_uts_api_key before pg_env/connect_from_pg_env/healthcheck. Confirmed the diff contains only the reordering and a comment, with no other behavioral changes. All previously approved invariants remain intact.
