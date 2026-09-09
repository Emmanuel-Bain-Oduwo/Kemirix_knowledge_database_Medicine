"""KMX-002 deterministic resolver and repository tests (Phase 7).

Unit tests run against an in-memory fake repository. The CI-gated
integration test runs only on the isolated hosted CI PostgreSQL
(KEMIRIX_CI_POSTGRES=1 and GITHUB_ACTIONS=true) and never touches any
development or production database.
"""

import os
from pathlib import Path

import pytest

from kmx.models import KmxLevel
from kmx.normalizer import normalize_name
from kmx.repository import ExternalBinding, KmxRepository, NameCandidate
from kmx.resolver import (
    APPROVED_PRODUCT_CREATORS,
    MappingExceptionOutcome,
    ResolutionRequest,
    Resolved,
    resolve_identity,
)

pytestmark = pytest.mark.contract

CI_POSTGRES = (
    os.environ.get("KEMIRIX_CI_POSTGRES") == "1" and os.environ.get("GITHUB_ACTIONS") == "true"
)


class FakeRepository:
    """In-memory bindings and names for the resolver algorithm."""

    def __init__(self, bindings=(), names=()):
        self.bindings = {(system, value): rows for system, value, rows in bindings}
        self.names = {name: rows for name, rows in names}
        self.exceptions = []

    def external_bindings(self, system, value):
        return self.bindings.get((system, value), [])

    def name_candidates(self, normalized_name, *, level=None):
        rows = self.names.get(normalized_name, [])
        if level is not None:
            rows = [row for row in rows if row.level == level]
        return rows

    def record_mapping_exception(self, **kwargs):
        self.exceptions.append(kwargs)
        return len(self.exceptions)


def binding(kmx_id, level, source_id="rxnorm_athena"):
    return ExternalBinding(kmx_id, level, source_id)


def name_row(kmx_id, level, normalized_name):
    return NameCandidate(kmx_id, level, normalized_name)


def request(**overrides):
    base = dict(
        identifiers=[("RXNORM", "12345")],
        lane_id="S01",
        source_id="rxnorm_athena",
        source_record_key="RXCUI-12345",
    )
    base.update(overrides)
    return ResolutionRequest(**base)


def test_exact_rxcui_identifier_resolves():
    repo = FakeRepository(
        bindings=[("RXNORM", "12345", [binding("KMX-CD-000001", "clinical_drug")])]
    )
    outcome = resolve_identity(repo, request())
    assert isinstance(outcome, Resolved)
    assert outcome.kmx_id == "KMX-CD-000001"
    assert outcome.level == "clinical_drug"


def test_unii_fixture_resolves():
    repo = FakeRepository(
        bindings=[("UNII", "362O9ITL9D", [binding("KMX-ING-000042", "ingredient")])]
    )
    outcome = resolve_identity(
        repo,
        request(identifiers=[("UNII", "362O9ITL9D")], source_record_key="UNII-362O9ITL9D"),
    )
    assert isinstance(outcome, Resolved)
    assert outcome.kmx_id == "KMX-ING-000042"


def test_zero_match_fails_closed():
    repo = FakeRepository()
    outcome = resolve_identity(repo, request(identifiers=[("RXNORM", "99999")]))
    assert isinstance(outcome, MappingExceptionOutcome)
    assert outcome.reason_code == "NO_MATCH"
    assert outcome.candidate_kmx_ids == ()


def test_one_identifier_bound_to_several_kmx_is_multiple_matches():
    repo = FakeRepository(
        bindings=[
            (
                "RXNORM",
                "777",
                [
                    binding("KMX-ING-000001", "ingredient"),
                    binding("KMX-ING-000002", "ingredient"),
                ],
            )
        ]
    )
    outcome = resolve_identity(repo, request(identifiers=[("RXNORM", "777")]))
    assert outcome.reason_code == "MULTIPLE_MATCHES"
    assert outcome.candidate_kmx_ids == ("KMX-ING-000001", "KMX-ING-000002")


def test_identifiers_disagreeing_across_kmx_is_identifier_conflict():
    repo = FakeRepository(
        bindings=[
            ("RXNORM", "1", [binding("KMX-CD-000001", "clinical_drug")]),
            ("UNII", "A", [binding("KMX-ING-000003", "ingredient")]),
        ]
    )
    outcome = resolve_identity(repo, request(identifiers=[("RXNORM", "1"), ("UNII", "A")]))
    assert outcome.reason_code == "IDENTIFIER_CONFLICT"
    assert outcome.candidate_kmx_ids == ("KMX-CD-000001", "KMX-ING-000003")


def test_level_mismatch_on_exact_identifier_is_a_conflict():
    repo = FakeRepository(bindings=[("RXNORM", "5", [binding("KMX-CD-000009", "clinical_drug")])])
    outcome = resolve_identity(
        repo,
        request(
            identifiers=[("RXNORM", "5")],
            desired_level=KmxLevel.INGREDIENT,
        ),
    )
    assert outcome.reason_code == "IDENTIFIER_CONFLICT"


def test_name_fallback_requires_permission():
    repo = FakeRepository(
        names=[("amoxicillin", [name_row("KMX-ING-000001", "ingredient", "amoxicillin")])]
    )
    denied = resolve_identity(
        repo,
        request(
            identifiers=[("RXNORM", "404")],
            normalized_name="amoxicillin",
            name_fallback_permitted=False,
        ),
    )
    assert denied.reason_code == "NO_MATCH"
    allowed = resolve_identity(
        repo,
        request(
            identifiers=[("RXNORM", "404")],
            normalized_name="amoxicillin",
            name_fallback_permitted=True,
        ),
    )
    assert isinstance(allowed, Resolved)
    assert allowed.kmx_id == "KMX-ING-000001"


def test_ambiguous_strength_and_form_candidates_fail_to_formulation_ambiguity():
    repo = FakeRepository(
        names=[
            (
                "amoxicillin 500 mg capsule",
                [
                    name_row("KMX-CD-000001", "clinical_drug", "amoxicillin 500 mg capsule"),
                    name_row("KMX-CD-000002", "clinical_drug", "amoxicillin 500 mg capsule"),
                ],
            )
        ]
    )
    outcome = resolve_identity(
        repo,
        request(
            identifiers=[("RXNORM", "404")],
            normalized_name="amoxicillin 500 mg capsule",
            name_fallback_permitted=True,
            desired_level=KmxLevel.CLINICAL_DRUG,
        ),
    )
    assert outcome.reason_code == "FORMULATION_AMBIGUITY"
    assert outcome.candidate_kmx_ids == ("KMX-CD-000001", "KMX-CD-000002")


def test_name_fallback_no_candidates_is_no_match():
    repo = FakeRepository()
    outcome = resolve_identity(
        repo,
        request(
            identifiers=[("RXNORM", "404")],
            normalized_name="unknown substance",
            name_fallback_permitted=True,
        ),
    )
    assert outcome.reason_code == "NO_MATCH"


def test_combination_identity_is_left_to_containment_not_resolver():
    # A combination item resolves to its CD; contains lives in kmx.contains,
    # which the resolver never touches.
    repo = FakeRepository(
        bindings=[
            (
                "RXNORM",
                "combo-1",
                [binding("KMX-CD-000777", "clinical_drug")],
            )
        ]
    )
    outcome = resolve_identity(repo, request(identifiers=[("RXNORM", "combo-1")]))
    assert isinstance(outcome, Resolved)
    assert outcome.kmx_id == "KMX-CD-000777"


def test_product_level_from_non_regulator_lane_is_unproven():
    repo = FakeRepository(
        bindings=[("RXNORM", "brand-1", [binding("KMX-CD-000100", "clinical_drug")])]
    )
    outcome = resolve_identity(
        repo,
        request(
            identifiers=[("RXNORM", "brand-1")],
            desired_level=KmxLevel.PRODUCT,
            source_id="rxnorm_athena",
        ),
    )
    assert outcome.reason_code == "PRODUCT_IDENTITY_UNPROVEN"
    assert "rxnorm_athena" not in APPROVED_PRODUCT_CREATORS
    assert set(APPROVED_PRODUCT_CREATORS) == {"ppb_register", "ema", "mhra"}


def test_product_level_from_approved_regulator_lane_resolves():
    repo = FakeRepository(
        bindings=[("EMA_PRODUCT", "prod-9", [binding("KMX-PROD-000001", "product")])]
    )
    outcome = resolve_identity(
        repo,
        request(
            identifiers=[("EMA_PRODUCT", "prod-9")],
            desired_level=KmxLevel.PRODUCT,
            lane_id="S26",
            source_id="ema",
            source_record_key="prod-9",
        ),
    )
    assert isinstance(outcome, Resolved)
    assert outcome.kmx_id == "KMX-PROD-000001"


def test_conservative_normalization_behaviour():
    assert normalize_name("  Amoxicillin   Trihydrate ") == "amoxicillin trihydrate"
    assert normalize_name("ASPIRIN") == "aspirin"
    # NFKC folds full-width and compatibility forms.
    assert normalize_name("Ａｍｏｘ") == "amox"
    assert normalize_name("caf\u00e9") == normalize_name("cafe\u0301")
    # Strength, form and punctuation are identity-bearing: never stripped.
    assert normalize_name("Amoxicillin 500mg") != normalize_name("Amoxicillin 250mg")
    assert normalize_name("drug-name") != normalize_name("drugname")
    assert normalize_name("levonorgestrel (bb)") != normalize_name("levonorgestrel")
    with pytest.raises(ValueError):
        normalize_name("   ")


def test_resolver_has_no_ai_or_network_path():
    import importlib
    import sys

    before = set(sys.modules)
    importlib.import_module("kmx.resolver")
    loaded = set(sys.modules) - before
    for banned in ("httpx", "requests", "boto3", "psycopg", "openai", "anthropic"):
        assert not any(name == banned or name.startswith(banned + ".") for name in loaded), (
            f"resolver must not load {banned}"
        )

    import ast

    tree = ast.parse(Path("src/kmx/resolver.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert imported <= {"exceptions", "models"}, f"unexpected resolver imports: {imported}"


def test_request_validates_its_inputs():
    with pytest.raises(Exception):
        request(identifiers=[], normalized_name=None)
    with pytest.raises(Exception):
        request(identifiers=[("", "value")])
    with pytest.raises(Exception):
        request(desired_level="presentation")


def test_provenance_is_recordable():
    outcome = resolve_identity(FakeRepository(), request(identifiers=[("RXNORM", "9")]))
    assert isinstance(outcome, MappingExceptionOutcome)
    provenance = outcome.request.provenance()
    assert provenance["lane_id"] == "S01"
    assert provenance["source_id"] == "rxnorm_athena"
    assert provenance["identifiers"] == [{"system": "RXNORM", "value": "9"}]
    assert provenance["normalized_name"] is None


@pytest.mark.integration
@pytest.mark.skipif(not CI_POSTGRES, reason="isolated hosted CI PostgreSQL only")
def test_repository_against_ci_postgres():
    from database.connection import connect
    from database.migrations import apply_or_verify
    from database.transaction import transaction

    root = os.path.join(os.path.dirname(__file__), "..")
    connection = connect(
        host="127.0.0.1",
        port=5432,
        dbname="kemirix_knowledge",
        user="kemirix_ci",
        password="disposable-ci-only",
        sslmode="disable",
        allow_insecure=True,
    )
    try:
        assert apply_or_verify(connection, root)["status"] in ("applied", "verified")
        repository = KmxRepository(connection)
        with transaction(connection):
            connection.execute(
                "INSERT INTO kmx.registry (kmx_id, level, preferred_name, normalized_name) "
                "VALUES ('KMX-ING-900001', 'ingredient', 'Test Substance', 'test substance')"
            )
            connection.execute(
                "INSERT INTO kmx.external_identifier (kmx_id, identifier_system, "
                "identifier_value, source_id) VALUES ('KMX-ING-900001', 'UNII', "
                "'TESTUNII1', 'rxnorm_athena')"
            )
            exception_id = repository.record_mapping_exception(
                lane_id="S01",
                source_id="rxnorm_athena",
                source_version_key="test-version",
                source_record_key="test-record",
                reason_code="NO_MATCH",
                normalized_input={"name": "test"},
                candidate_kmx_ids=[],
            )
            assert exception_id > 0
        bindings = repository.external_bindings("UNII", "TESTUNII1")
        assert [b.kmx_id for b in bindings] == ["KMX-ING-900001"]
        candidates = repository.name_candidates("test substance")
        assert [c.kmx_id for c in candidates] == ["KMX-ING-900001"]
        outcome = resolve_identity(
            repository,
            ResolutionRequest(
                identifiers=[("UNII", "TESTUNII1")],
                lane_id="S01",
                source_id="rxnorm_athena",
                source_record_key="test-record",
            ),
        )
        assert isinstance(outcome, Resolved)
        assert outcome.kmx_id == "KMX-ING-900001"
        with transaction(connection):
            row = connection.execute(
                "SELECT reason_code FROM kmx.mapping_exception WHERE exception_id = %s",
                (exception_id,),
            ).fetchone()
        assert row is not None and row[0] == "NO_MATCH"
        # The CI gate re-applies from zero on its own database; clean up the
        # synthetic rows so the shared database state stays pristine.
        with transaction(connection):
            connection.execute(
                "DELETE FROM kmx.mapping_exception WHERE source_id = 'rxnorm_athena' "
                "AND source_record_key = 'test-record'"
            )
            connection.execute(
                "DELETE FROM kmx.external_identifier WHERE identifier_value = 'TESTUNII1'"
            )
            connection.execute("DELETE FROM kmx.registry WHERE kmx_id = 'KMX-ING-900001'")
    finally:
        connection.close()
