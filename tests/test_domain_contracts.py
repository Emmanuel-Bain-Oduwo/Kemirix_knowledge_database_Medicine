"""Phase 1 domain contract validation (DOMAIN-CONTRACT-001 + PHASE1-2-CONTRACT-HARDENING-001).

Proves the frozen contracts for all 27 approved source lanes against the
owner-approved blueprints of 2026-09-08 (SKILL v5.0, execution book), plus the
hardened exact-per-lane Rule authority policies, the full structural Rule
contract, manifest forbidden-field key inspection, Object Storage docs
consistency and the six-table non-executable Evidence placeholder.
"""

import re
import subprocess
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

# Owner-approved authority matrix (SKILL v5.0 section 7). KMX capability is
# checked here; the per-lane Rule policy lives in exactly one canonical
# frozen representation, rule_contract.yaml source_rule_policies.
APPROVED_AUTHORITY = {
    1: {"ingredient", "clinical_drug"},
    2: {"ingredient", "clinical_drug"},
    3: {"ingredient"},
    4: {"ingredient"},
    5: {"ingredient", "clinical_drug"},
    6: {"ingredient", "clinical_drug", "product"},
    7: {"ingredient", "clinical_drug", "product"},
    8: {"ingredient", "clinical_drug", "product"},
    9: {"ingredient", "clinical_drug", "product"},
    10: {"ingredient", "clinical_drug"},
    11: {"ingredient", "clinical_drug"},
    12: {"ingredient", "clinical_drug"},
    13: {"ingredient", "clinical_drug"},
    14: {"ingredient", "clinical_drug"},
    15: {"ingredient"},
    16: {"ingredient"},
    17: {"ingredient"},
    18: {"ingredient", "clinical_drug"},
    19: {"ingredient"},
    20: {"ingredient"},
    21: {"ingredient"},
    22: {"ingredient"},
    23: {"ingredient"},
    24: {"ingredient"},
    25: {"ingredient", "clinical_drug"},
    26: {"ingredient", "clinical_drug", "product"},
    27: {"ingredient", "clinical_drug", "product"},
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
        lane = config["lane"]
        expected = APPROVED_AUTHORITY[lane]
        assert set(config["kmx_levels"]) == expected, f"{name}: kmx_levels"


def canonical_rule_policies(root=ROOT):
    """The one canonical frozen per-lane Rule policy map (rule_contract.yaml)."""
    return yaml.safe_load((root / "config/rule_contract.yaml").read_text())["rule_contract"][
        "source_rule_policies"
    ]


def _assert_exact_rule_policies(root):
    """Every S01-S27 config must carry its exact frozen approved Rule policy.

    Exact equality including type: bool lanes accept only true/false and
    conditional lanes only the one approved conditional string. Any other
    value (for example "disabled", "false_initially" on a true lane, or an
    arbitrary string) is authority drift and fails.
    """
    policies = canonical_rule_policies(root)
    assert sorted(policies) == [f"S{lane:02d}" for lane in range(1, 28)], (
        "exactly 27 frozen rule policies S01-S27 are required"
    )
    for path in sorted((root / "config/sources").glob("*.yaml")):
        config = yaml.safe_load(path.read_text())
        expected = policies[f"S{config['lane']:02d}"]
        actual = config["rules"]
        assert type(actual) is type(expected) and actual == expected, (
            f"{path.name}: rule policy {actual!r} does not match the frozen "
            f"approved policy {expected!r} for lane S{config['lane']:02d}"
        )


def test_source_rule_policies_match_frozen_canonical_map():
    _assert_exact_rule_policies(ROOT)


def test_frozen_policy_map_encodes_owner_approved_policies():
    policies = canonical_rule_policies()
    assert policies["S06"] is True
    assert policies["S09"] is True
    assert policies["S12"] is True
    assert policies["S26"] is True
    assert policies["S27"] is True
    assert policies["S11"] == "executable_recommendations_only"
    assert policies["S13"] == "actionable guidance only"
    assert policies["S14"] == "explicit_computable_recommendations_only"
    assert policies["S15"] == "guideline_recommendations"
    assert policies["S19"] == "false_initially"
    assert policies["S07"] is False  # duplicate projection, never an independent vote
    assert sum(value is False for value in policies.values()) == 17


def _copy_config_tree(tmp_path):
    subprocess.run(["cp", "-r", str(ROOT / "config"), str(tmp_path / "config")], check=True)
    return tmp_path


def _mutate_source(tmp_path, filename, rules):
    target = tmp_path / "config/sources" / filename
    data = yaml.safe_load(target.read_text())
    data["rules"] = rules
    target.write_text(yaml.safe_dump(data))


def test_rule_authority_drift_fails_closed(tmp_path):
    root = _copy_config_tree(tmp_path)
    _assert_exact_rule_policies(root)  # the copied tree still matches exactly
    for drift in ("disabled", "false_initially", "whatever", False):
        _mutate_source(root, "06_dailymed.yaml", drift)
        with pytest.raises(AssertionError):
            _assert_exact_rule_policies(root)
    _mutate_source(root, "06_dailymed.yaml", True)
    _assert_exact_rule_policies(root)  # the exact approved policy passes again


def test_conditional_policy_drift_fails_closed(tmp_path):
    root = _copy_config_tree(tmp_path)
    # S11 is approved only as executable_recommendations_only.
    for drift in ("disabled", "guideline_recommendations", "whatever", True, False):
        _mutate_source(root, "11_knmf.yaml", drift)
        with pytest.raises(AssertionError):
            _assert_exact_rule_policies(root)


def test_canonical_map_drift_fails_closed(tmp_path):
    root = _copy_config_tree(tmp_path)
    contract = root / "config/rule_contract.yaml"
    data = yaml.safe_load(contract.read_text())
    data["rule_contract"]["source_rule_policies"]["S06"] = "disabled"
    contract.write_text(yaml.safe_dump(data))
    with pytest.raises(AssertionError):
        _assert_exact_rule_policies(root)


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


def _forbidden_field_locations(node, forbidden, prefix="manifest"):
    """Exact recursive key inspection; values are never substring-scanned.

    The contract forbids credential FIELD NAMES, so only mapping keys are
    compared exactly. Harmless substrings inside values (for example the
    legitimate filename secretin.xml) never trigger a false positive.
    """
    hits = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in forbidden:
                hits.append(f"{prefix}.{key}")
            hits.extend(_forbidden_field_locations(value, forbidden, f"{prefix}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            hits.extend(_forbidden_field_locations(value, forbidden, f"{prefix}[{index}]"))
    return hits


def _validate_manifest(manifest, contract):
    spec = contract["manifest"]
    for field in spec["required_fields"]:
        assert field in manifest, f"manifest missing {field}"
    for artifact in manifest["artifacts"]:
        for field in spec["artifact_required_fields"]:
            assert field in artifact, f"artifact missing {field}"
        assert re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"])
        assert isinstance(artifact["byte_size"], int) and artifact["byte_size"] >= 0
    forbidden = _forbidden_field_locations(manifest, set(spec["forbidden_manifest_fields"]))
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


def test_manifest_forbidden_field_check_inspects_keys_not_values():
    contract = read("config/storage_contract.yaml")["storage_contract"]
    sample = {
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
                "byte_size": 123456,
                "object_key": "dailymed/v1/setid-123/original/spl.xml",
                "sha256": "b" * 64,
            }
        ],
    }
    # A legitimate value containing the substring "secret" must pass: the
    # contract forbids credential field names, not harmless value substrings.
    artifact = dict(sample["artifacts"][0], original_filename="secretin.xml")
    artifact["object_key"] = "dailymed/v1/setid-123/original/secretin.xml"
    _validate_manifest(dict(sample, artifacts=[artifact]), contract)

    # Forbidden credential FIELD NAMES fail at every depth, exactly.
    for field in ("api_key", "password", "secret", "credential", "presigned_url"):
        with pytest.raises(AssertionError):
            _validate_manifest(dict(sample, **{field: "value"}), contract)
    with pytest.raises(AssertionError):
        artifact = dict(sample["artifacts"][0], bearer_token="token")
        _validate_manifest(dict(sample, artifacts=[artifact]), contract)


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


FROZEN_CLINICAL_RULE_FIELDS = [
    "rule_id",
    "target_kmx_id",
    "target_level",
    "category",
    "jurisdiction",
    "patient_trigger",
    "required_patient_data",
    "verdict",
    "verdict_reason",
    "severity",
    "severity_reason",
    "immediate_action",
    "action_reason",
    "recommendation",
    "recommendation_reason",
    "alternatives",
    "risk_factors",
    "monitoring",
    "follow_up",
    "status",
    "created_at",
    "updated_at",
    "reviewed_at",
    "reviewed_by",
]


def test_clinical_rule_structural_contract_frozen():
    rules = read("config/rule_contract.yaml")["rule_contract"]
    clinical = rules["clinical_rule"]
    assert clinical["required_fields"] == FROZEN_CLINICAL_RULE_FIELDS
    # The 17-part approved logical Rule is completely covered: target medicine,
    # category, patient trigger, required patient data, verdict + reason,
    # severity + reason, immediate action + reason, recommendation + reason,
    # alternatives, risk factors, monitoring, follow-up, connected Evidence.
    joined = " ".join(clinical["required_fields"])
    for part in (
        "patient_trigger",
        "required_patient_data",
        "verdict verdict_reason",
        "severity severity_reason",
        "immediate_action action_reason",
        "recommendation recommendation_reason",
        "alternatives",
        "risk_factors",
        "monitoring",
        "follow_up",
    ):
        assert part in joined, f"17-part logical Rule missing {part}"
    # Connected Evidence is bound through rule_evidence, not remapped here.
    semantics = clinical["field_semantics"]
    for field in ("patient_trigger", "required_patient_data", "status", "reviewed_by"):
        assert field in semantics


def test_rule_evidence_structural_contract_frozen():
    rules = read("config/rule_contract.yaml")["rule_contract"]
    rule_evidence = rules["rule_evidence"]
    assert rule_evidence["required_fields"] == [
        "rule_id",
        "evidence_id",
        "support_role",
        "supports_fields",
        "ordinal",
    ]
    joined = " ".join(rule_evidence["rules"])
    assert "primary regulatory Evidence controls executable clinical action" in joined
    assert (
        "supporting Evidence may support explanation but cannot "
        "independently change the action" in joined
    ), "supporting Evidence must never independently change clinical action"


def test_rule_test_structural_contract_frozen():
    rules = read("config/rule_contract.yaml")["rule_contract"]
    rule_test = rules["rule_test"]
    assert rule_test["required_fields"] == [
        "test_id",
        "rule_id",
        "test_name",
        "patient_fixture",
        "expected_outcome",
        "expected_decision_fields",
        "active",
    ]
    assert rule_test["field_semantics"]["expected_outcome"] == (
        "exactly one of MATCH, NO_MATCH, CANNOT_FULLY_EVALUATE"
    )


def test_rule_outcomes_and_semantics_frozen():
    rules = read("config/rule_contract.yaml")["rule_contract"]
    assert rules["outcomes"] == ["MATCH", "NO_MATCH", "CANNOT_FULLY_EVALUATE"]
    joined = " ".join(rules["outcome_rules"]).lower()
    assert "missing required patient data returns cannot_fully_evaluate" in joined
    assert "never no_match" in joined
    assert "wrong formulation or product returns no_match" in joined
    assert "all trigger conditions satisfied returns match" in joined


def test_rule_evidence_inheritance_and_no_remap_frozen():
    rules = read("config/rule_contract.yaml")["rule_contract"]
    inheritance = rules["inheritance"]
    assert inheritance["rule_target_kmx_id"] == "evidence_kmx_subject"
    assert inheritance["rule_target_level"] == "evidence_truth_level"
    assert inheritance["rule_category"] == "evidence_category"
    assert inheritance["rule_jurisdiction"] == "evidence_jurisdiction"
    joined = " ".join(inheritance["rules"])
    assert "inheritance is immutable" in joined
    assert "never resolves medicine identity again" in joined
    assert "supporting biomedical sources never independently change" in joined


def test_object_storage_docs_match_frozen_contract():
    docs = (ROOT / "docs/OBJECT_STORAGE.md").read_text()
    contract = read("config/storage_contract.yaml")["storage_contract"]
    # Frozen five-segment layout documented exactly as the machine contract.
    assert "<source_id>/<source_version>/<source_record_key>/original/<original_filename>" in docs
    # Bulk releases use the literal record key __release__.
    for bulk in (
        "chembl/<release>/__release__/original/chembl_postgresql.tar.gz",
        "drugcentral/<release>/__release__/original/drugcentral.dump",
        "onsides/<release>/__release__/original/onsides.sqlite",
        "open_targets/<release>/__release__/original/<partition>.parquet",
    ):
        assert bulk in docs, f"missing __release__ bulk example: {bulk}"
    # Stale pre-hardening bulk keys (missing the record-key segment) are gone.
    assert "chembl/<release>/original/chembl_postgresql.tar.gz" not in docs
    assert "open_targets/<release>/original/*.parquet" not in docs
    # lane_id stays outside the object key; source_id stays inside it.
    assert "lane_id" in docs and "manifest only" in docs
    assert "never in the object key" in docs
    assert "source_id -> object key + manifest" in docs
    # The vault/authority boundary is documented.
    assert "Object Storage -> immutable raw source vault" in docs
    assert "PostgreSQL" in docs and "normalized KMX/Evidence/Rule authority" in docs
    # Every frozen manifest and artifact field is documented.
    spec = contract["manifest"]
    for field in spec["required_fields"] + spec["artifact_required_fields"]:
        assert f"`{field}`" in docs, f"docs must document manifest field {field}"


def test_evidence_placeholder_is_six_table_and_non_executable():
    sql = (ROOT / "migrations/002_evidence.sql").read_text()
    planned = [
        "evidence.source",
        "evidence.source_version",
        "evidence.source_block",
        "evidence.block_subject",
        "evidence.clinical_evidence",
        "evidence.evidence_support",
    ]
    for table in planned:
        assert table in sql, f"missing planned Evidence table {table}"
    lines = [line for line in sql.splitlines() if line.strip()]
    assert all(line.lstrip().startswith("--") for line in lines), (
        "002_evidence.sql must remain comment-only non-executable"
    )
    suite = read("config/migration_suite.yaml")["migrations"]
    entry = next(m for m in suite if m["path"] == "migrations/002_evidence.sql")
    assert entry["state"] == "pending", "002 must not be promoted before its design task"
