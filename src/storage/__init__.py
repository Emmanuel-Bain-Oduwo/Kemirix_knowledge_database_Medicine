"""Storage domain core: contract enums, object keys, manifests and the raw vault client."""

from .checksum import md5_file, sha256_file, sha256_stream
from .client import PutResult, S3RawObjectStore
from .exceptions import StorageContractError
from .keys import build_object_key, validate_object_key
from .manifest import Manifest, ManifestArtifact
from .models import AcquisitionMode, ParseStatus, RightsStatus

__all__ = [
    "AcquisitionMode",
    "Manifest",
    "ManifestArtifact",
    "ParseStatus",
    "PutResult",
    "RightsStatus",
    "S3RawObjectStore",
    "StorageContractError",
    "build_object_key",
    "md5_file",
    "sha256_file",
    "sha256_stream",
    "validate_object_key",
]
