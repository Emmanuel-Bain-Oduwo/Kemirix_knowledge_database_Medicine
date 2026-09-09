"""The psycopg-backed KMX repository over the five frozen tables.

Reads: active external-identifier bindings and level-filtered normalized
name candidates for the deterministic resolver. Writes: mapping-exception
recording with full provenance only (identity creation lives in the later
builder phases). psycopg is imported lazily inside methods so importing the
domain packages never loads it.
"""

from .exceptions import MappingExceptionBoundaryError
from .models import KmxLevel

REASON_CODES = (
    "NO_MATCH",
    "MULTIPLE_MATCHES",
    "IDENTIFIER_CONFLICT",
    "FORMULATION_AMBIGUITY",
    "PRODUCT_IDENTITY_UNPROVEN",
)


class ExternalBinding:
    """One active external identifier bound to exactly one KMX per source."""

    __slots__ = ("kmx_id", "level", "source_id")

    def __init__(self, kmx_id, level, source_id):
        self.kmx_id = kmx_id
        self.level = level
        self.source_id = source_id


class NameCandidate:
    """One registry row reachable through a normalized name."""

    __slots__ = ("kmx_id", "level", "normalized_name")

    def __init__(self, kmx_id, level, normalized_name):
        self.kmx_id = kmx_id
        self.level = level
        self.normalized_name = normalized_name


class KmxRepository:
    """Read bindings/names and record mapping exceptions. Nothing else."""

    def __init__(self, connection):
        self._connection = connection

    def external_bindings(self, identifier_system, identifier_value):
        """Active bindings of one exact external identifier, if any."""
        rows = self._connection.execute(
            "SELECT kmx_id, r.level, source_id FROM kmx.external_identifier e "
            "JOIN kmx.registry r ON r.kmx_id = e.kmx_id "
            "WHERE e.identifier_system = %s AND e.identifier_value = %s "
            "AND e.active AND r.status = 'active'",
            (identifier_system, identifier_value),
        ).fetchall()
        return [ExternalBinding(row[0], row[1], row[2]) for row in rows]

    def name_candidates(self, normalized_name, *, level=None):
        """Active registry rows sharing one exact normalized name.

        The level filter narrows to one KMX level when the caller needs it;
        it never widens or remaps identity.
        """
        if level is not None and level not in KmxLevel.ALL:
            raise MappingExceptionBoundaryError(f"unknown KMX level: {level!r}")
        if level is None:
            rows = self._connection.execute(
                "SELECT kmx_id, level, normalized_name FROM kmx.registry "
                "WHERE normalized_name = %s AND status = 'active'",
                (normalized_name,),
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT kmx_id, level, normalized_name FROM kmx.registry "
                "WHERE normalized_name = %s AND level = %s AND status = 'active'",
                (normalized_name, level),
            ).fetchall()
        return [NameCandidate(row[0], row[1], row[2]) for row in rows]

    def get_kmx(self, kmx_id):
        """One registry row or None."""
        row = self._connection.execute(
            "SELECT kmx_id, level, normalized_name FROM kmx.registry "
            "WHERE kmx_id = %s AND status = 'active'",
            (kmx_id,),
        ).fetchone()
        return NameCandidate(row[0], row[1], row[2]) if row else None

    def record_mapping_exception(
        self,
        *,
        lane_id,
        source_id,
        source_version_key,
        source_record_key,
        reason_code,
        normalized_input,
        candidate_kmx_ids=(),
    ):
        """Persist one mapping exception with full provenance. Never resolves it."""
        import json

        if reason_code not in REASON_CODES:
            raise MappingExceptionBoundaryError(f"unknown reason code: {reason_code!r}")
        row = self._connection.execute(
            "INSERT INTO kmx.mapping_exception (lane_id, source_id, "
            "source_version_key, source_record_key, reason_code, "
            "normalized_input, candidate_kmx_ids) "
            "VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb) "
            "RETURNING exception_id",
            (
                lane_id,
                source_id,
                source_version_key,
                source_record_key,
                reason_code,
                json.dumps(normalized_input, sort_keys=True),
                json.dumps(sorted(candidate_kmx_ids)),
            ),
        ).fetchone()
        return row[0]

    # --- write surface used by the builders (the resolver stays read-only) ---

    def insert_kmx(self, *, kmx_id, level, preferred_name, normalized_name):
        """Insert one registry row (the caller owns the transaction)."""
        self._connection.execute(
            "INSERT INTO kmx.registry (kmx_id, level, preferred_name, normalized_name) "
            "VALUES (%s, %s, %s, %s)",
            (kmx_id, level, preferred_name, normalized_name),
        )

    def insert_external_identifier(
        self, *, kmx_id, identifier_system, identifier_value, source_id, jurisdiction=None
    ):
        """Bind one external identifier to exactly one KMX assertion."""
        self._connection.execute(
            "INSERT INTO kmx.external_identifier (kmx_id, identifier_system, "
            "identifier_value, source_id, jurisdiction) VALUES (%s, %s, %s, %s, %s)",
            (kmx_id, identifier_system, identifier_value, source_id, jurisdiction),
        )

    def insert_name(self, *, kmx_id, normalized_name, name_type, source_id, language="en"):
        """Add one name index entry. Names never mint identity."""
        self._connection.execute(
            "INSERT INTO kmx.name_index (kmx_id, normalized_name, name_type, "
            "source_id, language) VALUES (%s, %s, %s, %s, %s)",
            (kmx_id, normalized_name, name_type, source_id, language),
        )

    def insert_containment(
        self, *, container_kmx_id, member_kmx_id, relationship_type, ordinal=None
    ):
        """Record one containment edge with its deterministic ordinal."""
        self._connection.execute(
            "INSERT INTO kmx.contains (container_kmx_id, member_kmx_id, "
            "relationship_type, ordinal) VALUES (%s, %s, %s, %s)",
            (container_kmx_id, member_kmx_id, relationship_type, ordinal),
        )

    def existing_containment(self, *, container_kmx_id, member_kmx_id, relationship_type):
        """True when this exact containment edge already exists."""
        row = self._connection.execute(
            "SELECT 1 FROM kmx.contains WHERE container_kmx_id = %s "
            "AND member_kmx_id = %s AND relationship_type = %s",
            (container_kmx_id, member_kmx_id, relationship_type),
        ).fetchone()
        return row is not None
