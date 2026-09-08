"""Storage contract errors."""

from kmx.exceptions import KemirixError


class StorageContractError(KemirixError):
    """A violation of the frozen Object Storage / manifest contract."""
