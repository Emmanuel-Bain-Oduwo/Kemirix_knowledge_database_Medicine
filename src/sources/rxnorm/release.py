"""Official RxNorm release discovery and pinned-release verification.

The discovery endpoint (verified live 2026-09-09) returns a JSON list:
    [{"fileName": ..., "releaseVersion": ..., "releaseDate": ...,
      "downloadUrl": ..., "releaseType": ..., "product": ..., "current": ...}]

This program pins exactly one release (owner directive): the RxNorm full
monthly release of 2026-09-08. At live execution, discovery runs anyway and
any drift fails closed with PINNED_RELEASE_MISMATCH — a newer release is
never silently ingested, and RxNorm_full_current.zip is never used.
"""

from ..exceptions import SourceContractError

DISCOVERY_URL = (
    "https://uts-ws.nlm.nih.gov/releases?releaseType=rxnorm-full-monthly-release&current=true"
)
RELEASE_TYPE = "RxNorm Full Monthly Release"
PRODUCT = "RxNorm"

PINNED_FILENAME = "RxNorm_full_09082026.zip"
PINNED_RELEASE_VERSION = "2026-09-08"
PINNED_RELEASE_DATE = "2026-09-08"
PINNED_DOWNLOAD_URL = "https://download.nlm.nih.gov/umls/kss/rxnorm/RxNorm_full_09082026.zip"
PINNED_OFFICIAL_MD5 = "34dd95b0ae128fb81bc68166944514f2"

_REQUIRED_FIELDS = (
    "fileName",
    "releaseVersion",
    "releaseDate",
    "downloadUrl",
    "releaseType",
    "product",
    "current",
)


class ReleaseMismatchError(SourceContractError):
    """The live official release does not match the program pin."""


class DiscoveredRelease:
    """One validated release entry from the official discovery endpoint."""

    __slots__ = (
        "file_name",
        "release_version",
        "release_date",
        "download_url",
        "release_type",
        "product",
        "current",
    )

    def __init__(self, entry):
        missing = [field for field in _REQUIRED_FIELDS if field not in entry]
        if missing:
            raise SourceContractError(f"release discovery entry missing: {', '.join(missing)}")
        self.file_name = entry["fileName"]
        self.release_version = entry["releaseVersion"]
        self.release_date = entry["releaseDate"]
        self.download_url = entry["downloadUrl"]
        self.release_type = entry["releaseType"]
        self.product = entry["product"]
        self.current = bool(entry["current"])


def parse_release_discovery(payload):
    """Parse the official discovery response; require exactly one current
    RxNorm full monthly release."""
    if not isinstance(payload, list) or not payload:
        raise SourceContractError("release discovery returned no entries")
    current = []
    for entry in payload:
        release = DiscoveredRelease(entry)
        if not release.current:
            continue
        if release.product != PRODUCT:
            raise SourceContractError(
                f"unexpected product in release discovery: {release.product!r}"
            )
        if release.release_type != RELEASE_TYPE:
            raise SourceContractError(f"unexpected release type: {release.release_type!r}")
        current.append(release)
    if len(current) != 1:
        raise SourceContractError(
            f"expected exactly one current full monthly release, found {len(current)}"
        )
    return current[0]


def verify_pinned(discovered):
    """Fail closed unless the discovered release is exactly the pinned one."""
    if not isinstance(discovered, DiscoveredRelease):
        raise SourceContractError("verify_pinned requires a discovered release")
    checks = (
        ("filename", discovered.file_name, PINNED_FILENAME),
        ("release version", discovered.release_version, PINNED_RELEASE_VERSION),
        ("download URL", discovered.download_url, PINNED_DOWNLOAD_URL),
    )
    for what, actual, expected in checks:
        if actual != expected:
            raise ReleaseMismatchError(
                f"PINNED_RELEASE_MISMATCH ({what}): discovered {actual!r} "
                f"but the program pins {expected!r}"
            )
    return discovered


def pinned_release_metadata():
    """Acquisition metadata for the pinned release (recorded before download)."""
    return {
        "file_name": PINNED_FILENAME,
        "release_version": PINNED_RELEASE_VERSION,
        "release_date": PINNED_RELEASE_DATE,
        "download_url": PINNED_DOWNLOAD_URL,
        "official_md5": PINNED_OFFICIAL_MD5,
        "source_id": "rxnorm_athena",
        "lane_id": "S01",
        "acquisition_mode": "bulk",
        "object_key": (
            f"rxnorm_athena/{PINNED_RELEASE_VERSION}/__release__/original/{PINNED_FILENAME}"
        ),
    }
