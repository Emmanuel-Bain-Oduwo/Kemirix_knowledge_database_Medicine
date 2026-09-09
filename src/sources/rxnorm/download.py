"""Authenticated UTS download of the pinned RxNorm release.

The credential is the UTS API key from the UTS_API_KEY environment variable
only; the key is passed as a query parameter to the official Download API
and never logged, echoed into errors or persisted. The official pinned MD5
is verified before the canonical SHA-256 is computed (S3 ETag is never a
hash). Downloads run through the shared Phase 4 HTTP client, so NLM rate
limits are respected and 429/Retry-After semantics apply.
"""

import os
from pathlib import Path
from urllib.parse import quote

from ..exceptions import SourceContractError
from ..http import SourceHttpClient
from .release import (
    DISCOVERY_URL,
    PINNED_DOWNLOAD_URL,
    PINNED_FILENAME,
    PINNED_OFFICIAL_MD5,
    ReleaseMismatchError,
    parse_release_discovery,
    verify_pinned,
)

UTS_API_KEY_ENV = "UTS_API_KEY"
DOWNLOAD_API = "https://uts-ws.nlm.nih.gov/download"


def build_download_url(api_key):
    """The authenticated download URL; the key never appears in any log."""
    if not api_key or not api_key.strip():
        raise SourceContractError(f"{UTS_API_KEY_ENV} is missing or empty")
    return f"{DOWNLOAD_API}?url={quote(PINNED_DOWNLOAD_URL, safe='')}&apiKey={api_key}"


def fetch_current_release(client):
    """Run official release discovery and verify the pin before downloading."""
    import io
    import json

    sink = io.BytesIO()
    client.get_to_file(DISCOVERY_URL, sink)
    try:
        payload = json.loads(sink.getvalue().decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise SourceContractError("release discovery returned malformed JSON") from None
    discovered = parse_release_discovery(payload)
    try:
        verify_pinned(discovered)
    except ReleaseMismatchError:
        raise
    return discovered


def download_pinned_release(client, api_key, destination):
    """Stream the pinned release into a binary destination (temp file)."""
    url = build_download_url(api_key)
    return client.get_to_file(url, destination)


def verify_official_md5(path):
    """Verify the downloaded file against the official pinned MD5."""
    from storage.checksum import md5_file

    actual = md5_file(Path(path))
    if actual != PINNED_OFFICIAL_MD5:
        raise SourceContractError(
            "pinned release MD5 mismatch: the downloaded artifact does not "
            f"match the official {PINNED_FILENAME} checksum"
        )
    return actual


def require_uts_api_key(env=None):
    """Read the UTS API key from the environment; never log the value."""
    source = env if env is not None else os.environ
    api_key = source.get(UTS_API_KEY_ENV)
    if not api_key or not api_key.strip():
        raise SourceContractError(
            f"the pinned RxNorm download requires the {UTS_API_KEY_ENV} "
            "environment credential (UTS account with UMLS license)"
        )
    return api_key


def make_client():
    """The shared NLM-capped HTTP client for UTS control-plane calls."""
    return SourceHttpClient(
        source_id="rxnorm_athena",
        requests_per_second=2.0,
        policy_host="uts-ws.nlm.nih.gov",
    )
