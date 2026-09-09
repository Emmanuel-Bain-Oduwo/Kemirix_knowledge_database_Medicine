PASS
Task-ID: INGESTION-CORE-001
Head-SHA: 727b0d5acf8c85b584e28a09cf43bc916373eb7b
Role: minimax

1: OK - HTTPS-only enforced, source-specific UA, connect/read timeouts, streamed chunks to sink, bounded exponential backoff with jitter, Retry-After (seconds + HTTP-date, capped), per-source RateLimiter (2 rps / 2 concurrency / 5 attempts), NLM hosts capped at 20 rps via rate_policy.
2: OK - 429/408/5xx retryable with bounded budget, deterministic 4xx raises immediately on attempt 1, retry_exhausted carries attempts and last status; all error messages use generic phrasing with no URL, header value, or body content.
3: OK - Streamed to temp, SHA-256, put_immutable, manifest written LAST via Manifest.model_validate; parse_stored_original downloads then parses; parser failure preserves raw + manifest; local files follow hash-then-vault with optional expected_sha256.
4: OK - AcquisitionResult is frozen with extra="forbid" and the required fields; SourceAdapter implements save_original/verify_hash/validate, raises NotImplementedError for acquire/iter_source_items and the identity/Evidence halves; no Rule logic (verified by test).
5: OK - Only download_to added to S3RawObjectStore, streaming via CHUNK_SIZE, covered by Stubber test; no other storage changes.
6: OK - All required scenarios covered offline via httpx MockTransport and FakeStore; only src/sources, src/storage/client.py, and tests/test_ingestion.py changed; no live ingestion, no new dependencies.
Findings: The framework cleanly separates the network boundary (http.py), the vault boundary (acquisition.py), the typed result (results.py), and the frozen adapter concept (base.py). Error messages are scrubbed of URLs/headers/bodies, and the parser boundary is enforced by parse_stored_original downloading before parsing.
Checks: Every required test scenario is present and offline; the storage client change is minimal and Stubber-tested; the adapter concept correctly defers lane-specific work to Phases 9-10 with explicit NotImplementedError boundaries.
