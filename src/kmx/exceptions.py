"""Shared error hierarchy rooted in the KMX identity domain.

Small by design: a common base plus the configuration, identity-resolution
and mapping-exception-boundary errors. Storage, database and source contract
errors extend the same base from their own packages.
"""


class KemirixError(Exception):
    """Base class for every domain error."""


class ConfigurationError(KemirixError):
    """Invalid or unverifiable configuration; loading fails closed."""


class IdentityResolutionError(KemirixError):
    """A source item could not be resolved deterministically to KMX."""


class MappingExceptionBoundaryError(KemirixError):
    """Ambiguity must fail closed into kmx.mapping_exception, never be guessed."""
