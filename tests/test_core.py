"""CORE-001 domain foundation tests (Phase 2).

Prove: domain packages import, packaging includes them, all 27 configs load
through the common interface, enums match the frozen contracts, KMX IDs
validate, invalid configs fail closed and no external services are required.
"""

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[1]

DOMAIN_PACKAGES = ("kmx", "evidence", "rules", "storage", "database", "sources")


def test_every_domain_package_imports():
    for package in DOMAIN_PACKAGES + ("agents",):
        module = importlib.import_module(package)
        assert module is not None


def test_packaging_includes_domain_modules():
    import tomllib

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    packages = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    for expected in ["src/agents", *[f"src/{name}" for name in DOMAIN_PACKAGES]]:
        assert expected in packages, f"packaging must include {expected}"
    for name in DOMAIN_PACKAGES:
        assert (ROOT / f"src/{name}/__init__.py").is_file(), name


def test_all_27_source_configs_validate_through_common_interface():
    from sources.config import load_source_configs

    configs = load_source_configs(ROOT)
    assert len(configs) == 27
    assert sorted(c.lane for c in configs) == list(range(1, 28))
    assert len({c.source_id for c in configs}) == 27
    for config in configs:
        assert config.lane_id == f"S{config.lane:02d}"


def test_source_registry_foundation_exposes_lane_policies():
    from sources.registry import load_source_registry

    registry = load_source_registry(ROOT)
    assert len(registry) == 27
    dailymed = registry.by_source_id("dailymed")
    assert dailymed.lane_id == "S06"
    view = registry.describe(dailymed)
    assert view["source_role"] == "primary_rule"
    assert view["kmx_capability"] == ("ingredient", "clinical_drug", "product")
    assert view["rule_policy"] is True
    assert registry.by_lane_id("S27").source_id == "mhra"
    with pytest.raises(KeyError):
        registry.by_lane_id("S28")
    with pytest.raises(KeyError):
        registry.by_source_id("S06")


def test_shared_enums_match_frozen_contracts():
    from evidence.categories import CATEGORY_VALUES, load_categories
    from evidence.models import STATUS_VALUES
    from rules.models import OUTCOME_VALUES
    from storage.models import ACQUISITION_MODES, PARSE_STATUSES, RIGHTS_STATUSES

    assert len(CATEGORY_VALUES) == len(set(CATEGORY_VALUES)) == 24
    assert "follow_up" not in CATEGORY_VALUES
    assert load_categories(ROOT) == CATEGORY_VALUES
    assert STATUS_VALUES == ("draft", "approved", "stale", "retired")
    assert OUTCOME_VALUES == ("MATCH", "NO_MATCH", "CANNOT_FULLY_EVALUATE")
    assert ACQUISITION_MODES == ("api", "bulk", "db", "pdf", "web", "manual")
    assert RIGHTS_STATUSES == ("cleared", "pending_review", "restricted")
    assert PARSE_STATUSES == ("staged", "parsed", "quarantined")
    evidence = yaml.safe_load((ROOT / "config/evidence_contract.yaml").read_text())
    rule = yaml.safe_load((ROOT / "config/rule_contract.yaml").read_text())
    storage = yaml.safe_load((ROOT / "config/storage_contract.yaml").read_text())
    assert list(evidence["evidence_contract"]["statuses"]) == list(STATUS_VALUES)
    assert list(rule["rule_contract"]["outcomes"]) == list(OUTCOME_VALUES)
    assert list(storage["storage_contract"]["acquisition_modes"]) == list(ACQUISITION_MODES)
    assert list(storage["storage_contract"]["rights_statuses"]) == list(RIGHTS_STATUSES)
    assert list(storage["storage_contract"]["parse_statuses"]) == list(PARSE_STATUSES)


def test_kmx_ids_validate():
    from kmx.models import KmxId, KmxLevel, is_valid_kmx_id

    for valid in ("KMX-ING-000412", "KMX-CD-003871", "KMX-PROD-000001"):
        assert is_valid_kmx_id(valid)
        assert (
            KmxId(valid).level
            == {
                "KMX-ING-000412": KmxLevel.INGREDIENT,
                "KMX-CD-003871": KmxLevel.CLINICAL_DRUG,
                "KMX-PROD-000001": KmxLevel.PRODUCT,
            }[valid]
        )
    for invalid in (
        "KMX-PRES-000001",
        "kmx-ing-000412",
        "KMX-ING-12",
        "KMX-ING-0004127",
        "KMX-ING-00041a",
        "",
        None,
    ):
        assert not is_valid_kmx_id(invalid)
        with pytest.raises(Exception):
            KmxId(invalid)
    assert KmxId.build(KmxLevel.INGREDIENT, 412).value == "KMX-ING-000412"
    assert KmxLevel.ALL == ("ingredient", "clinical_drug", "product")


def test_no_unsupported_kmx_level_exists():
    from kmx.exceptions import KemirixError
    from kmx.models import KmxId

    with pytest.raises(KemirixError):
        KmxId.build("presentation", 1)
    with pytest.raises(KemirixError):
        KmxId("KMX-PRES-000001")


def _copy_config_tree(tmp_path):
    for folder in ("config",):
        subprocess.run(["cp", "-r", str(ROOT / folder), str(tmp_path / folder)], check=True)
    return tmp_path


def test_invalid_configs_fail_closed(tmp_path):
    from kmx.exceptions import ConfigurationError
    from sources.config import load_source_configs

    root = _copy_config_tree(tmp_path)
    bad = root / "config/sources/06_dailymed.yaml"
    data = yaml.safe_load(bad.read_text())
    data["source_id"] = "S06"  # lane ID used as slug
    bad.write_text(yaml.safe_dump(data))
    with pytest.raises(ConfigurationError):
        load_source_configs(root)


def test_missing_field_fails_closed(tmp_path):
    from sources.config import load_source_configs
    from sources.exceptions import SourceContractError

    root = _copy_config_tree(tmp_path)
    bad = root / "config/sources/06_dailymed.yaml"
    data = yaml.safe_load(bad.read_text())
    del data["rate_limit"]
    bad.write_text(yaml.safe_dump(data))
    with pytest.raises(SourceContractError):
        load_source_configs(root)


def test_duplicate_lane_fails_closed(tmp_path):
    from sources.exceptions import SourceContractError

    root = _copy_config_tree(tmp_path)
    target = root / "config/sources/07_openfda_label.yaml"
    data = yaml.safe_load(target.read_text())
    data["lane"] = 6  # duplicate of dailymed
    target.write_text(yaml.safe_dump(data))
    from sources.config import load_source_configs

    with pytest.raises(SourceContractError):
        load_source_configs(root)


def test_duplicate_source_id_fails_closed(tmp_path):
    from sources.config import load_source_configs
    from sources.exceptions import SourceContractError

    root = _copy_config_tree(tmp_path)
    target = root / "config/sources/07_openfda_label.yaml"
    data = yaml.safe_load(target.read_text())
    data["source_id"] = "dailymed"
    target.write_text(yaml.safe_dump(data))
    with pytest.raises(SourceContractError):
        load_source_configs(root)


def test_unknown_category_fails_closed(tmp_path):
    from kmx.exceptions import ConfigurationError
    from sources.config import load_source_configs

    root = _copy_config_tree(tmp_path)
    bad = root / "config/sources/06_dailymed.yaml"
    data = yaml.safe_load(bad.read_text())
    data["categories"] = ["follow_up"]
    bad.write_text(yaml.safe_dump(data))
    with pytest.raises(ConfigurationError):
        load_source_configs(root)


def test_database_contract_loads_exact_inventory():
    from database.config import load_database_contract

    contract = load_database_contract(ROOT)
    assert contract.database == "kemirix_knowledge"
    assert contract.provider == "ovh_managed_postgresql"
    assert contract.ssl_required is True
    assert len(contract.schemas["kmx"]) == 5
    assert len(contract.schemas["evidence"]) == 6
    assert len(contract.schemas["rules"]) == 3
    assert contract.table_count == 14


def test_manifest_round_trips_deterministically_and_rejects_secrets():
    from storage.manifest import Manifest

    payload = {
        "schema_version": 1,
        "lane_id": "S06",
        "source_id": "dailymed",
        "source_version": "v1",
        "source_record_key": "setid-123",
        "acquisition_mode": "api",
        "fetched_at": "2026-09-08T00:00:00Z",
        "upstream_published_at": None,
        "adapter_git_sha": "a" * 40,
        "rights_status": "cleared",
        "parse_status": "staged",
        "artifacts": [
            {
                "artifact_type": "structured_document",
                "original_filename": "spl.xml",
                "content_type": "application/xml",
                "byte_size": 3,
                "object_key": "dailymed/v1/setid-123/original/spl.xml",
                "sha256": "b" * 64,
            }
        ],
    }
    manifest = Manifest.model_validate(payload)
    again = Manifest.model_validate(json.loads(manifest.model_dump_json()))
    assert again == manifest

    for forbidden_key, forbidden_value in (
        ("presigned_url", "https://example.invalid/s"),
        ("api_key", "value"),
        ("password", "value"),
    ):
        with pytest.raises(Exception):
            Manifest.model_validate({**payload, forbidden_key: forbidden_value})
    with pytest.raises(Exception):
        Manifest.model_validate({**payload, "acquisition_mode": "carrier-pigeon"})
    with pytest.raises(Exception):
        Manifest.model_validate({**payload, "lane_id": "dailymed"})


def test_object_key_builder_and_validator():
    from storage.exceptions import StorageContractError
    from storage.keys import build_object_key, validate_object_key

    key = build_object_key("dailymed", "2026-09-08", "setid-123", "spl.xml")
    assert key == "dailymed/2026-09-08/setid-123/original/spl.xml"
    assert validate_object_key(key) == key
    bulk = build_object_key("rxnorm_athena", "2026-08", "__release__", "release.zip")
    assert bulk == "rxnorm_athena/2026-08/__release__/original/release.zip"
    with pytest.raises(StorageContractError):
        build_object_key("S06", "v", "k", "f.xml")  # lane ID as slug
    with pytest.raises(StorageContractError):
        build_object_key("dailymed", "v", "k", "../escape.xml")
    with pytest.raises(StorageContractError):
        validate_object_key("dailymed/v/k/NOT-original/spl.xml")


def test_manifest_artifact_lineage_is_bound_to_manifest_provenance():
    from storage.exceptions import StorageContractError
    from storage.manifest import Manifest

    base = {
        "schema_version": 1,
        "lane_id": "S06",
        "source_id": "dailymed",
        "source_version": "V1",
        "source_record_key": "SETID1",
        "acquisition_mode": "api",
        "fetched_at": "2026-09-08T00:00:00Z",
        "upstream_published_at": None,
        "adapter_git_sha": "a" * 40,
        "rights_status": "cleared",
        "parse_status": "staged",
        "artifacts": [
            {
                "artifact_type": "structured_document",
                "original_filename": "spl.xml",
                "content_type": "application/xml",
                "byte_size": 3,
                "object_key": "dailymed/V1/SETID1/original/spl.xml",
                "sha256": "b" * 64,
            }
        ],
    }

    def with_artifact(**overrides):
        return dict(base, artifacts=[dict(base["artifacts"][0], **overrides)])

    # The exact provenance-derived key passes.
    manifest = Manifest.model_validate(base)
    assert manifest.artifacts[0].object_key == "dailymed/V1/SETID1/original/spl.xml"

    # A harmless value containing the substring "secret" passes.
    secretin = with_artifact(
        original_filename="secretin.xml",
        object_key="dailymed/V1/SETID1/original/secretin.xml",
    )
    assert Manifest.model_validate(secretin).artifacts[0].original_filename == "secretin.xml"

    # Every provenance mismatch fails closed and is never silently rewritten.
    for key in (
        "ema/V1/SETID1/original/spl.xml",  # wrong source
        "dailymed/V2/SETID1/original/spl.xml",  # wrong source version
        "dailymed/V1/SETID2/original/spl.xml",  # wrong source record key
        "dailymed/V1/SETID1/original/other.xml",  # wrong original filename
    ):
        with pytest.raises(StorageContractError):
            Manifest.model_validate(with_artifact(object_key=key))

    # Credential field names still fail (unknown fields are forbidden).
    for field in ("secret", "api_key", "password", "presigned_url"):
        with pytest.raises(Exception):
            Manifest.model_validate({**base, field: "value"})


def test_non_primary_rule_policies_fail_closed(tmp_path):
    from sources.config import load_source_configs
    from sources.exceptions import SourceContractError

    def loaded_with(filename, rules):
        root = tmp_path / f"tree-{filename}-{rules}"
        root.mkdir()
        subprocess.run(["cp", "-r", str(ROOT / "config"), str(root / "config")], check=True)
        target = root / "config/sources" / filename
        data = yaml.safe_load(target.read_text())
        data["rules"] = rules
        target.write_text(yaml.safe_dump(data))
        return load_source_configs(root)

    # A supporting lane never carries an independent rule policy.
    for rejected in ("whatever", "disabled", True, "guideline_recommendations"):
        with pytest.raises(SourceContractError):
            loaded_with("18_onsides.yaml", rejected)
    # The one approved non-primary conditional (S19 false_initially) loads.
    configs = loaded_with("19_civic.yaml", "false_initially")
    assert [c.source_id for c in configs if c.lane == 19] == ["civic"]


def test_domain_packages_require_no_external_services():
    before = set(sys.modules)
    for package in DOMAIN_PACKAGES:
        importlib.import_module(package)
    loaded = set(sys.modules) - before
    for forbidden in ("boto3", "psycopg", "psycopg2", "requests", "httpx", "lxml", "fitz"):
        assert not any(name == forbidden or name.startswith(forbidden + ".") for name in loaded), (
            f"{forbidden} must not be imported by the domain foundation"
        )
