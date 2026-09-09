"""IDENTITY-SOURCES-001 S02-S05 identity-enrichment tests (Phase 10).

Everything is offline: synthetic OMOP CSVs, GSRS JSON snapshots, ChEBI
JSON archives, MED-RT XML/crosswalk fixtures and archive-index HTML. No
live network access, no real S02-S05 downloads.
"""

import json
import zipfile

import pytest

from kmx.builders import KmxBuilder
from kmx.normalizer import normalize_name
from kmx.repository import KmxRepository
from sources.athena_extension.omop import (
    map_omop_into_existing,
    validate_athena_zip,
    vocabulary_manifest,
)
from sources.chebi_unichem.chebi import (
    bridge_to_ing,
    compound_summary,
    iter_chebi_compounds,
    unichem_compounds_request,
    unichem_connectivity_request,
    unichem_sources_url,
)
from sources.exceptions import SourceContractError
from sources.gsrs_unii.substance import (
    canary_url,
    iter_substances,
    parse_canary_result,
    resolve_unii_to_ing,
)
from sources.medrt.medrt import (
    attach_via_crosswalk,
    discover_paired_releases,
    iter_associations,
    newest_pair,
    parse_crosswalk,
)

pytestmark = pytest.mark.contract


class FakeConnection:
    def __init__(self):
        self.registry = {}
        self.identifiers = {}
        self.names = {}
        self.containment = set()
        self.exceptions = []
        self.next_number = {"ingredient": 0, "clinical_drug": 0, "product": 0}
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append(sql)
        if sql in ("BEGIN", "COMMIT", "ROLLBACK"):
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
            self.registry[kmx_id] = {"level": level, "normalized": normalized}
            self.next_number[level] = int(kmx_id[-6:])
            return _Rows([])
        if sql.startswith("INSERT INTO kmx.external_identifier"):
            kmx_id, system, value, source_id, jurisdiction = params
            self.identifiers.setdefault((system, value), []).append(kmx_id)
            return _Rows([])
        if sql.startswith("INSERT INTO kmx.name_index"):
            kmx_id, normalized, name_type, source_id, language = params
            self.names.setdefault((normalized, name_type), []).append(kmx_id)
            return _Rows([])
        if sql.startswith("INSERT INTO kmx.contains"):
            container, member, relationship, ordinal = params
            self.containment.add((container, member, relationship, ordinal))
            return _Rows([])
        if sql.startswith("INSERT INTO kmx.mapping_exception"):
            self.exceptions.append(params)
            return _Rows([(len(self.exceptions),)])
        if sql.startswith("SELECT 1 FROM kmx.contains"):
            container, member, relationship = params
            return _Rows(
                [(1,)]
                if any(e[:3] == (container, member, relationship) for e in self.containment)
                else []
            )
        if sql.startswith("SELECT kmx_id, level, normalized_name FROM kmx.registry"):
            row = self.registry.get(params[0])
            return _Rows([(params[0], row["level"], row["normalized"])] if row else [])
        if "identifier_system = %s" in sql:
            system, value = params
            ids = self.identifiers.get((system, value), [])
            return _Rows([(k, self.registry[k]["level"], "rxnorm_athena") for k in ids])
        if "normalized_name = %s" in sql:
            ids = [k for k in self.registry if self.registry[k]["normalized"] == params[0]]
            return _Rows([(k, self.registry[k]["level"], params[0]) for k in ids])
        raise AssertionError(f"unexpected SQL: {sql}")


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


def make_stack():
    connection = FakeConnection()
    repository = KmxRepository(connection)
    builder = KmxBuilder(repository, connection)
    return connection, repository, builder


def seed_ingredient(builder, rxcui, name):
    return builder.build_ingredient(
        lane_id="S01",
        source_id="rxnorm_athena",
        allowed_levels=("ingredient", "clinical_drug"),
        preferred_name=name,
        normalized_name=normalize_name(name),
        identifiers=[("RXNORM", rxcui)],
    )


# --- S02 OMOP Athena ---------------------------------------------------------


def build_athena_zip(path, concepts, vocabularies):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "CONCEPT.csv",
            "concept_id,concept_code,vocabulary_id,concept_name\n" + concepts,
        )
        archive.writestr(
            "VOCABULARY.csv",
            "vocabulary_id,vocabulary_name,vocabulary_version,vocabulary_reference\n"
            + vocabularies,
        )
        archive.writestr("CONCEPT_RELATIONSHIP.csv", "concept_id_1,concept_id_2,relationship_id\n")
        archive.writestr("CONCEPT_SYNONYM.csv", "concept_id,synonym_concept_id\n")
        archive.writestr("DRUG_STRENGTH.csv", "drug_concept_id,ing_concept_id\n")


def test_athena_zip_validation_and_vocabulary_manifest(tmp_path):
    path = tmp_path / "athena.zip"
    build_athena_zip(
        path, "1,723,RxNorm,Amoxicillin\n", "RxNorm,RxNorm,2026-09-08,https://www.nlm.nih.gov\n"
    )
    assert validate_athena_zip(path) is True
    manifest = vocabulary_manifest(path)
    assert manifest["RxNorm"]["version"] == "2026-09-08"
    broken = tmp_path / "broken.zip"
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr("CONCEPT.csv", "concept_id\n")
    with pytest.raises(SourceContractError, match="missing members"):
        validate_athena_zip(broken)


def test_omop_enrichment_attaches_to_existing_kmx_only(tmp_path):
    connection, repository, builder = make_stack()
    seed_ingredient(builder, "723", "Amoxicillin")
    path = tmp_path / "athena.zip"
    concepts = (
        "111,723,RxNorm,Amoxicillin\n"
        "222,999999,RxNorm,Not In Kemirix\n"
        "333,ABC,RxNorm Extension,Some Extension Concept\n"
        "444,777,SNOMED,Not RxNorm Vocabulary\n"
    )
    build_athena_zip(path, concepts, "RxNorm,RxNorm,2026-09-08,ref\n")
    stats = map_omop_into_existing(repository, path, exception_recorder=repository)
    assert stats["concepts_seen"] == 4
    assert stats["rxnorm_rows"] == 3
    assert stats["attached"] == 1
    assert stats["unresolved"] == 2
    # Only the existing identity got an OMOP identifier; nothing was minted.
    assert ("OMOP_CONCEPT_ID", "111") in connection.identifiers
    ing = connection.identifiers[("RXNORM", "723")][0]
    assert connection.identifiers[("OMOP_CONCEPT_ID", "111")] == [ing]
    assert len(connection.registry) == 1
    # Both unresolved RxNorm/Extension rows recorded mapping exceptions.
    assert len(connection.exceptions) == 2


# --- S03 GSRS / UNII ---------------------------------------------------------


def build_gsrs_zip(path, records):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("substance.json", json.dumps(records))


def test_gsrs_snapshot_parsing_and_unii_resolution(tmp_path):
    path = tmp_path / "gsrs.zip"
    build_gsrs_zip(
        path,
        [
            {
                "unii": "362O9ITL9D",
                "preferred_name": "AMOXICILLIN",
                "substance_class": "chemical",
                "relationships": [],
            },
            {
                "unii": "00937I7Y57",
                "preferred_name": "AMOXICILLIN TRIHYDRATE",
                "substance_class": "chemical",
                "relationships": [
                    {
                        "type": "has_parent",
                        "associated_substance": {"unii": "362O9ITL9D"},
                    }
                ],
            },
            {
                "unii": "804826J2VX",
                "preferred_name": "AMOXICILLIN SODIUM",  # same name family, distinct salt
                "substance_class": "chemical",
                "relationships": [
                    {
                        "type": "has_parent",
                        "associated_substance": {"unii": "362O9ITL9D"},
                    }
                ],
            },
        ],
    )
    substances = list(iter_substances(path))
    assert [s["unii"] for s in substances] == ["362O9ITL9D", "00937I7Y57", "804826J2VX"]
    connection, repository, builder = make_stack()
    stats = resolve_unii_to_ing(builder, repository, substances)
    assert stats["created"] == 3 and stats["reused"] == 0
    # Both salts kept their own identities and linked to the base: never merged.
    base = connection.identifiers[("UNII", "362O9ITL9D")][0]
    trihydrate = connection.identifiers[("UNII", "00937I7Y57")][0]
    sodium = connection.identifiers[("UNII", "804826J2VX")][0]
    assert len({base, trihydrate, sodium}) == 3
    assert (base, trihydrate, "precise_ingredient", None) in connection.containment
    assert (base, sodium, "precise_ingredient", None) in connection.containment
    assert stats["parent_links"] == 2
    # Rerun reuses every identity and adds no duplicate links.
    rerun = resolve_unii_to_ing(builder, repository, substances)
    assert rerun["created"] == 0 and rerun["reused"] == 3 and rerun["parent_links"] == 0


def test_openfda_canary_client_surface():
    assert (
        canary_url("362O9ITL9D")
        == 'https://api.fda.gov/other/substance.json?search=unii:"362O9ITL9D"'
    )
    with pytest.raises(SourceContractError):
        canary_url('x"y')
    payload = parse_canary_result(
        json.dumps({"results": [{"unii": "362O9ITL9D", "preferred_name": "AMOXICILLIN"}]})
    )
    assert payload["unii"] == "362O9ITL9D"
    assert parse_canary_result(json.dumps({"results": []})) is None
    with pytest.raises(SourceContractError):
        parse_canary_result("not json")


# --- S04 ChEBI + UniChem ------------------------------------------------------


def build_chebi_zip(path, compounds):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("chebi_full.json", json.dumps(compounds))


def test_chebi_bridge_is_exact_curated_only(tmp_path):
    path = tmp_path / "chebi.zip"
    build_chebi_zip(
        path,
        [
            {
                "chebiId": 2676,
                "name": "amoxicillin",
                "inchiKey": "LSQZJJSYHWCUBN-UHFFFAOYSA-N",
                "synonyms": [{"name": "amoxycillin"}],
                "ontologyParents": [{"targetChebiId": 5000}],
                "crossReferences": [{"dataSource": "UNII", "referenceId": "362O9ITL9D"}],
            },
            {
                "chebiId": 5371,
                "name": "amoxicillin trihydrate",
                "inchiKey": "MSHWWDQULRXYPG-UHFFFAOYSA-N",
                "synonyms": [],
                "ontologyParents": [{"targetChebiId": 2676}],
                "crossReferences": [{"dataSource": "UNII", "referenceId": "00937I7Y57"}],
            },
        ],
    )
    compounds = list(iter_chebi_compounds(path))
    summaries = [compound_summary(c) for c in compounds]
    assert summaries[0]["xrefs"]["UNII"] == ["362O9ITL9D"]
    assert summaries[1]["parents"] == [2676]
    connection, repository, builder = make_stack()
    base = seed_ingredient(builder, "723", "Amoxicillin")
    repository.insert_external_identifier(
        kmx_id=base.kmx_id,
        identifier_system="UNII",
        identifier_value="362O9ITL9D",
        source_id="gsrs_unii",
    )
    stats = bridge_to_ing(builder, repository, compounds)
    # Amoxicillin bridged onto the existing UNII identity (and its CHEBI id
    # attached through the enrichment path); the trihydrate minted its own
    # identity (stereo/salt distinction preserved, never merged).
    assert stats["bridged"] == 1 and stats["created"] == 1
    bridged = connection.identifiers[("UNII", "362O9ITL9D")]
    assert base.kmx_id in bridged
    chebi_ids = {key[1] for key in connection.identifiers if key[0] == "CHEBI"}
    assert {"2676", "5371"} <= chebi_ids
    assert len(connection.registry) == 2


def test_unichem_client_surface():
    assert unichem_sources_url() == "https://www.ebi.ac.uk/unichem/api/v1/sources/"
    assert unichem_compounds_request("1", "723") == {"src_id": "1", "src_compound_id": "723"}
    connectivity = unichem_connectivity_request("1", "723")
    assert connectivity["type"] == "connectivity"
    # Connectivity results are a distinct, non-identity type by design.
    from sources.chebi_unichem.chebi import UniChemConnectivity

    assert UniChemConnectivity.__doc__ and "NOT an identity" in UniChemConnectivity.__doc__


# --- S05 MED-RT ---------------------------------------------------------------


ARCHIVE_HTML = """
<html><body>
<a href="Core_MEDRT_202509_01_Accessory_Files.zip">Core_MEDRT_202509_01_Accessory_Files.zip</a>
<a href="Core_MEDRT_202509_01_XML.zip">Core_MEDRT_202509_01_XML.zip</a>
<a href="Core_MEDRT_202504_01_Accessory_Files.zip">Core_MEDRT_202504_01_Accessory_Files.zip</a>
<a href="Core_MEDRT_202504_01_XML.zip">Core_MEDRT_202504_01_XML.zip</a>
<a href="Core_MEDRT_202410_01_XML.zip">Core_MEDRT_202410_01_XML.zip</a>
<a href="something_else.txt">something_else.txt</a>
</body></html>
"""


def test_medrt_paired_release_discovery():
    pairs = discover_paired_releases(ARCHIVE_HTML)
    assert [pair["release"] for pair in pairs] == ["202509_01", "202504_01"]
    newest = newest_pair(ARCHIVE_HTML)
    assert newest["core_archive"] == "Core_MEDRT_202509_01_XML.zip"
    assert newest["accessory_archive"] == "Core_MEDRT_202509_01_Accessory_Files.zip"
    with pytest.raises(SourceContractError):
        newest_pair("<html>nothing here</html>")


def test_medrt_association_parsing_and_crosswalk_attachment(tmp_path):
    core = tmp_path / "core.xml"
    core.write_text(
        "<medrt>"
        "<association fromCode='C1' name='has_anti_infective_class' toCode='C2'/>"
        "<association fromCode='C3' name='has_moa' toCode='NOXWALK'/>"
        "</medrt>"
    )
    associations = list(iter_associations(core))
    assert associations[0]["from_code"] == "C1"
    accessory = tmp_path / "accessory.zip"
    with zipfile.ZipFile(accessory, "w") as archive:
        archive.writestr("mapping.csv", "code,rxcui\nC1,723\nC2,999\nC3,111\n")
    crosswalk = parse_crosswalk(accessory)
    assert crosswalk == {"C1": "723", "C2": "999", "C3": "111"}
    connection, repository, builder = make_stack()
    amox = seed_ingredient(builder, "723", "Amoxicillin")
    seed_ingredient(builder, "999", "Some Class Ingredient")
    seed_ingredient(builder, "111", "Another Ingredient")
    stats = attach_via_crosswalk(repository, associations, crosswalk)
    # C3->NOXWALK has no crosswalk on the target side: skipped, not guessed.
    assert stats["associations"] == 2
    assert stats["resolved"] == 1
    assert stats["unresolved"] == 1
    edges = [e for e in connection.containment if e[2] == "medrt:has_anti_infective_class"]
    assert edges == [
        (
            amox.kmx_id,
            connection.identifiers[("RXNORM", "999")][0],
            "medrt:has_anti_infective_class",
            None,
        )
    ]


def test_no_live_downloads_or_rule_logic_in_identity_lanes():
    import inspect

    import sources.athena_extension.omop as s02
    import sources.chebi_unichem.chebi as s04
    import sources.gsrs_unii.substance as s03
    import sources.medrt.medrt as s05

    for module in (s02, s03, s04, s05):
        source = inspect.getsource(module)
        for banned in (
            "clinical_rule",
            "rule_evidence",
            "RuleOutcome",
            "evidence_support",
            "boto3",
            "psycopg",
        ):
            assert banned not in source, f"{module.__name__} must not contain {banned}"
