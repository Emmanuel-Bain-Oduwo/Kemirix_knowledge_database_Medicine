# DBeaver Database Viewer

DBeaver is the human database viewer for the OVH Managed PostgreSQL instance.

```text
Laptop / DBeaver
      │
      │ PostgreSQL over TLS
      ▼
OVH Managed PostgreSQL
      │
      ├── kmx
      ├── evidence
      └── rules
```

Recommended saved views/queries during development:

- KMX registry with external identifiers
- KMX-ING → KMX-CD → KMX-PROD relationships
- Evidence grouped by KMX + category + source
- Rules grouped by KMX + category + jurisdiction
- Mapping exceptions
- Rule → Evidence lineage

Do not store database passwords in this repository. Connection secrets remain local or in the deployment secret store.
