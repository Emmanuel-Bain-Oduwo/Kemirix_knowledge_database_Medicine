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


def table_block(table):
    match = re.search(rf"CREATE TABLE {re.escape(table)} \((.*?)\n\);", SQL, re.DOTALL)
    assert match, f"missing CREATE TABLE {table}"
    return match.group(1)


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
    assert "PRIMARY KEY (kmx_id)" in SQL
    assert "level IN ('ingredient', 'clinical_drug', 'product')" in SQL
    assert "status IN ('active', 'retired')" in SQL
    assert "length(btrim(preferred_name)) > 0" in SQL
    registry = table_block("kmx.registry")
    # Approved registry contract: kmx_id alone is the identity; level is bound
    # by the prefix check, not by a composite unique key.
    assert "normalized_name" in registry
    assert "updated_at" in registry
    assert "UNIQUE" not in registry


def test_contains_uses_container_member_model():
    contains = table_block("kmx.contains")
    assert "container_kmx_id" in contains
    assert "member_kmx_id" in contains
    assert "relationship_type" in contains
    assert "ordinal           integer" in contains
    assert "PRIMARY KEY (container_kmx_id, member_kmx_id, relationship_type)" in contains
    assert "CHECK (container_kmx_id <> member_kmx_id)" in contains
    assert "FOREIGN KEY (container_kmx_id) REFERENCES kmx.registry (kmx_id)" in contains
    assert "FOREIGN KEY (member_kmx_id) REFERENCES kmx.registry (kmx_id)" in contains
    assert "CREATE INDEX contains_member_idx ON kmx.contains (member_kmx_id)" in SQL
    # Parent/child wording is retired: containers hold members, and legal
    # combinations are application-validated (owner-approved blueprint 6.2).
    for banned in ("parent_kmx_id", "child_kmx_id", "parent_level", "child_level"):
        assert banned not in SQL


def test_external_identifier_conflicts_remain_recordable():
    external = table_block("kmx.external_identifier")
    assert "UNIQUE (kmx_id, identifier_system, identifier_value)" in external
    # A source identifier pointing at two different KMX rows stays recordable
    # so the conflict is preserved as a mapping exception (fail closed),
    # never hidden by a global database-level unique binding.
    assert "UNIQUE (source_id" not in external
    assert re.search(r"UNIQUE \((?!kmx_id, identifier_system)", external) is None
    assert "jurisdiction" in external
    assert "active" in external
    assert "identifier_system" in external
    assert "identifier_value" in external
    pattern = re.search(r"source_id ~ '([^']+)'", external).group(1)
    assert pattern == "^[a-z][a-z0-9_]*$"
    for valid in ("dailymed", "rxnorm_athena", "ppb_smpc", "chembl"):
        assert re.fullmatch(pattern, valid)
    for invalid in ("S06", "DailyMed", "dailymed-", "6dailymed", "", "daily med"):
        assert not re.fullmatch(pattern, invalid)


def test_name_index_is_lookup_only():
    name_index = table_block("kmx.name_index")
    assert "name_index_id" in name_index
    assert "normalized_name" in name_index
    assert "language" in name_index
    assert "DEFAULT 'en'" in name_index
    assert "source_id" in name_index
    assert "PRIMARY KEY (name_index_id)" in name_index
    assert "FOREIGN KEY (kmx_id) REFERENCES kmx.registry (kmx_id)" in name_index
    assert "CREATE INDEX name_index_normalized_name_idx ON kmx.name_index (normalized_name)" in SQL
    # A pure lookup aid never mints identity: no uniqueness on names, so one
    # name may legitimately map to several KMX rows.
    assert "UNIQUE" not in name_index


def test_mapping_exception_preserves_full_provenance():
    exception = table_block("kmx.mapping_exception")
    for column in (
        "lane_id",
        "source_id",
        "source_version_key",
        "source_record_key",
        "reason_code",
        "normalized_input",
        "candidate_kmx_ids",
        "status",
        "reviewed_at",
        "reviewed_by",
    ):
        assert column in exception
    assert "DEFAULT '[]'::jsonb" in exception
    lane = re.search(r"lane_id ~ '([^']+)'", exception).group(1)
    assert lane == "^S(0[1-9]|1[0-9]|2[0-7])$"
    for valid in ("S01", "S06", "S15", "S27"):
        assert re.fullmatch(lane, valid)
    for invalid in ("S00", "S28", "S6", "S001", "s06", "", "dailymed"):
        assert not re.fullmatch(lane, invalid)
    assert "'NO_MATCH'" in exception
    assert "'MULTIPLE_MATCHES'" in exception
    assert "'IDENTIFIER_CONFLICT'" in exception
    assert "'FORMULATION_AMBIGUITY'" in exception
    assert "'PRODUCT_IDENTITY_UNPROVEN'" in exception
    assert "status IN ('open', 'resolved', 'dismissed')" in exception
    assert "status <> 'resolved'" in exception
    assert "reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL" in exception
    for retired in ("zero_match", "multiple_match", "resolution_kmx_id", "resolved_at"):
        assert retired not in exception


def test_migration_001_is_independent_of_evidence_tables():
    # Plain provenance columns only: no evidence/rules schema references and
    # no cross-schema foreign keys from migration 001 to future migrations.
    for forbidden in (
        "evidence.",
        "rules.",
        "CREATE SCHEMA evidence",
        "CREATE SCHEMA rules",
        "REFERENCES evidence",
        "REFERENCES rules",
    ):
        assert forbidden not in SQL


def test_migration_suite_declaration_matches_config():
    suite = yaml.safe_load((ROOT / "config/migration_suite.yaml").read_text())
    states = {item["path"]: item["state"] for item in suite["migrations"]}
    assert states["migrations/001_kmx.sql"] == "executable"
    assert states["migrations/002_evidence.sql"] == "pending"
    assert states["migrations/003_rules.sql"] == "pending"
    assert contains_sql(SQL)
