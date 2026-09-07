# OVH Object Storage

## Purpose

Object Storage is the source vault. It stores the exact original artifact acquired from every upstream source before Kemirix transforms it.

Recommended bucket:

```text
kemirix-knowledge-raw
```

## Layout

```text
kemirix-knowledge-raw/
  <source_id>/
    <release_or_snapshot>/
      original/
        ...upstream files/responses...
      manifest.json
```

For record-oriented APIs, add the stable source record identifier:

```text
dailymed/<snapshot>/<SETID>/original/label.xml
openfda_label/<snapshot>/<RXCUI>/original/response.json
ema/<snapshot>/<EMA_PRODUCT>/original/product_information.pdf
mhra/<snapshot>/<PL_NUMBER>/original/spc.pdf
ppb_smpc/<snapshot>/<CTD_OR_REG_ID>/original/smpc.pdf
```

For bulk databases:

```text
chembl/<release>/original/chembl_postgresql.tar.gz
drugcentral/<release>/original/drugcentral.dump
onsides/<release>/original/onsides.sqlite
open_targets/<release>/original/*.parquet
```

## Manifest

Each snapshot has a small `manifest.json` with:

- source_id
- source_version/release
- source_record_id when applicable
- retrieved_at
- original object key(s)
- sha256
- acquisition method
- status

## Important boundary

Object Storage stores raw source artifacts. KMX identities, normalized Clinical Evidence and Rules live in Managed PostgreSQL, not in Object Storage.
