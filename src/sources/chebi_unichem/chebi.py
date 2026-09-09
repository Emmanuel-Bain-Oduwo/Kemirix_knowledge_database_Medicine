"""S04 chebi_unichem: ChEBI FULL JSON parsing, the curated bridge to
KMX-ING and the UniChem REST client.

Stereochemistry, isotope and salt distinctions are preserved — ChEBI
compounds bridge to KMX only through exact curated cross-references, and
UniChem connectivity lookups are explicitly NOT identity: the client
returns them under a separate type that no identity code path consumes.
"""

import gzip
import json
import zipfile
from urllib.parse import quote

from ..exceptions import SourceContractError

UNICHEM_BASE = "https://www.ebi.ac.uk/unichem/api"
UNICHEM_REQUESTS_PER_SECOND = 2.0  # internal conservative default; no published ceiling invented


def iter_chebi_compounds(zip_path):
    """Stream compounds from the ChEBI FULL JSON archive (.json or .json.gz)."""
    with zipfile.ZipFile(zip_path) as archive:
        member = archive.namelist()[0]
        with archive.open(member) as handle:
            raw = handle.read()
    if member.endswith(".gz"):
        raw = gzip.decompress(raw)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise SourceContractError("ChEBI FULL JSON is malformed") from None
    compounds = payload if isinstance(payload, list) else payload.get("compounds", [])
    for compound in compounds:
        if not isinstance(compound, dict) or not compound.get("chebiId"):
            continue
        yield compound


def compound_summary(compound):
    """Normalized view of one ChEBI compound."""
    xrefs = {}
    for reference in compound.get("crossReferences", []) or []:
        source = reference.get("dataSource", "")
        value = reference.get("referenceId", "")
        if source and value:
            xrefs.setdefault(source, []).append(value)
    return {
        "chebi_id": str(compound["chebiId"]),
        "name": compound.get("name", ""),
        "inchikey": compound.get("inchiKey"),
        "synonyms": [synonym.get("name", "") for synonym in compound.get("synonyms", []) or []],
        "parents": [
            relation.get("targetChebiId")
            for relation in compound.get("ontologyParents", []) or []
            if relation.get("targetChebiId")
        ],
        "xrefs": xrefs,
    }


def bridge_to_ing(builder, repository, compounds, *, crosswalk_system="UNII"):
    """Exact curated cross-references only; distinctions preserved.

    A compound bridges to an existing KMX-ING when one of its curated
    cross-references resolves exactly; otherwise it may mint an ingredient
    only under the lane authorization. Stereo/isotope/salt siblings never
    merge: each ChEBI compound keeps its own identity.
    """
    from kmx.normalizer import normalize_name

    stats = {"seen": 0, "bridged": 0, "created": 0, "reused": 0, "unresolved": 0}
    for compound in compounds:
        summary = compound_summary(compound)
        stats["seen"] += 1
        identifiers = [("CHEBI", summary["chebi_id"])]
        for value in sorted(set(summary["xrefs"].get(crosswalk_system, []))):
            identifiers.append((crosswalk_system, value))
        built = builder.build_ingredient(
            lane_id="S04",
            source_id="chebi_unichem",
            allowed_levels=("ingredient",),
            preferred_name=summary["name"] or summary["chebi_id"],
            normalized_name=normalize_name(summary["name"] or summary["chebi_id"]),
            identifiers=identifiers,
        )
        if not built.created:
            # Enrichment into the existing identity: the curated
            # cross-references proven consistent by the exact resolution
            # attach to the reused KMX when not yet bound.
            for system, value in identifiers:
                bound = repository.external_bindings(system, value)
                if not any(binding.kmx_id == built.kmx_id for binding in bound):
                    repository.insert_external_identifier(
                        kmx_id=built.kmx_id,
                        identifier_system=system,
                        identifier_value=value,
                        source_id="chebi_unichem",
                    )
        if built.created:
            stats["created"] += 1
        else:
            stats["bridged"] += 1
            stats["reused"] += 1
    return stats


class UniChemConnectivity:
    """A UniChem connectivity lookup result. NOT an identity assertion.

    Connectivity similarity must never silently become exact identity; this
    type exists so callers can see the difference statically.
    """


def unichem_sources_url():
    return f"{UNICHEM_BASE}/v1/sources/"


def unichem_source_url(srcid):
    return f"{UNICHEM_BASE}/v1/sources/{quote(str(srcid), safe='')}"


def unichem_compounds_request(src_id, src_compound_id):
    """The POST /compounds request payload for exact source lookups."""
    return {"src_id": str(src_id), "src_compound_id": str(src_compound_id)}


def unichem_connectivity_request(src_id, src_compound_id):
    """The POST /connectivity payload. Results are similarity, not identity."""
    return {"type": "connectivity", "src_id": str(src_id), "src_compound_id": str(src_compound_id)}


def make_unichem_client():
    from ..http import SourceHttpClient

    return SourceHttpClient(
        source_id="chebi_unichem",
        requests_per_second=UNICHEM_REQUESTS_PER_SECOND,
        policy_host="www.ebi.ac.uk",
    )
