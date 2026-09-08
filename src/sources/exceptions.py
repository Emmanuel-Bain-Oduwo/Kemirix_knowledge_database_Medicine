"""Source contract errors."""

from kmx.exceptions import KemirixError


class SourceContractError(KemirixError):
    """A violation of the frozen source-lane contract."""
