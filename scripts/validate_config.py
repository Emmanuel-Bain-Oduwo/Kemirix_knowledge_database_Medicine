"""Offline validation of foundation contracts; no runtime or clinical implementation."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate YAML keys instead of silently discarding configuration."""


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError("duplicate YAML key")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor("tag:yaml.org,2002:map", unique_mapping)


def read_yaml(path):
    return yaml.load(path.read_text(), Loader=UniqueLoader)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(root=ROOT):
    # Parse all configuration/operational YAML, including documents without a domain schema.
    for folder in ("config", "ops"):
        for path in sorted((root / folder).rglob("*.yaml")):
            require(isinstance(read_yaml(path), dict), f"{path.name}: expected a mapping")

    from agents.models import Task

    for path in sorted((root / "ops/tasks").glob("*.yaml")):
        if path.name != "TEMPLATE.yaml":
            task = Task.model_validate(read_yaml(path))
            require(path.stem == task.task_id, "task filename mismatch")

    categories = read_yaml(root / "config/categories.yaml")["categories"]
    require(isinstance(categories, list), "categories must be a list")
    require(len(categories) == len(set(categories)) == 24, "expected 24 unique categories")
    require("follow_up" not in categories, "follow_up is content, not a category")
    jurisdictions = read_yaml(root / "config/jurisdictions.yaml")["jurisdictions"]
    schema = read_yaml(root / "config/source_schema.yaml")
    database = read_yaml(root / "config/database.yaml")["database"]
    require(database["name"] == "kemirix_knowledge", "database name is frozen")
    require(database["provider"] == "ovh_managed_postgresql", "database authority is frozen")
    require(database["ssl_required"] is True, "managed PostgreSQL requires TLS")
    require(set(database["schemas"]) == {"kmx", "evidence", "rules"}, "schemas are frozen")
    storage = read_yaml(root / "config/object_storage.yaml")["object_storage"]
    require(storage["provider"] == "ovh_s3_compatible", "raw authority is OVH Object Storage")
    require(storage["purpose"] == "raw_source_vault", "storage purpose is frozen")
    require(storage["manifest"] == "manifest.json", "raw snapshots require manifests")
    require(
        set(storage["never_store_as_authority"])
        == {"kmx_normalized_truth", "clinical_evidence", "clinical_rules"},
        "normalized authority must remain PostgreSQL",
    )

    paths = sorted((root / "config/sources").glob("*.yaml"))
    require(len(paths) == 27, "expected 27 source contracts")
    sources = {}
    slugs = set()
    for path in paths:
        source = read_yaml(path)
        require(set(source) == set(schema["source_config_fields"]), f"{path.name}: fields")
        lane = source["lane"]
        require(type(lane) is int and 1 <= lane <= 27, f"{path.name}: invalid lane")
        require(lane not in sources, f"{path.name}: duplicate lane")
        for field in (
            "source_id",
            "name",
            "acquisition",
            "format",
            "object_storage_prefix",
            "rate_limit",
        ):
            require(
                isinstance(source[field], str) and bool(source[field].strip()),
                f"{path.name}: invalid {field}",
            )
        require(source["source_id"] not in slugs, f"{path.name}: duplicate source_id")
        require(source["jurisdiction"] in jurisdictions, f"{path.name}: jurisdiction")
        require(source["role"] in schema["roles"], f"{path.name}: role")
        for field in ("kmx_levels", "identifiers", "categories"):
            values = source[field]
            require(
                isinstance(values, list) and all(isinstance(v, str) for v in values),
                f"{path.name}: invalid {field}",
            )
            require(len(values) == len(set(values)), f"{path.name}: duplicate {field}")
        require(bool(source["identifiers"]), f"{path.name}: identifiers required")
        require(
            bool(source["kmx_levels"])
            and set(source["kmx_levels"]) <= {"ingredient", "clinical_drug", "product"},
            f"{path.name}: KMX levels",
        )
        require(set(source["categories"]) <= set(categories), f"{path.name}: unknown category")
        for field in ("evidence", "rules"):
            require(isinstance(source[field], (bool, str)), f"{path.name}: invalid {field}")
        if source["role"] != "primary_rule":
            require(
                source["rules"] is False or source["rules"] == "false_initially",
                f"{path.name}: non-primary source cannot independently create Rules",
            )
        sources[lane] = (source, path.relative_to(root).as_posix())
        slugs.add(source["source_id"])

    status = read_yaml(root / "ops/memory/SOURCE_STATUS.yaml")["sources"]
    require(set(status) == {f"S{i:02d}" for i in range(1, 28)}, "expected S01 through S27")
    for lane, (source, path) in sources.items():
        entry = status[f"S{lane:02d}"]
        require(
            entry["source_id"] == source["source_id"] and entry["config"] == path,
            f"S{lane:02d}: source status mapping mismatch",
        )
        require(entry["status"] == "not_started", "Phase 0 sources must remain not_started")


if __name__ == "__main__":
    try:
        validate()
    except (ValueError, KeyError, TypeError, yaml.YAMLError):
        # Do not echo arbitrary configuration values into logs.
        raise SystemExit("Configuration validation failed; inspect contracts locally.") from None
    print("Foundation configuration valid: 27 lanes; no external services accessed.")
