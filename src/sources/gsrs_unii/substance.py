"""S03 gsrs_unii: bulk snapshot parsing, exact UNII resolution and the
openFDA substance canary client.

The production bulk mode is the complete zipped JSON snapshot from the
official openFDA downloads catalogue (operator-provided in this program;
no live S02-S05 downloads). Base/salt relationships are preserved through
precise-ingredient containment and NEVER merged by name. The canary client
verifies a single UNII against api.fda.gov/other/substance.json with a
conservative 3 rps ceiling far below the published limits, honoring 429.
"""

import io
import json
import zipfile

from ..exceptions import SourceContractError

CANARY_URL = "https://api.fda.gov/other/substance.json"
CANARY_REQUESTS_PER_SECOND = 3.0
OPENFDA_OFFICIAL_LIMITS = {
    "no_key_per_minute": 240,
    "no_key_per_day": 1000,
    "with_key_per_minute": 240,
    "with_key_per_day": 120000,
}


def iter_substances(zip_path):
    """Stream substance records from the bulk zipped JSON snapshot.

    Each record carries its UNII, preferred name, substance class and any
    parent (base) UNIIs; structure is preserved, nothing is merged.
    """
    with zipfile.ZipFile(zip_path) as archive:
        member = archive.namelist()[0]
        with archive.open(member) as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8")
            payload = json.load(text)
    records = payload.get("results", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise SourceContractError("bulk snapshot must be a JSON list of substances")
    for record in records:
        if not isinstance(record, dict) or not record.get("unii"):
            continue
        parents = []
        for relationship in record.get("relationships", []) or []:
            associated = relationship.get("associated_substance", {}) or {}
            if relationship.get("type") == "has_parent" and associated.get("unii"):
                parents.append(associated["unii"])
        yield {
            "unii": record["unii"],
            "preferred_name": record.get("preferred_name", ""),
            "substance_class": record.get("substance_class", ""),
            "parents": parents,
        }


def resolve_unii_to_ing(builder, repository, substances, *, lane_id="S03", source_id="gsrs_unii"):
    """Exact UNII to KMX-ING with base/salt preservation.

    A UNII that does not resolve may mint an ingredient only because the
    lane's frozen kmx_levels contract authorizes the ingredient level;
    parent (base) UNIIs associate through the proven precise-ingredient
    containment exactly like RxNorm PINs. Name similarity never plays a
    role.
    """
    from kmx.normalizer import normalize_name

    stats = {"seen": 0, "created": 0, "reused": 0, "parent_links": 0}
    resolved = {}
    for substance in substances:
        stats["seen"] += 1
        unii = substance["unii"]
        name = substance["preferred_name"] or unii
        built = builder.build_ingredient(
            lane_id=lane_id,
            source_id=source_id,
            allowed_levels=("ingredient",),
            preferred_name=name,
            normalized_name=normalize_name(name),
            identifiers=[("UNII", unii)],
        )
        stats["created" if built.created else "reused"] += 1
        resolved[unii] = built.kmx_id
    for substance in substances:
        for parent_unii in substance["parents"]:
            parent_kmx = resolved.get(parent_unii)
            child_kmx = resolved.get(substance["unii"])
            if not parent_kmx or not child_kmx or parent_kmx == child_kmx:
                continue
            if repository.existing_containment(
                container_kmx_id=parent_kmx,
                member_kmx_id=child_kmx,
                relationship_type="precise_ingredient",
            ):
                continue
            repository.insert_containment(
                container_kmx_id=parent_kmx,
                member_kmx_id=child_kmx,
                relationship_type="precise_ingredient",
                ordinal=None,
            )
            stats["parent_links"] += 1
    return stats


def canary_url(unii):
    """The verification URL for one UNII."""
    if not unii or not isinstance(unii, str) or '"' in unii:
        raise SourceContractError("a single UNII value is required")
    return f'{CANARY_URL}?search=unii:"{unii}"'


def make_canary_client():
    """The conservative openFDA verification client (3 rps ceiling)."""
    from ..http import SourceHttpClient

    return SourceHttpClient(
        source_id="gsrs_unii",
        requests_per_second=CANARY_REQUESTS_PER_SECOND,
        policy_host="api.fda.gov",
    )


def verify_unii_canary(client, unii, destination):
    """Stream one canary verification response (offline tests fake this)."""
    return client.get_to_file(canary_url(unii), destination)


def parse_canary_result(payload_text):
    """Parse the canary response; None when the UNII is absent upstream."""
    try:
        payload = json.loads(payload_text)
    except ValueError:
        raise SourceContractError("canary response is not JSON") from None
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list) or not results:
        return None
    first = results[0]
    return {"unii": first.get("unii"), "preferred_name": first.get("preferred_name", "")}
