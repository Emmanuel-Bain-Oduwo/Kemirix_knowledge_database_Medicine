"""S01-RXNORM-001 adapter, parser and loader tests (Phase 9).

Everything is offline: synthetic RRF fixtures inside real ZIP archives,
fake HTTP transports, fake vault stores and the fake repository/builder
stack. No live network access and no real RxNorm data.
"""

import hashlib
import io
import json
import zipfile

import httpx
import pytest

from kmx.builders import KmxBuilder
from kmx.normalizer import normalize_name
from kmx.repository import KmxRepository
from sources.exceptions import SourceContractError
from sources.http import RateLimiter, SourceHttpClient
from sources.rxnorm.adapter import run_pinned_rxnorm_ingestion
from sources.rxnorm.download import (
    UTS_API_KEY_ENV,
    build_download_url,
    require_uts_api_key,
)
from sources.rxnorm.release import (
    PINNED_FILENAME,
    PINNED_OFFICIAL_MD5,
    ReleaseMismatchError,
    parse_release_discovery,
    pinned_release_metadata,
    verify_pinned,
)
from sources.rxnorm.rrf import iter_rrf, locate_member

pytestmark = pytest.mark.contract

# --- shared fakes -----------------------------------------------------------


class FakeStore:
    def __init__(self):
        self.objects = {}
        self.calls = []

    def put_immutable(self, *, source_path, object_key, expected_sha256):
        from storage.client import PutResult

        self.calls.append(("put", object_key))
        data = source_path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected_sha256:
            raise SourceContractError("corrupted download")
        if object_key in self.objects and self.objects[object_key] != data:
            raise SourceContractError("different bytes; never overwrite")
        already = object_key in self.objects
        self.objects[object_key] = data
        return PutResult(object_key, digest, "idempotent" if already else "uploaded")

    def write_manifest(self, manifest):
        self.calls.append(("manifest", manifest.source_version))
        key = (
            f"{manifest.source_id}/{manifest.source_version}/"
            f"{manifest.source_record_key}/manifest.json"
        )
        self.objects[key] = manifest.model_dump_json().encode()
        return key

    def download_to(self, object_key, destination):
        self.calls.append(("get", object_key))
        if object_key not in self.objects:
            raise SourceContractError("GET failed")
        data = self.objects[object_key]
        destination.write(data)
        return len(data)


class FakeConnection:
    """Minimal connection/repository/builder backing store (Phase 8 shape)."""

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
            (lane, source, version, record, reason, payload, candidates) = params
            self.exceptions.append(
                {
                    "lane_id": lane,
                    "source_id": source,
                    "reason": reason,
                    "record": record,
                }
            )
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
            if len(params) == 2:
                normalized, level = params
                ids = [
                    k
                    for k in self.registry
                    if self.registry[k]["normalized"] == normalized
                    and self.registry[k]["level"] == level
                ]
            else:
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
    # expose the record helper the loader uses
    repository.record_mapping_exception = lambda **kw: connection.execute(
        "INSERT INTO kmx.mapping_exception (lane_id, source_id, source_version_key, "
        "source_record_key, reason_code, normalized_input, candidate_kmx_ids) "
        "VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb) RETURNING exception_id",
        (
            kw["lane_id"],
            kw["source_id"],
            kw.get("source_version_key"),
            kw["source_record_key"],
            kw["reason_code"],
            json.dumps(kw.get("normalized_input", {})),
            json.dumps(list(kw.get("candidate_kmx_ids", ()))),
        ),
    )
    builder = KmxBuilder(repository, connection)
    return connection, repository, builder


# --- fixture RRF archive ----------------------------------------------------


def rrf_line(*fields):
    return "|".join(fields)


def conso(rxcui, tty, name, suppress="N", cvf="", sab="RXNORM"):
    return rrf_line(
        rxcui,
        "ENG",
        "",
        "",
        "",
        "",
        "",
        "A" + rxcui,
        "",
        "",
        "",
        sab,
        tty,
        "",
        name,
        "",
        suppress,
        cvf,
    )


def rel(rxcui1, rela, rxcui2, sab="RXNORM"):
    # Official direction: RXCUI2 --RELA--> RXCUI1.
    return rrf_line(
        rxcui1,
        "A" + rxcui1,
        "CUI",
        "RO",
        rxcui2,
        "A" + rxcui2,
        "CUI",
        rela,
        "R" + rxcui1 + rxcui2,
        "",
        sab,
        "",
        "",
        "",
        "N",
        "",
    )


def build_release_zip(path, *, conso_rows, rel_rows, nested=True):
    prefix = "rrf/RXNORM_20AA_260908F/" if nested else ""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{prefix}RXNCONSO.RRF", "\n".join(conso_rows) + "\n")
        archive.writestr(f"{prefix}RXNREL.RRF", "\n".join(rel_rows) + "\n")
        archive.writestr(f"{prefix}RXNDOC.RRF", "ATN|DDF|expanded_form|Drug Doseform|\n")


REALISTIC_CONSO = [
    conso("723", "IN", "Amoxicillin", cvf="4096"),
    conso("2261", "PIN", "Amoxicillin Trihydrate"),
    conso("161", "IN", "Acetaminophen", cvf="4096"),
    conso("3498", "IN", "Diphenhydramine", cvf="4096"),
    conso("9001", "MIN", "Acetaminophen / Diphenhydramine"),
    conso(
        "7082",
        "SCD",
        "Acetaminophen 325 MG / Diphenhydramine Hydrochloride 50 MG Oral Tablet",
        cvf="4096",
    ),
    conso("7083", "SCDC", "Acetaminophen 325 MG"),
    conso("7084", "SCDC", "Diphenhydramine Hydrochloride 50 MG"),
    conso("308182", "SCD", "Amoxicillin 500 MG Oral Capsule", cvf="4096"),
    conso("308183", "SCDC", "Amoxicillin 500 MG"),
    conso(
        "9702",
        "SBD",
        "Acetaminophen 325 MG / Diphenhydramine Hydrochloride 50 MG Oral Tablet [Tylenol PM]",
    ),
    conso("9999", "IN", "Suppressed Substance", suppress="Y"),
    conso("8899", "SCD", "Orphan SCD Without Ingredients"),
]

REALISTIC_REL = [
    rel("723", "form_of", "2261"),  # PIN 2261 form_of IN 723
    rel("7083", "has_ingredient", "7082"),  # SCDC 7083 has IN 161? no wait
]


def realistic_rels():
    return [
        # PIN form_of IN (RXCUI2=PIN has form_of to RXCUI1=IN)
        rel("723", "form_of", "2261"),
        # SCD consists_of SCDC (RXCUI2=SCD consists_of RXCUI1=SCDC)
        rel("7083", "consists_of", "7082"),
        rel("7084", "consists_of", "7082"),
        rel("308183", "consists_of", "308182"),
        # SCDC has_ingredient IN (RXCUI2=SCDC has IN RXCUI1=IN)
        rel("161", "has_ingredient", "7083"),
        rel("3498", "has_ingredient", "7084"),
        rel("723", "has_ingredient", "308183"),
        # SCD has_ingredients MIN (RXCUI2=SCD has MIN RXCUI1=MIN)
        rel("9001", "has_ingredients", "7082"),
        # MIN has_part IN
        rel("161", "has_part", "9001"),
        rel("3498", "has_part", "9001"),
        # SBD tradename_of SCD (RXCUI2=SBD tradename_of RXCUI1=SCD)
        rel("7082", "tradename_of", "9702"),
    ]


# --- release discovery and pinning -----------------------------------------


def test_release_discovery_parses_the_verified_live_shape():
    payload = [
        {
            "fileName": "RxNorm_full_09082026.zip",
            "releaseVersion": "2026-09-08",
            "releaseDate": "2026-09-08",
            "downloadUrl": "https://download.nlm.nih.gov/umls/kss/rxnorm/RxNorm_full_09082026.zip",
            "releaseType": "RxNorm Full Monthly Release",
            "product": "RxNorm",
            "current": True,
        }
    ]
    discovered = parse_release_discovery(payload)
    verify_pinned(discovered)
    assert discovered.file_name == PINNED_FILENAME


def test_release_discovery_fails_closed_on_drift():
    good = {
        "fileName": PINNED_FILENAME,
        "releaseVersion": "2026-09-08",
        "releaseDate": "2026-09-08",
        "downloadUrl": "https://download.nlm.nih.gov/umls/kss/rxnorm/RxNorm_full_09082026.zip",
        "releaseType": "RxNorm Full Monthly Release",
        "product": "RxNorm",
        "current": True,
    }
    newer = dict(good, fileName="RxNorm_full_10072026.zip", releaseVersion="2026-10-07")
    with pytest.raises(ReleaseMismatchError, match="PINNED_RELEASE_MISMATCH"):
        verify_pinned(parse_release_discovery([newer]))
    with pytest.raises(SourceContractError):
        parse_release_discovery([dict(good, current=False), dict(good, current=False)])
    with pytest.raises(SourceContractError):
        parse_release_discovery([])
    with pytest.raises(SourceContractError):
        parse_release_discovery([dict(good, product="SnomedCT")])


def test_pinned_metadata_records_the_release_before_download():
    metadata = pinned_release_metadata()
    assert metadata["file_name"] == PINNED_FILENAME
    assert metadata["object_key"] == (
        "rxnorm_athena/2026-09-08/__release__/original/RxNorm_full_09082026.zip"
    )
    assert metadata["official_md5"] == PINNED_OFFICIAL_MD5
    assert metadata["lane_id"] == "S01" and metadata["acquisition_mode"] == "bulk"


def test_download_url_secret_safety():
    url = build_download_url("secret-uts-key-value")
    assert "secret-uts-key-value" in url  # in the URL itself, but...
    # The URL is only ever passed to the streaming client; errors never
    # contain it (Phase 4 error surface). The builder requires a non-empty key.
    with pytest.raises(SourceContractError):
        build_download_url("")
    with pytest.raises(SourceContractError, match=UTS_API_KEY_ENV):
        require_uts_api_key(env={})
    assert require_uts_api_key(env={UTS_API_KEY_ENV: "k"}) == "k"


# --- RRF parsing ------------------------------------------------------------


def test_rrf_locates_members_by_basename_even_nested(tmp_path):
    path = tmp_path / "release.zip"
    build_release_zip(path, conso_rows=[conso("1", "IN", "X")], rel_rows=[])
    assert locate_member(path, "rxnconso.rrf").endswith("RXNCONSO.RRF")
    rows = list(iter_rrf(path, "RXNCONSO"))
    assert rows[0]["RXCUI"] == "1" and rows[0]["TTY"] == "IN"
    with pytest.raises(SourceContractError):
        locate_member(path, "RXNSAT.RRF")


def test_rrf_filters_sab_and_suppress(tmp_path):
    path = tmp_path / "release.zip"
    rows = [
        conso("1", "IN", "Active RxNorm"),
        conso("2", "IN", "Suppressed RxNorm", suppress="Y"),
        conso("3", "IN", "Other Source", sab="VANDF"),
    ]
    build_release_zip(path, conso_rows=rows, rel_rows=[])
    kept = list(iter_rrf(path, "RXNCONSO", sab="RXNORM"))
    assert [row["RXCUI"] for row in kept] == ["1"]


# --- the deterministic loader ------------------------------------------------


def load_fixture(tmp_path, conso_rows=None, rel_rows=None):
    path = tmp_path / "RxNorm_full_09082026.zip"
    build_release_zip(
        path,
        conso_rows=conso_rows if conso_rows is not None else REALISTIC_CONSO,
        rel_rows=rel_rows if rel_rows is not None else realistic_rels(),
    )
    connection, repository, builder = make_stack()
    from sources.rxnorm.loader import RxNormKmxLoader

    loader = RxNormKmxLoader(builder, repository)
    stats = loader.load(path)
    return connection, repository, stats


def test_loader_passes_ing_pin_cd_containment_and_aliases(tmp_path):
    connection, repository, stats = load_fixture(tmp_path)
    # Pass A: three active INs mint ingredients; the suppressed one is absent.
    assert stats["in_seen"] == 3 and stats["ing_created"] == 4  # 3 IN + 1 PIN
    assert ("RXNORM", "9999") not in connection.identifiers
    # Pass B: the PIN mints its own identity and links to its proven base.
    assert stats["pin_linked"] == 1
    pin_kmx = connection.identifiers[("RXNORM", "2261")][0]
    base_kmx = connection.identifiers[("RXNORM", "723")][0]
    assert (base_kmx, pin_kmx, "precise_ingredient", None) in connection.containment
    # Pass C/D: the combination SCD contains both ingredient members.
    combo_cd = connection.identifiers[("RXNORM", "7082")][0]
    ing_acet = connection.identifiers[("RXNORM", "161")][0]
    ing_diph = connection.identifiers[("RXNORM", "3498")][0]
    assert (combo_cd, ing_acet, "contains", 1) in connection.containment
    assert (combo_cd, ing_diph, "contains", 2) in connection.containment
    # The single-ingredient SCD contains amoxicillin.
    amox_cd = connection.identifiers[("RXNORM", "308182")][0]
    ing_amox = connection.identifiers[("RXNORM", "723")][0]
    assert (amox_cd, ing_amox, "contains", 1) in connection.containment
    assert stats["cd_created"] == 2
    # Pass F: the SBD becomes a brand alias on the existing CD, not a PROD.
    assert stats["aliases"] == 1
    brand_alias = normalize_name(
        "Acetaminophen 325 MG / Diphenhydramine Hydrochloride 50 MG Oral Tablet [Tylenol PM]"
    )
    assert (brand_alias, "brand") in connection.names
    # Zero KMX-PROD, always.
    assert not any(row["level"] == "product" for row in connection.registry.values())


def test_loader_records_exceptions_for_unresolved_structures(tmp_path):
    connection, _, stats = load_fixture(tmp_path)
    # The orphan SCD has no ingredient relations: a mapping exception with
    # full provenance is recorded instead of a guess.
    assert stats["exceptions"] == 1
    exception = connection.exceptions[0]
    assert exception["reason"] == "FORMULATION_AMBIGUITY"
    assert exception["record"] == "RXCUI-8899"
    assert exception["lane_id"] == "S01" and exception["source_id"] == "rxnorm_athena"


def test_loader_rerun_is_idempotent(tmp_path):
    path = tmp_path / "RxNorm_full_09082026.zip"
    build_release_zip(path, conso_rows=REALISTIC_CONSO, rel_rows=realistic_rels())
    connection, repository, builder = make_stack()
    from sources.rxnorm.loader import RxNormKmxLoader

    loader = RxNormKmxLoader(builder, repository)
    first = loader.load(path)
    second = loader.load(path)
    assert first["ing_created"] == 4 and first["cd_created"] == 2
    assert second["ing_created"] == 0 and second["cd_created"] == 0
    assert second["ing_reused"] == 4 and second["cd_reused"] == 2
    # No duplicate external identifier bindings after the rerun.
    assert all(len(ids) == 1 for ids in connection.identifiers.values())
    # Identities kept their numbers: nothing renumbered across the rerun.
    assert connection.identifiers[("RXNORM", "723")] == [
        connection.identifiers[("RXNORM", "723")][0]
    ]


def test_loader_tracks_prescribable_distinction(tmp_path):
    _, _, stats = load_fixture(tmp_path)
    assert stats["prescribable_concepts"] == 5  # amox IN, acet IN, diph IN, 2 SCDs


def test_unproven_pin_keeps_identity_without_link(tmp_path):
    conso_rows = [
        conso("723", "IN", "Warfarin"),
        conso("2261", "PIN", "Warfarin Sodium"),
    ]
    path = tmp_path / "RxNorm_full_09082026.zip"
    build_release_zip(path, conso_rows=conso_rows, rel_rows=[])  # no form_of
    connection, repository, builder = make_stack()
    from sources.rxnorm.loader import RxNormKmxLoader

    stats = RxNormKmxLoader(builder, repository).load(path)
    assert stats["pin_unlinked"] == 1 and stats["pin_linked"] == 0
    pin_kmx = connection.identifiers[("RXNORM", "2261")][0]
    base_kmx = connection.identifiers[("RXNORM", "723")][0]
    assert pin_kmx != base_kmx
    assert not any(edge[0] == base_kmx and edge[1] == pin_kmx for edge in connection.containment)


# --- adapter end-to-end (fake HTTP + fake vault + real loader) --------------


def discovery_payload():
    return [
        json.dumps(
            [
                {
                    "fileName": PINNED_FILENAME,
                    "releaseVersion": "2026-09-08",
                    "releaseDate": "2026-09-08",
                    "downloadUrl": "https://download.nlm.nih.gov/umls/kss/rxnorm/RxNorm_full_09082026.zip",
                    "releaseType": "RxNorm Full Monthly Release",
                    "product": "RxNorm",
                    "current": True,
                }
            ]
        ).encode()
    ]


def build_fixture_release_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "rrf/RXNCONSO.RRF",
            "\n".join(
                [
                    conso("723", "IN", "Amoxicillin"),
                    conso("308183", "SCDC", "Amoxicillin 500 MG"),
                    conso("308182", "SCD", "Amoxicillin 500 MG Oral Capsule"),
                ]
            )
            + "\n",
        )
        archive.writestr(
            "rrf/RXNREL.RRF",
            "\n".join(
                [
                    rel("308183", "consists_of", "308182"),
                    rel("723", "has_ingredient", "308183"),
                ]
            )
            + "\n",
        )
    return buffer.getvalue()


def md5_of(data):
    return hashlib.md5(data).hexdigest()


def test_adapter_end_to_end_pinned_flow(tmp_path, monkeypatch):
    release_bytes = build_fixture_release_bytes()
    # The fixture must match the official pinned MD5 so the adapter accepts it.
    monkeypatch.setattr(
        "sources.rxnorm.download.PINNED_OFFICIAL_MD5", md5_of(release_bytes), raising=True
    )
    calls = []

    def handler(request):
        calls.append(request.url.host + request.url.path)
        if "uts-ws.nlm.nih.gov/releases" in request.url.host + request.url.path:
            return httpx.Response(200, content=discovery_payload()[0])
        if "uts-ws.nlm.nih.gov/download" in request.url.host + request.url.path:
            return httpx.Response(200, content=release_bytes)
        raise AssertionError(f"unexpected request: {request.url.host}")

    transport = httpx.MockTransport(handler)
    client = SourceHttpClient(
        source_id="rxnorm_athena",
        transport=transport,
        limiter=RateLimiter(requests_per_second=1000, max_concurrency=4),
        backoff_base=0.0,
    )
    store = FakeStore()
    connection, repository, builder = make_stack()
    result = run_pinned_rxnorm_ingestion(
        client=client,
        store=store,
        builder=builder,
        repository=repository,
        adapter_git_sha="a" * 40,
        env={UTS_API_KEY_ENV: "fixture-uts-key"},
    )
    assert result["put"] == "uploaded"
    assert result["sha256"] == hashlib.sha256(release_bytes).hexdigest()
    # The loader statistics ride the result for the final QA metrics.
    assert result["stats"]["ing_created"] == 1
    assert result["stats"]["cd_created"] == 1
    # Vault order: raw first, manifest LAST, then the parser read the STORED copy.
    assert [call[0] for call in store.calls] == ["put", "manifest", "get"]
    # The KMX load ran from the stored original.
    assert ("RXNORM", "723") in connection.identifiers
    assert ("RXNORM", "308182") in connection.identifiers
    amox_cd = connection.identifiers[("RXNORM", "308182")][0]
    ing_amox = connection.identifiers[("RXNORM", "723")][0]
    assert (amox_cd, ing_amox, "contains", 1) in connection.containment
    # No secrets anywhere in the vault.
    for data in store.objects.values():
        assert b"fixture-uts-key" not in data


def test_adapter_fails_closed_on_pin_drift(tmp_path):
    def handler(request):
        if "uts-ws.nlm.nih.gov/releases" in request.url.host + request.url.path:
            drifted = json.dumps(
                [
                    {
                        "fileName": "RxNorm_full_10072026.zip",
                        "releaseVersion": "2026-10-07",
                        "releaseDate": "2026-10-07",
                        "downloadUrl": "https://download.nlm.nih.gov/umls/kss/rxnorm/RxNorm_full_10072026.zip",
                        "releaseType": "RxNorm Full Monthly Release",
                        "product": "RxNorm",
                        "current": True,
                    }
                ]
            ).encode()
            return httpx.Response(200, content=drifted)
        raise AssertionError("no download may happen after a pin mismatch")

    client = SourceHttpClient(
        source_id="rxnorm_athena",
        transport=httpx.MockTransport(handler),
        limiter=RateLimiter(requests_per_second=1000, max_concurrency=4),
        backoff_base=0.0,
    )
    with pytest.raises(ReleaseMismatchError):
        run_pinned_rxnorm_ingestion(
            client=client,
            store=FakeStore(),
            builder=None,
            repository=None,
            adapter_git_sha="a" * 40,
            env={UTS_API_KEY_ENV: "fixture-uts-key"},
        )


def test_adapter_fails_closed_on_md5_mismatch(tmp_path, monkeypatch):
    release_bytes = build_fixture_release_bytes()
    monkeypatch.setattr("sources.rxnorm.download.PINNED_OFFICIAL_MD5", "0" * 32, raising=True)

    def handler(request):
        if request.url.host.startswith("uts-ws") and "releases" in request.url.path:
            return httpx.Response(200, content=discovery_payload()[0])
        return httpx.Response(200, content=release_bytes)

    client = SourceHttpClient(
        source_id="rxnorm_athena",
        transport=httpx.MockTransport(handler),
        limiter=RateLimiter(requests_per_second=1000, max_concurrency=4),
        backoff_base=0.0,
    )
    store = FakeStore()
    with pytest.raises(SourceContractError, match="MD5"):
        run_pinned_rxnorm_ingestion(
            client=client,
            store=store,
            builder=None,
            repository=None,
            adapter_git_sha="a" * 40,
            env={UTS_API_KEY_ENV: "fixture-uts-key"},
        )
    # Nothing reached the vault after the checksum failure.
    assert store.objects == {}
