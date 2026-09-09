"""S02 athena_extension: operator-provided OMOP Athena export enrichment.

Athena exports are downloaded manually by the operator (license acceptance
is human-only). This module validates the archive, streams its concept
rows, records exact vocabularies/versions/licenses, and maps verified
OMOP / RxNorm Extension identifiers into EXISTING KMX identities — it never
mints a parallel universe.
"""

import csv
import io
import zipfile

from ..exceptions import SourceContractError

REQUIRED_MEMBERS = (
    "CONCEPT.csv",
    "CONCEPT_RELATIONSHIP.csv",
    "CONCEPT_SYNONYM.csv",
    "DRUG_STRENGTH.csv",
    "VOCABULARY.csv",
)
RXNORM_VOCABULARIES = ("RxNorm", "RxNorm Extension")


def validate_athena_zip(zip_path):
    """All five required members present and readable."""
    with zipfile.ZipFile(zip_path) as archive:
        names = {name.rsplit("/", 1)[-1] for name in archive.namelist()}
    missing = [member for member in REQUIRED_MEMBERS if member not in names]
    if missing:
        raise SourceContractError(f"OMOP Athena export missing members: {', '.join(missing)}")
    return True


def iter_concepts(zip_path):
    """Stream CONCEPT.csv rows (concept_id, concept_code, vocabulary_id, ...)."""
    with zipfile.ZipFile(zip_path) as archive:
        member = next(
            name for name in archive.namelist() if name.rsplit("/", 1)[-1] == "CONCEPT.csv"
        )
        with archive.open(member) as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8")
            for row in csv.DictReader(text):
                yield row


def vocabulary_manifest(zip_path):
    """Exact vocabularies/versions/licenses recorded from VOCABULARY.csv."""
    manifest = {}
    with zipfile.ZipFile(zip_path) as archive:
        member = next(
            name for name in archive.namelist() if name.rsplit("/", 1)[-1] == "VOCABULARY.csv"
        )
        with archive.open(member) as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8")
            for row in csv.DictReader(text):
                manifest[row["vocabulary_id"]] = {
                    "name": row.get("vocabulary_name", ""),
                    "version": row.get("vocabulary_version", ""),
                    "reference": row.get("vocabulary_reference", ""),
                }
    return manifest


def map_omop_into_existing(repository, zip_path, *, exception_recorder=None):
    """Attach OMOP identifiers to EXISTING KMX through exact RxCUI codes.

    RxNorm-vocabulary concepts carry their RXCUI as concept_code; resolving
    that RXCUI against the existing KMX external identifiers and attaching
    the OMOP_CONCEPT_ID enriches existing identities without minting.
    """
    stats = {"concepts_seen": 0, "rxnorm_rows": 0, "attached": 0, "unresolved": 0}
    for row in iter_concepts(zip_path):
        stats["concepts_seen"] += 1
        vocabulary = row.get("vocabulary_id", "")
        if vocabulary not in RXNORM_VOCABULARIES:
            continue
        stats["rxnorm_rows"] += 1
        rxcui = row.get("concept_code", "").strip()
        concept_id = row.get("concept_id", "").strip()
        if not rxcui or not concept_id:
            continue
        bindings = repository.external_bindings("RXNORM", rxcui)
        if len(bindings) != 1:
            stats["unresolved"] += 1
            if exception_recorder is not None and not bindings:
                exception_recorder.record_mapping_exception(
                    lane_id="S02",
                    source_id="athena_extension",
                    source_version_key=None,
                    source_record_key=f"OMOP-{concept_id}",
                    reason_code="NO_MATCH",
                    normalized_input={"rxcui": rxcui, "concept_id": concept_id},
                )
            continue
        existing = repository.external_bindings("OMOP_CONCEPT_ID", concept_id)
        if any(binding.kmx_id == bindings[0].kmx_id for binding in existing):
            continue
        repository.insert_external_identifier(
            kmx_id=bindings[0].kmx_id,
            identifier_system="OMOP_CONCEPT_ID",
            identifier_value=concept_id,
            source_id="athena_extension",
        )
        stats["attached"] += 1
    return stats
