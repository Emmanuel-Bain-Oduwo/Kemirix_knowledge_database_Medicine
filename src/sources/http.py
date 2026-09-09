"""The one shared HTTP acquisition client for every source lane.

Frozen classification (owner directive 2026-09-09, Phase 4):

    429                         retry using Retry-After or bounded backoff+jitter
    408 / transient network     bounded retry
    500/502/503/504            bounded retry
    400/401/403/404             deterministic fail; no blind retry
    success                     preserve raw first, then parse the stored copy

Per-source rate limiting uses an internal conservative default far below any
published ceiling; NLM hosts are hard-capped at or below the published
20 requests/second/IP limit. No secret ever enters a header default, a log
line or an exception message.
"""

import random
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from .exceptions import SourceContractError

DEFAULT_REQUESTS_PER_SECOND = 2.0
DEFAULT_MAX_CONCURRENCY = 2
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_CONNECT_TIMEOUT = 10.0
DEFAULT_READ_TIMEOUT = 60.0
DEFAULT_BACKOFF_BASE = 0.5
DEFAULT_BACKOFF_CAP = 30.0
RETRY_AFTER_CAP = 60.0
NLM_RPS_CEILING = 20.0
NLM_HOST_SUFFIX = ".nlm.nih.gov"

RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})

FAILURE_RATE_LIMITED = "rate_limited"
FAILURE_TRANSIENT_HTTP = "transient_http"
FAILURE_DETERMINISTIC_HTTP = "deterministic_http"
FAILURE_TIMEOUT = "timeout"
FAILURE_NETWORK = "network"
FAILURE_RETRY_EXHAUSTED = "retry_exhausted"


class HttpAcquisitionError(SourceContractError):
    """A failed HTTP acquisition; carries safe metadata only, never bodies."""

    def __init__(self, *, failure_class, message, attempts, http_status=None, retryable):
        super().__init__(message)
        self.failure_class = failure_class
        self.attempts = attempts
        self.http_status = http_status
        self.retryable = retryable


class HttpFetch:
    """A successful streamed fetch: status, headers and attempt metadata."""

    __slots__ = ("status_code", "headers", "attempts", "content_type")

    def __init__(self, status_code, headers, attempts, content_type=None):
        self.status_code = status_code
        self.headers = headers
        self.attempts = attempts
        self.content_type = content_type

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"HttpFetch({self.status_code}, attempts={self.attempts})"


class RateLimiter:
    """Per-source politeness: request spacing plus bounded concurrency."""

    def __init__(self, *, requests_per_second, max_concurrency):
        if requests_per_second <= 0:
            raise SourceContractError("requests_per_second must be positive")
        if max_concurrency < 1:
            raise SourceContractError("max_concurrency must be at least 1")
        self._min_interval = 1.0 / requests_per_second
        self._semaphore = threading.Semaphore(max_concurrency)
        self._lock = threading.Lock()
        self._next_slot = 0.0
        self._clock = time.monotonic
        self._sleep = time.sleep

    def _wait_for_slot(self):
        with self._lock:
            now = self._clock()
            start = max(now, self._next_slot)
            self._next_slot = start + self._min_interval
        delay = start - now
        if delay > 0:
            self._sleep(delay)

    @contextmanager
    def request(self):
        self._wait_for_slot()
        with self._semaphore:
            yield


def rate_policy(
    *,
    requests_per_second=DEFAULT_REQUESTS_PER_SECOND,
    max_concurrency=DEFAULT_MAX_CONCURRENCY,
    host=None,
):
    """Build the per-source limiter; NLM hosts are hard-capped at 20 rps."""
    if requests_per_second <= 0:
        raise SourceContractError("requests_per_second must be positive")
    if isinstance(host, str) and host.lower().endswith(NLM_HOST_SUFFIX):
        requests_per_second = min(requests_per_second, NLM_RPS_CEILING)
    return RateLimiter(requests_per_second=requests_per_second, max_concurrency=max_concurrency)


def _parse_retry_after(value, *, now=None, cap=RETRY_AFTER_CAP):
    """Parse a Retry-After header (seconds or HTTP-date), capped for safety."""
    if not value:
        return None
    text = value.strip()
    try:
        seconds = float(text)
    except ValueError:
        try:
            when = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
        if when is None:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        now = now or datetime.now(timezone.utc)
        seconds = (when - now).total_seconds()
    if seconds <= 0:
        return 0.0
    return min(seconds, cap)


class SourceHttpClient:
    """One shared httpx client per source lane with the frozen retry policy."""

    def __init__(
        self,
        *,
        source_id,
        transport=None,
        requests_per_second=DEFAULT_REQUESTS_PER_SECOND,
        max_concurrency=DEFAULT_MAX_CONCURRENCY,
        max_attempts=DEFAULT_MAX_ATTEMPTS,
        connect_timeout=DEFAULT_CONNECT_TIMEOUT,
        read_timeout=DEFAULT_READ_TIMEOUT,
        backoff_base=DEFAULT_BACKOFF_BASE,
        backoff_cap=DEFAULT_BACKOFF_CAP,
        user_agent=None,
        limiter=None,
        policy_host=None,
        clock=time.monotonic,
        sleep=time.sleep,
    ):
        if max_attempts < 1:
            raise SourceContractError("max_attempts must be at least 1")
        self.source_id = source_id
        self.user_agent = user_agent or f"kemirix/{source_id}"
        self.limiter = limiter or rate_policy(
            requests_per_second=requests_per_second,
            max_concurrency=max_concurrency,
            host=policy_host,
        )
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self._clock = clock
        self._sleep = sleep
        self._client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(
                connect=connect_timeout, read=read_timeout, write=60.0, pool=10.0
            ),
            follow_redirects=False,
        )

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def get_to_file(self, url, destination, *, headers=None):
        """Stream one URL into a binary destination under the frozen policy.

        The response body is streamed chunk-by-chunk to the caller's sink; it
        is never fully buffered in memory. Returns HttpFetch metadata on 2xx;
        raises HttpAcquisitionError otherwise (with attempts and a safe
        failure class).
        """
        if not isinstance(url, str) or not url.startswith("https://"):
            raise SourceContractError("acquisition URLs must be HTTPS")
        request_headers = {"User-Agent": self.user_agent}
        if headers:
            request_headers.update({str(k): str(v) for k, v in headers.items()})
        attempts = 0
        last_error = None
        while attempts < self.max_attempts:
            attempts += 1
            retry_after = None
            with self.limiter.request():
                try:
                    with self._client.stream("GET", url, headers=request_headers) as response:
                        if 200 <= response.status_code < 300:
                            for chunk in response.iter_bytes():
                                destination.write(chunk)
                            return HttpFetch(
                                response.status_code,
                                dict(response.headers),
                                attempts,
                                response.headers.get("content-type"),
                            )
                        failure = self._classify_status(response.status_code)
                        retry_after = _parse_retry_after(
                            response.headers.get("retry-after"),
                            cap=RETRY_AFTER_CAP,
                        )
                except httpx.TimeoutException as error:
                    failure = {
                        "class": FAILURE_TIMEOUT,
                        "retryable": True,
                        "message": f"{type(error).__name__} acquiring this resource",
                    }
                    retry_after = None
                except httpx.HTTPError as error:
                    failure = {
                        "class": FAILURE_NETWORK,
                        "retryable": True,
                        "message": f"{type(error).__name__} acquiring this resource",
                    }
                    retry_after = None
            last_error = failure
            if not failure["retryable"]:
                raise HttpAcquisitionError(
                    failure_class=failure["class"],
                    message=failure["message"],
                    attempts=attempts,
                    http_status=failure.get("status"),
                    retryable=False,
                )
            if attempts < self.max_attempts:
                self._sleep(self._backoff_delay(attempts, retry_after))
        detail = ""
        if last_error:
            detail = f": {last_error['message']}"
        raise HttpAcquisitionError(
            failure_class=FAILURE_RETRY_EXHAUSTED,
            message=(
                f"retry budget exhausted acquiring this resource after {attempts} attempts{detail}"
            ),
            attempts=attempts,
            http_status=last_error.get("status") if last_error else None,
            retryable=True,
        )

    def _classify_status(self, status):
        if status == 429:
            return {
                "class": FAILURE_RATE_LIMITED,
                "retryable": True,
                "status": status,
                "message": f"rate limited ({status}) acquiring this resource",
            }
        if status in RETRYABLE_STATUS:
            return {
                "class": FAILURE_TRANSIENT_HTTP,
                "retryable": True,
                "status": status,
                "message": f"transient upstream status {status}",
            }
        return {
            "class": FAILURE_DETERMINISTIC_HTTP,
            "retryable": False,
            "status": status,
            "message": f"deterministic upstream status {status}; not retried",
        }

    def _backoff_delay(self, attempt, retry_after):
        if retry_after is not None:
            return retry_after
        base = min(self.backoff_base * (2 ** (attempt - 1)), self.backoff_cap)
        return random.uniform(0, base) if base > 0 else 0.0
