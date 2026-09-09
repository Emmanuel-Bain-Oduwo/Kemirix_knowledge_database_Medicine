"""The small transaction helper: BEGIN -> work -> COMMIT, exception -> ROLLBACK.

Connections are opened with autocommit enabled, so this context manager owns
transaction boundaries explicitly. Identity creation together with
external-ID, containment and name links must run inside one transaction so
KMX identities can never be persisted half-built.
"""

from contextlib import contextmanager

from .exceptions import DatabaseContractError


@contextmanager
def transaction(connection):
    """Run the block inside one explicit PostgreSQL transaction."""
    connection.execute("BEGIN")
    try:
        yield connection
    except BaseException:
        try:
            connection.execute("ROLLBACK")
        except Exception as error:  # pragma: no cover - defensive
            raise DatabaseContractError(
                f"rollback failed ({type(error).__name__}); connection state unknown"
            ) from None
        raise
    connection.execute("COMMIT")
