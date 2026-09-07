# API Rate Limiting and Caching

Keep API behaviour conservative and simple.

## Shared policy

1. Query only the medicines/identifiers Kemirix needs.
2. Save every successful upstream response to Object Storage.
3. Do not call the upstream API again when the same source/version/record is already cached.
4. On HTTP 429: back off and retry later.
5. On temporary 5xx errors: bounded retries with exponential backoff.
6. Never bypass source terms or published limits.

## Initial internal caps

These are Kemirix-side conservative caps, not claims that every provider publishes the same quota:

- openFDA: 3 requests/second with API key, while remaining within the provider's documented quotas.
- DailyMed: 2 requests/second.
- GSRS/UniChem/OCL and similar APIs without a needed higher rate: 1 request/second initially.
- CPIC/ClinPGx: up to 2 requests/second initially.
- CIViC: 2 requests/second for API use; bulk releases preferred for cloning.
- Web/PDF indexes such as PPB/MHRA/MoH: 1 request/second when automated access is permitted.

Bulk/download sources should use the published release artifact instead of thousands of record-level requests when a full clone is desired.
