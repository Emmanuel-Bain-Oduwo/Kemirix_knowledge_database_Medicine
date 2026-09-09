"""Stable, concurrency-safe KMX id allocation (KMX-003).

No sequences and no new permanent tables: the next number for each level is
computed under a transaction-scoped PostgreSQL advisory lock, so concurrent
transactions in separate connections can never allocate the same id. Ids
are never random and never renumbered — a refresh that re-encounters the
same identity reuses it through exact external identifiers instead of
allocating again.
"""

from .exceptions import KemirixError
from .models import KmxId, KmxLevel

LEVEL_LOCK_KEYS = {
    KmxLevel.INGREDIENT: 910001,
    KmxLevel.CLINICAL_DRUG: 910002,
    KmxLevel.PRODUCT: 910003,
}

LEVEL_PREFIX_LIKE = {
    KmxLevel.INGREDIENT: "KMX-ING-%",
    KmxLevel.CLINICAL_DRUG: "KMX-CD-%",
    KmxLevel.PRODUCT: "KMX-PROD-%",
}


def allocate_kmx_id(connection, level):
    """Allocate the next stable id for one level inside the caller transaction.

    Takes the per-level transaction-scoped advisory lock, reads the current
    maximum numeric suffix and returns max+1. The lock is held until the
    surrounding transaction commits or rolls back, which serializes
    allocation per level without any permanent bookkeeping table.
    """
    if level not in LEVEL_LOCK_KEYS:
        raise KemirixError(f"unsupported KMX level: {level!r}")
    connection.execute("SELECT pg_advisory_xact_lock(%s)", (LEVEL_LOCK_KEYS[level],))
    row = connection.execute(
        "SELECT COALESCE(MAX(RIGHT(kmx_id, 6)::int), 0) FROM kmx.registry WHERE kmx_id LIKE %s",
        (LEVEL_PREFIX_LIKE[level],),
    ).fetchone()
    current = int(row[0]) if row else 0
    if current >= 999_999:
        raise KemirixError(f"KMX id space exhausted for level {level}")
    return KmxId.build(level, current + 1)
