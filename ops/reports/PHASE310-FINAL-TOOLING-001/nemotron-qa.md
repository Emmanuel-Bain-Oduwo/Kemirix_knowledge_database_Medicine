QA_PASS
Task-ID: PHASE310-FINAL-TOOLING-001
Head-SHA: 958de909cdaa0459708dbfb9cd610d831449f5ca
Role: nemotron

1: OK - Credential checks (UTS, S3, dev DB) execute before any external touch; no credential values appear in logs, metrics, or commits; dev DB file parsed in-process only.
2: OK - Zero-PROD invariant raises SystemExit on violation; rerun proves idempotency via both loader stats (ing_created/cd_created == 0) and unchanged KMX ING/CD counts; second download exercises put_immutable for vault deduplication.
3: OK - Imports only stdlib and verified internal modules; no network/database ops beyond the specified UTS/S3/PostgreSQL flow; adapter stats addition does not alter frozen flow semantics (vault order, MD5, stored-copy parsing still proven).
4: OK - Diff touches only scripts/live_rxnorm.py, src/sources/rxnorm/adapter.py, tests/test_rxnorm.py; no Evidence/Rule changes, no live downloads in diff, no new dependencies.
Findings: The tooling satisfies all four adversarial properties: secrets fail closed before external contact, invariants are hard-enforced with dual idempotency proof, the flow remains frozen with only authorized modules, and scope is exactly the three permitted files. (Reviewer note on urlsplit: not a defect — urlsplit is the correct stdlib function, the same one scripts/runtime.py itself uses for the credential file.)
Checks: Confirmed credential ordering fails closed with variable names only; confirmed zero-PROD exit and rerun checks both loader stats and database counts; confirmed no hidden imports or external touches; confirmed diff scope matches exactly the three authorized files.
