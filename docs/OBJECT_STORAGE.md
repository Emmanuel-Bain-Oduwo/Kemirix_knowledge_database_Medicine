# OVH Object Storage

## Purpose

Object Storage is the immutable raw source vault. It stores the exact original
artifact acquired from every upstream source before Kemirix transforms it.

Recommended bucket:

```text
kemirix-knowledge-raw
```

## Authority boundary

```text
lane_id   -> manifest only (never in the object key)
source_id -> object key + manifest
Object Storage -> immutable raw source vault
PostgreSQL     -> normalized KMX/Evidence/Rule authority
```

## Layout

The frozen object-key contract (config/storage_contract.yaml, SKILL v5.0
section 10):

```text
<source_id>/<source_version>/<source_record_key>/original/<original_filename>
```

Record-oriented examples:

```text
dailymed/<version>/<SETID>/original/label.xml
openfda_label/<version>/<RXCUI>/original/response.json
ema/<version>/<EMA_PRODUCT>/original/product_information.pdf
mhra/<version>/<PL_NUMBER>/original/spc.pdf
ppb_smpc/<version>/<CTD_OR_REG_ID>/original/smpc.pdf
```

Bulk releases use the literal record key `__release__`:

```text
chembl/<release>/__release__/original/chembl_postgresql.tar.gz
drugcentral/<release>/__release__/original/drugcentral.dump
onsides/<release>/__release__/original/onsides.sqlite
open_targets/<release>/__release__/original/<partition>.parquet
rxnorm_athena/<release>/__release__/original/<official-full-release>.zip
kdigo/<version>/CKD_GUIDELINE/original/guideline.pdf
```

The key is deterministic: the same source version and record always produce the
same key. Keys have five segments; `lane_id` (S01-S27) never appears in a key.

## Upload semantics

Every acquisition follows the frozen immutable upload rule:

```text
download to temporary file
  -> calculate SHA-256
  -> build deterministic object key
  -> HEAD object
       absent      -> upload
       same hash   -> idempotent success
       other hash  -> reject / quarantine
  -> upload manifest last
```

Never overwrite a supposedly immutable original with different bytes. Original
bytes are preserved exactly; parsing never modifies originals. The combination
source_id + source_record_key + source_version uniquely identifies one
immutable upstream version.

## Manifest

Each record/version carries one `manifest.json` describing all artifacts,
uploaded last, with the frozen fields:

- `schema_version` (1)
- `lane_id` (S01-S27; manifest only, never in the object key)
- `source_id` (stable implementation slug, e.g. `dailymed`)
- `source_version`
- `source_record_key`
- `acquisition_mode` (`api` / `bulk` / `db` / `pdf` / `web` / `manual`)
- `fetched_at`
- `upstream_published_at` (or null)
- `adapter_git_sha`
- `rights_status` (`cleared` / `pending_review` / `restricted`)
- `parse_status` (`staged` / `parsed` / `quarantined`)
- `artifacts`: each with `artifact_type`, `original_filename`, `content_type`,
  `byte_size`, `object_key`, `sha256`

Each artifact's `object_key` is exactly
`<source_id>/<source_version>/<source_record_key>/original/<original_filename>`
bound to the manifest provenance; a mismatch fails closed.

Never store credentials, bearer tokens, database passwords or presigned URLs
in the manifest.

## Runtime client (STORAGE-001)

`src/storage/client.py` provides `S3RawObjectStore`, the one client that
moves bytes into the vault (OVH Object Storage, S3 Signature V4, boto3
imported lazily so the domain packages stay import-clean):

- `from_environment()` reads the bucket/endpoint/region from
  `config/object_storage.yaml` (env overrides `KEMIRIX_S3_ENDPOINT_URL`,
  `KEMIRIX_S3_REGION`) and the access credentials **only** from the VM-side
  secret environment (`KEMIRIX_S3_ACCESS_KEY_ID`,
  `KEMIRIX_S3_SECRET_ACCESS_KEY`, optional `KEMIRIX_S3_SESSION_TOKEN`).
  Missing credentials fail closed with an error that names the variables and
  never prints values.
- `put_immutable()` enforces the frozen procedure: the local temp file must
  already be written and closed; its streamed SHA-256 must equal the expected
  value (corrupted downloads are rejected before any remote call); the key
  must satisfy the frozen five-segment pattern; HEAD first — absent means
  upload then streaming verification, the same SHA-256 means idempotent
  success, different bytes fail closed and are never overwritten.
- `exists()` / `verify()` — the SHA-256 in the manifest is canonical; S3 ETag
  is never treated as a hash. Objects without our sha256 metadata are
  verified by streaming, not by trusting ETag.
- `write_manifest()` uploads the manifest **last**, at
  `<source_id>/<source_version>/<source_record_key>/manifest.json`, through
  the frozen hardened Manifest model; an uploaded manifest is never rewritten
  with different bytes.

`src/storage/checksum.py` provides the streaming SHA-256 (canonical) and MD5
(official upstream publication checksums only) helpers.

## Important boundary

Object Storage stores raw source artifacts. KMX identities, normalized
Clinical Evidence and Rules live in Managed PostgreSQL, not in Object Storage.
