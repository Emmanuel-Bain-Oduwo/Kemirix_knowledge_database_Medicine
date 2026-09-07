# OVH Ingestion VM

## Role

One VM is enough initially. It is a worker/processing machine, not the clinical database authority.

The VM will eventually run:

- source API clients
- bulk-file downloaders
- PDF/XML/JSON/CSV/TSV parsers
- temporary import/restore jobs for large source databases
- KMX resolver
- Evidence builder
- Rule builder/validator
- Object Storage client
- PostgreSQL client

## Data path

```text
UPSTREAM SOURCES
      ↓
OVH VM
  ├── acquire
  ├── checksum
  ├── store raw original → Object Storage
  ├── parse
  ├── resolve KMX
  ├── build Evidence
  └── build approved Rules
      ↓
OVH Managed PostgreSQL
```

Temporary source database restores can use VM disk and can be deleted after normalized extraction. Production clinical truth remains in Managed PostgreSQL.
