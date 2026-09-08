"""The frozen database contract: one database, three schemas, 5+6+3 tables.

Loading config/database.yaml fails closed unless the inventory matches the
owner-approved blueprint exactly.
"""

from pathlib import Path

import yaml

from .exceptions import DatabaseContractError

KMX_TABLES = (
    "registry",
    "contains",
    "external_identifier",
    "name_index",
    "mapping_exception",
)
EVIDENCE_TABLES = (
    "source",
    "source_version",
    "source_block",
    "block_subject",
    "clinical_evidence",
    "evidence_support",
)
RULES_TABLES = ("clinical_rule", "rule_evidence", "rule_test")


class DatabaseContract:
    """The frozen database inventory (value object)."""

    __slots__ = ("database", "provider", "ssl_required", "schemas")

    def __init__(self, *, database, provider, ssl_required, schemas):
        self.database = database
        self.provider = provider
        self.ssl_required = ssl_required
        self.schemas = schemas

    @property
    def table_count(self):
        return sum(len(tables) for tables in self.schemas.values())


def load_database_contract(root):
    """Load and validate config/database.yaml against the frozen inventory."""
    path = Path(root) / "config/database.yaml"
    data = yaml.safe_load(path.read_text()) or {}
    database = data.get("database") or {}
    expected = {
        "database": "kemirix_knowledge",
        "provider": "ovh_managed_postgresql",
        "ssl_required": True,
        "kmx": list(KMX_TABLES),
        "evidence": list(EVIDENCE_TABLES),
        "rules": list(RULES_TABLES),
    }
    schemas = database.get("schemas")
    if (
        database.get("name") != expected["database"]
        or database.get("provider") != expected["provider"]
        or database.get("ssl_required") is not expected["ssl_required"]
        or not isinstance(schemas, dict)
        or set(schemas) != {"kmx", "evidence", "rules"}
        or schemas.get("kmx") != expected["kmx"]
        or schemas.get("evidence") != expected["evidence"]
        or schemas.get("rules") != expected["rules"]
    ):
        raise DatabaseContractError("database.yaml does not match the frozen 5+6+3 inventory")
    return DatabaseContract(
        database=expected["database"],
        provider=expected["provider"],
        ssl_required=True,
        schemas={name: tuple(tables) for name, tables in schemas.items()},
    )
