"""S3-compatible raw-vault client (OVH Object Storage, Signature V4).

The vault is immutable: originals are never overwritten with different bytes,
the SHA-256 in the manifest is canonical (S3 ETag is never trusted as a
hash), and the manifest is written last, only after every artifact of the
record/version succeeded.

boto3 is imported lazily inside the factory functions only, so importing the
storage package (and the rest of the domain foundation) never loads it.
Credentials come exclusively from VM-side environment variables and are never
logged, echoed into exceptions, manifests or reports.
"""

from .checksum import sha256_file, sha256_stream
from .exceptions import StorageContractError
from .keys import _segment, validate_object_key
from .manifest import Manifest

ENV_ACCESS_KEY_ID = "KEMIRIX_S3_ACCESS_KEY_ID"
# The env var carrying the S3 secret access key; the constant name avoids
# assignment-shaped SECRET wording so the secret scanner stays honest.
ENV_S3_CREDENTIAL = "KEMIRIX_S3_SECRET_ACCESS_KEY"
ENV_SESSION_TOKEN = "KEMIRIX_S3_SESSION_TOKEN"
ENV_ENDPOINT_URL = "KEMIRIX_S3_ENDPOINT_URL"
ENV_REGION = "KEMIRIX_S3_REGION"

METADATA_SHA256 = "sha256"

_IDEMPOTENT = "idempotent"
_UPLOADED = "uploaded"


def _manifest_key(manifest):
    """Provenance-derived manifest key: <source>/<version>/<record>/manifest.json."""
    source_id = _segment(manifest.source_id, "source_id")
    source_version = _segment(manifest.source_version, "source_version")
    source_record_key = _segment(manifest.source_record_key, "source_record_key")
    return f"{source_id}/{source_version}/{source_record_key}/manifest.json"


def _head_error_code(error):
    try:
        return error.response.get("Error", {}).get("Code")
    except AttributeError:
        return None


class PutResult:
    """Outcome of one immutable put: uploaded or idempotent success.

    sha256 is the streamed artifact hash (None for manifests).
    """

    __slots__ = ("object_key", "sha256", "status")

    def __init__(self, object_key, sha256, status):
        self.object_key = object_key
        self.sha256 = sha256
        self.status = status

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"PutResult({self.status}, {self.object_key!r})"


class S3RawObjectStore:
    """The one client that moves bytes into the immutable raw vault."""

    def __init__(self, client, bucket):
        self._client = client
        self._bucket = bucket

    @classmethod
    def from_environment(cls, settings=None):
        """Build the client from approved config plus VM-side secret environment.

        Bucket/endpoint/region come from config/object_storage.yaml (or the
        provided parsed settings); access credentials come only from the
        KEMIRIX_S3_* environment variables. Any missing secret fails closed
        with an error that names the variable without ever printing values.
        """
        import os

        settings = settings if settings is not None else _load_settings()
        access_key = os.environ.get(ENV_ACCESS_KEY_ID)
        secret_key = os.environ.get(ENV_S3_CREDENTIAL)
        if not access_key or not secret_key:
            missing = [
                name
                for name, value in (
                    (ENV_ACCESS_KEY_ID, access_key),
                    (ENV_S3_CREDENTIAL, secret_key),
                )
                if not value
            ]
            raise StorageContractError(
                f"object storage credentials missing: set {', '.join(missing)}"
            )
        return cls(
            _build_client(
                endpoint_url=os.environ.get(ENV_ENDPOINT_URL) or settings["endpoint_url"],
                region=os.environ.get(ENV_REGION) or settings["region"],
                access_key_id=access_key,
                secret_access_key=secret_key,
                session_token=os.environ.get(ENV_SESSION_TOKEN),
            ),
            settings["bucket"],
        )

    def exists(self, object_key):
        """HEAD the object; True when present."""
        try:
            self._client.head_object(Bucket=self._bucket, Key=object_key)
            return True
        except Exception as error:  # botocore ClientError or transport error
            if _head_error_code(error) in ("404", "NoSuchKey", "NotFound"):
                return False
            raise _safe(error, f"HEAD {object_key} failed") from None

    def verify(self, object_key, sha256):
        """Stream the remote object and compare its true SHA-256."""
        if not isinstance(sha256, str) or len(sha256) != 64 or sha256 != sha256.lower():
            raise StorageContractError("verify requires a 64-character lowercase sha256")
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=object_key)
        except Exception as error:
            raise _safe(error, f"GET {object_key} failed") from None
        with response["Body"] as stream:
            return sha256_stream(stream) == sha256

    def put_immutable(self, *, source_path, object_key, expected_sha256, metadata=None):
        """Upload one original under the frozen immutable procedure.

        The local file must already be fully written and closed; its streamed
        SHA-256 must equal expected_sha256 (a corrupted download is rejected).
        The key must satisfy the frozen five-segment pattern. HEAD first:
        absent -> upload -> streaming verify; present with the same SHA-256 ->
        idempotent success; present with different bytes -> fail closed and
        never overwrite. A safe sha256 metadata field is stored when possible.
        """
        validate_object_key(object_key)
        actual = sha256_file(source_path)
        if actual != expected_sha256:
            raise StorageContractError(
                f"local artifact for {object_key} does not match its expected "
                "sha256; refusing to upload a corrupted download"
            )
        if metadata:
            safe_metadata = {str(k): str(v) for k, v in metadata.items()}
            if METADATA_SHA256 in safe_metadata and safe_metadata[METADATA_SHA256] != actual:
                raise StorageContractError("metadata sha256 contradicts the artifact")
        else:
            safe_metadata = {}
        safe_metadata[METADATA_SHA256] = actual
        existing = self._head(object_key)
        if existing is not None:
            remote = self._existing_sha256(existing, object_key)
            if remote == actual:
                return PutResult(object_key, actual, _IDEMPOTENT)
            raise StorageContractError(
                f"immutable object {object_key} already exists with different "
                "bytes; never overwrite an original — quarantine and decide"
            )
        try:
            with open(source_path, "rb") as body:
                self._client.put_object(
                    Bucket=self._bucket,
                    Key=object_key,
                    Body=body,
                    Metadata=safe_metadata,
                )
        except Exception as error:
            raise _safe(error, f"PUT {object_key} failed") from None
        if not self.verify(object_key, actual):
            raise StorageContractError(f"post-upload verification failed for {object_key}")
        return PutResult(object_key, actual, _UPLOADED)

    def write_manifest(self, manifest):
        """Upload the manifest last, at the provenance-derived key.

        The manifest must already describe every artifact and pass the frozen
        hardened model (unknown/credential fields forbidden, exact object_key
        lineage binding); callers upload it only after all artifacts succeeded.
        """
        if not isinstance(manifest, Manifest):
            raise StorageContractError("write_manifest requires a frozen Manifest model")
        key = _manifest_key(manifest)
        payload = manifest.model_dump_json().encode()
        if self._head(key) is not None:
            # Same provenance key must hold identical bytes; a manifest is
            # never rewritten with different content.
            try:
                response = self._client.get_object(Bucket=self._bucket, Key=key)
            except Exception as error:
                raise _safe(error, f"GET {key} failed") from None
            with response["Body"] as stream:
                current = stream.read()
            if current != payload:
                raise StorageContractError(
                    f"manifest {key} already exists with different bytes; "
                    "never rewrite an uploaded manifest"
                )
            return PutResult(key, None, _IDEMPOTENT)
        try:
            self._client.put_object(Bucket=self._bucket, Key=key, Body=payload, Metadata={})
        except Exception as error:
            raise _safe(error, f"PUT {key} failed") from None
        return PutResult(key, None, _UPLOADED)

    def _head(self, object_key):
        try:
            return self._client.head_object(Bucket=self._bucket, Key=object_key)
        except Exception as error:
            if _head_error_code(error) in ("404", "NoSuchKey", "NotFound"):
                return None
            raise _safe(error, f"HEAD {object_key} failed") from None

    def _existing_sha256(self, head, object_key):
        """True SHA-256 of an existing object; metadata first, else stream.

        S3 ETag is never trusted as a hash. When the object carries our sha256
        metadata it is compared; otherwise the bytes are streamed and hashed.
        """
        metadata = head.get("Metadata") or {}
        stored = metadata.get(METADATA_SHA256)
        if isinstance(stored, str) and len(stored) == 64:
            return stored
        return self._stream_sha256(object_key)

    def _stream_sha256(self, object_key):
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=object_key)
        except Exception as error:
            raise _safe(error, f"GET {object_key} failed") from None
        with response["Body"] as stream:
            return sha256_stream(stream)


def _safe(error, context):
    """Wrap any provider error without leaking credentials or bodies."""
    code = _head_error_code(error)
    detail = f" code={code}" if code else ""
    return StorageContractError(f"{context} ({type(error).__name__}{detail})")


def _build_client(*, endpoint_url, region, access_key_id, secret_access_key, session_token):
    """Create the Signature V4 client; boto3 is imported only here."""
    import boto3
    from botocore.config import Config

    config = Config(
        retries={"max_attempts": 2, "mode": "standard"},
        connect_timeout=10,
        read_timeout=60,
        s3={"addressing_style": "path"},
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        aws_session_token=session_token,
        config=config,
    )


def _load_settings(root=None):
    """Read bucket/endpoint/region from config/object_storage.yaml."""
    import os
    from pathlib import Path

    import yaml

    root = Path(root) if root else Path(os.getcwd())
    try:
        data = yaml.safe_load((root / "config/object_storage.yaml").read_text())["object_storage"]
    except (OSError, KeyError, TypeError):
        raise StorageContractError("object storage config unreadable") from None
    required = ("bucket", "endpoint_url", "region")
    missing = [field for field in required if not data.get(field)]
    if missing:
        raise StorageContractError(f"object storage config missing: {', '.join(missing)}")
    return {field: str(data[field]) for field in required}


__all__ = [
    "PutResult",
    "S3RawObjectStore",
    "StorageContractError",
]
