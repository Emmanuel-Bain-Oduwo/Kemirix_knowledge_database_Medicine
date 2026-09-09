"""S05 medrt: dynamic paired-release discovery and association parsing.

MED-RT publishes paired archives on the official NCI FTP mirror; the
newest approved pair (Core_MEDRT_<release>_XML.zip plus its Accessory
archive) is discovered dynamically from the directory index — no release
date is hardcoded. Associations attach to existing KMX only through exact
RxNorm crosswalks; MED-RT has no prescribing authority.
"""

import re
import zipfile

from ..exceptions import SourceContractError

ARCHIVE_ROOT = "https://evs.nci.nih.gov/ftp1/MED-RT/Archive/"
CORE_PATTERN = re.compile(r"Core_MEDRT_(\d{6}(?:_\d+)?)_XML\.zip", re.IGNORECASE)
ACCESSORY_PATTERN = re.compile(r"Core_MEDRT_(\d{6}(?:_\d+)?)_Accessory_Files\.zip", re.IGNORECASE)


def discover_paired_releases(index_html):
    """All paired releases found in the archive index, newest first.

    A pair is complete only when both the Core XML archive and its matching
    Accessory archive are listed. Callers pin the newest approved pair —
    the discovery itself never hardcodes a release date.
    """
    cores = {}
    accessories = {}
    for match in re.finditer(r'href="([^"]+)"', index_html or ""):
        name = match.group(1).rsplit("/", 1)[-1]
        core = CORE_PATTERN.search(name)
        accessory = ACCESSORY_PATTERN.search(name)
        if core:
            cores.setdefault(core.group(1), name)
        elif accessory:
            accessories.setdefault(accessory.group(1), name)
    pairs = []
    for release in sorted(set(cores) & set(accessories), reverse=True):
        pairs.append(
            {
                "release": release,
                "core_archive": cores[release],
                "accessory_archive": accessories[release],
            }
        )
    return pairs


def newest_pair(index_html):
    """The newest paired release, or fail closed."""
    pairs = discover_paired_releases(index_html)
    if not pairs:
        raise SourceContractError("no complete MED-RT paired release found")
    return pairs[0]


def iter_associations(core_xml_path):
    """Stream (from_code, association, to_code) from the core XML.

    MED-RT core XML lists concepts and their role/association links; codes
    are preserved exactly as published.
    """
    import xml.etree.ElementTree as ET

    tree = ET.parse(core_xml_path)
    for association in tree.iter("association"):
        from_code = association.get("fromCode") or ""
        association_name = association.get("name") or association.get("role") or ""
        to_code = association.get("toCode") or ""
        if from_code and association_name and to_code:
            yield {
                "from_code": from_code,
                "association": association_name,
                "to_code": to_code,
            }


def parse_crosswalk(accessory_zip_path):
    """Code to RXCUI crosswalk from the accessory archive (exact only)."""
    crosswalk = {}
    with zipfile.ZipFile(accessory_zip_path) as archive:
        for name in archive.namelist():
            if not name.lower().endswith(".csv"):
                continue
            import csv
            import io

            with archive.open(name) as handle:
                text = io.TextIOWrapper(handle, encoding="utf-8-sig")
                for row in csv.DictReader(text):
                    code = (row.get("code") or row.get("MEDRT_CODE") or "").strip()
                    rxcui = (row.get("rxcui") or row.get("RXCUI") or "").strip()
                    if code and rxcui:
                        crosswalk[code] = rxcui
    return crosswalk


def attach_via_crosswalk(repository, associations, crosswalk, *, source_id="medrt"):
    """Attach MED-RT metadata to existing KMX through exact crosswalks.

    Only associations whose concept codes carry an exact RXCUI crosswalk
    resolve; everything else is skipped (recorded as unresolved), never
    guessed. No prescribing authority exists here.
    """
    stats = {"associations": 0, "resolved": 0, "unresolved": 0}
    for association in associations:
        stats["associations"] += 1
        from_rxcui = crosswalk.get(association["from_code"])
        to_rxcui = crosswalk.get(association["to_code"])
        if not from_rxcui or not to_rxcui:
            stats["unresolved"] += 1
            continue
        from_bindings = repository.external_bindings("RXNORM", from_rxcui)
        to_bindings = repository.external_bindings("RXNORM", to_rxcui)
        if len(from_bindings) != 1 or len(to_bindings) != 1:
            stats["unresolved"] += 1
            continue
        if repository.existing_containment(
            container_kmx_id=from_bindings[0].kmx_id,
            member_kmx_id=to_bindings[0].kmx_id,
            relationship_type=f"medrt:{association['association']}",
        ):
            continue
        repository.insert_containment(
            container_kmx_id=from_bindings[0].kmx_id,
            member_kmx_id=to_bindings[0].kmx_id,
            relationship_type=f"medrt:{association['association']}",
            ordinal=None,
        )
        stats["resolved"] += 1
    return stats
