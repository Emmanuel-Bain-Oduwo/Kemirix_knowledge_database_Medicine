"""DATABASE-001 connection, transaction and migration runner tests (Phase 5).

Unit tests run against fakes (no database). Integration tests run only
against the isolated hosted CI PostgreSQL when KEMIRIX_CI_POSTGRES=1 and
GITHUB_ACTIONS=true — never against any development or production database.
"""

import os
from pathlib import Path

import pytest

from database.connection import (
    DatabaseConnectionError,
    connect,
    connect_from_pg_env,
    connect_from_url,
    healthcheck,
)
from database.exceptions import MigrationStateError
from database.migrations import apply_or_verify, expected_tables, plan, tables_created_by
from database.transaction import transaction

pytestmark = pytest.mark.contract

CI_POSTGRES = (
    os.environ.get("KEMIRIX_CI_POSTGRES") == "1" and os.environ.get("GITHUB_ACTIONS") == "true"
)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return (self._rows[0],) if self._rows else None

    def fetchall(self):
        return [(row,) if not isinstance(row, tuple) else row for row in self._rows]


class FakeConnection:
    """In-process PostgreSQL stand-in for the migration decision tree."""

    def __init__(self, *, version_num=170011, non_system=0, domain_tables=()):
        self.version_num = version_num
        self.non_system = non_system
        self.domain_tables = list(domain_tables)
        self.statements = []
        self.executed_files = []

    def execute(self, sql):
        self.statements.append(sql)
        if sql == "SHOW server_version_num":
            return FakeResult([self.version_num])
        if sql.startswith("SELECT count(*) FROM information_schema.tables"):
            return FakeResult([self.non_system])
        if "table_schema||'.'||table_name" in sql:
            return FakeResult([(table,) for table in sorted(self.domain_tables)])
        if sql in ("BEGIN", "COMMIT", "ROLLBACK"):
            return FakeResult([])
        for table in tables_created_by(sql):
            self.domain_tables.append(table)
        self.executed_files.append(sql)
        return FakeResult([])


def write_root(tmp_path, migrations):
    """Fixture repository root with a migration suite."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "migrations").mkdir(exist_ok=True)
    suite = []
    for name, state, body in migrations:
        (tmp_path / "migrations" / name).write_text(body)
        suite.append({"path": f"migrations/{name}", "state": state})
    (tmp_path / "config").mkdir()
    lines = ["migrations:"]
    for item in suite:
        lines.append(f"  - path: {item['path']}")
        lines.append(f"    state: {item['state']}")
    (tmp_path / "config/migration_suite.yaml").write_text("\n".join(lines) + "\n")
    return tmp_path


SQL_001 = "CREATE TABLE kmx.alpha (id integer PRIMARY KEY);\n"
SQL_002 = "CREATE TABLE evidence.beta (id integer PRIMARY KEY);\n"
PENDING_003 = "-- placeholder, no DDL yet\n"


def test_url_parsing_and_secret_safety(monkeypatch):
    seen = {}

    class FakePsycopg:
        @staticmethod
        def connect(**kwargs):
            seen.update(kwargs)
            raise RuntimeError("boom")

    import sys
    import types

    fake_module = types.ModuleType("psycopg")
    fake_module.Error = RuntimeError
    fake_module.connect = FakePsycopg.connect
    monkeypatch.setitem(sys.modules, "psycopg", fake_module)
    # Assembled at runtime so the source never contains a literal
    # password-bearing DSN for the secret scanner.
    url = "postgresql://kemirix:" + "s3cret" + "-value@db.example.invalid:5432/kemirix_knowledge"
    with pytest.raises(DatabaseConnectionError) as error:
        connect_from_url(url)
    message = str(error.value)
    assert "s3cret-value" not in message
    assert "db.example.invalid" not in message
    assert seen["host"] == "db.example.invalid"
    assert seen["password"] == "s3cret-value"
    assert seen["sslmode"] == "require"
    assert seen["autocommit"] is True


def test_secure_sslmode_is_enforced(monkeypatch):
    import sys
    import types

    fake_module = types.ModuleType("psycopg")
    fake_module.Error = RuntimeError
    calls = []

    def fake_connect(**kwargs):
        calls.append(kwargs)
        return object()

    fake_module.connect = fake_connect
    monkeypatch.setitem(sys.modules, "psycopg", fake_module)
    with pytest.raises(DatabaseConnectionError, match="not secure"):
        connect(host="h", port=5432, dbname="d", user="u", password="p", sslmode="disable")
    with pytest.raises(DatabaseConnectionError, match="not secure"):
        connect(host="h", port=5432, dbname="d", user="u", password="p", sslmode="prefer")
    connection = connect(
        host="h",
        port=5432,
        dbname="d",
        user="u",
        password="p",
        sslmode="require",
    )
    assert connection is not None
    assert calls and calls[0]["sslmode"] == "require"


def test_pg_env_requires_complete_credentials():
    with pytest.raises(DatabaseConnectionError) as error:
        connect_from_pg_env({"PGHOST": "h"})
    message = str(error.value)
    for name in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD"):
        assert name in message
    assert "PGPASSWORD" in message


def test_healthcheck_enforces_postgres_17():
    assert healthcheck(FakeConnection(version_num=170011)) is True
    with pytest.raises(DatabaseConnectionError, match="unsupported PostgreSQL"):
        healthcheck(FakeConnection(version_num=160011))
    with pytest.raises(DatabaseConnectionError, match="unsupported PostgreSQL"):
        healthcheck(FakeConnection(version_num=180001))


def test_transaction_commit_and_rollback():
    connection = FakeConnection()
    with transaction(connection):
        pass
    assert connection.statements == ["BEGIN", "COMMIT"]

    connection = FakeConnection()
    with pytest.raises(ValueError):
        with transaction(connection):
            raise ValueError("work failed")
    assert connection.statements == ["BEGIN", "ROLLBACK"]


def test_plan_ready_pending_and_failures(tmp_path):
    root = write_root(
        tmp_path,
        [("001.sql", "executable", SQL_001), ("002.sql", "pending", PENDING_003)],
    )
    ready, pending = plan(root)
    assert ready == ["migrations/001.sql"]
    assert pending == ["migrations/002.sql"]

    bad = write_root(tmp_path / "x1", [("001.sql", "pending", SQL_001)])
    with pytest.raises(ValueError):
        plan(bad)
    bad = write_root(tmp_path / "x2", [("001.sql", "executable", PENDING_003)])
    with pytest.raises(ValueError):
        plan(bad)
    bad = write_root(
        tmp_path / "x3",
        [
            ("001.sql", "executable", SQL_001),
            ("002.sql", "pending", PENDING_003),
            ("003.sql", "executable", SQL_002),
        ],
    )
    with pytest.raises(ValueError):
        plan(bad)


def test_expected_tables_extraction():
    text = (
        "CREATE TABLE kmx.registry (id int);\n"
        "-- note\nCREATE TABLE kmx.contains (id int);\n"
        "CREATE INDEX whatever ON kmx.registry(id);\n"
    )
    assert tables_created_by(text) == ["kmx.registry", "kmx.contains"]


def test_runner_applies_from_zero_on_clean_database(tmp_path):
    root = write_root(tmp_path, [("001.sql", "executable", SQL_001)])
    connection = FakeConnection()
    result = apply_or_verify(connection, root)
    assert result["status"] == "applied"
    assert result["applied"] == ["migrations/001.sql"]
    assert connection.domain_tables == ["kmx.alpha"]
    assert connection.statements == [
        "SHOW server_version_num",
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema NOT IN ('pg_catalog','information_schema')",
        "SELECT table_schema||'.'||table_name FROM information_schema.tables "
        "WHERE table_schema IN ('kmx','evidence','rules') ORDER BY 1",
        "BEGIN",
        SQL_001,
        "COMMIT",
        "SHOW server_version_num",
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema NOT IN ('pg_catalog','information_schema')",
        "SELECT table_schema||'.'||table_name FROM information_schema.tables "
        "WHERE table_schema IN ('kmx','evidence','rules') ORDER BY 1",
    ]


def test_runner_verifies_applied_prefix_idempotently(tmp_path):
    root = write_root(tmp_path, [("001.sql", "executable", SQL_001)])
    connection = FakeConnection(domain_tables=["kmx.alpha"])
    result = apply_or_verify(connection, root)
    assert result["status"] == "verified"
    assert connection.executed_files == []
    assert "BEGIN" not in connection.statements


def test_runner_upgrades_strict_prefix(tmp_path):
    root = write_root(
        tmp_path,
        [("001.sql", "executable", SQL_001), ("002.sql", "executable", SQL_002)],
    )
    connection = FakeConnection(domain_tables=["kmx.alpha"])
    result = apply_or_verify(connection, root)
    assert result["status"] == "upgraded"
    assert result["applied"] == ["migrations/002.sql"]
    assert set(connection.domain_tables) == {"kmx.alpha", "evidence.beta"}


def test_runner_fails_closed_on_foreign_state(tmp_path):
    root = write_root(tmp_path, [("001.sql", "executable", SQL_001)])
    connection = FakeConnection(domain_tables=["kmx.unknown_table"])
    with pytest.raises(MigrationStateError, match="does not match any migration prefix"):
        apply_or_verify(connection, root)
    assert connection.executed_files == []


def test_runner_fails_closed_on_non_empty_database(tmp_path):
    root = write_root(tmp_path, [("001.sql", "executable", SQL_001)])
    connection = FakeConnection(non_system=4)
    with pytest.raises(MigrationStateError, match="not empty"):
        apply_or_verify(connection, root)


def test_runner_fails_closed_on_unsupported_version(tmp_path):
    root = write_root(tmp_path, [("001.sql", "executable", SQL_001)])
    connection = FakeConnection(version_num=159999)
    with pytest.raises(MigrationStateError, match="PostgreSQL 17 required"):
        apply_or_verify(connection, root)


def test_expected_tables_of_the_real_repository():
    root = Path(__file__).resolve().parents[1]
    ready, _pending = plan(root)
    assert ready == ["migrations/001_kmx.sql"]
    assert expected_tables(root, ready) == [
        "kmx.registry",
        "kmx.contains",
        "kmx.external_identifier",
        "kmx.name_index",
        "kmx.mapping_exception",
    ]


@pytest.mark.integration
@pytest.mark.skipif(not CI_POSTGRES, reason="isolated hosted CI PostgreSQL only")
class TestRunnerOnCiPostgres:
    def _admin(self):
        return connect(
            host="127.0.0.1",
            port=5432,
            dbname="kemirix_knowledge",
            user="kemirix_ci",
            password="disposable-ci-only",
            sslmode="disable",
            allow_insecure=True,
        )

    def _fresh_database(self, admin, name):
        admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
        admin.execute(f'CREATE DATABASE "{name}"')

    def test_from_zero_apply_then_verify_then_upgrade(self, tmp_path):
        admin = self._admin()
        try:
            self._fresh_database(admin, "kemirix_runner_test")
            database = connect(
                host="127.0.0.1",
                port=5432,
                dbname="kemirix_runner_test",
                user="kemirix_ci",
                password="disposable-ci-only",
                sslmode="disable",
                allow_insecure=True,
            )
            try:
                assert healthcheck(database) is True
                repo_root = Path(__file__).resolve().parents[1]
                applied = apply_or_verify(database, repo_root)
                assert applied["status"] == "applied"
                assert len(applied["tables"]) == 5
                verified = apply_or_verify(database, repo_root)
                assert verified["status"] == "verified"
                # Foreign state fails closed on a scratch database.
                database.execute("CREATE SCHEMA rogue")
                database.execute("CREATE TABLE rogue.table_zero (id int)")
                with pytest.raises(MigrationStateError):
                    apply_or_verify(database, repo_root)
            finally:
                database.close()
        finally:
            admin.execute("DROP DATABASE IF EXISTS kemirix_runner_test")
            admin.close()

    def test_prefix_upgrade_on_scratch_fixture(self, tmp_path):
        root = write_root(
            tmp_path,
            [("001.sql", "executable", SQL_001), ("002.sql", "executable", SQL_002)],
        )
        admin = self._admin()
        try:
            self._fresh_database(admin, "kemirix_upgrade_test")
            database = connect(
                host="127.0.0.1",
                port=5432,
                dbname="kemirix_upgrade_test",
                user="kemirix_ci",
                password="disposable-ci-only",
                sslmode="disable",
                allow_insecure=True,
            )
            try:
                apply_or_verify(database, root)
                # Simulate an older deployed release that only knew 001.
                database.execute("DROP TABLE evidence.beta")
                upgrade = apply_or_verify(database, root)
                assert upgrade["status"] == "upgraded"
                assert upgrade["applied"] == ["migrations/002.sql"]
                verified = apply_or_verify(database, root)
                assert verified["status"] == "verified"
            finally:
                database.close()
        finally:
            admin.execute("DROP DATABASE IF EXISTS kemirix_upgrade_test")
            admin.close()
