"""Acquisition-to-vault orchestration (the non-negotiable parser boundary).

    network bytes -> temp -> hash -> immutable Object Storage -> manifest LAST
    -> parser reads the stored original

A parser failure never touches the raw original: the vault is immutable and
the manifest is already durably stored. Operator-provided local files
(manual/bulk lanes) follow the same hash-then-vault path without any network
step. Every outcome is reported through the typed AcquisitionResult.
"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from storage.checksum import sha256_file
from storage.exceptions import StorageContractError
from storage.keys import build_object_key
from storage.manifest import Manifest

from .exceptions import SourceContractError
from .http import HttpAcquisitionError
from .results import STATUS_FAILED, STATUS_SUCCEEDED, AcquisitionResult

CHUNK = 1024 * 1024


def _now():
    return datetime.now(timezone.utc).isoformat()


def _record_result(
    *,
    identity,
    status,
    started,
    attempts=1,
    retryable=False,
    failure_class=None,
    http_status=None,
    artifact_keys=(),
    manifest_key=None,
    detail=None,
):
    return AcquisitionResult(
        lane_id=identity["lane_id"],
        source_id=identity["source_id"],
        source_version=identity["source_version"],
        source_record_key=identity["source_record_key"],
        status=status,
        started_at=started,
        finished_at=_now(),
        attempts=attempts,
        retryable=retryable,
        failure_class=failure_class,
        http_status=http_status,
        artifact_keys=tuple(artifact_keys),
        manifest_key=manifest_key,
        detail=detail,
    )


def _build_manifest(
    *,
    identity,
    acquisition_mode,
    upstream_published_at,
    adapter_git_sha,
    rights_status,
    parse_status,
    artifacts,
):
    return Manifest.model_validate(
        {
            "schema_version": 1,
            "lane_id": identity["lane_id"],
            "source_id": identity["source_id"],
            "source_version": identity["source_version"],
            "source_record_key": identity["source_record_key"],
            "acquisition_mode": acquisition_mode,
            "fetched_at": _now(),
            "upstream_published_at": upstream_published_at,
            "adapter_git_sha": adapter_git_sha,
            "rights_status": rights_status,
            "parse_status": parse_status,
            "artifacts": artifacts,
        }
    )


def _vault_artifact(
    *,
    identity,
    original_filename,
    content_type,
    byte_size,
    object_key,
    sha256,
    artifact_type="original",
):
    return {
        "artifact_type": artifact_type,
        "original_filename": original_filename,
        "content_type": content_type,
        "byte_size": byte_size,
        "object_key": object_key,
        "sha256": sha256,
    }


def _finalize(store, manifest):
    """Write the manifest last; return its key."""
    store.write_manifest(manifest)
    source = manifest.source_id
    version = manifest.source_version
    record = manifest.source_record_key
    return f"{source}/{version}/{record}/manifest.json"


def acquire_url_to_vault(
    *,
    client,
    store,
    url,
    lane_id,
    source_id,
    source_version,
    source_record_key,
    original_filename,
    content_type,
    adapter_git_sha,
    acquisition_mode="api",
    upstream_published_at=None,
    rights_status="pending_review",
    parse_status="staged",
    artifact_type="original",
    extra_headers=None,
):
    """Fetch one URL streamed to temp, then hash, vault and manifest it.

    The parser is NOT part of this function: parsing reads the stored
    original afterwards (see parse_stored_original). A failure anywhere
    before the manifest leaves no final manifest.
    """
    identity = {
        "lane_id": lane_id,
        "source_id": source_id,
        "source_version": source_version,
        "source_record_key": source_record_key,
    }
    started = _now()
    try:
        with tempfile.NamedTemporaryFile(prefix="kemirix-acquire-") as temp:
            fetch = client.get_to_file(url, temp, headers=extra_headers)
            temp.flush()
            path = Path(temp.name)
            sha256 = sha256_file(path)
            byte_size = path.stat().st_size
            object_key = build_object_key(
                source_id, source_version, source_record_key, original_filename
            )
            store.put_immutable(source_path=path, object_key=object_key, expected_sha256=sha256)
            manifest = _build_manifest(
                identity=identity,
                acquisition_mode=acquisition_mode,
                upstream_published_at=upstream_published_at,
                adapter_git_sha=adapter_git_sha,
                rights_status=rights_status,
                parse_status=parse_status,
                artifacts=[
                    _vault_artifact(
                        identity=identity,
                        original_filename=original_filename,
                        content_type=content_type,
                        byte_size=byte_size,
                        object_key=object_key,
                        sha256=sha256,
                        artifact_type=artifact_type,
                    )
                ],
            )
            manifest_key = _finalize(store, manifest)
        return _record_result(
            identity=identity,
            status=STATUS_SUCCEEDED,
            started=started,
            attempts=fetch.attempts,
            http_status=fetch.status_code,
            artifact_keys=[object_key],
            manifest_key=manifest_key,
        )
    except HttpAcquisitionError as error:
        return _record_result(
            identity=identity,
            status=STATUS_FAILED,
            started=started,
            attempts=error.attempts,
            retryable=error.retryable,
            failure_class=error.failure_class,
            http_status=error.http_status,
            detail=str(error),
        )
    except StorageContractError as error:
        return _record_result(
            identity=identity,
            status=STATUS_FAILED,
            started=started,
            failure_class="storage",
            detail=str(error),
        )
    except SourceContractError as error:
        return _record_result(
            identity=identity,
            status=STATUS_FAILED,
            started=started,
            failure_class="configuration",
            detail=str(error),
        )


def acquire_file_to_vault(
    *,
    store,
    source_path,
    lane_id,
    source_id,
    source_version,
    source_record_key,
    original_filename,
    content_type,
    adapter_git_sha,
    expected_sha256=None,
    acquisition_mode="manual",
    upstream_published_at=None,
    rights_status="pending_review",
    parse_status="staged",
    artifact_type="original",
):
    """Vault one operator-provided local file (manual/bulk lanes).

    Same boundary as the network path: hash first, immutable upload, manifest
    last, parse only the stored copy. An optional expected_sha256 (for
    operator-verified downloads) is checked before upload.
    """
    identity = {
        "lane_id": lane_id,
        "source_id": source_id,
        "source_version": source_version,
        "source_record_key": source_record_key,
    }
    started = _now()
    try:
        path = Path(source_path)
        sha256 = sha256_file(path)
        if expected_sha256 is not None and sha256 != expected_sha256:
            raise StorageContractError("operator-provided file does not match its expected sha256")
        object_key = build_object_key(
            source_id, source_version, source_record_key, original_filename
        )
        store.put_immutable(source_path=path, object_key=object_key, expected_sha256=sha256)
        manifest = _build_manifest(
            identity=identity,
            acquisition_mode=acquisition_mode,
            upstream_published_at=upstream_published_at,
            adapter_git_sha=adapter_git_sha,
            rights_status=rights_status,
            parse_status=parse_status,
            artifacts=[
                _vault_artifact(
                    identity=identity,
                    original_filename=original_filename,
                    content_type=content_type,
                    byte_size=path.stat().st_size,
                    object_key=object_key,
                    sha256=sha256,
                    artifact_type=artifact_type,
                )
            ],
        )
        manifest_key = _finalize(store, manifest)
        return _record_result(
            identity=identity,
            status=STATUS_SUCCEEDED,
            started=started,
            artifact_keys=[object_key],
            manifest_key=manifest_key,
        )
    except StorageContractError as error:
        return _record_result(
            identity=identity,
            status=STATUS_FAILED,
            started=started,
            failure_class="storage",
            detail=str(error),
        )
    except SourceContractError as error:
        return _record_result(
            identity=identity,
            status=STATUS_FAILED,
            started=started,
            failure_class="configuration",
            detail=str(error),
        )


def parse_stored_original(*, store, identity, object_key, destination, parser):
    """Run the parser over the STORED original, never the network bytes.

    The vault object is downloaded (streamed) to the destination first; the
    parser then reads only that stored copy. A parser failure is reported as
    a failed result with the parse failure class while the raw original and
    its manifest stay fully preserved in the immutable vault.
    """
    started = _now()
    try:
        store.download_to(object_key, destination)
        if hasattr(destination, "seek"):
            destination.seek(0)
        parser(destination)
    except StorageContractError as error:
        return _record_result(
            identity=identity,
            status=STATUS_FAILED,
            started=started,
            failure_class="storage",
            detail=str(error),
        )
    except Exception as error:
        return _record_result(
            identity=identity,
            status=STATUS_FAILED,
            started=started,
            failure_class="parse",
            detail=f"parser failed on the stored original ({type(error).__name__})",
        )
    return _record_result(
        identity=identity,
        status=STATUS_SUCCEEDED,
        started=started,
        artifact_keys=[object_key],
    )
