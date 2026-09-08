# Frozen invariants

- GitHub is code/config/tests authority. Changes use branches and reviewed PRs; no direct main pushes and no manual runtime editing.
- OVH Object Storage is immutable raw-source authority: preserve original bytes, version, object key, manifest and SHA-256 before transformation.
- OVH Managed PostgreSQL is normalized KMX/Evidence/Rules authority. Use one database, `kemirix_knowledge`, with schemas `kmx`, `evidence`, `rules`. The VM is execution only.
- Agents are engineering assistants only. One writer per task; reviewers do not edit the writer's files. SKILL.md is mandatory.
- No secrets in Git, prompts, logs, source manifests or review artifacts. CI has no production credentials.
- No agent approves Clinical Evidence. Human clinical review and high-stakes Rule activation are separate from engineering approval.
- Deterministic KMX only: ING, CD, PROD. Reuse established exact identifiers. Zero/multiple/conflicting identity matches => `mapping_exception`. No guessed mapping, fuzzy automatic acceptance, salt/base conflation or unproven commercial product identities.
- Distinguish mechanical join level from clinical truth level. Preserve source-specific Evidence and exact source/version/block lineage; duplicate projections are not independent evidence.
- Rules inherit KMX, truth level, category and jurisdiction from approved Evidence. No second medicine resolution at Rule stage. Supporting or classification-only sources do not independently generate prescribing action.
- Use the 24 shared categories. `follow_up` is not a clinical category; it is content within Evidence/Rules. Missing alternatives/monitoring/follow-up remain `not_specified_by_connected_evidence`.
- Python 3.12 and PostgreSQL 17 in CI; use uv, ruff, pytest, configuration validation and migration-from-zero checks on disposable infrastructure.
- No Kubernetes, Kafka, Redis, graph DB, vector DB, Airflow or Celery.
- Phase 0 must not change migrations/001_kmx.sql, migrations/002_evidence.sql or migrations/003_rules.sql, create source adapters, or implement KMX/Evidence/Rules.
