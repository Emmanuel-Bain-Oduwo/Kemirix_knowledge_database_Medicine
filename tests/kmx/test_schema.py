"""KMX schema DDL and migration-suite contracts for migrations/001_kmx.sql."""

import re
from pathlib import Path

import pytest
import yaml

from scripts.migration_gate import contains_sql, plan

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
SQL = (ROOT / "migrations/001_kmx.sql").read_text()

TABLES = [
    "kmx.registry",
    "kmx.contains",
    "kmx.external_identifier",
    "kmx.name_index",
    "kmx.mapping_exception",
]


def test_migration_suite_executes_only_kmx_prefix():
    ready, pending = plan(ROOT)
    assert ready == ["migrations/001_kmx.sql"]
    assert pending == ["migrations/002_evidence.sql", "migrations/003_rules.sql"]


def test_later_migrations_remain_placeholders():
    for path in ("migrations/002_evidence.sql", "migrations/003_rules.sql"):
        assert not contains_sql((ROOT / path).read_text())


def test_ddl_matches_database_inventory():
    inventory = yaml.safe_load((ROOT / "config/database.yaml").read_text())
    expected = inventory["database"]["schemas"]["kmx"]
    assert set(TABLES) == set(f"kmx.{name}" for name in expected)
    for table in TABLES:
        assert re.search(rf"CREATE TABLE {re.escape(table)} \(", SQL)
    for forbidden in ("evidence", "rules"):
        assert not re.search(rf"CREATE SCHEMA {forbidden}", SQL)


def test_ddl_is_migration_safe():
    assert "CREATE SCHEMA kmx;" in SQL
    for banned in (
        "DROP ",
        "CREATE DATABASE",
        "CREATE EXTENSION",
        "GRANT ",
        "ALTER SYSTEM",
        "COPY ",
    ):
        assert banned not in SQL
    assert not SQL.rstrip().endswith("\\")
    statements = []
    for statement in SQL.split(";"):
        body = "\n".join(
            line for line in statement.splitlines() if not line.lstrip().startswith("--")
        ).strip()
        if body:
            statements.append(body)
    assert all(s.startswith(("CREATE ", "COMMENT ON ")) for s in statements), statements


def test_kmx_id_format():
    pattern = re.search(r"kmx_id ~ '([^']+)'", SQL).group(1)
    assert pattern == "^KMX-(ING|CD|PROD)-[0-9]{6}$"
    for valid in ("KMX-ING-000412", "KMX-CD-003871", "KMX-PROD-000001"):
        assert re.fullmatch(pattern, valid)
    for invalid in (
        "KMX-PRES-000001",
        "KMX-ING-12",
        "KMX-ING-0004127",
        "KMX-ING-00041a",
        "kmx-ing-000412",
        "KMX-ING_000412",
        "",
    ):
        assert not re.fullmatch(pattern, invalid)


def test_registry_level_prefix_binding():
    for level, prefix in (
        ("ingredient", "KMX-ING-"),
        ("clinical_drug", "KMX-CD-"),
        ("product", "KMX-PROD-"),
    ):
        assert f"level = '{level}'" in SQL
        assert f"kmx_id LIKE '{prefix}%'" in SQL
    assert "UNIQUE (kmx_id, level)" in SQL
    assert "level IN ('ingredient', 'clinical_drug', 'product')" in SQL
    assert "status IN ('active', 'retired')" in SQL
    assert "length(btrim(preferred_name)) > 0" in SQL


def test_contains_level_order_allows_only_downward_edges():
    assert "UNIQUE (kmx_id, level)" in SQL
    assert "(parent_level = 'ingredient' AND child_level = 'clinical_drug')" in SQL
    assert "(parent_level = 'clinical_drug' AND child_level = 'product')" in SQL
    assert "PRIMARY KEY (parent_kmx_id, child_kmx_id)" in SQL
    assert "REFERENCES kmx.registry (kmx_id, level)" in SQL
    assert "CREATE INDEX contains_child_idx ON kmx.contains (child_kmx_id)" in SQL


def test_external_identifier_single_binding():
    assert "UNIQUE (source_id, external_id_type, external_id)" in SQL
    assert "REFERENCES kmx.registry (kmx_id)" in SQL
    pattern = re.search(r"source_id ~ '([^']+)'", SQL).group(1)
    assert pattern == "^S(0[1-9]|1[0-9]|2[0-7])$"
    for valid in ("S01", "S09", "S15", "S27"):
        assert re.fullmatch(pattern, valid)
    for invalid in ("S00", "S28", "S1", "S001", "s01", "S", "S1x"):
        assert not re.fullmatch(pattern, invalid)


def test_name_index_is_lookup_only():
    assert "PRIMARY KEY (name, name_type, kmx_id)" in SQL
    assert "name_type IN ('preferred', 'synonym')" in SQL
    assert "REFERENCES kmx.registry (kmx_id)" in SQL
    assert not re.search("name_index.*GENERATED", SQL)


def test_mapping_exception_preserves_conflicts():
    assert "reason IN ('zero_match', 'multiple_match', 'conflict')" in SQL
    assert "status IN ('open', 'under_review', 'resolved')" in SQL
    assert "(status = 'resolved') = (resolved_at IS NOT NULL)" in SQL
    assert "detail               jsonb       NOT NULL" in SQL
    assert "resolution_kmx_id" in SQL
    assert re.search(
        r"source_id IS NOT NULL\s*\n\s*OR external_id IS NOT NULL"
        r"\s*\n\s*OR length\(btrim\(coalesce\(name_text, ''\)\)\) > 0",
        SQL,
    )


def test_migration_suite_declaration_matches_config():
    suite = yaml.safe_load((ROOT / "config/migration_suite.yaml").read_text())
    states = {item["path"]: item["state"] for item in suite["migrations"]}
    assert states["migrations/001_kmx.sql"] == "executable"
    assert states["migrations/002_evidence.sql"] == "pending"
    assert states["migrations/003_rules.sql"] == "pending"
    assert contains_sql(SQL)
