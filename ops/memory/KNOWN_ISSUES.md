# Known issues and remaining gates

- Migrations are placeholders: all three unchanged SQL files are explicitly pending/non-executable. No schema or clinical correctness claim follows from a foundation CI pass.
- CI not yet validated on GitHub. Local tests/YAML/shell checks do not establish hosted service startup, branch protection or workflow_run delivery.
- Development deployment has not run. Human must configure the four SSH deployment secrets, trusted host-key pinning, development environment, dedicated bare Git repository, uv/Python and isolated deploy/runtime ownership. Workflow must exist on the default branch. No production credentials belong in GitHub.
- Provider smoke tests not yet performed. Credential values were not read. Requested model availability, account entitlements and endpoint compatibility remain unverified. Use the protected EnvironmentFile/operator wrapper method, never loosen /etc/kemirix/agents.env permissions.
- Worktrees not yet initialized. Tooling refuses conflicting branches/checkpoints; no /srv/kemirix/worktrees directories were created in this task. The prepared dry-run base is the pre-foundation commit and must be updated to an approved integrated develop SHA.
- Five-agent dry run is prepared, not executed. No external analysis/review/QA result is fabricated. Provider execution and access separation require human setup.
- Gated writes/submit enforce ownership, but unrestricted shells under one Unix account can bypass them. Operators must restrict reviewer tools/OS write access, protect governance/runtime paths and stop the old writer before handoff. Human approval flags are attestations, not authentication.
- Canonical lifecycle updates and mirrored reports remain uncommitted control-checkout changes until the owner incorporates them into Git. They are not automatically durable in GitHub. One control VM is supported; the file lock is not distributed coordination.
- DBeaver verification pending. Existing documentation describes usage but does not confirm inspection.
- Source configs use slugs while SKILL.md uses S01–S27 IDs. SOURCE_STATUS.yaml maps the two; decide persisted identifier/object-key contracts before domain coding.
- SKILL.md names evidence.source_version and evidence.block_subject beyond the shorter config/database table list. Reconcile the schema contract in a reviewed design task before migrations; no domain DDL was changed here.
- Source rights/access registry and rate limits remain unverified contracts. Source integrations remain not_started.
- Runtime pointer updates are individually atomic; a crash between them produces detectable mismatch requiring operator reconciliation. Partial failed releases are preserved for explicit quarantine. OS/interpreter integrity and a compromised deploy account are outside the release hash guarantee.
- Search backend is intentionally disabled. Existing safe agent web/MCP tools may be used only when already approved; no new paid service/credential was introduced.
- The local sandbox fails during bwrap initialization; approved execution fallback is required for local repository commands.
