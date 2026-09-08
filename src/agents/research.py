"""Public engineering research only. Search disabled until an approved backend is supplied."""

import ipaddress
import os
import socket
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin, urlsplit

import httpx

from .security import ensure_no_secrets


class ResearchError(RuntimeError):
    pass


class SearchBackend(Protocol):
    def search(self, query: str, limit: int = 5) -> list[dict]: ...


class DisabledSearch:
    def search(self, query, limit=5):
        raise ResearchError("search_backend_disabled")


@dataclass(frozen=True)
class PublicDocument:
    url: str
    content_type: str
    text: str
    trust: str = "untrusted_public_research_not_clinical_evidence"


def public_target(url, resolver=socket.getaddrinfo):
    ensure_no_secrets(url)
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in [None, 443]
        or parsed.fragment
    ):
        raise ResearchError("public_https_url_required")
    try:
        addresses = {row[4][0] for row in resolver(parsed.hostname, 443, type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
            raise ResearchError("private_or_reserved_target_rejected")
    except OSError:
        raise ResearchError("dns_failure") from None
    return parsed, sorted(addresses)[0]


class ResearchGateway:
    def __init__(
        self,
        backend=None,
        transport=None,
        resolver=socket.getaddrinfo,
        max_bytes=1_000_000,
        max_redirects=3,
        timeout=15,
    ):
        if backend is None and os.environ.get("RESEARCH_SEARCH_PROVIDER", "disabled") != "disabled":
            raise ResearchError("unconfigured_search_backend")
        self.backend = backend or DisabledSearch()
        self.transport, self.resolver = transport, resolver
        self.max_bytes, self.max_redirects, self.timeout = max_bytes, max_redirects, timeout

    def search(self, query, limit=5):
        ensure_no_secrets(query)
        if not 1 <= limit <= 10 or len(query) > 2000:
            raise ResearchError("invalid_search_bounds")
        return self.backend.search(query, limit=limit)

    def fetch(self, url):
        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
            ) as client:
                for hop in range(self.max_redirects + 1):
                    parsed, address = public_target(url, self.resolver)
                    # Pin the vetted IP against rebinding, retaining TLS hostname validation.
                    authority = f"[{address}]" if ":" in address else address
                    pinned = parsed._replace(netloc=authority).geturl()
                    with client.stream(
                        "GET",
                        pinned,
                        headers={
                            "Host": parsed.hostname,
                            "Accept-Encoding": "identity",
                            "User-Agent": "Kemirix-Engineering-Research/0.1",
                            "Accept": "text/html,text/plain,application/json,application/xml",
                        },
                        extensions={"sni_hostname": parsed.hostname},
                    ) as response:
                        if response.status_code in [301, 302, 303, 307, 308]:
                            if hop == self.max_redirects or "location" not in response.headers:
                                raise ResearchError("redirect_limit_or_invalid_redirect")
                            url = urljoin(url, response.headers["location"])
                            continue
                        if response.status_code != 200:
                            raise ResearchError("http_fetch_failed")
                        if response.headers.get("content-encoding", "identity") != "identity":
                            raise ResearchError("compressed_response_rejected")
                        kind = response.headers.get("content-type", "").split(";")[0].lower()
                        if kind not in [
                            "text/html",
                            "text/plain",
                            "application/json",
                            "application/xml",
                            "text/xml",
                        ]:
                            raise ResearchError("unsupported_content_type")
                        body = bytearray()
                        for chunk in response.iter_bytes():
                            body.extend(chunk)
                            if len(body) > self.max_bytes:
                                raise ResearchError("response_size_limit")
                        text = body.decode("utf-8", errors="replace")
                        ensure_no_secrets(text)
                        return PublicDocument(url=url, content_type=kind, text=text)
        except httpx.TimeoutException:
            raise ResearchError("timeout") from None
        except httpx.HTTPError:
            raise ResearchError("network_or_tls_failure") from None
        raise ResearchError("fetch_failed")


def search(query, **kwargs):
    return ResearchGateway().search(query, **kwargs)


def fetch(url, **kwargs):
    return ResearchGateway(**kwargs).fetch(url)
