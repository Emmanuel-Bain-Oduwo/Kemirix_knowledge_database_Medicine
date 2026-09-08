"""Database contract errors."""

from kmx.exceptions import KemirixError


class DatabaseContractError(KemirixError):
    """A violation of the frozen database inventory contract."""
