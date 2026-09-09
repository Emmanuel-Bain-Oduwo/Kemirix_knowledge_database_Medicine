"""KMX identity core: levels, validated KMX IDs, identity errors, the
conservative normalizer, the psycopg-backed repository and the deterministic
resolver."""

from .allocation import allocate_kmx_id
from .builders import Built, KmxBuilder, PreciseParent
from .exceptions import (
    ConfigurationError,
    IdentityResolutionError,
    KemirixError,
    MappingExceptionBoundaryError,
)
from .models import KMX_ID_PATTERN, KmxId, KmxLevel, is_valid_kmx_id
from .normalizer import normalize_name
from .repository import ExternalBinding, KmxRepository, NameCandidate
from .resolver import (
    APPROVED_PRODUCT_CREATORS,
    MappingExceptionOutcome,
    ResolutionRequest,
    Resolved,
    resolve_identity,
)

__all__ = [
    "APPROVED_PRODUCT_CREATORS",
    "Built",
    "KMX_ID_PATTERN",
    "KmxBuilder",
    "PreciseParent",
    "ConfigurationError",
    "ExternalBinding",
    "IdentityResolutionError",
    "KemirixError",
    "KmxId",
    "KmxLevel",
    "KmxRepository",
    "MappingExceptionBoundaryError",
    "MappingExceptionOutcome",
    "NameCandidate",
    "ResolutionRequest",
    "Resolved",
    "allocate_kmx_id",
    "is_valid_kmx_id",
    "normalize_name",
    "resolve_identity",
]
