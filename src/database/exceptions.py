"""Database contract errors."""

from kmx.exceptions import KemirixError


class DatabaseContractError(KemirixError):
    """A violation of the frozen database inventory contract."""


class DatabaseConnectionError(DatabaseContractError):
    """A connection or health failure; never carries credentials."""


class MigrationStateError(DatabaseContractError):
    """The database does not match any valid migration state; fail closed."""
