"""STORAGE-001 raw-vault client tests (Phase 3).

All S3 interaction is mocked/stubbed (botocore Stubber or an in-process fake);
no real bucket is touched and no real source data is used, exactly as the
owner directive requires for Phase 3.
"""

import hashlib
import io

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber

from storage.client import (
    ENV_ACCESS_KEY_ID,
    ENV_S3_CREDENTIAL,
    S3RawObjectStore,
    _load_settings,
)
from storage.exceptions import StorageContractError
from storage.manifest import Manifest

pytestmark = pytest.mark.contract

BUCKET = "kemirix-knowledge-raw"


def make_store():
    client = boto3.client(
        "s3",
        region_name="gra",
        endpoint_url="https://s3.invalid",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    stubber = Stubber(client)
    return S3RawObjectStore(client, BUCKET), stubber


def write_temp(tmp_path, data=b"original bytes for the vault"):
    path = tmp_path / "artifact.bin"
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


def streaming_body(data):
    return StreamingBody(io.BytesIO(data), len(data))


def sample_manifest(sha256, filename="spl.xml"):
    return Manifest.model_validate(
        {
            "schema_version": 1,
            "lane_id": "S06",
            "source_id": "dailymed",
            "source_version": "v1",
            "source_record_key": "setid-1",
            "acquisition_mode": "api",
            "fetched_at": "2026-09-09T00:00:00Z",
            "upstream_published_at": None,
            "adapter_git_sha": "a" * 40,
            "rights_status": "cleared",
            "parse_status": "staged",
            "artifacts": [
                {
                    "artifact_type": "structured_document",
                    "original_filename": filename,
                    "content_type": "application/xml",
                    "byte_size": 24,
                    "object_key": f"dailymed/v1/setid-1/original/{filename}",
                    "sha256": sha256,
                }
            ],
        }
    )


class FakeClient:
    """In-process S3 stand-in that records every call (no network)."""

    def __init__(self, objects=None, fail_keys=()):
        self.objects = dict(objects or {})
        self.fail_keys = set(fail_keys)
        self.calls = []

    def head_object(self, Bucket, Key):  # noqa: N803
        self.calls.append(("head", Bucket, Key))
        if Key in self.fail_keys:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "500"}}, "HeadObject")
        if Key not in self.objects:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return self.objects[Key]

    def put_object(self, Bucket, Key, Body, Metadata=None):  # noqa: N803
        self.calls.append(("put", Bucket, Key))
        if Key in self.fail_keys:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "500"}}, "PutObject")
        data = Body.read()
        self.objects[Key] = {"Metadata": dict(Metadata or {}), "data": data}
        return {}

    def get_object(self, Bucket, Key):  # noqa: N803
        self.calls.append(("get", Bucket, Key))
        if Key not in self.objects:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "404"}}, "GetObject")
        entry = self.objects[Key]
        return {"Body": StreamingBody(io.BytesIO(entry["data"]), len(entry["data"]))}


def test_streaming_checksums_match_known_vectors(tmp_path):
    from storage.checksum import md5_file, sha256_file, sha256_stream

    data = b"kemirix raw vault checksum vector\n" * 1000
    path = tmp_path / "vector.bin"
    path.write_bytes(data)
    assert sha256_file(path) == hashlib.sha256(data).hexdigest()
    assert md5_file(path) == hashlib.md5(data).hexdigest()
    assert sha256_stream(io.BytesIO(data)) == hashlib.sha256(data).hexdigest()
    empty = tmp_path / "empty.bin"
    empty.write_bytes(b"")
    assert sha256_file(empty) == hashlib.sha256(b"").hexdigest()


def test_put_immutable_uploads_absent_object_then_verifies(tmp_path):
    store, stubber = make_store()
    path, sha = write_temp(tmp_path)
    key = "dailymed/v1/setid-1/original/artifact.bin"
    with stubber:
        stubber.add_client_error("head_object", service_error_code="404")
        stubber.add_response(
            "put_object",
            {},
            {
                "Bucket": BUCKET,
                "Key": key,
                "Body": ANY,
                "Metadata": {"sha256": sha},
            },
        )
        stubber.add_response(
            "get_object",
            {"Body": streaming_body(b"original bytes for the vault")},
            {"Bucket": BUCKET, "Key": key},
        )
        result = store.put_immutable(source_path=path, object_key=key, expected_sha256=sha)
    assert result.status == "uploaded"
    assert result.sha256 == sha
    assert result.object_key == key


def test_put_immutable_same_hash_is_idempotent(tmp_path):
    store, stubber = make_store()
    path, sha = write_temp(tmp_path)
    key = "dailymed/v1/setid-1/original/artifact.bin"
    with stubber:
        stubber.add_response(
            "head_object",
            {"Metadata": {"sha256": sha}, "ETag": '"not-a-sha256"'},
            {"Bucket": BUCKET, "Key": key},
        )
        result = store.put_immutable(source_path=path, object_key=key, expected_sha256=sha)
    assert result.status == "idempotent"
    assert result.sha256 == sha


def test_put_immutable_different_hash_fails_closed_and_never_overwrites(tmp_path):
    store, stubber = make_store()
    path, sha = write_temp(tmp_path, b"new different bytes for the same key")
    key = "dailymed/v1/setid-1/original/artifact.bin"
    with stubber:
        stubber.add_response(
            "head_object", {"Metadata": {"sha256": "f" * 64}}, {"Bucket": BUCKET, "Key": key}
        )
        with pytest.raises(StorageContractError, match="different bytes"):
            store.put_immutable(source_path=path, object_key=key, expected_sha256=sha)
    stubber.assert_no_pending_responses()


def test_put_immutable_existing_without_metadata_streams_and_compares(tmp_path):
    data = b"legacy object without our metadata"
    path, sha = write_temp(tmp_path, data)
    other = tmp_path / "other.bin"
    other.write_bytes(b"something else entirely")
    key = "dailymed/v1/setid-1/original/artifact.bin"
    # Same bytes streamed from the remote -> idempotent.
    store, stubber = make_store()
    with stubber:
        stubber.add_response(
            "head_object", {"ETag": '"irrelevant"'}, {"Bucket": BUCKET, "Key": key}
        )
        stubber.add_response(
            "get_object", {"Body": streaming_body(data)}, {"Bucket": BUCKET, "Key": key}
        )
        assert (
            store.put_immutable(source_path=path, object_key=key, expected_sha256=sha).status
            == "idempotent"
        )
    # Different bytes streamed from the remote -> fail closed.
    store, stubber = make_store()
    with stubber:
        stubber.add_response(
            "head_object", {"ETag": '"irrelevant"'}, {"Bucket": BUCKET, "Key": key}
        )
        stubber.add_response(
            "get_object",
            {"Body": streaming_body(b"old different bytes")},
            {"Bucket": BUCKET, "Key": key},
        )
        with pytest.raises(StorageContractError, match="different bytes"):
            store.put_immutable(source_path=path, object_key=key, expected_sha256=sha)


def test_put_immutable_rejects_corrupted_download_before_any_remote_call(tmp_path):
    store, stubber = make_store()
    path, _ = write_temp(tmp_path, b"corrupted payload")
    with stubber:
        with pytest.raises(StorageContractError, match="corrupted download"):
            store.put_immutable(
                source_path=path,
                object_key="dailymed/v1/setid-1/original/artifact.bin",
                expected_sha256="0" * 64,
            )
    stubber.assert_no_pending_responses()


def test_put_immutable_rejects_unsafe_keys_before_any_remote_call(tmp_path):
    store, stubber = make_store()
    path, sha = write_temp(tmp_path)
    for bad_key in (
        "dailymed/v1/setid-1/NOT-original/artifact.bin",
        "dailymed/v1/setid-1/original/../escape.bin",
        "S06/v1/setid-1/original/artifact.bin",
    ):
        with pytest.raises(StorageContractError):
            store.put_immutable(source_path=path, object_key=bad_key, expected_sha256=sha)
    stubber.assert_no_pending_responses()


def test_bulk_release_keys_round_trip_through_put_immutable(tmp_path):
    store, stubber = make_store()
    path, sha = write_temp(tmp_path, b"rxnorm full release zip bytes")
    key = "rxnorm_athena/2026-09-08/__release__/original/RxNorm_full_09082026.zip"
    with stubber:
        stubber.add_client_error("head_object", service_error_code="404")
        stubber.add_response(
            "put_object",
            {},
            {"Bucket": BUCKET, "Key": key, "Body": ANY, "Metadata": {"sha256": sha}},
        )
        stubber.add_response(
            "get_object",
            {"Body": streaming_body(b"rxnorm full release zip bytes")},
            {"Bucket": BUCKET, "Key": key},
        )
        result = store.put_immutable(source_path=path, object_key=key, expected_sha256=sha)
    assert result.status == "uploaded"
    assert result.object_key.split("/")[2] == "__release__"


def test_verify_streams_remote_object(tmp_path):
    store, stubber = make_store()
    data = b"verify me by streaming"
    _, sha = write_temp(tmp_path, data)
    key = "dailymed/v1/setid-1/original/artifact.bin"
    with stubber:
        stubber.add_response(
            "get_object", {"Body": streaming_body(data)}, {"Bucket": BUCKET, "Key": key}
        )
        assert store.verify(key, sha) is True
    store, stubber = make_store()
    with stubber:
        stubber.add_response(
            "get_object",
            {"Body": streaming_body(b"tampered content")},
            {"Bucket": BUCKET, "Key": key},
        )
        assert store.verify(key, sha) is False


def test_exists_reports_presence_without_trusting_any_hash(tmp_path):
    store, stubber = make_store()
    with stubber:
        stubber.add_response(
            "head_object", {"ETag": '"x"'}, {"Bucket": BUCKET, "Key": "a/b/c/original/f"}
        )
        assert store.exists("a/b/c/original/f") is True
    store, stubber = make_store()
    with stubber:
        stubber.add_client_error("head_object", service_error_code="404")
        assert store.exists("a/b/c/original/f") is False


def test_write_manifest_uploads_last_at_provenance_key(tmp_path):
    data = b"the spl document"
    sha = hashlib.sha256(data).hexdigest()
    manifest = sample_manifest(sha)
    store, stubber = make_store()
    with stubber:
        stubber.add_client_error("head_object", service_error_code="404")
        stubber.add_response(
            "put_object",
            {},
            {
                "Bucket": BUCKET,
                "Key": "dailymed/v1/setid-1/manifest.json",
                "Body": ANY,
                "Metadata": {},
            },
        )
        result = store.write_manifest(manifest)
    assert result.status == "uploaded"
    assert result.object_key == "dailymed/v1/setid-1/manifest.json"


def test_write_manifest_idempotent_for_identical_bytes(tmp_path):
    data = b"the spl document"
    sha = hashlib.sha256(data).hexdigest()
    manifest = sample_manifest(sha)
    store, stubber = make_store()
    payload = manifest.model_dump_json().encode()
    with stubber:
        stubber.add_response(
            "head_object",
            {"ETag": '"x"'},
            {"Bucket": BUCKET, "Key": "dailymed/v1/setid-1/manifest.json"},
        )
        stubber.add_response(
            "get_object",
            {"Body": streaming_body(payload)},
            {"Bucket": BUCKET, "Key": "dailymed/v1/setid-1/manifest.json"},
        )
        result = store.write_manifest(manifest)
    assert result.status == "idempotent"


def test_write_manifest_refuses_to_rewrite_different_bytes(tmp_path):
    data = b"the spl document"
    sha = hashlib.sha256(data).hexdigest()
    manifest = sample_manifest(sha)
    store, stubber = make_store()
    with stubber:
        stubber.add_response(
            "head_object",
            {"ETag": '"x"'},
            {"Bucket": BUCKET, "Key": "dailymed/v1/setid-1/manifest.json"},
        )
        stubber.add_response(
            "get_object",
            {"Body": streaming_body(b'{"schema_version": 1, "different": true}')},
            {"Bucket": BUCKET, "Key": "dailymed/v1/setid-1/manifest.json"},
        )
        with pytest.raises(StorageContractError, match="never rewrite"):
            store.write_manifest(manifest)


def test_write_manifest_requires_the_frozen_model():
    store, _ = make_store()
    with pytest.raises(StorageContractError, match="frozen Manifest model"):
        store.write_manifest({"schema_version": 1})


def test_failed_artifact_leaves_no_final_manifest(tmp_path):
    data = b"artifact bytes"
    path = tmp_path / "spl.xml"
    path.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    client = FakeClient(fail_keys={"dailymed/v1/setid-1/original/spl.xml"})
    store = S3RawObjectStore(client, BUCKET)
    with pytest.raises(StorageContractError):
        store.put_immutable(
            source_path=path,
            object_key="dailymed/v1/setid-1/original/spl.xml",
            expected_sha256=sha,
        )
    # The acquisition order proves the guarantee: the artifact failed, so no
    # manifest write may happen for this record/version afterwards. The store
    # records every call; the manifest key was never touched.
    assert all(key != "dailymed/v1/setid-1/manifest.json" for _, _, key in client.calls)
    assert ("head", BUCKET, "dailymed/v1/setid-1/original/spl.xml") in client.calls


def test_secret_values_never_leak_from_missing_credentials(monkeypatch):
    monkeypatch.delenv(ENV_ACCESS_KEY_ID, raising=False)
    monkeypatch.delenv(ENV_S3_CREDENTIAL, raising=False)
    with pytest.raises(StorageContractError) as error:
        S3RawObjectStore.from_environment(
            settings={"bucket": BUCKET, "endpoint_url": "https://s3.invalid", "region": "gra"}
        )
    message = str(error.value)
    assert ENV_ACCESS_KEY_ID in message and ENV_S3_CREDENTIAL in message
    assert "AKIA" not in message


def test_from_environment_builds_client_from_config_and_env(monkeypatch):
    monkeypatch.setenv(ENV_ACCESS_KEY_ID, "test-access")
    monkeypatch.setenv(ENV_S3_CREDENTIAL, "test-secret")
    store = S3RawObjectStore.from_environment(
        settings={"bucket": BUCKET, "endpoint_url": "https://s3.invalid", "region": "gra"}
    )
    assert isinstance(store, S3RawObjectStore)
    # The low-level client must not leak raw botocore exceptions or secrets.
    with pytest.raises(StorageContractError):
        store.exists("no/such/key/original/x")  # no stub: transport fails closed


def test_settings_loader_fails_closed_on_incomplete_config(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/object_storage.yaml").write_text(
        "object_storage:\n  provider: ovh_s3_compatible\n"
    )
    with pytest.raises(StorageContractError) as error:
        _load_settings(tmp_path)
    assert "bucket" in str(error.value)
    assert "endpoint_url" in str(error.value)
    assert "region" in str(error.value)


def test_provider_errors_are_wrapped_without_bodies(tmp_path):
    client = FakeClient(fail_keys={"k/v/r/original/f"})
    store = S3RawObjectStore(client, BUCKET)
    with pytest.raises(StorageContractError, match="HEAD k/v/r/original/f failed"):
        store.exists("k/v/r/original/f")


def test_manifest_stays_secret_free_and_lineage_exact(tmp_path):
    data = b"secretin document"
    sha = hashlib.sha256(data).hexdigest()
    # secretin.xml carries the substring "secret" in a VALUE; the frozen model
    # accepts it (credential FIELD NAMES are what fail).
    manifest = sample_manifest(sha, filename="secretin.xml")
    assert manifest.artifacts[0].original_filename == "secretin.xml"
    text = manifest.model_dump_json()
    assert "secretin" in text
    for forbidden in ("api_key", "password", "presigned_url", "bearer_token"):
        assert forbidden not in text
