"""Phase 1 domain contract validation (DOMAIN-CONTRACT-001).

Proves the frozen contracts for all 27 approved source lanes against the
owner-approved blueprints of 2026-09-08 (SKILL v5.0, execution book).
"""

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return yaml.safe_load((ROOT / path).read_text())


def source_configs():
    return {
        path.stem: read(f"config/sources/{path.name}")
        for path in sorted((ROOT / "config/sources").glob("*.yaml"))
    }


# The owner-approved implementation registry (SKILL v5.0 section 7B.1):
# lane -> stable source slug.
APPROVED_REGISTRY = {
    1: "rxnorm_athena",
    2: "athena_extension",
    3: "gsrs_unii",
    4: "chebi_unichem",
    5: "medrt",
    6: "dailymed",
    7: "openfda_label",
    8: "ppb_register",
    9: "ppb_smpc",
    10: "keml",
    11: "knmf",
    12: "kenya_moh",
    13: "who",
    14: "kdigo",
    15: "cpic_clinpgx",
    16: "inxight",
    17: "drugcentral",
    18: "onsides",
    19: "civic",
    20: "chembl",
    21: "gtopdb",
    22: "dgidb",
    23: "open_targets",
    24: "drugmechdb",
    25: "ciel_ocl",
    26: "ema",
    27: "mhra",
}

# Owner-approved authority matrix (SKILL v5.0 section 7).
APPROVED_AUTHORITY = {
    1: {"kmx_levels": {"ingredient", "clinical_drug"}, "rules": False},
    2: {"kmx_levels": {"ingredient", "clinical_drug"}, "rules": False},
    3: {"kmx_levels": {"ingredient"}, "rules": False},
    4: {"kmx_levels": {"ingredient"}, "rules": False},
    5: {"kmx_levels": {"ingredient", "clinical_drug"}, "rules": False},
    6: {"kmx_levels": {"ingredient", "clinical_drug", "product"}, "rules": True},
    7: {"kmx_levels": {"ingredient", "clinical_drug", "product"}, "rules": False},
    8: {"kmx_levels": {"ingredient", "clinical_drug", "product"}, "rules": False},
    9: {"kmx_levels": {"ingredient", "clinical_drug", "product"}, "rules": True},
    10: {"kmx_levels": {"ingredient", "clinical_drug"}, "rules": False},
    11: {"kmx_levels": {"ingredient", "clinical_drug"}, "rules": "gated"},
    12: {"kmx_levels": {"ingredient", "clinical_drug"}, "rules": True},
    13: {"kmx_levels": {"ingredient", "clinical_drug"}, "rules": "guidance_only"},
    14: {"kmx_levels": {"ingredient", "clinical_drug"}, "rules": "computable_only"},
    15: {"kmx_levels": {"ingredient"}, "rules": True},
    16: {"kmx_levels": {"ingredient"}, "rules": False},
    17: {"kmx_levels": {"ingredient"}, "rules": False},
    18: {"kmx_levels": {"ingredient", "clinical_drug"}, "rules": False},
    19: {"kmx_levels": {"ingredient"}, "rules": "not_general_v1"},
    20: {"kmx_levels": {"ingredient"}, "rules": False},
    21: {"kmx_levels": {"ingredient"}, "rules": False},
    22: {"kmx_levels": {"ingredient"}, "rules": False},
    23: {"kmx_levels": {"ingredient"}, "rules": False},
    24: {"kmx_levels": {"ingredient"}, "rules": False},
    25: {"kmx_levels": {"ingredient", "clinical_drug"}, "rules": False},
    26: {"kmx_levels": {"ingredient", "clinical_drug", "product"}, "rules": True},
    27: {"kmx_levels": {"ingredient", "clinical_drug", "product"}, "rules": True},
}

APPROVED_CATEGORIES = [
    "indication",
    "contraindication",
    "drug_disease",
    "drug_drug",
    "drug_food_substance",
    "allergy_hypersensitivity",
    "dosing",
    "renal",
    "hepatic",
    "paediatric",
    "geriatric",
    "pregnancy",
    "lactation",
    "laboratory",
    "vital_signs",
    "monitoring",
    "adverse_effects",
    "duplication",
    "polypharmacy",
    "administration",
    "high_alert_safety",
    "pharmacogenomic",
    "treatment_appropriateness",
    "counselling",
]


def test_all_27_lanes_exist_with_unique_ids():
    sources = source_configs()
    assert len(sources) == 27
    lanes = [config["lane"] for config in sources.values()]
    slugs = [config["source_id"] for config in sources.values()]
    assert sorted(lanes) == list(range(1, 28)), "all 27 lanes must exist exactly once"
    assert len(set(slugs)) == 27, "source IDs must be unique"


def test_lane_and_source_id_semantics_are_distinct():
    for config in source_configs().values():
        lane = config["lane"]
        slug = config["source_id"]
        assert isinstance(lane, int) and 1 <= lane <= 27
        assert re.fullmatch(r"[a-z][a-z0-9_]*", slug), slug
        assert not re.fullmatch(r"S\d{2}", slug), "lane IDs must never be source slugs"
        assert f"S{lane:02d}" != slug


def test_source_configs_match_owner_approved_registry():
    for name, config in source_configs().items():
        lane = config["lane"]
        assert lane in APPROVED_REGISTRY, f"{name}: unknown lane"
        assert config["source_id"] == APPROVED_REGISTRY[lane], (
            f"{name}: source_id {config['source_id']} does not match the approved "
            f"slug {APPROVED_REGISTRY[lane]} for lane S{lane:02d}"
        )


def test_source_authority_matrix_matches_owner_approved_blueprint():
    for name, config in source_configs().items():
        expected = APPROVED_AUTHORITY[config["lane"]]
        assert set(config["kmx_levels"]) == expected["kmx_levels"], f"{name}: kmx_levels"
        rules = config["rules"]
        if expected["rules"] is True:
            assert rules is True or isinstance(rules, str), f"{name}: rules must be allowed"
        elif expected["rules"] is False:
            assert rules is False or rules == "false_initially", f"{name}: rules must be denied"
        else:
            assert isinstance(rules, str) and rules, f"{name}: conditional rule policy required"


def test_only_ing_cd_prod_exist():
    allowed = {"ingredient", "clinical_drug", "product"}
    for name, config in source_configs().items():
        assert set(config["kmx_levels"]) <= allowed, f"{name}: forbidden KMX level"
    for path in list((ROOT / "config").rglob("*.yaml")) + [ROOT / "migrations/001_kmx.sql"]:
        text = path.read_text()
        assert "KMX-PRES" not in text, f"{path.name}: KMX-PRES is forbidden"
    # SKILL.md mentions KMX-PRES only in order to forbid it.
    assert "Do not add KMX-PRES" in (ROOT / "SKILL.md").read_text()


def test_exactly_24_categories_with_follow_up_excluded():
    categories = read("config/categories.yaml")["categories"]
    assert categories == APPROVED_CATEGORIES
    assert len(categories) == len(set(categories)) == 24
    assert "follow_up" not in categories


def test_database_inventory_is_exactly_5_6_3():
    schemas = read("config/database.yaml")["database"]["schemas"]
    assert schemas["kmx"] == [
        "registry",
        "contains",
        "external_identifier",
        "name_index",
        "mapping_exception",
    ]
    assert schemas["evidence"] == [
        "source",
        "source_version",
        "source_block",
        "block_subject",
        "clinical_evidence",
        "evidence_support",
    ]
    assert schemas["rules"] == ["clinical_rule", "rule_evidence", "rule_test"]
    assert set(schemas) == {"kmx", "evidence", "rules"}


def test_join_level_and_truth_level_remain_distinct():
    contract = read("config/evidence_contract.yaml")["evidence_contract"]
    join = contract["join_level"]
    truth = contract["truth_level"]
    assert join["values"] == truth["values"] == ["ingredient", "clinical_drug", "product"]
    assert join["meaning"] != truth["meaning"]
    assert any("separately" in rule for rule in contract["join_truth_rules"])


def _validate_manifest(manifest, contract):
    spec = contract["manifest"]
    for field in spec["required_fields"]:
        assert field in manifest, f"manifest missing {field}"
    for artifact in manifest["artifacts"]:
        for field in spec["artifact_required_fields"]:
            assert field in artifact, f"artifact missing {field}"
        assert re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"])
        assert isinstance(artifact["byte_size"], int) and artifact["byte_size"] >= 0
    forbidden = [f for f in spec["forbidden_manifest_fields"] if f in str(manifest)]
    assert not forbidden, f"manifest contains forbidden fields: {forbidden}"
    assert manifest["acquisition_mode"] in contract["acquisition_modes"]
    assert manifest["rights_status"] in contract["rights_statuses"]
    assert manifest["parse_status"] in contract["parse_statuses"]
    assert re.fullmatch(r"S(0[1-9]|1[0-9]|2[0-7])", manifest["lane_id"])
    assert re.fullmatch(r"[a-z][a-z0-9_]*", manifest["source_id"])
    assert manifest["schema_version"] == spec["schema_version"]


def test_storage_manifest_validates_against_frozen_contract():
    contract = read("config/storage_contract.yaml")["storage_contract"]
    sample = {
        "schema_version": 1,
        "lane_id": "S06",
        "source_id": "dailymed",
        "source_version": "2026-09-08-spl-version",
        "source_record_key": "73833f2e-38b2-4cd0-a5c3-9d6c74c55f3e",
        "acquisition_mode": "api",
        "fetched_at": "2026-09-08T00:00:00Z",
        "upstream_published_at": "2026-08-01T00:00:00Z",
        "adapter_git_sha": "a" * 40,
        "rights_status": "cleared",
        "parse_status": "staged",
        "artifacts": [
            {
                "artifact_type": "structured_document",
                "original_filename": "spl.xml",
                "content_type": "application/xml",
                "byte_size": 123456,
                "object_key": (
                    "dailymed/2026-09-08-spl-version/"
                    "73833f2e-38b2-4cd0-a5c3-9d6c74c55f3e/original/spl.xml"
                ),
                "sha256": "b" * 64,
            }
        ],
    }
    _validate_manifest(sample, contract)
    broken = dict(sample, acquisition_mode="carrier-pigeon")
    with pytest.raises(AssertionError):
        _validate_manifest(broken, contract)
    leaking = dict(sample, presigned_url="https://example.invalid/signature")
    with pytest.raises(AssertionError):
        _validate_manifest(leaking, contract)


def test_object_key_contract_validates():
    storage = read("config/object_storage.yaml")["object_storage"]
    contract = read("config/storage_contract.yaml")["storage_contract"]
    assert storage["layout"] == "<source_id>/<source_version>/<source_record_key>/original/"
    pattern = contract["object_key_pattern"]
    expected = r"^<source_id>/<source_version>/<source_record_key>/original/<original_filename>$"
    assert pattern == expected
    valid_keys = [
        "dailymed/2026-09-08/73833f2e-38b2-4cd0-a5c3-9d6c74c55f3e/original/spl.xml",
        "rxnorm_athena/2026-08-01/__release__/original/rxnorm-full-release.zip",
        "kdigo/2024/CKD_GUIDELINE/original/guideline.pdf",
        "gsrs_unii/2026-07/substance-data/original/substance-data.zip",
    ]
    regex = pattern.replace("<source_id>", r"(?P<source>[a-z][a-z0-9_]*)")
    regex = regex.replace("<source_version>", r"[^/]+")
    regex = regex.replace("<source_record_key>", r"[^/]+")
    regex = regex.replace("<original_filename>", r"[^/]+")
    for key in valid_keys:
        match = re.fullmatch(regex, key)
        assert match, key
        assert not re.match(r"S\d{2}/", key), "lane IDs never appear in object keys"
        parts = key.split("/")
        assert len(parts) == 5 and parts[3] == "original"


def test_kmx_migration_has_no_evidence_dependency():
    sql = (ROOT / "migrations/001_kmx.sql").read_text()
    for forbidden in ("evidence.", "rules.", "CREATE SCHEMA evidence", "REFERENCES evidence"):
        assert forbidden not in sql


def test_controlled_statuses_validate():
    evidence = read("config/evidence_contract.yaml")["evidence_contract"]
    rules = read("config/rule_contract.yaml")["rule_contract"]
    storage = read("config/storage_contract.yaml")["storage_contract"]
    assert evidence["statuses"] == ["draft", "approved", "stale", "retired"]
    assert rules["outcomes"] == ["MATCH", "NO_MATCH", "CANNOT_FULLY_EVALUATE"]
    assert storage["rights_statuses"] == ["cleared", "pending_review", "restricted"]
    assert storage["parse_statuses"] == ["staged", "parsed", "quarantined"]
    assert storage["acquisition_modes"] == ["api", "bulk", "db", "pdf", "web", "manual"]


def test_source_authority_invariants_validate():
    rules = read("config/rule_contract.yaml")["rule_contract"]
    invariants = rules["authority_invariants"]
    for needle in (
        "S07",
        "S11 knmf",
        "S16 inxight excludes",
        "S20 chembl",
        "S16-S24",
        "S26 ema and S27 mhra",
        "duplicate projections",
    ):
        assert any(needle in i for i in invariants), f"missing authority invariant: {needle}"
    eligibility = rules["eligibility"]
    assert any("primary regulatory/guideline" in e for e in eligibility)
    assert any("never independently create Rules" in e for e in eligibility)


def test_forbidden_architecture_additions_are_absent():
    banned = [
        "KMX-PRES",
        "graph database",
        "graph_db",
        "LangChain",
        "Airflow",
        "Kubernetes",
        "kubernetes",
    ]
    for path in sorted((ROOT / "config").rglob("*.yaml")):
        text = path.read_text()
        for needle in banned:
            assert needle not in text, f"{path.name}: forbidden architecture addition {needle}"
    sources = source_configs()
    assert len(sources) == 27, "a 28th source is forbidden"
    all_text = "\n".join(p.read_text() for p in (ROOT / "config").rglob("*.yaml"))
    assert "696" not in all_text, "catalogue size is data-driven; never hardcode old counts"


def test_manifest_last_and_immutable_upload_semantics_frozen():
    contract = read("config/storage_contract.yaml")["storage_contract"]
    semantics = contract["upload_semantics"]
    assert any("manifest is uploaded last" in rule for rule in semantics)
    assert any("idempotent success" in rule for rule in semantics)
    assert any("rejected" in rule and "quarantined" in rule for rule in semantics)
    assert any("original bytes are preserved" in rule.lower() for rule in semantics)
    assert contract["manifest_filename"] == "manifest.json"
