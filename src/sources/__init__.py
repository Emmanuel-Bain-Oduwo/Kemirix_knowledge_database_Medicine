"""Sources domain core: config model, common loader, the 27-lane registry
and the shared acquisition framework (HTTP client, results, orchestration
and the frozen SourceAdapter concept)."""

from .acquisition import acquire_file_to_vault, acquire_url_to_vault, parse_stored_original
from .base import SourceAdapter
from .config import SourceConfig, load_source_configs
from .exceptions import SourceContractError
from .http import (
    HttpAcquisitionError,
    HttpFetch,
    RateLimiter,
    SourceHttpClient,
    rate_policy,
)
from .registry import SourceRegistry, load_source_registry
from .results import AcquisitionResult

__all__ = [
    "AcquisitionResult",
    "HttpAcquisitionError",
    "HttpFetch",
    "RateLimiter",
    "SourceAdapter",
    "SourceConfig",
    "SourceContractError",
    "SourceHttpClient",
    "SourceRegistry",
    "acquire_file_to_vault",
    "acquire_url_to_vault",
    "load_source_configs",
    "load_source_registry",
    "parse_stored_original",
    "rate_policy",
]
