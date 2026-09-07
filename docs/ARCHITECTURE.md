# Final Architecture

## Purpose

Keep the system simple: every source resolves to KMX-ING, KMX-CD or KMX-PROD, clinical content is organized into shared categories, and executable Evidence produces Rules that inherit the same KMX target and category.

```text
27 SOURCES
   ↓
API / BULK DB / PDF / WEB / MANUAL
   ↓
OVH VM
   ├── acquire
   ├── validate
   ├── parse
   └── resolve KMX
   ↓
OVH OBJECT STORAGE
raw originals + manifest
   ↓
KMX-ING / KMX-CD / KMX-PROD
   ↓
SOURCE BLOCK
   ↓
24 CLINICAL CATEGORIES
   ↓
CLINICAL EVIDENCE
   ↓
EXECUTABLE?
   ├── no → Evidence only
   └── yes → Full Rule
               ↓
          same KMX + category
   ↓
OVH MANAGED POSTGRESQL
   ├── kmx
   ├── evidence
   └── rules
   ↓
DBEAVER VIEWER
```

## Responsibilities

- GitHub: source definitions, architecture, code and tests.
- VM: acquisition and processing only.
- Object Storage: original source artifacts and snapshots only.
- Managed PostgreSQL: normalized KMX, Evidence and Rules.
- DBeaver: human inspection of PostgreSQL.

No graph database is required. Raw source databases are not copied wholesale into the production knowledge schemas; large dumps can be restored/read temporarily on the VM and only the normalized Kemirix result is written to Managed PostgreSQL.
