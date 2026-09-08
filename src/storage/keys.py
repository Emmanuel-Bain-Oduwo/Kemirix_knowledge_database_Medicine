"""Deterministic object keys for the immutable raw vault.

Approved pattern (SKILL v5.0 section 10, frozen by DOMAIN-CONTRACT-001):
  <source_id>/<source_version>/<source_record_key>/original/<original_filename>

lane_id (S01-S27) never appears in an object key; it is preserved inside the
manifest. Bulk releases use the literal record key __release__.
"""

import re

from .exceptions import StorageContractError
from .models import AcquisitionMode

SOURCE_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
LANE_ID_PATTERN = re.compile(r"^S(0[1-9]|1[0-9]|2[0-7])$")
RELEASE_RECORD_KEY = "__release__"

_KEY_SEGMENT = r"[^/]+"


def _segment(value, what):
    if not isinstance(value, str) or not value.strip() or "/" in value or value.startswith("."):
        raise StorageContractError(f"unsafe {what}: {value!r}")
    return value


def validate_source_slug(value):
    if not isinstance(value, str) or not SOURCE_SLUG_PATTERN.fullmatch(value):
        raise StorageContractError(f"source_id must be a stable slug, got {value!r}")
    if LANE_ID_PATTERN.fullmatch(value):
        raise StorageContractError(
            "lane IDs (S01-S27) are never source slugs; keep lane_id in the manifest"
        )
    return value


def validate_lane_id(value):
    if not isinstance(value, str) or not LANE_ID_PATTERN.fullmatch(value):
        raise StorageContractError(f"lane_id must be S01-S27, got {value!r}")
    return value


def build_object_key(source_id, source_version, source_record_key, original_filename):
    """Compose the deterministic object key; every segment is validated."""
    validate_source_slug(source_id)
    _segment(source_version, "source_version")
    _segment(source_record_key, "source_record_key")
    _segment(original_filename, "original_filename")
    return f"{source_id}/{source_version}/{source_record_key}/original/{original_filename}"


def validate_object_key(key, *, acquisition_mode=None):
    """Validate a raw-vault object key against the frozen pattern."""
    if not isinstance(key, str):
        raise StorageContractError(f"object key must be a string, got {type(key)!r}")
    pattern = (
        rf"(?P<source_id>{SOURCE_SLUG_PATTERN.pattern[1:-1]})"
        rf"/{_KEY_SEGMENT}/{_KEY_SEGMENT}/original/{_KEY_SEGMENT}"
    )
    match = re.fullmatch(pattern, key)
    if not match:
        raise StorageContractError(f"object key violates the frozen pattern: {key!r}")
    parts = key.split("/")
    if len(parts) != 5 or parts[3] != "original":
        raise StorageContractError(f"object key must have five segments: {key!r}")
    validate_source_slug(parts[0])
    if acquisition_mode is not None:
        AcquisitionMode.parse(acquisition_mode)
    return key
