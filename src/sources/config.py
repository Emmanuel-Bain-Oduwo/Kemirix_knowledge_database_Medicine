"""The common source configuration interface.

All 27 source configs load through one fail-closed interface. lane (integer
1-27 in files) and source_id (stable slug) are deliberately distinct
identifier kinds; S01-S27 lane IDs are never valid slugs.
"""

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from kmx.exceptions import ConfigurationError

from .exceptions import SourceContractError

LANE_MIN, LANE_MAX = 1, 27
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

SOURCE_CONFIG_FIELDS = (
    "lane",
    "source_id",
    "name",
    "acquisition",
    "format",
    "jurisdiction",
    "role",
    "kmx_levels",
    "identifiers",
    "evidence",
    "rules",
    "categories",
    "object_storage_prefix",
    "rate_limit",
)
SOURCE_ROLES = (
    "primary_rule",
    "supporting",
    "identity_only",
    "catalogue_only",
    "duplicate_projection",
)


class SourceConfig(BaseModel):
    """One approved source lane (validated, frozen field set)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lane: int
    source_id: str
    name: str
    acquisition: str
    format: str
    jurisdiction: str
    role: str
    kmx_levels: list[str]
    identifiers: list[str]
    evidence: bool | str
    rules: bool | str
    categories: list[str]
    object_storage_prefix: str
    rate_limit: str

    @field_validator("lane")
    @classmethod
    def _lane(cls, value):
        if not isinstance(value, int) or not LANE_MIN <= value <= LANE_MAX:
            raise ConfigurationError(f"lane must be an integer 1-27, got {value!r}")
        return value

    @field_validator("source_id", "object_storage_prefix")
    @classmethod
    def _slug(cls, value, info):
        if not SLUG_PATTERN.fullmatch(value):
            raise ConfigurationError(f"{info.field_name} must be a slug: {value!r}")
        return value

    @field_validator("name", "acquisition", "format", "rate_limit")
    @classmethod
    def _nonempty(cls, value, info):
        if not value.strip():
            raise ConfigurationError(f"{info.field_name} must not be blank")
        return value

    @field_validator("role")
    @classmethod
    def _role(cls, value):
        if value not in SOURCE_ROLES:
            raise ConfigurationError(f"unknown source role: {value!r}")
        return value

    @field_validator("kmx_levels")
    @classmethod
    def _levels(cls, value):
        from kmx.models import KmxLevel

        if not value or any(level not in KmxLevel.ALL for level in value):
            raise ConfigurationError(f"unsupported KMX levels: {value!r}")
        if len(set(value)) != len(value):
            raise ConfigurationError("duplicate KMX levels")
        return value

    @field_validator("identifiers")
    @classmethod
    def _identifiers(cls, value):
        if not value or not all(isinstance(item, str) and item.strip() for item in value):
            raise ConfigurationError("identifiers must be a non-empty string list")
        if len(set(value)) != len(value):
            raise ConfigurationError("duplicate identifiers")
        return value

    @field_validator("categories")
    @classmethod
    def _categories(cls, value):
        # Identity/catalogue lanes legitimately carry no Evidence categories.
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise ConfigurationError("categories must be a string list")
        if len(set(value)) != len(value):
            raise ConfigurationError("duplicate categories")
        return value

    @model_validator(mode="after")
    def _categories_known(self):
        from evidence.categories import EvidenceCategory

        unknown = [c for c in self.categories if not EvidenceCategory.is_valid(c)]
        if unknown:
            raise ConfigurationError(f"unknown Evidence categories: {unknown}")
        if self.role != "primary_rule" and self.rules is True:
            raise SourceContractError(
                f"{self.source_id}: non-primary source cannot independently create Rules"
            )
        if self.role != "primary_rule" and self.rules not in (False, "false_initially"):
            # Non-primary lanes never carry independent rule authority; the
            # only approved non-primary conditional is false_initially (S19).
            # Exact per-lane policies are frozen in config/rule_contract.yaml.
            raise SourceContractError(
                f"{self.source_id}: unknown non-primary rule policy {self.rules!r}"
            )
        return self

    @property
    def lane_id(self):
        return f"S{self.lane:02d}"


def _read_yaml(path):
    class UniqueLoader(yaml.SafeLoader):
        pass

    def full_mapping(loader, node):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node)
            if key in result:
                raise ConfigurationError(f"duplicate YAML key in {path.name}")
            result[key] = loader.construct_object(value_node)
        return result

    UniqueLoader.add_constructor("tag:yaml.org,2002:map", full_mapping)
    return yaml.load(path.read_text(), Loader=UniqueLoader)


def load_source_configs(root, *, expected_lanes=range(1, 28)):
    """Load every source config through the one common fail-closed interface."""
    directory = Path(root) / "config/sources"
    from pathlib import Path as _Path

    from evidence.categories import load_categories
    from evidence.models import load_jurisdictions

    categories = load_categories(_Path(root))
    jurisdictions = load_jurisdictions(_Path(root))
    configs = []
    seen_lanes = {}
    seen_slugs = {}
    for path in sorted(directory.glob("*.yaml")):
        data = _read_yaml(path)
        if not isinstance(data, dict):
            raise ConfigurationError(f"{path.name}: expected a mapping")
        missing = [field for field in SOURCE_CONFIG_FIELDS if field not in data]
        extra = [field for field in data if field not in SOURCE_CONFIG_FIELDS]
        if missing or extra:
            raise SourceContractError(
                f"{path.name}: field mismatch (missing={missing}, extra={extra})"
            )
        if data["jurisdiction"] not in jurisdictions:
            raise ConfigurationError(f"{path.name}: unknown jurisdiction")
        if any(c not in categories for c in data["categories"]):
            raise ConfigurationError(f"{path.name}: unknown category")
        config = SourceConfig(**data)
        if config.lane in seen_lanes:
            raise SourceContractError(
                f"{path.name}: duplicate lane {config.lane} (already {seen_lanes[config.lane]})"
            )
        if config.source_id in seen_slugs:
            raise SourceContractError(
                f"{path.name}: duplicate source_id {config.source_id} "
                f"(already {seen_slugs[config.source_id]})"
            )
        seen_lanes[config.lane] = path.name
        seen_slugs[config.source_id] = path.name
        configs.append(config)
    expected = list(expected_lanes)
    if sorted(config.lane for config in configs) != expected:
        raise SourceContractError(
            f"expected exactly {len(expected)} source lanes, got {len(configs)}"
        )
    return configs
