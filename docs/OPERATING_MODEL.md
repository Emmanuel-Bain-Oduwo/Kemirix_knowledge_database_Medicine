# Operating model

Read SKILL.md before acting. It is the product constitution; chat history and tmux sessions are not authority. The current scope is engineering foundation 0B–0F, preserving Phase 0A. No KMX/Evidence/Rules, source adapter or domain migration implementation is authorized.

| Authority | Responsibility |
| --- | --- |
| GitHub | Reviewed code, configuration, tests, task contracts and durable engineering memory |
| OVH Object Storage | Immutable approved raw-source originals, versions, manifests and SHA-256 |
| OVH Managed PostgreSQL | Normalized knowledge in kemirix_knowledge: kmx, evidence, rules |
| VM | Replaceable execution, worktrees, development releases and temporary run logs |
| Agents | Engineering assistance within deterministic ownership gates |

Only one production writer is active per task. The Python coordinator validates contracts and paths, records lifecycle changes and builds context. Models never decide coordination authority or clinical approval. Reviewers own separate report paths. See [coordination](AGENT_COORDINATION.md) and [memory](AGENT_MEMORY.md).

Use `agent/<agent>/<task-id>` branches and PRs into `main`, the single permanent branch. When all required automated gates pass (CI, Qwen, GLM, Nemotron, required tests, valid contract, no blockers), GitHub merges automatically with squash merge and the resulting main SHA becomes the approved engineering baseline. There is no direct agent push to main, no develop/staging/release branch and no automatic production deployment; a validated main push deploys its exact tested SHA to the OVH development environment automatically. Runtime changes are reconstructed from Git; never edit current/ manually. See [CI/CD](CI_CD.md).

Codex + GPT-6 Astra is the primary engineering harness; OpenCode + GLM 5.3 is the first fallback harness and OpenCode + Qwen 3.8 the second. Switching from Codex to OpenCode is an explicit writer handoff that preserves the same task, branch, base/HEAD SHA, Git-backed memory, reports and deterministic coordinator state. See [engineering harnesses](ENGINEERING_HARNESSES.md).

Deterministic identity, mapping_exception for zero/multiple/conflicting matches, source-specific Evidence and Rule inheritance remain frozen. follow_up is an Evidence/Rule field when connected Evidence supports it; it is never one of the 24 categories. Code deployment does not approve or activate clinical knowledge.

No Kubernetes, Kafka, Redis, graph/vector DB, Airflow, Celery, model orchestration framework or coordination daemon. New runtime dependencies are limited to Pydantic 2, httpx and PyYAML; existing pytest/ruff remain development tools. psycopg/boto3 wait until actual database/storage implementation needs them.

Human setup and real external validation remain gates before Phase 1: approve and checkpoint this foundation, enable protected GitHub PR/CI/CD settings, provision isolated deployment permissions, run provider checks and the five-agent dry run, and resolve the source-ID/schema questions in KNOWN_ISSUES.md. Implementation presence alone is not evidence that these operations passed.
