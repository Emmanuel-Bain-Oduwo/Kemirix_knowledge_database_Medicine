"""Evidence statuses and the join/truth level semantics.

join_level records where the source mechanically connected; truth_level records
which KMX level the complete Evidence package actually applies to. They reuse
the single KMX level vocabulary and are never duplicated as separate enums.
"""

from pathlib import Path

import yaml

from kmx.exceptions import ConfigurationError
from kmx.models import KmxLevel

STATUS_VALUES = ("draft", "approved", "stale", "retired")

# The join and truth levels share one vocabulary with two distinct meanings.
JoinLevel = KmxLevel
TruthLevel = KmxLevel


class EvidenceStatus:
    """Frozen Evidence statuses; a model never grants clinical approval."""

    DRAFT, APPROVED, STALE, RETIRED = STATUS_VALUES
    ALL = STATUS_VALUES

    def __new__(cls):
        raise TypeError("EvidenceStatus is a constants namespace")

    @classmethod
    def parse(cls, value):
        if value not in STATUS_VALUES:
            raise ConfigurationError(f"unknown Evidence status: {value!r}")
        return value


def load_jurisdictions(root):
    """Load config/jurisdictions.yaml (frozen jurisdiction identifiers)."""
    path = Path(root) / "config/jurisdictions.yaml"
    data = yaml.safe_load(path.read_text()) or {}
    jurisdictions = data.get("jurisdictions")
    if not isinstance(jurisdictions, dict) or not jurisdictions:
        raise ConfigurationError("jurisdictions.yaml must map identifiers to descriptions")
    return tuple(jurisdictions)
