"""KMX-003 builder and allocation tests (Phase 8).

Unit tests run against an in-memory fake repository/connection. The
CI-gated concurrency test runs only on the isolated hosted CI PostgreSQL
(KEMIRIX_CI_POSTGRES=1 and GITHUB_ACTIONS=true).
"""

import os
import threading

import pytest

from kmx.builders import Built, KmxBuilder, PreciseParent
from kmx.exceptions import MappingExceptionBoundaryError
from kmx.models import KmxLevel
from kmx.normalizer import normalize_name

pytestmark = pytest.mark.contract

CI_POSTGRES = (
    os.environ.get("KEMIRIX_CI_POSTGRES") == "1" and os.environ.get("GITHUB_ACTIONS") == "true"
)

RXNORM_LEVELS = (KmxLevel.INGREDIENT, KmxLevel.CLINICAL_DRUG)


class FakeStore:
    """In-memory registry, identifiers, names, containment and exceptions."""

    def __init__(self):
        self.registry = {}
        self.identifiers = {}  # (system, value) -> [kmx_id]
        self.names = {}
        self.containment = set()
        self.next_number = {"ingredient": 0, "clinical_drug": 0, "product": 0}
        self.statements = []
        self._snapshot = None

    def _take_snapshot(self):
        return (
            dict(self.registry),
            {key: list(value) for key, value in self.identifiers.items()},
            {key: list(value) for key, value in self.names.items()},
            set(self.containment),
            dict(self.next_number),
        )

    def _restore_snapshot(self):
        (
            self.registry,
            self.identifiers,
            self.names,
            self.containment,
            self.next_number,
        ) = self._snapshot
        self._snapshot = None

    # connection surface
    def execute(self, sql, params=None):
        self.statements.append(sql)
        if sql == "BEGIN":
            self._snapshot = self._take_snapshot()
            return _Rows([])
        if sql == "COMMIT":
            self._snapshot = None
            return _Rows([])
        if sql == "ROLLBACK":
            if self._snapshot is not None:
                self._restore_snapshot()
            return _Rows([])
        if "pg_advisory_xact_lock" in sql:
            return _Rows([(1,)])
        if "COALESCE(MAX(RIGHT(kmx_id" in sql:
            level = "product"
            if params and params[0] == "KMX-ING-%":
                level = "ingredient"
            elif params and params[0] == "KMX-CD-%":
                level = "clinical_drug"
            return _Rows([(self.next_number[level],)])
        if sql.startswith("INSERT INTO kmx.registry"):
            kmx_id, level, preferred, normalized = params
            self.registry[kmx_id] = {
                "level": level,
                "preferred": preferred,
                "normalized": normalized,
            }
            self.next_number[level] = int(kmx_id[-6:])
            return _Rows([])
        if sql.startswith("INSERT INTO kmx.external_identifier"):
            kmx_id, system, value, source_id, jurisdiction = params
            self.identifiers.setdefault((system, value), []).append(kmx_id)
            return _Rows([])
        if sql.startswith("INSERT INTO kmx.name_index"):
            kmx_id, normalized, name_type, source_id, language = params
            self.names.setdefault(normalized, []).append(kmx_id)
            return _Rows([])
        if sql.startswith("INSERT INTO kmx.contains"):
            container, member, relationship, ordinal = params
            self.containment.add((container, member, relationship, ordinal))
            return _Rows([])
        if sql.startswith("SELECT 1 FROM kmx.contains"):
            container, member, relationship = params
            return _Rows(
                [(1,)]
                if any(edge[:3] == (container, member, relationship) for edge in self.containment)
                else []
            )
        if sql.startswith("SELECT kmx_id, level, normalized_name FROM kmx.registry"):
            kmx_id = params[0]
            row = self.registry.get(kmx_id)
            return _Rows([(kmx_id, row["level"], row["normalized"])] if row else [])
        if "identifier_system = %s" in sql:
            system, value = params
            ids = self.identifiers.get((system, value), [])
            return _Rows(
                [(kmx_id, self.registry[kmx_id]["level"], "rxnorm_athena") for kmx_id in ids]
            )
        if "normalized_name = %s" in sql:
            if len(params) == 2:
                normalized, level = params
                ids = [
                    kmx_id
                    for kmx_id in self.names.get(normalized, [])
                    if self.registry[kmx_id]["level"] == level
                ]
            else:
                normalized = params[0]
                ids = list(self.names.get(normalized, []))
            return _Rows([(kmx_id, self.registry[kmx_id]["level"], normalized) for kmx_id in ids])
        raise AssertionError(f"unexpected SQL: {sql}")

    # repository surface
    def external_bindings(self, system, value):
        from kmx.repository import ExternalBinding

        return [
            ExternalBinding(kmx_id, self.registry[kmx_id]["level"], "rxnorm_athena")
            for kmx_id in self.identifiers.get((system, value), [])
        ]

    def name_candidates(self, normalized_name, *, level=None):
        from kmx.repository import NameCandidate

        kmx_ids = self.names.get(normalized_name, [])
        if level is not None:
            kmx_ids = [k for k in kmx_ids if self.registry[k]["level"] == level]
        return [NameCandidate(k, self.registry[k]["level"], normalized_name) for k in kmx_ids]

    def get_kmx(self, kmx_id):
        from kmx.repository import NameCandidate

        row = self.registry.get(kmx_id)
        if not row:
            return None
        return NameCandidate(kmx_id, row["level"], row["normalized"])

    def insert_kmx(self, *, kmx_id, level, preferred_name, normalized_name):
        self.execute(
            "INSERT INTO kmx.registry (kmx_id, level, preferred_name, normalized_name) "
            "VALUES (%s, %s, %s, %s)",
            (kmx_id, level, preferred_name, normalized_name),
        )

    def insert_external_identifier(
        self, *, kmx_id, identifier_system, identifier_value, source_id, jurisdiction=None
    ):
        self.execute(
            "INSERT INTO kmx.external_identifier (kmx_id, identifier_system, "
            "identifier_value, source_id, jurisdiction) VALUES (%s, %s, %s, %s, %s)",
            (kmx_id, identifier_system, identifier_value, source_id, jurisdiction),
        )

    def insert_name(self, *, kmx_id, normalized_name, name_type, source_id, language="en"):
        self.execute(
            "INSERT INTO kmx.name_index (kmx_id, normalized_name, name_type, "
            "source_id, language) VALUES (%s, %s, %s, %s, %s)",
            (kmx_id, normalized_name, name_type, source_id, language),
        )

    def insert_containment(
        self, *, container_kmx_id, member_kmx_id, relationship_type, ordinal=None
    ):
        self.execute(
            "INSERT INTO kmx.contains (container_kmx_id, member_kmx_id, "
            "relationship_type, ordinal) VALUES (%s, %s, %s, %s)",
            (container_kmx_id, member_kmx_id, relationship_type, ordinal),
        )

    def existing_containment(self, *, container_kmx_id, member_kmx_id, relationship_type):
        row = self.execute(
            "SELECT 1 FROM kmx.contains WHERE container_kmx_id = %s "
            "AND member_kmx_id = %s AND relationship_type = %s",
            (container_kmx_id, member_kmx_id, relationship_type),
        ).fetchone()
        return row is not None


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


def make_builder():
    store = FakeStore()
    from kmx.repository import KmxRepository

    return KmxBuilder(KmxRepository(store), store), store


def test_ingredient_builder_mints_and_reuses():
    builder, store = make_builder()
    built = builder.build_ingredient(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Amoxicillin",
        normalized_name=normalize_name("Amoxicillin"),
        identifiers=[("RXNORM", "723")],
    )
    assert built == Built("KMX-ING-000001", "ingredient", True)
    reused = builder.build_ingredient(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Amoxicillin",
        normalized_name=normalize_name("Amoxicillin"),
        identifiers=[("RXNORM", "723")],
    )
    assert reused == Built("KMX-ING-000001", "ingredient", False)
    assert store.next_number["ingredient"] == 1


def test_unauthorized_lane_cannot_mint_ingredient():
    builder, _ = make_builder()
    with pytest.raises(MappingExceptionBoundaryError, match="not authorized"):
        builder.build_ingredient(
            lane_id="S12",
            source_id="kenya_moh",
            allowed_levels=(),  # guideline lane: no identity minting
            preferred_name="Anything",
            normalized_name=normalize_name("Anything"),
            identifiers=[("LOCAL", "x")],
        )


def test_min_concepts_never_mint_a_fake_single_ingredient():
    builder, _ = make_builder()
    with pytest.raises(MappingExceptionBoundaryError, match="MIN"):
        builder.build_ingredient(
            lane_id="S01",
            source_id="rxnorm_athena",
            allowed_levels=RXNORM_LEVELS,
            preferred_name="amoxicillin / clavulanate",
            normalized_name=normalize_name("amoxicillin / clavulanate"),
            identifiers=[("RXNORM", "min-1")],
            concept_type="MIN",
        )


def test_proven_pin_mints_own_identity_and_links_to_base():
    builder, store = make_builder()
    base = builder.build_ingredient(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Amoxicillin",
        normalized_name=normalize_name("Amoxicillin"),
        identifiers=[("RXNORM", "723")],
    )
    pin = builder.build_ingredient(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Amoxicillin Trihydrate",
        normalized_name=normalize_name("Amoxicillin Trihydrate"),
        identifiers=[("RXNORM", "2261")],
        concept_type="PIN",
        precise_parent=PreciseParent(base.kmx_id, relationship_proven=True),
    )
    assert pin.kmx_id != base.kmx_id
    assert pin.created is True
    assert (base.kmx_id, pin.kmx_id, "precise_ingredient", None) in store.containment


def test_unproven_pin_keeps_own_identity_without_blind_link():
    builder, store = make_builder()
    base = builder.build_ingredient(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Amoxicillin",
        normalized_name=normalize_name("Amoxicillin"),
        identifiers=[("RXNORM", "723")],
    )
    pin = builder.build_ingredient(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Amoxicillin Sodium",
        normalized_name=normalize_name("Amoxicillin Sodium"),
        identifiers=[("RXNORM", "9999")],
        concept_type="PIN",
        precise_parent=PreciseParent(base.kmx_id, relationship_proven=False),
    )
    assert pin.created is True
    assert not any(edge[0] == base.kmx_id and edge[1] == pin.kmx_id for edge in store.containment)


def test_scd_builds_cd_with_deterministic_containment():
    builder, store = make_builder()
    amox = builder.build_ingredient(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Amoxicillin",
        normalized_name=normalize_name("Amoxicillin"),
        identifiers=[("RXNORM", "723")],
    )
    cd = builder.build_clinical_drug(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Amoxicillin 500 MG Oral Capsule",
        normalized_name=normalize_name("Amoxicillin 500 MG Oral Capsule"),
        identifiers=[("RXNORM", "308182")],
        ingredient_kmx_ids=[amox.kmx_id],
    )
    assert cd == Built("KMX-CD-000001", "clinical_drug", True)
    assert (cd.kmx_id, amox.kmx_id, "contains", 1) in store.containment


def test_release_and_strength_variants_never_collapse():
    builder, store = make_builder()
    amox = builder.build_ingredient(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Amoxicillin",
        normalized_name=normalize_name("Amoxicillin"),
        identifiers=[("RXNORM", "723")],
    )
    ir = builder.build_clinical_drug(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Amoxicillin 500 MG Oral Tablet",
        normalized_name=normalize_name("Amoxicillin 500 MG Oral Tablet"),
        identifiers=[("RXNORM", "a")],
        ingredient_kmx_ids=[amox.kmx_id],
    )
    er = builder.build_clinical_drug(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Amoxicillin ER 500 MG Oral Tablet",
        normalized_name=normalize_name("Amoxicillin ER 500 MG Oral Tablet"),
        identifiers=[("RXNORM", "b")],
        ingredient_kmx_ids=[amox.kmx_id],
    )
    low = builder.build_clinical_drug(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Amoxicillin 250 MG Oral Tablet",
        normalized_name=normalize_name("Amoxicillin 250 MG Oral Tablet"),
        identifiers=[("RXNORM", "c")],
        ingredient_kmx_ids=[amox.kmx_id],
    )
    assert len({ir.kmx_id, er.kmx_id, low.kmx_id}) == 3
    # Same normalized names never merge distinct formulations by name either:
    # reuse is exact-identifier only.
    again = builder.build_clinical_drug(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Amoxicillin 500 MG Oral Tablet",
        normalized_name=normalize_name("Amoxicillin 500 MG Oral Tablet"),
        identifiers=[("RXNORM", "a")],
        ingredient_kmx_ids=[amox.kmx_id],
    )
    assert again.created is False and again.kmx_id == ir.kmx_id


def test_combination_cd_contains_each_ingredient_with_ordinals():
    builder, store = make_builder()
    amox = builder.build_ingredient(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Amoxicillin",
        normalized_name=normalize_name("Amoxicillin"),
        identifiers=[("RXNORM", "723")],
    )
    clav = builder.build_ingredient(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Clavulanate",
        normalized_name=normalize_name("Clavulanate"),
        identifiers=[("RXNORM", "1545")],
    )
    cd = builder.build_clinical_drug(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Amoxicillin 500 MG / Clavulanate 125 MG Oral Tablet",
        normalized_name=normalize_name("Amoxicillin 500 MG / Clavulanate 125 MG Oral Tablet"),
        identifiers=[("RXNORM", "combo")],
        ingredient_kmx_ids=[amox.kmx_id, clav.kmx_id],
    )
    assert (cd.kmx_id, amox.kmx_id, "contains", 1) in store.containment
    assert (cd.kmx_id, clav.kmx_id, "contains", 2) in store.containment


def test_cd_builder_requires_resolved_ingredient_members():
    builder, _ = make_builder()
    with pytest.raises(MappingExceptionBoundaryError, match="at least one"):
        builder.build_clinical_drug(
            lane_id="S01",
            source_id="rxnorm_athena",
            allowed_levels=RXNORM_LEVELS,
            preferred_name="Ghost",
            normalized_name=normalize_name("Ghost"),
            identifiers=[("RXNORM", "g")],
            ingredient_kmx_ids=[],
        )
    with pytest.raises(MappingExceptionBoundaryError, match="not a resolved ingredient"):
        builder.build_clinical_drug(
            lane_id="S01",
            source_id="rxnorm_athena",
            allowed_levels=RXNORM_LEVELS,
            preferred_name="Ghost",
            normalized_name=normalize_name("Ghost"),
            identifiers=[("RXNORM", "g")],
            ingredient_kmx_ids=["KMX-CD-000001"],
        )


def test_sbd_or_brand_never_mints_product():
    builder, _ = make_builder()
    with pytest.raises(MappingExceptionBoundaryError, match="PRODUCT_IDENTITY_UNPROVEN"):
        builder.build_product(
            lane_id="S01",
            source_id="rxnorm_athena",  # not an approved regulator product lane
            preferred_name="Augmentin",
            normalized_name=normalize_name("Augmentin"),
            regulator_identifier={"system": "RXNORM", "value": "sbd-1"},
            clinical_drug_kmx_ids=["KMX-CD-000001"],
        )
    with pytest.raises(MappingExceptionBoundaryError, match="regulator product"):
        builder.build_product(
            lane_id="S26",
            source_id="ema",
            preferred_name="Some EMA Product",
            normalized_name=normalize_name("Some EMA Product"),
            regulator_identifier=None,
            clinical_drug_kmx_ids=["KMX-CD-000001"],
        )


def test_regulator_fixture_creates_and_reuses_product():
    builder, store = make_builder()
    amox = builder.build_ingredient(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Amoxicillin",
        normalized_name=normalize_name("Amoxicillin"),
        identifiers=[("RXNORM", "723")],
    )
    cd = builder.build_clinical_drug(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Amoxicillin 500 MG Oral Capsule",
        normalized_name=normalize_name("Amoxicillin 500 MG Oral Capsule"),
        identifiers=[("RXNORM", "308182")],
        ingredient_kmx_ids=[amox.kmx_id],
    )
    prod = builder.build_product(
        lane_id="S26",
        source_id="ema",
        preferred_name="Amoxicillin EMA Product",
        normalized_name=normalize_name("Amoxicillin EMA Product"),
        regulator_identifier={"system": "EMA_PRODUCT", "value": "EU/1/26/001"},
        clinical_drug_kmx_ids=[cd.kmx_id],
    )
    assert prod == Built("KMX-PROD-000001", "product", True)
    assert (prod.kmx_id, cd.kmx_id, "contains", 1) in store.containment
    reused = builder.build_product(
        lane_id="S26",
        source_id="ema",
        preferred_name="Amoxicillin EMA Product",
        normalized_name=normalize_name("Amoxicillin EMA Product"),
        regulator_identifier={"system": "EMA_PRODUCT", "value": "EU/1/26/001"},
        clinical_drug_kmx_ids=[cd.kmx_id],
    )
    assert reused.created is False and reused.kmx_id == prod.kmx_id


def test_product_requires_resolved_clinical_drug():
    builder, _ = make_builder()
    with pytest.raises(MappingExceptionBoundaryError, match="clinical drug"):
        builder.build_product(
            lane_id="S26",
            source_id="ema",
            preferred_name="X",
            normalized_name=normalize_name("X"),
            regulator_identifier={"system": "EMA_PRODUCT", "value": "v"},
            clinical_drug_kmx_ids=["KMX-ING-000001"],
        )


def test_refresh_does_not_renumber():
    builder, store = make_builder()
    first = builder.build_ingredient(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Substance One",
        normalized_name=normalize_name("Substance One"),
        identifiers=[("RXNORM", "1")],
    )
    second = builder.build_ingredient(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Substance Two",
        normalized_name=normalize_name("Substance Two"),
        identifiers=[("RXNORM", "2")],
    )
    # A refresh re-encounters the same identities and reuses them.
    refreshed_first = builder.build_ingredient(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Substance One",
        normalized_name=normalize_name("Substance One"),
        identifiers=[("RXNORM", "1")],
    )
    third = builder.build_ingredient(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=RXNORM_LEVELS,
        preferred_name="Substance Three",
        normalized_name=normalize_name("Substance Three"),
        identifiers=[("RXNORM", "3")],
    )
    assert first.kmx_id == refreshed_first.kmx_id
    assert (first.kmx_id, second.kmx_id, third.kmx_id) == (
        "KMX-ING-000001",
        "KMX-ING-000002",
        "KMX-ING-000003",
    )


def test_build_failure_rolls_back_atomically():
    builder, store = make_builder()
    # The in-transaction failure: an ingredient mint whose precise parent
    # links to a clinical drug after the registry/identifier/name inserts.
    with pytest.raises(MappingExceptionBoundaryError):
        builder.build_ingredient(
            lane_id="S01",
            source_id="rxnorm_athena",
            allowed_levels=RXNORM_LEVELS,
            preferred_name="Broken Precise",
            normalized_name=normalize_name("Broken Precise"),
            identifiers=[("RXNORM", "broken")],
            precise_parent=PreciseParent("KMX-CD-000001", relationship_proven=True),
        )
    assert "BEGIN" in store.statements and "ROLLBACK" in store.statements
    assert ("RXNORM", "broken") not in store.identifiers
    assert all(row["normalized"] != "broken precise" for row in store.registry.values())


@pytest.mark.integration
@pytest.mark.skipif(not CI_POSTGRES, reason="isolated hosted CI PostgreSQL only")
def test_concurrent_allocation_is_unique_on_ci_postgres():
    from database.connection import connect
    from database.migrations import apply_or_verify
    from database.transaction import transaction
    from kmx.allocation import allocate_kmx_id

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
        allocated = []
        errors = []
        lock = threading.Lock()

        def allocate():
            try:
                with transaction(connection):
                    kmx_id = allocate_kmx_id(connection, "ingredient")
                    connection.execute(
                        "INSERT INTO kmx.registry (kmx_id, level, preferred_name, "
                        "normalized_name) VALUES (%s, 'ingredient', %s, %s)",
                        (str(kmx_id), f"Concurrent {kmx_id.value}", f"concurrent {kmx_id.value}"),
                    )
                with lock:
                    allocated.append(str(kmx_id))
            except Exception as error:  # pragma: no cover - surfaced by assertion
                with lock:
                    errors.append(type(error).__name__)

        threads = [threading.Thread(target=allocate) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert not errors, errors
        assert len(set(allocated)) == 8, allocated
        # Clean up the synthetic rows so the shared CI database stays pristine.
        with transaction(connection):
            connection.execute("DELETE FROM kmx.registry WHERE normalized_name LIKE 'concurrent %'")
    finally:
        connection.close()
