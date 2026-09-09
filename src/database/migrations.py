"""The deterministic migration runner and the canonical migration plan.

One implementation, reused by the CI gate and the development deploy hook:
read the repository migration-suite readiness, execute only the reviewed
ready prefix in deterministic order inside a single transaction, apply from
zero on a clean PostgreSQL 17, verify an already-applied prefix
idempotently, upgrade by prefix, and fail closed on partial, foreign or
unexpected state. No migration-history table is added to the frozen 5+6+3
inventory: applied state is derived from the tables the ready files create.
"""

import json
import re
import sys
from pathlib import Path

import yaml

from .exceptions import MigrationStateError

DOMAIN_SCHEMAS = ("kmx", "evidence", "rules")
SUPPORTED_MAJOR = 17


def contains_sql(text):
    """Recognize whitespace/comments only, including nested comments and CR endings."""
    i, depth = 0, 0
    while i < len(text):
        if depth:
            if text.startswith("/*", i):
                depth += 1
                i += 2
            elif text.startswith("*/", i):
                depth -= 1
                i += 2
            else:
                i += 1
        elif text[i].isspace():
            i += 1
        elif text.startswith("--", i):
            while i < len(text) and text[i] not in "\r\n":
                i += 1
        elif text.startswith("/*", i):
            depth = 1
            i += 2
        else:
            return True
    if depth:
        raise ValueError("unterminated SQL comment")
    return False


def plan(root):
    """The reviewed executable prefix and the pending placeholders, in order."""
    config = yaml.safe_load((Path(root) / "config/migration_suite.yaml").read_text())["migrations"]
    listed = [item["path"] for item in config]
    actual = [
        p.relative_to(root).as_posix() for p in sorted((Path(root) / "migrations").glob("*.sql"))
    ]
    if listed != actual or not listed or len(set(listed)) != len(listed):
        raise ValueError("migration inventory/order mismatch")
    ready, pending = [], []
    for item in config:
        path = Path(root) / item["path"]
        sql = contains_sql(path.read_text())
        if item["state"] == "pending" and not sql:
            pending.append(item["path"])
        elif item["state"] == "executable" and sql and not pending:
            ready.append(item["path"])
        else:
            raise ValueError("migration declaration/content mismatch or non-prefix execution")
    return ready, pending


def tables_created_by(sql_text):
    """Schema-qualified tables one migration file creates (order preserved)."""
    return re.findall(r"CREATE TABLE\s+([a-z_]+\.[a-z_]+)\s*\(", sql_text, re.IGNORECASE)


def expected_tables(root, ready):
    """Schema-qualified tables the ready migration files create, in order."""
    tables = []
    for relative in ready:
        tables += tables_created_by((Path(root) / relative).read_text())
    return tables


def _inspect(connection):
    version = int(connection.execute("SHOW server_version_num").fetchone()[0])
    if not SUPPORTED_MAJOR * 10000 <= version < (SUPPORTED_MAJOR + 1) * 10000:
        raise MigrationStateError(
            f"PostgreSQL {SUPPORTED_MAJOR} required, found {version // 10000}"
        )
    non_system = int(
        connection.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema NOT IN ('pg_catalog','information_schema')"
        ).fetchone()[0]
    )
    domain_tables = [
        row[0]
        for row in connection.execute(
            "SELECT table_schema||'.'||table_name FROM information_schema.tables "
            "WHERE table_schema IN ('kmx','evidence','rules') ORDER BY 1"
        ).fetchall()
    ]
    return non_system, domain_tables


def _execute_file(connection, path):
    connection.execute(path.read_text())


def apply_or_verify(connection, root):
    """Apply or verify the reviewed executable migration prefix.

    Clean database: apply every ready migration in one transaction, then
    verify. Matching prefix: verified (idempotent). Strict prefix of the
    ready list: upgrade by applying the remaining files in one transaction,
    then verify. Anything else fails closed.
    """
    ready, _pending = plan(root)
    non_system, domain_tables = _inspect(connection)
    per_file = [tables_created_by((Path(root) / relative).read_text()) for relative in ready]
    expected = [table for tables in per_file for table in tables]

    if domain_tables:
        present = set(domain_tables)
        if present == set(expected):
            return {"status": "verified", "applied": list(ready), "tables": sorted(present)}
        # The applied state must be exactly the cumulative tables of a
        # strict prefix of the ready files; otherwise it is foreign.
        cumulative = set()
        applied_count = None
        for index, tables in enumerate(per_file):
            cumulative.update(tables)
            if present == cumulative:
                applied_count = index + 1
        if applied_count is None or applied_count >= len(ready):
            raise MigrationStateError(
                "database state does not match any migration prefix; refusing"
            )
        missing = ready[applied_count:]
        with _transaction(connection):
            for relative in missing:
                _execute_file(connection, Path(root) / relative)
        non_system, domain_tables = _inspect(connection)
        if set(domain_tables) != set(expected):
            raise MigrationStateError("upgrade verification failed; state mismatch")
        return {"status": "upgraded", "applied": list(missing), "tables": sorted(domain_tables)}

    if non_system:
        raise MigrationStateError("database is not empty; refusing from-zero migration")
    with _transaction(connection):
        for relative in ready:
            _execute_file(connection, Path(root) / relative)
    non_system, domain_tables = _inspect(connection)
    if set(domain_tables) != set(expected):
        raise MigrationStateError("from-zero verification failed; state mismatch")
    return {"status": "applied", "applied": list(ready), "tables": sorted(domain_tables)}


def _transaction(connection):
    from .transaction import transaction

    return transaction(connection)


def main(argv=None):
    """Release-venv entry point for the development migration hook.

    Usage: python -m database.migrations <release-root>

    Credentials arrive only through the PG* environment; the status is
    printed as JSON and every failure exits non-zero without ever echoing
    credentials or DSNs.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: python -m database.migrations <release-root>", file=sys.stderr)
        return 2
    root = Path(argv[0]).resolve()
    from .connection import connect_from_pg_env

    connection = connect_from_pg_env(__import__("os").environ)
    try:
        from .connection import healthcheck

        healthcheck(connection)
        result = apply_or_verify(connection, root)
    finally:
        connection.close()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
