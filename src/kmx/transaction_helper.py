"""The per-build transaction scope for the KMX builders.

Mirrors the frozen database.transaction contract (BEGIN -> work -> COMMIT,
exception -> ROLLBACK) so the kmx package stays free of cross-domain
imports. Connections are opened with autocommit; each build call owns its
own atomic transaction.
"""

from contextlib import contextmanager

from .exceptions import KemirixError


@contextmanager
def owning_transaction(connection):
    """Run the block inside one explicit PostgreSQL transaction."""
    connection.execute("BEGIN")
    try:
        yield connection
    except BaseException:
        try:
            connection.execute("ROLLBACK")
        except Exception as error:  # pragma: no cover - defensive
            raise KemirixError(
                f"rollback failed ({type(error).__name__}); connection state unknown"
            ) from None
        raise
    connection.execute("COMMIT")
