QA_PASS
Task-ID: INGESTION-CORE-001
Head-SHA: 727b0d5acf8c85b584e28a09cf43bc916373eb7b
Role: nemotron

1: OK - Network bytes stream to temp file, hash, immutable upload, manifest written last; parsers only read stored originals via parse_stored_original; parser failure preserves raw+manifest; failed acquisitions write no manifest.
2: OK - 400/401/403/404 classified deterministic_http and fail on attempt 1; 429 retries with Retry-After (capped 60s) or bounded backoff+jitter; 408/500/502/503/504 and network/timeout errors retry within max_attempts (default 5); exhaustion raises retry_exhausted with attempts and last status; no path flips deterministic↔retryable.
3: OK - No URL, header, body, or credential appears in error messages, HttpFetch headers are not persisted, AcquisitionResult is frozen with extra="forbid" and contains no secret-shaped fields.
4: OK - resolve_kmx, create_source_blocks, build_full_evidence raise explicit NotImplementedError; acquire and iter_source_items are NotImplementedError lane boundaries; no adapter implementation exists in framework.
5: OK - RateLimiter defaults 2 rps/2 concurrency/5 attempts; NLM hosts hard-capped at 20 rps; constructor and rate_policy reject non-positive rates.
6: OK - Changes limited to src/sources (base,http,acquisition,results,__init__), src/storage/client.py (download_to), tests/test_ingestion.py; tests use httpx MockTransport, fake stores, injected clock/sleep; no new deps, no live ingestion, no real bucket writes.
Findings: All six adversarial boundaries hold. The acquisition pipeline enforces raw-before-parse, retry classification is deterministic and exhaustive, secrets never leak into errors or results, phase boundaries are hard NotImplementedError guards, rate limiting is honest and capped, and scope is strictly contained.
Checks: Verified every code path in acquisition.py, http.py, base.py, results.py, and storage/client.py against the six checks. Test suite exercises failure modes (404 leaves no manifest, storage conflict reports storage failure, parser failure preserves vault, adapter boundaries raise NotImplementedError, hash verification streams).
