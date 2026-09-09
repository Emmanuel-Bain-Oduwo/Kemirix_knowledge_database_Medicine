"""INGESTION-CORE-001 shared acquisition framework tests (Phase 4).

Everything is offline: httpx MockTransport, fake stores and injected
sleep/clock functions. No live source is contacted and no real bucket is
touched, exactly as the owner directive requires.
"""

import hashlib
import io
import pathlib
import threading

import httpx
import pytest

from sources.acquisition import (
    acquire_file_to_vault,
    acquire_url_to_vault,
    parse_stored_original,
)
from sources.base import SourceAdapter
from sources.config import load_source_configs
from sources.exceptions import SourceContractError
from sources.http import (
    NLM_RPS_CEILING,
    HttpAcquisitionError,
    RateLimiter,
    SourceHttpClient,
    rate_policy,
)
from sources.results import AcquisitionResult
from storage.exceptions import StorageContractError

pytestmark = pytest.mark.contract

ROOT_LIKE = None  # load via the real config tree below


def handler(*responses):
    """MockTransport handler serving the scripted responses in order."""
    calls = []
    lock = threading.Lock()

    def route(request):
        with lock:
            calls.append(request)
        status, headers, body = responses[len(calls) - 1]
        return httpx.Response(status, headers=headers, content=body)

    return httpx.MockTransport(route), calls


class FakeStore:
    """In-process vault recording every operation in order."""

    def __init__(self, objects=None):
        self.objects = dict(objects or {})
        self.calls = []

    def put_immutable(self, *, source_path, object_key, expected_sha256):
        self.calls.append(("put", object_key))
        data = source_path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected_sha256:
            raise StorageContractError("corrupted download rejected")
        if object_key in self.objects and self.objects[object_key] != data:
            raise StorageContractError("different bytes; never overwrite")
        self.objects[object_key] = data
        return object_key

    def write_manifest(self, manifest):
        self.calls.append(("manifest", manifest.source_record_key))
        key = (
            f"{manifest.source_id}/{manifest.source_version}/"
            f"{manifest.source_record_key}/manifest.json"
        )
        payload = manifest.model_dump_json().encode()
        if key in self.objects and self.objects[key] != payload:
            raise StorageContractError("never rewrite a manifest")
        self.objects[key] = payload
        return key

    def download_to(self, object_key, destination):
        self.calls.append(("get", object_key))
        if object_key not in self.objects:
            raise StorageContractError("GET failed (ClientError)")
        data = self.objects[object_key]
        destination.write(data)
        return len(data)


IDENTITY = {
    "lane_id": "S06",
    "source_id": "dailymed",
    "source_version": "v1",
    "source_record_key": "setid-1",
}


def make_client(transport, **kwargs):
    kwargs.setdefault("source_id", "dailymed")
    kwargs.setdefault("backoff_base", 0.0)
    kwargs.setdefault("limiter", RateLimiter(requests_per_second=1000, max_concurrency=4))
    return SourceHttpClient(transport=transport, **kwargs)


def test_success_200_vaults_raw_then_manifest(tmp_path):
    transport, calls = handler(*[(200, {"content-type": "application/xml"}, b"<spl/>")])
    store = FakeStore()
    client = make_client(transport)
    result = acquire_url_to_vault(
        client=client,
        store=store,
        url="https://example.invalid/label.xml",
        lane_id="S06",
        source_id="dailymed",
        source_version="v1",
        source_record_key="setid-1",
        original_filename="label.xml",
        content_type="application/xml",
        adapter_git_sha="a" * 40,
        rights_status="cleared",
    )
    assert result.status == "succeeded"
    assert result.artifact_keys == ("dailymed/v1/setid-1/original/label.xml",)
    assert result.manifest_key == "dailymed/v1/setid-1/manifest.json"
    assert result.attempts == 1 and result.http_status == 200
    # Vault order: raw first, manifest LAST.
    assert store.calls == [
        ("put", "dailymed/v1/setid-1/original/label.xml"),
        ("manifest", "setid-1"),
    ]
    # The stored manifest validates against the frozen model and carries the
    # exact artifact lineage and hash.
    from storage.manifest import Manifest

    manifest = Manifest.model_validate_json(store.objects["dailymed/v1/setid-1/manifest.json"])
    assert manifest.artifacts[0].sha256 == hashlib.sha256(b"<spl/>").hexdigest()
    assert manifest.rights_status == "cleared"
    assert manifest.parse_status == "staged"


def test_rate_limited_429_retries_with_retry_after_then_succeeds():
    transport, calls = handler(
        (429, {"retry-after": "0"}, b""),
        (200, {}, b"second try"),
    )
    sleeps = []
    client = make_client(transport, sleep=sleeps.append)
    sink = io.BytesIO()
    fetch = client.get_to_file("https://example.invalid/x", sink)
    assert fetch.status_code == 200 and fetch.attempts == 2
    assert sink.getvalue() == b"second try"
    assert len(calls) == 2
    # Retry-After was honored (0 second delay) rather than exponential backoff.
    assert sleeps == [0.0]


def test_transient_5xx_retries_then_succeeds():
    transport, calls = handler(
        (503, {}, b""),
        (502, {}, b""),
        (200, {}, b"third time lucky"),
    )
    client = make_client(transport)
    sink = io.BytesIO()
    fetch = client.get_to_file("https://example.invalid/x", sink)
    assert fetch.status_code == 200 and fetch.attempts == 3
    assert len(calls) == 3


def test_deterministic_404_fails_immediately_without_retry():
    transport, calls = handler(*[(404, {}, b"not found")])
    client = make_client(transport)
    sink = io.BytesIO()
    with pytest.raises(HttpAcquisitionError) as error:
        client.get_to_file("https://example.invalid/missing", sink)
    assert error.value.failure_class == "deterministic_http"
    assert error.value.attempts == 1
    assert error.value.retryable is False
    assert error.value.http_status == 404
    assert len(calls) == 1


def test_timeout_retries_then_reports_exhaustion():
    def timeout_handler(request):
        raise httpx.ReadTimeout("timed out")

    transport = httpx.MockTransport(timeout_handler)
    client = make_client(transport, max_attempts=3)
    sink = io.BytesIO()
    with pytest.raises(HttpAcquisitionError) as error:
        client.get_to_file("https://example.invalid/slow", sink)
    assert error.value.failure_class == "retry_exhausted"
    assert error.value.attempts == 3
    assert error.value.retryable is True


def test_network_error_exhausts_the_retry_budget():
    def network_handler(request):
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(network_handler)
    client = make_client(transport, max_attempts=1)
    sink = io.BytesIO()
    with pytest.raises(HttpAcquisitionError) as error:
        client.get_to_file("https://example.invalid/unreachable", sink)
    # A single attempt means the bounded retry budget is exhausted; the
    # underlying class was network and the error stays retryable.
    assert error.value.failure_class == "retry_exhausted"
    assert error.value.attempts == 1
    assert error.value.retryable is True
    assert "ConnectError" in str(error.value)


def test_retry_exhaustion_reports_attempts_and_last_status():
    transport, calls = handler(*[(503, {}, b""), (503, {}, b"")])
    client = make_client(transport, max_attempts=2)
    sink = io.BytesIO()
    with pytest.raises(HttpAcquisitionError) as error:
        client.get_to_file("https://example.invalid/down", sink)
    assert error.value.failure_class == "retry_exhausted"
    assert error.value.attempts == 2
    assert error.value.http_status == 503
    assert len(calls) == 2


def test_per_source_rate_limiter_spaces_requests():
    limiter = RateLimiter(requests_per_second=20, max_concurrency=2)
    clock = {"now": 0.0}
    sleeps = []

    def fake_clock():
        return clock["now"]

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += seconds

    limiter._clock = fake_clock
    limiter._sleep = fake_sleep
    with limiter.request():
        clock["now"] += 0.001
    with limiter.request():
        clock["now"] += 0.001
    with limiter.request():
        pass
    assert sleeps, "the second and third requests must be spaced by the limiter"
    assert all(0 < s <= 0.05 for s in sleeps)
    assert len(sleeps) == 2


def test_rate_policy_caps_nlm_hosts_at_published_ceiling():
    policy = rate_policy(requests_per_second=100.0, host="uts-ws.nlm.nih.gov")
    assert policy._min_interval >= 1.0 / NLM_RPS_CEILING
    uncapped = rate_policy(requests_per_second=2.0, host="uts-ws.nlm.nih.gov")
    assert uncapped._min_interval == 0.5
    foreign = rate_policy(requests_per_second=50.0, host="api.example.invalid")
    assert foreign._min_interval < 1.0 / 20.0


def test_source_specific_user_agent_is_sent():
    transport, calls = handler(*[(200, {}, b"ok")])
    client = make_client(transport, user_agent="kemirix/rxnorm_athena")
    sink = io.BytesIO()
    client.get_to_file("https://example.invalid/x", sink)
    assert calls[0].headers["user-agent"] == "kemirix/rxnorm_athena"
    assert "dailymed" not in calls[0].headers["user-agent"]


def test_default_user_agent_carries_the_source():
    transport, calls = handler(*[(200, {}, b"ok")])
    client = make_client(transport)
    sink = io.BytesIO()
    client.get_to_file("https://example.invalid/x", sink)
    assert calls[0].headers["user-agent"] == "kemirix/dailymed"


def test_non_https_urls_are_refused():
    transport, _ = handler(*[(200, {}, b"ok")])
    client = make_client(transport)
    with pytest.raises(SourceContractError, match="HTTPS"):
        client.get_to_file("http://example.invalid/x", io.BytesIO())


def test_result_model_validation():
    good = AcquisitionResult(
        lane_id="S06",
        source_id="dailymed",
        source_version="v1",
        source_record_key="setid-1",
        status="succeeded",
        started_at="2026-09-09T00:00:00+00:00",
        finished_at="2026-09-09T00:00:01+00:00",
    )
    assert good.status == "succeeded"
    assert good.artifact_keys == () and good.attempts == 1
    with pytest.raises(Exception):
        AcquisitionResult.model_validate(
            {
                **good.model_dump(),
                "api_key": "no secrets allowed",
            }
        )
    with pytest.raises(Exception):
        AcquisitionResult.model_validate({**good.model_dump(), "status": "maybe"})
    with pytest.raises(Exception):
        AcquisitionResult.model_validate({**good.model_dump(), "failure_class": "not-a-class"})
    with pytest.raises(Exception):
        AcquisitionResult.model_validate({**good.model_dump(), "lane_id": "S06 "})


def test_local_file_acquisition_vaults_without_network(tmp_path):
    source = tmp_path / "manual.pdf"
    source.write_bytes(b"official manual document")
    store = FakeStore()
    result = acquire_file_to_vault(
        store=store,
        source_path=source,
        lane_id="S10",
        source_id="keml",
        source_version="2026-09",
        source_record_key="KEML_DOC",
        original_filename="keml.pdf",
        content_type="application/pdf",
        adapter_git_sha="b" * 40,
        expected_sha256=hashlib.sha256(b"official manual document").hexdigest(),
        rights_status="cleared",
    )
    assert result.status == "succeeded"
    assert result.artifact_keys == ("keml/2026-09/KEML_DOC/original/keml.pdf",)
    assert result.manifest_key == "keml/2026-09/KEML_DOC/manifest.json"


def test_local_file_with_wrong_expected_hash_fails_before_upload(tmp_path):
    source = tmp_path / "release.zip"
    source.write_bytes(b"not what the operator pinned")
    store = FakeStore()
    result = acquire_file_to_vault(
        store=store,
        source_path=source,
        lane_id="S02",
        source_id="athena_extension",
        source_version="v1",
        source_record_key="__release__",
        original_filename="vocab.zip",
        content_type="application/zip",
        adapter_git_sha="b" * 40,
        expected_sha256="0" * 64,
    )
    assert result.status == "failed"
    assert result.failure_class == "storage"
    assert store.calls == []


def test_parser_reads_the_stored_original_not_the_network_bytes():
    transport, _ = handler(*[(200, {"content-type": "text/plain"}, b"network copy")])
    store = FakeStore()
    client = make_client(transport)
    result = acquire_url_to_vault(
        client=client,
        store=store,
        url="https://example.invalid/doc.txt",
        lane_id="S06",
        source_id="dailymed",
        source_version="v1",
        source_record_key="setid-1",
        original_filename="doc.txt",
        content_type="text/plain",
        adapter_git_sha="a" * 40,
    )
    assert result.status == "succeeded"
    # Tamper the in-memory "network" buffer conceptually: the parser must
    # receive the bytes the STORE holds.
    seen = {}

    def parser(destination):
        seen["bytes"] = destination.read()

    parse_result = parse_stored_original(
        store=store,
        identity=IDENTITY,
        object_key="dailymed/v1/setid-1/original/doc.txt",
        destination=io.BytesIO(),
        parser=parser,
    )
    assert parse_result.status == "succeeded"
    assert seen["bytes"] == b"network copy"
    assert ("get", "dailymed/v1/setid-1/original/doc.txt") in store.calls


def test_parser_failure_preserves_the_raw_original():
    store = FakeStore({"dailymed/v1/setid-1/original/doc.txt": b"precious raw"})
    manifest_json = b'{"stored": "manifest"}'
    store.objects["dailymed/v1/setid-1/manifest.json"] = manifest_json

    def broken_parser(destination):
        raise ValueError("parser exploded")

    result = parse_stored_original(
        store=store,
        identity=IDENTITY,
        object_key="dailymed/v1/setid-1/original/doc.txt",
        destination=io.BytesIO(),
        parser=broken_parser,
    )
    assert result.status == "failed"
    assert result.failure_class == "parse"
    # The raw original and its manifest remain fully preserved.
    assert store.objects["dailymed/v1/setid-1/original/doc.txt"] == b"precious raw"
    assert store.objects["dailymed/v1/setid-1/manifest.json"] == manifest_json


def test_http_failure_leaves_no_manifest_and_reports_the_class():
    transport, _ = handler(*[(404, {}, b"missing")])
    store = FakeStore()
    client = make_client(transport)
    result = acquire_url_to_vault(
        client=client,
        store=store,
        url="https://example.invalid/gone.xml",
        lane_id="S06",
        source_id="dailymed",
        source_version="v1",
        source_record_key="setid-1",
        original_filename="gone.xml",
        content_type="application/xml",
        adapter_git_sha="a" * 40,
    )
    assert result.status == "failed"
    assert result.failure_class == "deterministic_http"
    assert result.http_status == 404
    assert result.manifest_key is None
    assert store.calls == []


def test_storage_conflict_during_acquisition_reports_storage_failure():
    transport, _ = handler(*[(200, {"content-type": "text/plain"}, b"bytes")])
    store = FakeStore({"dailymed/v1/setid-1/original/doc.txt": b"different old bytes"})
    client = make_client(transport)
    result = acquire_url_to_vault(
        client=client,
        store=store,
        url="https://example.invalid/doc.txt",
        lane_id="S06",
        source_id="dailymed",
        source_version="v1",
        source_record_key="setid-1",
        original_filename="doc.txt",
        content_type="text/plain",
        adapter_git_sha="a" * 40,
    )
    assert result.status == "failed"
    assert result.failure_class == "storage"
    assert store.calls == [("put", "dailymed/v1/setid-1/original/doc.txt")]
    # No manifest was written for the failed record.
    assert all(call[0] != "manifest" for call in store.calls)


def test_adapter_boundary_refuses_kmx_and_evidence_work():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    config = load_source_configs(root)[5]  # S06 dailymed
    adapter = SourceAdapter(config)
    assert adapter.validate()["source_id"] == "dailymed"
    with pytest.raises(NotImplementedError):
        adapter.resolve_kmx(object())
    with pytest.raises(NotImplementedError):
        adapter.create_source_blocks(object())
    with pytest.raises(NotImplementedError):
        adapter.build_full_evidence(object())
    with pytest.raises(NotImplementedError):
        adapter.acquire()
    with pytest.raises(NotImplementedError):
        adapter.iter_source_items()
    with pytest.raises(SourceContractError):
        SourceAdapter({"not": "a config"})


def test_adapter_verify_hash_streams_and_compares(tmp_path):
    root = pathlib.Path(__file__).resolve().parents[1]
    config = load_source_configs(root)[5]
    adapter = SourceAdapter(config)
    artifact = tmp_path / "x.bin"
    artifact.write_bytes(b"artifact")
    digest = hashlib.sha256(b"artifact").hexdigest()
    assert adapter.verify_hash(artifact, digest) == digest
    with pytest.raises(StorageContractError):
        adapter.verify_hash(artifact, "0" * 64)


def test_adapter_save_original_uses_the_frozen_vault_contract(tmp_path):
    root = pathlib.Path(__file__).resolve().parents[1]
    config = load_source_configs(root)[5]
    store = FakeStore()
    adapter = SourceAdapter(config, store=store)
    artifact = tmp_path / "spl.xml"
    artifact.write_bytes(b"<spl/>")
    adapter.save_original(
        source_path=artifact,
        source_version="v9",
        source_record_key="setid-9",
        original_filename="spl.xml",
        expected_sha256=hashlib.sha256(b"<spl/>").hexdigest(),
        adapter_git_sha="a" * 40,
    )
    assert store.objects["dailymed/v9/setid-9/original/spl.xml"] == b"<spl/>"


def test_real_store_download_to_streams_the_stored_original():
    import boto3
    from botocore.response import StreamingBody
    from botocore.stub import Stubber

    from storage.client import S3RawObjectStore

    client = boto3.client(
        "s3",
        region_name="gra",
        endpoint_url="https://s3.invalid",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    stubber = Stubber(client)
    store = S3RawObjectStore(client, "kemirix-knowledge-raw")
    data = b"the stored original"
    stubber.add_response(
        "get_object",
        {"Body": StreamingBody(io.BytesIO(data), len(data))},
        {"Bucket": "kemirix-knowledge-raw", "Key": "dailymed/v1/setid-1/original/spl.xml"},
    )
    sink = io.BytesIO()
    with stubber:
        assert store.download_to("dailymed/v1/setid-1/original/spl.xml", sink) == len(data)
    assert sink.getvalue() == data


def test_no_rule_logic_enters_the_framework():
    import inspect

    import sources.acquisition as acquisition_module
    import sources.base as base_module
    import sources.http as http_module

    for module in (acquisition_module, base_module, http_module):
        source = inspect.getsource(module)
        assert "clinical_rule" not in source
        assert "rule_evidence" not in source
        assert "RuleOutcome" not in source
        assert "evidence_support" not in source
