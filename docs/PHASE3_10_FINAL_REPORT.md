# Kemirix Phase 3 → 10 Program — Final Integrated Report

**Directive:** 2026-09-09 owner master directive (Phase 3 → Phase 10 autonomous GLM program)
**Program writer:** GLM 5.3 (OpenCode harness, `KEMIRIX_ENGINEERING_HARNESS=opencode-glm-5.3`, seat provenance per D020)
**Program window:** 2026-09-09 (single continuous autonomous session)
**Final deployed main SHA:** `4c94ce31a18ab976e6fd32be62803d138b9f76dd` (verified: DEPLOYED_SHA == expected, integrity PASS, smoke PASS)

---

## Milestones

Every milestone ran the full governed chain: writer checkpoint → real Nebius
MiniMax-M3 independent cross-check → GLM architecture/code review → real
Nebius Nemotron 3 Ultra adversarial QA → foundation CI → deterministic merge
gate MERGE_READY (13/13) → kemirix-agent-gate SUCCESS on the exact PR head →
squash merge → main CI SUCCESS → Deploy development of the exact merged SHA →
verify-runtime PASS → lifecycle closed.

| Phase | Task | Outcome | Merge SHA | Deployed |
|---|---|---|---|---|
| 3 | STORAGE-001 | Immutable OVH S3 raw vault (lazy boto3 client, ten-step put_immutable, streaming checksums, manifest-last) | `0667b26` | ✅ |
| 4 | INGESTION-CORE-001 | Shared acquisition framework (frozen HTTP retry classification, Retry-After, per-source rate limits, NLM cap, parser boundary, AcquisitionResult) | `afb952a` | ✅ |
| 5 | DATABASE-001 | Psycopg 3 layer + canonical migration runner (from-zero, idempotent verify, prefix upgrades, fail-closed state validation; stdlib-only runtime bridge) | `9f97f46` | ✅ (live migration-runner verification on dev DB) |
| 6 | KMX-001 | **Reconciliation audit:** canonical KMX DDL already fully satisfied by KMX-SCHEMA-001 (merged `b36b909`, PR #6; applied live, proven through DATABASE-001); no code change per the directive (no duplication of correct work) | satisfied-by-prior-work | n/a (no code) |
| 7 | KMX-002 | Deterministic resolver + repository + conservative normalizer (IDENTIFIER_CONFLICT, MULTIPLE_MATCHES, NO_MATCH, FORMULATION_AMBIGUITY, PRODUCT_IDENTITY_UNPROVEN; no AI path — AST-proven) | `279f9d0` | ✅ |
| 8 | KMX-003 | ING/CD/PROD builders (advisory-lock stable IDs, PIN proven-only links, MIN refusal, combination ordinals, strict PROD proof gate: S08/S26/S27 + exact regulator identifier only) | `c0f18e6` | ✅ |
| 9 | S01-RXNORM-001 | Production RxNorm adapter/RRF parser/KMX loader (verified-live discovery + PINNED_RELEASE_MISMATCH, UTS download with MD5, official RXCUI2→RELA→RXCUI1 directions, deterministic passes A–G, zero PROD, idempotent reruns) | `8543ed7` | ✅ |
| 10 | IDENTITY-SOURCES-001 | S02–S05 enrichment code (OMOP into existing KMX, GSRS UNII with salt/base preservation + openFDA canary, ChEBI curated bridge + UniChem non-identity connectivity, MED-RT paired-release discovery + crosswalks) | `cc29a09` | ✅ |
| — | PHASE310-FINAL-TOOLING-001 | Final live-execution tooling (adapter statistics return; turnkey `scripts/live_rxnorm.py`; MiniMax REQUEST_CHANGES loop exercised and resolved) | `4c94ce3` | ✅ |

**Tests:** 446 passing (plus 4 CI-gated integration tests that run only on the
isolated hosted CI PostgreSQL 17). Ruff clean; config validation clean
(27 lanes); secret scan clean at every checkpoint.

## The authorized live ingestion — status

The one authorized live load is the **pinned RxNorm full monthly release**:

- File: `RxNorm_full_09082026.zip`
- Release date/version: `2026-09-08`
- Official MD5: `34dd95b0ae128fb81bc68166944514f2`
- Official URL: `https://download.nlm.nih.gov/umls/kss/rxnorm/RxNorm_full_09082026.zip`
- Target vault key: `rxnorm_athena/2026-09-08/__release__/original/RxNorm_full_09082026.zip`

The code is **complete, merged, deployed and reviewed** (discovery verified
live during Phase 9 — the official endpoint currently returns exactly this
release). The run is blocked by exactly two absent owner-side credentials
(verified by a full audit of the environment, `/srv/kemirix/secrets/`, and
the root-owned `/etc/kemirix/app.env` and `/etc/kemirix/agents.env` variable
names):

### BLOCKER 1 — UTS API key (authenticated RxNorm download)
- **Why it blocks:** the pinned release requires an authenticated UTS
  Download API call (`UTS_API_KEY`); unauthenticated downloads are refused.
- **Exact owner action:** create a UTS API key (UTS account with an accepted
  UMLS license) and export `UTS_API_KEY=<key>` in the run environment.

### BLOCKER 2 — OVH Object Storage credentials (immutable vault upload)
- **Why it blocks:** `put_immutable` needs `KEMIRIX_S3_ACCESS_KEY_ID` and
  `KEMIRIX_S3_SECRET_ACCESS_KEY` for the `kemirix-knowledge-raw` bucket (and
  the bucket region must be confirmed — the config default is `gra`).
- **Exact owner action:** create S3 credentials for the bucket in the OVH
  control panel (Object Storage → S3 users) and export both variables (plus
  `KEMIRIX_S3_ENDPOINT_URL`/`KEMIRIX_S3_REGION` if the bucket is not in
  `gra`).

### Turnkey run (after both are provisioned)

```bash
cd /srv/kemirix/runtime/development/current
export UTS_API_KEY=<key>
export KEMIRIX_S3_ACCESS_KEY_ID=<access>
export KEMIRIX_S3_SECRET_ACCESS_KEY=<secret>
.venv/bin/python scripts/live_rxnorm.py
```

The script: verifies the credentials before touching anything external,
runs official discovery + pin verification (fails closed on
`PINNED_RELEASE_MISMATCH`), downloads, verifies the official MD5, computes
the SHA-256, uploads immutably, writes the manifest last, parses the stored
copy, loads KMX ING/CD deterministically, **reruns the full flow proving
idempotency** (no duplicate bytes, no new KMX for exact existing RXCUIs),
enforces the hard invariant **KMX-PROD from RxNorm = 0** (non-zero exit on
violation) and prints the QA metrics (release metadata, raw object key,
SHA-256, upstream MD5, loader statistics, KMX ING/CD/PROD counts, RXCUI
bindings, combination CDs, mapping exceptions by reason).

## Explicitly not started

```text
Evidence not started.
Rules not started.
Phase 11 real regulator PROD ingestion not started.
S02-S05 real bulk downloads not started.
```

The roadmap after the live ingestion completes is Phase 11 per the approved
execution book (product identity lanes S08/S26/S27, then EVIDENCE-001).

## Program governance record

- PRs: #15 (STORAGE-001), #16 (INGESTION-CORE-001), #17 (DATABASE-001),
  #18 (KMX-002), #19 (KMX-003), #20 (S01-RXNORM-001), #21
  (IDENTITY-SOURCES-001), #22 (PHASE310-FINAL-TOOLING-001); KMX-001 was an
  audit record with no PR (satisfied by prior work, directive rule).
- Independent provider seats: MiniMax-M3 and Nemotron 3 Ultra ran as genuine
  independent Nebius calls on every milestone, bound to the exact reviewed
  checkpoint SHAs; the GLM review seat executed under the owner-approved
  D020 exception with provenance recorded in every report.
- One governance loop was genuinely exercised: PHASE310-FINAL-TOOLING-001
  received a MiniMax REQUEST_CHANGES (valid credential-ordering finding) and
  was fixed and re-reviewed through the fixes → checkpoint → re-review flow.
- The task ownership gate also refused one out-of-scope edit during
  IDENTITY-SOURCES-001 (a `src/kmx` change outside allowed paths); it was
  reverted and reimplemented caller-side.
